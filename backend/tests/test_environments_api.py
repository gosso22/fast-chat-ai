"""
Tests for environment management API endpoints.

Uses module-level async test functions with httpx.AsyncClient and
MagicMock (base) + AsyncMock (selective) for the DB session mock.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
import pytest

from app.db.base import get_db
from app.main import app
from app.models.environment import Environment

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime.now(timezone.utc)


def _make_env(**kwargs):
    """Create an Environment instance with sensible defaults."""
    defaults = {
        "id": uuid4(),
        "name": "test-env",
        "created_by": "admin",
        "created_at": _NOW,
        "updated_at": _NOW,
    }
    defaults.update(kwargs)
    return Environment(**defaults)


def _mock_db():
    """MagicMock base with only the async methods as AsyncMock."""
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    db.close = AsyncMock()
    return db



def _patch_refresh(env):
    """Async side-effect that populates server-default fields on refresh."""
    async def _refresh(obj):
        if obj.id is None:
            obj.id = env.id
        if obj.created_at is None:
            obj.created_at = _NOW
        if obj.updated_at is None:
            obj.updated_at = _NOW
    return _refresh


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db():
    """Fresh MagicMock-based DB mock per test."""
    return _mock_db()


@pytest.fixture()
async def client(db):
    """httpx.AsyncClient with the DB dependency overridden."""
    async def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-User-ID": "default_admin"},
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# CREATE  -  POST /api/v1/environments
# ---------------------------------------------------------------------------


async def test_create_success(db, client):
    """Create a new environment returns 201."""
    env = _make_env(name="production")

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db.execute.return_value = result_mock
    db.refresh.side_effect = _patch_refresh(env)

    response = await client.post(
        "/api/v1/environments",
        json={"name": "production", "description": "Production KB"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "production"
    assert data["description"] == "Production KB"
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data
    db.add.assert_called_once()
    db.commit.assert_called_once()


async def test_create_duplicate_name(db, client):
    """409 when name already exists."""
    existing = _make_env(name="production")
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = existing
    db.execute.return_value = result_mock

    response = await client.post(
        "/api/v1/environments",
        json={"name": "production"},
    )

    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


async def test_create_missing_name(client):
    """422 when name is missing."""
    response = await client.post(
        "/api/v1/environments",
        json={"description": "No name"},
    )
    assert response.status_code == 422


async def test_create_empty_name(client):
    """422 when name is empty string."""
    response = await client.post(
        "/api/v1/environments",
        json={"name": ""},
    )
    assert response.status_code == 422


async def test_create_without_description(db, client):
    """Create without optional description returns 201."""
    env = _make_env(name="minimal-env")

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db.execute.return_value = result_mock
    db.refresh.side_effect = _patch_refresh(env)

    response = await client.post(
        "/api/v1/environments",
        json={"name": "minimal-env"},
    )

    assert response.status_code == 201
    assert response.json()["description"] is None
    db.add.assert_called_once()



# ---------------------------------------------------------------------------
# LIST  -  GET /api/v1/environments
# ---------------------------------------------------------------------------


async def test_list_returns_environments(db, client):
    """Listing returns a list of environments."""
    envs = [_make_env(name="env-1"), _make_env(name="env-2")]

    result_mock = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = envs
    result_mock.scalars.return_value = scalars_mock
    db.execute.return_value = result_mock

    response = await client.get("/api/v1/environments")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 2


async def test_list_empty(db, client):
    """Listing when no environments exist returns empty list."""
    result_mock = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = []
    result_mock.scalars.return_value = scalars_mock
    db.execute.return_value = result_mock

    response = await client.get("/api/v1/environments")

    assert response.status_code == 200
    assert response.json() == []


async def test_list_pagination(db, client):
    """Listing with skip and limit query params."""
    result_mock = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = []
    result_mock.scalars.return_value = scalars_mock
    db.execute.return_value = result_mock

    response = await client.get("/api/v1/environments?skip=5&limit=10")

    assert response.status_code == 200
    db.execute.assert_called_once()


# ---------------------------------------------------------------------------
# GET  -  GET /api/v1/environments/{id}
# ---------------------------------------------------------------------------


async def test_get_success(db, client):
    """Getting a single environment by ID."""
    env = _make_env(name="test-env", description="Test")

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = env
    db.execute.return_value = result_mock

    response = await client.get(f"/api/v1/environments/{env.id}")

    assert response.status_code == 200
    assert response.json()["name"] == "test-env"


async def test_get_not_found(db, client):
    """404 for non-existent environment."""
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db.execute.return_value = result_mock

    response = await client.get(f"/api/v1/environments/{uuid4()}")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"]



# ---------------------------------------------------------------------------
# UPDATE  -  PUT /api/v1/environments/{id}
# ---------------------------------------------------------------------------


async def test_update_name(db, client):
    """Updating an environment's name."""
    env = _make_env(name="old-name")

    find_mock = MagicMock()
    find_mock.scalar_one_or_none.return_value = env
    dup_mock = MagicMock()
    dup_mock.scalar_one_or_none.return_value = None
    db.execute.side_effect = [find_mock, dup_mock]
    db.refresh.side_effect = _patch_refresh(env)

    response = await client.put(
        f"/api/v1/environments/{env.id}",
        json={"name": "new-name"},
    )

    assert response.status_code == 200
    db.commit.assert_called_once()


