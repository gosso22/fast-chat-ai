"""
Chat API endpoints for RAG chatbot functionality.
Implements conversation management, message handling, and real-time response streaming.
"""

import logging
from typing import List, Optional, Dict, Any
from uuid import UUID, uuid4
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Header, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.base import get_db
from ..services.rag_pipeline import RAGPipeline, RAGRequest, RAGResponse
from ..services.rag_service import SemanticSearchService
from ..services.llm_providers.manager import LLMProviderManager
from ..services.memory_manager import HybridMemoryManager
from ..models.conversation import Conversation, ChatMessage
from ..models.environment import Environment
from ..models.user_role import UserRole
from ..core.config import settings
from .dependencies import require_environment_access, validate_environment_exists

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])
env_chat_router = APIRouter(
    prefix="/environments", tags=["environment-chat"]
)


# Pydantic models for API requests/responses
class ChatMessageSchema(BaseModel):
    """Chat message model."""
    id: Optional[UUID] = None
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=1, max_length=10000)
    timestamp: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None


class StartConversationRequest(BaseModel):
    """Request to start a new conversation."""
    title: Optional[str] = Field(None, max_length=255)
    user_id: str = Field(..., min_length=1, max_length=255)
    document_ids: Optional[List[UUID]] = None
    system_prompt: Optional[str] = Field(None, max_length=2000)
    environment_id: Optional[UUID] = None


class StartConversationResponse(BaseModel):
    """Response for starting a new conversation."""
    conversation_id: UUID
    title: str
    created_at: datetime
    message: str = "Conversation started successfully"


class SendMessageRequest(BaseModel):
    """Request to send a message in a conversation."""
    message: str = Field(..., min_length=1, max_length=10000)
    max_context_chunks: int = Field(default=5, ge=1, le=20)
    similarity_threshold: float = Field(default=0.3, ge=0.0, le=1.0)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, ge=1, le=4000)
    include_citations: bool = True
    stream: bool = False


class SendMessageResponse(BaseModel):
    """Response for sending a message."""
    message_id: UUID
    conversation_id: UUID
    response: str
    sources: List[Dict[str, Any]] = []
    metadata: Dict[str, Any] = {}
    timestamp: datetime


class UpdateConversationRequest(BaseModel):
    """Request to update a conversation."""
    title: str = Field(..., min_length=1, max_length=255)
    user_id: str = Field(..., min_length=1, max_length=255)


class ConversationSummary(BaseModel):
    """Summary of a conversation."""
    id: UUID
    title: str
    user_id: str
    created_at: datetime
    updated_at: datetime
    message_count: int
    last_message_preview: Optional[str] = None


class ConversationDetail(BaseModel):
    """Detailed conversation with messages."""
    id: UUID
    title: str
    user_id: str
    created_at: datetime
    updated_at: datetime
    messages: List[ChatMessageSchema]


class ConversationListResponse(BaseModel):
    """Response for listing conversations."""
    conversations: List[ConversationSummary]
    total: int
    page: int
    page_size: int


# Dependency to get RAG pipeline
async def get_rag_pipeline() -> RAGPipeline:
    """Get configured RAG pipeline instance with proper error handling and fallback."""
    try:
        # Initialize search service with error handling
        try:
            search_service = SemanticSearchService()
            logger.info("Successfully initialized semantic search service")
        except Exception as e:
            logger.error(f"Failed to initialize search service: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Search service initialization failed"
            )
        
        # Initialize LLM manager with proper configuration and fallback
        llm_manager = None
        
        try:
            from ..services.llm_providers.manager import LLMProviderManager
            from ..services.llm_providers.base import ProviderConfig, ModelConfig
            from ..core.config import settings
            
            # Collect available provider configurations
            provider_configs = []
            
            # OpenAI Provider
            if settings.OPENAI_API_KEY and settings.OPENAI_ENABLED:
                try:
                    openai_models = [
                        ModelConfig(
                            name="gpt-3.5-turbo",
                            input_cost_per_1k_tokens=0.001,
                            output_cost_per_1k_tokens=0.002,
                            max_tokens=4096,
                            context_window=4096
                        ),
                        ModelConfig(
                            name="gpt-4",
                            input_cost_per_1k_tokens=0.03,
                            output_cost_per_1k_tokens=0.06,
                            max_tokens=4096,
                            context_window=8192
                        )
                    ]
                    
                    openai_config = ProviderConfig(
                        name="openai",
                        api_key=settings.OPENAI_API_KEY,
                        models=openai_models,
                        priority=settings.OPENAI_PRIORITY,
                        enabled=True
                    )
                    provider_configs.append(openai_config)
                    logger.info("Added OpenAI provider configuration")
                except Exception as e:
                    logger.warning(f"Failed to configure OpenAI provider: {e}")
            
            # Anthropic Provider
            if settings.ANTHROPIC_API_KEY and settings.ANTHROPIC_ENABLED:
                try:
                    anthropic_models = [
                        ModelConfig(
                            name="claude-3-haiku-20240307",
                            input_cost_per_1k_tokens=0.00025,
                            output_cost_per_1k_tokens=0.00125,
                            max_tokens=4096,
                            context_window=200000
                        ),
                        ModelConfig(
                            name="claude-3-sonnet-20240229",
                            input_cost_per_1k_tokens=0.003,
                            output_cost_per_1k_tokens=0.015,
                            max_tokens=4096,
                            context_window=200000
                        )
                    ]
                    
                    anthropic_config = ProviderConfig(
                        name="anthropic",
                        api_key=settings.ANTHROPIC_API_KEY,
                        models=anthropic_models,
                        priority=settings.ANTHROPIC_PRIORITY,
                        enabled=True
                    )
                    provider_configs.append(anthropic_config)
                    logger.info("Added Anthropic provider configuration")
                except Exception as e:
                    logger.warning(f"Failed to configure Anthropic provider: {e}")
            
            # Google Provider
            if settings.GOOGLE_API_KEY and settings.GOOGLE_ENABLED:
                try:
                    google_models = [
                        ModelConfig(
                            name="gemini-pro",
                            input_cost_per_1k_tokens=0.0005,
                            output_cost_per_1k_tokens=0.0015,
                            max_tokens=2048,
                            context_window=30720
                        )
                    ]
                    
                    google_config = ProviderConfig(
                        name="google",
                        api_key=settings.GOOGLE_API_KEY,
                        models=google_models,
                        priority=settings.GOOGLE_PRIORITY,
                        enabled=True
                    )
                    provider_configs.append(google_config)
                    logger.info("Added Google provider configuration")
                except Exception as e:
                    logger.warning(f"Failed to configure Google provider: {e}")
            
            # Initialize LLM manager if we have at least one provider
            if provider_configs:
                try:
                    llm_manager = LLMProviderManager(provider_configs)
                    logger.info(f"Successfully initialized LLM manager with {len(provider_configs)} providers")
                    
                    # Validate at least one provider is healthy
                    provider_status = llm_manager.get_provider_status()
                    
                    # Check if provider_status is a coroutine and await it if needed
                    if hasattr(provider_status, '__await__'):
                        provider_status = await provider_status
                    
                    healthy_providers = [
                        name for name, status in provider_status.items()
                        if status.get("enabled", False)
                    ]
                    
                    if not healthy_providers:
                        logger.warning("No healthy LLM providers available")
                        raise ValueError("No healthy LLM providers configured")
                    
                    logger.info(f"Available LLM providers: {healthy_providers}")
                    
                except Exception as e:
                    logger.error(f"Failed to initialize LLM manager: {e}")
                    raise ValueError(f"LLM manager initialization failed: {e}")
            else:
                logger.error("No LLM provider configurations available")
                raise ValueError("No LLM providers configured - check API keys and settings")
                
        except Exception as e:
            logger.error(f"LLM provider setup failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"LLM providers not available: {str(e)}"
            )
        
        # Initialize RAG pipeline
        try:
            pipeline = RAGPipeline(
                search_service=search_service,
                llm_manager=llm_manager
            )
            logger.info("Successfully initialized RAG pipeline")
        except Exception as e:
            logger.error(f"Failed to initialize RAG pipeline: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"RAG pipeline initialization failed: {str(e)}"
            )
        
        # Validate pipeline functionality
        try:
            is_valid = await pipeline.validate_pipeline()
            if not is_valid:
                logger.error("RAG pipeline validation failed")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="RAG pipeline validation failed"
                )
            logger.info("RAG pipeline validation successful")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"RAG pipeline validation error: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"RAG pipeline validation error: {str(e)}"
            )
        
        return pipeline
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in RAG pipeline initialization: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RAG service temporarily unavailable"
        )


