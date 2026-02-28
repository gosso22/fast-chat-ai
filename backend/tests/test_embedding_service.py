"""
Unit tests for the embedding generation service.
Tests embedding generation, batch processing, error handling, and retry logic.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from app.services.embedding_service import (
    EmbeddingService,
    EmbeddingRequest,
    EmbeddingResult,
    BatchEmbeddingResult,
    EmbeddingError,
    OpenAIEmbeddingGenerator
)


class TestEmbeddingRequest:
    """Test EmbeddingRequest data class."""
    
    def test_valid_request(self):
        """Test creating a valid embedding request."""
        request = EmbeddingRequest(
            id="test-1",
            text="This is a test text for embedding.",
            metadata={"source": "test"}
        )
        
        assert request.id == "test-1"
        assert request.text == "This is a test text for embedding."
        assert request.metadata == {"source": "test"}
    
    def test_empty_text_raises_error(self):
        """Test that empty text raises ValueError."""
        with pytest.raises(ValueError, match="Text cannot be empty"):
            EmbeddingRequest(id="test", text="")
    
    def test_whitespace_only_text_raises_error(self):
        """Test that whitespace-only text raises ValueError."""
        with pytest.raises(ValueError, match="Text cannot be empty"):
            EmbeddingRequest(id="test", text="   \n\t  ")
    
    def test_long_text_warning(self, caplog):
        """Test that very long text generates a warning."""
        long_text = "a" * 10000  # Exceeds 8191 character limit
        request = EmbeddingRequest(id="test", text=long_text)
        
        assert "exceeds recommended limit" in caplog.text
        assert request.text == long_text


class TestEmbeddingResult:
    """Test EmbeddingResult data class."""
    
    def test_valid_result(self):
        """Test creating a valid embedding result."""
        embedding = [0.1] * 1536  # Standard OpenAI embedding dimension
        
        result = EmbeddingResult(
            id="test-1",
            embedding=embedding,
            token_count=10,
            model="text-embedding-3-small",
            metadata={"source": "test"},
            processing_time=0.5
        )
        
        assert result.id == "test-1"
        assert len(result.embedding) == 1536
        assert result.token_count == 10
        assert result.model == "text-embedding-3-small"
        assert result.processing_time == 0.5
    
    def test_empty_embedding_raises_error(self):
        """Test that empty embedding raises ValueError."""
        with pytest.raises(ValueError, match="Embedding cannot be empty"):
            EmbeddingResult(
                id="test",
                embedding=[],
                token_count=10,
                model="test-model"
            )
    
    def test_wrong_dimension_raises_error(self):
        """Test that wrong embedding dimension raises ValueError."""
        with pytest.raises(ValueError, match="doesn't match expected dimension"):
            EmbeddingResult(
                id="test",
                embedding=[0.1] * 512,  # Wrong dimension
                token_count=10,
                model="test-model"
            )


class TestBatchEmbeddingResult:
    """Test BatchEmbeddingResult data class."""
    
    def test_batch_result_properties(self):
        """Test batch result properties and calculations."""
        embedding = [0.1] * 1536
        results = [
            EmbeddingResult("1", embedding, 10, "model"),
            EmbeddingResult("2", embedding, 15, "model")
        ]
        
        batch_result = BatchEmbeddingResult(
            results=results,
            total_tokens=25,
            total_processing_time=1.5,
            failed_requests=["3", "4"]
        )
        
        assert batch_result.success_count == 2
        assert batch_result.failure_count == 2
        assert batch_result.success_rate == 50.0
    
    def test_empty_batch_result(self):
        """Test batch result with no results."""
        batch_result = BatchEmbeddingResult(
            results=[],
            total_tokens=0,
            total_processing_time=0.0,
            failed_requests=[]
        )
        
        assert batch_result.success_count == 0
        assert batch_result.failure_count == 0
        assert batch_result.success_rate == 0.0


class TestOpenAIEmbeddingGenerator:
    """Test OpenAI embedding generator."""
    
    @pytest.fixture
    def mock_openai_client(self):
        """Mock OpenAI client."""
        client = AsyncMock()
        
        # Mock successful response
        mock_response = Mock()
        mock_response.data = [Mock()]
        mock_response.data[0].embedding = [0.1] * 1536
        
        client.embeddings.create.return_value = mock_response
        return client
    
    @pytest.fixture
    def generator(self, mock_openai_client):
        """Create generator with mocked client."""
        with patch('app.services.embedding_service.AsyncOpenAI') as mock_openai:
            mock_openai.return_value = mock_openai_client
            generator = OpenAIEmbeddingGenerator(api_key="test-key")
            generator.client = mock_openai_client
            return generator
    
    def test_initialization_without_api_key(self):
        """Test that initialization without API key raises error."""
        with patch('app.services.embedding_service.settings') as mock_settings:
            mock_settings.OPENAI_API_KEY = ""
            
            with pytest.raises(ValueError, match="OpenAI API key is required"):
                OpenAIEmbeddingGenerator()
    
    def test_token_counting(self, generator):
        """Test token counting functionality."""
        text = "This is a test sentence."
        
        # Mock tiktoken encoding
        with patch.object(generator, 'encoding') as mock_encoding:
            mock_encoding.encode.return_value = [1, 2, 3, 4, 5]
            
            token_count = generator.count_tokens(text)
            assert token_count == 5
            mock_encoding.encode.assert_called_once_with(text)
    
    def test_token_counting_fallback(self, generator):
        """Test token counting fallback when tiktoken fails."""
        generator.encoding = None
        text = "This is a test sentence."
        
        token_count = generator.count_tokens(text)
        # Should use word count * 1.3 as fallback
        expected = len(text.split()) * 1.3
        assert token_count == expected
    
    @pytest.mark.asyncio
    async def test_successful_embedding_generation(self, generator, mock_openai_client):
        """Test successful embedding generation."""
        request = EmbeddingRequest(
            id="test-1",
            text="Test text for embedding"
        )
        
        # Mock token counting
        with patch.object(generator, 'count_tokens', return_value=5):
            result = await generator.generate_embedding(request)
        
        assert result.id == "test-1"
        assert len(result.embedding) == 1536
        assert result.token_count == 5
        assert result.model == "text-embedding-3-small"
        assert result.processing_time > 0
        
        mock_openai_client.embeddings.create.assert_called_once_with(
            input="Test text for embedding",
            model="text-embedding-3-small"
        )
    
    @pytest.mark.asyncio
    async def test_text_too_long_error(self, generator):
        """Test error when text is too long."""
        request = EmbeddingRequest(
            id="test-1",
            text="Very long text"
        )
        
        # Mock token counting to return too many tokens
        with patch.object(generator, 'count_tokens', return_value=10000):
            with pytest.raises(EmbeddingError) as exc_info:
                await generator.generate_embedding(request)
            
            assert "Text too long" in str(exc_info.value)
            assert exc_info.value.request_id == "test-1"
            assert not exc_info.value.retryable
    
    @pytest.mark.asyncio
    async def test_rate_limit_retry(self, generator, mock_openai_client):
        """Test retry logic for rate limit errors."""
        import openai
        
        request = EmbeddingRequest(id="test-1", text="Test text")
        
        # Mock rate limit error then success
        rate_limit_error = openai.RateLimitError(
            message="Rate limit exceeded",
            response=Mock(),
            body={}
        )
        
        mock_openai_client.embeddings.create.side_effect = [
            rate_limit_error,
            Mock(data=[Mock(embedding=[0.1] * 1536)])
        ]
        
        with patch.object(generator, 'count_tokens', return_value=5):
            with patch('asyncio.sleep') as mock_sleep:
                result = await generator.generate_embedding(request)
        
        assert result.id == "test-1"
        assert mock_openai_client.embeddings.create.call_count == 2
        mock_sleep.assert_called_once()  # Should have slept for retry
    
    @pytest.mark.asyncio
    async def test_rate_limit_max_retries_exceeded(self, generator, mock_openai_client):
        """Test rate limit error when max retries exceeded."""
        import openai
        
        request = EmbeddingRequest(id="test-1", text="Test text")
        
        rate_limit_error = openai.RateLimitError(
            message="Rate limit exceeded",
            response=Mock(),
            body={}
        )
        
        mock_openai_client.embeddings.create.side_effect = rate_limit_error
        
        with patch.object(generator, 'count_tokens', return_value=5):
            with patch('asyncio.sleep'):
                with pytest.raises(EmbeddingError) as exc_info:
                    await generator.generate_embedding(request)
        
        assert "Rate limit exceeded after" in str(exc_info.value)
        assert exc_info.value.retryable
        assert mock_openai_client.embeddings.create.call_count == 4  # Initial + 3 retries
    
    @pytest.mark.asyncio
    async def test_api_error_retry_on_server_error(self, generator, mock_openai_client):
        """Test retry logic for server errors (5xx)."""
        import openai
        
        request = EmbeddingRequest(id="test-1", text="Test text")
        
        # Mock server error then success
        server_error = openai.APIError(
            message="Internal server error",
            request=Mock(),
            body={}
        )
        server_error.status_code = 500
        
        mock_openai_client.embeddings.create.side_effect = [
            server_error,
            Mock(data=[Mock(embedding=[0.1] * 1536)])
        ]
        
        with patch.object(generator, 'count_tokens', return_value=5):
            with patch('asyncio.sleep'):
                result = await generator.generate_embedding(request)
        
        assert result.id == "test-1"
        assert mock_openai_client.embeddings.create.call_count == 2
    
    @pytest.mark.asyncio
    async def test_api_error_no_retry_on_client_error(self, generator, mock_openai_client):
        """Test no retry for client errors (4xx)."""
        import openai
        
        request = EmbeddingRequest(id="test-1", text="Test text")
        
        client_error = openai.APIError(
            message="Bad request",
            request=Mock(),
            body={}
        )
        client_error.status_code = 400
        
        mock_openai_client.embeddings.create.side_effect = client_error
        
        with patch.object(generator, 'count_tokens', return_value=5):
            with pytest.raises(EmbeddingError) as exc_info:
                await generator.generate_embedding(request)
        
        assert "OpenAI API error" in str(exc_info.value)
        assert not exc_info.value.retryable
        assert mock_openai_client.embeddings.create.call_count == 1  # No retries
    
    @pytest.mark.asyncio
    async def test_batch_embedding_generation(self, generator, mock_openai_client):
        """Test batch embedding generation."""
        requests = [
            EmbeddingRequest(id="1", text="Text 1"),
            EmbeddingRequest(id="2", text="Text 2"),
            EmbeddingRequest(id="3", text="Text 3")
        ]
        
        # Mock successful responses
        mock_openai_client.embeddings.create.return_value = Mock(
            data=[Mock(embedding=[0.1] * 1536)]
        )
        
        with patch.object(generator, 'count_tokens', return_value=5):
            result = await generator.generate_embeddings_batch(requests, batch_size=2)
        
        assert result.success_count == 3
        assert result.failure_count == 0
        assert result.total_tokens == 15  # 3 * 5 tokens
        assert len(result.results) == 3
        assert result.success_rate == 100.0
    
    @pytest.mark.asyncio
    async def test_batch_with_failures(self, generator, mock_openai_client):
        """Test batch processing with some failures."""
        import openai
        
        requests = [
            EmbeddingRequest(id="1", text="Text 1"),
            EmbeddingRequest(id="2", text="Text 2")
        ]
        
        # Mock one success, one failure
        success_response = Mock(data=[Mock(embedding=[0.1] * 1536)])
        failure_error = openai.APIError(message="Error", request=Mock(), body={})
        failure_error.status_code = 400
        
        mock_openai_client.embeddings.create.side_effect = [
            success_response,
            failure_error
        ]
        
        with patch.object(generator, 'count_tokens', return_value=5):
            result = await generator.generate_embeddings_batch(requests)
        
        assert result.success_count == 1
        assert result.failure_count == 1
        assert result.success_rate == 50.0
        assert "2" in result.failed_requests
    
    @pytest.mark.asyncio
    async def test_empty_batch(self, generator):
        """Test batch processing with empty request list."""
        result = await generator.generate_embeddings_batch([])
        
        assert result.success_count == 0
        assert result.failure_count == 0
        assert result.total_tokens == 0
        assert result.success_rate == 0.0


class TestEmbeddingService:
    """Test EmbeddingService main service class."""
    
    @pytest.fixture
    def mock_generator(self):
        """Mock embedding generator."""
        generator = AsyncMock()
        generator.count_tokens.return_value = 10
        return generator
    
    @pytest.fixture
    def service(self, mock_generator):
        """Create service with mocked generator."""
        return EmbeddingService(generator=mock_generator)
    
    @pytest.mark.asyncio
    async def test_generate_embedding_for_text(self, service, mock_generator):
        """Test generating embedding for single text."""
        expected_result = EmbeddingResult(
            id="test-id",
            embedding=[0.1] * 1536,
            token_count=10,
            model="test-model"
        )
        mock_generator.generate_embedding.return_value = expected_result
        
        result = await service.generate_embedding_for_text(
            text="Test text",
            request_id="test-id",
            metadata={"source": "test"}
        )
        
        assert result == expected_result
        
        # Verify the request was created correctly
        call_args = mock_generator.generate_embedding.call_args[0][0]
        assert call_args.id == "test-id"
        assert call_args.text == "Test text"
        assert call_args.metadata == {"source": "test"}
    
    @pytest.mark.asyncio
    async def test_generate_embedding_auto_id(self, service, mock_generator):
        """Test generating embedding with auto-generated ID."""
        expected_result = EmbeddingResult(
            id="auto-id",
            embedding=[0.1] * 1536,
            token_count=10,
            model="test-model"
        )
        mock_generator.generate_embedding.return_value = expected_result
        
        result = await service.generate_embedding_for_text("Test text")
        
        # Should have generated a UUID for the request
        call_args = mock_generator.generate_embedding.call_args[0][0]
        assert call_args.id is not None
        assert len(call_args.id) > 0
    
    @pytest.mark.asyncio
    async def test_generate_embeddings_for_chunks(self, service, mock_generator):
        """Test generating embeddings for chunks."""
        chunks = [
            {"id": "chunk-1", "content": "Content 1", "metadata": {"pos": 0}},
            {"id": "chunk-2", "content": "Content 2", "metadata": {"pos": 1}}
        ]
        
        expected_result = BatchEmbeddingResult(
            results=[],
            total_tokens=20,
            total_processing_time=1.0,
            failed_requests=[]
        )
        mock_generator.generate_embeddings_batch.return_value = expected_result
        
        result = await service.generate_embeddings_for_chunks(chunks, batch_size=10)
        
        assert result == expected_result
        
        # Verify the requests were created correctly
        call_args = mock_generator.generate_embeddings_batch.call_args[0][0]
        assert len(call_args) == 2
        assert call_args[0].id == "chunk-1"
        assert call_args[0].text == "Content 1"
        assert call_args[1].id == "chunk-2"
        assert call_args[1].text == "Content 2"
    
    @pytest.mark.asyncio
    async def test_generate_embeddings_invalid_chunks(self, service):
        """Test error handling for invalid chunk format."""
        invalid_chunks = [
            {"content": "Missing ID"},  # Missing 'id'
            {"id": "chunk-2"}  # Missing 'content'
        ]
        
        with pytest.raises(ValueError, match="must have 'id' and 'content' fields"):
            await service.generate_embeddings_for_chunks(invalid_chunks)
    
    def test_count_tokens(self, service, mock_generator):
        """Test token counting delegation."""
        service.count_tokens("Test text")
        mock_generator.count_tokens.assert_called_once_with("Test text")
    
    @pytest.mark.asyncio
    async def test_validate_api_connection_success(self, service, mock_generator):
        """Test successful API connection validation."""
        mock_generator.generate_embedding.return_value = EmbeddingResult(
            id="test",
            embedding=[0.1] * 1536,
            token_count=5,
            model="test-model"
        )
        
        result = await service.validate_api_connection()
        assert result is True
    
    @pytest.mark.asyncio
    async def test_validate_api_connection_failure(self, service, mock_generator):
        """Test API connection validation failure."""
        mock_generator.generate_embedding.side_effect = Exception("Connection failed")
        
        result = await service.validate_api_connection()
        assert result is False
    
    def test_get_model_info(self, service, mock_generator):
        """Test getting model information."""
        mock_generator.model = "text-embedding-3-small"
        
        info = service.get_model_info()
        
        assert info["model"] == "text-embedding-3-small"
        assert info["dimension"] == 1536
        assert info["max_tokens"] == 8191
        assert info["provider"] == "openai"


class TestEmbeddingError:
    """Test EmbeddingError exception class."""
    
    def test_basic_error(self):
        """Test basic error creation."""
        error = EmbeddingError("Test error message")
        
        assert str(error) == "Test error message"
        assert error.message == "Test error message"
        assert error.request_id is None
        assert error.original_error is None
        assert error.retryable is False
    
    def test_full_error(self):
        """Test error with all parameters."""
        original = ValueError("Original error")
        error = EmbeddingError(
            message="Wrapper error",
            request_id="req-123",
            original_error=original,
            retryable=True
        )
        
        assert error.message == "Wrapper error"
        assert error.request_id == "req-123"
        assert error.original_error == original
        assert error.retryable is True