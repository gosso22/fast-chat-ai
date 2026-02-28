"""
LangChain memory integration with persistent storage.
"""

import json
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime
from uuid import UUID

import tiktoken
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_openai import ChatOpenAI
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.db.base import get_db
from app.models.conversation import Conversation, ChatMessage, MessageRole
from app.services.redis_client import SessionManager

logger = logging.getLogger(__name__)


class TokenCounter:
    """Token counting utility using tiktoken."""
    
    def __init__(self, model_name: str = "gpt-3.5-turbo"):
        """Initialize token counter with specified model."""
        try:
            self.encoding = tiktoken.encoding_for_model(model_name)
        except KeyError:
            # Fallback to cl100k_base encoding if model not found
            self.encoding = tiktoken.get_encoding("cl100k_base")
        
        self.model_name = model_name
    
    def count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        return len(self.encoding.encode(text))
    
    def count_message_tokens(self, message: Dict[str, Any]) -> int:
        """Count tokens in a message including role and content."""
        # Add tokens for role and formatting
        role_tokens = self.count_tokens(message.get("role", ""))
        content_tokens = self.count_tokens(message.get("content", ""))
        
        # Add overhead tokens for message formatting (approximate)
        overhead = 4  # Tokens for message structure
        
        return role_tokens + content_tokens + overhead
    
    def count_messages_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """Count total tokens in a list of messages."""
        return sum(self.count_message_tokens(msg) for msg in messages)


class DatabaseMemoryStore:
    """Database storage for conversation memory."""
    
    def __init__(self):
        self.token_counter = TokenCounter()
    
    async def save_conversation(
        self, 
        conversation_id: UUID, 
        user_id: str, 
        title: Optional[str] = None
    ) -> Conversation:
        """Save or update conversation in database."""
        async for session in get_db():
            try:
                # Check if conversation exists
                result = await session.execute(
                    select(Conversation).where(Conversation.id == conversation_id)
                )
                conversation = result.scalar_one_or_none()
                
                if conversation:
                    # Update existing conversation
                    conversation.updated_at = datetime.utcnow()
                    if title:
                        conversation.title = title
                else:
                    # Create new conversation
                    conversation = Conversation(
                        id=conversation_id,
                        user_id=user_id,
                        title=title or f"Conversation {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"
                    )
                    session.add(conversation)
                
                await session.commit()
                await session.refresh(conversation)
                return conversation
            finally:
                await session.close()
    
    async def save_message(
        self, 
        conversation_id: UUID, 
        role: MessageRole, 
        content: str
    ) -> ChatMessage:
        """Save a message to the database."""
        token_count = self.token_counter.count_tokens(content)
        
        async for session in get_db():
            try:
                message = ChatMessage(
                    conversation_id=conversation_id,
                    role=role.value,
                    content=content,
                    token_count=token_count
                )
                session.add(message)
                await session.commit()
                await session.refresh(message)
                return message
            finally:
                await session.close()
    
    async def get_conversation_messages(
        self, 
        conversation_id: UUID, 
        limit: Optional[int] = None
    ) -> List[ChatMessage]:
        """Retrieve messages for a conversation."""
        async for session in get_db():
            try:
                query = select(ChatMessage).where(
                    ChatMessage.conversation_id == conversation_id
                ).order_by(ChatMessage.created_at)
                
                if limit:
                    query = query.limit(limit)
                
                result = await session.execute(query)
                return result.scalars().all()
            finally:
                await session.close()
    
    async def get_recent_messages(
        self, 
        conversation_id: UUID, 
        count: int = 10
    ) -> List[ChatMessage]:
        """Get the most recent N messages."""
        async for session in get_db():
            try:
                query = select(ChatMessage).where(
                    ChatMessage.conversation_id == conversation_id
                ).order_by(ChatMessage.created_at.desc()).limit(count)
                
                result = await session.execute(query)
                messages = result.scalars().all()
                
                # Return in chronological order
                return list(reversed(messages))
            finally:
                await session.close()
    
    async def get_conversation_token_count(self, conversation_id: UUID) -> int:
        """Get total token count for a conversation."""
        async for session in get_db():
            try:
                query = select(ChatMessage.token_count).where(
                    ChatMessage.conversation_id == conversation_id
                )
                result = await session.execute(query)
                token_counts = result.scalars().all()
                return sum(token_counts)
            finally:
                await session.close()
    
    async def delete_old_messages(
        self, 
        conversation_id: UUID, 
        keep_count: int = 10
    ) -> int:
        """Delete old messages, keeping only the most recent ones."""
        async for session in get_db():
            try:
                # Get messages to delete (all except the most recent keep_count)
                subquery = select(ChatMessage.id).where(
                    ChatMessage.conversation_id == conversation_id
                ).order_by(ChatMessage.created_at.desc()).limit(keep_count)
                
                delete_query = delete(ChatMessage).where(
                    ChatMessage.conversation_id == conversation_id,
                    ChatMessage.id.not_in(subquery)
                )
                
                result = await session.execute(delete_query)
                await session.commit()
                return result.rowcount
            finally:
                await session.close()
    
    async def conversation_exists(self, conversation_id: UUID) -> bool:
        """Check if conversation exists in database."""
        async for session in get_db():
            try:
                result = await session.execute(
                    select(Conversation.id).where(Conversation.id == conversation_id)
                )
                return result.scalar_one_or_none() is not None
            finally:
                await session.close()


