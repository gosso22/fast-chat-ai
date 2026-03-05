"""
Background document processing pipeline.

Handles text extraction, chunking, embedding generation, and DB storage
outside the HTTP request lifecycle.
"""

import logging
from uuid import UUID

from app.core.config import settings
from app.db.base import get_async_session
from app.models.document import Document, DocumentChunk
from app.services.embedding_service import EmbeddingService
from app.services.text_chunker import TextChunkingService
from app.services.text_extractor import TextExtractionError, TextExtractionService

logger = logging.getLogger(__name__)


async def process_document_background(
    document_id: UUID,
    file_content: bytes,
    filename: str,
) -> None:
    """Process a document in the background: extract text, chunk, embed, store.

    This function owns its own DB session so it can run after the request has
    already returned.
    """
    session = get_async_session()
    try:
        # Re-load the document inside this session
        from sqlalchemy import select

        result = await session.execute(
            select(Document).where(Document.id == document_id)
        )
        document = result.scalar_one_or_none()
        if document is None:
            logger.error("Document %s not found for background processing", document_id)
            return

        # --- Text extraction ---
        try:
            text_extractor = TextExtractionService()
            extraction_result = text_extractor.extract_text(file_content, filename)
        except TextExtractionError as e:
            document.processing_status = "extraction_failed"
            document.extraction_metadata = {
                "error": str(e),
                "error_type": e.file_type,
            }
            await session.commit()
            logger.warning("Document %s extraction failed: %s", document_id, e)
            return

        document.extraction_metadata = {
            "extraction_method": extraction_result.extraction_method,
            "word_count": extraction_result.word_count,
            "character_count": extraction_result.character_count,
            "extraction_metadata": extraction_result.metadata,
        }

        # --- Chunking ---
        chunker = TextChunkingService()
        chunks = chunker.chunk_document_text(
            text=extraction_result.text,
            document_id=document.id,
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
        )

        # --- Embedding generation ---
        try:
            embedding_service = EmbeddingService()
            chunk_dicts = [
                {"id": str(c.id), "content": c.content} for c in chunks
            ]
            embedding_results = await embedding_service.generate_embeddings_for_chunks(
                chunk_dicts
            )
        except Exception as e:
            document.processing_status = "embedding_failed"
            document.extraction_metadata["embedding_error"] = str(e)
            await session.commit()
            logger.error("Document %s embedding failed: %s", document_id, e)
            return

        embedding_map = {r.id: r.embedding for r in embedding_results.results}

        # --- Store chunks ---
        ok = 0
        failed_ids: list[str] = []
        for chunk in chunks:
            emb = embedding_map.get(str(chunk.id))
            if emb is not None:
                ok += 1
                session.add(
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
            else:
                failed_ids.append(str(chunk.id))

        logger.info(
            "Document %s embedding validation: %d/%d chunks have embeddings",
            document_id, ok, len(chunks),
        )

        if ok == len(chunks) and ok > 0:
            document.processing_status = "processed"
        elif ok > 0:
            document.processing_status = "partially_processed"
            document.extraction_metadata["embedding_issues"] = {
                "chunks_with_embeddings": ok,
                "chunks_without_embeddings": len(failed_ids),
                "failed_chunk_ids": failed_ids[:20],
            }
        else:
            document.processing_status = "embedding_failed"
            document.extraction_metadata["embedding_error"] = (
                "No chunks received embeddings"
            )

        await session.commit()
        logger.info(
            "Document %s background processing complete: %s",
            document_id, document.processing_status,
        )

    except Exception:
        await session.rollback()
        # Best-effort: try to mark the document as failed
        try:
            result = await session.execute(
                select(Document).where(Document.id == document_id)
            )
            document = result.scalar_one_or_none()
            if document:
                document.processing_status = "embedding_failed"
                document.extraction_metadata = document.extraction_metadata or {}
                document.extraction_metadata["error"] = "Unexpected processing error"
                await session.commit()
        except Exception:
            await session.rollback()
        logger.exception("Unexpected error processing document %s", document_id)
    finally:
        await session.close()
