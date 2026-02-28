"""
Tests for LangChain memory manager integration.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4, UUID
from datetime import datetime

from app.services.memory_manager import (
    TokenCounter, 
    DatabaseMemoryStore, 
    LangChainMemoryManager,
    get_memory_manager
)
from app.services.redis_client import SessionManager
from app.models.conversation import MessageRole, ChatMessage, Conversation


class TestTokenCounter:
    """Test token counting functionality."""
    
    def test_init_with_valid_model(self):
        """Test initialization with valid model."""
        counter = TokenCounter("gpt-3.5-turbo")
        assert counter.model_name == "gpt-3.5-turbo"
        assert counter.encoding is not None
    
    def test_init_with_invalid_model(self):
        """Test initialization with invalid model falls back to default."""
        counter = TokenCounter("invalid-model")
        assert counter.model_name == "invalid-model"
        assert counter.encoding is not None
    
    def test_count_tokens(self):
        """Test token counting for text."""
        counter = TokenCounter()
        
        # Test simple text
        count = counter.count_tokens("Hello world")
        assert isinstance(count, int)
        assert count > 0
        
        # Test empty text
        assert counter.count_tokens("") == 0
        
        # Test longer text has more tokens
        short_count = counter.count_tokens("Hi")
        long_count = counter.count_tokens("This is a much longer sentence with many more words")
        assert long_count > short_count
    
    def test_count_message_tokens(self):
        """Test token counting for messages."""
        counter = TokenCounter()
        
        message = {
            "role": "user",
            "content": "Hello, how are you?"
        }
        
        count = counter.count_message_tokens(message)
        assert isinstance(count, int)
        assert count > 0
        
        # Should include overhead for message structure
        content_only = counter.count_tokens(message["content"])
        assert count > content_only
    
    def test_count_messages_tokens(self):
        """Test token counting for multiple messages."""
        counter = TokenCounter()
        
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "How are you?"}
        ]
        
        total_count = counter.count_messages_tokens(messages)
        individual_sum = sum(counter.count_message_tokens(msg) for msg in messages)
        
        assert total_count == individual_sum
        assert total_count > 0


class TestDatabaseMemoryStore:
    """Test database memory store functionality."""
    
    @pytest.fixture
    def memory_store(self):
        """Create memory store for testing."""
        return DatabaseMemoryStore()
    
    @pytest.fixture
    def mock_session(self):
        """Create mock database session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        session.add = MagicMock()
        return session
    
    @pytest.mark.asyncio
    async def test_save_new_conversation(self, memory_store, mock_session):
        """Test saving new conversation."""
        conversation_id = uuid4()
        user_id = "test-user"
        title = "Test Conversation"
        
        # Mock database query to return None (conversation doesn't exist)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        
        with patch('app.services.memory_manager.get_async_session') as mock_get_session:
            mock_get_session.return_value.__aenter__.return_value = mock_session
            
            result = await memory_store.save_conversation(conversation_id, user_id, title)
            
            # Verify session operations
            mock_session.execute.assert_called_once()
            mock_session.add.assert_called_once()
            mock_session.commit.assert_called_once()
            mock_session.refresh.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_save_existing_conversation(self, memory_store, mock_session):
        """Test updating existing conversation."""
        conversation_id = uuid4()
        user_id = "test-user"
        title = "Updated Title"
        
        # Mock existing conversation
        existing_conversation = MagicMock()
        existing_conversation.id = conversation_id
        existing_conversation.title = "Old Title"
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_conversation
        mock_session.execute.return_value = mock_result
        
        with patch('app.services.memory_manager.get_async_session') as mock_get_session:
            mock_get_session.return_value.__aenter__.return_value = mock_session
            
            result = await memory_store.save_conversation(conversation_id, user_id, title)
            
            # Verify conversation was updated
            assert existing_conversation.title == title
            mock_session.commit.assert_called_once()
            mock_session.refresh.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_save_message(self, memory_store, mock_session):
        """Test saving message to database."""
        conversation_id = uuid4()
        role = MessageRole.USER
        content = "Test message"
        
        with patch('app.services.memory_manager.get_async_session') as mock_get_session:
            mock_get_session.return_value.__aenter__.return_value = mock_session
            
            result = await memory_store.save_message(conversation_id, role, content)
            
            # Verify message was added
            mock_session.add.assert_called_once()
            mock_session.commit.assert_called_once()
            mock_session.refresh.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_conversation_messages(self, memory_store, mock_session):
        """Test retrieving conversation messages."""
        conversation_id = uuid4()
        
        # Mock messages
        mock_messages = [
            MagicMock(content="Message 1", role="user"),
            MagicMock(content="Message 2", role="assistant")
        ]
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_messages
        mock_session.execute.return_value = mock_result
        
        with patch('app.services.memory_manager.get_async_session') as mock_get_session:
            mock_get_session.return_value.__aenter__.return_value = mock_session
            
            result = await memory_store.get_conversation_messages(conversation_id)
            
            assert len(result) == 2
            mock_session.execute.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_recent_messages(self, memory_store, mock_session):
        """Test retrieving recent messages."""
        conversation_id = uuid4()
        count = 5
        
        # Mock messages (in reverse order as they come from DB)
        mock_messages = [
            MagicMock(content="Message 3", role="user"),
            MagicMock(content="Message 2", role="assistant"),
            MagicMock(content="Message 1", role="user")
        ]
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_messages
        mock_session.execute.return_value = mock_result
        
        with patch('app.services.memory_manager.get_async_session') as mock_get_session:
            mock_get_session.return_value.__aenter__.return_value = mock_session
            
            result = await memory_store.get_recent_messages(conversation_id, count)
            
            # Should return messages in chronological order (reversed)
            assert len(result) == 3
            assert result[0].content == "Message 1"
            assert result[2].content == "Message 3"
    
    @pytest.mark.asyncio
    async def test_get_conversation_token_count(self, memory_store, mock_session):
        """Test getting total token count for conversation."""
        conversation_id = uuid4()
        
        # Mock token counts
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [10, 15, 20]
        mock_session.execute.return_value = mock_result
        
        with patch('app.services.memory_manager.get_async_session') as mock_get_session:
            mock_get_session.return_value.__aenter__.return_value = mock_session
            
            result = await memory_store.get_conversation_token_count(conversation_id)
            
            assert result == 45  # Sum of token counts
    
    @pytest.mark.asyncio
    async def test_conversation_exists_true(self, memory_store, mock_session):
        """Test conversation exists check returns True."""
        conversation_id = uuid4()
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = conversation_id
        mock_session.execute.return_value = mock_result
        
        with patch('app.services.memory_manager.get_async_session') as mock_get_session:
            mock_get_session.return_value.__aenter__.return_value = mock_session
            
            result = await memory_store.conversation_exists(conversation_id)
            assert result is True
    
    @pytest.mark.asyncio
    async def test_conversation_exists_false(self, memory_store, mock_session):
        """Test conversation exists check returns False."""
        conversation_id = uuid4()
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        
        with patch('app.services.memory_manager.get_async_session') as mock_get_session:
            mock_get_session.return_value.__aenter__.return_value = mock_session
            
            result = await memory_store.conversation_exists(conversation_id)
            assert result is False