# Dependency to get memory manager
async def get_memory_manager() -> HybridMemoryManager:
    """Get configured memory manager instance with Redis error handling and graceful degradation."""
    try:
        from ..services.redis_client import SessionManager, RedisClient
        
        # Initialize Redis client with error handling
        redis_client = RedisClient()
        redis_connected = False
        
        try:
            await redis_client.connect()
            redis_connected = await redis_client.is_connected()
            
            if redis_connected:
                logger.info("Successfully connected to Redis for memory management")
            else:
                logger.warning("Redis connection test failed")
                
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}")
            redis_connected = False
        
        # Create session manager with Redis if available
        if redis_connected:
            try:
                session_manager = SessionManager(redis_client)
                memory_manager = HybridMemoryManager(session_manager)
                logger.info("Successfully initialized hybrid memory manager with Redis")
                return memory_manager
            except Exception as e:
                logger.error(f"Failed to initialize hybrid memory manager with Redis: {e}")
                # Fall through to database-only mode
        
        # Fallback: Create a database-only memory manager
        logger.warning("Falling back to database-only memory management (Redis unavailable)")
        
        try:
            # Create a mock session manager that only uses database
            class DatabaseOnlySessionManager:
                """Mock session manager that only uses database storage."""
                
                def __init__(self):
                    self.redis_available = False
                
                async def create_session(self, conversation_id: str, user_id: str, initial_data=None):
                    logger.debug(f"Database-only session created for {conversation_id}")
                
                async def get_session(self, conversation_id: str):
                    return None  # Always return None to force database lookup
                
                async def session_exists(self, conversation_id: str):
                    return False  # Always return False to force database lookup
                
                async def add_message(self, conversation_id: str, message: dict):
                    logger.debug(f"Database-only message storage for {conversation_id}")
                
                async def get_messages(self, conversation_id: str, limit=None):
                    return []  # Return empty to force database lookup
                
                async def delete_session(self, conversation_id: str):
                    logger.debug(f"Database-only session deletion for {conversation_id}")
                
                async def get_session_stats(self, conversation_id: str):
                    return None
                
                async def extend_session_ttl(self, conversation_id: str, ttl: int):
                    pass  # No-op for database-only mode
                
                async def cleanup_expired_sessions(self):
                    return 0
                
                async def get_active_sessions(self, user_id=None):
                    return []
            
            fallback_session_manager = DatabaseOnlySessionManager()
            memory_manager = HybridMemoryManager(fallback_session_manager)
            
            logger.info("Successfully initialized database-only memory manager")
            return memory_manager
            
        except Exception as e:
            logger.error(f"Failed to initialize fallback memory manager: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Memory management service unavailable"
            )
        
    except Exception as e:
        logger.error(f"Critical error in memory manager initialization: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Memory service temporarily unavailable"
        )


@router.post("/conversations", response_model=StartConversationResponse)
async def start_conversation(
    request: StartConversationRequest,
    session: AsyncSession = Depends(get_db),
    memory_manager: HybridMemoryManager = Depends(get_memory_manager)
) -> StartConversationResponse:
    """
    Start a new conversation.
    
    Creates a new conversation record and initializes memory management.
    """
    try:
        # Generate conversation ID
        conversation_id = uuid4()
        
        # Create conversation title if not provided
        title = request.title or f"Conversation {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"
        
        # Create conversation record
        conversation = Conversation(
            id=conversation_id,
            user_id=request.user_id,
            title=title,
            environment_id=request.environment_id,
        )
        
        session.add(conversation)
        await session.commit()
        await session.refresh(conversation)
        
        # Initialize conversation memory
        await memory_manager.initialize_memory(
            conversation_id=str(conversation_id),
            user_id=request.user_id,
            warm_cache=False
        )
        
        logger.info(f"Started conversation {conversation_id} for user {request.user_id}")
        
        return StartConversationResponse(
            conversation_id=conversation_id,
            title=title,
            created_at=conversation.created_at
        )
        
    except Exception as e:
        logger.error(f"Failed to start conversation: {e}")
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start conversation"
        )


