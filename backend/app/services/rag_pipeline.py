"""
RAG (Retrieval-Augmented Generation) pipeline for response generation.
Implements prompt engineering, response generation, and source citation tracking.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Tuple
from uuid import UUID
import time
import json
from datetime import datetime

from .rag_service import SemanticSearchService, QueryContext, RetrievedChunk, RetrievalResult
from .llm_providers.manager import LLMProviderManager
from .llm_providers.base import LLMRequest, LLMResponse

logger = logging.getLogger(__name__)


@dataclass
class SourceCitation:
    """Citation information for a source document."""
    
    document_id: UUID
    document_filename: str
    chunk_index: int
    similarity_score: float
    excerpt: str  # Short excerpt from the chunk
    start_position: int
    end_position: int
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "document_id": str(self.document_id),
            "document_filename": self.document_filename,
            "chunk_index": self.chunk_index,
            "similarity_score": self.similarity_score,
            "excerpt": self.excerpt,
            "start_position": self.start_position,
            "end_position": self.end_position
        }


@dataclass
class RAGRequest:
    """Request for RAG response generation."""
    
    query: str
    user_id: Optional[str] = None
    conversation_id: Optional[str] = None
    document_ids: Optional[List[UUID]] = None
    environment_id: Optional[UUID] = None
    max_context_chunks: int = 5
    similarity_threshold: float = 0.3
    max_tokens: Optional[int] = None
    temperature: float = 0.7
    include_citations: bool = True
    system_prompt: Optional[str] = None
    
    def __post_init__(self):
        """Validate RAG request parameters."""
        if not self.query.strip():
            raise ValueError("Query cannot be empty")
        if self.max_context_chunks <= 0:
            raise ValueError("Max context chunks must be positive")
        if self.max_context_chunks > 20:
            raise ValueError("Max context chunks cannot exceed 20")
        if not (0.0 <= self.similarity_threshold <= 1.0):
            raise ValueError("Similarity threshold must be between 0.0 and 1.0")
        if not (0.0 <= self.temperature <= 2.0):
            raise ValueError("Temperature must be between 0.0 and 2.0")


@dataclass
class RAGResponse:
    """Response from RAG pipeline."""
    
    query: str
    response: str
    sources: List[SourceCitation]
    retrieval_result: RetrievalResult
    llm_response: LLMResponse
    processing_time: float
    context_tokens: int
    response_tokens: int
    total_cost: float
    
    @property
    def source_count(self) -> int:
        """Number of source citations."""
        return len(self.sources)
    
    @property
    def total_tokens(self) -> int:
        """Total tokens used (context + response)."""
        return self.context_tokens + self.response_tokens
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "query": self.query,
            "response": self.response,
            "sources": [source.to_dict() for source in self.sources],
            "retrieval_stats": {
                "chunks_retrieved": self.retrieval_result.chunk_count,
                "documents_searched": self.retrieval_result.document_count,
                "average_similarity": self.retrieval_result.average_similarity,
                "retrieval_time": self.retrieval_result.processing_time
            },
            "generation_stats": {
                "processing_time": self.processing_time,
                "context_tokens": self.context_tokens,
                "response_tokens": self.response_tokens,
                "total_tokens": self.total_tokens,
                "total_cost": self.total_cost,
                "provider": self.llm_response.provider,
                "model": self.llm_response.model
            }
        }


class RAGPipelineError(Exception):
    """Custom exception for RAG pipeline operations."""
    
    def __init__(
        self,
        message: str,
        stage: Optional[str] = None,
        query: Optional[str] = None,
        original_error: Optional[Exception] = None
    ):
        self.message = message
        self.stage = stage
        self.query = query
        self.original_error = original_error
        super().__init__(self.message)


class BasePromptTemplate(ABC):
    """Abstract base class for prompt templates."""
    
    @abstractmethod
    def format_prompt(
        self,
        query: str,
        context_chunks: List[RetrievedChunk],
        system_prompt: Optional[str] = None
    ) -> str:
        """Format the prompt with query and context."""
        pass
    
    @abstractmethod
    def extract_citations(
        self,
        response: str,
        context_chunks: List[RetrievedChunk]
    ) -> List[SourceCitation]:
        """Extract source citations from the response."""
        pass


class DefaultPromptTemplate(BasePromptTemplate):
    """Default prompt template for RAG responses."""
    
    def __init__(self, max_excerpt_length: int = 150):
        self.max_excerpt_length = max_excerpt_length
        self.default_system_prompt = """You are a helpful AI assistant that answers questions based on the provided context. 
