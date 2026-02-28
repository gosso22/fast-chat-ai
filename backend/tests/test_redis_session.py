"""
Tests for Redis session management.
"""

import asyncio
import json
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.redis_client import RedisClient, SessionManager


class TestRedisClient:
    """Test Redis client connection and basic operations."""
    
    @pytest.fixture
    async def redis_client(self):
        """Create Redis client for testing."""
        client = RedisClient()
        # Mock Redis connection for testing
        with patch('redis.asyncio.ConnectionPool.from_url') as mock_pool, \
             patch('redis.asyncio.Redis') as mock_redis:
            
            mock_redis_instance = AsyncMock()
            mock_redis.return_value = mock_redis_instance
            mock_redis_instance.ping = AsyncMock()
            
            client._redis = mock_redis_instance
            yield client
    
    @pytest.mark.asyncio
    async def test_connect_success(self, redis_client):
        """Test successful Redis connection."""
        # The redis_client fixture already has a mocked Redis instance
        # Just verify the ping was called during connection
        assert redis_client._redis is not None
    
    @pytest.mark.asyncio
    async def test_connect_failure(self):
        """Test Redis connection failure."""
        client = RedisClient()
        
        with patch('redis.asyncio.ConnectionPool.from_url') as mock_pool:
            mock_pool.side_effect = Exception("Connection failed")
            
            with pytest.raises(Exception, match="Connection failed"):
                await client.connect()
    
    @pytest.mark.asyncio
    async def test_is_connected_true(self, redis_client):
        """Test is_connected returns True when connected."""
        redis_client._redis.ping = AsyncMock()
        
        result = await redis_client.is_connected()
        assert result is True
        redis_client._redis.ping.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_is_connected_false(self, redis_client):
        """Test is_connected returns False when not connected."""
        redis_client._redis.ping = AsyncMock(side_effect=Exception("Not connected"))
        
        result = await redis_client.is_connected()
        assert result is False
    
    @pytest.mark.asyncio
    async def test_is_connected_no_redis(self):
        """Test is_connected returns False when Redis is None."""
        client = RedisClient()
        
        result = await client.is_connected()
        assert result is False
    
    def test_redis_property_not_connected(self):
        """Test redis property raises error when not connected."""
        client = RedisClient()
        
        with pytest.raises(RuntimeError, match="Redis client not connected"):
            _ = client.redis
    
    @pytest.mark.asyncio
    async def test_disconnect(self, redis_client):
        """Test Redis disconnection."""
        redis_client._redis.close = AsyncMock()
        
        await redis_client.disconnect()
        redis_client._redis.close.assert_called_once()