@router.post("/conversations/{conversation_id}/messages", response_model=SendMessageResponse)
async def send_message(
    conversation_id: UUID,
    request: SendMessageRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
    rag_pipeline: RAGPipeline = Depends(get_rag_pipeline),
    memory_manager: HybridMemoryManager = Depends(get_memory_manager)
) -> SendMessageResponse:
    """
    Send a message in a conversation and get RAG response.
    
    Processes the user message through the RAG pipeline and returns
    a contextual response with source citations.
    """
    # Enhanced logging for debugging RAG pipeline issues
    logger.info(
        f"Processing message in conversation {conversation_id}: "
        f"user_message='{request.message[:100]}...', "
        f"max_chunks={request.max_context_chunks}, "
        f"similarity_threshold={request.similarity_threshold}"
    )
    
    user_message = None
    assistant_message = None
    
    try:
        # Verify conversation exists
        conversation = await session.get(Conversation, conversation_id)
        if not conversation:
            logger.error(f"Conversation {conversation_id} not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found"
            )
        
        logger.info(f"Found conversation {conversation_id} for user {conversation.user_id}")
        
        # Create user message record
        user_message_id = uuid4()
        user_message = ChatMessage(
            id=user_message_id,
            conversation_id=conversation_id,
            role="user",
            content=request.message,
            token_count=int(len(request.message.split()) * 1.3)  # Rough token estimate
        )
        
        session.add(user_message)
        logger.debug(f"Added user message {user_message_id} to session")
        
        # Add user message to memory with error handling
        try:
            await memory_manager.add_user_message(
                conversation_id=str(conversation_id),
                message=request.message,
                user_id=conversation.user_id
            )
            logger.debug(f"Added user message to memory for conversation {conversation_id}")
        except Exception as memory_error:
            logger.warning(f"Failed to add user message to memory: {memory_error}")
            # Continue processing even if memory fails
        
        # Create RAG request with comprehensive logging
        rag_request = RAGRequest(
            query=request.message,
            user_id=conversation.user_id,
            conversation_id=str(conversation_id),
            max_context_chunks=request.max_context_chunks,
            similarity_threshold=request.similarity_threshold,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            include_citations=request.include_citations,
            environment_id=conversation.environment_id,
        )
        
        logger.info(
            f"Starting RAG pipeline for conversation {conversation_id}: "
            f"user_id={conversation.user_id}, query_length={len(request.message)}"
        )
        
        # Generate RAG response with detailed error handling
        try:
            rag_response = await rag_pipeline.generate_response(rag_request)
            
            logger.info(
                f"RAG pipeline completed for conversation {conversation_id}: "
                f"chunks_retrieved={rag_response.retrieval_result.chunk_count}, "
                f"documents_searched={rag_response.retrieval_result.document_count}, "
                f"avg_similarity={rag_response.retrieval_result.average_similarity:.3f}, "
                f"response_tokens={rag_response.response_tokens}, "
                f"total_cost=${rag_response.total_cost:.4f}"
            )
            
            # Log if no context was retrieved
            if rag_response.retrieval_result.chunk_count == 0:
                logger.warning(
                    f"No document chunks retrieved for query in conversation {conversation_id}. "
                    f"This may indicate: no documents uploaded, embedding issues, or "
                    f"similarity threshold too high ({request.similarity_threshold})"
                )
            
        except Exception as rag_error:
            logger.error(
                f"RAG pipeline failed for conversation {conversation_id}: {rag_error}",
                exc_info=True
            )
            # Rollback the user message since RAG failed
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"RAG pipeline failed: {str(rag_error)}"
            )
        
        # Create assistant message record
        assistant_message_id = uuid4()
        assistant_message = ChatMessage(
            id=assistant_message_id,
            conversation_id=conversation_id,
            role="assistant",
            content=rag_response.response,
            token_count=rag_response.response_tokens
        )
        
        session.add(assistant_message)
        logger.debug(f"Added assistant message {assistant_message_id} to session")
        
        # Add assistant message to memory with error handling
        try:
            await memory_manager.add_ai_message(
                conversation_id=str(conversation_id),
                message=rag_response.response,
                user_id=conversation.user_id
            )
            logger.debug(f"Added assistant message to memory for conversation {conversation_id}")
        except Exception as memory_error:
            logger.warning(f"Failed to add assistant message to memory: {memory_error}")
            # Continue processing even if memory fails
        
        # Update conversation timestamp
        conversation.updated_at = datetime.utcnow()
        
        # Commit all database changes in a single transaction
        try:
            await session.commit()
            logger.info(f"Successfully committed transaction for conversation {conversation_id}")
        except Exception as commit_error:
            logger.error(
                f"Database commit failed for conversation {conversation_id}: {commit_error}",
                exc_info=True
            )
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database transaction failed: {str(commit_error)}"
            )
        
        # Prepare response metadata with enhanced debugging info
        metadata = {
            "retrieval_stats": {
                "chunks_retrieved": rag_response.retrieval_result.chunk_count,
                "documents_searched": rag_response.retrieval_result.document_count,
                "average_similarity": rag_response.retrieval_result.average_similarity,
                "retrieval_time": rag_response.retrieval_result.processing_time,
                "embedding_time": rag_response.retrieval_result.embedding_time,
                "search_time": rag_response.retrieval_result.search_time,
                "ranking_time": rag_response.retrieval_result.ranking_time
            },
            "generation_stats": {
                "processing_time": rag_response.processing_time,
                "context_tokens": rag_response.context_tokens,
                "response_tokens": rag_response.response_tokens,
                "total_tokens": rag_response.total_tokens,
                "total_cost": rag_response.total_cost,
                "provider": rag_response.llm_response.provider,
                "model": rag_response.llm_response.model
            },
            "debug_info": {
                "user_id": conversation.user_id,
                "conversation_id": str(conversation_id),
                "similarity_threshold": request.similarity_threshold,
                "max_context_chunks": request.max_context_chunks,
                "environment_id": str(conversation.environment_id) if conversation.environment_id else None
            }
        }
        
        # Schedule background title generation on first message
        default_title = (
            conversation.title is None
            or conversation.title.startswith("Conversation ")
            or conversation.title == "New Conversation"
        )
        if default_title:
            background_tasks.add_task(
                generate_conversation_title_task,
                str(conversation_id),
                request.message,
            )

        # Schedule background task for memory optimization
        background_tasks.add_task(
            optimize_conversation_memory,
            str(conversation_id),
            memory_manager
        )
        
        logger.info(
            f"Successfully processed message in conversation {conversation_id} "
            f"({rag_response.total_tokens} tokens, ${rag_response.total_cost:.4f})"
        )
        
        return SendMessageResponse(
            message_id=assistant_message_id,
            conversation_id=conversation_id,
            response=rag_response.response,
            sources=[source.to_dict() for source in rag_response.sources],
            metadata=metadata,
            timestamp=assistant_message.created_at
        )
        
    except HTTPException:
        # HTTPExceptions are already handled, just re-raise
        await session.rollback()
        raise
    except Exception as e:
        logger.error(
            f"Unexpected error processing message in conversation {conversation_id}: {e}",
            exc_info=True
        )
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process message: {str(e)}"
        )


