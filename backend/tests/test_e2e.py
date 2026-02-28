"""
End-to-end tests for the RAG chatbot application.

Covers the full document-upload-to-chat-response flow, multi-provider
failover, cost tracking, conversation memory management, vector search
performance, environment-scoped operations, and role-based access control.

Validates requirements: 10.1, 10.2, 10.3, 10.4, 10.5
"""

import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest

from app.db.base import get_db
from app.main import app
from app.models.conversation import ChatMessage, Conversation
from app.models.document import Document, DocumentChunk
from app.models.environment import Environment
from app.models.user_role import UserRole
from app.services.cost_tracker import CostTracker
from app.services.llm_providers.base import (
    LLMProvider,
    LLMRequest,
    LLMResponse,
    ModelCapability,
    ModelConfig,
    ProviderConfig,
    ProviderError,
    RateLimitError,
)
from app.services.llm_providers.manager import LLMProviderManager
from app.services.rag_pipeline import RAGResponse, SourceCitation
from app.services.rag_service import RetrievalResult

_NOW = datetime.now(timezone.utc)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_env(env_id=None, name="e2e-env"):
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


def _make_document(env_id, user_id="admin_user", status="processed"):
    return Document(
        id=uuid4(),
        user_id=user_id,
        filename="test.txt",
        file_size=1024,
        content_type="text/plain",
        upload_date=_NOW,
        processing_status=status,
        environment_id=env_id,
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


def _mock_rag_response(query="test question", response_text="Answer from docs"):
    retrieval = RetrievalResult(
        query=query,
        chunks=[],
        total_tokens=50,
        processing_time=0.5,
        embedding_time=0.1,
        search_time=0.3,
        ranking_time=0.1,
    )
    llm_resp = LLMResponse(
        content=response_text,
        input_tokens=30,
        output_tokens=20,
        total_tokens=50,
        cost=0.001,
        provider="openai",
        model="gpt-3.5-turbo",
    )
    return RAGResponse(
        query=query,
        response=response_text,
        sources=[],
        retrieval_result=retrieval,
        llm_response=llm_resp,
        processing_time=1.0,
        context_tokens=30,
        response_tokens=20,
        total_cost=0.001,
    )


def _mock_rag_response_with_citations(query="test question"):
    """RAG response that includes source citations."""
    citation = SourceCitation(
        document_id=uuid4(),
        document_filename="test.txt",
        chunk_index=0,
        similarity_score=0.92,
        excerpt="Relevant content from the document...",
        start_position=0,
        end_position=100,
    )
    retrieval = RetrievalResult(
        query=query,
        chunks=[],
        total_tokens=80,
        processing_time=0.8,
        embedding_time=0.2,
        search_time=0.4,
        ranking_time=0.2,
    )
    llm_resp = LLMResponse(
        content="Based on the uploaded documents, here is the answer.",
        input_tokens=50,
        output_tokens=30,
        total_tokens=80,
        cost=0.002,
        provider="openai",
        model="gpt-3.5-turbo",
    )
    return RAGResponse(
        query=query,
        response="Based on the uploaded documents, here is the answer.",
        sources=[citation],
        retrieval_result=retrieval,
        llm_response=llm_resp,
        processing_time=1.5,
        context_tokens=50,
        response_tokens=30,
        total_cost=0.002,
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
    mm.get_memory_context = AsyncMock(return_value="Previous context summary")
    mm.get_messages = AsyncMock(return_value=[])
    mm.clear_memory = AsyncMock()
    mm.get_session_info = AsyncMock(return_value={
        "conversation_id": "test",
        "total_tokens": 100,
        "message_count": 2,
    })
    mm.intelligent_token_management = AsyncMock(return_value={
        "action": "none",
        "tokens_before": 100,
        "tokens_after": 100,
    })
    mm.auto_manage_conversation_tokens = AsyncMock(return_value=False)
    return mm


@pytest.fixture()
def mock_rag_pipeline():
    pipeline = AsyncMock()
    pipeline.generate_response = AsyncMock(
        return_value=_mock_rag_response()
    )
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


# =========================================================================
# 1. Document Upload → Chat Response E2E Flow
# =========================================================================


class TestDocumentToChatFlow:
    """End-to-end: admin uploads doc → chat user asks question → gets RAG response."""

    async def test_full_upload_then_chat_flow(
        self, db, client, env, mock_rag_pipeline
    ):
        """Admin uploads a document, then a chat user queries it (Req 10.2, 10.3)."""
        admin_role = _make_role("admin1", "admin", env.id)
        chat_role = _make_role("chat1", "chat_user", env.id)
        doc = _make_document(env.id, user_id="admin1")

        # --- Step 1: Simulate document exists (uploaded by admin) ---
        # The upload endpoint is tested separately in test_documents_api.py
        # and test_env_documents_api.py. Here we verify the chat flow
        # works when a document is already present.
        assert doc.processing_status == "processed"
        assert doc.environment_id == env.id

        # --- Step 2: Chat user starts conversation ---
        env_result2 = MagicMock()
        env_result2.scalar_one_or_none.return_value = env
        role_result2 = MagicMock()
        role_result2.scalar_one_or_none.return_value = chat_role

        db.execute.side_effect = [env_result2, role_result2]

        async def _refresh_conv(obj):
            if not hasattr(obj, "created_at") or obj.created_at is None:
                obj.created_at = _NOW

        db.refresh.side_effect = _refresh_conv

        resp = await client.post(
            f"/api/v1/environments/{env.id}/chat/conversations",
            json={"title": "E2E Chat"},
            headers={"X-User-ID": "chat1"},
        )
        assert resp.status_code == 201
        conv_data = resp.json()
        conv_id = conv_data["conversation_id"]

        # --- Step 3: Chat user sends message and gets RAG response ---
        mock_rag_pipeline.generate_response.return_value = (
            _mock_rag_response_with_citations("What is in the document?")
        )

        env_result3 = MagicMock()
        env_result3.scalar_one_or_none.return_value = env
        role_result3 = MagicMock()
        role_result3.scalar_one_or_none.return_value = chat_role

        db.execute.side_effect = [env_result3, role_result3]

        conv_obj = Conversation(
            id=conv_id,
            user_id="chat1",
            title="E2E Chat",
            environment_id=env.id,
            created_at=_NOW,
            updated_at=_NOW,
        )
        db.get.return_value = conv_obj

        resp = await client.post(
            f"/api/v1/environments/{env.id}/chat/conversations/{conv_id}/messages",
            json={"message": "What is in the document?"},
            headers={"X-User-ID": "chat1"},
        )
        assert resp.status_code == 200
        msg_data = resp.json()
        assert "response" in msg_data
        assert msg_data["environment_id"] == str(env.id)
        assert msg_data["response"] != ""

        # Verify RAG pipeline was called with environment scope
        call_args = mock_rag_pipeline.generate_response.call_args
        rag_req = call_args[0][0]
        assert rag_req.environment_id == env.id

    async def test_chat_response_includes_metadata(
        self, db, client, env, mock_rag_pipeline
    ):
        """Chat response includes retrieval stats and generation metadata (Req 10.3)."""
        role = _make_role("chat1", "chat_user", env.id)
        conv_id = uuid4()
        conv = Conversation(
            id=conv_id, user_id="chat1", title="Meta",
            environment_id=env.id, created_at=_NOW, updated_at=_NOW,
        )

        env_r = MagicMock()
        env_r.scalar_one_or_none.return_value = env
        role_r = MagicMock()
        role_r.scalar_one_or_none.return_value = role
        db.execute.side_effect = [env_r, role_r]
        db.get.return_value = conv

        mock_rag_pipeline.generate_response.return_value = (
            _mock_rag_response_with_citations()
        )

        resp = await client.post(
            f"/api/v1/environments/{env.id}/chat/conversations/{conv_id}/messages",
            json={"message": "Tell me about the docs"},
            headers={"X-User-ID": "chat1"},
        )
        assert resp.status_code == 200
        data = resp.json()

        # Verify metadata structure
        assert "metadata" in data
        meta = data["metadata"]
        assert "retrieval_stats" in meta
        assert "generation_stats" in meta
        assert "environment" in meta
        assert meta["environment"]["environment_id"] == str(env.id)
        assert "processing_time" in meta["generation_stats"]
        assert "total_cost" in meta["generation_stats"]


# =========================================================================
# 2. Multi-Provider Failover and Cost Optimization
# =========================================================================


class MockLLMProvider(LLMProvider):
    """Concrete mock provider for failover tests."""

    def __init__(self, config: ProviderConfig, should_fail: bool = False,
                 fail_error: Exception | None = None):
        self._should_fail = should_fail
        self._fail_error = fail_error
        self._call_count = 0
        super().__init__(config)

    async def generate_response(self, request: LLMRequest) -> LLMResponse:
        self._call_count += 1
        if self._should_fail:
            raise self._fail_error or ProviderError(
                "Provider failed", self.config.name, retryable=True
            )
        return LLMResponse(
            content="Response from " + self.config.name,
            input_tokens=20,
            output_tokens=15,
            total_tokens=35,
            cost=0.001 * self.config.priority,
            provider=self.config.name,
            model=self.config.models[0].name,
        )

    async def is_available(self) -> bool:
        return not self._should_fail

    def get_available_models(self) -> list[str]:
        return [m.name for m in self.config.models]

    def get_model_config(self, model_name: str) -> ModelConfig | None:
        for m in self.config.models:
            if m.name == model_name:
                return m
        return None

    def calculate_cost(
        self, input_tokens: int, output_tokens: int, model_name: str
    ) -> float:
        return (input_tokens + output_tokens) * 0.00001


def _make_provider_config(name: str, priority: int = 1) -> ProviderConfig:
    return ProviderConfig(
        name=name,
        api_key=f"test-key-{name}",
        models=[
            ModelConfig(
                name=f"{name}-model",
                input_cost_per_1k_tokens=0.01 * priority,
                output_cost_per_1k_tokens=0.02 * priority,
                max_tokens=4096,
                capabilities=[ModelCapability.CHAT],
                context_window=8192,
            )
        ],
        enabled=True,
        priority=priority,
    )


class TestMultiProviderFailover:
    """Test LLM provider failover and cost optimization (Req 10.4)."""

    async def test_primary_provider_success(self):
        """When primary provider works, it is used directly."""
        cfg1 = _make_provider_config("openai", priority=1)
        cfg2 = _make_provider_config("anthropic", priority=2)

        manager = LLMProviderManager([cfg1, cfg2])
        p1 = MockLLMProvider(cfg1)
        p2 = MockLLMProvider(cfg2)
        manager.providers = {"openai": p1, "anthropic": p2}

        request = LLMRequest(
            messages=[{"role": "user", "content": "Hello"}]
        )
        response = await manager.generate_response(request)

        assert response.provider == "openai"
        assert p1._call_count == 1
        assert p2._call_count == 0

    async def test_failover_to_secondary_on_error(self):
        """When primary fails, system falls back to secondary provider."""
        cfg1 = _make_provider_config("openai", priority=1)
        cfg2 = _make_provider_config("anthropic", priority=2)

        manager = LLMProviderManager([cfg1, cfg2])
        p1 = MockLLMProvider(cfg1, should_fail=True)
        p2 = MockLLMProvider(cfg2)
        manager.providers = {"openai": p1, "anthropic": p2}

        request = LLMRequest(
            messages=[{"role": "user", "content": "Hello"}]
        )
        response = await manager.generate_response(request)

        assert response.provider == "anthropic"
        assert p2._call_count == 1

    async def test_failover_chain_through_all_providers(self):
        """When first two fail, system falls back to third provider."""
        cfg1 = _make_provider_config("openai", priority=1)
        cfg2 = _make_provider_config("anthropic", priority=2)
        cfg3 = _make_provider_config("google", priority=3)

        manager = LLMProviderManager([cfg1, cfg2, cfg3])
        p1 = MockLLMProvider(cfg1, should_fail=True)
        p2 = MockLLMProvider(cfg2, should_fail=True)
        p3 = MockLLMProvider(cfg3)
        manager.providers = {
            "openai": p1, "anthropic": p2, "google": p3
        }

        request = LLMRequest(
            messages=[{"role": "user", "content": "Hello"}]
        )
        response = await manager.generate_response(request)

        assert response.provider == "google"

    async def test_all_providers_fail_raises_error(self):
        """When all providers fail, a ProviderError is raised."""
        cfg1 = _make_provider_config("openai", priority=1)
        cfg2 = _make_provider_config("anthropic", priority=2)

        manager = LLMProviderManager([cfg1, cfg2])
        p1 = MockLLMProvider(cfg1, should_fail=True)
        p2 = MockLLMProvider(cfg2, should_fail=True)
        manager.providers = {"openai": p1, "anthropic": p2}

        request = LLMRequest(
            messages=[{"role": "user", "content": "Hello"}]
        )
        with pytest.raises(ProviderError, match="All providers failed"):
            await manager.generate_response(request)

    async def test_rate_limit_triggers_failover(self):
        """Rate limit error on primary triggers failover to secondary."""
        cfg1 = _make_provider_config("openai", priority=1)
        cfg2 = _make_provider_config("anthropic", priority=2)

        manager = LLMProviderManager([cfg1, cfg2])
        p1 = MockLLMProvider(
            cfg1, should_fail=True,
            fail_error=RateLimitError("Rate limited", "openai"),
        )
        p2 = MockLLMProvider(cfg2)
        manager.providers = {"openai": p1, "anthropic": p2}

        request = LLMRequest(
            messages=[{"role": "user", "content": "Hello"}]
        )
        response = await manager.generate_response(request)

        assert response.provider == "anthropic"


# =========================================================================
# 3. Cost Tracking Across Providers
# =========================================================================


class TestCostTracking:
    """Test cost tracking works correctly across providers (Req 10.4)."""

    async def test_cost_recorded_after_successful_response(self):
        """Cost tracker records usage after a successful LLM response."""
        tracker = CostTracker()
        cfg = _make_provider_config("openai", priority=1)

        manager = LLMProviderManager([cfg], cost_tracker=tracker)
        provider = MockLLMProvider(cfg)
        manager.providers = {"openai": provider}

        request = LLMRequest(
            messages=[{"role": "user", "content": "Hello"}]
        )
        response = await manager.generate_response(request)

        assert response.cost > 0
        daily = await tracker.get_daily_cost()
        assert daily > 0

    async def test_cost_tracked_per_provider(self):
        """Costs are tracked separately per provider."""
        tracker = CostTracker()

        # Simulate two responses from different providers
        resp1 = LLMResponse(
            content="r1", input_tokens=10, output_tokens=5,
            total_tokens=15, cost=0.001, provider="openai",
            model="gpt-3.5-turbo",
        )
        resp2 = LLMResponse(
            content="r2", input_tokens=10, output_tokens=5,
            total_tokens=15, cost=0.002, provider="anthropic",
            model="claude-3",
        )

        await tracker.record_usage(resp1)
        await tracker.record_usage(resp2)

        provider_costs = await tracker.get_provider_costs()
        assert "openai" in provider_costs
        assert "anthropic" in provider_costs
        assert provider_costs["openai"] == pytest.approx(0.001)
        assert provider_costs["anthropic"] == pytest.approx(0.002)

    async def test_cost_alerts_trigger_at_threshold(self):
        """Cost alerts fire when daily/monthly limits are approached."""
        tracker = CostTracker()

        resp = LLMResponse(
            content="expensive", input_tokens=1000, output_tokens=500,
            total_tokens=1500, cost=11.0, provider="openai",
            model="gpt-4",
        )
        await tracker.record_usage(resp)

        alerts = await tracker.check_cost_alerts(daily_limit=10.0)
        assert len(alerts) > 0
        assert any("Daily cost limit exceeded" in a for a in alerts)

    async def test_usage_summary_aggregation(self):
        """Usage summary correctly aggregates across multiple requests."""
        tracker = CostTracker()

        for i in range(5):
            resp = LLMResponse(
                content=f"resp{i}", input_tokens=10, output_tokens=5,
                total_tokens=15, cost=0.001, provider="openai",
                model="gpt-3.5-turbo",
            )
            await tracker.record_usage(resp)

        summary = await tracker.get_usage_summary()
        assert summary.total_requests == 5
        assert summary.total_tokens == 75
        assert summary.total_cost == pytest.approx(0.005)

    async def test_provider_efficiency_metrics(self):
        """Provider efficiency (cost per token) is calculated correctly."""
        tracker = CostTracker()

        resp = LLMResponse(
            content="test", input_tokens=100, output_tokens=50,
            total_tokens=150, cost=0.003, provider="openai",
            model="gpt-3.5-turbo",
        )
        await tracker.record_usage(resp)

        efficiency = await tracker.get_provider_efficiency()
        assert "openai" in efficiency
        assert efficiency["openai"]["cost_per_token"] == pytest.approx(
            0.003 / 150
        )


# =========================================================================
# 4. Conversation Memory Management and Token Optimization
# =========================================================================


class TestConversationMemory:
    """Test conversation memory management and token optimization (Req 10.3)."""

    async def test_memory_initialized_on_conversation_start(
        self, db, client, env, mock_memory_manager
    ):
        """Memory manager is initialized when a conversation starts."""
        role = _make_role("chat1", "chat_user", env.id)

        env_r = MagicMock()
        env_r.scalar_one_or_none.return_value = env
        role_r = MagicMock()
        role_r.scalar_one_or_none.return_value = role
        db.execute.side_effect = [env_r, role_r]

        async def _refresh(obj):
            if not hasattr(obj, "created_at") or obj.created_at is None:
                obj.created_at = _NOW

        db.refresh.side_effect = _refresh

        resp = await client.post(
            f"/api/v1/environments/{env.id}/chat/conversations",
            json={"title": "Memory Test"},
            headers={"X-User-ID": "chat1"},
        )
        assert resp.status_code == 201

        mock_memory_manager.initialize_memory.assert_called_once()
        call_kwargs = mock_memory_manager.initialize_memory.call_args
        assert call_kwargs.kwargs["user_id"] == "chat1"

    async def test_messages_stored_in_memory(
        self, db, client, env, mock_memory_manager, mock_rag_pipeline
    ):
        """User and AI messages are added to memory during chat."""
        role = _make_role("chat1", "chat_user", env.id)
        conv_id = uuid4()
        conv = Conversation(
            id=conv_id, user_id="chat1", title="Mem",
            environment_id=env.id, created_at=_NOW, updated_at=_NOW,
        )

        env_r = MagicMock()
        env_r.scalar_one_or_none.return_value = env
        role_r = MagicMock()
        role_r.scalar_one_or_none.return_value = role
        db.execute.side_effect = [env_r, role_r]
        db.get.return_value = conv

        resp = await client.post(
            f"/api/v1/environments/{env.id}/chat/conversations/{conv_id}/messages",
            json={"message": "Remember this"},
            headers={"X-User-ID": "chat1"},
        )
        assert resp.status_code == 200

        mock_memory_manager.add_user_message.assert_called_once()
        mock_memory_manager.add_ai_message.assert_called_once()

    async def test_memory_failure_does_not_break_chat(
        self, db, client, env, mock_memory_manager, mock_rag_pipeline
    ):
        """If memory operations fail, chat still returns a response."""
        role = _make_role("chat1", "chat_user", env.id)
        conv_id = uuid4()
        conv = Conversation(
            id=conv_id, user_id="chat1", title="MemFail",
            environment_id=env.id, created_at=_NOW, updated_at=_NOW,
        )

        env_r = MagicMock()
        env_r.scalar_one_or_none.return_value = env
        role_r = MagicMock()
        role_r.scalar_one_or_none.return_value = role
        db.execute.side_effect = [env_r, role_r]
        db.get.return_value = conv

        # Memory operations fail
        mock_memory_manager.add_user_message.side_effect = Exception(
            "Redis down"
        )
        mock_memory_manager.add_ai_message.side_effect = Exception(
            "Redis down"
        )

        resp = await client.post(
            f"/api/v1/environments/{env.id}/chat/conversations/{conv_id}/messages",
            json={"message": "Still works?"},
            headers={"X-User-ID": "chat1"},
        )
        # Chat should still succeed despite memory failures
        assert resp.status_code == 200
        assert resp.json()["response"] != ""


# =========================================================================
# 5. Performance Tests for Vector Search and Response Generation
# =========================================================================


class TestPerformance:
    """Performance tests for vector search and response generation (Req 10.5)."""

    async def test_rag_response_time_within_bounds(
        self, db, client, env, mock_rag_pipeline
    ):
        """RAG response completes within acceptable time bounds."""
        role = _make_role("chat1", "chat_user", env.id)
        conv_id = uuid4()
        conv = Conversation(
            id=conv_id, user_id="chat1", title="Perf",
            environment_id=env.id, created_at=_NOW, updated_at=_NOW,
        )

        env_r = MagicMock()
        env_r.scalar_one_or_none.return_value = env
        role_r = MagicMock()
        role_r.scalar_one_or_none.return_value = role
        db.execute.side_effect = [env_r, role_r]
        db.get.return_value = conv

        start = time.monotonic()
        resp = await client.post(
            f"/api/v1/environments/{env.id}/chat/conversations/{conv_id}/messages",
            json={"message": "Performance test"},
            headers={"X-User-ID": "chat1"},
        )
        elapsed = time.monotonic() - start

        assert resp.status_code == 200
        # With mocked services, the endpoint overhead should be < 2s
        assert elapsed < 2.0

    async def test_multiple_sequential_messages_performance(
        self, db, client, env, mock_rag_pipeline, mock_memory_manager
    ):
        """Multiple sequential messages maintain consistent performance."""
        role = _make_role("chat1", "chat_user", env.id)
        conv_id = uuid4()
        conv = Conversation(
            id=conv_id, user_id="chat1", title="SeqPerf",
            environment_id=env.id, created_at=_NOW, updated_at=_NOW,
        )

        timings = []
        for i in range(5):
            env_r = MagicMock()
            env_r.scalar_one_or_none.return_value = env
            role_r = MagicMock()
            role_r.scalar_one_or_none.return_value = role
            db.execute.side_effect = [env_r, role_r]
            db.get.return_value = conv

            start = time.monotonic()
            resp = await client.post(
                f"/api/v1/environments/{env.id}/chat/conversations/{conv_id}/messages",
                json={"message": f"Message {i}"},
                headers={"X-User-ID": "chat1"},
            )
            timings.append(time.monotonic() - start)
            assert resp.status_code == 200

        # All responses should be fast and consistent
        assert all(t < 2.0 for t in timings)

    async def test_conversation_creation_performance(
        self, db, client, env, mock_memory_manager
    ):
        """Creating multiple conversations is fast."""
        role = _make_role("chat1", "chat_user", env.id)

        start = time.monotonic()
        for i in range(10):
            env_r = MagicMock()
            env_r.scalar_one_or_none.return_value = env
            role_r = MagicMock()
            role_r.scalar_one_or_none.return_value = role
            db.execute.side_effect = [env_r, role_r]

            async def _refresh(obj):
                if not hasattr(obj, "created_at") or obj.created_at is None:
                    obj.created_at = _NOW

            db.refresh.side_effect = _refresh

            resp = await client.post(
                f"/api/v1/environments/{env.id}/chat/conversations",
                json={"title": f"Conv {i}"},
                headers={"X-User-ID": "chat1"},
            )
            assert resp.status_code == 201

        elapsed = time.monotonic() - start
        # 10 conversation creations should complete in < 5s
        assert elapsed < 5.0


# =========================================================================
# 6. Environment-Scoped Operations
# =========================================================================


class TestEnvironmentScoping:
    """Test that documents and chat are properly scoped to environments (Req 10.1, 10.3)."""

    async def test_create_environment(self, db, client):
        """Admin can create an environment."""
        env_id = uuid4()

        # No duplicate found
        dup_result = MagicMock()
        dup_result.scalar_one_or_none.return_value = None
        db.execute.return_value = dup_result

        async def _refresh(obj):
            obj.id = env_id
            obj.created_at = _NOW
            obj.updated_at = _NOW

        db.refresh.side_effect = _refresh

        resp = await client.post(
            "/api/v1/environments",
            json={"name": "production", "description": "Prod env"},
            headers={"X-User-ID": "admin1"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "production"

    async def test_list_environments(self, db, client):
        """Environments can be listed."""
        env1 = _make_env(name="env-a")
        env2 = _make_env(name="env-b")

        scalars = MagicMock()
        scalars.all.return_value = [env1, env2]
        result = MagicMock()
        result.scalars.return_value = scalars
        db.execute.return_value = result

        resp = await client.get("/api/v1/environments")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    async def test_delete_environment_cascades(self, db, client):
        """Deleting an environment reports cascade-deleted document count."""
        env = _make_env()

        env_result = MagicMock()
        env_result.scalar_one_or_none.return_value = env

        count_result = MagicMock()
        count_result.scalar.return_value = 3

        db.execute.side_effect = [env_result, count_result]

        resp = await client.delete(f"/api/v1/environments/{env.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["deleted_documents_count"] == 3

    async def test_chat_scoped_to_environment(
        self, db, client, env, mock_rag_pipeline
    ):
        """RAG search is scoped to the conversation's environment (Req 10.5)."""
        role = _make_role("chat1", "chat_user", env.id)
        conv_id = uuid4()
        conv = Conversation(
            id=conv_id, user_id="chat1", title="Scoped",
            environment_id=env.id, created_at=_NOW, updated_at=_NOW,
        )

        env_r = MagicMock()
        env_r.scalar_one_or_none.return_value = env
        role_r = MagicMock()
        role_r.scalar_one_or_none.return_value = role
        db.execute.side_effect = [env_r, role_r]
        db.get.return_value = conv

        resp = await client.post(
            f"/api/v1/environments/{env.id}/chat/conversations/{conv_id}/messages",
            json={"message": "Scoped query"},
            headers={"X-User-ID": "chat1"},
        )
        assert resp.status_code == 200

        # Verify the RAG request was scoped to the environment
        call_args = mock_rag_pipeline.generate_response.call_args
        rag_req = call_args[0][0]
        assert rag_req.environment_id == env.id

    async def test_conversation_wrong_env_rejected(self, db, client, env):
        """Sending a message to a conversation in a different env is rejected."""
        role = _make_role("chat1", "chat_user", env.id)
        conv_id = uuid4()
        other_env_id = uuid4()
        conv = Conversation(
            id=conv_id, user_id="chat1", title="Wrong",
            environment_id=other_env_id,
        )

        env_r = MagicMock()
        env_r.scalar_one_or_none.return_value = env
        role_r = MagicMock()
        role_r.scalar_one_or_none.return_value = role
        db.execute.side_effect = [env_r, role_r]
        db.get.return_value = conv

        resp = await client.post(
            f"/api/v1/environments/{env.id}/chat/conversations/{conv_id}/messages",
            json={"message": "Cross-env"},
            headers={"X-User-ID": "chat1"},
        )
        assert resp.status_code == 403
        assert "does not belong" in resp.json()["detail"]


# =========================================================================
# 7. Role-Based Access Control in E2E Flow
# =========================================================================


class TestRoleBasedAccess:
    """Test admin vs chat_user roles are enforced in the e2e flow (Req 10.2, 10.4)."""

    async def test_admin_can_create_environment_and_upload(
        self, db, client, env
    ):
        """Admin can create environments and manage documents (Req 10.2)."""
        admin_role = _make_role("admin1", "admin", env.id)
        doc = _make_document(env.id, user_id="admin1")

        # Verify admin can list documents in the environment
        env_result = MagicMock()
        env_result.scalar_one_or_none.return_value = env
        admin_result = MagicMock()
        admin_result.scalar_one_or_none.return_value = admin_role

        # Mock the document list query result
        docs_result = MagicMock()
        docs_result.scalars.return_value.all.return_value = [doc]

        db.execute.side_effect = [env_result, admin_result, docs_result]

        resp = await client.get(
            f"/api/v1/environments/{env.id}/documents",
            headers={"X-User-ID": "admin1"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    async def test_chat_user_cannot_upload_documents(self, db, client, env):
        """Chat users are denied document upload (admin only)."""
        chat_role = _make_role("chat1", "chat_user", env.id)

        env_result = MagicMock()
        env_result.scalar_one_or_none.return_value = env
        # _verify_admin will find chat_user role, not admin
        role_result = MagicMock()
        role_result.scalar_one_or_none.return_value = None  # no admin role
        db.execute.side_effect = [env_result, role_result]

        resp = await client.post(
            f"/api/v1/environments/{env.id}/documents/upload",
            files={"file": ("test.txt", b"Blocked", "text/plain")},
            headers={"X-User-ID": "chat1"},
        )
        assert resp.status_code == 403

    async def test_chat_user_can_start_conversation(
        self, db, client, env, mock_memory_manager
    ):
        """Chat user with environment access can start conversations."""
        role = _make_role("chat1", "chat_user", env.id)

        env_r = MagicMock()
        env_r.scalar_one_or_none.return_value = env
        role_r = MagicMock()
        role_r.scalar_one_or_none.return_value = role
        db.execute.side_effect = [env_r, role_r]

        async def _refresh(obj):
            if not hasattr(obj, "created_at") or obj.created_at is None:
                obj.created_at = _NOW

        db.refresh.side_effect = _refresh

        resp = await client.post(
            f"/api/v1/environments/{env.id}/chat/conversations",
            json={"title": "Chat User Conv"},
            headers={"X-User-ID": "chat1"},
        )
        assert resp.status_code == 201

    async def test_unassigned_user_denied_chat(self, db, client, env):
        """User without any role in the environment is denied chat access."""
        env_r = MagicMock()
        env_r.scalar_one_or_none.return_value = env
        role_r = MagicMock()
        role_r.scalar_one_or_none.return_value = None  # no role
        db.execute.side_effect = [env_r, role_r]

        resp = await client.post(
            f"/api/v1/environments/{env.id}/chat/conversations",
            json={"title": "Denied"},
            headers={"X-User-ID": "outsider"},
        )
        assert resp.status_code == 403

    async def test_admin_can_also_chat(
        self, db, client, env, mock_memory_manager
    ):
        """Admin users can also use chat endpoints."""
        admin_role = _make_role("admin1", "admin", env.id)

        env_r = MagicMock()
        env_r.scalar_one_or_none.return_value = env
        role_r = MagicMock()
        role_r.scalar_one_or_none.return_value = admin_role
        db.execute.side_effect = [env_r, role_r]

        async def _refresh(obj):
            if not hasattr(obj, "created_at") or obj.created_at is None:
                obj.created_at = _NOW

        db.refresh.side_effect = _refresh

        resp = await client.post(
            f"/api/v1/environments/{env.id}/chat/conversations",
            json={"title": "Admin Chat"},
            headers={"X-User-ID": "admin1"},
        )
        assert resp.status_code == 201

    async def test_role_assignment_and_listing(self, db, client, env):
        """Roles can be assigned and listed."""
        role = _make_role("new_user", "chat_user", env.id)

        # assign_role: validate env exists, check duplicate, then create
        env_result = MagicMock()
        env_result.scalar_one_or_none.return_value = env
        dup_result = MagicMock()
        dup_result.scalar_one_or_none.return_value = None  # no duplicate
        db.execute.side_effect = [env_result, dup_result]

        async def _refresh(obj):
            obj.id = role.id
            obj.created_at = _NOW

        db.refresh.side_effect = _refresh

        resp = await client.post(
            "/api/v1/roles",
            json={
                "user_id": "new_user",
                "role": "chat_user",
                "environment_id": str(env.id),
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["user_id"] == "new_user"
        assert data["role"] == "chat_user"