class TestLangChainMemoryManager:
    """Test LangChain memory manager functionality."""
    
    @pytest.fixture
    def mock_session_manager(self):
        """Create mock session manager."""
        return MagicMock()
    
    @pytest.fixture
    def memory_manager(self, mock_session_manager):
        """Create memory manager for testing."""
        with patch('app.services.memory_manager.ChatOpenAI'):
            return LangChainMemoryManager(mock_session_manager)
    
    def test_init(self, mock_session_manager):
        """Test memory manager initialization."""
        with patch('app.services.memory_manager.ChatOpenAI') as mock_llm:
            manager = LangChainMemoryManager(mock_session_manager, max_token_limit=2000)
            
            assert manager.session_manager == mock_session_manager
            assert manager.max_token_limit == 2000
            assert manager.return_messages is True
            assert len(manager._memory_cache) == 0
            mock_llm.assert_called_once()
    
    def test_get_memory_instance(self, memory_manager):
        """Test getting memory instance for conversation."""
        conversation_id = "test-conv-123"
        
        # First call should create new instance
        memory1 = memory_manager._get_memory_instance(conversation_id)
        assert memory1 is not None
        assert conversation_id in memory_manager._memory_cache
        
        # Second call should return same instance
        memory2 = memory_manager._get_memory_instance(conversation_id)
        assert memory1 is memory2
    
    def test_convert_db_message_to_langchain(self, memory_manager):
        """Test converting database message to LangChain format."""
        # Test user message
        user_message = MagicMock()
        user_message.role = MessageRole.USER.value
        user_message.content = "Hello"
        
        langchain_msg = memory_manager._convert_db_message_to_langchain(user_message)
        assert langchain_msg.content == "Hello"
        
        # Test assistant message
        ai_message = MagicMock()
        ai_message.role = MessageRole.ASSISTANT.value
        ai_message.content = "Hi there"
        
        langchain_msg = memory_manager._convert_db_message_to_langchain(ai_message)
        assert langchain_msg.content == "Hi there"
    
    def test_convert_langchain_message_to_dict(self, memory_manager):
        """Test converting LangChain message to dictionary."""
        from langchain_core.messages import HumanMessage, AIMessage
        
        # Test human message
        human_msg = HumanMessage(content="Hello")
        result = memory_manager._convert_langchain_message_to_dict(human_msg)
        
        assert result["role"] == MessageRole.USER.value
        assert result["content"] == "Hello"
        assert "timestamp" in result
        
        # Test AI message
        ai_msg = AIMessage(content="Hi there")
        result = memory_manager._convert_langchain_message_to_dict(ai_msg)
        
        assert result["role"] == MessageRole.ASSISTANT.value
        assert result["content"] == "Hi there"
    
    @pytest.mark.asyncio
    async def test_initialize_memory_new_conversation(self, memory_manager):
        """Test initializing memory for new conversation."""
        conversation_id = str(uuid4())
        user_id = "test-user"
        
        # Mock database store
        memory_manager.db_store.get_conversation_messages = AsyncMock(return_value=[])
        memory_manager.db_store.save_conversation = AsyncMock()
        
        result = await memory_manager.initialize_memory(conversation_id, user_id)
        
        assert result is not None
        memory_manager.db_store.get_conversation_messages.assert_called_once()
        memory_manager.db_store.save_conversation.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_initialize_memory_existing_conversation(self, memory_manager):
        """Test initializing memory for existing conversation."""
        conversation_id = str(uuid4())
        user_id = "test-user"
        
        # Mock existing messages
        mock_messages = [
            MagicMock(role=MessageRole.USER.value, content="Hello"),
            MagicMock(role=MessageRole.ASSISTANT.value, content="Hi there")
        ]
        
        memory_manager.db_store.get_conversation_messages = AsyncMock(return_value=mock_messages)
        
        result = await memory_manager.initialize_memory(conversation_id, user_id)
        
        assert result is not None
        memory_manager.db_store.get_conversation_messages.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_initialize_memory_invalid_uuid(self, memory_manager):
        """Test initializing memory with invalid UUID."""
        conversation_id = "invalid-uuid"
        user_id = "test-user"
        
        with pytest.raises(ValueError):
            await memory_manager.initialize_memory(conversation_id, user_id)
    
    @pytest.mark.asyncio
    async def test_add_user_message(self, memory_manager):
        """Test adding user message."""
        conversation_id = str(uuid4())
        message = "Hello, world!"
        
        # Mock dependencies
        memory_manager.db_store.save_message = AsyncMock()
        memory_manager.session_manager.add_message = AsyncMock()
        
        # Initialize memory first
        memory_manager._get_memory_instance(conversation_id)
        
        await memory_manager.add_user_message(conversation_id, message)
        
        memory_manager.db_store.save_message.assert_called_once()
        memory_manager.session_manager.add_message.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_add_ai_message(self, memory_manager):
        """Test adding AI message."""
        conversation_id = str(uuid4())
        message = "Hello there!"
        
        # Mock dependencies
        memory_manager.db_store.save_message = AsyncMock()
        memory_manager.session_manager.add_message = AsyncMock()
        
        # Initialize memory first
        memory_manager._get_memory_instance(conversation_id)
        
        await memory_manager.add_ai_message(conversation_id, message)
        
        memory_manager.db_store.save_message.assert_called_once()
        memory_manager.session_manager.add_message.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_memory_context(self, memory_manager):
        """Test getting memory context."""
        conversation_id = str(uuid4())
        
        # Initialize memory and add some messages to create context
        memory = memory_manager._get_memory_instance(conversation_id)
        memory.add_user_message("Hello")
        memory.add_ai_message("Hi there")
        
        result = await memory_manager.get_memory_context(conversation_id)
        
        assert "Hello" in result
        assert "Hi there" in result
    
    @pytest.mark.asyncio
    async def test_get_memory_context_with_token_limit(self, memory_manager):
        """Test getting memory context with token limit."""
        conversation_id = str(uuid4())
        
        # Initialize memory and add messages
        memory = memory_manager._get_memory_instance(conversation_id)
        memory.add_user_message("Hello")
        memory.add_ai_message("Hi there")
        
        # Mock token counter to return high count initially, then lower after pruning
        memory_manager.token_counter.count_tokens = MagicMock(side_effect=[1000, 500])
        
        # Mock the prune method
        memory.prune = MagicMock()
        
        result = await memory_manager.get_memory_context(conversation_id, max_tokens=800)
        
        # Should trigger pruning due to high token count
        memory.prune.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_messages(self, memory_manager):
        """Test getting messages from memory."""
        from langchain_core.messages import HumanMessage, AIMessage
        
        conversation_id = str(uuid4())
        
        # Initialize memory and add messages
        memory = memory_manager._get_memory_instance(conversation_id)
        memory.chat_memory.messages = [
            HumanMessage(content="Hello"),
            AIMessage(content="Hi there")
        ]
        
        result = await memory_manager.get_messages(conversation_id)
        
        assert len(result) == 2
        assert result[0]["role"] == MessageRole.USER.value
        assert result[0]["content"] == "Hello"
        assert result[1]["role"] == MessageRole.ASSISTANT.value
        assert result[1]["content"] == "Hi there"
    
    @pytest.mark.asyncio
    async def test_get_messages_with_limit(self, memory_manager):
        """Test getting messages with limit."""
        from langchain_core.messages import HumanMessage, AIMessage
        
        conversation_id = str(uuid4())
        
        # Initialize memory and add messages
        memory = memory_manager._get_memory_instance(conversation_id)
        memory.chat_memory.messages = [
            HumanMessage(content="Message 1"),
            AIMessage(content="Response 1"),
            HumanMessage(content="Message 2"),
            AIMessage(content="Response 2")
        ]
        
        result = await memory_manager.get_messages(conversation_id, limit=2)
        
        # Should return last 2 messages
        assert len(result) == 2
        assert result[0]["content"] == "Message 2"
        assert result[1]["content"] == "Response 2"
    
    @pytest.mark.asyncio
    async def test_clear_memory(self, memory_manager):
        """Test clearing memory for conversation."""
        conversation_id = str(uuid4())
        
        # Initialize memory
        memory_manager._get_memory_instance(conversation_id)
        assert conversation_id in memory_manager._memory_cache
        
        await memory_manager.clear_memory(conversation_id)
        
        assert conversation_id not in memory_manager._memory_cache
    
    @pytest.mark.asyncio
    async def test_get_token_count(self, memory_manager):
        """Test getting token count for conversation."""
        conversation_id = str(uuid4())
        
        # Initialize memory and add messages
        memory = memory_manager._get_memory_instance(conversation_id)
        memory.add_user_message("Hello")
        memory.add_ai_message("Hi there")
        
        # Mock token counter
        memory_manager.token_counter.count_tokens = MagicMock(return_value=50)
        
        result = await memory_manager.get_token_count(conversation_id)
        
        assert result == 50
        memory_manager.token_counter.count_tokens.assert_called()
    
    @pytest.mark.asyncio
    async def test_force_summarize(self, memory_manager):
        """Test forcing summarization of conversation."""
        conversation_id = str(uuid4())
        
        # Initialize memory and add messages
        memory = memory_manager._get_memory_instance(conversation_id)
        memory.add_user_message("Hello")
        memory.add_ai_message("Hi there")
        
        # Mock the prune method and set a summary
        memory.prune = MagicMock()
        memory.summary = "Summary of conversation"
        
        result = await memory_manager.force_summarize(conversation_id)
        
        memory.prune.assert_called_once()
        assert result == "Summary of conversation"
    
    @pytest.mark.asyncio
    async def test_persist_to_database(self, memory_manager):
        """Test persisting memory to database."""
        from langchain_core.messages import HumanMessage, AIMessage
        
        conversation_id = str(uuid4())
        
        # Initialize memory with messages
        memory = memory_manager._get_memory_instance(conversation_id)
        memory.chat_memory.messages = [
            HumanMessage(content="Hello"),
            AIMessage(content="Hi there")
        ]
        
        # Mock database operations
        memory_manager.db_store.get_conversation_messages = AsyncMock(return_value=[])
        memory_manager.db_store.save_message = AsyncMock()
        
        await memory_manager.persist_to_database(conversation_id)
        
        # Should save both messages
        assert memory_manager.db_store.save_message.call_count == 2
    
    @pytest.mark.asyncio
    async def test_persist_to_database_with_existing_messages(self, memory_manager):
        """Test persisting memory with existing messages in database."""
        from langchain_core.messages import HumanMessage, AIMessage
        
        conversation_id = str(uuid4())
        
        # Initialize memory with messages
        memory = memory_manager._get_memory_instance(conversation_id)
        memory.chat_memory.messages = [
            HumanMessage(content="Hello"),
            AIMessage(content="Hi there"),
            HumanMessage(content="How are you?")
        ]
        
        # Mock existing messages (first 2)
        existing_messages = [MagicMock(), MagicMock()]
        memory_manager.db_store.get_conversation_messages = AsyncMock(return_value=existing_messages)
        memory_manager.db_store.save_message = AsyncMock()
        
        await memory_manager.persist_to_database(conversation_id)
        
        # Should only save the new message (3rd one)
        memory_manager.db_store.save_message.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_cleanup_old_conversations(self, memory_manager):
        """Test cleaning up old conversations."""
        # Add some conversations to cache
        memory_manager._memory_cache["conv1"] = MagicMock()
        memory_manager._memory_cache["conv2"] = MagicMock()
        
        result = await memory_manager.cleanup_old_conversations()
        
        assert result == 2
        assert len(memory_manager._memory_cache) == 0


def test_get_memory_manager():
    """Test getting global memory manager instance."""
    mock_session_manager = MagicMock()
    
    with patch('app.services.memory_manager.ChatOpenAI'):
        # First call should create instance
        manager1 = get_memory_manager(mock_session_manager)
        assert manager1 is not None
        
        # Second call should return same instance
        manager2 = get_memory_manager(mock_session_manager)
        assert manager1 is manager2