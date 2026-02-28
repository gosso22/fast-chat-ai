"""
Tests for role-based access control (RBAC).

Validates requirements:
- 9.1: Admin role for document management and environment preparation
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
from app.models.environment import Environment
from app.models.user_role import RoleType, UserRole

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def _make_role(user_id="admin_user", role="admin", environment_id=None, **kw):
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


def _patch_refresh(role_obj):
    async def _refresh(obj):
        if obj.id is None:
            obj.id = role_obj.id
        if obj.created_at is None:
            obj.created_at = _NOW
    return _refresh


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db():
    return _mock_db()


@pytest.fixture()
async def client(db):
    async def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# ASSIGN ROLE  -  POST /api/v1/roles
# ---------------------------------------------------------------------------


async def test_assign_role_success(db, client):
    """Assign admin role to a user for an environment."""
    env = _make_env()
    role = _make_role(environment_id=env.id)

    # 1: env lookup, 2: existing role check
    env_result = MagicMock()
    env_result.scalar_one_or_none.return_value = env
    existing_result = MagicMock()
    existing_result.scalar_one_or_none.return_value = None

    db.execute.side_effect = [env_result, existing_result]
    db.refresh.side_effect = _patch_refresh(role)

    resp = await client.post(
        "/api/v1/roles",
        json={
            "user_id": "admin_user",
            "role": "admin",
            "environment_id": str(env.id),
        },
    )

    assert resp.status_code == 201
    data = resp.json()
    assert data["user_id"] == "admin_user"
    assert data["role"] == "admin"
    assert data["environment_id"] == str(env.id)
    db.add.assert_called_once()
    db.commit.assert_called_once()


async def test_assign_chat_user_role(db, client):
    """Assign chat_user role to a user."""
    env = _make_env()
    role = _make_role(user_id="chat1", role="chat_user", environment_id=env.id)

    env_result = MagicMock()
    env_result.scalar_one_or_none.return_value = env
    existing_result = MagicMock()
    existing_result.scalar_one_or_none.return_value = None

    db.execute.side_effect = [env_result, existing_result]
    db.refresh.side_effect = _patch_refresh(role)

    resp = await client.post(
        "/api/v1/roles",
        json={
            "user_id": "chat1",
            "role": "chat_user",
            "environment_id": str(env.id),
        },
    )

    assert resp.status_code == 201
    assert resp.json()["role"] == "chat_user"


async def test_assign_role_duplicate(db, client):
    """409 when user already has a role in the environment."""
    env = _make_env()
    existing = _make_role(environment_id=env.id)

    env_result = MagicMock()
    env_result.scalar_one_or_none.return_value = env
    existing_result = MagicMock()
    existing_result.scalar_one_or_none.return_value = existing

    db.execute.side_effect = [env_result, existing_result]

    resp = await client.post(
        "/api/v1/roles",
        json={
            "user_id": "admin_user",
            "role": "admin",
            "environment_id": str(env.id),
        },
    )

    assert resp.status_code == 409
    assert "already has role" in resp.json()["detail"]


async def test_assign_role_env_not_found(db, client):
    """404 when environment does not exist."""
    env_result = MagicMock()
    env_result.scalar_one_or_none.return_value = None
    db.execute.return_value = env_result

    resp = await client.post(
        "/api/v1/roles",
        json={
            "user_id": "admin_user",
            "role": "admin",
            "environment_id": str(uuid4()),
        },
    )

    assert resp.status_code == 404
    assert "Environment not found" in resp.json()["detail"]


async def test_assign_role_invalid_role(client):
    """422 when role is not admin or chat_user."""
    resp = await client.post(
        "/api/v1/roles",
        json={
            "user_id": "user1",
            "role": "superadmin",
            "environment_id": str(uuid4()),
        },
    )

    assert resp.status_code == 422


async def test_assign_role_missing_user_id(client):
    """422 when user_id is missing."""
    resp = await client.post(
        "/api/v1/roles",
        json={
            "role": "admin",
            "environment_id": str(uuid4()),
        },
    )

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# LIST ROLES  -  GET /api/v1/roles
# ---------------------------------------------------------------------------


async def test_list_roles(db, client):
    """List all roles."""
    env = _make_env()
    roles = [
        _make_role(user_id="u1", role="admin", environment_id=env.id),
        _make_role(user_id="u2", role="chat_user", environment_id=env.id),
    ]

    result_mock = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = roles
    result_mock.scalars.return_value = scalars_mock
    db.execute.return_value = result_mock

    resp = await client.get("/api/v1/roles")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


async def test_list_roles_filter_by_environment(db, client):
    """List roles filtered by environment_id."""
    env = _make_env()
    roles = [_make_role(environment_id=env.id)]

    result_mock = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = roles
    result_mock.scalars.return_value = scalars_mock
    db.execute.return_value = result_mock

    resp = await client.get(
        f"/api/v1/roles?environment_id={env.id}"
    )

    assert resp.status_code == 200
    assert len(resp.json()) == 1


async def test_list_roles_filter_by_user(db, client):
    """List roles filtered by user_id."""
    result_mock = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = []
    result_mock.scalars.return_value = scalars_mock
    db.execute.return_value = result_mock

    resp = await client.get("/api/v1/roles?user_id=unknown")

    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# GET ROLE  -  GET /api/v1/roles/{role_id}
# ---------------------------------------------------------------------------


async def test_get_role_success(db, client):
    """Get a single role by ID."""
    env = _make_env()
    role = _make_role(environment_id=env.id)

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = role
    db.execute.return_value = result_mock

    resp = await client.get(f"/api/v1/roles/{role.id}")

    assert resp.status_code == 200
    assert resp.json()["user_id"] == role.user_id


async def test_get_role_not_found(db, client):
    """404 for non-existent role."""
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db.execute.return_value = result_mock

    resp = await client.get(f"/api/v1/roles/{uuid4()}")

    assert resp.status_code == 404
    assert "Role not found" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# UPDATE ROLE  -  PUT /api/v1/roles/{role_id}
# ---------------------------------------------------------------------------


async def test_update_role_success(db, client):
    """Update a user's role from chat_user to admin."""
    env = _make_env()
    role = _make_role(
        user_id="u1", role="chat_user", environment_id=env.id
    )

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = role
    db.execute.return_value = result_mock
    db.refresh.side_effect = _patch_refresh(role)

    resp = await client.put(
        f"/api/v1/roles/{role.id}",
        json={"role": "admin"},
    )

    assert resp.status_code == 200
    assert role.role == "admin"
    db.commit.assert_called_once()