@router.post("/conversations/{conversation_id}/messages/stream")
async def send_message_stream(
    conversation_id: UUID,
    request: SendMessageRequest,
    session: AsyncSession = Depends(get_db),
    rag_pipeline: RAGPipeline = Depends(get_rag_pipeline),
    memory_manager: HybridMemoryManager = Depends(get_memory_manager)
) -> StreamingResponse:
    """
    Send a message and stream the response in real-time.
    
    This endpoint provides real-time streaming of the RAG response
    for better user experience with long responses.
    """
    # For now, return a simple implementation
    # In a full implementation, this would stream the LLM response
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Streaming responses not yet implemented"
    )


@router.get("/conversations", response_model=ConversationListResponse)
async def list_conversations(
    user_id: str,
    page: int = 1,
    page_size: int = 20,
    session: AsyncSession = Depends(get_db)
) -> ConversationListResponse:
    """
    List conversations for a user with pagination.
    
    Returns a paginated list of conversations ordered by most recent activity.
    """
    try:
        # Validate pagination parameters
        if page < 1:
            page = 1
        if page_size < 1 or page_size > 100:
            page_size = 20
        
        offset = (page - 1) * page_size
        
        # Query conversations with message count and last message preview
        from sqlalchemy import select, func, desc
        from sqlalchemy.orm import selectinload
        
        # Get total count
        count_query = select(func.count(Conversation.id)).where(
            Conversation.user_id == user_id
        )
        total_result = await session.execute(count_query)
        total = total_result.scalar()
        
        # Get conversations with basic info
        conversations_query = (
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(desc(Conversation.updated_at))
            .offset(offset)
            .limit(page_size)
        )
        
        conversations_result = await session.execute(conversations_query)
        conversations = conversations_result.scalars().all()
        
        # Build response with message counts and previews
        conversation_summaries = []
        for conv in conversations:
            # Get message count for this conversation
            message_count_query = select(func.count(ChatMessage.id)).where(
                ChatMessage.conversation_id == conv.id
            )
            message_count_result = await session.execute(message_count_query)
            message_count = message_count_result.scalar()
            
            # Get last message preview
            last_message_query = (
                select(ChatMessage.content)
                .where(ChatMessage.conversation_id == conv.id)
                .order_by(desc(ChatMessage.created_at))
                .limit(1)
            )
            last_message_result = await session.execute(last_message_query)
            last_message = last_message_result.scalar()
            
            # Create preview (first 100 characters)
            preview = None
            if last_message:
                preview = last_message[:100] + "..." if len(last_message) > 100 else last_message
            
            conversation_summaries.append(ConversationSummary(
                id=conv.id,
                title=conv.title,
                user_id=conv.user_id,
                created_at=conv.created_at,
                updated_at=conv.updated_at,
                message_count=message_count,
                last_message_preview=preview
            ))
        
        return ConversationListResponse(
            conversations=conversation_summaries,
            total=total,
            page=page,
            page_size=page_size
        )
        
    except Exception as e:
        logger.error(f"Failed to list conversations for user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve conversations"
        )


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: UUID,
    user_id: str,
    session: AsyncSession = Depends(get_db)
) -> ConversationDetail:
    """
    Get a specific conversation with all messages.
    
    Returns the complete conversation history including all messages.
    """
    try:
        # Get conversation with messages
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        
        query = (
            select(Conversation)
            .options(selectinload(Conversation.messages))
            .where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id
            )
        )
        
        result = await session.execute(query)
        conversation = result.scalar_one_or_none()
        
        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found"
            )
        
        # Convert messages to API format
        messages = []
        for msg in sorted(conversation.messages, key=lambda x: x.created_at):
            messages.append(ChatMessageSchema(
                id=msg.id,
                role=msg.role,
                content=msg.content,
                timestamp=msg.created_at,
                metadata={}
            ))
        
        return ConversationDetail(
            id=conversation.id,
            title=conversation.title,
            user_id=conversation.user_id,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            messages=messages
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get conversation {conversation_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve conversation"
        )


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: UUID,
    user_id: str,
    session: AsyncSession = Depends(get_db),
    memory_manager: HybridMemoryManager = Depends(get_memory_manager)
) -> Dict[str, str]:
    """
    Delete a conversation and all its messages.
    
    Removes the conversation from both database and memory storage.
    """
    try:
        # Get conversation to verify ownership
        conversation = await session.get(Conversation, conversation_id)
        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found"
            )
        
        if conversation.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to delete this conversation"
            )
        
        # Delete from memory first
        await memory_manager.clear_memory(str(conversation_id))
        
        # Delete from database (messages will be deleted via cascade)
        await session.delete(conversation)
        await session.commit()
        
        logger.info(f"Deleted conversation {conversation_id} for user {user_id}")
        
        return {"message": "Conversation deleted successfully"}
        
    except HTTPException:
        await session.rollback()
        raise
    except Exception as e:
        logger.error(f"Failed to delete conversation {conversation_id}: {e}")
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete conversation"
        )


