"""
Vector storage service for RAG applications.
Implements PostgreSQL vector storage using pgvector extension with similarity search and document management.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Tuple
from uuid import UUID

from sqlalchemy import select, delete, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.document import Document, DocumentChunk
from ..db.base import get_db
from .embedding_service import EmbeddingService, EmbeddingResult

logger = logging.getLogger(__name__)


@dataclass
class ChunkData:
    """Data structure for storing chunk information."""
    
    id: UUID
    document_id: UUID
    chunk_index: int
    content: str
    start_position: int
    end_position: int
    token_count: int
    embedding: Optional[List[float]] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "id": str(self.id),
            "document_id": str(self.document_id),
            "chunk_index": self.chunk_index,
            "content": self.content,
            "start_position": self.start_position,
            "end_position": self.end_position,
            "token_count": self.token_count,
            "embedding": self.embedding,
            "metadata": self.metadata or {}
        }


@dataclass
class DocumentMetadata:
    """Metadata for documents in vector storage."""
    
    id: UUID
    filename: str
    user_id: str
    upload_date: str
    file_size: int
    content_type: str
    processing_status: str
    chunk_count: int = 0
    environment_id: Optional[UUID] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "id": str(self.id),
            "filename": self.filename,
            "user_id": self.user_id,
            "upload_date": self.upload_date,
            "file_size": self.file_size,
            "content_type": self.content_type,
            "processing_status": self.processing_status,
            "chunk_count": self.chunk_count
        }


@dataclass
class SearchResult:
    """Result from similarity search."""
    
    chunk: ChunkData
    document: DocumentMetadata
    similarity_score: float
    rank: int
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "chunk": self.chunk.to_dict(),
            "document": self.document.to_dict(),
            "similarity_score": self.similarity_score,
            "rank": self.rank
        }


@dataclass
class SearchQuery:
    """Query parameters for similarity search."""

    query_text: str
    user_id: Optional[str] = None
    document_ids: Optional[List[UUID]] = None
    environment_id: Optional[UUID] = None
    limit: int = 5
    similarity_threshold: float = 0.0
    include_metadata: bool = True

    def __post_init__(self):
        """Validate search query parameters."""
        if self.limit <= 0:
            raise ValueError("Limit must be positive")
        if self.limit > 100:
            raise ValueError("Limit cannot exceed 100")
        if not (0.0 <= self.similarity_threshold <= 1.0):
            raise ValueError("Similarity threshold must be between 0.0 and 1.0")


class VectorStoreError(Exception):
    """Custom exception for vector store operations."""
    
    def __init__(
        self,
        message: str,
        operation: Optional[str] = None,
        document_id: Optional[UUID] = None,
        original_error: Optional[Exception] = None
    ):
        self.message = message
        self.operation = operation
        self.document_id = document_id
        self.original_error = original_error
        super().__init__(self.message)


class BaseVectorStore(ABC):
    """Abstract base class for vector storage operations."""
    
    @abstractmethod
    async def store_chunks(
        self,
        chunks: List[ChunkData],
        document_metadata: DocumentMetadata
    ) -> None:
        """Store document chunks with embeddings."""
        pass
    
    @abstractmethod
    async def search_similar(
        self,
        query: SearchQuery,
        query_embedding: List[float]
    ) -> List[SearchResult]:
        """Search for similar chunks using vector similarity."""
        pass
    
    @abstractmethod
    async def delete_document(self, document_id: UUID, user_id: Optional[str] = None) -> bool:
        """Delete a document and all its chunks."""
        pass
    
    @abstractmethod
    async def get_document_chunks(
        self,
        document_id: UUID,
        user_id: Optional[str] = None
    ) -> List[ChunkData]:
        """Get all chunks for a document."""
        pass
    
    @abstractmethod
    async def get_document_metadata(
        self,
        document_id: UUID,
        user_id: Optional[str] = None
    ) -> Optional[DocumentMetadata]:
        """Get document metadata."""
        pass


class PostgreSQLVectorStore(BaseVectorStore):
    """PostgreSQL vector store implementation using pgvector."""
    
    def __init__(self, session_factory=None):
        self.session_factory = session_factory or get_db
    
    async def store_chunks(
        self,
        chunks: List[ChunkData],
        document_metadata: DocumentMetadata
    ) -> None:
        """
        Store document chunks with embeddings in PostgreSQL.
        
        Args:
            chunks: List of chunk data with embeddings
            document_metadata: Document metadata
            
        Raises:
            VectorStoreError: If storage operation fails
        """
        if not chunks:
            raise VectorStoreError("Cannot store empty chunks list", "store_chunks")
        
        try:
            async for session in self.session_factory():
                try:
                    # First, create or update the document record
                    document = Document(
                        id=document_metadata.id,
                        user_id=document_metadata.user_id,
                        filename=document_metadata.filename,
                        file_size=document_metadata.file_size,
                        content_type=document_metadata.content_type,
                        processing_status=document_metadata.processing_status
                    )
                    
                    # Use merge to handle both insert and update cases
                    session.add(document)
                    
                    # Store all chunks
                    chunk_models = []
                    for chunk_data in chunks:
                        if not chunk_data.embedding:
                            raise VectorStoreError(
                                f"Chunk {chunk_data.id} missing embedding",
                                "store_chunks",
                                document_metadata.id
                            )
                        
                        chunk_model = DocumentChunk(
                            id=chunk_data.id,
                            document_id=chunk_data.document_id,
                            environment_id=document_metadata.environment_id,
                            chunk_index=chunk_data.chunk_index,
                            content=chunk_data.content,
                            start_position=chunk_data.start_position,
                            end_position=chunk_data.end_position,
                            token_count=chunk_data.token_count,
                            embedding=chunk_data.embedding
                        )
                        chunk_models.append(chunk_model)
                    
                    session.add_all(chunk_models)
                    await session.commit()
                    
                    logger.info(
                        f"Successfully stored {len(chunks)} chunks for document {document_metadata.id}"
                    )
                    break  # Exit the async for loop after successful operation
                finally:
                    await session.close()
                
        except Exception as e:
            logger.error(f"Failed to store chunks for document {document_metadata.id}: {e}")
            raise VectorStoreError(
                f"Failed to store chunks: {str(e)}",
                "store_chunks",
                document_metadata.id,
                e
            )
    
    async def search_similar(
        self,
        query: SearchQuery,
        query_embedding: List[float]
    ) -> List[SearchResult]:
        """
        Search for similar chunks using cosine similarity.
        
        Args:
            query: Search query parameters
            query_embedding: Query text embedding vector
            
        Returns:
            List of search results ordered by similarity
            
        Raises:
            VectorStoreError: If search operation fails
        """
        try:
            async for session in self.session_factory():
                try:
                    # Build the base query with similarity calculation
                    # Using pgvector's cosine distance (1 - cosine_similarity)
                    similarity_expr = (
                        1 - DocumentChunk.embedding.cosine_distance(query_embedding)
                    ).label('similarity_score')
                    
                    # Base query with joins
                    query_stmt = (
                        select(
                            DocumentChunk,
                            Document,
                            similarity_expr,
                            func.row_number().over(
                                order_by=similarity_expr.desc()
                            ).label('rank')
                        )
                        .join(Document, DocumentChunk.document_id == Document.id)
                        .where(DocumentChunk.embedding.is_not(None))
                    )
                    
                    # Apply filters
                    # When environment_id is set, skip user_id filter — environment
                    # scoping already provides data isolation and all users with
                    # access to the environment should search all its documents.
                    if query.user_id and not query.environment_id:
                        query_stmt = query_stmt.where(Document.user_id == query.user_id)

                    if query.document_ids:
                        query_stmt = query_stmt.where(Document.id.in_(query.document_ids))

                    if query.environment_id:
                        query_stmt = query_stmt.where(
                            DocumentChunk.environment_id == query.environment_id
                        )
                    
                    if query.similarity_threshold > 0.0:
                        query_stmt = query_stmt.where(similarity_expr >= query.similarity_threshold)
                    
                    # Order by similarity and limit results
                    query_stmt = (
                        query_stmt
                        .order_by(similarity_expr.desc())
                        .limit(query.limit)
                    )
                    
                    result = await session.execute(query_stmt)
                    rows = result.fetchall()
                
                    # Convert results to SearchResult objects
                    search_results = []
                    for row in rows:
                        chunk_model, document_model, similarity_score, rank = row
                        
                        chunk_data = ChunkData(
                            id=chunk_model.id,
                            document_id=chunk_model.document_id,
                            chunk_index=chunk_model.chunk_index,
                            content=chunk_model.content,
                            start_position=chunk_model.start_position,
                            end_position=chunk_model.end_position,
                            token_count=chunk_model.token_count,
                            embedding=chunk_model.embedding if query.include_metadata else None
                        )
                        
                        document_metadata = DocumentMetadata(
                            id=document_model.id,
                            filename=document_model.filename,
                            user_id=document_model.user_id,
                            upload_date=document_model.upload_date.isoformat(),
                            file_size=document_model.file_size,
                            content_type=document_model.content_type,
                            processing_status=document_model.processing_status
                        )
                        
                        search_result = SearchResult(
                            chunk=chunk_data,
                            document=document_metadata,
                            similarity_score=float(similarity_score),
                            rank=int(rank)
                        )
                        search_results.append(search_result)
                    
                    logger.info(
                        f"Similarity search returned {len(search_results)} results "
                        f"for query: '{query.query_text[:50]}...'"
                    )
                    
                    return search_results
                finally:
                    await session.close()
                
        except Exception as e:
            logger.error(f"Failed to perform similarity search: {e}")
            raise VectorStoreError(
                f"Failed to search similar chunks: {str(e)}",
                "search_similar",
                original_error=e
            )
    
    async def delete_document(self, document_id: UUID, user_id: Optional[str] = None) -> bool:
        """
        Delete a document and all its chunks.
        
        Args:
            document_id: ID of document to delete
            user_id: Optional user ID for authorization
            
        Returns:
            True if document was deleted, False if not found
            
        Raises:
            VectorStoreError: If deletion operation fails
        """
        try:
            async for session in self.session_factory():
                try:
                    # Build delete query with optional user filter
                    delete_stmt = delete(Document).where(Document.id == document_id)
                    
                    if user_id:
                        delete_stmt = delete_stmt.where(Document.user_id == user_id)
                    
                    result = await session.execute(delete_stmt)
                    await session.commit()
                    
                    deleted_count = result.rowcount
                    
                    if deleted_count > 0:
                        logger.info(f"Successfully deleted document {document_id}")
                        return True
                    else:
                        logger.warning(f"Document {document_id} not found or not authorized")
                        return False
                finally:
                    await session.close()
                    
        except Exception as e:
            logger.error(f"Failed to delete document {document_id}: {e}")
            raise VectorStoreError(
                f"Failed to delete document: {str(e)}",
                "delete_document",
                document_id,
                e
            )
    
    async def get_document_chunks(
        self,
        document_id: UUID,
        user_id: Optional[str] = None
    ) -> List[ChunkData]:
        """
        Get all chunks for a document.
        
        Args:
            document_id: ID of document
            user_id: Optional user ID for authorization
            
        Returns:
            List of chunk data
            
        Raises:
            VectorStoreError: If retrieval operation fails
        """
        try:
            async for session in self.session_factory():
                try:
                    # Build query with optional user filter
                    query_stmt = (
                        select(DocumentChunk)
                        .join(Document, DocumentChunk.document_id == Document.id)
                        .where(DocumentChunk.document_id == document_id)
                        .order_by(DocumentChunk.chunk_index)
                    )
                    
                    if user_id:
                        query_stmt = query_stmt.where(Document.user_id == user_id)
                    
                    result = await session.execute(query_stmt)
                    chunk_models = result.scalars().all()
                    
                    # Convert to ChunkData objects
                    chunks = []
                    for chunk_model in chunk_models:
                        chunk_data = ChunkData(
                            id=chunk_model.id,
                            document_id=chunk_model.document_id,
                            chunk_index=chunk_model.chunk_index,
                            content=chunk_model.content,
                            start_position=chunk_model.start_position,
                            end_position=chunk_model.end_position,
                            token_count=chunk_model.token_count,
                            embedding=chunk_model.embedding
                        )
                        chunks.append(chunk_data)
                    
                    logger.info(f"Retrieved {len(chunks)} chunks for document {document_id}")
                    return chunks
                finally:
                    await session.close()
                
        except Exception as e:
            logger.error(f"Failed to get chunks for document {document_id}: {e}")
            raise VectorStoreError(
                f"Failed to get document chunks: {str(e)}",
                "get_document_chunks",
                document_id,
                e
            )
    
    async def get_document_metadata(
        self,
        document_id: UUID,
        user_id: Optional[str] = None
    ) -> Optional[DocumentMetadata]:
        """
        Get document metadata.
        
        Args:
            document_id: ID of document
            user_id: Optional user ID for authorization
            
        Returns:
            Document metadata or None if not found
            
        Raises:
            VectorStoreError: If retrieval operation fails
        """
        try:
            async for session in self.session_factory():
                try:
                    # Build query with optional user filter and chunk count
                    query_stmt = (
                        select(
                            Document,
                            func.count(DocumentChunk.id).label('chunk_count')
                        )
                        .outerjoin(DocumentChunk, Document.id == DocumentChunk.document_id)
                        .where(Document.id == document_id)
                        .group_by(Document.id)
                    )
                    
                    if user_id:
                        query_stmt = query_stmt.where(Document.user_id == user_id)
                    
                    result = await session.execute(query_stmt)
                    row = result.first()
                    
                    if not row:
                        return None
                    
                    document_model, chunk_count = row
                    
                    metadata = DocumentMetadata(
                        id=document_model.id,
                        filename=document_model.filename,
                        user_id=document_model.user_id,
                        upload_date=document_model.upload_date.isoformat(),
                        file_size=document_model.file_size,
                        content_type=document_model.content_type,
                        processing_status=document_model.processing_status,
                        chunk_count=chunk_count
                    )
                    
                    return metadata
                finally:
                    await session.close()
                
        except Exception as e:
            logger.error(f"Failed to get metadata for document {document_id}: {e}")
            raise VectorStoreError(
                f"Failed to get document metadata: {str(e)}",
                "get_document_metadata",
                document_id,
                e
            )
    
    async def get_storage_stats(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get storage statistics.
        
        Args:
            user_id: Optional user ID to filter stats
            
        Returns:
            Dictionary with storage statistics
        """
        try:
            async for session in self.session_factory():
                try:
                    # Build base queries
                    doc_query = select(func.count(Document.id))
                    chunk_query = select(func.count(DocumentChunk.id))
                    
                    if user_id:
                        doc_query = doc_query.where(Document.user_id == user_id)
                        chunk_query = (
                            chunk_query
                            .join(Document, DocumentChunk.document_id == Document.id)
                            .where(Document.user_id == user_id)
                        )
                    
                    # Execute queries
                    doc_count_result = await session.execute(doc_query)
                    chunk_count_result = await session.execute(chunk_query)
                    
                    doc_count = doc_count_result.scalar()
                    chunk_count = chunk_count_result.scalar()
                    
                    return {
                        "document_count": doc_count,
                        "chunk_count": chunk_count,
                        "user_id": user_id
                    }
                finally:
                    await session.close()
                
        except Exception as e:
            logger.error(f"Failed to get storage stats: {e}")
            raise VectorStoreError(
                f"Failed to get storage statistics: {str(e)}",
                "get_storage_stats",
                original_error=e
            )


