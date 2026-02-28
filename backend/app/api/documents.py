"""
Document upload and management API endpoints.
"""

import logging
import os
from pathlib import Path
from typing import List
from uuid import UUID

import aiofiles
from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.base import get_db
from app.models.document import Document, DocumentChunk
from app.models.environment import Environment
from app.models.user_role import RoleType, UserRole
from app.schemas.document import (
    DocumentDeleteResponse,
    DocumentDetailResponse,
    DocumentListResponse,
    DocumentUploadResponse,
    UploadErrorResponse,
)
from app.services.file_validator import FileValidator
from app.services.text_extractor import TextExtractionError, TextExtractionService

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
    file: UploadFile = File(...),
    user_id: str = "default_user",  # TODO: Replace with actual auth
    db: AsyncSession = Depends(get_db)
):
    """
    Upload a document for processing.
    
    Supports PDF, TXT, DOCX, and Markdown files up to 50MB.
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
        
        # Write file asynchronously
        async with aiofiles.open(file_path, 'wb') as f:
            content = await file.read()
            await f.write(content)
        
        # Extract text from the uploaded file
        try:
            text_extractor = TextExtractionService()
            extraction_result = text_extractor.extract_text(content, file_info["filename"])
            
            # Update document with extraction metadata
            document.extraction_metadata = {
                "extraction_method": extraction_result.extraction_method,
                "word_count": extraction_result.word_count,
                "character_count": extraction_result.character_count,
                "extraction_metadata": extraction_result.metadata
            }
            
            # Chunk the extracted text
            from app.services.text_chunker import TextChunkingService
            from app.services.embedding_service import EmbeddingService
            
            chunker = TextChunkingService()
            chunks = chunker.chunk_document_text(
                text=extraction_result.text,
                document_id=document.id,
                chunk_size=settings.CHUNK_SIZE,
                chunk_overlap=settings.CHUNK_OVERLAP
            )
            
            # Generate embeddings for chunks
            embedding_service = EmbeddingService()
            chunk_dicts = [{"id": str(chunk.id), "content": chunk.content} for chunk in chunks]
            embedding_results = await embedding_service.generate_embeddings_for_chunks(chunk_dicts)
            
            # Create a mapping of chunk_id to embedding
            embedding_map = {result.id: result.embedding for result in embedding_results.results}
            
            # Validate that all chunks have embeddings before marking as processed
            chunks_with_embeddings = 0
            chunks_without_embeddings = []
            
            # Store chunks with embeddings in database
            for chunk in chunks:
                chunk_embedding = embedding_map.get(str(chunk.id))
                if chunk_embedding is not None:
                    chunks_with_embeddings += 1
                    document_chunk = DocumentChunk(
                        id=chunk.id,
                        document_id=document.id,
                        chunk_index=chunk.metadata.chunk_index,
                        content=chunk.content,
                        start_position=chunk.metadata.start_position,
                        end_position=chunk.metadata.end_position,
                        token_count=chunk.metadata.token_count,
                        embedding=chunk_embedding
                    )
                    db.add(document_chunk)
                else:
                    chunks_without_embeddings.append(str(chunk.id))
            
            # Log embedding validation results
            logger.info(
                f"Document {document.id} embedding validation: "
                f"{chunks_with_embeddings}/{len(chunks)} chunks have embeddings"
            )
            
            if chunks_without_embeddings:
                logger.warning(
                    f"Document {document.id} has {len(chunks_without_embeddings)} chunks without embeddings: "
                    f"{chunks_without_embeddings[:5]}..."  # Log first 5 chunk IDs
                )
            
            # Only mark as processed if all chunks have embeddings
            if chunks_with_embeddings == len(chunks) and chunks_with_embeddings > 0:
                document.processing_status = "processed"
                logger.info(f"Document {document.id} marked as processed with {chunks_with_embeddings} chunks")
            elif chunks_with_embeddings > 0:
                document.processing_status = "partially_processed"
                document.extraction_metadata["embedding_issues"] = {
                    "chunks_with_embeddings": chunks_with_embeddings,
                    "chunks_without_embeddings": len(chunks_without_embeddings),
                    "failed_chunk_ids": chunks_without_embeddings
                }
                logger.warning(f"Document {document.id} marked as partially_processed due to embedding failures")
            else:
                document.processing_status = "embedding_failed"
                document.extraction_metadata["embedding_error"] = "No chunks received embeddings"
                logger.error(f"Document {document.id} marked as embedding_failed - no embeddings generated")
            
        except TextExtractionError as e:
            # If text extraction fails, mark as failed but don't fail the upload
            document.processing_status = "extraction_failed"
            document.extraction_metadata = {
                "error": str(e),
                "error_type": e.file_type
            }
        
        await db.commit()
        
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
    
    # Build response
    response_data = DocumentDetailResponse.from_orm(document).dict()
    response_data["chunks"] = [
        {
            "id": chunk.id,
            "chunk_index": chunk.chunk_index,
            "content": chunk.content,
            "start_position": chunk.start_position,
            "end_position": chunk.end_position,
            "token_count": chunk.token_count,
            "created_at": chunk.created_at
        }
        for chunk in chunks
    ]
    
    return DocumentDetailResponse(**response_data)


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
    file: UploadFile = File(...),
    user_id: str = Header(default="default_admin", alias="X-User-ID"),
    db: AsyncSession = Depends(get_db),
):
    """Upload a document into a specific environment (admin only)."""
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

        async with aiofiles.open(file_path, "wb") as f:
            content = await file.read()
            await f.write(content)

        # Extract, chunk, embed
        try:
            from app.services.embedding_service import EmbeddingService
            from app.services.text_chunker import TextChunkingService

            text_extractor = TextExtractionService()
            extraction_result = text_extractor.extract_text(
                content, file_info["filename"]
            )

            document.extraction_metadata = {
                "extraction_method": extraction_result.extraction_method,
                "word_count": extraction_result.word_count,
                "character_count": extraction_result.character_count,
                "extraction_metadata": extraction_result.metadata,
            }

            chunker = TextChunkingService()
            chunks = chunker.chunk_document_text(
                text=extraction_result.text,
                document_id=document.id,
                chunk_size=settings.CHUNK_SIZE,
                chunk_overlap=settings.CHUNK_OVERLAP,
            )

            embedding_service = EmbeddingService()
            chunk_dicts = [
                {"id": str(c.id), "content": c.content} for c in chunks
            ]
            embedding_results = (
                await embedding_service.generate_embeddings_for_chunks(
                    chunk_dicts
                )
            )
            embedding_map = {
                r.id: r.embedding for r in embedding_results.results
            }

            ok = 0
            for chunk in chunks:
                emb = embedding_map.get(str(chunk.id))
                if emb is not None:
                    ok += 1
                    db.add(
                        DocumentChunk(
                            id=chunk.id,
                            document_id=document.id,
                            chunk_index=chunk.metadata.chunk_index,
                            content=chunk.content,
                            start_position=chunk.metadata.start_position,
                            end_position=chunk.metadata.end_position,
                            token_count=chunk.metadata.token_count,
                            embedding=emb,
                        )
                    )

            if ok == len(chunks) and ok > 0:
                document.processing_status = "processed"
            elif ok > 0:
                document.processing_status = "partially_processed"
            else:
                document.processing_status = "embedding_failed"

        except TextExtractionError as e:
            document.processing_status = "extraction_failed"
            document.extraction_metadata = {
                "error": str(e),
                "error_type": e.file_type,
            }

        await db.commit()
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