async def test_update_description(db, client):
    """Updating only the description."""
    env = _make_env(description="Old desc")

    find_mock = MagicMock()
    find_mock.scalar_one_or_none.return_value = env
    db.execute.return_value = find_mock
    db.refresh.side_effect = _patch_refresh(env)

    response = await client.put(
        f"/api/v1/environments/{env.id}",
        json={"description": "Updated description"},
    )

    assert response.status_code == 200
    assert env.description == "Updated description"
    db.commit.assert_called_once()


async def test_update_not_found(db, client):
    """404 when environment doesn't exist."""
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db.execute.return_value = result_mock

    response = await client.put(
        f"/api/v1/environments/{uuid4()}",
        json={"name": "whatever"},
    )

    assert response.status_code == 404


async def test_update_duplicate_name(db, client):
    """409 when renaming to an existing name."""
    env = _make_env(name="env-a")
    other = _make_env(name="env-b")

    find_mock = MagicMock()
    find_mock.scalar_one_or_none.return_value = env
    dup_mock = MagicMock()
    dup_mock.scalar_one_or_none.return_value = other
    db.execute.side_effect = [find_mock, dup_mock]

    response = await client.put(
        f"/api/v1/environments/{env.id}",
        json={"name": "env-b"},
    )

    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


# ---------------------------------------------------------------------------
# DELETE  -  DELETE /api/v1/environments/{id}
# ---------------------------------------------------------------------------


async def test_delete_success(db, client):
    """Deleting an environment with cascade document cleanup."""
    env = _make_env(name="to-delete")

    find_mock = MagicMock()
    find_mock.scalar_one_or_none.return_value = env
    count_mock = MagicMock()
    count_mock.scalar.return_value = 3
    db.execute.side_effect = [find_mock, count_mock]

    response = await client.delete(f"/api/v1/environments/{env.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["deleted_environment_id"] == str(env.id)
    assert data["deleted_documents_count"] == 3
    assert data["message"] == "Environment deleted successfully"
    db.delete.assert_called_once_with(env)
    db.commit.assert_called_once()


async def test_delete_not_found(db, client):
    """404 when environment doesn't exist."""
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db.execute.return_value = result_mock

    response = await client.delete(f"/api/v1/environments/{uuid4()}")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


async def test_delete_no_documents(db, client):
    """Deleting an environment that has no documents."""
    env = _make_env(name="empty-env")

    find_mock = MagicMock()
    find_mock.scalar_one_or_none.return_value = env
    count_mock = MagicMock()
    count_mock.scalar.return_value = 0
    db.execute.side_effect = [find_mock, count_mock]

    response = await client.delete(f"/api/v1/environments/{env.id}")

    assert response.status_code == 200
    assert response.json()["deleted_documents_count"] == 0


# ---------------------------------------------------------------------------
# STATS  -  GET /api/v1/environments/{id}/stats
# ---------------------------------------------------------------------------


async def test_stats_success(db, client):
    """Get stats for an environment with documents and conversations."""
    env = _make_env(name="stats-env")

    # 1: env lookup
    env_result = MagicMock()
    env_result.scalar_one_or_none.return_value = env
    # 2: doc stats (count=5, storage=1024)
    doc_stats = MagicMock()
    doc_stats.one.return_value = (5, 1024)
    # 3: chunk stats (count=20, tokens=5000)
    chunk_stats = MagicMock()
    chunk_stats.one.return_value = (20, 5000)
    # 4: conversation count
    conv_count = MagicMock()
    conv_count.scalar.return_value = 3
    # 5: message count
    msg_count = MagicMock()
    msg_count.scalar.return_value = 15

    db.execute.side_effect = [env_result, doc_stats, chunk_stats, conv_count, msg_count]

    response = await client.get(f"/api/v1/environments/{env.id}/stats")

    assert response.status_code == 200
    data = response.json()
    assert data["environment_id"] == str(env.id)
    assert data["name"] == "stats-env"
    assert data["document_count"] == 5
    assert data["total_storage_bytes"] == 1024
    assert data["chunk_count"] == 20
    assert data["total_tokens"] == 5000
    assert data["conversation_count"] == 3
    assert data["message_count"] == 15


async def test_stats_empty_environment(db, client):
    """Stats for an environment with no documents or conversations."""
    env = _make_env(name="empty-stats")

    env_result = MagicMock()
    env_result.scalar_one_or_none.return_value = env
    doc_stats = MagicMock()
    doc_stats.one.return_value = (0, 0)
    chunk_stats = MagicMock()
    chunk_stats.one.return_value = (0, 0)
    conv_count = MagicMock()
    conv_count.scalar.return_value = 0
    msg_count = MagicMock()
    msg_count.scalar.return_value = 0

    db.execute.side_effect = [env_result, doc_stats, chunk_stats, conv_count, msg_count]

    response = await client.get(f"/api/v1/environments/{env.id}/stats")

    assert response.status_code == 200
    data = response.json()
    assert data["document_count"] == 0
    assert data["chunk_count"] == 0
    assert data["total_tokens"] == 0
    assert data["total_storage_bytes"] == 0
    assert data["conversation_count"] == 0
    assert data["message_count"] == 0


async def test_stats_not_found(db, client):
    """404 when environment doesn't exist."""
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db.execute.return_value = result_mock

    response = await client.get(f"/api/v1/environments/{uuid4()}/stats")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"]
