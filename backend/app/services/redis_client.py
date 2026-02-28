"""
Redis client for session management and caching.
"""

import json
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

import redis.asyncio as redis
from redis.asyncio import Redis

from app.core.config import settings

logger = logging.getLogger(__name__)


class RedisClient:
    """Redis client for managing conversation sessions and caching."""
    
    def __init__(self):
        self._redis: Optional[Redis] = None
        self._connection_pool: Optional[redis.ConnectionPool] = None
    
    async def connect(self) -> None:
        """Establish connection to Redis."""
        try:
            self._connection_pool = redis.ConnectionPool.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                max_connections=20
            )
            self._redis = Redis(connection_pool=self._connection_pool)
            
            # Test connection
            await self._redis.ping()
            logger.info("Successfully connected to Redis")
            
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise
    
    async def disconnect(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            logger.info("Redis connection closed")
    
    @property
    def redis(self) -> Redis:
        """Get Redis client instance."""
        if not self._redis:
            raise RuntimeError("Redis client not connected. Call connect() first.")
        return self._redis
    
    async def is_connected(self) -> bool:
        """Check if Redis is connected and responsive."""
        try:
            if not self._redis:
                return False
            await self._redis.ping()
            return True
        except Exception:
            return False


class SessionManager:
    """Manage conversation sessions in Redis with TTL."""
    
    def __init__(self, redis_client: RedisClient):
        self.redis_client = redis_client
        self.session_ttl = 3600  # 1 hour default TTL
        self.active_session_ttl = 1800  # 30 minutes for active sessions
    
    def _session_key(self, conversation_id: str) -> str:
        """Generate Redis key for session."""
        return f"session:{conversation_id}"
    
    def _messages_key(self, conversation_id: str) -> str:
        """Generate Redis key for session messages."""
        return f"messages:{conversation_id}"
    
    def _metadata_key(self, conversation_id: str) -> str:
        """Generate Redis key for session metadata."""
        return f"metadata:{conversation_id}"
    
    async def create_session(
        self, 
        conversation_id: str, 
        user_id: str,
        initial_data: Optional[Dict[str, Any]] = None
    ) -> None:
        """Create a new conversation session in Redis."""
        redis = self.redis_client.redis
        
        session_data = {
            "conversation_id": conversation_id,
            "user_id": user_id,
            "created_at": datetime.utcnow().isoformat(),
            "last_activity": datetime.utcnow().isoformat(),
            "message_count": 0,
            "total_tokens": 0,
            **(initial_data or {})
        }
        
        # Store session metadata
        await redis.hset(
            self._session_key(conversation_id),
            mapping={k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) 
                    for k, v in session_data.items()}
        )
        
        # Set TTL for session
        await redis.expire(self._session_key(conversation_id), self.session_ttl)
        
        # Initialize empty message list
        await redis.delete(self._messages_key(conversation_id))
        await redis.expire(self._messages_key(conversation_id), self.session_ttl)
        
        logger.info(f"Created session {conversation_id} for user {user_id}")
    
    async def get_session(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve session data from Redis."""
        redis = self.redis_client.redis
        
        session_data = await redis.hgetall(self._session_key(conversation_id))
        if not session_data:
            return None
        
        # Parse JSON values back to objects
        parsed_data = {}
        for key, value in session_data.items():
            try:
                parsed_data[key] = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                parsed_data[key] = value
        
        return parsed_data
    
    async def update_session_activity(self, conversation_id: str) -> None:
        """Update last activity timestamp and extend TTL."""
        redis = self.redis_client.redis
        
        await redis.hset(
            self._session_key(conversation_id),
            "last_activity",
            datetime.utcnow().isoformat()
        )
        
        # Extend TTL for active session
        await redis.expire(self._session_key(conversation_id), self.active_session_ttl)
        await redis.expire(self._messages_key(conversation_id), self.active_session_ttl)
    
    async def add_message(
        self, 
        conversation_id: str, 
        message: Dict[str, Any]
    ) -> None:
        """Add a message to the session's message list."""
        redis = self.redis_client.redis
        
        # Add timestamp if not present
        if "timestamp" not in message:
            message["timestamp"] = datetime.utcnow().isoformat()
        
        # Store message in list
        await redis.lpush(
            self._messages_key(conversation_id),
            json.dumps(message)
        )
        
        # Update session metadata
        await redis.hincrby(self._session_key(conversation_id), "message_count", 1)
        
        # Update token count if provided
        if "token_count" in message:
            await redis.hincrby(
                self._session_key(conversation_id), 
                "total_tokens", 
                message["token_count"]
            )
        
        # Update activity
        await self.update_session_activity(conversation_id)
    
    async def get_messages(
        self, 
        conversation_id: str, 
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Retrieve messages from session (most recent first)."""
        redis = self.redis_client.redis
        
        if limit:
            messages = await redis.lrange(self._messages_key(conversation_id), 0, limit - 1)
        else:
            messages = await redis.lrange(self._messages_key(conversation_id), 0, -1)
        
        # Parse JSON messages and reverse to get chronological order
        parsed_messages = []
        for msg in reversed(messages):
            try:
                parsed_messages.append(json.loads(msg))
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse message: {msg}")
                continue
        
        return parsed_messages
    
    async def get_recent_messages(
        self, 
        conversation_id: str, 
        count: int = 10
    ) -> List[Dict[str, Any]]:
        """Get the most recent N messages."""
        return await self.get_messages(conversation_id, limit=count)
    
    async def session_exists(self, conversation_id: str) -> bool:
        """Check if session exists in Redis."""
        redis = self.redis_client.redis
        return await redis.exists(self._session_key(conversation_id)) > 0
    
    async def delete_session(self, conversation_id: str) -> None:
        """Delete session and all associated data."""
        redis = self.redis_client.redis
        
        await redis.delete(
            self._session_key(conversation_id),
            self._messages_key(conversation_id),
            self._metadata_key(conversation_id)
        )
        
        logger.info(f"Deleted session {conversation_id}")
    
    async def extend_session_ttl(self, conversation_id: str, ttl: int) -> None:
        """Extend session TTL."""
        redis = self.redis_client.redis
        
        await redis.expire(self._session_key(conversation_id), ttl)
        await redis.expire(self._messages_key(conversation_id), ttl)
    
    async def get_session_stats(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """Get session statistics."""
        session = await self.get_session(conversation_id)
        if not session:
            return None
        
        redis = self.redis_client.redis
        message_count = await redis.llen(self._messages_key(conversation_id))
        ttl = await redis.ttl(self._session_key(conversation_id))
        
        return {
            "conversation_id": conversation_id,
            "user_id": session.get("user_id"),
            "created_at": session.get("created_at"),
            "last_activity": session.get("last_activity"),
            "message_count": message_count,
            "total_tokens": session.get("total_tokens", 0),
            "ttl_seconds": ttl
        }
    
    async def cleanup_expired_sessions(self) -> int:
        """Clean up expired sessions (Redis handles this automatically, but this can be used for logging)."""
        redis = self.redis_client.redis
        
        # Get all session keys
        session_keys = await redis.keys("session:*")
        expired_count = 0
        
        for key in session_keys:
            ttl = await redis.ttl(key)
            if ttl == -2:  # Key doesn't exist (expired)
                expired_count += 1
        
        if expired_count > 0:
            logger.info(f"Found {expired_count} expired sessions")
        
        return expired_count
    
    async def get_active_sessions(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all active sessions, optionally filtered by user."""
        redis = self.redis_client.redis
        
        session_keys = await redis.keys("session:*")
        active_sessions = []
        
        for key in session_keys:
            session_data = await redis.hgetall(key)
            if session_data:
                # Parse session data
                parsed_data = {}
                for k, v in session_data.items():
                    try:
                        parsed_data[k] = json.loads(v)
                    except (json.JSONDecodeError, TypeError):
                        parsed_data[k] = v
                
                # Filter by user if specified
                if user_id is None or parsed_data.get("user_id") == user_id:
                    # Add TTL info
                    ttl = await redis.ttl(key)
                    parsed_data["ttl_seconds"] = ttl
                    active_sessions.append(parsed_data)
        
        return active_sessions


# Global Redis client instance
redis_client = RedisClient()
session_manager = SessionManager(redis_client)