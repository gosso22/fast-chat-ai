"""
RAG (Retrieval-Augmented Generation) service for semantic search and context retrieval.
Implements query processing, similarity search, and context ranking for RAG pipeline.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Tuple
from uuid import UUID
import time

from .vector_store import VectorStoreService, SearchResult
from .embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


@dataclass
class QueryContext:
    """Context information for a query."""

    query_text: str
    user_id: Optional[str] = None
    conversation_id: Optional[str] = None
    document_ids: Optional[List[UUID]] = None
    environment_id: Optional[UUID] = None
    max_results: int = 5
    similarity_threshold: float = 0.3
    include_metadata: bool = True

    def __post_init__(self):
        """Validate query context parameters."""
        if not self.query_text.strip():
            raise ValueError("Query text cannot be empty")
        if self.max_results <= 0:
            raise ValueError("Max results must be positive")
        if self.max_results > 20:
            raise ValueError("Max results cannot exceed 20")
        if not (0.0 <= self.similarity_threshold <= 1.0):
            raise ValueError("Similarity threshold must be between 0.0 and 1.0")


@dataclass
class RetrievedChunk:
    """A chunk retrieved from semantic search with enhanced metadata."""
    
    id: UUID
    content: str
    document_id: UUID
    document_filename: str
    chunk_index: int
    similarity_score: float
    rank: int
    token_count: int
    start_position: int
    end_position: int
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "id": str(self.id),
            "content": self.content,
            "document_id": str(self.document_id),
            "document_filename": self.document_filename,
            "chunk_index": self.chunk_index,
            "similarity_score": self.similarity_score,
            "rank": self.rank,
            "token_count": self.token_count,
            "start_position": self.start_position,
            "end_position": self.end_position
        }


@dataclass
class RetrievalResult:
    """Result of semantic search and context retrieval."""
    
    query: str
    chunks: List[RetrievedChunk]
    total_tokens: int
    processing_time: float
    embedding_time: float
    search_time: float
    ranking_time: float
    
    @property
    def chunk_count(self) -> int:
        """Number of retrieved chunks."""
        return len(self.chunks)
    
    @property
    def document_count(self) -> int:
        """Number of unique documents in results."""
        return len(set(chunk.document_id for chunk in self.chunks))
    
    @property
    def average_similarity(self) -> float:
        """Average similarity score of retrieved chunks."""
        if not self.chunks:
            return 0.0
        return sum(chunk.similarity_score for chunk in self.chunks) / len(self.chunks)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "query": self.query,
            "chunks": [chunk.to_dict() for chunk in self.chunks],
            "total_tokens": self.total_tokens,
            "processing_time": self.processing_time,
            "embedding_time": self.embedding_time,
            "search_time": self.search_time,
            "ranking_time": self.ranking_time,
            "chunk_count": self.chunk_count,
            "document_count": self.document_count,
            "average_similarity": self.average_similarity
        }


class RAGError(Exception):
    """Custom exception for RAG operations."""
    
    def __init__(
        self,
        message: str,
        operation: Optional[str] = None,
        query: Optional[str] = None,
        original_error: Optional[Exception] = None
    ):
        self.message = message
        self.operation = operation
        self.query = query
        self.original_error = original_error
        super().__init__(self.message)


class BaseQueryProcessor(ABC):
    """Abstract base class for query processing."""
    
    @abstractmethod
    async def process_query(self, query_context: QueryContext) -> str:
        """Process and potentially modify the query for better retrieval."""
        pass


class DefaultQueryProcessor(BaseQueryProcessor):
    """Default query processor with basic text cleaning."""
    
    async def process_query(self, query_context: QueryContext) -> str:
        """
        Process query with basic cleaning and normalization.
        
        Args:
            query_context: Query context with original text
            
        Returns:
            Processed query text
        """
        query = query_context.query_text.strip()
        
        # Basic cleaning
        query = " ".join(query.split())  # Normalize whitespace
        
        # Remove common stop phrases that might interfere with search
        stop_phrases = [
            "can you tell me",
            "i want to know",
            "please explain",
            "what is",
            "how do",
            "could you"
        ]
        
        query_lower = query.lower()
        for phrase in stop_phrases:
            if query_lower.startswith(phrase):
                query = query[len(phrase):].strip()
                break
        
        logger.debug(f"Processed query: '{query_context.query_text}' -> '{query}'")
        return query


class BaseContextRanker(ABC):
    """Abstract base class for context ranking."""
    
    @abstractmethod
    async def rank_chunks(
        self,
        chunks: List[RetrievedChunk],
        query: str,
        query_context: QueryContext
    ) -> List[RetrievedChunk]:
        """Rank retrieved chunks for relevance."""
        pass


class DefaultContextRanker(BaseContextRanker):
    """Default context ranker with similarity-based ranking and diversity."""
    
    def __init__(self, diversity_penalty: float = 0.1, max_chunks_per_doc: int = 3):
        self.diversity_penalty = diversity_penalty
        self.max_chunks_per_doc = max_chunks_per_doc
    
    async def rank_chunks(
        self,
        chunks: List[RetrievedChunk],
        query: str,
        query_context: QueryContext
    ) -> List[RetrievedChunk]:
        """
        Rank chunks with diversity penalty to avoid over-representation from single documents.
        
        Args:
            chunks: List of retrieved chunks
            query: Processed query text
            query_context: Original query context
            
        Returns:
            Ranked list of chunks
        """
        if not chunks:
            return chunks
        
        # Group chunks by document
        doc_chunks: Dict[UUID, List[RetrievedChunk]] = {}
        for chunk in chunks:
            if chunk.document_id not in doc_chunks:
                doc_chunks[chunk.document_id] = []
            doc_chunks[chunk.document_id].append(chunk)
        
        # Sort chunks within each document by similarity
        for doc_id in doc_chunks:
            doc_chunks[doc_id].sort(key=lambda x: x.similarity_score, reverse=True)
        
        # Apply diversity penalty and select top chunks from each document
        ranked_chunks = []
        document_counts = {}
        
        # Create a pool of all chunks sorted by similarity
        all_chunks = sorted(chunks, key=lambda x: x.similarity_score, reverse=True)
        
        for chunk in all_chunks:
            doc_count = document_counts.get(chunk.document_id, 0)
            
            # Apply diversity penalty
            adjusted_score = chunk.similarity_score
            if doc_count > 0:
                adjusted_score *= (1 - self.diversity_penalty * doc_count)
            
            # Check if we should include this chunk
            if doc_count < self.max_chunks_per_doc:
                # Update the chunk with adjusted score for ranking
                adjusted_chunk = RetrievedChunk(
                    id=chunk.id,
                    content=chunk.content,
                    document_id=chunk.document_id,
                    document_filename=chunk.document_filename,
                    chunk_index=chunk.chunk_index,
                    similarity_score=adjusted_score,
                    rank=len(ranked_chunks) + 1,
                    token_count=chunk.token_count,
                    start_position=chunk.start_position,
                    end_position=chunk.end_position
                )
                
                ranked_chunks.append(adjusted_chunk)
                document_counts[chunk.document_id] = doc_count + 1
        
        # Final sort by adjusted similarity score
        ranked_chunks.sort(key=lambda x: x.similarity_score, reverse=True)
        
        # Update ranks
        for i, chunk in enumerate(ranked_chunks):
            chunk.rank = i + 1
        
        logger.debug(
            f"Ranked {len(ranked_chunks)} chunks from {len(doc_chunks)} documents "
            f"(diversity penalty: {self.diversity_penalty})"
        )
        
        return ranked_chunks[:query_context.max_results]


class SemanticSearchService:
    """Service for semantic search and context retrieval."""
    
    def __init__(
        self,
        vector_store_service: Optional[VectorStoreService] = None,
        embedding_service: Optional[EmbeddingService] = None,
        query_processor: Optional[BaseQueryProcessor] = None,
        context_ranker: Optional[BaseContextRanker] = None
    ):
        self.vector_store_service = vector_store_service or VectorStoreService()
        self.embedding_service = embedding_service or EmbeddingService()
        self.query_processor = query_processor or DefaultQueryProcessor()
        self.context_ranker = context_ranker or DefaultContextRanker()
    
    async def retrieve_context(self, query_context: QueryContext) -> RetrievalResult:
        """
        Retrieve relevant context for a query using semantic search.
        
        Args:
            query_context: Query context with search parameters
            
        Returns:
            RetrievalResult with ranked chunks and metadata
            
        Raises:
            RAGError: If retrieval operation fails
        """
        start_time = time.time()
        
        try:
            # Step 1: Process the query
            embedding_start = time.time()
            processed_query = await self.query_processor.process_query(query_context)
            
            # Step 2: Generate query embedding
            query_embedding_result = await self.embedding_service.generate_embedding_for_text(
                processed_query,
                metadata={"original_query": query_context.query_text}
            )
            embedding_time = time.time() - embedding_start
            
            # Step 3: Perform similarity search
            search_start = time.time()
            search_results = await self.vector_store_service.search_documents(
                query_text=processed_query,
                user_id=query_context.user_id,
                document_ids=query_context.document_ids,
                environment_id=query_context.environment_id,
                limit=min(query_context.max_results * 2, 20),  # Get more results for ranking
                similarity_threshold=query_context.similarity_threshold
            )
            search_time = time.time() - search_start
            
            # Step 4: Convert search results to retrieved chunks
            retrieved_chunks = []
            total_tokens = 0
            
            for result in search_results:
                chunk = RetrievedChunk(
                    id=result.chunk.id,
                    content=result.chunk.content,
                    document_id=result.chunk.document_id,
                    document_filename=result.document.filename,
                    chunk_index=result.chunk.chunk_index,
                    similarity_score=result.similarity_score,
                    rank=result.rank,
                    token_count=result.chunk.token_count,
                    start_position=result.chunk.start_position,
                    end_position=result.chunk.end_position
                )
                retrieved_chunks.append(chunk)
                total_tokens += chunk.token_count
            
            # Step 5: Rank and filter chunks
            ranking_start = time.time()
            ranked_chunks = await self.context_ranker.rank_chunks(
                retrieved_chunks,
                processed_query,
                query_context
            )
            ranking_time = time.time() - ranking_start
            
            # Recalculate total tokens for final result set
            final_total_tokens = sum(chunk.token_count for chunk in ranked_chunks)
            
            processing_time = time.time() - start_time
            
            result = RetrievalResult(
                query=query_context.query_text,
                chunks=ranked_chunks,
                total_tokens=final_total_tokens,
                processing_time=processing_time,
                embedding_time=embedding_time,
                search_time=search_time,
                ranking_time=ranking_time
            )
            
            logger.info(
                f"Retrieved {len(ranked_chunks)} chunks for query '{query_context.query_text[:50]}...' "
                f"in {processing_time:.3f}s (avg similarity: {result.average_similarity:.3f})"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to retrieve context for query '{query_context.query_text}': {e}")
            raise RAGError(
                f"Failed to retrieve context: {str(e)}",
                "retrieve_context",
                query_context.query_text,
                e
            )
    
    async def search_documents(
        self,
        query: str,
        user_id: Optional[str] = None,
        document_ids: Optional[List[UUID]] = None,
        environment_id: Optional[UUID] = None,
        max_results: int = 5,
        similarity_threshold: float = 0.3
    ) -> RetrievalResult:
        """
        Convenience method for document search.
        
        Args:
            query: Search query text
            user_id: Optional user ID filter
            document_ids: Optional document ID filter
            environment_id: Optional environment ID filter
            max_results: Maximum number of results
            similarity_threshold: Minimum similarity score
            
        Returns:
            RetrievalResult with search results
        """
        query_context = QueryContext(
            query_text=query,
            user_id=user_id,
            document_ids=document_ids,
            environment_id=environment_id,
            max_results=max_results,
            similarity_threshold=similarity_threshold
        )
        
        return await self.retrieve_context(query_context)
    
    async def get_similar_chunks(
        self,
        chunk_id: UUID,
        user_id: Optional[str] = None,
        max_results: int = 5,
        similarity_threshold: float = 0.5
    ) -> List[RetrievedChunk]:
        """
        Find chunks similar to a given chunk.
        
        Args:
            chunk_id: ID of the reference chunk
            user_id: Optional user ID filter
            max_results: Maximum number of results
            similarity_threshold: Minimum similarity score
            
        Returns:
            List of similar chunks
            
        Raises:
            RAGError: If operation fails
        """
        try:
            # Get the reference chunk
            # Note: This would require a method to get chunk by ID from vector store
            # For now, we'll raise an error indicating this needs implementation
            raise NotImplementedError(
                "get_similar_chunks requires vector_store.get_chunk_by_id method"
            )
            
        except Exception as e:
            logger.error(f"Failed to find similar chunks for {chunk_id}: {e}")
            raise RAGError(
                f"Failed to find similar chunks: {str(e)}",
                "get_similar_chunks",
                str(chunk_id),
                e
            )
    
    async def validate_search_capability(self) -> bool:
        """
        Validate that the search service is properly configured and functional.
        
        Returns:
            True if search is working, False otherwise
        """
        try:
            # Test with a simple query
            test_context = QueryContext(
                query_text="test query for validation",
                max_results=1,
                similarity_threshold=0.0
            )
            
            # This should not fail even if no documents are indexed
            result = await self.retrieve_context(test_context)
            
            logger.info("Semantic search validation successful")
            return True
            
        except Exception as e:
            logger.error(f"Semantic search validation failed: {e}")
            return False
    
    def get_service_info(self) -> Dict[str, Any]:
        """Get information about the search service configuration."""
        return {
            "vector_store": type(self.vector_store_service).__name__,
            "embedding_service": type(self.embedding_service).__name__,
            "query_processor": type(self.query_processor).__name__,
            "context_ranker": type(self.context_ranker).__name__,
            "embedding_model": self.embedding_service.get_model_info()
        }