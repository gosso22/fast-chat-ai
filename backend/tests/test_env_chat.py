"""
Integration tests for environment-scoped chat endpoints.

Validates requirements:
- 9.3: Chat users can query documents uploaded by admin users
- 9.5: Chat users only access documents within their assigned environment
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
import pytest

from app.db.base import get_db
from app.main import app
from app.models.conversation import Conversation, ChatMessage
from app.models.environment import Environment
from app.models.user_role import UserRole
from app.services.rag_pipeline import RAGResponse
from app.services.rag_service import RetrievalResult
from app.services.llm_providers.base import LLMResponse

_NOW = datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_env(env_id=None, name="test-env"):
    return Environment(
        id=env_id or uuid4(),
        name=name,
        created_by="admin",
        created_at=_NOW,
        updated_at=_NOW,
    )


def _make_role(user_id, role, environment_id):
    return UserRole(
        id=uuid4(),
        user_id=user_id,
        role=role,
        environment_id=environment_id,
        created_at=_NOW,
    )


def _mock_db():
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()
    db.delete = AsyncMock()
    db.close = AsyncMock()
    db.add = MagicMock()
    db.get = AsyncMock()
    return db


def _mock_rag_response():
    retrieval = RetrievalResult(
        query="test",
        chunks=[],
        total_tokens=50,
        processing_time=0.5,
        embedding_time=0.1,
        search_time=0.3,
        ranking_time=0.1,
    )
    llm_resp = LLMResponse(
        content="Answer from docs",
        input_tokens=30,
        output_tokens=20,
        total_tokens=50,
        cost=0.001,
        provider="openai",
        model="gpt-3.5-turbo",
    )
    return RAGResponse(
        query="test",
        response="Answer from docs",
        sources=[],
        retrieval_result=retrieval,
        llm_response=llm_resp,
        processing_time=1.0,
        context_tokens=30,
        response_tokens=20,
        total_cost=0.001,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db():
    return _mock_db()


@pytest.fixture()
def env():
    return _make_env()


@pytest.fixture()
def mock_memory_manager():
    mm = AsyncMock()
    mm.initialize_memory = AsyncMock()
    mm.add_user_message = AsyncMock()
    mm.add_ai_message = AsyncMock()
    return mm


@pytest.fixture()
def mock_rag_pipeline():
    pipeline = AsyncMock()
    pipeline.generate_response = AsyncMock(return_value=_mock_rag_response())
    pipeline.validate_pipeline = AsyncMock(return_value=True)
    return pipeline


@pytest.fixture()
async def client(db, mock_memory_manager, mock_rag_pipeline):
    from app.api.chat import get_memory_manager, get_rag_pipeline

    async def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_memory_manager] = lambda: mock_memory_manager
    app.dependency_overrides[get_rag_pipeline] = lambda: mock_rag_pipeline

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# POST /api/v1/environments/{env_id}/chat/conversations
# ---------------------------------------------------------------------------


class TestStartEnvConversation:
    """Tests for creating conversations within an environment."""

    async def test_chat_user_can_start_conversation(self, db, client, env):
        """Chat user with access can start a conversation (Req 9.3)."""
        role = _make_role("chat1", "chat_user", env.id)

        # 1: validate_environment_exists, 2: require_environment_access
        env_result = MagicMock()
        env_result.scalar_one_or_none.return_value = env
        role_result = MagicMock()
        role_result.scalar_one_or_none.return_value = role

        db.execute.side_effect = [env_result, role_result]

        async def _refresh(obj):
            if not hasattr(obj, "created_at") or obj.created_at is None:
                obj.created_at = _NOW

        db.refresh.side_effect = _refresh

        resp = await client.post(
            f"/api/v1/environments/{env.id}/chat/conversations",
            json={"title": "My Chat"},
            headers={"X-User-ID": "chat1"},
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "My Chat"
        assert data["environment_id"] == str(env.id)
        assert "conversation_id" in data
        db.add.assert_called_once()
        db.commit.assert_called_once()

    async def test_admin_can_start_conversation(self, db, client, env):
        """Admin user can also start conversations (Req 9.3)."""
        role = _make_role("admin1", "admin", env.id)

        env_result = MagicMock()
        env_result.scalar_one_or_none.return_value = env
        role_result = MagicMock()
        role_result.scalar_one_or_none.return_value = role

        db.execute.side_effect = [env_result, role_result]

        async def _refresh(obj):
            if not hasattr(obj, "created_at") or obj.created_at is None:
                obj.created_at = _NOW

        db.refresh.side_effect = _refresh

        resp = await client.post(
            f"/api/v1/environments/{env.id}/chat/conversations",
            json={},
            headers={"X-User-ID": "admin1"},
        )

        assert resp.status_code == 201

    async def test_no_access_returns_403(self, db, client, env):
        """User without role in environment gets 403 (Req 9.5)."""
        env_result = MagicMock()
        env_result.scalar_one_or_none.return_value = env
        role_result = MagicMock()
        role_result.scalar_one_or_none.return_value = None  # no role

        db.execute.side_effect = [env_result, role_result]

        resp = await client.post(
            f"/api/v1/environments/{env.id}/chat/conversations",
            json={"title": "Blocked"},
            headers={"X-User-ID": "outsider"},
        )

        assert resp.status_code == 403
        assert "No access" in resp.json()["detail"]

    async def test_missing_env_returns_404(self, db, client):
        """Non-existent environment returns 404."""
        env_result = MagicMock()
        env_result.scalar_one_or_none.return_value = None

        db.execute.return_value = env_result

        resp = await client.post(
            f"/api/v1/environments/{uuid4()}/chat/conversations",
            json={"title": "Nope"},
            headers={"X-User-ID": "chat1"},
        )

        assert resp.status_code == 404
        assert "Environment not found" in resp.json()["detail"]

    async def test_missing_user_header_returns_422(self, client):
        """Missing X-User-ID header returns 422."""
        resp = await client.post(
            f"/api/v1/environments/{uuid4()}/chat/conversations",
            json={"title": "No header"},
        )

        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/v1/environments/{env_id}/chat/conversations/{conv_id}/messages
# ---------------------------------------------------------------------------


class TestSendEnvMessage:
    """Tests for sending messages in environment-scoped conversations."""

    async def test_send_message_success(
        self, db, client, env, mock_rag_pipeline
    ):
        """Chat user can send a message and get RAG response (Req 9.3)."""
        role = _make_role("chat1", "chat_user", env.id)
        conv_id = uuid4()
        conv = Conversation(
            id=conv_id,
            user_id="chat1",
            title="Test",
            environment_id=env.id,
            created_at=_NOW,
            updated_at=_NOW,
        )

        env_result = MagicMock()
        env_result.scalar_one_or_none.return_value = env
        role_result = MagicMock()
        role_result.scalar_one_or_none.return_value = role

        db.execute.side_effect = [env_result, role_result]
        db.get.return_value = conv

        resp = await client.post(
            f"/api/v1/environments/{env.id}/chat/conversations/{conv_id}/messages",
            json={"message": "What is in the docs?"},
            headers={"X-User-ID": "chat1"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["environment_id"] == str(env.id)
        assert data["response"] == "Answer from docs"
        assert "environment" in data["metadata"]
        assert data["metadata"]["environment"]["environment_id"] == str(env.id)

        # Verify RAG request was scoped to environment
        call_args = mock_rag_pipeline.generate_response.call_args
        rag_req = call_args[0][0]
        assert rag_req.environment_id == env.id

    async def test_conversation_wrong_environment_returns_403(
        self, db, client, env
    ):
        """Conversation belonging to different env returns 403."""
        role = _make_role("chat1", "chat_user", env.id)
        other_env_id = uuid4()
        conv_id = uuid4()
        conv = Conversation(
            id=conv_id,
            user_id="chat1",
            title="Other",
            environment_id=other_env_id,  # different env
        )

        env_result = MagicMock()
        env_result.scalar_one_or_none.return_value = env
        role_result = MagicMock()
        role_result.scalar_one_or_none.return_value = role

        db.execute.side_effect = [env_result, role_result]
        db.get.return_value = conv

        resp = await client.post(
            f"/api/v1/environments/{env.id}/chat/conversations/{conv_id}/messages",
            json={"message": "Hello"},
            headers={"X-User-ID": "chat1"},
        )

        assert resp.status_code == 403
        assert "does not belong" in resp.json()["detail"]

    async def test_no_access_returns_403(self, db, client, env):
        """User without environment access gets 403 (Req 9.5)."""
        env_result = MagicMock()
        env_result.scalar_one_or_none.return_value = env
        role_result = MagicMock()
        role_result.scalar_one_or_none.return_value = None

        db.execute.side_effect = [env_result, role_result]

        resp = await client.post(
            f"/api/v1/environments/{env.id}/chat/conversations/{uuid4()}/messages",
            json={"message": "Blocked"},
            headers={"X-User-ID": "outsider"},
        )

        assert resp.status_code == 403

    async def test_conversation_not_found_returns_404(self, db, client, env):
        """Non-existent conversation returns 404."""
        role = _make_role("chat1", "chat_user", env.id)

        env_result = MagicMock()
        env_result.scalar_one_or_none.return_value = env
        role_result = MagicMock()
        role_result.scalar_one_or_none.return_value = role

        db.execute.side_effect = [env_result, role_result]
        db.get.return_value = None  # conversation not found

        resp = await client.post(
            f"/api/v1/environments/{env.id}/chat/conversations/{uuid4()}/messages",
            json={"message": "Hello"},
            headers={"X-User-ID": "chat1"},
        )

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/v1/environments/{env_id}/chat/conversations
# ---------------------------------------------------------------------------


class TestListEnvConversations:
    """Tests for listing conversations within an environment."""

    async def test_list_conversations_success(self, db, client, env):
        """User can list their conversations in an environment."""
        role = _make_role("chat1", "chat_user", env.id)
        conv = Conversation(
            id=uuid4(),
            user_id="chat1",
            title="Chat 1",
            environment_id=env.id,
            created_at=_NOW,
            updated_at=_NOW,
        )

        env_result = MagicMock()
        env_result.scalar_one_or_none.return_value = env
        role_result = MagicMock()
        role_result.scalar_one_or_none.return_value = role

        # count query
        count_result = MagicMock()
        count_result.scalar.return_value = 1

        # conversations query
        conv_scalars = MagicMock()
        conv_scalars.all.return_value = [conv]
        conv_result = MagicMock()
        conv_result.scalars.return_value = conv_scalars

        # message count
        mc_result = MagicMock()
        mc_result.scalar.return_value = 3

        # last message
        lm_result = MagicMock()
        lm_result.scalar.return_value = "Hello world"

        db.execute.side_effect = [
            env_result,
            role_result,
            count_result,
            conv_result,
            mc_result,
            lm_result,
        ]

        resp = await client.get(
            f"/api/v1/environments/{env.id}/chat/conversations",
            headers={"X-User-ID": "chat1"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["conversations"]) == 1
        assert data["conversations"][0]["title"] == "Chat 1"

    async def test_no_access_returns_403(self, db, client, env):
        """User without access gets 403."""
        env_result = MagicMock()
        env_result.scalar_one_or_none.return_value = env
        role_result = MagicMock()
        role_result.scalar_one_or_none.return_value = None

        db.execute.side_effect = [env_result, role_result]

        resp = await client.get(
            f"/api/v1/environments/{env.id}/chat/conversations",
            headers={"X-User-ID": "outsider"},
        )

        assert resp.status_code == 403

    async def test_empty_list(self, db, client, env):
        """Returns empty list when no conversations exist."""
        role = _make_role("chat1", "chat_user", env.id)

        env_result = MagicMock()
        env_result.scalar_one_or_none.return_value = env
        role_result = MagicMock()
        role_result.scalar_one_or_none.return_value = role

        count_result = MagicMock()
        count_result.scalar.return_value = 0

        conv_scalars = MagicMock()
        conv_scalars.all.return_value = []
        conv_result = MagicMock()
        conv_result.scalars.return_value = conv_scalars

        db.execute.side_effect = [
            env_result,
            role_result,
            count_result,
            conv_result,
        ]

        resp = await client.get(
            f"/api/v1/environments/{env.id}/chat/conversations",
            headers={"X-User-ID": "chat1"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["conversations"] == []


# ---------------------------------------------------------------------------
# Environment isolation: cross-environment access denied
# ---------------------------------------------------------------------------


class TestEnvironmentIsolation:
    """Verify that users cannot access other environments' chats (Req 9.5)."""

    async def test_user_cannot_chat_in_unassigned_env(self, db, client):
        """User assigned to env A cannot start chat in env B."""
        env_b = _make_env(name="env-b")

        env_result = MagicMock()
        env_result.scalar_one_or_none.return_value = env_b
        role_result = MagicMock()
        role_result.scalar_one_or_none.return_value = None  # no role in B

        db.execute.side_effect = [env_result, role_result]

        resp = await client.post(
            f"/api/v1/environments/{env_b.id}/chat/conversations",
            json={"title": "Cross-env attempt"},
            headers={"X-User-ID": "user_in_env_a"},
        )

        assert resp.status_code == 403