Follow these guidelines:
1. Answer the question using only the information provided in the context
2. If the context doesn't contain enough information to answer the question, say so clearly
3. Cite your sources by referencing the document names when making specific claims
4. Be concise but comprehensive in your response
5. If multiple sources support the same point, mention all relevant sources"""
    
    def format_prompt(
        self,
        query: str,
        context_chunks: List[RetrievedChunk],
        system_prompt: Optional[str] = None
    ) -> str:
        """
        Format the prompt with query and context chunks.
        
        Args:
            query: User's question
            context_chunks: Retrieved context chunks
            system_prompt: Optional custom system prompt
            
        Returns:
            Formatted prompt string
        """
        # Use custom system prompt or default
        system = system_prompt or self.default_system_prompt
        
        # Format context
        if not context_chunks:
            context_section = "No relevant context found in the knowledge base."
        else:
            context_parts = []
            for i, chunk in enumerate(context_chunks, 1):
                # Create a short excerpt for context
                excerpt = chunk.content[:500] + "..." if len(chunk.content) > 500 else chunk.content
                
                context_parts.append(
                    f"Source {i} (from {chunk.document_filename}, chunk {chunk.chunk_index}):\n{excerpt}"
                )
            
            context_section = "\n\n".join(context_parts)
        
        # Format the complete prompt
        prompt = f"""{system}

Context Information:
{context_section}

Question: {query}

Please provide a comprehensive answer based on the context above. If you reference specific information, please cite the source (e.g., "according to Source 1" or "as mentioned in {context_chunks[0].document_filename if context_chunks else 'the document'}")."""
        
        return prompt
    
    def extract_citations(
        self,
        response: str,
        context_chunks: List[RetrievedChunk]
    ) -> List[SourceCitation]:
        """
        Extract source citations from the response.
        
        Args:
            response: Generated response text
            context_chunks: Context chunks that were used
            
        Returns:
            List of source citations
        """
        citations = []
        response_lower = response.lower()
        
        # Create citations for all chunks that appear to be referenced
        for chunk in context_chunks:
            is_referenced = False
            
            # Check for various citation patterns
            citation_patterns = [
                f"source {chunk.rank}",
                f"source{chunk.rank}",
                chunk.document_filename.lower(),
                f"chunk {chunk.chunk_index}",
                f"according to {chunk.document_filename.lower()}",
                f"as mentioned in {chunk.document_filename.lower()}",
                f"from {chunk.document_filename.lower()}"
            ]
            
            for pattern in citation_patterns:
                if pattern in response_lower:
                    is_referenced = True
                    break
            
            # Also check if key phrases from the chunk appear in the response
            if not is_referenced:
                # Extract key phrases from chunk (simple approach)
                chunk_words = set(chunk.content.lower().split())
                response_words = set(response_lower.split())
                
                # If significant overlap, consider it referenced
                overlap = len(chunk_words.intersection(response_words))
                if overlap >= min(5, len(chunk_words) * 0.3):
                    is_referenced = True
            
            if is_referenced:
                # Create excerpt for citation
                excerpt = chunk.content[:self.max_excerpt_length]
                if len(chunk.content) > self.max_excerpt_length:
                    excerpt += "..."
                
                citation = SourceCitation(
                    document_id=chunk.document_id,
                    document_filename=chunk.document_filename,
                    chunk_index=chunk.chunk_index,
                    similarity_score=chunk.similarity_score,
                    excerpt=excerpt,
                    start_position=chunk.start_position,
                    end_position=chunk.end_position
                )
                citations.append(citation)
        
        return citations


class RAGPipeline:
    """Main RAG pipeline for response generation."""
    
    def __init__(
        self,
        search_service: Optional[SemanticSearchService] = None,
        llm_manager: Optional[LLMProviderManager] = None,
        prompt_template: Optional[BasePromptTemplate] = None
    ):
        self.search_service = search_service or SemanticSearchService()
        self.llm_manager = llm_manager
        self.prompt_template = prompt_template or DefaultPromptTemplate()
        
        if not self.llm_manager:
            raise ValueError("LLM manager is required for RAG pipeline")
    
    async def generate_response(self, request: RAGRequest) -> RAGResponse:
        """
        Generate a RAG response for the given request.
        
        Args:
            request: RAG request with query and parameters
            
        Returns:
            RAG response with generated text and citations
            
        Raises:
            RAGPipelineError: If any stage of the pipeline fails
        """
        start_time = time.time()
        
        try:
            # Stage 1: Retrieve relevant context
            logger.info(f"Starting RAG pipeline for query: '{request.query[:50]}...'")
            
            query_context = QueryContext(
                query_text=request.query,
                user_id=request.user_id,
                conversation_id=request.conversation_id,
                document_ids=request.document_ids,
                environment_id=request.environment_id,
                max_results=request.max_context_chunks,
                similarity_threshold=request.similarity_threshold
            )
            
            retrieval_result = await self.search_service.retrieve_context(query_context)
            
            logger.info(
                f"Retrieved {retrieval_result.chunk_count} chunks from "
                f"{retrieval_result.document_count} documents "
                f"(avg similarity: {retrieval_result.average_similarity:.3f})"
            )
            
            # Error recovery: Handle empty search results
            if retrieval_result.chunk_count == 0:
                logger.warning(
                    f"No relevant context found for query: '{request.query}' "
                    f"(user_id: {request.user_id}, threshold: {request.similarity_threshold})"
                )
                
                # Try with lower similarity threshold as recovery mechanism
                if request.similarity_threshold > 0.1:
                    logger.info("Attempting recovery with lower similarity threshold (0.1)")
                    
                    recovery_context = QueryContext(
                        query_text=request.query,
                        user_id=request.user_id,
                        conversation_id=request.conversation_id,
                        document_ids=request.document_ids,
                        environment_id=request.environment_id,
                        max_results=request.max_context_chunks,
                        similarity_threshold=0.1  # Lower threshold for recovery
                    )
                    
                    try:
                        recovery_result = await self.search_service.retrieve_context(recovery_context)
                        if recovery_result.chunk_count > 0:
                            logger.info(
                                f"Recovery successful: found {recovery_result.chunk_count} chunks "
                                f"with lower threshold"
                            )
                            retrieval_result = recovery_result
                        else:
                            logger.warning("Recovery attempt also returned no results")
                    except Exception as recovery_error:
                        logger.error(f"Recovery attempt failed: {recovery_error}")
            
            # Stage 2: Format prompt with context (handle empty context gracefully)
            if retrieval_result.chunk_count == 0:
                # Generate response without context but inform user
                no_context_prompt = f"""You are a helpful AI assistant. The user asked: "{request.query}"

