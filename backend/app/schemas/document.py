"""
Document schemas for API requests and responses.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class DocumentUploadResponse(BaseModel):
    """Response schema for document upload."""

    id: UUID
    filename: str
    file_size: int
    content_type: str
    processing_status: str
    upload_date: datetime
    environment_id: Optional[UUID] = None
    extraction_metadata: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class DocumentListResponse(BaseModel):
    """Response schema for document listing."""

    id: UUID
    filename: str
    file_size: int
    content_type: str
    processing_status: str
    upload_date: datetime
    environment_id: Optional[UUID] = None
    chunk_count: Optional[int] = 0

    class Config:
        from_attributes = True


class DocumentDetailResponse(BaseModel):
    """Response schema for detailed document information."""
    
    id: UUID
    filename: str
    file_size: int
    content_type: str
    processing_status: str
    upload_date: datetime
    chunks: List["DocumentChunkResponse"] = []
    
    class Config:
        from_attributes = True


class DocumentChunkResponse(BaseModel):
    """Response schema for document chunks."""
    
    id: UUID
    chunk_index: int
    content: str
    start_position: int
    end_position: int
    token_count: int
    created_at: datetime
    
    class Config:
        from_attributes = True


class DocumentDeleteResponse(BaseModel):
    """Response schema for document deletion."""
    
    message: str
    deleted_document_id: UUID
    deleted_chunks_count: int


class FileValidationError(BaseModel):
    """Schema for file validation errors."""
    
    field: str
    message: str
    code: str


class UploadErrorResponse(BaseModel):
    """Response schema for upload errors."""
    
    error: str
    details: List[FileValidationError] = []
    
    
# File validation constants
ALLOWED_EXTENSIONS = {".pdf", ".txt", ".docx", ".md", ".markdown"}
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "text/plain", 
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/markdown",
    "text/x-markdown"
}

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
MIN_FILE_SIZE = 1  # 1 byte