@router.patch("/conversations/{conversation_id}", response_model=ConversationSummary)
async def update_conversation(
    conversation_id: UUID,
    request: UpdateConversationRequest,
    session: AsyncSession = Depends(get_db)
) -> ConversationSummary:
    """
    Update a conversation's title.
    """
    try:
        conversation = await session.get(Conversation, conversation_id)
        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found"
            )

        if conversation.user_id != request.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to update this conversation"
            )

        conversation.title = request.title
        conversation.updated_at = datetime.utcnow()
        await session.commit()
        await session.refresh(conversation)

        logger.info(f"Updated conversation {conversation_id} title to: {request.title}")

        # Get message count for response
        from sqlalchemy import select, func
        message_count_result = await session.execute(
            select(func.count(ChatMessage.id)).where(
                ChatMessage.conversation_id == conversation_id
            )
        )
        message_count = message_count_result.scalar()

        return ConversationSummary(
            id=conversation.id,
            title=conversation.title,
            user_id=conversation.user_id,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            message_count=message_count,
        )

    except HTTPException:
        await session.rollback()
        raise
    except Exception as e:
        logger.error(f"Failed to update conversation {conversation_id}: {e}")
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update conversation"
        )


@router.get("/conversations/{conversation_id}/memory/stats")
async def get_conversation_memory_stats(
    conversation_id: UUID,
    user_id: str,
    memory_manager: HybridMemoryManager = Depends(get_memory_manager)
) -> Dict[str, Any]:
    """
    Get memory usage statistics for a conversation.
    
    Returns information about token usage, memory optimization, and conversation state.
    """
    try:
        stats = await memory_manager.get_session_info(str(conversation_id))
        
        if not stats:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation memory not found"
            )
        
        return stats
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get memory stats for conversation {conversation_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve memory statistics"
        )


# Background task functions
async def generate_conversation_title_task(
    conversation_id: str,
    first_message: str,
) -> None:
    """
    Background task to generate a conversation title from the first message.
    """
    try:
        from uuid import UUID as _UUID
        from ..services.title_generator import generate_title
        from ..db.base import get_async_session

        conv_uuid = _UUID(conversation_id) if isinstance(conversation_id, str) else conversation_id

        # Build a lightweight LLM manager for the title call
        llm_manager = await _build_llm_manager()
        if not llm_manager:
            logger.warning(f"No LLM manager available for title generation (conversation {conversation_id})")
            return

        title = await generate_title(first_message, llm_manager)

        # Persist the new title using a fresh session
        session = get_async_session()
        try:
            conversation = await session.get(Conversation, conv_uuid)
            if conversation:
                conversation.title = title
                await session.commit()
                logger.info(f"Auto-generated title for conversation {conversation_id}: {title}")
        finally:
            await session.close()

    except Exception as e:
        logger.error(f"Background title generation failed for conversation {conversation_id}: {e}")


async def _build_llm_manager() -> Optional[LLMProviderManager]:
    """Build a minimal LLM provider manager for lightweight calls like title generation."""
    try:
        from ..services.llm_providers.base import ProviderConfig, ModelConfig

        provider_configs = []

        if settings.OPENAI_API_KEY and settings.OPENAI_ENABLED:
            provider_configs.append(ProviderConfig(
                name="openai",
                api_key=settings.OPENAI_API_KEY,
                models=[ModelConfig(
                    name="gpt-3.5-turbo",
                    input_cost_per_1k_tokens=0.001,
                    output_cost_per_1k_tokens=0.002,
                    max_tokens=4096,
                    context_window=4096,
                )],
                priority=1,
                enabled=True,
            ))

        if settings.ANTHROPIC_API_KEY and settings.ANTHROPIC_ENABLED:
            provider_configs.append(ProviderConfig(
                name="anthropic",
                api_key=settings.ANTHROPIC_API_KEY,
                models=[ModelConfig(
                    name="claude-3-haiku-20240307",
                    input_cost_per_1k_tokens=0.00025,
                    output_cost_per_1k_tokens=0.00125,
                    max_tokens=4096,
                    context_window=200000,
                )],
                priority=2 if provider_configs else 1,
                enabled=True,
            ))

        if not provider_configs:
            return None

        return LLMProviderManager(provider_configs=provider_configs)

    except Exception as e:
        logger.error(f"Failed to build LLM manager for title generation: {e}")
        return None


async def optimize_conversation_memory(
    conversation_id: str,
    memory_manager: HybridMemoryManager
) -> None:
    """
    Background task to optimize conversation memory.
    
    Performs memory cleanup and optimization to manage token usage.
    """
    try:
        await memory_manager.auto_manage_conversation_tokens(conversation_id)
        logger.info(f"Optimized memory for conversation {conversation_id}")
    except Exception as e:
        logger.error(f"Failed to optimize memory for conversation {conversation_id}: {e}")


