"""
Integration tests for RAG pipeline functionality.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4, UUID
from typing import List

from app.services.rag_pipeline import (
    RAGPipeline,
    RAGRequest,
    RAGResponse,
    SourceCitation,
    DefaultPromptTemplate,
    RAGPipelineError
)
from app.services.rag_service import RetrievalResult, RetrievedChunk
from app.services.llm_providers.base import LLMResponse


class TestRAGRequest:
    """Test RAGRequest validation and functionality."""
    
    def test_valid_rag_request(self):
        """Test creating a valid RAG request."""
        request = RAGRequest(
            query="What is machine learning?",
            user_id="user123",
            max_context_chunks=5,
            similarity_threshold=0.3,
            temperature=0.7
        )
        
        assert request.query == "What is machine learning?"
        assert request.user_id == "user123"
        assert request.max_context_chunks == 5
        assert request.similarity_threshold == 0.3
        assert request.temperature == 0.7
    
    def test_empty_query_raises_error(self):
        """Test that empty query raises ValueError."""
        with pytest.raises(ValueError, match="Query cannot be empty"):
            RAGRequest(query="")
    
    def test_whitespace_only_query_raises_error(self):
        """Test that whitespace-only query raises ValueError."""
        with pytest.raises(ValueError, match="Query cannot be empty"):
            RAGRequest(query="   ")
    
    def test_invalid_max_context_chunks_raises_error(self):
        """Test that invalid max_context_chunks raises ValueError."""
        with pytest.raises(ValueError, match="Max context chunks must be positive"):
            RAGRequest(query="test", max_context_chunks=0)
        
        with pytest.raises(ValueError, match="Max context chunks cannot exceed 20"):
            RAGRequest(query="test", max_context_chunks=25)
    
    def test_invalid_similarity_threshold_raises_error(self):
        """Test that invalid similarity threshold raises ValueError."""
        with pytest.raises(ValueError, match="Similarity threshold must be between 0.0 and 1.0"):
            RAGRequest(query="test", similarity_threshold=-0.1)
        
        with pytest.raises(ValueError, match="Similarity threshold must be between 0.0 and 1.0"):
            RAGRequest(query="test", similarity_threshold=1.1)
    
    def test_invalid_temperature_raises_error(self):
        """Test that invalid temperature raises ValueError."""
        with pytest.raises(ValueError, match="Temperature must be between 0.0 and 2.0"):
            RAGRequest(query="test", temperature=-0.1)
        
        with pytest.raises(ValueError, match="Temperature must be between 0.0 and 2.0"):
            RAGRequest(query="test", temperature=2.1)


class TestDefaultPromptTemplate:
    """Test DefaultPromptTemplate functionality."""
    
    @pytest.fixture
    def template(self):
        return DefaultPromptTemplate()
    
    def create_test_chunk(self, doc_id: UUID, filename: str, content: str, rank: int = 1) -> RetrievedChunk:
        """Helper to create test chunks."""
        return RetrievedChunk(
            id=uuid4(),
            content=content,
            document_id=doc_id,
            document_filename=filename,
            chunk_index=0,
            similarity_score=0.8,
            rank=rank,
            token_count=len(content.split()),
            start_position=0,
            end_position=len(content)
        )
    
    def test_format_prompt_with_context(self, template):
        """Test prompt formatting with context chunks."""
        doc_id = uuid4()
        chunks = [
            self.create_test_chunk(doc_id, "test.txt", "Machine learning is a subset of AI.", 1),
            self.create_test_chunk(doc_id, "guide.txt", "Neural networks are used in ML.", 2)
        ]
        
        prompt = template.format_prompt("What is machine learning?", chunks)
        
        assert "What is machine learning?" in prompt
        assert "Machine learning is a subset of AI." in prompt
        assert "Neural networks are used in ML." in prompt
        assert "Source 1 (from test.txt" in prompt
        assert "Source 2 (from guide.txt" in prompt
    
    def test_format_prompt_without_context(self, template):
        """Test prompt formatting without context chunks."""
        prompt = template.format_prompt("What is machine learning?", [])
        
        assert "What is machine learning?" in prompt
        assert "No relevant context found" in prompt
    
    def test_format_prompt_with_custom_system_prompt(self, template):
        """Test prompt formatting with custom system prompt."""
        doc_id = uuid4()
        chunks = [self.create_test_chunk(doc_id, "test.txt", "Test content", 1)]
        custom_system = "You are a specialized AI assistant."
        
        prompt = template.format_prompt("Test query", chunks, custom_system)
        
        assert custom_system in prompt
        assert "Test query" in prompt
    
    def test_format_prompt_truncates_long_content(self, template):
        """Test that long content is truncated in prompt."""
        doc_id = uuid4()
        long_content = "This is a very long piece of content. " * 50  # > 500 chars
        chunks = [self.create_test_chunk(doc_id, "test.txt", long_content, 1)]
        
        prompt = template.format_prompt("Test query", chunks)
        
        assert "..." in prompt  # Should be truncated
        assert len(prompt) < len(long_content) + 1000  # Should be significantly shorter
    
    def test_extract_citations_with_explicit_references(self, template):
        """Test citation extraction with explicit source references."""
        doc_id = uuid4()
        chunks = [
            self.create_test_chunk(doc_id, "ml_guide.txt", "Machine learning is powerful", 1),
            self.create_test_chunk(uuid4(), "ai_book.txt", "AI has many applications", 2)
        ]
        
        response = "According to Source 1, machine learning is very useful. As mentioned in ai_book.txt, AI is versatile."
        
        citations = template.extract_citations(response, chunks)
        
        assert len(citations) == 2
        assert any(c.document_filename == "ml_guide.txt" for c in citations)
        assert any(c.document_filename == "ai_book.txt" for c in citations)
    
    def test_extract_citations_with_content_overlap(self, template):
        """Test citation extraction based on content overlap."""
        doc_id = uuid4()
        chunks = [
            self.create_test_chunk(doc_id, "test.txt", "Machine learning algorithms are powerful tools", 1)
        ]
        
        response = "Machine learning algorithms can solve complex problems effectively."
        
        citations = template.extract_citations(response, chunks)
        
        assert len(citations) >= 1
        assert citations[0].document_filename == "test.txt"
    
    def test_extract_citations_no_references(self, template):
        """Test citation extraction when no references are found."""
        doc_id = uuid4()
        chunks = [
            self.create_test_chunk(doc_id, "test.txt", "Completely unrelated content", 1)
        ]
        
        response = "This response has nothing to do with the context."
        
        citations = template.extract_citations(response, chunks)
        
        assert len(citations) == 0
    
    def test_citation_excerpt_truncation(self, template):
        """Test that citation excerpts are properly truncated."""
        template.max_excerpt_length = 50
        doc_id = uuid4()
        long_content = "This is a very long piece of content that should be truncated. " * 10
        chunks = [self.create_test_chunk(doc_id, "test.txt", long_content, 1)]
        
        response = "According to Source 1, this information is relevant."
        
        citations = template.extract_citations(response, chunks)
        
        assert len(citations) == 1
        assert len(citations[0].excerpt) <= 53  # 50 + "..."
        assert citations[0].excerpt.endswith("...")


class TestRAGPipeline:
    """Test RAGPipeline functionality."""
    
    @pytest.fixture
    def mock_search_service(self):
        return AsyncMock()
    
    @pytest.fixture
    def mock_llm_manager(self):
        return AsyncMock()
    
    @pytest.fixture
    def rag_pipeline(self, mock_search_service, mock_llm_manager):
        return RAGPipeline(
            search_service=mock_search_service,
            llm_manager=mock_llm_manager
        )
    
    def create_mock_retrieval_result(self, chunks: List[RetrievedChunk]) -> RetrievalResult:
        """Helper to create mock retrieval results."""
        return RetrievalResult(
            query="test query",
            chunks=chunks,
            total_tokens=sum(chunk.token_count for chunk in chunks),
            processing_time=0.5,
            embedding_time=0.1,
            search_time=0.3,
            ranking_time=0.1
        )
    
    def create_test_chunk(self, doc_id: UUID, filename: str, content: str) -> RetrievedChunk:
        """Helper to create test chunks."""
        return RetrievedChunk(
            id=uuid4(),
            content=content,
            document_id=doc_id,
            document_filename=filename,
            chunk_index=0,
            similarity_score=0.8,
            rank=1,
            token_count=len(content.split()),
            start_position=0,
            end_position=len(content)
        )
    
    @pytest.mark.asyncio
    async def test_generate_response_success(self, rag_pipeline, mock_search_service, mock_llm_manager):
        """Test successful RAG response generation."""
        # Setup mocks
        doc_id = uuid4()
        chunks = [
            self.create_test_chunk(doc_id, "test.txt", "Machine learning is a subset of AI"),
            self.create_test_chunk(doc_id, "guide.txt", "Neural networks are powerful")
        ]
        
        mock_retrieval_result = self.create_mock_retrieval_result(chunks)
        mock_search_service.retrieve_context.return_value = mock_retrieval_result
        
        mock_llm_response = LLMResponse(
            content="Machine learning is indeed a subset of artificial intelligence, as mentioned in the sources.",
            input_tokens=20,
            output_tokens=25,
            total_tokens=45,
            cost=0.001,
            provider="openai",
            model="gpt-3.5-turbo"
        )
        mock_llm_manager.generate_response.return_value = mock_llm_response
        
        # Execute
        request = RAGRequest(
            query="What is machine learning?",
            user_id="user123",
            max_context_chunks=5
        )
        
        response = await rag_pipeline.generate_response(request)
        
        # Verify
        assert isinstance(response, RAGResponse)
        assert response.query == "What is machine learning?"
        assert response.response == mock_llm_response.content
        assert response.source_count >= 0  # Citations may or may not be found
        assert response.total_tokens > 0
        assert response.processing_time > 0
        
        # Verify service calls
        mock_search_service.retrieve_context.assert_called_once()
        mock_llm_manager.generate_response.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_generate_response_no_context(self, rag_pipeline, mock_search_service, mock_llm_manager):
        """Test RAG response generation with no retrieved context."""
        # Setup mocks
        mock_retrieval_result = self.create_mock_retrieval_result([])
        mock_search_service.retrieve_context.return_value = mock_retrieval_result
        
        mock_llm_response = LLMResponse(
            content="I don't have enough information to answer that question.",
            input_tokens=10,
            output_tokens=15,
            total_tokens=25,
            cost=0.0005,
            provider="openai",
            model="gpt-3.5-turbo"
        )
        mock_llm_manager.generate_response.return_value = mock_llm_response
        
        # Execute
        request = RAGRequest(query="What is quantum computing?", user_id="user123")
        response = await rag_pipeline.generate_response(request)
        
        # Verify
        assert response.source_count == 0
        assert response.retrieval_result.chunk_count == 0
        prompt_content = mock_llm_manager.generate_response.call_args[0][0].messages[0]["content"]
        assert "I don't have any relevant documents" in prompt_content
    
    @pytest.mark.asyncio
    async def test_generate_response_retrieval_failure(self, rag_pipeline, mock_search_service, mock_llm_manager):
        """Test RAG response generation when retrieval fails."""
        # Setup mocks
        mock_search_service.retrieve_context.side_effect = Exception("Retrieval failed")
        
        # Execute and verify exception
        request = RAGRequest(query="Test query", user_id="user123")
        
        with pytest.raises(RAGPipelineError, match="RAG pipeline failed"):
            await rag_pipeline.generate_response(request)
    
    @pytest.mark.asyncio
    async def test_generate_response_llm_failure(self, rag_pipeline, mock_search_service, mock_llm_manager):
        """Test RAG response generation when LLM generation fails uses fallback."""
        # Setup mocks
        mock_retrieval_result = self.create_mock_retrieval_result([])
        mock_search_service.retrieve_context.return_value = mock_retrieval_result
        mock_llm_manager.generate_response.side_effect = Exception("LLM generation failed")

        # Execute - pipeline catches LLM errors and returns a fallback response
        request = RAGRequest(query="Test query", user_id="user123")
        response = await rag_pipeline.generate_response(request)

        # Verify fallback response is returned
        assert isinstance(response, RAGResponse)
        assert "technical difficulties" in response.response
        assert response.llm_response.provider == "fallback"
    
    @pytest.mark.asyncio
    async def test_generate_simple_response(self, rag_pipeline, mock_search_service, mock_llm_manager):
        """Test the convenience generate_simple_response method."""
        # Setup mocks
        mock_retrieval_result = self.create_mock_retrieval_result([])
        mock_search_service.retrieve_context.return_value = mock_retrieval_result
        
        mock_llm_response = LLMResponse(
            content="Simple response",
            input_tokens=5,
            output_tokens=10,
            total_tokens=15,
            cost=0.0003,
            provider="openai",
            model="gpt-3.5-turbo"
        )
        mock_llm_manager.generate_response.return_value = mock_llm_response
        
        # Execute
        response = await rag_pipeline.generate_simple_response(
            query="Simple query",
            user_id="user123",
            max_chunks=3,
            similarity_threshold=0.5
        )
        
        # Verify
        assert isinstance(response, RAGResponse)
        assert response.query == "Simple query"
        
        # Verify that retrieve_context was called with correct parameters
        # The first call uses the original parameters; recovery may follow with lower threshold
        first_call_args = mock_search_service.retrieve_context.call_args_list[0][0][0]
        assert first_call_args.query_text == "Simple query"
        assert first_call_args.user_id == "user123"
        assert first_call_args.max_results == 3
        assert first_call_args.similarity_threshold == 0.5
    
    @pytest.mark.asyncio
    async def test_validate_pipeline_success(self, rag_pipeline, mock_search_service, mock_llm_manager):
        """Test successful pipeline validation."""
        # Setup mocks
        mock_search_service.validate_search_capability.return_value = True
        mock_llm_manager.get_provider_status.return_value = {
            "openai": {"enabled": True, "healthy": True}
        }
        
        # Execute
        result = await rag_pipeline.validate_pipeline()
        
        # Verify
        assert result is True
        mock_search_service.validate_search_capability.assert_called_once()
        mock_llm_manager.get_provider_status.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_validate_pipeline_search_failure(self, rag_pipeline, mock_search_service, mock_llm_manager):
        """Test pipeline validation when search service fails."""
        # Setup mocks
        mock_search_service.validate_search_capability.return_value = False
        
        # Execute
        result = await rag_pipeline.validate_pipeline()
        
        # Verify
        assert result is False
    
    @pytest.mark.asyncio
    async def test_validate_pipeline_no_healthy_providers(self, rag_pipeline, mock_search_service, mock_llm_manager):
        """Test pipeline validation when no healthy providers are available."""
        # Setup mocks
        mock_search_service.validate_search_capability.return_value = True
        mock_llm_manager.get_provider_status.return_value = {
            "openai": {"enabled": False, "healthy": False}
        }
        
        # Execute
        result = await rag_pipeline.validate_pipeline()
        
        # Verify
        assert result is False
    
    def test_pipeline_requires_llm_manager(self, mock_search_service):
        """Test that RAGPipeline requires an LLM manager."""
        with pytest.raises(ValueError, match="LLM manager is required"):
            RAGPipeline(search_service=mock_search_service, llm_manager=None)
    
    def test_get_pipeline_info(self, rag_pipeline, mock_search_service, mock_llm_manager):
        """Test getting pipeline information."""
        # Setup mocks
        mock_search_service.get_service_info.return_value = {"search": "info"}
        mock_llm_manager.get_provider_status.return_value = {"openai": {"status": "healthy"}}
        
        # Execute
        info = rag_pipeline.get_pipeline_info()
        
        # Verify
        assert "search_service" in info
        assert "prompt_template" in info
        assert "llm_providers" in info
        assert "pipeline_stages" in info
        assert len(info["pipeline_stages"]) == 4
    
    @pytest.mark.asyncio
    async def test_get_pipeline_stats(self, rag_pipeline, mock_llm_manager):
        """Test getting pipeline statistics."""
        # Setup mocks
        mock_llm_manager.get_daily_cost.return_value = 1.50
        mock_llm_manager.get_monthly_cost.return_value = 45.00
        
        # Execute
        stats = await rag_pipeline.get_pipeline_stats()
        
        # Verify
        assert stats["search_service"] == "available"
        assert stats["llm_manager"] == "available"
        assert stats["daily_cost"] == 1.50
        assert stats["monthly_cost"] == 45.00
    
    @pytest.mark.asyncio
    async def test_get_pipeline_stats_cost_failure(self, rag_pipeline, mock_llm_manager):
        """Test getting pipeline statistics when cost retrieval fails."""
        # Setup mocks
        mock_llm_manager.get_daily_cost.side_effect = Exception("Cost retrieval failed")
        mock_llm_manager.get_monthly_cost.side_effect = Exception("Cost retrieval failed")
        
        # Execute
        stats = await rag_pipeline.get_pipeline_stats()
        
        # Verify basic stats are still returned
        assert stats["search_service"] == "available"
        assert stats["llm_manager"] == "available"
        assert "daily_cost" not in stats
        assert "monthly_cost" not in stats


class TestRAGResponse:
    """Test RAGResponse functionality."""
    
    def test_rag_response_properties(self):
        """Test RAGResponse computed properties."""
        # Create mock objects
        retrieval_result = RetrievalResult(
            query="test",
            chunks=[],
            total_tokens=100,
            processing_time=1.0,
            embedding_time=0.2,
            search_time=0.6,
            ranking_time=0.2
        )
        
        llm_response = LLMResponse(
            content="Test response",
            input_tokens=30,
            output_tokens=50,
            total_tokens=80,
            cost=0.002,
            provider="openai",
            model="gpt-3.5-turbo"
        )
        
        sources = [
            SourceCitation(
                document_id=uuid4(),
                document_filename="test.txt",
                chunk_index=0,
                similarity_score=0.8,
                excerpt="Test excerpt",
                start_position=0,
                end_position=100
            )
        ]
        
        response = RAGResponse(
            query="test query",
            response="test response",
            sources=sources,
            retrieval_result=retrieval_result,
            llm_response=llm_response,
            processing_time=2.0,
            context_tokens=200,
            response_tokens=50,
            total_cost=0.002
        )
        
        assert response.source_count == 1
        assert response.total_tokens == 250
    
    def test_rag_response_to_dict(self):
        """Test RAGResponse to_dict conversion."""
        # Create minimal mock objects
        retrieval_result = RetrievalResult(
            query="test",
            chunks=[],
            total_tokens=0,
            processing_time=1.0,
            embedding_time=0.2,
            search_time=0.6,
            ranking_time=0.2
        )
        
        llm_response = LLMResponse(
            content="Test response",
            input_tokens=30,
            output_tokens=50,
            total_tokens=80,
            cost=0.002,
            provider="openai",
            model="gpt-3.5-turbo"
        )
        
        response = RAGResponse(
            query="test query",
            response="test response",
            sources=[],
            retrieval_result=retrieval_result,
            llm_response=llm_response,
            processing_time=2.0,
            context_tokens=200,
            response_tokens=50,
            total_cost=0.002
        )
        
        response_dict = response.to_dict()
        
        assert response_dict["query"] == "test query"
        assert response_dict["response"] == "test response"
        assert "sources" in response_dict
        assert "retrieval_stats" in response_dict
        assert "generation_stats" in response_dict
        assert response_dict["generation_stats"]["provider"] == "openai"