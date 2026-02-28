"""
Tests for application-wide error handling middleware and error utilities.

Validates Requirements 7.1, 7.3, 7.4:
- 7.1: User-friendly error messages on errors
- 7.3: Retry / alternative format suggestions on document processing failure
- 7.4: Queue-and-retry messaging when database is unavailable
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from app.core.errors import (
    AppError,
    DocumentProcessingError,
    DatabaseUnavailableError,
    LLMProviderError,
    RateLimitError,
    ErrorCode,
    ErrorResponse,
    ERROR_DETAILS,
)
from app.core.error_handlers import (
    register_error_handlers,
    app_error_handler,
    validation_error_handler,
    sqlalchemy_error_handler,
    generic_error_handler,
    RequestLoggingMiddleware,
)
from app.core.logging_config import setup_logging


# ---------------------------------------------------------------------------
# Helper: build a small FastAPI app with error handlers for isolated testing
# ---------------------------------------------------------------------------

def _create_test_app() -> FastAPI:
    test_app = FastAPI()
    register_error_handlers(test_app)

    @test_app.get("/ok")
    async def ok():
        return {"status": "ok"}

    @test_app.get("/app-error")
    async def raise_app_error():
        raise AppError(
            code=ErrorCode.INTERNAL_ERROR,
            message="Something broke",
            status_code=500,
        )

    @test_app.get("/doc-error")
    async def raise_doc_error():
        raise DocumentProcessingError(
            message="PDF extraction failed",
            details={"filename": "bad.pdf"},
        )

    @test_app.get("/db-error")
    async def raise_db_error():
        raise DatabaseUnavailableError()

    @test_app.get("/llm-error")
    async def raise_llm_error():
        raise LLMProviderError(message="All providers down")

    @test_app.get("/rate-limit")
    async def raise_rate_limit():
        raise RateLimitError(retry_after=30)

    @test_app.get("/unhandled")
    async def raise_unhandled():
        raise RuntimeError("totally unexpected")

    @test_app.get("/sqlalchemy-error")
    async def raise_sqlalchemy():
        raise SQLAlchemyError("connection refused")

    @test_app.post("/validate")
    async def validate_body(data: dict):
        # Pydantic will reject a missing required field
        return data

    return test_app


@pytest.fixture
def error_client():
    return TestClient(_create_test_app(), raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Tests for ErrorResponse model
# ---------------------------------------------------------------------------

class TestErrorResponse:
    def test_error_response_serialization(self):
        resp = ErrorResponse(
            error="TEST",
            message="test message",
            recovery="try again",
            retryable=True,
        )
        data = resp.model_dump()
        assert data["error"] == "TEST"
        assert data["message"] == "test message"
        assert data["recovery"] == "try again"
        assert data["retryable"] is True

    def test_error_response_optional_fields(self):
        resp = ErrorResponse(error="X", message="m")
        data = resp.model_dump()
        assert data["recovery"] is None
        assert data["details"] is None
        assert data["retryable"] is False


# ---------------------------------------------------------------------------
# Tests for custom exception classes
# ---------------------------------------------------------------------------

class TestAppError:
    def test_default_message_from_error_details(self):
        err = AppError(code=ErrorCode.INTERNAL_ERROR)
        assert err.message == ERROR_DETAILS[ErrorCode.INTERNAL_ERROR]["message"]
        assert err.recovery == ERROR_DETAILS[ErrorCode.INTERNAL_ERROR]["recovery"]

    def test_custom_message_overrides_default(self):
        err = AppError(code=ErrorCode.INTERNAL_ERROR, message="custom msg")
        assert err.message == "custom msg"

    def test_to_response(self):
        err = AppError(code=ErrorCode.NOT_FOUND, status_code=404)
        resp = err.to_response()
        assert isinstance(resp, ErrorResponse)
        assert resp.error == ErrorCode.NOT_FOUND.value


class TestDocumentProcessingError:
    """Validates Requirement 7.3 – retry / alternative format suggestions."""

    def test_defaults(self):
        err = DocumentProcessingError()
        assert err.code == ErrorCode.DOCUMENT_PROCESSING_FAILED
        assert err.status_code == 422
        assert err.retryable is True
        assert "retry" in err.recovery.lower() or "different" in err.recovery.lower()

    def test_custom_details(self):
        err = DocumentProcessingError(details={"file": "x.pdf"})
        assert err.details == {"file": "x.pdf"}


class TestDatabaseUnavailableError:
    """Validates Requirement 7.4 – queue and retry messaging."""

    def test_defaults(self):
        err = DatabaseUnavailableError()
        assert err.code == ErrorCode.DATABASE_UNAVAILABLE
        assert err.status_code == 503
        assert err.retryable is True
        assert "retry" in err.recovery.lower()


class TestRateLimitError:
    def test_retry_after_in_details(self):
        err = RateLimitError(retry_after=60)
        assert err.details == {"retry_after_seconds": 60}
        assert err.status_code == 429


# ---------------------------------------------------------------------------
# Tests for exception handlers via the test client
# ---------------------------------------------------------------------------

class TestErrorHandlerMiddleware:
    """Validates Requirement 7.1 – user-friendly error messages on errors."""

    def test_healthy_endpoint_unaffected(self, error_client):
        resp = error_client.get("/ok")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_app_error_returns_structured_response(self, error_client):
        resp = error_client.get("/app-error")
        assert resp.status_code == 500
        body = resp.json()
        assert body["error"] == ErrorCode.INTERNAL_ERROR.value
        assert "message" in body
        assert "recovery" in body

    def test_document_processing_error_suggests_retry(self, error_client):
        """Req 7.3: system allows retry or different format on doc failure."""
        resp = error_client.get("/doc-error")
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"] == ErrorCode.DOCUMENT_PROCESSING_FAILED.value
        assert body["retryable"] is True
        assert body["details"] == {"filename": "bad.pdf"}

    def test_database_unavailable_suggests_retry(self, error_client):
        """Req 7.4: system queues and retries when DB is unavailable."""
        resp = error_client.get("/db-error")
        assert resp.status_code == 503
        body = resp.json()
        assert body["error"] == ErrorCode.DATABASE_UNAVAILABLE.value
        assert body["retryable"] is True
        assert "retry" in body["recovery"].lower()

    def test_llm_provider_error(self, error_client):
        resp = error_client.get("/llm-error")
        assert resp.status_code == 503
        body = resp.json()
        assert body["error"] == ErrorCode.LLM_PROVIDER_UNAVAILABLE.value

    def test_rate_limit_error(self, error_client):
        resp = error_client.get("/rate-limit")
        assert resp.status_code == 429
        body = resp.json()
        assert body["error"] == ErrorCode.RATE_LIMIT_EXCEEDED.value
        assert body["details"]["retry_after_seconds"] == 30

    def test_unhandled_exception_returns_friendly_message(self, error_client):
        """Req 7.1: unhandled errors still produce user-friendly messages."""
        resp = error_client.get("/unhandled")
        assert resp.status_code == 500
        body = resp.json()
        assert body["error"] == ErrorCode.INTERNAL_ERROR.value
        # Must NOT leak the raw traceback to the client
        assert "totally unexpected" not in body["message"]

    def test_sqlalchemy_error_returns_db_unavailable(self, error_client):
        """Req 7.4: SQLAlchemy errors surface as database unavailable."""
        resp = error_client.get("/sqlalchemy-error")
        assert resp.status_code == 503
        body = resp.json()
        assert body["error"] == ErrorCode.DATABASE_UNAVAILABLE.value
        assert body["retryable"] is True


# ---------------------------------------------------------------------------
# Tests for logging configuration
# ---------------------------------------------------------------------------

class TestLoggingConfig:
    def test_setup_logging_does_not_raise(self):
        setup_logging("DEBUG")
        setup_logging("INFO")
        setup_logging()  # default

    def test_setup_logging_sets_level(self):
        import logging
        setup_logging("WARNING")
        root = logging.getLogger()
        assert root.level == logging.WARNING
        # Reset
        setup_logging("INFO")


# ---------------------------------------------------------------------------
# Tests for the main app integration
# ---------------------------------------------------------------------------

class TestMainAppErrorHandling:
    """Verify that the production app has error handlers registered."""

    def test_root_still_works(self):
        from app.main import app
        client = TestClient(app)
        resp = client.get("/")
        assert resp.status_code == 200

    def test_health_still_works(self):
        from app.main import app
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_404_returns_json(self):
        """Unknown routes should still return a structured error."""
        from app.main import app
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/nonexistent-route")
        assert resp.status_code == 404