# Health check endpoint for chat service
@router.get("/health")
async def chat_health_check() -> Dict[str, Any]:
    """
    Health check endpoint for chat service.
    
    Returns the status of chat service dependencies.
    """
    try:
        # Check RAG pipeline
        try:
            pipeline = await get_rag_pipeline()
            rag_status = "healthy"
        except Exception:
            rag_status = "unhealthy"
        
        # Check memory manager
        try:
            memory_manager = await get_memory_manager()
            memory_status = "healthy"
        except Exception:
            memory_status = "unhealthy"
        
        overall_status = "healthy" if rag_status == "healthy" and memory_status == "healthy" else "degraded"
        
        return {
            "status": overall_status,
            "components": {
                "rag_pipeline": rag_status,
                "memory_manager": memory_status
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }


@router.get("/diagnostics/documents")
async def get_document_diagnostics(
    user_id: Optional[str] = None,
    session: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get diagnostic information about documents and chunks for debugging RAG pipeline issues.
    
    Returns document count, chunk count, embedding status, and user_id consistency.
    """
    try:
        from sqlalchemy import select, func, and_
        from ..models.document import Document, DocumentChunk
        
        # Get document count
        doc_count_query = select(func.count(Document.id))
        if user_id:
            doc_count_query = doc_count_query.where(Document.user_id == user_id)
        
        doc_count_result = await session.execute(doc_count_query)
        document_count = doc_count_result.scalar() or 0
        
        # Get chunk count
        chunk_count_query = select(func.count(DocumentChunk.id))
        if user_id:
            chunk_count_query = (
                chunk_count_query
                .join(Document, DocumentChunk.document_id == Document.id)
                .where(Document.user_id == user_id)
            )
        
        chunk_count_result = await session.execute(chunk_count_query)
        chunk_count = chunk_count_result.scalar() or 0
        
        # Get chunks with embeddings count
        chunks_with_embeddings_query = select(func.count(DocumentChunk.id)).where(
            DocumentChunk.embedding.is_not(None)
        )
        if user_id:
            chunks_with_embeddings_query = (
                chunks_with_embeddings_query
                .join(Document, DocumentChunk.document_id == Document.id)
                .where(Document.user_id == user_id)
            )
        
        chunks_with_embeddings_result = await session.execute(chunks_with_embeddings_query)
        chunks_with_embeddings = chunks_with_embeddings_result.scalar() or 0
        
        # Get processing status breakdown
        processing_status_query = (
            select(Document.processing_status, func.count(Document.id))
            .group_by(Document.processing_status)
        )
        if user_id:
            processing_status_query = processing_status_query.where(Document.user_id == user_id)
        
        processing_status_result = await session.execute(processing_status_query)
        processing_status = dict(processing_status_result.fetchall())
        
        # Get user_id consistency check
        user_ids_query = select(Document.user_id, func.count(Document.id)).group_by(Document.user_id)
        user_ids_result = await session.execute(user_ids_query)
        user_id_distribution = dict(user_ids_result.fetchall())
        
        # Calculate embedding coverage
        chunks_without_embeddings = chunk_count - chunks_with_embeddings
        embedding_coverage = (chunks_with_embeddings / chunk_count * 100) if chunk_count > 0 else 0
        
        diagnostics = {
            "document_count": document_count,
            "chunk_count": chunk_count,
            "chunks_with_embeddings": chunks_with_embeddings,
            "chunks_without_embeddings": chunks_without_embeddings,
            "embedding_coverage_percent": round(embedding_coverage, 2),
            "processing_status_breakdown": processing_status,
            "user_id_distribution": user_id_distribution,
            "filter_user_id": user_id,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Add warnings for common issues
        warnings = []
        if document_count == 0:
            warnings.append("No documents found - users need to upload documents first")
        if chunk_count == 0 and document_count > 0:
            warnings.append("Documents exist but no chunks found - check document processing")
        if embedding_coverage < 100:
            warnings.append(f"Only {embedding_coverage:.1f}% of chunks have embeddings - check embedding generation")
        if "extraction_failed" in processing_status:
            warnings.append(f"{processing_status['extraction_failed']} documents failed text extraction")
        
        diagnostics["warnings"] = warnings
        
        logger.info(f"Document diagnostics requested for user_id={user_id}: {diagnostics}")
        
        return diagnostics
        
    except Exception as e:
        logger.error(f"Failed to get document diagnostics: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve diagnostics: {str(e)}"
        )


@router.get("/diagnostics/search")
async def test_search_pipeline(
    query: str = "test query",
    user_id: Optional[str] = None,
    max_chunks: int = 5,
    similarity_threshold: float = 0.3,
    session: AsyncSession = Depends(get_db),
    rag_pipeline: RAGPipeline = Depends(get_rag_pipeline)
) -> Dict[str, Any]:
    """
    Test the search pipeline with detailed logging and diagnostics.
    
    Helps debug issues with query embedding generation, vector search, and similarity scoring.
    """
    try:
        logger.info(
            f"Testing search pipeline: query='{query}', user_id={user_id}, "
            f"max_chunks={max_chunks}, similarity_threshold={similarity_threshold}"
        )
        
        # Test RAG request creation
        rag_request = RAGRequest(
            query=query,
            user_id=user_id,
            max_context_chunks=max_chunks,
            similarity_threshold=similarity_threshold,
            include_citations=True
        )
        
        # Test search service directly
        search_service = rag_pipeline.search_service
        
        from ..services.rag_service import QueryContext
        query_context = QueryContext(
            query_text=query,
            user_id=user_id,
            max_results=max_chunks,
            similarity_threshold=similarity_threshold
        )
        
        # Perform retrieval with detailed timing
        retrieval_result = await search_service.retrieve_context(query_context)
        
        # Prepare diagnostic response
        diagnostics = {
            "query": query,
            "user_id": user_id,
            "parameters": {
                "max_chunks": max_chunks,
                "similarity_threshold": similarity_threshold
            },
            "retrieval_results": {
                "chunks_found": retrieval_result.chunk_count,
                "documents_found": retrieval_result.document_count,
                "average_similarity": retrieval_result.average_similarity,
                "total_tokens": retrieval_result.total_tokens,
                "processing_time": retrieval_result.processing_time,
                "embedding_time": retrieval_result.embedding_time,
                "search_time": retrieval_result.search_time,
                "ranking_time": retrieval_result.ranking_time
            },
            "chunks": [
                {
                    "rank": chunk.rank,
                    "similarity_score": chunk.similarity_score,
                    "document_filename": chunk.document_filename,
                    "chunk_index": chunk.chunk_index,
                    "token_count": chunk.token_count,
                    "content_preview": chunk.content[:200] + "..." if len(chunk.content) > 200 else chunk.content
                }
                for chunk in retrieval_result.chunks
            ],
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Add warnings for common issues
        warnings = []
        if retrieval_result.chunk_count == 0:
            warnings.append("No chunks retrieved - check if documents are uploaded and processed")
        if retrieval_result.average_similarity < similarity_threshold:
            warnings.append(f"Average similarity ({retrieval_result.average_similarity:.3f}) below threshold ({similarity_threshold})")
        if retrieval_result.embedding_time > 1.0:
            warnings.append(f"Embedding generation slow ({retrieval_result.embedding_time:.2f}s)")
        if retrieval_result.search_time > 2.0:
            warnings.append(f"Vector search slow ({retrieval_result.search_time:.2f}s)")
        
        diagnostics["warnings"] = warnings
        
        logger.info(
            f"Search pipeline test completed: found {retrieval_result.chunk_count} chunks "
            f"in {retrieval_result.processing_time:.3f}s"
        )
        
        return diagnostics
        
    except Exception as e:
        logger.error(f"Search pipeline test failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search pipeline test failed: {str(e)}"
        )


@router.get("/diagnostics/embedding")
async def test_embedding_generation(
    text: str = "test embedding generation",
    session: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Test embedding generation service for debugging.
    
    Helps diagnose issues with embedding service connectivity and performance.
    """
    try:
        from ..services.embedding_service import EmbeddingService
        import time
        
        logger.info(f"Testing embedding generation for text: '{text[:50]}...'")
        
        embedding_service = EmbeddingService()
        
        start_time = time.time()
        result = await embedding_service.generate_embedding_for_text(text)
        generation_time = time.time() - start_time
        
        diagnostics = {
            "text": text,
            "text_length": len(text),
            "embedding_dimension": len(result.embedding) if result.embedding else 0,
            "generation_time": round(generation_time, 3),
            "model_info": embedding_service.get_model_info(),
            "success": result.embedding is not None,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Add performance warnings
        warnings = []
        if generation_time > 2.0:
            warnings.append(f"Embedding generation slow ({generation_time:.2f}s)")
        if not result.embedding:
            warnings.append("Embedding generation failed - check API keys and service availability")
        if len(result.embedding) != 1536:  # OpenAI text-embedding-3-small dimension
            warnings.append(f"Unexpected embedding dimension: {len(result.embedding)}")
        
        diagnostics["warnings"] = warnings
        
        logger.info(f"Embedding generation test completed in {generation_time:.3f}s")
        
        return diagnostics
        
    except Exception as e:
        logger.error(f"Embedding generation test failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Embedding generation test failed: {str(e)}"
        )



# ---------------------------------------------------------------------------
# Environment-scoped chat endpoints
# ---------------------------------------------------------------------------


class EnvStartConversationRequest(BaseModel):
    """Request to start a conversation within an environment."""

    title: Optional[str] = Field(None, max_length=255)
    system_prompt: Optional[str] = Field(None, max_length=2000)


class EnvStartConversationResponse(BaseModel):
    """Response for starting an environment-scoped conversation."""

    conversation_id: UUID
    title: str
    environment_id: UUID
    created_at: datetime
    message: str = "Conversation started successfully"


class EnvSendMessageResponse(BaseModel):
    """Response for sending a message in an environment-scoped conversation."""

    message_id: UUID
    conversation_id: UUID
    environment_id: UUID
    response: str
    sources: List[Dict[str, Any]] = []
    metadata: Dict[str, Any] = {}
    timestamp: datetime


@env_chat_router.post(
    "/{environment_id}/chat/conversations",
    response_model=EnvStartConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_env_conversation(
    environment_id: UUID,
    request: EnvStartConversationRequest,
    user_id: str = Header(..., alias="X-User-ID"),
    session: AsyncSession = Depends(get_db),
    memory_manager: HybridMemoryManager = Depends(get_memory_manager),
    _env: Environment = Depends(validate_environment_exists),
    _role: UserRole = Depends(require_environment_access),
) -> EnvStartConversationResponse:
    """Start a new conversation within an environment.

    The caller must have a role (admin or chat_user) in the environment.
    """
    try:
        conversation_id = uuid4()
        title = request.title or (
            f"Conversation {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"
        )

        conversation = Conversation(
            id=conversation_id,
            user_id=user_id,
            title=title,
            environment_id=environment_id,
        )

        session.add(conversation)
        await session.commit()
        await session.refresh(conversation)

        await memory_manager.initialize_memory(
            conversation_id=str(conversation_id),
            user_id=user_id,
            warm_cache=False,
        )

        logger.info(
            "Started env conversation %s for user %s in env %s",
            conversation_id,
            user_id,
            environment_id,
        )

        return EnvStartConversationResponse(
            conversation_id=conversation_id,
            title=title,
            environment_id=environment_id,
            created_at=conversation.created_at,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to start env conversation: %s", e)
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start conversation",
        )


@env_chat_router.post(
    "/{environment_id}/chat/conversations/{conversation_id}/messages",
    response_model=EnvSendMessageResponse,
)
async def send_env_message(
    environment_id: UUID,
    conversation_id: UUID,
    request: SendMessageRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Header(..., alias="X-User-ID"),
    session: AsyncSession = Depends(get_db),
    rag_pipeline: RAGPipeline = Depends(get_rag_pipeline),
    memory_manager: HybridMemoryManager = Depends(get_memory_manager),
    env: Environment = Depends(validate_environment_exists),
    _role: UserRole = Depends(require_environment_access),
) -> EnvSendMessageResponse:
    """Send a message in an environment-scoped conversation.

    RAG search is filtered to documents within this environment so that
    chat users can only query documents in their assigned environments
    (Req 9.5). Both admin and chat_user roles can use this endpoint
    (Req 9.3).
    """
    logger.info(
        "Env message in conv %s env %s: '%s'",
        conversation_id,
        environment_id,
        request.message[:80],
    )

    try:
        # Verify conversation exists and belongs to this environment
        conversation = await session.get(Conversation, conversation_id)
        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )
        if conversation.environment_id != environment_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Conversation does not belong to this environment",
            )

        # Create user message
        user_message_id = uuid4()
        user_message = ChatMessage(
            id=user_message_id,
            conversation_id=conversation_id,
            role="user",
            content=request.message,
            token_count=int(len(request.message.split()) * 1.3),
        )
        session.add(user_message)

        try:
            await memory_manager.add_user_message(
                conversation_id=str(conversation_id),
                message=request.message,
                user_id=conversation.user_id,
            )
        except Exception as mem_err:
            logger.warning("Memory add failed: %s", mem_err)

        # Apply environment settings as defaults
        env_settings = env.settings or {}
        rag_request = RAGRequest(
            query=request.message,
            user_id=conversation.user_id,
            conversation_id=str(conversation_id),
            max_context_chunks=request.max_context_chunks or env_settings.get("max_context_chunks", 5),
            similarity_threshold=request.similarity_threshold or env_settings.get("similarity_threshold", 0.3),
            temperature=request.temperature or env_settings.get("temperature", 0.7),
            max_tokens=request.max_tokens or env_settings.get("max_tokens"),
            include_citations=request.include_citations,
            environment_id=environment_id,
            system_prompt=env.system_prompt,
        )

        try:
            rag_response = await rag_pipeline.generate_response(rag_request)
        except Exception as rag_err:
            logger.error("RAG pipeline failed: %s", rag_err, exc_info=True)
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"RAG pipeline failed: {rag_err}",
            )

        # Create assistant message
        assistant_message_id = uuid4()
        now = datetime.utcnow()
        assistant_message = ChatMessage(
            id=assistant_message_id,
            conversation_id=conversation_id,
            role="assistant",
            content=rag_response.response,
            token_count=rag_response.response_tokens,
            created_at=now,
        )
        session.add(assistant_message)

        try:
            await memory_manager.add_ai_message(
                conversation_id=str(conversation_id),
                message=rag_response.response,
                user_id=conversation.user_id,
            )
        except Exception as mem_err:
            logger.warning("Memory add failed: %s", mem_err)

        conversation.updated_at = datetime.utcnow()

        try:
            await session.commit()
        except Exception as commit_err:
            logger.error("Commit failed: %s", commit_err, exc_info=True)
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database transaction failed",
            )

        metadata = {
            "retrieval_stats": {
                "chunks_retrieved": rag_response.retrieval_result.chunk_count,
                "documents_searched": rag_response.retrieval_result.document_count,
                "average_similarity": rag_response.retrieval_result.average_similarity,
            },
            "generation_stats": {
                "processing_time": rag_response.processing_time,
                "context_tokens": rag_response.context_tokens,
                "response_tokens": rag_response.response_tokens,
                "total_cost": rag_response.total_cost,
                "provider": rag_response.llm_response.provider,
                "model": rag_response.llm_response.model,
            },
            "environment": {
                "environment_id": str(environment_id),
            },
        }

        # Schedule background title generation on first message
        default_title = (
            conversation.title is None
            or conversation.title.startswith("Conversation ")
            or conversation.title == "New Conversation"
        )
        if default_title:
            background_tasks.add_task(
                generate_conversation_title_task,
                str(conversation_id),
                request.message,
            )

        background_tasks.add_task(
            optimize_conversation_memory,
            str(conversation_id),
            memory_manager,
        )

        return EnvSendMessageResponse(
            message_id=assistant_message_id,
            conversation_id=conversation_id,
            environment_id=environment_id,
            response=rag_response.response,
            sources=[s.to_dict() for s in rag_response.sources],
            metadata=metadata,
            timestamp=assistant_message.created_at,
        )

    except HTTPException:
        await session.rollback()
        raise
    except Exception as e:
        logger.error("Unexpected error in env message: %s", e, exc_info=True)
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process message: {e}",
        )


