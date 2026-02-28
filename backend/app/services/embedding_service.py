"""
Embedding generation service for RAG applications.
Integrates with OpenAI text-embedding-3-small for consistent embeddings with batch processing and error handling.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Union
from uuid import UUID, uuid4
import time

import openai
from openai import AsyncOpenAI
import tiktoken

from ..core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingRequest:
    """Request for generating embeddings."""
    
    id: str  # Unique identifier for this request
    text: str
    metadata: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        """Validate embedding request."""
        if not self.text.strip():
            raise ValueError("Text cannot be empty")
        if len(self.text) > 8191:  # OpenAI's max input length for embeddings
            logger.warning(f"Text length ({len(self.text)}) exceeds recommended limit (8191)")


@dataclass
class EmbeddingResult:
    """Result of embedding generation."""
    
    id: str  # Matches the request ID
    embedding: List[float]
    token_count: int
    model: str
    metadata: Optional[Dict[str, Any]] = None
    processing_time: Optional[float] = None
    
    def __post_init__(self):
        """Validate embedding result."""
        if not self.embedding:
            raise ValueError("Embedding cannot be empty")
        if len(self.embedding) != settings.EMBEDDING_DIMENSION:
            raise ValueError(
                f"Embedding dimension ({len(self.embedding)}) doesn't match "
                f"expected dimension ({settings.EMBEDDING_DIMENSION})"
            )


@dataclass
class BatchEmbeddingResult:
    """Result of batch embedding generation."""
    
    results: List[EmbeddingResult]
    total_tokens: int
    total_processing_time: float
    failed_requests: List[str]  # IDs of failed requests
    
    @property
    def success_count(self) -> int:
        """Number of successful embeddings."""
        return len(self.results)
    
    @property
    def failure_count(self) -> int:
        """Number of failed embeddings."""
        return len(self.failed_requests)
    
    @property
    def success_rate(self) -> float:
        """Success rate as percentage."""
        total = self.success_count + self.failure_count
        return (self.success_count / total * 100) if total > 0 else 0.0


class EmbeddingError(Exception):
    """Custom exception for embedding generation errors."""
    
    def __init__(
        self,
        message: str,
        request_id: Optional[str] = None,
        original_error: Optional[Exception] = None,
        retryable: bool = False
    ):
        self.message = message
        self.request_id = request_id
        self.original_error = original_error
        self.retryable = retryable
        super().__init__(self.message)


class BaseEmbeddingGenerator(ABC):
    """Abstract base class for embedding generators."""
    
    @abstractmethod
    async def generate_embedding(self, request: EmbeddingRequest) -> EmbeddingResult:
        """Generate embedding for a single text."""
        pass
    
    @abstractmethod
    async def generate_embeddings_batch(
        self,
        requests: List[EmbeddingRequest],
        batch_size: int = 100
    ) -> BatchEmbeddingResult:
        """Generate embeddings for multiple texts in batches."""
        pass
    
    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """Count tokens in text for the embedding model."""
        pass


class OpenAIEmbeddingGenerator(BaseEmbeddingGenerator):
    """OpenAI embedding generator with retry logic and batch processing."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "text-embedding-3-small",
        max_retries: int = 3,
        retry_delay: float = 1.0,
        timeout: float = 30.0
    ):
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.model = model
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.timeout = timeout
        
        if not self.api_key:
            raise ValueError("OpenAI API key is required")
        
        self.client = AsyncOpenAI(api_key=self.api_key, timeout=self.timeout)
        
        # Initialize tokenizer for token counting
        try:
            self.encoding = tiktoken.get_encoding("cl100k_base")
        except Exception as e:
            logger.error(f"Failed to load tiktoken encoding: {e}")
            self.encoding = None
    
    def count_tokens(self, text: str) -> int:
        """Count tokens using tiktoken."""
        if self.encoding:
            return len(self.encoding.encode(text))
        else:
            # Fallback to rough estimation
            return len(text.split()) * 1.3
    
    async def generate_embedding(self, request: EmbeddingRequest) -> EmbeddingResult:
        """
        Generate embedding for a single text with retry logic.
        
        Args:
            request: EmbeddingRequest containing text and metadata
            
        Returns:
            EmbeddingResult with generated embedding
            
        Raises:
            EmbeddingError: If embedding generation fails after retries
        """
        start_time = time.time()
        
        for attempt in range(self.max_retries + 1):
            try:
                # Validate input length
                token_count = self.count_tokens(request.text)
                if token_count > 8191:
                    raise EmbeddingError(
                        f"Text too long: {token_count} tokens (max 8191)",
                        request.id,
                        retryable=False
                    )
                
                # Call OpenAI API
                response = await self.client.embeddings.create(
                    input=request.text,
                    model=self.model
                )
                
                # Extract embedding
                embedding_data = response.data[0]
                embedding = embedding_data.embedding
                
                processing_time = time.time() - start_time
                
                result = EmbeddingResult(
                    id=request.id,
                    embedding=embedding,
                    token_count=token_count,
                    model=self.model,
                    metadata=request.metadata,
                    processing_time=processing_time
                )
                
                logger.debug(
                    f"Generated embedding for request {request.id} "
                    f"({token_count} tokens, {processing_time:.2f}s)"
                )
                
                return result
                
            except openai.RateLimitError as e:
                if attempt < self.max_retries:
                    delay = self.retry_delay * (2 ** attempt)  # Exponential backoff
                    logger.warning(
                        f"Rate limit hit for request {request.id}, "
                        f"retrying in {delay}s (attempt {attempt + 1}/{self.max_retries + 1})"
                    )
                    await asyncio.sleep(delay)
                    continue
                else:
                    raise EmbeddingError(
                        f"Rate limit exceeded after {self.max_retries} retries",
                        request.id,
                        e,
                        retryable=True
                    )
            
            except openai.APIError as e:
                if attempt < self.max_retries and e.status_code >= 500:
                    delay = self.retry_delay * (2 ** attempt)
                    logger.warning(
                        f"API error for request {request.id}, "
                        f"retrying in {delay}s (attempt {attempt + 1}/{self.max_retries + 1}): {e}"
                    )
                    await asyncio.sleep(delay)
                    continue
                else:
                    raise EmbeddingError(
                        f"OpenAI API error: {e}",
                        request.id,
                        e,
                        retryable=e.status_code >= 500
                    )
            
            except EmbeddingError:
                # Re-raise EmbeddingError without modification
                raise
            
            except Exception as e:
                if attempt < self.max_retries:
                    delay = self.retry_delay * (2 ** attempt)
                    logger.warning(
                        f"Unexpected error for request {request.id}, "
                        f"retrying in {delay}s (attempt {attempt + 1}/{self.max_retries + 1}): {e}"
                    )
                    await asyncio.sleep(delay)
                    continue
                else:
                    raise EmbeddingError(
                        f"Unexpected error: {e}",
                        request.id,
                        e,
                        retryable=True
                    )
        
        # This should never be reached due to the loop structure
        raise EmbeddingError(
            f"Failed to generate embedding after {self.max_retries} retries",
            request.id,
            retryable=True
        )
    
    async def generate_embeddings_batch(
        self,
        requests: List[EmbeddingRequest],
        batch_size: int = 100
    ) -> BatchEmbeddingResult:
        """
        Generate embeddings for multiple texts in batches with concurrent processing.
        
        Args:
            requests: List of EmbeddingRequest objects
            batch_size: Maximum number of requests to process concurrently
            
        Returns:
            BatchEmbeddingResult with all results and statistics
        """
        if not requests:
            return BatchEmbeddingResult(
                results=[],
                total_tokens=0,
                total_processing_time=0.0,
                failed_requests=[]
            )
        
        start_time = time.time()
        results = []
        failed_requests = []
        total_tokens = 0
        
        # Process requests in batches to avoid overwhelming the API
        for i in range(0, len(requests), batch_size):
            batch = requests[i:i + batch_size]
            
            # Create tasks for concurrent processing
            tasks = [self.generate_embedding(request) for request in batch]
            
            # Wait for all tasks in this batch to complete
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            for request, result in zip(batch, batch_results):
                if isinstance(result, EmbeddingResult):
                    results.append(result)
                    total_tokens += result.token_count
                elif isinstance(result, EmbeddingError):
                    logger.error(f"Failed to generate embedding for {request.id}: {result.message}")
                    failed_requests.append(request.id)
                else:
                    logger.error(f"Unexpected result type for {request.id}: {type(result)}")
                    failed_requests.append(request.id)
            
            # Add small delay between batches to be respectful to the API
            if i + batch_size < len(requests):
                await asyncio.sleep(0.1)
        
        total_processing_time = time.time() - start_time
        
        logger.info(
            f"Batch embedding generation completed: "
            f"{len(results)} successful, {len(failed_requests)} failed, "
            f"{total_tokens} total tokens, {total_processing_time:.2f}s"
        )
        
        return BatchEmbeddingResult(
            results=results,
            total_tokens=total_tokens,
            total_processing_time=total_processing_time,
            failed_requests=failed_requests
        )


