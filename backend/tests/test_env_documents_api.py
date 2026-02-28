"""
Tests for environment-scoped document management API endpoints.

Validates requirements 9.2, 9.4, 9.6:
- Documents are associated with environments (not individual users)
- Admin-only access control for document management
- Admins can create and delete documents across environments
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
import pytest

from app.db.base import get_db
from app.main import app
from app.models.document import Document, DocumentChunk
from app.models.environment import Environment
from app.models.user_role import UserRole

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


def _make_doc(environment_id=None, **kwargs):
    defaults = {
        "id": uuid4(),
        "user_id": "default_admin",
        "filename": "test.txt",
        "file_size": 100,
        "content_type": "text/plain",
        "processing_status": "processed",
        "upload_date": _NOW,
        "environment_id": environment_id,
    }
    defaults.update(kwargs)
    return Document(**defaults)


def _make_role(user_id="default_admin", role="admin", environment_id=None):
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
    db.delete = AsyncMock()
    db.rollback = AsyncMock()
    db.close = AsyncMock()
    return db


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
# LIST  -  GET /api/v1/environments/{env_id}/documents
# ---------------------------------------------------------------------------


async def test_list_env_documents_success(db, client):
    """List documents filtered by environment."""
    env = _make_env()
    doc = _make_doc(environment_id=env.id)

    # 1st execute: _get_environment
    env_result = MagicMock()
    env_result.scalar_one_or_none.return_value = env

    # 2nd execute: list query
    list_result = MagicMock()
    list_result.all.return_value = [(doc, 3)]

    db.execute.side_effect = [env_result, list_result]

    resp = await client.get(f"/api/v1/environments/{env.id}/documents")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["filename"] == "test.txt"
    assert data[0]["environment_id"] == str(env.id)
    assert data[0]["chunk_count"] == 3


async def test_list_env_documents_empty(db, client):
    """Empty list when environment has no documents."""
    env = _make_env()

    env_result = MagicMock()
    env_result.scalar_one_or_none.return_value = env
    list_result = MagicMock()
    list_result.all.return_value = []

    db.execute.side_effect = [env_result, list_result]

    resp = await client.get(f"/api/v1/environments/{env.id}/documents")

    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_env_documents_not_found(db, client):
    """404 when environment does not exist."""
    env_result = MagicMock()
    env_result.scalar_one_or_none.return_value = None
    db.execute.return_value = env_result

    resp = await client.get(
        f"/api/v1/environments/{uuid4()}/documents"
    )

    assert resp.status_code == 404
    assert "Environment not found" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# DELETE  -  DELETE /api/v1/environments/{env_id}/documents/{doc_id}
# ---------------------------------------------------------------------------


async def test_delete_env_document_success(db, client):
    """Admin can delete a document scoped to an environment."""
    env = _make_env()
    doc = _make_doc(environment_id=env.id)
    role = _make_role(environment_id=env.id)

    # 1: _get_environment, 2: _verify_admin, 3: find doc, 4: chunk count
    env_result = MagicMock()
    env_result.scalar_one_or_none.return_value = env
    role_result = MagicMock()
    role_result.scalar_one_or_none.return_value = role
    doc_result = MagicMock()
    doc_result.scalar_one_or_none.return_value = doc
    count_result = MagicMock()
    count_result.scalar.return_value = 5

    db.execute.side_effect = [
        env_result,
        role_result,
        doc_result,
        count_result,
    ]

    resp = await client.delete(
        f"/api/v1/environments/{env.id}/documents/{doc.id}",
        headers={"X-User-ID": "default_admin"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["deleted_document_id"] == str(doc.id)
    assert data["deleted_chunks_count"] == 5
    db.delete.assert_called_once_with(doc)
    db.commit.assert_called_once()


async def test_delete_env_document_forbidden(db, client):
    """Non-admin user gets 403 when deleting."""
    env = _make_env()
    doc = _make_doc(environment_id=env.id)

    env_result = MagicMock()
    env_result.scalar_one_or_none.return_value = env
    role_result = MagicMock()
    role_result.scalar_one_or_none.return_value = None  # no admin role

    db.execute.side_effect = [env_result, role_result]

    resp = await client.delete(
        f"/api/v1/environments/{env.id}/documents/{doc.id}",
        headers={"X-User-ID": "non_admin_user"},
    )

    assert resp.status_code == 403
    assert "Admin access required" in resp.json()["detail"]


async def test_delete_env_document_not_found(db, client):
    """404 when document does not belong to the environment."""
    env = _make_env()
    role = _make_role(environment_id=env.id)

    env_result = MagicMock()
    env_result.scalar_one_or_none.return_value = env
    role_result = MagicMock()
    role_result.scalar_one_or_none.return_value = role
    doc_result = MagicMock()
    doc_result.scalar_one_or_none.return_value = None

    db.execute.side_effect = [env_result, role_result, doc_result]

    resp = await client.delete(
        f"/api/v1/environments/{env.id}/documents/{uuid4()}",
        headers={"X-User-ID": "default_admin"},
    )

    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"]


async def test_delete_env_document_env_not_found(db, client):
    """404 when environment does not exist."""
    env_result = MagicMock()
    env_result.scalar_one_or_none.return_value = None
    db.execute.return_value = env_result

    resp = await client.delete(
        f"/api/v1/environments/{uuid4()}/documents/{uuid4()}"
    )

    assert resp.status_code == 404
    assert "Environment not found" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# UPLOAD  -  POST /api/v1/environments/{env_id}/documents/upload
# ---------------------------------------------------------------------------


async def test_upload_env_document_forbidden(db, client):
    """Non-admin user gets 403 when uploading."""
    env = _make_env()

    env_result = MagicMock()
    env_result.scalar_one_or_none.return_value = env
    role_result = MagicMock()
    role_result.scalar_one_or_none.return_value = None

    db.execute.side_effect = [env_result, role_result]

    resp = await client.post(
        f"/api/v1/environments/{env.id}/documents/upload",
        files={"file": ("test.txt", b"hello", "text/plain")},
        headers={"X-User-ID": "non_admin_user"},
    )

    assert resp.status_code == 403
    assert "Admin access required" in resp.json()["detail"]


async def test_upload_env_document_env_not_found(db, client):
    """404 when environment does not exist."""
    env_result = MagicMock()
    env_result.scalar_one_or_none.return_value = None
    db.execute.return_value = env_result

    resp = await client.post(
        f"/api/v1/environments/{uuid4()}/documents/upload",
        files={"file": ("test.txt", b"hello", "text/plain")},
        headers={"X-User-ID": "default_admin"},
    )

    assert resp.status_code == 404
    assert "Environment not found" in resp.json()["detail"]
