"""
Tests for RAG service semantic search and context retrieval functionality.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4, UUID
from typing import List

from app.services.rag_service import (
    SemanticSearchService,
    QueryContext,
    RetrievedChunk,
    RetrievalResult,
    DefaultQueryProcessor,
    DefaultContextRanker,
    RAGError
)
from app.services.vector_store import SearchResult, ChunkData, DocumentMetadata
from app.services.embedding_service import EmbeddingResult


class TestQueryContext:
    """Test QueryContext validation and functionality."""
    
    def test_valid_query_context(self):
        """Test creating a valid query context."""
        context = QueryContext(
            query_text="What is machine learning?",
            user_id="user123",
            max_results=5,
            similarity_threshold=0.3
        )
        
        assert context.query_text == "What is machine learning?"
        assert context.user_id == "user123"
        assert context.max_results == 5
        assert context.similarity_threshold == 0.3
    
    def test_empty_query_text_raises_error(self):
        """Test that empty query text raises ValueError."""
        with pytest.raises(ValueError, match="Query text cannot be empty"):
            QueryContext(query_text="")
    
    def test_whitespace_only_query_text_raises_error(self):
        """Test that whitespace-only query text raises ValueError."""
        with pytest.raises(ValueError, match="Query text cannot be empty"):
            QueryContext(query_text="   ")
    
    def test_invalid_max_results_raises_error(self):
        """Test that invalid max_results raises ValueError."""
        with pytest.raises(ValueError, match="Max results must be positive"):
            QueryContext(query_text="test", max_results=0)
        
        with pytest.raises(ValueError, match="Max results cannot exceed 20"):
            QueryContext(query_text="test", max_results=25)
    
    def test_invalid_similarity_threshold_raises_error(self):
        """Test that invalid similarity threshold raises ValueError."""
        with pytest.raises(ValueError, match="Similarity threshold must be between 0.0 and 1.0"):
            QueryContext(query_text="test", similarity_threshold=-0.1)
        
        with pytest.raises(ValueError, match="Similarity threshold must be between 0.0 and 1.0"):
            QueryContext(query_text="test", similarity_threshold=1.1)


class TestDefaultQueryProcessor:
    """Test DefaultQueryProcessor functionality."""
    
    @pytest.fixture
    def processor(self):
        return DefaultQueryProcessor()
    
    @pytest.mark.asyncio
    async def test_basic_query_processing(self, processor):
        """Test basic query cleaning and normalization."""
        context = QueryContext(query_text="  What   is   machine learning?  ")
        result = await processor.process_query(context)
        
        assert result == "machine learning?"
    
    @pytest.mark.asyncio
    async def test_stop_phrase_removal(self, processor):
        """Test removal of common stop phrases."""
        test_cases = [
            ("can you tell me about Python?", "about Python?"),
            ("i want to know about databases", "about databases"),
            ("please explain neural networks", "neural networks"),
            ("what is artificial intelligence", "artificial intelligence"),
            ("how do I implement this", "I implement this"),
            ("could you help with this", "help with this")
        ]
        
        for input_query, expected in test_cases:
            context = QueryContext(query_text=input_query)
            result = await processor.process_query(context)
            assert result == expected
    
    @pytest.mark.asyncio
    async def test_no_stop_phrase_processing(self, processor):
        """Test that queries without stop phrases are unchanged."""
        context = QueryContext(query_text="machine learning algorithms")
        result = await processor.process_query(context)
        
        assert result == "machine learning algorithms"


class TestDefaultContextRanker:
    """Test DefaultContextRanker functionality."""
    
    @pytest.fixture
    def ranker(self):
        return DefaultContextRanker(diversity_penalty=0.1, max_chunks_per_doc=3)
    
    def create_test_chunk(self, doc_id: UUID, similarity: float, chunk_index: int = 0) -> RetrievedChunk:
        """Helper to create test chunks."""
        return RetrievedChunk(
            id=uuid4(),
            content=f"Test content {chunk_index}",
            document_id=doc_id,
            document_filename=f"doc_{doc_id}.txt",
            chunk_index=chunk_index,
            similarity_score=similarity,
            rank=1,
            token_count=100,
            start_position=0,
            end_position=100
        )
    
    @pytest.mark.asyncio
    async def test_empty_chunks_list(self, ranker):
        """Test ranking empty chunks list."""
        context = QueryContext(query_text="test")
        result = await ranker.rank_chunks([], "test", context)
        
        assert result == []
    
    @pytest.mark.asyncio
    async def test_single_chunk_ranking(self, ranker):
        """Test ranking single chunk."""
        doc_id = uuid4()
        chunk = self.create_test_chunk(doc_id, 0.8)
        context = QueryContext(query_text="test")
        
        result = await ranker.rank_chunks([chunk], "test", context)
        
        assert len(result) == 1
        assert result[0].rank == 1
        assert result[0].similarity_score == 0.8
    
    @pytest.mark.asyncio
    async def test_diversity_penalty_application(self, ranker):
        """Test that diversity penalty is applied to multiple chunks from same document."""
        doc_id = uuid4()
        chunks = [
            self.create_test_chunk(doc_id, 0.9, 0),
            self.create_test_chunk(doc_id, 0.8, 1),
            self.create_test_chunk(doc_id, 0.7, 2)
        ]
        context = QueryContext(query_text="test", max_results=5)
        
        result = await ranker.rank_chunks(chunks, "test", context)
        
        # First chunk should have original score
        assert result[0].similarity_score == 0.9
        
        # Second chunk should have penalty applied (0.8 * 0.9 = 0.72)
        assert result[1].similarity_score == pytest.approx(0.72, rel=1e-2)
        
        # Third chunk should have more penalty (0.7 * 0.8 = 0.56)
        assert result[2].similarity_score == pytest.approx(0.56, rel=1e-2)
    
    @pytest.mark.asyncio
    async def test_max_chunks_per_document_limit(self, ranker):
        """Test that max chunks per document limit is enforced."""
        doc_id = uuid4()
        chunks = [
            self.create_test_chunk(doc_id, 0.9, i) for i in range(5)
        ]
        context = QueryContext(query_text="test", max_results=10)
        
        result = await ranker.rank_chunks(chunks, "test", context)
        
        # Should only return 3 chunks (max_chunks_per_doc)
        assert len(result) == 3
        assert all(chunk.document_id == doc_id for chunk in result)
    
    @pytest.mark.asyncio
    async def test_multiple_documents_ranking(self, ranker):
        """Test ranking chunks from multiple documents."""
        doc1_id = uuid4()
        doc2_id = uuid4()
        
        chunks = [
            self.create_test_chunk(doc1_id, 0.9, 0),
            self.create_test_chunk(doc2_id, 0.85, 0),
            self.create_test_chunk(doc1_id, 0.8, 1),
            self.create_test_chunk(doc2_id, 0.75, 1)
        ]
        context = QueryContext(query_text="test", max_results=4)
        
        result = await ranker.rank_chunks(chunks, "test", context)
        
        assert len(result) == 4
        # Should be ordered by adjusted similarity scores
        assert result[0].document_id == doc1_id  # 0.9
        assert result[1].document_id == doc2_id  # 0.85
        # Next should be doc1 chunk with penalty or doc2 chunk without penalty
        assert result[0].similarity_score > result[1].similarity_score


class TestSemanticSearchService:
    """Test SemanticSearchService functionality."""
    
    @pytest.fixture
    def mock_vector_store(self):
        return AsyncMock()
    
    @pytest.fixture
    def mock_embedding_service(self):
        return AsyncMock()
    
    @pytest.fixture
    def search_service(self, mock_vector_store, mock_embedding_service):
        return SemanticSearchService(
            vector_store_service=mock_vector_store,
            embedding_service=mock_embedding_service
        )
    
    def create_mock_search_result(self, doc_id: UUID, similarity: float) -> SearchResult:
        """Helper to create mock search results."""
        chunk_data = ChunkData(
            id=uuid4(),
            document_id=doc_id,
            chunk_index=0,
            content="Test content",
            start_position=0,
            end_position=100,
            token_count=25
        )
        
        doc_metadata = DocumentMetadata(
            id=doc_id,
            filename="test.txt",
            user_id="user123",
            upload_date="2024-01-01T00:00:00",
            file_size=1000,
            content_type="text/plain",
            processing_status="completed"
        )
        
        return SearchResult(
            chunk=chunk_data,
            document=doc_metadata,
            similarity_score=similarity,
            rank=1
        )
    
    @pytest.mark.asyncio
    async def test_retrieve_context_success(self, search_service, mock_vector_store, mock_embedding_service):
        """Test successful context retrieval."""
        # Setup mocks
        mock_embedding_service.generate_embedding_for_text.return_value = EmbeddingResult(
            id="test",
            embedding=[0.1] * 1536,
            token_count=5,
            model="text-embedding-3-small"
        )
        
        doc_id = uuid4()
        mock_search_results = [
            self.create_mock_search_result(doc_id, 0.8),
            self.create_mock_search_result(doc_id, 0.7)
        ]
        mock_vector_store.search_documents.return_value = mock_search_results
        
        # Execute
        context = QueryContext(query_text="What is machine learning?", max_results=5)
        result = await search_service.retrieve_context(context)
        
        # Verify
        assert isinstance(result, RetrievalResult)
        assert result.query == "What is machine learning?"
        assert len(result.chunks) == 2
        assert result.chunk_count == 2
        assert result.document_count == 1
        assert result.total_tokens == 50  # 2 chunks * 25 tokens each
        assert result.processing_time > 0
        
        # Verify service calls
        mock_embedding_service.generate_embedding_for_text.assert_called_once()
        mock_vector_store.search_documents.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_retrieve_context_no_results(self, search_service, mock_vector_store, mock_embedding_service):
        """Test context retrieval with no search results."""
        # Setup mocks
        mock_embedding_service.generate_embedding_for_text.return_value = EmbeddingResult(
            id="test",
            embedding=[0.1] * 1536,
            token_count=5,
            model="text-embedding-3-small"
        )
        mock_vector_store.search_documents.return_value = []
        
        # Execute
        context = QueryContext(query_text="nonexistent query", max_results=5)
        result = await search_service.retrieve_context(context)
        
        # Verify
        assert result.chunk_count == 0
        assert result.total_tokens == 0
        assert result.average_similarity == 0.0
    
    @pytest.mark.asyncio
    async def test_retrieve_context_embedding_failure(self, search_service, mock_vector_store, mock_embedding_service):
        """Test context retrieval when embedding generation fails."""
        # Setup mocks
        mock_embedding_service.generate_embedding_for_text.side_effect = Exception("Embedding failed")
        
        # Execute and verify exception
        context = QueryContext(query_text="test query", max_results=5)
        
        with pytest.raises(RAGError, match="Failed to retrieve context"):
            await search_service.retrieve_context(context)
    
    @pytest.mark.asyncio
    async def test_retrieve_context_search_failure(self, search_service, mock_vector_store, mock_embedding_service):
        """Test context retrieval when vector search fails."""
        # Setup mocks
        mock_embedding_service.generate_embedding_for_text.return_value = EmbeddingResult(
            id="test",
            embedding=[0.1] * 1536,
            token_count=5,
            model="text-embedding-3-small"
        )
        mock_vector_store.search_documents.side_effect = Exception("Search failed")
        
        # Execute and verify exception
        context = QueryContext(query_text="test query", max_results=5)
        
        with pytest.raises(RAGError, match="Failed to retrieve context"):
            await search_service.retrieve_context(context)
    
    @pytest.mark.asyncio
    async def test_search_documents_convenience_method(self, search_service, mock_vector_store, mock_embedding_service):
        """Test the convenience search_documents method."""
        # Setup mocks
        mock_embedding_service.generate_embedding_for_text.return_value = EmbeddingResult(
            id="test",
            embedding=[0.1] * 1536,
            token_count=5,
            model="text-embedding-3-small"
        )
        mock_vector_store.search_documents.return_value = []
        
        # Execute
        result = await search_service.search_documents(
            query="test query",
            user_id="user123",
            max_results=3,
            similarity_threshold=0.5
        )
        
        # Verify
        assert isinstance(result, RetrievalResult)
        assert result.query == "test query"
        
        # Verify vector store was called with correct parameters
        mock_vector_store.search_documents.assert_called_once_with(
            query_text="test query",
            user_id="user123",
            document_ids=None,
            limit=6,  # max_results * 2 for ranking
            similarity_threshold=0.5
        )
    
    @pytest.mark.asyncio
    async def test_get_similar_chunks_not_implemented(self, search_service):
        """Test that get_similar_chunks raises RAGError."""
        with pytest.raises(RAGError, match="Failed to find similar chunks"):
            await search_service.get_similar_chunks(uuid4())
    
    @pytest.mark.asyncio
    async def test_validate_search_capability_success(self, search_service, mock_vector_store, mock_embedding_service):
        """Test successful search capability validation."""
        # Setup mocks
        mock_embedding_service.generate_embedding_for_text.return_value = EmbeddingResult(
            id="test",
            embedding=[0.1] * 1536,
            token_count=5,
            model="text-embedding-3-small"
        )
        mock_vector_store.search_documents.return_value = []
        
        # Execute
        result = await search_service.validate_search_capability()
        
        # Verify
        assert result is True
    
    @pytest.mark.asyncio
    async def test_validate_search_capability_failure(self, search_service, mock_vector_store, mock_embedding_service):
        """Test search capability validation failure."""
        # Setup mocks
        mock_embedding_service.generate_embedding_for_text.side_effect = Exception("Validation failed")
        
        # Execute
        result = await search_service.validate_search_capability()
        
        # Verify
        assert result is False
    
    def test_get_service_info(self, search_service, mock_embedding_service):
        """Test getting service information."""
        # Setup mock
        mock_embedding_service.get_model_info.return_value = {
            "model": "text-embedding-3-small",
            "dimension": 1536
        }
        
        # Execute
        info = search_service.get_service_info()
        
        # Verify
        assert "vector_store" in info
        assert "embedding_service" in info
        assert "query_processor" in info
        assert "context_ranker" in info
        assert "embedding_model" in info


class TestRetrievalResult:
    """Test RetrievalResult functionality."""
    
    def test_retrieval_result_properties(self):
        """Test RetrievalResult computed properties."""
        doc1_id = uuid4()
        doc2_id = uuid4()
        
        chunks = [
            RetrievedChunk(
                id=uuid4(),
                content="content1",
                document_id=doc1_id,
                document_filename="doc1.txt",
                chunk_index=0,
                similarity_score=0.8,
                rank=1,
                token_count=100,
                start_position=0,
                end_position=100
            ),
            RetrievedChunk(
                id=uuid4(),
                content="content2",
                document_id=doc2_id,
                document_filename="doc2.txt",
                chunk_index=0,
                similarity_score=0.6,
                rank=2,
                token_count=150,
                start_position=0,
                end_position=150
            )
        ]
        
        result = RetrievalResult(
            query="test query",
            chunks=chunks,
            total_tokens=250,
            processing_time=1.5,
            embedding_time=0.5,
            search_time=0.8,
            ranking_time=0.2
        )
        
        assert result.chunk_count == 2
        assert result.document_count == 2
        assert result.average_similarity == 0.7
    
    def test_retrieval_result_empty_chunks(self):
        """Test RetrievalResult with empty chunks."""
        result = RetrievalResult(
            query="test query",
            chunks=[],
            total_tokens=0,
            processing_time=0.1,
            embedding_time=0.05,
            search_time=0.03,
            ranking_time=0.02
        )
        
        assert result.chunk_count == 0
        assert result.document_count == 0
        assert result.average_similarity == 0.0
    
    def test_retrieval_result_to_dict(self):
        """Test RetrievalResult to_dict conversion."""
        chunk = RetrievedChunk(
            id=uuid4(),
            content="test content",
            document_id=uuid4(),
            document_filename="test.txt",
            chunk_index=0,
            similarity_score=0.8,
            rank=1,
            token_count=100,
            start_position=0,
            end_position=100
        )
        
        result = RetrievalResult(
            query="test query",
            chunks=[chunk],
            total_tokens=100,
            processing_time=1.0,
            embedding_time=0.3,
            search_time=0.5,
            ranking_time=0.2
        )
        
        result_dict = result.to_dict()
        
        assert result_dict["query"] == "test query"
        assert len(result_dict["chunks"]) == 1
        assert result_dict["total_tokens"] == 100
        assert result_dict["chunk_count"] == 1
        assert result_dict["document_count"] == 1
        assert result_dict["average_similarity"] == 0.8