However, I don't have any relevant documents in my knowledge base to answer this question. Please let the user know that:
1. No relevant information was found in the uploaded documents
2. They may need to upload documents related to their question
3. They can try rephrasing their question or using different keywords
4. If they believe relevant documents exist, there may be a technical issue with document processing

Please provide a helpful response explaining this situation."""

                prompt = no_context_prompt
                context_tokens = len(prompt.split()) * 1.3
                
                logger.info("Generating response without context due to empty search results")
            else:
                prompt = self.prompt_template.format_prompt(
                    request.query,
                    retrieval_result.chunks,
                    request.system_prompt
                )
                context_tokens = len(prompt.split()) * 1.3
            
            # Stage 3: Generate response using LLM
            llm_request = LLMRequest(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                user_id=request.user_id
            )
            
            try:
                llm_response = await self.llm_manager.generate_response(
                    llm_request,
                    conversation_id=request.conversation_id,
                    user_id=request.user_id
                )
                
                logger.info(
                    f"LLM response generated: {llm_response.output_tokens} tokens, "
                    f"${llm_response.cost:.4f} cost, provider: {llm_response.provider}"
                )
                
            except Exception as llm_error:
                logger.error(f"LLM generation failed: {llm_error}")
                
                # Error recovery: Generate a fallback response
                fallback_response = LLMResponse(
                    content="I apologize, but I'm experiencing technical difficulties generating a response. Please try again in a moment.",
                    input_tokens=int(context_tokens),
                    output_tokens=20,
                    total_tokens=int(context_tokens) + 20,
                    cost=0.0,
                    provider="fallback",
                    model="fallback",
                    timestamp=datetime.utcnow(),
                    metadata={"error": str(llm_error), "fallback": True}
                )
                
                logger.warning("Using fallback response due to LLM failure")
                llm_response = fallback_response
            
            # Stage 4: Extract citations if requested and context available
            sources = []
            if request.include_citations and retrieval_result.chunks:
                try:
                    sources = self.prompt_template.extract_citations(
                        llm_response.content,
                        retrieval_result.chunks
                    )
                    logger.debug(f"Extracted {len(sources)} source citations")
                except Exception as citation_error:
                    logger.warning(f"Citation extraction failed: {citation_error}")
                    # Continue without citations rather than failing
            
            processing_time = time.time() - start_time
            
            # Create response
            rag_response = RAGResponse(
                query=request.query,
                response=llm_response.content,
                sources=sources,
                retrieval_result=retrieval_result,
                llm_response=llm_response,
                processing_time=processing_time,
                context_tokens=int(context_tokens),
                response_tokens=llm_response.output_tokens,
                total_cost=llm_response.cost
            )
            
            logger.info(
                f"RAG pipeline completed in {processing_time:.3f}s "
                f"({rag_response.total_tokens} tokens, ${rag_response.total_cost:.4f})"
            )
            
            return rag_response
            
        except Exception as e:
            logger.error(f"RAG pipeline failed for query '{request.query}': {e}", exc_info=True)
            
            # Determine which stage failed
            stage = "unknown"
            if "retrieve_context" in str(e) or "search" in str(e).lower():
                stage = "retrieval"
            elif "generate_response" in str(e) or "llm" in str(e).lower():
                stage = "generation"
            elif "format_prompt" in str(e) or "prompt" in str(e).lower():
                stage = "prompt_formatting"
            elif "extract_citations" in str(e) or "citation" in str(e).lower():
                stage = "citation_extraction"
            
            raise RAGPipelineError(
                f"RAG pipeline failed at {stage} stage: {str(e)}",
                stage,
                request.query,
                e
            )
    
    async def generate_simple_response(
        self,
        query: str,
        user_id: Optional[str] = None,
        max_chunks: int = 5,
        similarity_threshold: float = 0.3
    ) -> RAGResponse:
        """
        Convenience method for simple RAG response generation.
        
        Args:
            query: User's question
            user_id: Optional user ID
            max_chunks: Maximum context chunks to retrieve
            similarity_threshold: Minimum similarity score
            
        Returns:
            RAG response
        """
        request = RAGRequest(
            query=query,
            user_id=user_id,
            max_context_chunks=max_chunks,
            similarity_threshold=similarity_threshold
        )
        
        return await self.generate_response(request)
    
    async def validate_pipeline(self) -> bool:
        """
        Validate that the RAG pipeline is properly configured and functional.
        
        Returns:
            True if pipeline is working, False otherwise
        """
        try:
            # Test search service
            search_valid = await self.search_service.validate_search_capability()
            if not search_valid:
                logger.error("Search service validation failed")
                return False
            
            # Test LLM manager (basic check)
            if not self.llm_manager:
                logger.error("LLM manager not configured")
                return False
            
            # Check if any providers are available
            provider_status = self.llm_manager.get_provider_status()
            if hasattr(provider_status, '__await__'):
                # If it's a coroutine, await it
                provider_status = await provider_status
            healthy_providers = [
                name for name, status in provider_status.items()
                if status.get("enabled", False) and status.get("healthy", False)
            ]
            
            if not healthy_providers:
                logger.error("No healthy LLM providers available")
                return False
            
            logger.info(f"RAG pipeline validation successful (providers: {healthy_providers})")
            return True
            
        except Exception as e:
            logger.error(f"RAG pipeline validation failed: {e}")
            return False
    
    def get_pipeline_info(self) -> Dict[str, Any]:
        """Get information about the RAG pipeline configuration."""
        provider_status = {}
        if self.llm_manager:
            provider_status = self.llm_manager.get_provider_status()
        
        return {
            "search_service": self.search_service.get_service_info(),
            "prompt_template": type(self.prompt_template).__name__,
            "llm_providers": provider_status,
            "pipeline_stages": [
                "context_retrieval",
                "prompt_formatting", 
                "response_generation",
                "citation_extraction"
            ]
        }
    
    async def get_pipeline_stats(self) -> Dict[str, Any]:
        """Get pipeline usage statistics."""
        stats = {
            "search_service": "available",
            "llm_manager": "available" if self.llm_manager else "not_configured"
        }
        
        if self.llm_manager:
            # Get cost information if available
            try:
                daily_cost = await self.llm_manager.get_daily_cost()
                monthly_cost = await self.llm_manager.get_monthly_cost()
                stats.update({
                    "daily_cost": daily_cost,
                    "monthly_cost": monthly_cost
                })
            except Exception as e:
                logger.warning(f"Could not retrieve cost stats: {e}")
        
        return stats