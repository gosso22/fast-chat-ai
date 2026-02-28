"""
Centralized error handling middleware and exception handlers for FastAPI.

Catches all unhandled exceptions and returns user-friendly error responses
with recovery suggestions (Requirements 7.1, 7.3, 7.4).
"""

import logging
import time
import traceback
from typing import Callable

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, OperationalError, SQLAlchemyError
from starlette.middleware.base import BaseHTTPMiddleware

from .errors import (
    AppError,
    DatabaseUnavailableError,
    ErrorCode,
    ErrorResponse,
    ERROR_DETAILS,
)

logger = logging.getLogger("rag_chatbot.errors")


# ---------------------------------------------------------------------------
# Exception handlers (registered on the FastAPI app)
# ---------------------------------------------------------------------------

async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Handle custom AppError exceptions with user-friendly responses."""
    logger.error(
        "AppError [%s] %s | path=%s details=%s",
        exc.code.value,
        exc.message,
        request.url.path,
        exc.details,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_response().model_dump(),
    )


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle Pydantic / request validation errors with friendly messages."""
    details = []
    for err in exc.errors():
        loc = " -> ".join(str(l) for l in err.get("loc", []))
        details.append({"field": loc, "message": err.get("msg", "")})

    logger.warning("Validation error on %s: %s", request.url.path, details)

    defaults = ERROR_DETAILS[ErrorCode.VALIDATION_ERROR]
    body = ErrorResponse(
        error=ErrorCode.VALIDATION_ERROR.value,
        message=defaults["message"],
        recovery=defaults["recovery"],
        details=details,
        retryable=False,
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=body.model_dump(),
    )


async def sqlalchemy_error_handler(
    request: Request, exc: SQLAlchemyError
) -> JSONResponse:
    """Handle SQLAlchemy / database errors (Req 7.4)."""
    logger.error(
        "Database error on %s: %s",
        request.url.path,
        str(exc),
        exc_info=True,
    )
    defaults = ERROR_DETAILS[ErrorCode.DATABASE_UNAVAILABLE]
    body = ErrorResponse(
        error=ErrorCode.DATABASE_UNAVAILABLE.value,
        message=defaults["message"],
        recovery=defaults["recovery"],
        retryable=True,
    )
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=body.model_dump(),
    )


async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler for any unhandled exception (Req 7.1)."""
    logger.error(
        "Unhandled exception on %s: %s\n%s",
        request.url.path,
        str(exc),
        traceback.format_exc(),
    )
    defaults = ERROR_DETAILS[ErrorCode.INTERNAL_ERROR]
    body = ErrorResponse(
        error=ErrorCode.INTERNAL_ERROR.value,
        message=defaults["message"],
        recovery=defaults["recovery"],
        retryable=False,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=body.model_dump(),
    )


# ---------------------------------------------------------------------------
# Request logging middleware
# ---------------------------------------------------------------------------

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Logs every request/response with timing and records metrics."""

    async def dispatch(self, request: Request, call_next: Callable):
        from app.services.metrics_collector import metrics_collector, RequestMetric

        start = time.time()
        request_id = request.headers.get("X-Request-ID", "")

        logger.info(
            "Request  %s %s [request_id=%s]",
            request.method,
            request.url.path,
            request_id,
        )

        error_msg = None
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as exc:
            duration_ms = (time.time() - start) * 1000
            error_msg = str(exc)
            logger.error(
                "Request  %s %s failed after %.1f ms [request_id=%s]",
                request.method,
                request.url.path,
                duration_ms,
                request_id,
            )
            await metrics_collector.record_request(RequestMetric(
                endpoint=request.url.path,
                method=request.method,
                status_code=500,
                duration_ms=duration_ms,
                error=error_msg,
            ))
            raise

        duration_ms = (time.time() - start) * 1000
        logger.info(
            "Response %s %s -> %s (%.1f ms) [request_id=%s]",
            request.method,
            request.url.path,
            status_code,
            duration_ms,
            request_id,
        )

        await metrics_collector.record_request(RequestMetric(
            endpoint=request.url.path,
            method=request.method,
            status_code=status_code,
            duration_ms=duration_ms,
        ))

        return response


# ---------------------------------------------------------------------------
# Registration helper
# ---------------------------------------------------------------------------

def register_error_handlers(app: FastAPI) -> None:
    """Register all exception handlers and middleware on the FastAPI app."""
    # Order matters: more specific first
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(SQLAlchemyError, sqlalchemy_error_handler)
    app.add_exception_handler(Exception, generic_error_handler)

    # Request logging middleware
    app.add_middleware(RequestLoggingMiddleware)
