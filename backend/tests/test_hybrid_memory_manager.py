"""
Integration tests for hybrid memory management system.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4, UUID
from datetime import datetime, timedelta

from app.services.memory_manager import (
    HybridMemoryManager,
    get_hybrid_memory_manager,
    DatabaseMemoryStore,
    TokenCounter
)
from app.services.redis_client import SessionManager
from app.models.conversation import MessageRole, ChatMessage, Conversation


class TestHybridMemoryManager:
    """Test hybrid memory management functionality."""

    @pytest.fixture
    def mock_session_manager(self):
        """Create mock session manager."""
        return MagicMock()

    @pytest.fixture
    def hybrid_manager(self, mock_session_manager):
        """Create hybrid memory manager for testing."""
        with patch('app.services.memory_manager.ChatOpenAI'):
            return HybridMemoryManager(
                mock_session_manager,
                session_promotion_threshold=3,
                cache_warming_limit=2
            )

    def test_init(self, mock_session_manager):
        """Test hybrid memory manager initialization."""
        with patch('app.services.memory_manager.ChatOpenAI') as mock_llm:
            manager = HybridMemoryManager(
                mock_session_manager,
                max_token_limit=2000,
                session_promotion_threshold=5,
                cache_warming_limit=3
            )

            assert manager.session_manager == mock_session_manager
            assert manager.max_token_limit == 2000
            assert manager.session_promotion_threshold == 5
            assert manager.cache_warming_limit == 3
            assert len(manager._memory_cache) == 0
            mock_llm.assert_called_once()

    @pytest.mark.asyncio
    async def test_should_promote_session_true(self, hybrid_manager):
        """Test session promotion check returns True when threshold met."""
        conversation_id = "test-conv-123"

        # Mock session stats with message count above threshold
        hybrid_manager.session_manager.get_session_stats = AsyncMock(return_value={
            "message_count": 5,
            "total_tokens": 100
        })

        result = await hybrid_manager._should_promote_session(conversation_id)
        assert result is True

    @pytest.mark.asyncio
    async def test_should_promote_session_false(self, hybrid_manager):
        """Test session promotion check returns False when threshold not met."""
        conversation_id = "test-conv-123"

        # Mock session stats with message count below threshold
        hybrid_manager.session_manager.get_session_stats = AsyncMock(return_value={
            "message_count": 2,
            "total_tokens": 50
        })

        result = await hybrid_manager._should_promote_session(conversation_id)
        assert result is False

    @pytest.mark.asyncio
    async def test_should_promote_session_no_stats(self, hybrid_manager):
        """Test session promotion check returns False when no stats available."""
        conversation_id = "test-conv-123"

        hybrid_manager.session_manager.get_session_stats = AsyncMock(return_value=None)

        result = await hybrid_manager._should_promote_session(conversation_id)
        assert result is False

    @pytest.mark.asyncio
    async def test_promote_session_to_database(self, hybrid_manager):
        """Test promoting session from Redis to database."""
        conversation_id = str(uuid4())
        user_id = "test-user"

        # Mock Redis messages
        redis_messages = [
            {"role": "user", "content": "Hello", "token_count": 5},
            {"role": "assistant", "content": "Hi there", "token_count": 7},
            {"role": "user", "content": "How are you?", "token_count": 8}
        ]

        hybrid_manager.session_manager.get_messages = AsyncMock(return_value=redis_messages)
        hybrid_manager.db_store.save_conversation = AsyncMock()
        hybrid_manager.db_store.get_conversation_messages = AsyncMock(return_value=[])
        hybrid_manager.db_store.save_message = AsyncMock()
        hybrid_manager.session_manager.extend_session_ttl = AsyncMock()

        await hybrid_manager._promote_session_to_database(conversation_id, user_id)

        # Verify database operations
        hybrid_manager.db_store.save_conversation.assert_called_once()
        assert hybrid_manager.db_store.save_message.call_count == 3
        hybrid_manager.session_manager.extend_session_ttl.assert_called_once()

    @pytest.mark.asyncio
    async def test_promote_session_with_existing_messages(self, hybrid_manager):
        """Test promoting session with some messages already in database."""
        conversation_id = str(uuid4())
        user_id = "test-user"

        # Mock Redis messages (3 total)
        redis_messages = [
            {"role": "user", "content": "Hello", "token_count": 5},
            {"role": "assistant", "content": "Hi there", "token_count": 7},
            {"role": "user", "content": "How are you?", "token_count": 8}
        ]

        # Mock existing database messages (first 2)
        existing_messages = [MagicMock(), MagicMock()]

        hybrid_manager.session_manager.get_messages = AsyncMock(return_value=redis_messages)
        hybrid_manager.db_store.save_conversation = AsyncMock()
        hybrid_manager.db_store.get_conversation_messages = AsyncMock(return_value=existing_messages)
        hybrid_manager.db_store.save_message = AsyncMock()
        hybrid_manager.session_manager.extend_session_ttl = AsyncMock()

        await hybrid_manager._promote_session_to_database(conversation_id, user_id)

        # Should only save 1 new message (3rd one)
        hybrid_manager.db_store.save_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_warm_cache_for_conversation(self, hybrid_manager):
        """Test warming Redis cache from database."""
        conversation_id = str(uuid4())

        # Mock database messages
        mock_messages = [
            MagicMock(
                role="user",
                content="Hello",
                token_count=5,
                created_at=datetime.utcnow()
            ),
            MagicMock(
                role="assistant",
                content="Hi there",
                token_count=7,
                created_at=datetime.utcnow()
            )
        ]

        hybrid_manager.session_manager.session_exists = AsyncMock(return_value=False)
        hybrid_manager.db_store.get_conversation_messages = AsyncMock(return_value=mock_messages)
        hybrid_manager.db_store.conversation_exists = AsyncMock(return_value=True)
        hybrid_manager.session_manager.create_session = AsyncMock()
        hybrid_manager.session_manager.add_message = AsyncMock()
        hybrid_manager.session_manager.extend_session_ttl = AsyncMock()

        await hybrid_manager._warm_cache_for_conversation(conversation_id)

        # Verify cache warming operations
        hybrid_manager.session_manager.create_session.assert_called_once()
        assert hybrid_manager.session_manager.add_message.call_count == 2
        hybrid_manager.session_manager.extend_session_ttl.assert_called_once()

    @pytest.mark.asyncio
    async def test_warm_cache_already_exists(self, hybrid_manager):
        """Test cache warming skips if conversation already in Redis."""
        conversation_id = str(uuid4())

        hybrid_manager.session_manager.session_exists = AsyncMock(return_value=True)

        await hybrid_manager._warm_cache_for_conversation(conversation_id)

        # Should not perform any warming operations
        hybrid_manager.session_manager.session_exists.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_frequently_accessed_conversations(self, hybrid_manager):
        """Test getting frequently accessed conversations for cache warming."""
        user_id = "test-user"

        # Mock active sessions
        active_sessions = [
            {
                "conversation_id": "conv1",
                "last_activity": "2024-01-01T12:00:00",
                "message_count": 10
            },
            {
                "conversation_id": "conv2",
                "last_activity": "2024-01-01T11:00:00",
                "message_count": 5
            },
            {
                "conversation_id": "conv3",
                "last_activity": "2024-01-01T10:00:00",
                "message_count": 15
            }
        ]

        hybrid_manager.session_manager.get_active_sessions = AsyncMock(return_value=active_sessions)

        result = await hybrid_manager._get_frequently_accessed_conversations(user_id)

        # Should return conversations sorted by activity and message count
        assert len(result) == 2  # Limited by cache_warming_limit
        assert "conv1" in result  # Most recent activity
        # conv2 should be second due to more recent activity than conv3
        assert "conv2" in result

    @pytest.mark.asyncio
    async def test_initialize_memory_from_redis(self, hybrid_manager):
        """Test initializing memory from Redis session."""
        conversation_id = str(uuid4())
        user_id = "test-user"

        # Mock Redis session and messages
        redis_session = {"conversation_id": conversation_id, "user_id": user_id}
        redis_messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"}
        ]

        hybrid_manager.session_manager.get_session = AsyncMock(return_value=redis_session)
        hybrid_manager.session_manager.get_messages = AsyncMock(return_value=redis_messages)
        hybrid_manager._get_frequently_accessed_conversations = AsyncMock(return_value=[])

        memory = await hybrid_manager.initialize_memory(conversation_id, user_id)

        assert memory is not None
        hybrid_manager.session_manager.get_session.assert_called_once()
        hybrid_manager.session_manager.get_messages.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_memory_from_database(self, hybrid_manager):
        """Test initializing memory from database when not in Redis."""
        conversation_id = str(uuid4())
        user_id = "test-user"

        # Mock database messages
        mock_messages = [
            MagicMock(
                role=MessageRole.USER.value,
                content="Hello",
                token_count=5,
                created_at=datetime.utcnow()
            ),
            MagicMock(
                role=MessageRole.ASSISTANT.value,
                content="Hi there",
                token_count=7,
                created_at=datetime.utcnow()
            )
        ]

        hybrid_manager.session_manager.get_session = AsyncMock(return_value=None)
        hybrid_manager.db_store.get_conversation_messages = AsyncMock(return_value=mock_messages)
        hybrid_manager.session_manager.create_session = AsyncMock()
        hybrid_manager.session_manager.add_message = AsyncMock()
        hybrid_manager._get_frequently_accessed_conversations = AsyncMock(return_value=[])

        memory = await hybrid_manager.initialize_memory(conversation_id, user_id)

        assert memory is not None
        hybrid_manager.session_manager.create_session.assert_called_once()
        assert hybrid_manager.session_manager.add_message.call_count == 2

    @pytest.mark.asyncio
    async def test_initialize_memory_new_conversation(self, hybrid_manager):
        """Test initializing memory for new conversation."""
        conversation_id = str(uuid4())
        user_id = "test-user"

        hybrid_manager.session_manager.get_session = AsyncMock(return_value=None)
        hybrid_manager.db_store.get_conversation_messages = AsyncMock(return_value=[])
        hybrid_manager.db_store.save_conversation = AsyncMock()
        hybrid_manager.session_manager.create_session = AsyncMock()
        hybrid_manager._get_frequently_accessed_conversations = AsyncMock(return_value=[])

        memory = await hybrid_manager.initialize_memory(conversation_id, user_id)

        assert memory is not None
        hybrid_manager.db_store.save_conversation.assert_called_once()
        hybrid_manager.session_manager.create_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_memory_with_cache_warming(self, hybrid_manager):
        """Test memory initialization with cache warming."""
        conversation_id = str(uuid4())
        user_id = "test-user"

        # Mock frequent conversations
        frequent_convs = ["other-conv-1", "other-conv-2"]

        hybrid_manager.session_manager.get_session = AsyncMock(return_value=None)
        hybrid_manager.db_store.get_conversation_messages = AsyncMock(return_value=[])
        hybrid_manager.db_store.save_conversation = AsyncMock()
        hybrid_manager.session_manager.create_session = AsyncMock()
        hybrid_manager._get_frequently_accessed_conversations = AsyncMock(return_value=frequent_convs)
        hybrid_manager._warm_cache_for_conversation = AsyncMock()

        await hybrid_manager.initialize_memory(conversation_id, user_id, warm_cache=True)

        # Should warm cache for other conversations
        assert hybrid_manager._warm_cache_for_conversation.call_count == 2

    @pytest.mark.asyncio
    async def test_add_user_message_with_promotion(self, hybrid_manager):
        """Test adding user message with automatic promotion."""
        conversation_id = str(uuid4())
        user_id = "test-user"
        message = "Hello, world!"

        # Mock promotion trigger
        hybrid_manager._should_promote_session = AsyncMock(return_value=True)
        hybrid_manager._promote_session_to_database = AsyncMock()
        hybrid_manager.session_manager.add_message = AsyncMock()

        # Initialize memory first
        hybrid_manager._get_memory_instance(conversation_id)

        await hybrid_manager.add_user_message(conversation_id, message, user_id)

        hybrid_manager.session_manager.add_message.assert_called_once()
        hybrid_manager._promote_session_to_database.assert_called_once_with(conversation_id, user_id)

    @pytest.mark.asyncio
    async def test_add_ai_message_without_promotion(self, hybrid_manager):
        """Test adding AI message without promotion."""
        conversation_id = str(uuid4())
        user_id = "test-user"
        message = "Hello there!"

        # Mock no promotion needed
        hybrid_manager._should_promote_session = AsyncMock(return_value=False)
        hybrid_manager._promote_session_to_database = AsyncMock()
        hybrid_manager.session_manager.add_message = AsyncMock()

        # Initialize memory first
        hybrid_manager._get_memory_instance(conversation_id)

        await hybrid_manager.add_ai_message(conversation_id, message, user_id)

        hybrid_manager.session_manager.add_message.assert_called_once()
        hybrid_manager._promote_session_to_database.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_messages_redis_preference(self, hybrid_manager):
        """Test getting messages with Redis preference."""
        conversation_id = str(uuid4())

        redis_messages = [
            {"role": "user", "content": "Hello", "token_count": 5},
            {"role": "assistant", "content": "Hi there", "token_count": 7}
        ]

        hybrid_manager.session_manager.session_exists = AsyncMock(return_value=True)
        hybrid_manager.session_manager.get_messages = AsyncMock(return_value=redis_messages)

        result = await hybrid_manager.get_messages(conversation_id, source_preference="redis")

        assert len(result) == 2
        assert result[0]["content"] == "Hello"
        hybrid_manager.session_manager.get_messages.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_messages_database_fallback(self, hybrid_manager):
        """Test getting messages with database fallback."""
        conversation_id = str(uuid4())

        # Mock database messages
        mock_messages = [
            MagicMock(
                role="user",
                content="Hello",
                token_count=5,
                created_at=datetime.utcnow()
            )
        ]

        hybrid_manager.session_manager.session_exists = AsyncMock(return_value=False)
        hybrid_manager.db_store.get_conversation_messages = AsyncMock(return_value=mock_messages)

        result = await hybrid_manager.get_messages(conversation_id, source_preference="redis")

        assert len(result) == 1
        assert result[0]["content"] == "Hello"
        hybrid_manager.db_store.get_conversation_messages.assert_called_once()

    @pytest.mark.asyncio
    async def test_clear_memory(self, hybrid_manager):
        """Test clearing memory from hybrid storage."""
        conversation_id = str(uuid4())

        # Add to cache first
        hybrid_manager._get_memory_instance(conversation_id)
        hybrid_manager._session_stats[conversation_id] = {"test": "data"}

        hybrid_manager.session_manager.delete_session = AsyncMock()

        await hybrid_manager.clear_memory(conversation_id)

        # Verify cleanup
        hybrid_manager.session_manager.delete_session.assert_called_once()
        assert conversation_id not in hybrid_manager._memory_cache
        assert conversation_id not in hybrid_manager._session_stats

    @pytest.mark.asyncio
    async def test_get_session_info_redis_active(self, hybrid_manager):
        """Test getting session info when Redis is active."""
        conversation_id = str(uuid4())

        redis_stats = {
            "message_count": 5,
            "total_tokens": 100,
            "last_activity": "2024-01-01T12:00:00",
            "ttl_seconds": 1800
        }

        hybrid_manager.session_manager.get_session_stats = AsyncMock(return_value=redis_stats)
        hybrid_manager.db_store.conversation_exists = AsyncMock(return_value=True)

        result = await hybrid_manager.get_session_info(conversation_id)

        assert result["redis_active"] is True
        assert result["database_exists"] is True
        assert result["message_count"] == 5
        assert result["source"] == "redis"

    @pytest.mark.asyncio
    async def test_get_session_info_database_only(self, hybrid_manager):
        """Test getting session info when only in database."""
        conversation_id = str(uuid4())

        # Mock database messages
        mock_messages = [MagicMock(), MagicMock(), MagicMock()]

        hybrid_manager.session_manager.get_session_stats = AsyncMock(return_value=None)
        hybrid_manager.db_store.conversation_exists = AsyncMock(return_value=True)
        hybrid_manager.db_store.get_conversation_token_count = AsyncMock(return_value=150)
        hybrid_manager.db_store.get_conversation_messages = AsyncMock(return_value=mock_messages)

        result = await hybrid_manager.get_session_info(conversation_id)

        assert result["redis_active"] is False
        assert result["database_exists"] is True
        assert result["message_count"] == 3
        assert result["total_tokens"] == 150
        assert result["source"] == "database"

    @pytest.mark.asyncio
    async def test_force_promotion(self, hybrid_manager):
        """Test forcing session promotion."""
        conversation_id = str(uuid4())
        user_id = "test-user"

        hybrid_manager._promote_session_to_database = AsyncMock()

        result = await hybrid_manager.force_promotion(conversation_id, user_id)

        assert result is True
        hybrid_manager._promote_session_to_database.assert_called_once_with(conversation_id, user_id)

    @pytest.mark.asyncio
    async def test_force_promotion_failure(self, hybrid_manager):
        """Test force promotion failure handling."""
        conversation_id = str(uuid4())
        user_id = "test-user"

        hybrid_manager._promote_session_to_database = AsyncMock(side_effect=Exception("Database error"))

        result = await hybrid_manager.force_promotion(conversation_id, user_id)

        assert result is False

    @pytest.mark.asyncio
    async def test_cleanup_expired_sessions(self, hybrid_manager):
        """Test cleaning up expired sessions."""
        # Add some conversations to cache
        conv1 = str(uuid4())
        conv2 = str(uuid4())
        hybrid_manager._memory_cache[conv1] = MagicMock()
        hybrid_manager._memory_cache[conv2] = MagicMock()
        hybrid_manager._session_stats[conv1] = {"test": "data"}

        # Mock Redis cleanup
        hybrid_manager.session_manager.cleanup_expired_sessions = AsyncMock(return_value=2)

        # Mock session existence check (conv1 exists, conv2 doesn't)
        def mock_session_exists(conv_id):
            return conv_id == conv1

        hybrid_manager.session_manager.session_exists = AsyncMock(side_effect=mock_session_exists)

        result = await hybrid_manager.cleanup_expired_sessions()

        assert result["redis_expired"] == 2
        assert result["cache_cleaned"] == 1  # conv2 should be cleaned
        assert result["total_cleaned"] == 3

        # Verify conv2 was removed from cache
        assert conv1 in hybrid_manager._memory_cache
        assert conv2 not in hybrid_manager._memory_cache


class TestHybridMemoryManagerFailover:
    """Test failover scenarios for hybrid memory manager."""

    @pytest.fixture
    def hybrid_manager(self):
        """Create hybrid manager with mocked dependencies."""
        mock_session_manager = MagicMock()
        with patch('app.services.memory_manager.ChatOpenAI'):
            return HybridMemoryManager(mock_session_manager)

    @pytest.mark.asyncio
    async def test_redis_failure_fallback_to_database(self, hybrid_manager):
        """Test fallback to database when Redis fails."""
        conversation_id = str(uuid4())

        # Mock Redis failure
        hybrid_manager.session_manager.session_exists = AsyncMock(return_value=False)

        # Mock successful database operation
        mock_messages = [
            MagicMock(
                role=MessageRole.USER.value,
                content="Hello",
                token_count=5,
                created_at=datetime.utcnow()
            )
        ]
        hybrid_manager.db_store.get_conversation_messages = AsyncMock(return_value=mock_messages)

        # Should not raise exception and fallback to database
        result = await hybrid_manager.get_messages(conversation_id)

        assert len(result) == 1
        assert result[0]["content"] == "Hello"

    @pytest.mark.asyncio
    async def test_database_failure_graceful_handling(self, hybrid_manager):
        """Test graceful handling of database failures."""
        conversation_id = str(uuid4())
        user_id = "test-user"

        # Mock database failure
        hybrid_manager.db_store.save_conversation = AsyncMock(side_effect=Exception("Database connection failed"))

        # Should handle exception gracefully
        with pytest.raises(Exception):
            await hybrid_manager.initialize_memory(conversation_id, user_id)

    @pytest.mark.asyncio
    async def test_partial_failure_recovery(self, hybrid_manager):
        """Test recovery from partial failures."""
        conversation_id = str(uuid4())
        user_id = "test-user"
        message = "Test message"

        # Mock Redis success but promotion failure
        hybrid_manager.session_manager.add_message = AsyncMock()
        hybrid_manager._should_promote_session = AsyncMock(return_value=True)
        hybrid_manager._promote_session_to_database = AsyncMock(side_effect=Exception("Promotion failed"))

        # Initialize memory first
        hybrid_manager._get_memory_instance(conversation_id)

        # Should raise exception due to promotion failure
        with pytest.raises(Exception):
            await hybrid_manager.add_user_message(conversation_id, message, user_id)

        # But Redis operation should have succeeded
        hybrid_manager.session_manager.add_message.assert_called_once()


def test_get_hybrid_memory_manager():
    """Test getting global hybrid memory manager instance."""
    mock_session_manager = MagicMock()

    with patch('app.services.memory_manager.ChatOpenAI'):
        # First call should create instance
        manager1 = get_hybrid_memory_manager(mock_session_manager)
        assert manager1 is not None

        # Second call should return same instance
        manager2 = get_hybrid_memory_manager(mock_session_manager)
        assert manager1 is manager2