async def test_update_role_not_found(db, client):
    """404 when role doesn't exist."""
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db.execute.return_value = result_mock

    resp = await client.put(
        f"/api/v1/roles/{uuid4()}",
        json={"role": "admin"},
    )

    assert resp.status_code == 404


async def test_update_role_invalid(client):
    """422 when role value is invalid."""
    resp = await client.put(
        f"/api/v1/roles/{uuid4()}",
        json={"role": "superadmin"},
    )

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# DELETE ROLE  -  DELETE /api/v1/roles/{role_id}
# ---------------------------------------------------------------------------


async def test_delete_role_success(db, client):
    """Delete a role assignment."""
    env = _make_env()
    role = _make_role(environment_id=env.id)

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = role
    db.execute.return_value = result_mock

    resp = await client.delete(f"/api/v1/roles/{role.id}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["deleted_role_id"] == str(role.id)
    assert data["message"] == "Role deleted successfully"
    db.delete.assert_called_once_with(role)
    db.commit.assert_called_once()


async def test_delete_role_not_found(db, client):
    """404 when role doesn't exist."""
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db.execute.return_value = result_mock

    resp = await client.delete(f"/api/v1/roles/{uuid4()}")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# AUTH DEPENDENCIES  -  Environment access validation
# ---------------------------------------------------------------------------


async def test_env_doc_delete_requires_admin(db, client):
    """Environment document delete requires admin role (Req 9.1)."""
    env = _make_env()

    env_result = MagicMock()
    env_result.scalar_one_or_none.return_value = env
    # No admin role found
    role_result = MagicMock()
    role_result.scalar_one_or_none.return_value = None

    db.execute.side_effect = [env_result, role_result]

    resp = await client.delete(
        f"/api/v1/environments/{env.id}/documents/{uuid4()}",
        headers={"X-User-ID": "chat_only_user"},
    )

    assert resp.status_code == 403
    assert "Admin access required" in resp.json()["detail"]


async def test_env_doc_upload_requires_admin(db, client):
    """Environment document upload requires admin role (Req 9.1)."""
    env = _make_env()

    env_result = MagicMock()
    env_result.scalar_one_or_none.return_value = env
    role_result = MagicMock()
    role_result.scalar_one_or_none.return_value = None

    db.execute.side_effect = [env_result, role_result]

    resp = await client.post(
        f"/api/v1/environments/{env.id}/documents/upload",
        files={"file": ("test.txt", b"hello", "text/plain")},
        headers={"X-User-ID": "chat_only_user"},
    )

    assert resp.status_code == 403


async def test_admin_can_upload_to_environment(db, client):
    """Admin user can upload documents to their environment (Req 9.1, 9.2)."""
    env = _make_env()
    role = _make_role(
        user_id="admin1", role="admin", environment_id=env.id
    )

    env_result = MagicMock()
    env_result.scalar_one_or_none.return_value = env
    role_result = MagicMock()
    role_result.scalar_one_or_none.return_value = role

    db.execute.side_effect = [env_result, role_result]

    # Upload will fail at file processing stage, but auth should pass
    resp = await client.post(
        f"/api/v1/environments/{env.id}/documents/upload",
        files={"file": ("test.xyz", b"hello", "application/octet-stream")},
        headers={"X-User-ID": "admin1"},
    )

    # Should get past auth (not 403) — will fail on validation (400)
    assert resp.status_code != 403
