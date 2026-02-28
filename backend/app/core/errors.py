"""
Custom exception classes and error response models for the RAG Chatbot.

Provides user-friendly error messages with recovery suggestions
per Requirements 7.1, 7.3, 7.4.
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ErrorCode(str, Enum):
    """Application error codes."""
    # General
    INTERNAL_ERROR = "INTERNAL_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"

    # Document processing (Req 7.3)
    DOCUMENT_PROCESSING_FAILED = "DOCUMENT_PROCESSING_FAILED"
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    TEXT_EXTRACTION_FAILED = "TEXT_EXTRACTION_FAILED"

    # Database (Req 7.4)
    DATABASE_UNAVAILABLE = "DATABASE_UNAVAILABLE"
    DATABASE_TRANSACTION_FAILED = "DATABASE_TRANSACTION_FAILED"

    # LLM / RAG
    LLM_PROVIDER_UNAVAILABLE = "LLM_PROVIDER_UNAVAILABLE"
    RAG_PIPELINE_FAILED = "RAG_PIPELINE_FAILED"
    EMBEDDING_FAILED = "EMBEDDING_FAILED"

    # Rate limiting
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"

    # Service
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"


# Maps error codes to user-friendly messages and recovery suggestions
ERROR_DETAILS: Dict[str, Dict[str, Any]] = {
    ErrorCode.INTERNAL_ERROR: {
        "message": "An unexpected error occurred. Please try again.",
        "recovery": "If the problem persists, please contact support.",
    },
    ErrorCode.VALIDATION_ERROR: {
        "message": "The request contains invalid data.",
        "recovery": "Please check your input and try again.",
    },
    ErrorCode.NOT_FOUND: {
        "message": "The requested resource was not found.",
        "recovery": "Please verify the resource ID and try again.",
    },
    ErrorCode.DOCUMENT_PROCESSING_FAILED: {
        "message": "Document processing failed.",
        "recovery": "Please retry the upload or try a different file format (PDF, TXT, DOCX, MD).",
    },
    ErrorCode.UNSUPPORTED_FORMAT: {
        "message": "The uploaded file format is not supported.",
        "recovery": "Please upload a file in one of the supported formats: PDF, TXT, DOCX, or MD.",
    },
    ErrorCode.FILE_TOO_LARGE: {
        "message": "The uploaded file exceeds the maximum size limit.",
        "recovery": "Please upload a file smaller than 50 MB.",
    },
    ErrorCode.TEXT_EXTRACTION_FAILED: {
        "message": "Failed to extract text from the document.",
        "recovery": "The file may be corrupted. Please retry or upload a different format.",
    },
    ErrorCode.DATABASE_UNAVAILABLE: {
        "message": "The database service is temporarily unavailable.",
        "recovery": "Your request has been noted. The system will retry automatically.",
    },
    ErrorCode.DATABASE_TRANSACTION_FAILED: {
        "message": "A database operation failed.",
        "recovery": "Please try your request again in a moment.",
    },
    ErrorCode.LLM_PROVIDER_UNAVAILABLE: {
        "message": "The AI service is temporarily unavailable.",
        "recovery": "The system is switching to an alternative provider. Please retry shortly.",
    },
    ErrorCode.RAG_PIPELINE_FAILED: {
        "message": "Failed to generate a response from your documents.",
        "recovery": "Please try rephrasing your question or try again in a moment.",
    },
    ErrorCode.EMBEDDING_FAILED: {
        "message": "Failed to process document embeddings.",
        "recovery": "Please retry the upload. If the issue persists, try a smaller document.",
    },
    ErrorCode.RATE_LIMIT_EXCEEDED: {
        "message": "Too many requests. Please slow down.",
        "recovery": "Wait a moment before sending your next request.",
    },
    ErrorCode.SERVICE_UNAVAILABLE: {
        "message": "The service is temporarily unavailable.",
        "recovery": "Please try again in a few moments.",
    },
}


class ErrorResponse(BaseModel):
    """Standardized error response returned to clients."""
    error: str = Field(..., description="Error code")
    message: str = Field(..., description="User-friendly error message")
    recovery: Optional[str] = Field(None, description="Suggested recovery action")
    details: Optional[Any] = Field(None, description="Additional error details")
    retryable: bool = Field(False, description="Whether the client should retry")


class AppError(Exception):
    """Base application exception with user-friendly messaging."""

    def __init__(
        self,
        code: ErrorCode = ErrorCode.INTERNAL_ERROR,
        message: Optional[str] = None,
        recovery: Optional[str] = None,
        details: Optional[Any] = None,
        status_code: int = 500,
        retryable: bool = False,
    ):
        defaults = ERROR_DETAILS.get(code, ERROR_DETAILS[ErrorCode.INTERNAL_ERROR])
        self.code = code
        self.message = message or defaults["message"]
        self.recovery = recovery or defaults["recovery"]
        self.details = details
        self.status_code = status_code
        self.retryable = retryable
        super().__init__(self.message)

    def to_response(self) -> ErrorResponse:
        return ErrorResponse(
            error=self.code.value,
            message=self.message,
            recovery=self.recovery,
            details=self.details,
            retryable=self.retryable,
        )


class DocumentProcessingError(AppError):
    """Raised when document processing fails (Req 7.3)."""

    def __init__(self, message: Optional[str] = None, details: Optional[Any] = None):
        super().__init__(
            code=ErrorCode.DOCUMENT_PROCESSING_FAILED,
            message=message,
            details=details,
            status_code=422,
            retryable=True,
        )


class DatabaseUnavailableError(AppError):
    """Raised when the database is unavailable (Req 7.4)."""

    def __init__(self, message: Optional[str] = None, details: Optional[Any] = None):
        super().__init__(
            code=ErrorCode.DATABASE_UNAVAILABLE,
            message=message,
            details=details,
            status_code=503,
            retryable=True,
        )


class LLMProviderError(AppError):
    """Raised when LLM providers are unavailable."""

    def __init__(self, message: Optional[str] = None, details: Optional[Any] = None):
        super().__init__(
            code=ErrorCode.LLM_PROVIDER_UNAVAILABLE,
            message=message,
            details=details,
            status_code=503,
            retryable=True,
        )


class RateLimitError(AppError):
    """Raised when rate limits are exceeded."""

    def __init__(self, message: Optional[str] = None, retry_after: Optional[int] = None):
        super().__init__(
            code=ErrorCode.RATE_LIMIT_EXCEEDED,
            message=message,
            details={"retry_after_seconds": retry_after} if retry_after else None,
            status_code=429,
            retryable=True,
        )