class EmbeddingService:
    """Main service for embedding generation operations."""
    
    def __init__(self, generator: Optional[BaseEmbeddingGenerator] = None):
        self.generator = generator or OpenAIEmbeddingGenerator()
    
    async def generate_embedding_for_text(
        self,
        text: str,
        request_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> EmbeddingResult:
        """
        Generate embedding for a single text.
        
        Args:
            text: Text to generate embedding for
            request_id: Optional unique identifier for the request
            metadata: Optional metadata to include with the result
            
        Returns:
            EmbeddingResult with generated embedding
            
        Raises:
            EmbeddingError: If embedding generation fails
        """
        request_id = request_id or str(uuid4())
        request = EmbeddingRequest(
            id=request_id,
            text=text,
            metadata=metadata
        )
        
        return await self.generator.generate_embedding(request)
    
    async def generate_embeddings_for_chunks(
        self,
        chunks: List[Dict[str, Any]],
        batch_size: int = 50
    ) -> BatchEmbeddingResult:
        """
        Generate embeddings for text chunks.
        
        Args:
            chunks: List of chunk dictionaries with 'id', 'content', and optional 'metadata'
            batch_size: Number of chunks to process concurrently
            
        Returns:
            BatchEmbeddingResult with all embeddings and statistics
        """
        requests = []
        
        for chunk in chunks:
            if 'id' not in chunk or 'content' not in chunk:
                raise ValueError("Each chunk must have 'id' and 'content' fields")
            
            request = EmbeddingRequest(
                id=str(chunk['id']),
                text=chunk['content'],
                metadata=chunk.get('metadata')
            )
            requests.append(request)
        
        return await self.generator.generate_embeddings_batch(requests, batch_size)
    
    def count_tokens(self, text: str) -> int:
        """Count tokens in text for the embedding model."""
        return self.generator.count_tokens(text)
    
    async def validate_api_connection(self) -> bool:
        """
        Validate that the embedding service can connect to the API.
        
        Returns:
            True if connection is successful, False otherwise
        """
        try:
            test_request = EmbeddingRequest(
                id="test",
                text="This is a test message for API validation."
            )
            
            result = await self.generator.generate_embedding(test_request)
            logger.info("Embedding service API connection validated successfully")
            return True
            
        except Exception as e:
            logger.error(f"Embedding service API connection failed: {e}")
            return False
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the current embedding model."""
        return {
            "model": getattr(self.generator, 'model', 'unknown'),
            "dimension": settings.EMBEDDING_DIMENSION,
            "max_tokens": 8191,
            "provider": "openai"
        }