class VectorStoreService:
    """Main service for vector storage operations."""
    
    def __init__(
        self,
        vector_store: Optional[BaseVectorStore] = None,
        embedding_service: Optional[EmbeddingService] = None
    ):
        self.vector_store = vector_store or PostgreSQLVectorStore()
        self.embedding_service = embedding_service or EmbeddingService()
    
    async def store_document_chunks(
        self,
        chunks: List[Dict[str, Any]],
        document_metadata: Dict[str, Any]
    ) -> None:
        """
        Store document chunks with automatic embedding generation.
        
        Args:
            chunks: List of chunk dictionaries with content and metadata
            document_metadata: Document metadata dictionary
        """
        # Convert chunks to ChunkData objects
        chunk_data_list = []
        for chunk in chunks:
            chunk_data = ChunkData(
                id=chunk['id'],
                document_id=chunk['document_id'],
                chunk_index=chunk['chunk_index'],
                content=chunk['content'],
                start_position=chunk['start_position'],
                end_position=chunk['end_position'],
                token_count=chunk['token_count'],
                metadata=chunk.get('metadata')
            )
            chunk_data_list.append(chunk_data)
        
        # Generate embeddings for all chunks
        embedding_requests = [
            {"id": str(chunk.id), "content": chunk.content}
            for chunk in chunk_data_list
        ]
        
        batch_result = await self.embedding_service.generate_embeddings_for_chunks(
            embedding_requests
        )
        
        if batch_result.failure_count > 0:
            logger.warning(
                f"Failed to generate embeddings for {batch_result.failure_count} chunks"
            )
        
        # Map embeddings back to chunks
        embedding_map = {result.id: result.embedding for result in batch_result.results}
        
        for chunk_data in chunk_data_list:
            chunk_id = str(chunk_data.id)
            if chunk_id in embedding_map:
                chunk_data.embedding = embedding_map[chunk_id]
            else:
                logger.error(f"Missing embedding for chunk {chunk_id}")
        
        # Filter out chunks without embeddings
        chunks_with_embeddings = [
            chunk for chunk in chunk_data_list if chunk.embedding is not None
        ]
        
        if not chunks_with_embeddings:
            raise VectorStoreError("No chunks have embeddings, cannot store")
        
        # Convert document metadata
        doc_metadata = DocumentMetadata(
            id=document_metadata['id'],
            filename=document_metadata['filename'],
            user_id=document_metadata['user_id'],
            upload_date=document_metadata.get('upload_date', ''),
            file_size=document_metadata['file_size'],
            content_type=document_metadata['content_type'],
            processing_status=document_metadata.get('processing_status', 'completed')
        )
        
        # Store in vector database
        await self.vector_store.store_chunks(chunks_with_embeddings, doc_metadata)
    
    async def search_documents(
        self,
        query_text: str,
        user_id: Optional[str] = None,
        document_ids: Optional[List[UUID]] = None,
        environment_id: Optional[UUID] = None,
        limit: int = 5,
        similarity_threshold: float = 0.0
    ) -> List[SearchResult]:
        """
        Search for relevant document chunks.
        
        Args:
            query_text: Text to search for
            user_id: Optional user ID filter
            document_ids: Optional document ID filter
            environment_id: Optional environment ID filter
            limit: Maximum number of results
            similarity_threshold: Minimum similarity score
            
        Returns:
            List of search results
        """
        # Generate embedding for query
        query_embedding_result = await self.embedding_service.generate_embedding_for_text(
            query_text
        )
        
        # Create search query
        search_query = SearchQuery(
            query_text=query_text,
            user_id=user_id,
            document_ids=document_ids,
            environment_id=environment_id,
            limit=limit,
            similarity_threshold=similarity_threshold
        )
        
        # Perform search
        return await self.vector_store.search_similar(
            search_query,
            query_embedding_result.embedding
        )
    
    async def delete_document(self, document_id: UUID, user_id: Optional[str] = None) -> bool:
        """Delete a document and all its chunks."""
        return await self.vector_store.delete_document(document_id, user_id)
    
    async def get_document_chunks(
        self,
        document_id: UUID,
        user_id: Optional[str] = None
    ) -> List[ChunkData]:
        """Get all chunks for a document."""
        return await self.vector_store.get_document_chunks(document_id, user_id)
    
    async def get_document_metadata(
        self,
        document_id: UUID,
        user_id: Optional[str] = None
    ) -> Optional[DocumentMetadata]:
        """Get document metadata."""
        return await self.vector_store.get_document_metadata(document_id, user_id)
    
    async def get_storage_stats(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Get storage statistics."""
        return await self.vector_store.get_storage_stats(user_id)