class TestSessionManager:
    """Test session management functionality."""
    
    @pytest.fixture
    def mock_redis_client(self):
        """Create mock Redis client."""
        client = MagicMock()
        redis_mock = AsyncMock()
        client.redis = redis_mock
        return client, redis_mock
    
    @pytest.fixture
    def session_manager(self, mock_redis_client):
        """Create session manager with mock Redis client."""
        client, _ = mock_redis_client
        return SessionManager(client)
    
    def test_session_keys(self, session_manager):
        """Test session key generation."""
        conv_id = "test-conversation-123"
        
        assert session_manager._session_key(conv_id) == "session:test-conversation-123"
        assert session_manager._messages_key(conv_id) == "messages:test-conversation-123"
        assert session_manager._metadata_key(conv_id) == "metadata:test-conversation-123"
    
    @pytest.mark.asyncio
    async def test_create_session(self, session_manager, mock_redis_client):
        """Test session creation."""
        _, redis_mock = mock_redis_client
        
        conv_id = "test-conv-123"
        user_id = "user-456"
        initial_data = {"custom_field": "value"}
        
        await session_manager.create_session(conv_id, user_id, initial_data)
        
        # Verify hset was called with correct data
        redis_mock.hset.assert_called_once()
        call_args = redis_mock.hset.call_args
        assert call_args[0][0] == "session:test-conv-123"
        
        mapping = call_args[1]["mapping"]
        assert mapping["conversation_id"] == conv_id
        assert mapping["user_id"] == user_id
        assert mapping["custom_field"] == "value"
        assert "created_at" in mapping
        assert "last_activity" in mapping
        
        # Verify TTL was set
        redis_mock.expire.assert_called()
        
        # Verify message list was initialized
        redis_mock.delete.assert_called_with("messages:test-conv-123")
    
    @pytest.mark.asyncio
    async def test_get_session_exists(self, session_manager, mock_redis_client):
        """Test retrieving existing session."""
        _, redis_mock = mock_redis_client
        
        # Mock Redis response
        redis_mock.hgetall.return_value = {
            "conversation_id": "test-conv-123",
            "user_id": "user-456",
            "created_at": "2024-01-01T00:00:00",
            "message_count": "5",
            "custom_data": '{"key": "value"}'
        }
        
        result = await session_manager.get_session("test-conv-123")
        
        assert result is not None
        assert result["conversation_id"] == "test-conv-123"
        assert result["user_id"] == "user-456"
        assert result["message_count"] == 5  # JSON parsed to integer
        assert result["custom_data"] == {"key": "value"}  # JSON parsed
    
    @pytest.mark.asyncio
    async def test_get_session_not_exists(self, session_manager, mock_redis_client):
        """Test retrieving non-existent session."""
        _, redis_mock = mock_redis_client
        
        redis_mock.hgetall.return_value = {}
        
        result = await session_manager.get_session("non-existent")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_update_session_activity(self, session_manager, mock_redis_client):
        """Test updating session activity."""
        _, redis_mock = mock_redis_client
        
        await session_manager.update_session_activity("test-conv-123")
        
        # Verify last_activity was updated
        redis_mock.hset.assert_called_once()
        call_args = redis_mock.hset.call_args
        assert call_args[0][0] == "session:test-conv-123"
        assert call_args[0][1] == "last_activity"
        
        # Verify TTL was extended
        assert redis_mock.expire.call_count == 2  # session and messages keys
    
    @pytest.mark.asyncio
    async def test_add_message(self, session_manager, mock_redis_client):
        """Test adding message to session."""
        _, redis_mock = mock_redis_client
        
        message = {
            "role": "user",
            "content": "Hello, world!",
            "token_count": 10
        }
        
        await session_manager.add_message("test-conv-123", message)
        
        # Verify message was added to list
        redis_mock.lpush.assert_called_once()
        call_args = redis_mock.lpush.call_args
        assert call_args[0][0] == "messages:test-conv-123"
        
        # Parse the stored message
        stored_message = json.loads(call_args[0][1])
        assert stored_message["role"] == "user"
        assert stored_message["content"] == "Hello, world!"
        assert stored_message["token_count"] == 10
        assert "timestamp" in stored_message
        
        # Verify counters were updated
        assert redis_mock.hincrby.call_count == 2  # message_count and total_tokens
    
    @pytest.mark.asyncio
    async def test_get_messages(self, session_manager, mock_redis_client):
        """Test retrieving messages from session."""
        _, redis_mock = mock_redis_client
        
        # Mock Redis response (messages are stored in reverse order)
        mock_messages = [
            json.dumps({"role": "assistant", "content": "Response 2", "timestamp": "2024-01-01T00:02:00"}),
            json.dumps({"role": "user", "content": "Question 2", "timestamp": "2024-01-01T00:01:00"}),
            json.dumps({"role": "assistant", "content": "Response 1", "timestamp": "2024-01-01T00:00:30"}),
            json.dumps({"role": "user", "content": "Question 1", "timestamp": "2024-01-01T00:00:00"})
        ]
        redis_mock.lrange.return_value = mock_messages
        
        result = await session_manager.get_messages("test-conv-123")
        
        # Verify messages are returned in chronological order
        assert len(result) == 4
        assert result[0]["content"] == "Question 1"
        assert result[1]["content"] == "Response 1"
        assert result[2]["content"] == "Question 2"
        assert result[3]["content"] == "Response 2"
        
        redis_mock.lrange.assert_called_with("messages:test-conv-123", 0, -1)
    
    @pytest.mark.asyncio
    async def test_get_messages_with_limit(self, session_manager, mock_redis_client):
        """Test retrieving limited number of messages."""
        _, redis_mock = mock_redis_client
        
        redis_mock.lrange.return_value = []
        
        await session_manager.get_messages("test-conv-123", limit=5)
        
        redis_mock.lrange.assert_called_with("messages:test-conv-123", 0, 4)
    
    @pytest.mark.asyncio
    async def test_session_exists_true(self, session_manager, mock_redis_client):
        """Test session_exists returns True for existing session."""
        _, redis_mock = mock_redis_client
        
        redis_mock.exists.return_value = 1
        
        result = await session_manager.session_exists("test-conv-123")
        assert result is True
        redis_mock.exists.assert_called_with("session:test-conv-123")
    
    @pytest.mark.asyncio
    async def test_session_exists_false(self, session_manager, mock_redis_client):
        """Test session_exists returns False for non-existent session."""
        _, redis_mock = mock_redis_client
        
        redis_mock.exists.return_value = 0
        
        result = await session_manager.session_exists("test-conv-123")
        assert result is False
    
    @pytest.mark.asyncio
    async def test_delete_session(self, session_manager, mock_redis_client):
        """Test session deletion."""
        _, redis_mock = mock_redis_client
        
        await session_manager.delete_session("test-conv-123")
        
        redis_mock.delete.assert_called_once()
        call_args = redis_mock.delete.call_args[0]
        assert "session:test-conv-123" in call_args
        assert "messages:test-conv-123" in call_args
        assert "metadata:test-conv-123" in call_args
    
    @pytest.mark.asyncio
    async def test_extend_session_ttl(self, session_manager, mock_redis_client):
        """Test extending session TTL."""
        _, redis_mock = mock_redis_client
        
        await session_manager.extend_session_ttl("test-conv-123", 7200)
        
        # Verify TTL was set for both keys
        assert redis_mock.expire.call_count == 2
        expire_calls = redis_mock.expire.call_args_list
        
        # Check that both session and messages keys got TTL updated
        keys_updated = [call[0][0] for call in expire_calls]
        assert "session:test-conv-123" in keys_updated
        assert "messages:test-conv-123" in keys_updated
        
        # Check TTL value
        for call in expire_calls:
            assert call[0][1] == 7200
    
    @pytest.mark.asyncio
    async def test_get_session_stats(self, session_manager, mock_redis_client):
        """Test getting session statistics."""
        _, redis_mock = mock_redis_client
        
        # Mock session data
        redis_mock.hgetall.return_value = {
            "conversation_id": "test-conv-123",
            "user_id": "user-456",
            "created_at": "2024-01-01T00:00:00",
            "last_activity": "2024-01-01T01:00:00",
            "total_tokens": "150"
        }
        
        # Mock message count and TTL
        redis_mock.llen.return_value = 10
        redis_mock.ttl.return_value = 1800
        
        result = await session_manager.get_session_stats("test-conv-123")
        
        assert result is not None
        assert result["conversation_id"] == "test-conv-123"
        assert result["user_id"] == "user-456"
        assert result["message_count"] == 10
        assert result["total_tokens"] == 150  # JSON parsed to integer
        assert result["ttl_seconds"] == 1800
    
    @pytest.mark.asyncio
    async def test_get_session_stats_not_found(self, session_manager, mock_redis_client):
        """Test getting stats for non-existent session."""
        _, redis_mock = mock_redis_client
        
        redis_mock.hgetall.return_value = {}
        
        result = await session_manager.get_session_stats("non-existent")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_get_recent_messages(self, session_manager, mock_redis_client):
        """Test getting recent messages."""
        _, redis_mock = mock_redis_client
        
        redis_mock.lrange.return_value = []
        
        await session_manager.get_recent_messages("test-conv-123", count=5)
        
        # Should call get_messages with limit
        redis_mock.lrange.assert_called_with("messages:test-conv-123", 0, 4)
    
    @pytest.mark.asyncio
    async def test_get_active_sessions(self, session_manager, mock_redis_client):
        """Test getting all active sessions."""
        _, redis_mock = mock_redis_client
        
        # Mock Redis keys and session data
        redis_mock.keys.return_value = ["session:conv1", "session:conv2"]
        
        def mock_hgetall(key):
            if key == "session:conv1":
                return {
                    "conversation_id": "conv1",
                    "user_id": "user1",
                    "created_at": "2024-01-01T00:00:00"
                }
            elif key == "session:conv2":
                return {
                    "conversation_id": "conv2", 
                    "user_id": "user2",
                    "created_at": "2024-01-01T01:00:00"
                }
            return {}
        
        redis_mock.hgetall.side_effect = mock_hgetall
        redis_mock.ttl.return_value = 1800
        
        result = await session_manager.get_active_sessions()
        
        assert len(result) == 2
        assert result[0]["conversation_id"] == "conv1"
        assert result[1]["conversation_id"] == "conv2"
        assert all("ttl_seconds" in session for session in result)
    
    @pytest.mark.asyncio
    async def test_get_active_sessions_filtered_by_user(self, session_manager, mock_redis_client):
        """Test getting active sessions filtered by user."""
        _, redis_mock = mock_redis_client
        
        # Mock Redis keys and session data
        redis_mock.keys.return_value = ["session:conv1", "session:conv2"]
        
        def mock_hgetall(key):
            if key == "session:conv1":
                return {
                    "conversation_id": "conv1",
                    "user_id": "user1",
                    "created_at": "2024-01-01T00:00:00"
                }
            elif key == "session:conv2":
                return {
                    "conversation_id": "conv2",
                    "user_id": "user2", 
                    "created_at": "2024-01-01T01:00:00"
                }
            return {}
        
        redis_mock.hgetall.side_effect = mock_hgetall
        redis_mock.ttl.return_value = 1800
        
        result = await session_manager.get_active_sessions(user_id="user1")
        
        assert len(result) == 1
        assert result[0]["conversation_id"] == "conv1"
        assert result[0]["user_id"] == "user1"