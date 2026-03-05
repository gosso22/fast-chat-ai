"""
Document upload and management API endpoints.
"""

import logging
import os
from pathlib import Path
from typing import List
from uuid import UUID

import aiofiles
from fastapi import APIRouter, BackgroundTasks, Depends, File, Header, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.base import get_db
from app.models.document import Document, DocumentChunk
from app.models.environment import Environment
from app.models.user_role import RoleType, UserRole
from app.schemas.document import (
    DocumentChunkResponse,
    DocumentDeleteResponse,
    DocumentDetailResponse,
    DocumentListResponse,
    DocumentUploadResponse,
    UploadErrorResponse,
)
from app.services.document_processor import process_document_background
from app.services.file_validator import FileValidator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])
env_docs_router = APIRouter(
    prefix="/environments", tags=["environment-documents"]
)


async def _verify_admin(
    user_id: str,
    environment_id: UUID,
    db: AsyncSession,
) -> None:
    """Verify user has admin role for the given environment.

    Raises 403 if the user is not an admin for the environment.
    """
    result = await db.execute(
        select(UserRole).where(
            UserRole.user_id == user_id,
            UserRole.environment_id == environment_id,
            UserRole.role == RoleType.ADMIN.value,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required for this environment",
        )


async def _get_environment(
    environment_id: UUID,
    db: AsyncSession,
) -> Environment:
    """Fetch an environment or raise 404."""
    result = await db.execute(
        select(Environment).where(Environment.id == environment_id)
    )
    env = result.scalar_one_or_none()
    if env is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Environment not found",
        )
    return env


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": UploadErrorResponse},
        413: {"model": UploadErrorResponse},
        422: {"model": UploadErrorResponse}
    }
)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user_id: str = "default_user",  # TODO: Replace with actual auth
    db: AsyncSession = Depends(get_db)
):
    """
    Upload a document for processing.

    Supports PDF, TXT, DOCX, and Markdown files up to 50MB.
    Processing (text extraction, chunking, embedding) happens in the background.
    """
    # Validate file
    is_valid, validation_errors = FileValidator.validate_file(file)

    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=UploadErrorResponse(
                error="File validation failed",
                details=validation_errors
            ).dict()
        )

    try:
        # Get file information
        file_info = FileValidator.get_file_info(file)

        # Create document record
        document = Document(
            user_id=user_id,
            filename=file_info["filename"],
            file_size=file_info["size"],
            content_type=file_info["content_type"],
            processing_status="pending"
        )

        db.add(document)
        await db.commit()
        await db.refresh(document)

        # Save file to disk
        upload_dir = Path(settings.UPLOAD_DIR)
        upload_dir.mkdir(exist_ok=True)

        file_path = upload_dir / f"{document.id}_{file_info['filename']}"

        # Read file content and save to disk
        content = await file.read()
        async with aiofiles.open(file_path, 'wb') as f:
            await f.write(content)

        # Schedule heavy processing in the background
        background_tasks.add_task(
            process_document_background,
            document.id,
            content,
            file_info["filename"],
        )

        return DocumentUploadResponse.from_orm(document)

    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload document: {str(e)}"
        )


@router.get(
    "/",
    response_model=List[DocumentListResponse]
)
async def list_documents(
    user_id: str = "default_user",  # TODO: Replace with actual auth
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """
    List all documents for a user.
    """
    # Query documents with chunk count
    query = (
        select(
            Document,
            func.count(DocumentChunk.id).label("chunk_count")
        )
        .outerjoin(DocumentChunk)
        .where(Document.user_id == user_id)
        .group_by(Document.id)
        .order_by(Document.upload_date.desc())
        .offset(skip)
        .limit(limit)
    )
    
    result = await db.execute(query)
    documents_with_counts = result.all()
    
    # Format response
    response = []
    for doc, chunk_count in documents_with_counts:
        doc_dict = DocumentListResponse.from_orm(doc).dict()
        doc_dict["chunk_count"] = chunk_count or 0
        response.append(DocumentListResponse(**doc_dict))
    
    return response


@router.get(
    "/{document_id}",
    response_model=DocumentDetailResponse
)
async def get_document(
    document_id: UUID,
    user_id: str = "default_user",  # TODO: Replace with actual auth
    db: AsyncSession = Depends(get_db)
):
    """
    Get detailed information about a specific document.
    """
    # Query document with chunks
    query = (
        select(Document)
        .where(
            Document.id == document_id,
            Document.user_id == user_id
        )
    )
    
    result = await db.execute(query)
    document = result.scalar_one_or_none()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    # Get chunks separately to avoid loading issues
    chunks_query = (
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index)
    )
    
    chunks_result = await db.execute(chunks_query)
    chunks = chunks_result.scalars().all()
    
    # Build response without touching the lazy `chunks` relationship
    return DocumentDetailResponse(
        id=document.id,
        filename=document.filename,
        file_size=document.file_size,
        content_type=document.content_type,
        processing_status=document.processing_status,
        upload_date=document.upload_date,
        chunks=[
            DocumentChunkResponse(
                id=chunk.id,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                start_position=chunk.start_position,
                end_position=chunk.end_position,
                token_count=chunk.token_count,
                created_at=chunk.created_at,
            )
            for chunk in chunks
        ],
    )