@env_chat_router.get(
    "/{environment_id}/chat/conversations",
    response_model=ConversationListResponse,
)
async def list_env_conversations(
    environment_id: UUID,
    page: int = 1,
    page_size: int = 20,
    user_id: str = Header(..., alias="X-User-ID"),
    session: AsyncSession = Depends(get_db),
    _env: Environment = Depends(validate_environment_exists),
    _role: UserRole = Depends(require_environment_access),
) -> ConversationListResponse:
    """List conversations for the caller within an environment."""
    from sqlalchemy import select, func, desc

    try:
        if page < 1:
            page = 1
        if page_size < 1 or page_size > 100:
            page_size = 20
        offset = (page - 1) * page_size

        count_q = (
            select(func.count(Conversation.id))
            .where(
                Conversation.user_id == user_id,
                Conversation.environment_id == environment_id,
            )
        )
        total = (await session.execute(count_q)).scalar() or 0

        conv_q = (
            select(Conversation)
            .where(
                Conversation.user_id == user_id,
                Conversation.environment_id == environment_id,
            )
            .order_by(desc(Conversation.updated_at))
            .offset(offset)
            .limit(page_size)
        )
        conversations = (await session.execute(conv_q)).scalars().all()

        summaries = []
        for conv in conversations:
            mc_q = select(func.count(ChatMessage.id)).where(
                ChatMessage.conversation_id == conv.id
            )
            message_count = (await session.execute(mc_q)).scalar() or 0

            lm_q = (
                select(ChatMessage.content)
                .where(ChatMessage.conversation_id == conv.id)
                .order_by(desc(ChatMessage.created_at))
                .limit(1)
            )
            last_msg = (await session.execute(lm_q)).scalar()
            preview = None
            if last_msg:
                preview = (
                    last_msg[:100] + "..."
                    if len(last_msg) > 100
                    else last_msg
                )

            summaries.append(
                ConversationSummary(
                    id=conv.id,
                    title=conv.title,
                    user_id=conv.user_id,
                    created_at=conv.created_at,
                    updated_at=conv.updated_at,
                    message_count=message_count,
                    last_message_preview=preview,
                )
            )

        return ConversationListResponse(
            conversations=summaries,
            total=total,
            page=page,
            page_size=page_size,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to list env conversations: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve conversations",
        )