class ConversationMemory:
    """Custom conversation memory implementation similar to LangChain's ConversationSummaryBufferMemory."""
    
    def __init__(
        self, 
        llm: ChatOpenAI, 
        max_token_limit: int = 4000,
        return_messages: bool = True,
        human_prefix: str = "Human",
        ai_prefix: str = "Assistant"
    ):
        """Initialize conversation memory."""
        self.llm = llm
        self.max_token_limit = max_token_limit
        self.return_messages = return_messages
        self.human_prefix = human_prefix
        self.ai_prefix = ai_prefix
        
        self.messages: List[BaseMessage] = []
        self.summary: str = ""
        self.token_counter = TokenCounter()
    
    def add_user_message(self, message: str) -> None:
        """Add user message to memory."""
        self.messages.append(HumanMessage(content=message))
        self._maybe_prune()
    
    def add_ai_message(self, message: str) -> None:
        """Add AI message to memory."""
        self.messages.append(AIMessage(content=message))
        self._maybe_prune()
    
    def add_message(self, message: BaseMessage) -> None:
        """Add message to memory."""
        self.messages.append(message)
        self._maybe_prune()
    
    def _maybe_prune(self) -> None:
        """Prune messages if token limit is exceeded."""
        current_tokens = self._get_current_token_count()
        if current_tokens > self.max_token_limit:
            self.prune()
    
    def _get_current_token_count(self) -> int:
        """Get current token count of all messages."""
        total_tokens = 0
        
        # Count summary tokens if exists
        if self.summary:
            total_tokens += self.token_counter.count_tokens(self.summary)
        
        # Count message tokens
        for message in self.messages:
            total_tokens += self.token_counter.count_tokens(message.content)
        
        return total_tokens
    
    def prune(self) -> None:
        """Prune old messages by summarizing them."""
        if len(self.messages) <= 2:
            return  # Keep at least 2 messages
        
        # Take first half of messages for summarization
        messages_to_summarize = self.messages[:len(self.messages)//2]
        remaining_messages = self.messages[len(self.messages)//2:]
        
        # Create summary of old messages
        if messages_to_summarize:
            summary_text = self._create_summary(messages_to_summarize)
            
            # Combine with existing summary
            if self.summary:
                combined_summary = f"{self.summary}\n\n{summary_text}"
                self.summary = self._create_summary_from_text(combined_summary)
            else:
                self.summary = summary_text
        
        # Keep only remaining messages
        self.messages = remaining_messages
    
    def _create_summary(self, messages: List[BaseMessage]) -> str:
        """Create summary of messages using LLM."""
        if not messages:
            return ""
        
        # Format messages for summarization
        formatted_messages = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                formatted_messages.append(f"{self.human_prefix}: {msg.content}")
            elif isinstance(msg, AIMessage):
                formatted_messages.append(f"{self.ai_prefix}: {msg.content}")
        
        conversation_text = "\n".join(formatted_messages)
        
        prompt = f"""Progressively summarize the lines of conversation provided, adding onto the previous summary returning a new summary.

EXAMPLE
Current summary:
The human asks what the AI thinks of artificial intelligence. The AI thinks artificial intelligence is a force for good.

New lines of conversation:
{self.human_prefix}: Why do you think artificial intelligence is a force for good?
{self.ai_prefix}: Because artificial intelligence will help humans reach their full potential.

New summary:
The human asks what the AI thinks of artificial intelligence. The AI thinks artificial intelligence is a force for good because it will help humans reach their full potential.
END OF EXAMPLE

Current summary:
{self.summary}

New lines of conversation:
{conversation_text}

New summary:"""
        
        try:
            response = self.llm.invoke(prompt)
            return response.content.strip()
        except Exception as e:
            logger.error(f"Failed to create summary: {e}")
            # Fallback to simple truncation
            return f"Summary of {len(messages)} messages: {conversation_text[:200]}..."
    
    def _create_summary_from_text(self, text: str) -> str:
        """Create a condensed summary from existing summary text."""
        prompt = f"""Please create a concise summary of the following conversation summary:

{text}

Condensed summary:"""
        
        try:
            response = self.llm.invoke(prompt)
            return response.content.strip()
        except Exception as e:
            logger.error(f"Failed to condense summary: {e}")
            return text[:500] + "..." if len(text) > 500 else text
    
    @property
    def buffer(self) -> str:
        """Get the current buffer content (summary + recent messages)."""
        parts = []
        
        if self.summary:
            parts.append(f"Summary of conversation earlier:\n{self.summary}")
        
        if self.messages:
            parts.append("Current conversation:")
            for msg in self.messages:
                if isinstance(msg, HumanMessage):
                    parts.append(f"{self.human_prefix}: {msg.content}")
                elif isinstance(msg, AIMessage):
                    parts.append(f"{self.ai_prefix}: {msg.content}")
        
        return "\n".join(parts)
    
    def clear(self) -> None:
        """Clear all messages and summary."""
        self.messages = []
        self.summary = ""
    
    @property
    def chat_memory(self):
        """Compatibility property to mimic LangChain's interface."""
        return self


class LangChainMemoryManager:
    """LangChain memory manager with database persistence."""
    
    def __init__(
        self, 
        session_manager: SessionManager,
        max_token_limit: int = 4000,
        return_messages: bool = True
    ):
        """Initialize LangChain memory manager."""
        self.session_manager = session_manager
        self.db_store = DatabaseMemoryStore()
        self.token_counter = TokenCounter()
        self.max_token_limit = max_token_limit
        self.return_messages = return_messages
        
        # Initialize LLM for summarization
        self.llm = ChatOpenAI(
            model="gpt-3.5-turbo",
            temperature=0,
            openai_api_key=settings.OPENAI_API_KEY
        )
        
        # Cache for active memory instances
        self._memory_cache: Dict[str, ConversationMemory] = {}
    
    def _get_memory_instance(self, conversation_id: str) -> ConversationMemory:
        """Get or create memory instance for conversation."""
        if conversation_id not in self._memory_cache:
            self._memory_cache[conversation_id] = ConversationMemory(
                llm=self.llm,
                max_token_limit=self.max_token_limit,
                return_messages=self.return_messages,
                human_prefix="Human",
                ai_prefix="Assistant"
            )
        
        return self._memory_cache[conversation_id]
    
    def _convert_db_message_to_langchain(self, message: ChatMessage) -> BaseMessage:
        """Convert database message to LangChain message."""
        if message.role == MessageRole.USER.value:
            return HumanMessage(content=message.content)
        else:
            return AIMessage(content=message.content)
    
    def _convert_langchain_message_to_dict(self, message: BaseMessage) -> Dict[str, Any]:
        """Convert LangChain message to dictionary."""
        if isinstance(message, HumanMessage):
            role = MessageRole.USER.value
        elif isinstance(message, AIMessage):
            role = MessageRole.ASSISTANT.value
        else:
            role = "system"
        
        return {
            "role": role,
            "content": message.content,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    async def initialize_memory(
        self, 
        conversation_id: str, 
        user_id: str
    ) -> ConversationMemory:
        """Initialize memory for a conversation, loading from database if exists."""
        memory = self._get_memory_instance(conversation_id)
        
        try:
            conversation_uuid = UUID(conversation_id)
            
            # Load existing messages from database
            messages = await self.db_store.get_conversation_messages(conversation_uuid)
            
            if messages:
                # Add messages to memory
                for message in messages:
                    langchain_message = self._convert_db_message_to_langchain(message)
                    memory.add_message(langchain_message)
                
                logger.info(f"Loaded {len(messages)} messages for conversation {conversation_id}")
            else:
                # Ensure conversation exists in database
                await self.db_store.save_conversation(conversation_uuid, user_id)
                logger.info(f"Created new conversation {conversation_id}")
            
        except ValueError as e:
            logger.error(f"Invalid conversation ID format: {conversation_id}, error: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize memory for {conversation_id}: {e}")
            raise
        
        return memory
    
    async def add_user_message(self, conversation_id: str, message: str) -> None:
        """Add user message to memory and database."""
        try:
            conversation_uuid = UUID(conversation_id)
            memory = self._get_memory_instance(conversation_id)
            
            # Add to memory
            memory.add_user_message(message)
            
            # Save to database
            await self.db_store.save_message(
                conversation_uuid, 
                MessageRole.USER, 
                message
            )
            
            # Update Redis session
            await self.session_manager.add_message(conversation_id, {
                "role": MessageRole.USER.value,
                "content": message,
                "token_count": self.token_counter.count_tokens(message)
            })
            
            logger.debug(f"Added user message to conversation {conversation_id}")
            
        except Exception as e:
            logger.error(f"Failed to add user message to {conversation_id}: {e}")
            raise
    
    async def add_ai_message(self, conversation_id: str, message: str) -> None:
        """Add AI message to memory and database."""
        try:
            conversation_uuid = UUID(conversation_id)
            memory = self._get_memory_instance(conversation_id)
            
            # Add to memory
            memory.add_ai_message(message)
            
            # Save to database
            await self.db_store.save_message(
                conversation_uuid, 
                MessageRole.ASSISTANT, 
                message
            )
            
            # Update Redis session
            await self.session_manager.add_message(conversation_id, {
                "role": MessageRole.ASSISTANT.value,
                "content": message,
                "token_count": self.token_counter.count_tokens(message)
            })
            
            logger.debug(f"Added AI message to conversation {conversation_id}")
            
        except Exception as e:
            logger.error(f"Failed to add AI message to {conversation_id}: {e}")
            raise
    
    async def get_memory_context(
        self, 
        conversation_id: str, 
        max_tokens: Optional[int] = None
    ) -> str:
        """Get memory context for conversation."""
        try:
            memory = self._get_memory_instance(conversation_id)
            
            # Get buffer content (recent messages + summary if exists)
            context = memory.buffer
            
            # If max_tokens specified, truncate if necessary
            if max_tokens:
                token_count = self.token_counter.count_tokens(context)
                if token_count > max_tokens:
                    # Trigger summarization to reduce token count
                    memory.prune()
                    context = memory.buffer
            
            return context
            
        except Exception as e:
            logger.error(f"Failed to get memory context for {conversation_id}: {e}")
            return ""
    
    async def get_messages(
        self, 
        conversation_id: str, 
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get messages from memory."""
        try:
            memory = self._get_memory_instance(conversation_id)
            
            # Get messages from memory
            messages = memory.messages
            
            if limit:
                messages = messages[-limit:]
            
            # Convert to dictionary format
            return [self._convert_langchain_message_to_dict(msg) for msg in messages]
            
        except Exception as e:
            logger.error(f"Failed to get messages for {conversation_id}: {e}")
            return []
    
    async def clear_memory(self, conversation_id: str) -> None:
        """Clear memory for conversation."""
        try:
            if conversation_id in self._memory_cache:
                self._memory_cache[conversation_id].clear()
                del self._memory_cache[conversation_id]
            
            logger.info(f"Cleared memory for conversation {conversation_id}")
            
        except Exception as e:
            logger.error(f"Failed to clear memory for {conversation_id}: {e}")
    
    async def get_token_count(self, conversation_id: str) -> int:
        """Get current token count for conversation memory."""
        try:
            memory = self._get_memory_instance(conversation_id)
            context = memory.buffer
            return self.token_counter.count_tokens(context)
            
        except Exception as e:
            logger.error(f"Failed to get token count for {conversation_id}: {e}")
            return 0
    
    async def force_summarize(self, conversation_id: str) -> str:
        """Force summarization of conversation memory."""
        try:
            memory = self._get_memory_instance(conversation_id)
            
            # Trigger summarization
            memory.prune()
            
            # Return the summary
            return memory.summary
            
        except Exception as e:
            logger.error(f"Failed to summarize conversation {conversation_id}: {e}")
            return ""
    
    async def persist_to_database(self, conversation_id: str) -> None:
        """Persist current memory state to database."""
        try:
            conversation_uuid = UUID(conversation_id)
            memory = self._get_memory_instance(conversation_id)
            
            # Get all messages from memory
            messages = memory.messages
            
            # Get existing messages from database to avoid duplicates
            existing_messages = await self.db_store.get_conversation_messages(conversation_uuid)
            existing_count = len(existing_messages)
            
            # Only save new messages (those beyond existing count)
            new_messages = messages[existing_count:]
            
            for message in new_messages:
                role = MessageRole.USER if isinstance(message, HumanMessage) else MessageRole.ASSISTANT
                await self.db_store.save_message(
                    conversation_uuid,
                    role,
                    message.content
                )
            
            if new_messages:
                logger.info(f"Persisted {len(new_messages)} new messages for conversation {conversation_id}")
            
        except Exception as e:
            logger.error(f"Failed to persist memory for {conversation_id}: {e}")
            raise
    
    async def cleanup_old_conversations(self, days_old: int = 30) -> int:
        """Clean up old conversation memories from cache."""
        # This would typically involve checking database for old conversations
        # and removing them from the cache. For now, just clear the cache.
        cleared_count = len(self._memory_cache)
        self._memory_cache.clear()
        
        logger.info(f"Cleared {cleared_count} conversation memories from cache")
        return cleared_count


class HybridMemoryManager:
    """
    Hybrid memory management system that uses Redis for active sessions
    and PostgreSQL for persistence with automatic session promotion.
    """

    def __init__(
        self,
        session_manager: SessionManager,
        max_token_limit: int = 4000,
        session_promotion_threshold: int = 10,  # messages
        cache_warming_limit: int = 5,  # conversations
        active_session_ttl: int = 1800,  # 30 minutes
        persistent_session_ttl: int = 86400,  # 24 hours
        token_warning_threshold: float = 0.8,  # 80% of max tokens
        token_critical_threshold: float = 0.9,  # 90% of max tokens
        summarization_batch_size: int = 10,  # messages to summarize at once
        important_message_threshold: int = 50,  # tokens to consider message important
    ):
        """Initialize hybrid memory manager."""
        self.session_manager = session_manager
        self.db_store = DatabaseMemoryStore()
        self.token_counter = TokenCounter()
        self.max_token_limit = max_token_limit
        self.session_promotion_threshold = session_promotion_threshold
        self.cache_warming_limit = cache_warming_limit
        self.active_session_ttl = active_session_ttl
        self.persistent_session_ttl = persistent_session_ttl
        
        # Token management thresholds
        self.token_warning_threshold = token_warning_threshold
        self.token_critical_threshold = token_critical_threshold
        self.summarization_batch_size = summarization_batch_size
        self.important_message_threshold = important_message_threshold

        # Initialize LLM for summarization
        self.llm = ChatOpenAI(
            model="gpt-3.5-turbo",
            temperature=0,
            openai_api_key=settings.OPENAI_API_KEY
        )

        # Cache for active memory instances
        self._memory_cache: Dict[str, ConversationMemory] = {}
        self._session_stats: Dict[str, Dict[str, Any]] = {}
        
        # Token management tracking
        self._conversation_summaries: Dict[str, str] = {}
        self._last_summarization: Dict[str, datetime] = {}

    def _get_memory_instance(self, conversation_id: str) -> ConversationMemory:
        """Get or create memory instance for conversation."""
        if conversation_id not in self._memory_cache:
            self._memory_cache[conversation_id] = ConversationMemory(
                llm=self.llm,
                max_token_limit=self.max_token_limit,
                return_messages=True,
                human_prefix="Human",
                ai_prefix="Assistant"
            )
        return self._memory_cache[conversation_id]

    async def _should_promote_session(self, conversation_id: str) -> bool:
        """Check if session should be promoted from Redis to database."""
        try:
            session_stats = await self.session_manager.get_session_stats(conversation_id)
            if not session_stats:
                return False

            message_count = session_stats.get("message_count", 0)
            return message_count >= self.session_promotion_threshold

        except Exception as e:
            logger.error("Failed to check session promotion for %s: %s", conversation_id, e)
            return False

    async def _promote_session_to_database(self, conversation_id: str, user_id: str) -> None:
        """Promote active Redis session to persistent database storage."""
        try:
            conversation_uuid = UUID(conversation_id)

            # Get messages from Redis
            redis_messages = await self.session_manager.get_messages(conversation_id)

            if not redis_messages:
                logger.info("No messages to promote for conversation %s", conversation_id)
                return

            # Ensure conversation exists in database
            await self.db_store.save_conversation(conversation_uuid, user_id)

            # Get existing messages from database to avoid duplicates
            existing_messages = await self.db_store.get_conversation_messages(conversation_uuid)
            existing_count = len(existing_messages)

            # Only save new messages (those beyond existing count)
            new_messages = redis_messages[existing_count:]

            for message in new_messages:
                role = MessageRole.USER if message["role"] == "user" else MessageRole.ASSISTANT
                await self.db_store.save_message(
                    conversation_uuid,
                    role,
                    message["content"]
                )

            # Extend Redis TTL for persistent session
            await self.session_manager.extend_session_ttl(
                conversation_id,
                self.persistent_session_ttl
            )

            logger.info(
                "Promoted session %s to database with %d new messages",
                conversation_id,
                len(new_messages)
            )

        except Exception as e:
            logger.error("Failed to promote session %s to database: %s", conversation_id, e)
            raise

    async def _warm_cache_for_conversation(self, conversation_id: str) -> None:
        """Warm cache by loading conversation from database into Redis."""
        try:
            conversation_uuid = UUID(conversation_id)

            # Check if already in Redis
            if await self.session_manager.session_exists(conversation_id):
                logger.debug("Conversation %s already in Redis cache", conversation_id)
                return

            # Get messages from database
            db_messages = await self.db_store.get_conversation_messages(conversation_uuid)

            if not db_messages:
                logger.debug("No messages found in database for conversation %s", conversation_id)
                return

            # Get conversation details
            conversation_exists = await self.db_store.conversation_exists(conversation_uuid)
            if not conversation_exists:
                logger.warning("Conversation %s not found in database", conversation_id)
                return

            # Create Redis session with database messages
            session_data = {
                "source": "database_warmed",
                "warmed_at": datetime.utcnow().isoformat(),
                "message_count": len(db_messages),
                "total_tokens": sum(msg.token_count for msg in db_messages)
            }

            # Create session in Redis
            await self.session_manager.create_session(
                conversation_id,
                "unknown",  # User ID will be updated when session is accessed
                session_data
            )

            # Add messages to Redis
            for message in db_messages:
                redis_message = {
                    "role": message.role,
                    "content": message.content,
                    "token_count": message.token_count,
                    "timestamp": message.created_at.isoformat()
                }
                await self.session_manager.add_message(conversation_id, redis_message)

            # Set longer TTL for warmed cache
            await self.session_manager.extend_session_ttl(
                conversation_id,
                self.persistent_session_ttl
            )

            logger.info("Warmed cache for conversation %s with %d messages", conversation_id, len(db_messages))

        except Exception as e:
            logger.error("Failed to warm cache for conversation %s: %s", conversation_id, e)

    async def _get_frequently_accessed_conversations(self, user_id: str) -> List[str]:
        """Get list of frequently accessed conversations for cache warming."""
        try:
            # Get active sessions for user
            active_sessions = await self.session_manager.get_active_sessions(user_id)

            # Sort by last activity and message count
            sorted_sessions = sorted(
                active_sessions,
                key=lambda x: (
                    datetime.fromisoformat(x.get("last_activity", "1970-01-01T00:00:00")),
                    x.get("message_count", 0)
                ),
                reverse=True
            )

            # Return top conversations up to limit
            return [
                session["conversation_id"]
                for session in sorted_sessions[:self.cache_warming_limit]
            ]

        except Exception as e:
            logger.error("Failed to get frequently accessed conversations for user %s: %s", user_id, e)
            return []

    async def initialize_memory(
        self,
        conversation_id: str,
        user_id: str,
        warm_cache: bool = True
    ) -> ConversationMemory:
        """Initialize memory for a conversation with hybrid storage."""
        try:
            conversation_uuid = UUID(conversation_id)
            memory = self._get_memory_instance(conversation_id)

            # Check if session exists in Redis first
            redis_session = await self.session_manager.get_session(conversation_id)

            if redis_session:
                # Load from Redis
                redis_messages = await self.session_manager.get_messages(conversation_id)
                for message in redis_messages:
                    if message["role"] == "user":
                        memory.add_user_message(message["content"])
                    else:
                        memory.add_ai_message(message["content"])

                logger.info("Loaded conversation %s from Redis with %d messages", conversation_id, len(redis_messages))

            else:
                # Try to load from database
                db_messages = await self.db_store.get_conversation_messages(conversation_uuid)

                if db_messages:
                    # Load from database and warm Redis cache
                    for message in db_messages:
                        if message.role == MessageRole.USER.value:
                            memory.add_user_message(message.content)
                        else:
                            memory.add_ai_message(message.content)

                    # Create Redis session for future access
                    await self.session_manager.create_session(
                        conversation_id,
                        user_id,
                        {
                            "source": "database_loaded",
                            "loaded_at": datetime.utcnow().isoformat()
                        }
                    )

                    # Add messages to Redis
                    for message in db_messages:
                        redis_message = {
                            "role": message.role,
                            "content": message.content,
                            "token_count": message.token_count,
                            "timestamp": message.created_at.isoformat()
                        }
                        await self.session_manager.add_message(conversation_id, redis_message)

                    logger.info("Loaded conversation %s from database with %d messages", conversation_id, len(db_messages))

                else:
                    # Create new conversation
                    await self.db_store.save_conversation(conversation_uuid, user_id)
                    await self.session_manager.create_session(conversation_id, user_id)
                    logger.info("Created new conversation %s", conversation_id)

            # Warm cache for frequently accessed conversations if requested
            if warm_cache:
                frequent_conversations = await self._get_frequently_accessed_conversations(user_id)
                for conv_id in frequent_conversations:
                    if conv_id != conversation_id:  # Don't warm current conversation
                        await self._warm_cache_for_conversation(conv_id)

            return memory

        except ValueError as e:
            logger.error("Invalid conversation ID format: %s, error: %s", conversation_id, e)
            raise
        except Exception as e:
            logger.error("Failed to initialize hybrid memory for %s: %s", conversation_id, e)
            raise

    async def add_user_message(self, conversation_id: str, message: str, user_id: str) -> None:
        """Add user message with hybrid storage and automatic promotion."""
        try:
            conversation_uuid = UUID(conversation_id)
            memory = self._get_memory_instance(conversation_id)

            # Add to memory
            memory.add_user_message(message)

            # Add to Redis
            await self.session_manager.add_message(conversation_id, {
                "role": MessageRole.USER.value,
                "content": message,
                "token_count": self.token_counter.count_tokens(message)
            })

            # Check if session should be promoted to database
            if await self._should_promote_session(conversation_id):
                await self._promote_session_to_database(conversation_id, user_id)

            # Perform intelligent token management if needed
            await self.auto_manage_conversation_tokens(conversation_id)

            logger.debug("Added user message to hybrid storage for conversation %s", conversation_id)

        except Exception as e:
            logger.error("Failed to add user message to %s: %s", conversation_id, e)
            raise

    async def add_ai_message(self, conversation_id: str, message: str, user_id: str) -> None:
        """Add AI message with hybrid storage and automatic promotion."""
        try:
            conversation_uuid = UUID(conversation_id)
            memory = self._get_memory_instance(conversation_id)

            # Add to memory
            memory.add_ai_message(message)

            # Add to Redis
            await self.session_manager.add_message(conversation_id, {
                "role": MessageRole.ASSISTANT.value,
                "content": message,
                "token_count": self.token_counter.count_tokens(message)
            })

            # Check if session should be promoted to database
            if await self._should_promote_session(conversation_id):
                await self._promote_session_to_database(conversation_id, user_id)

            # Perform intelligent token management if needed
            await self.auto_manage_conversation_tokens(conversation_id)

            logger.debug("Added AI message to hybrid storage for conversation %s", conversation_id)

        except Exception as e:
            logger.error("Failed to add AI message to %s: %s", conversation_id, e)
            raise

    async def get_memory_context(
        self,
        conversation_id: str,
        max_tokens: Optional[int] = None
    ) -> str:
        """Get memory context with hybrid fallback and intelligent prioritization."""
        try:
            # Use intelligent context retrieval if max_tokens specified
            if max_tokens:
                return await self.get_prioritized_context(conversation_id, max_tokens)
            
            # Fallback to standard memory context
            memory = self._get_memory_instance(conversation_id)

            # Get buffer content (recent messages + summary if exists)
            context = memory.buffer

            # Check if token management is needed
            token_count = self.token_counter.count_tokens(context)
            if token_count > self.max_token_limit:
                # Trigger intelligent token management
                await self.intelligent_token_management(conversation_id)
                # Get updated context
                context = memory.buffer

            return context

        except Exception as e:
            logger.error("Failed to get hybrid memory context for %s: %s", conversation_id, e)
            return ""

    async def get_messages(
        self,
        conversation_id: str,
        limit: Optional[int] = None,
        source_preference: str = "redis"
    ) -> List[Dict[str, Any]]:
        """Get messages with hybrid source preference."""
        try:
            if source_preference == "redis":
                # Try Redis first
                if await self.session_manager.session_exists(conversation_id):
                    redis_messages = await self.session_manager.get_messages(conversation_id, limit)
                    if redis_messages:
                        return redis_messages

            # Fallback to database
            conversation_uuid = UUID(conversation_id)
            db_messages = await self.db_store.get_conversation_messages(conversation_uuid, limit)

            # Convert to dictionary format
            return [
                {
                    "role": msg.role,
                    "content": msg.content,
                    "token_count": msg.token_count,
                    "timestamp": msg.created_at.isoformat()
                }
                for msg in db_messages
            ]

        except Exception as e:
            logger.error("Failed to get hybrid messages for %s: %s", conversation_id, e)
            return []

    async def clear_memory(self, conversation_id: str) -> None:
        """Clear memory from both Redis and cache."""
        try:
            # Clear from Redis
            await self.session_manager.delete_session(conversation_id)

            # Clear from memory cache
            if conversation_id in self._memory_cache:
                self._memory_cache[conversation_id].clear()
                del self._memory_cache[conversation_id]

            # Clear session stats
            if conversation_id in self._session_stats:
                del self._session_stats[conversation_id]

            # Clear token management data
            if conversation_id in self._conversation_summaries:
                del self._conversation_summaries[conversation_id]
            
            if conversation_id in self._last_summarization:
                del self._last_summarization[conversation_id]

            logger.info("Cleared hybrid memory for conversation %s", conversation_id)

        except Exception as e:
            logger.error("Failed to clear hybrid memory for %s: %s", conversation_id, e)

    async def get_session_info(self, conversation_id: str) -> Dict[str, Any]:
        """Get comprehensive session information from hybrid storage."""
        try:
            info = {
                "conversation_id": conversation_id,
                "redis_active": False,
                "database_exists": False,
                "memory_cached": conversation_id in self._memory_cache,
                "message_count": 0,
                "total_tokens": 0,
                "last_activity": None,
                "source": "unknown",
                "token_management": {
                    "has_summary": conversation_id in self._conversation_summaries,
                    "last_summarization": self._last_summarization.get(conversation_id),
                    "warning_threshold": int(self.max_token_limit * self.token_warning_threshold),
                    "critical_threshold": int(self.max_token_limit * self.token_critical_threshold),
                    "needs_management": False
                }
            }

            # Check Redis
            redis_stats = await self.session_manager.get_session_stats(conversation_id)
            if redis_stats:
                info.update({
                    "redis_active": True,
                    "message_count": redis_stats.get("message_count", 0),
                    "total_tokens": redis_stats.get("total_tokens", 0),
                    "last_activity": redis_stats.get("last_activity"),
                    "ttl_seconds": redis_stats.get("ttl_seconds"),
                    "source": "redis"
                })

            # Check database
            try:
                conversation_uuid = UUID(conversation_id)
                db_exists = await self.db_store.conversation_exists(conversation_uuid)
                info["database_exists"] = db_exists

                if db_exists and not info["redis_active"]:
                    # Get database stats if not in Redis
                    db_token_count = await self.db_store.get_conversation_token_count(conversation_uuid)
                    db_messages = await self.db_store.get_conversation_messages(conversation_uuid)
                    info.update({
                        "message_count": len(db_messages),
                        "total_tokens": db_token_count,
                        "source": "database"
                    })

            except ValueError:
                pass  # Invalid UUID format

            # Add token management analysis
            total_tokens = await self._calculate_conversation_tokens(conversation_id)
            info["total_tokens"] = max(info["total_tokens"], total_tokens)  # Use the higher count
            
            info["token_management"]["needs_management"] = await self._should_trigger_summarization(conversation_id)
            info["token_management"]["is_critical"] = await self._is_critical_token_limit(conversation_id)
            
            if conversation_id in self._conversation_summaries:
                summary_tokens = self.token_counter.count_tokens(self._conversation_summaries[conversation_id])
                info["token_management"]["summary_tokens"] = summary_tokens

            return info

        except Exception as e:
            logger.error("Failed to get session info for %s: %s", conversation_id, e)
            return {"conversation_id": conversation_id, "error": str(e)}

    async def force_promotion(self, conversation_id: str, user_id: str) -> bool:
        """Force promotion of session from Redis to database."""
        try:
            await self._promote_session_to_database(conversation_id, user_id)
            return True
        except Exception as e:
            logger.error("Failed to force promotion for %s: %s", conversation_id, e)
            return False

    async def cleanup_expired_sessions(self) -> Dict[str, int]:
        """Clean up expired sessions from both Redis and memory cache."""
        try:
            # Clean up Redis (Redis handles expiration automatically)
            redis_expired = await self.session_manager.cleanup_expired_sessions()

            # Clean up memory cache for non-existent Redis sessions
            cache_cleaned = 0
            conversations_to_remove = []

            for conv_id in self._memory_cache.keys():
                if not await self.session_manager.session_exists(conv_id):
                    conversations_to_remove.append(conv_id)

            for conv_id in conversations_to_remove:
                del self._memory_cache[conv_id]
                if conv_id in self._session_stats:
                    del self._session_stats[conv_id]
                cache_cleaned += 1

            logger.info("Cleaned up %d expired Redis sessions and %d cached memories", redis_expired, cache_cleaned)

            return {
                "redis_expired": redis_expired,
                "cache_cleaned": cache_cleaned,
                "total_cleaned": redis_expired + cache_cleaned
            }

        except Exception as e:
            logger.error("Failed to cleanup expired sessions: %s", e)
            return {"error": str(e)}

    # Intelligent Token Management Methods

    async def _calculate_conversation_tokens(self, conversation_id: str) -> int:
        """Calculate total tokens for a conversation across all sources."""
        try:
            total_tokens = 0
            
            # Get tokens from Redis if available
            redis_stats = await self.session_manager.get_session_stats(conversation_id)
            if redis_stats:
                total_tokens += redis_stats.get("total_tokens", 0)
            else:
                # Fallback to database
                try:
                    conversation_uuid = UUID(conversation_id)
                    total_tokens = await self.db_store.get_conversation_token_count(conversation_uuid)
                except ValueError:
                    pass
            
            # Add summary tokens if exists
            if conversation_id in self._conversation_summaries:
                summary_tokens = self.token_counter.count_tokens(self._conversation_summaries[conversation_id])
                total_tokens += summary_tokens
            
            return total_tokens
            
        except Exception as e:
            logger.error("Failed to calculate tokens for conversation %s: %s", conversation_id, e)
            return 0

    async def _should_trigger_summarization(self, conversation_id: str) -> bool:
        """Check if conversation should be summarized based on token count."""
        try:
            total_tokens = await self._calculate_conversation_tokens(conversation_id)
            warning_threshold = int(self.max_token_limit * self.token_warning_threshold)
            
            return total_tokens >= warning_threshold
            
        except Exception as e:
            logger.error("Failed to check summarization trigger for %s: %s", conversation_id, e)
            return False

    async def _is_critical_token_limit(self, conversation_id: str) -> bool:
        """Check if conversation has reached critical token limit."""
        try:
            total_tokens = await self._calculate_conversation_tokens(conversation_id)
            critical_threshold = int(self.max_token_limit * self.token_critical_threshold)
            
            return total_tokens >= critical_threshold
            
        except Exception as e:
            logger.error("Failed to check critical token limit for %s: %s", conversation_id, e)
            return False

    async def _identify_important_messages(self, messages: List[Dict[str, Any]]) -> List[int]:
        """Identify indices of important messages that should be preserved."""
        important_indices = []
        
        for i, message in enumerate(messages):
            # Consider messages important if they:
            # 1. Have high token count (detailed responses)
            # 2. Are recent (last 3 messages)
            # 3. Contain specific keywords or patterns
            
            token_count = message.get("token_count", 0)
            is_recent = i >= len(messages) - 3
            
            # High token count indicates detailed/important content
            is_detailed = token_count >= self.important_message_threshold
            
            # Check for important keywords
            content = message.get("content", "").lower()
            important_keywords = [
                "error", "problem", "issue", "important", "critical",
                "summary", "conclusion", "result", "solution", "answer"
            ]
            contains_keywords = any(keyword in content for keyword in important_keywords)
            
            if is_recent or is_detailed or contains_keywords:
                important_indices.append(i)
        
        return important_indices

    async def _create_intelligent_summary(
        self, 
        conversation_id: str, 
        messages_to_summarize: List[Dict[str, Any]]
    ) -> str:
        """Create an intelligent summary preserving important context."""
        try:
            if not messages_to_summarize:
                return ""
            
            # Identify important messages
            important_indices = await self._identify_important_messages(messages_to_summarize)
            
            # Format messages for summarization
            formatted_messages = []
            for i, msg in enumerate(messages_to_summarize):
                role = "Human" if msg["role"] == "user" else "Assistant"
                content = msg["content"]
                
                # Mark important messages
                if i in important_indices:
                    formatted_messages.append(f"[IMPORTANT] {role}: {content}")
                else:
                    formatted_messages.append(f"{role}: {content}")
            
            conversation_text = "\n".join(formatted_messages)
            
            # Get existing summary if available
            existing_summary = self._conversation_summaries.get(conversation_id, "")
            
            prompt = f"""Create a comprehensive summary of this conversation, preserving all important context and key information. Pay special attention to messages marked as [IMPORTANT].

Guidelines:
- Preserve specific details, decisions, and conclusions
- Maintain context about problems discussed and solutions provided
- Keep track of user preferences and important facts
- Summarize routine exchanges briefly but preserve critical information
- If there's an existing summary, build upon it

Existing summary:
{existing_summary}

New conversation to summarize:
{conversation_text}

Comprehensive summary:"""
            
            response = await self.llm.ainvoke(prompt)
            summary = response.content.strip()
            
            # Store the summary
            self._conversation_summaries[conversation_id] = summary
            self._last_summarization[conversation_id] = datetime.utcnow()
            
            logger.info("Created intelligent summary for conversation %s (%d messages)", 
                       conversation_id, len(messages_to_summarize))
            
            return summary
            
        except Exception as e:
            logger.error("Failed to create intelligent summary for %s: %s", conversation_id, e)
            # Fallback to simple summary
            return f"Summary of {len(messages_to_summarize)} messages from conversation."

    async def _compress_conversation_history(self, conversation_id: str) -> Dict[str, Any]:
        """Compress conversation history by summarizing old messages."""
        try:
            compression_stats = {
                "messages_before": 0,
                "messages_after": 0,
                "tokens_before": 0,
                "tokens_after": 0,
                "summary_created": False
            }
            
            # Get messages from Redis first, fallback to database
            messages = []
            if await self.session_manager.session_exists(conversation_id):
                messages = await self.session_manager.get_messages(conversation_id)
            else:
                try:
                    conversation_uuid = UUID(conversation_id)
                    db_messages = await self.db_store.get_conversation_messages(conversation_uuid)
                    messages = [
                        {
                            "role": msg.role,
                            "content": msg.content,
                            "token_count": msg.token_count,
                            "timestamp": msg.created_at.isoformat()
                        }
                        for msg in db_messages
                    ]
                except ValueError:
                    pass
            
            if len(messages) < self.summarization_batch_size:
                logger.debug("Not enough messages to compress for conversation %s", conversation_id)
                return compression_stats
            
            compression_stats["messages_before"] = len(messages)
            compression_stats["tokens_before"] = sum(msg.get("token_count", 0) for msg in messages)
            
            # Keep recent messages, summarize older ones
            keep_count = max(5, len(messages) // 3)  # Keep at least 5 or 1/3 of messages
            messages_to_keep = messages[-keep_count:]
            messages_to_summarize = messages[:-keep_count]
            
            if messages_to_summarize:
                # Create intelligent summary
                summary = await self._create_intelligent_summary(conversation_id, messages_to_summarize)
                
                # Update Redis with compressed history
                if await self.session_manager.session_exists(conversation_id):
                    # Clear old messages and add summary + recent messages
                    await self.session_manager.delete_session(conversation_id)
                    
                    # Recreate session with summary
                    session_data = await self.session_manager.get_session(conversation_id)
                    if not session_data:
                        session_data = {"user_id": "unknown"}
                    
                    await self.session_manager.create_session(
                        conversation_id,
                        session_data.get("user_id", "unknown"),
                        {
                            "compressed_at": datetime.utcnow().isoformat(),
                            "summary": summary,
                            "original_message_count": len(messages)
                        }
                    )
                    
                    # Add recent messages back
                    for message in messages_to_keep:
                        await self.session_manager.add_message(conversation_id, message)
                
                # Update memory cache if exists
                if conversation_id in self._memory_cache:
                    memory = self._memory_cache[conversation_id]
                    memory.clear()
                    memory.summary = summary
                    
                    # Add recent messages to memory
                    for message in messages_to_keep:
                        if message["role"] == "user":
                            memory.add_user_message(message["content"])
                        else:
                            memory.add_ai_message(message["content"])
                
                compression_stats["summary_created"] = True
            
            compression_stats["messages_after"] = len(messages_to_keep)
            compression_stats["tokens_after"] = sum(msg.get("token_count", 0) for msg in messages_to_keep)
            
            # Add summary tokens
            if conversation_id in self._conversation_summaries:
                summary_tokens = self.token_counter.count_tokens(self._conversation_summaries[conversation_id])
                compression_stats["tokens_after"] += summary_tokens
            
            logger.info("Compressed conversation %s: %d->%d messages, %d->%d tokens", 
                       conversation_id, 
                       compression_stats["messages_before"],
                       compression_stats["messages_after"],
                       compression_stats["tokens_before"],
                       compression_stats["tokens_after"])
            
            return compression_stats
            
        except Exception as e:
            logger.error("Failed to compress conversation history for %s: %s", conversation_id, e)
            return compression_stats

    async def _cleanup_old_database_messages(self, conversation_id: str, keep_recent: int = 20) -> int:
        """Clean up old messages from database, keeping only recent ones."""
        try:
            conversation_uuid = UUID(conversation_id)
            
            # Delete old messages, keeping only the most recent ones
            deleted_count = await self.db_store.delete_old_messages(conversation_uuid, keep_recent)
            
            if deleted_count > 0:
                logger.info("Cleaned up %d old messages from database for conversation %s", 
                           deleted_count, conversation_id)
            
            return deleted_count
            
        except ValueError:
            logger.error("Invalid conversation ID format for cleanup: %s", conversation_id)
            return 0
        except Exception as e:
            logger.error("Failed to cleanup old database messages for %s: %s", conversation_id, e)
            return 0

    async def intelligent_token_management(self, conversation_id: str) -> Dict[str, Any]:
        """Perform intelligent token management for a conversation."""
        try:
            management_stats = {
                "conversation_id": conversation_id,
                "initial_tokens": 0,
                "final_tokens": 0,
                "action_taken": "none",
                "compression_stats": {},
                "cleanup_stats": {},
                "warning_triggered": False,
                "critical_triggered": False
            }
            
            # Calculate initial token count
            initial_tokens = await self._calculate_conversation_tokens(conversation_id)
            management_stats["initial_tokens"] = initial_tokens
            
            # Check if action is needed
            should_summarize = await self._should_trigger_summarization(conversation_id)
            is_critical = await self._is_critical_token_limit(conversation_id)
            
            management_stats["warning_triggered"] = should_summarize
            management_stats["critical_triggered"] = is_critical
            
            if is_critical:
                # Critical: Aggressive compression
                logger.warning("Critical token limit reached for conversation %s (%d tokens)", 
                              conversation_id, initial_tokens)
                
                compression_stats = await self._compress_conversation_history(conversation_id)
                management_stats["compression_stats"] = compression_stats
                management_stats["action_taken"] = "critical_compression"
                
                # Also cleanup database
                cleanup_count = await self._cleanup_old_database_messages(conversation_id, keep_recent=10)
                management_stats["cleanup_stats"] = {"deleted_messages": cleanup_count}
                
            elif should_summarize:
                # Warning: Standard compression
                logger.info("Token warning threshold reached for conversation %s (%d tokens)", 
                           conversation_id, initial_tokens)
                
                compression_stats = await self._compress_conversation_history(conversation_id)
                management_stats["compression_stats"] = compression_stats
                management_stats["action_taken"] = "standard_compression"
            
            # Calculate final token count
            final_tokens = await self._calculate_conversation_tokens(conversation_id)
            management_stats["final_tokens"] = final_tokens
            
            if management_stats["action_taken"] != "none":
                logger.info("Token management completed for %s: %d->%d tokens (%s)", 
                           conversation_id, initial_tokens, final_tokens, 
                           management_stats["action_taken"])
            
            return management_stats
            
        except Exception as e:
            logger.error("Failed intelligent token management for %s: %s", conversation_id, e)
            return {"conversation_id": conversation_id, "error": str(e)}

    async def get_prioritized_context(
        self, 
        conversation_id: str, 
        max_tokens: Optional[int] = None,
        include_summary: bool = True
    ) -> str:
        """Get conversation context prioritizing recent and important messages."""
        try:
            if max_tokens is None:
                max_tokens = self.max_token_limit
            
            context_parts = []
            current_tokens = 0
            
            # Add summary if available and requested
            if include_summary and conversation_id in self._conversation_summaries:
                summary = self._conversation_summaries[conversation_id]
                summary_tokens = self.token_counter.count_tokens(summary)
                
                if summary_tokens < max_tokens * 0.3:  # Use max 30% for summary
                    context_parts.append(f"Previous conversation summary:\n{summary}\n")
                    current_tokens += summary_tokens
            
            # Get recent messages
            messages = await self.get_messages(conversation_id, source_preference="redis")
            
            if not messages:
                return "\n".join(context_parts)
            
            # Identify important messages
            important_indices = await self._identify_important_messages(messages)
            
            # Prioritize messages: recent first, then important
            prioritized_messages = []
            
            # Add recent messages (last 5)
            recent_messages = messages[-5:]
            for i, msg in enumerate(recent_messages):
                original_index = len(messages) - 5 + i
                prioritized_messages.append((msg, original_index, "recent"))
            
            # Add important messages that aren't already included
            for idx in important_indices:
                if idx < len(messages) - 5:  # Not already in recent
                    prioritized_messages.append((messages[idx], idx, "important"))
            
            # Sort by priority (recent first, then important, then chronological)
            def priority_key(item):
                msg, idx, priority_type = item
                if priority_type == "recent":
                    return (0, idx)  # Highest priority
                elif priority_type == "important":
                    return (1, idx)  # Second priority
                else:
                    return (2, idx)  # Lowest priority
            
            prioritized_messages.sort(key=priority_key)
            
            # Add messages until token limit
            remaining_tokens = max_tokens - current_tokens
            
            for msg, idx, priority_type in prioritized_messages:
                role = "Human" if msg["role"] == "user" else "Assistant"
                content = msg["content"]
                
                # Format message
                if priority_type == "important":
                    formatted_msg = f"[Important] {role}: {content}\n"
                else:
                    formatted_msg = f"{role}: {content}\n"
                
                msg_tokens = self.token_counter.count_tokens(formatted_msg)
                
                if current_tokens + msg_tokens <= max_tokens:
                    context_parts.append(formatted_msg)
                    current_tokens += msg_tokens
                else:
                    # Try to fit a truncated version
                    if remaining_tokens > 50:  # Minimum viable message size
                        truncated_content = content[:remaining_tokens * 3]  # Rough estimate
                        truncated_msg = f"{role}: {truncated_content}...\n"
                        context_parts.append(truncated_msg)
                    break
            
            context = "\n".join(context_parts)
            
            logger.debug("Generated prioritized context for %s: %d tokens, %d messages", 
                        conversation_id, current_tokens, len(prioritized_messages))
            
            return context
            
        except Exception as e:
            logger.error("Failed to get prioritized context for %s: %s", conversation_id, e)
            return ""

    async def auto_manage_conversation_tokens(self, conversation_id: str) -> bool:
        """Automatically manage tokens for a conversation if needed."""
        try:
            # Check if management is needed
            should_manage = await self._should_trigger_summarization(conversation_id)
            
            if should_manage:
                management_stats = await self.intelligent_token_management(conversation_id)
                return management_stats.get("action_taken", "none") != "none"
            
            return False
            
        except Exception as e:
            logger.error("Failed auto token management for %s: %s", conversation_id, e)
            return False

    async def get_conversation_summary(self, conversation_id: str) -> Optional[str]:
        """Get the current summary for a conversation."""
        return self._conversation_summaries.get(conversation_id)

    async def force_conversation_summarization(self, conversation_id: str) -> str:
        """Force summarization of a conversation regardless of token count."""
        try:
            messages = await self.get_messages(conversation_id)
            if not messages:
                return ""
            
            # Summarize all messages
            summary = await self._create_intelligent_summary(conversation_id, messages)
            
            logger.info("Forced summarization completed for conversation %s", conversation_id)
            return summary
            
        except Exception as e:
            logger.error("Failed to force summarization for %s: %s", conversation_id, e)
            return ""


# Global memory manager instances
memory_manager: Optional[LangChainMemoryManager] = None
hybrid_memory_manager: Optional[HybridMemoryManager] = None


def get_memory_manager(session_manager: SessionManager) -> LangChainMemoryManager:
    """Get or create global memory manager instance."""
    global memory_manager
    if memory_manager is None:
        memory_manager = LangChainMemoryManager(session_manager)
    return memory_manager


def get_hybrid_memory_manager(session_manager: SessionManager) -> HybridMemoryManager:
    """Get or create global hybrid memory manager instance."""
    global hybrid_memory_manager
    if hybrid_memory_manager is None:
        hybrid_memory_manager = HybridMemoryManager(session_manager)
    return hybrid_memory_manager