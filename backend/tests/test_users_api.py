"""
Tests for user info API endpoints.

Validates:
- GET /api/v1/users/me returns user identity and admin status
- GET /api/v1/users/me/environments returns scoped environments
- Global admin sees all environments
- Regular user sees only assigned environments
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
import pytest

from app.db.base import get_db
from app.main import app
from app.models.environment import Environment
from app.models.user_role import UserRole

_NOW = datetime.now(timezone.utc)


def _make_env(**kwargs):
    defaults = {
        "id": uuid4(),
        "name": "test-env",
        "created_by": "admin",
        "created_at": _NOW,
        "updated_at": _NOW,
    }
    defaults.update(kwargs)
    return Environment(**defaults)


def _make_role(user_id="user1", role="chat_user", environment_id=None, **kw):
    defaults = {
        "id": uuid4(),
        "user_id": user_id,
        "role": role,
        "environment_id": environment_id,
        "created_at": _NOW,
    }
    defaults.update(kw)
    return UserRole(**defaults)


def _mock_db():
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    db.close = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture()
def db():
    return _mock_db()


@pytest.fixture()
async def admin_client(db):
    """Client authenticated as global admin (default_admin)."""
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


@pytest.fixture()
async def user_client(db):
    """Client authenticated as regular user."""
    async def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-User-ID": "regular_user"},
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# GET /api/v1/users/me
# ---------------------------------------------------------------------------


async def test_get_me_admin(admin_client):
    """Global admin gets is_global_admin=True."""
    resp = await admin_client.get("/api/v1/users/me")

    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == "default_admin"
    assert data["is_global_admin"] is True


async def test_get_me_regular_user(user_client):
    """Regular user gets is_global_admin=False."""
    resp = await user_client.get("/api/v1/users/me")

    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == "regular_user"
    assert data["is_global_admin"] is False


async def test_get_me_missing_header():
    """Request without X-User-ID header returns 422."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as ac:
        resp = await ac.get("/api/v1/users/me")

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/v1/users/me/environments
# ---------------------------------------------------------------------------


async def test_admin_sees_all_environments(db, admin_client):
    """Global admin sees all environments with admin role."""
    env1 = _make_env(name="env-1")
    env2 = _make_env(name="env-2")

    # First query: all environments
    env_result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = [env1, env2]
    env_result.scalars.return_value = scalars_mock

    # Second query: admin's explicit roles (none)
    roles_result = MagicMock()
    roles_scalars = MagicMock()
    roles_scalars.all.return_value = []
    roles_result.scalars.return_value = roles_scalars

    db.execute.side_effect = [env_result, roles_result]

    resp = await admin_client.get("/api/v1/users/me/environments")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    # Both should default to admin role since user is global admin
    assert data[0]["role"] == "admin"
    assert data[1]["role"] == "admin"


async def test_regular_user_sees_only_assigned_environments(db, user_client):
    """Regular user sees only environments where they have a role."""
    env = _make_env(name="assigned-env")
    role = _make_role(
        user_id="regular_user", role="chat_user", environment_id=env.id
    )

    result = MagicMock()
    result.all.return_value = [(role, env)]
    db.execute.return_value = result

    resp = await user_client.get("/api/v1/users/me/environments")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["environment"]["name"] == "assigned-env"
    assert data[0]["role"] == "chat_user"


async def test_regular_user_no_environments(db, user_client):
    """Regular user with no role assignments gets empty list."""
    result = MagicMock()
    result.all.return_value = []
    db.execute.return_value = result

    resp = await user_client.get("/api/v1/users/me/environments")

    assert resp.status_code == 200
    assert resp.json() == []


async def test_admin_with_explicit_role_uses_it(db, admin_client):
    """Global admin with explicit chat_user role returns that role."""
    env = _make_env(name="special-env")
    role = _make_role(
        user_id="default_admin", role="chat_user", environment_id=env.id
    )

    # First query: all environments
    env_result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = [env]
    env_result.scalars.return_value = scalars_mock

    # Second query: admin's explicit roles
    roles_result = MagicMock()
    roles_scalars = MagicMock()
    roles_scalars.all.return_value = [role]
    roles_result.scalars.return_value = roles_scalars

    db.execute.side_effect = [env_result, roles_result]

    resp = await admin_client.get("/api/v1/users/me/environments")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    # Should use the explicit role, not default admin
    assert data[0]["role"] == "chat_user"