@router.delete(
    "/{document_id}",
    response_model=DocumentDeleteResponse
)
async def delete_document(
    document_id: UUID,
    user_id: str = "default_user",  # TODO: Replace with actual auth
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a document and all its chunks.
    """
    # Find document
    query = (
        select(Document)
        .where(
            Document.id == document_id,
            Document.user_id == user_id
        )
    )
    
    result = await db.execute(query)
    document = result.scalar_one_or_none()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    try:
        # Count chunks before deletion
        chunks_query = select(func.count(DocumentChunk.id)).where(
            DocumentChunk.document_id == document_id
        )
        chunks_result = await db.execute(chunks_query)
        chunk_count = chunks_result.scalar() or 0
        
        # Delete file from disk
        upload_dir = Path(settings.UPLOAD_DIR)
        file_path = upload_dir / f"{document.id}_{document.filename}"
        
        if file_path.exists():
            os.remove(file_path)
        
        # Delete document (chunks will be deleted via CASCADE)
        await db.delete(document)
        await db.commit()
        
        return DocumentDeleteResponse(
            message="Document deleted successfully",
            deleted_document_id=document_id,
            deleted_chunks_count=chunk_count
        )
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete document: {str(e)}"
        )



# ---------------------------------------------------------------------------
# Environment-scoped document endpoints
# ---------------------------------------------------------------------------


@env_docs_router.post(
    "/{environment_id}/documents/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": UploadErrorResponse},
        403: {"description": "Admin access required"},
        404: {"description": "Environment not found"},
    },
)
async def upload_env_document(
    environment_id: UUID,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user_id: str = Header(default="default_admin", alias="X-User-ID"),
    db: AsyncSession = Depends(get_db),
):
    """Upload a document into a specific environment (admin only).

    Processing (text extraction, chunking, embedding) happens in the background.
    """
    await _get_environment(environment_id, db)
    await _verify_admin(user_id, environment_id, db)

    # Validate file
    is_valid, validation_errors = FileValidator.validate_file(file)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=UploadErrorResponse(
                error="File validation failed",
                details=validation_errors,
            ).dict(),
        )

    try:
        file_info = FileValidator.get_file_info(file)

        document = Document(
            user_id=user_id,
            filename=file_info["filename"],
            file_size=file_info["size"],
            content_type=file_info["content_type"],
            processing_status="pending",
            environment_id=environment_id,
        )
        db.add(document)
        await db.commit()
        await db.refresh(document)

        # Save file to disk
        upload_dir = Path(settings.UPLOAD_DIR)
        upload_dir.mkdir(exist_ok=True)
        file_path = upload_dir / f"{document.id}_{file_info['filename']}"

        content = await file.read()
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(content)

        # Schedule heavy processing in the background
        background_tasks.add_task(
            process_document_background,
            document.id,
            content,
            file_info["filename"],
        )

        return DocumentUploadResponse.from_orm(document)

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload document: {str(e)}",
        ) from e


@env_docs_router.get(
    "/{environment_id}/documents",
    response_model=List[DocumentListResponse],
)
async def list_env_documents(
    environment_id: UUID,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    """List documents belonging to an environment."""
    await _get_environment(environment_id, db)

    query = (
        select(Document, func.count(DocumentChunk.id).label("chunk_count"))
        .outerjoin(DocumentChunk)
        .where(Document.environment_id == environment_id)
        .group_by(Document.id)
        .order_by(Document.upload_date.desc())
        .offset(skip)
        .limit(limit)
    )

    result = await db.execute(query)
    rows = result.all()

    response = []
    for doc, chunk_count in rows:
        d = DocumentListResponse.from_orm(doc).dict()
        d["chunk_count"] = chunk_count or 0
        response.append(DocumentListResponse(**d))
    return response


@env_docs_router.delete(
    "/{environment_id}/documents/{document_id}",
    response_model=DocumentDeleteResponse,
)
async def delete_env_document(
    environment_id: UUID,
    document_id: UUID,
    user_id: str = Header(default="default_admin", alias="X-User-ID"),
    db: AsyncSession = Depends(get_db),
):
    """Delete a document from an environment (admin only)."""
    await _get_environment(environment_id, db)
    await _verify_admin(user_id, environment_id, db)

    # Find document scoped to this environment
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.environment_id == environment_id,
        )
    )
    document = result.scalar_one_or_none()
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found in this environment",
        )

    try:
        chunks_result = await db.execute(
            select(func.count(DocumentChunk.id)).where(
                DocumentChunk.document_id == document_id
            )
        )
        chunk_count = chunks_result.scalar() or 0

        upload_dir = Path(settings.UPLOAD_DIR)
        file_path = upload_dir / f"{document.id}_{document.filename}"
        if file_path.exists():
            os.remove(file_path)

        await db.delete(document)
        await db.commit()

        return DocumentDeleteResponse(
            message="Document deleted successfully",
            deleted_document_id=document_id,
            deleted_chunks_count=chunk_count,
        )
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete document: {str(e)}",
        ) from e
