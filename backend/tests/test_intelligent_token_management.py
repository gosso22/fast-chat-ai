"""
Tests for intelligent token management functionality.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4, UUID
from datetime import datetime, timedelta

from app.services.memory_manager import (
    HybridMemoryManager,
    TokenCounter,
    DatabaseMemoryStore
)
from app.services.redis_client import SessionManager
from app.models.conversation import MessageRole


class TestIntelligentTokenManagement:
    """Test intelligent token management functionality."""

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
                max_token_limit=1000,  # Lower limit for easier testing
                token_warning_threshold=0.8,  # 800 tokens
                token_critical_threshold=0.9,  # 900 tokens
                important_message_threshold=30
            )

    @pytest.mark.asyncio
    async def test_calculate_conversation_tokens_redis(self, hybrid_manager):
        """Test calculating tokens from Redis session."""
        conversation_id = "test-conv-123"
        
        # Mock Redis stats
        hybrid_manager.session_manager.get_session_stats = AsyncMock(return_value={
            "total_tokens": 500
        })
        
        # Add a summary
        hybrid_manager._conversation_summaries[conversation_id] = "This is a test summary"
        hybrid_manager.token_counter.count_tokens = MagicMock(return_value=20)
        
        result = await hybrid_manager._calculate_conversation_tokens(conversation_id)
        
        assert result == 520  # 500 + 20 for summary

    @pytest.mark.asyncio
    async def test_calculate_conversation_tokens_database_fallback(self, hybrid_manager):
        """Test calculating tokens with database fallback."""
        conversation_id = str(uuid4())
        
        # Mock Redis returning None (not found)
        hybrid_manager.session_manager.get_session_stats = AsyncMock(return_value=None)
        
        # Mock database token count
        hybrid_manager.db_store.get_conversation_token_count = AsyncMock(return_value=300)
        
        result = await hybrid_manager._calculate_conversation_tokens(conversation_id)
        
        assert result == 300

    @pytest.mark.asyncio
    async def test_should_trigger_summarization_true(self, hybrid_manager):
        """Test summarization trigger returns True when threshold exceeded."""
        conversation_id = "test-conv-123"
        
        # Mock token count above warning threshold (800)
        hybrid_manager._calculate_conversation_tokens = AsyncMock(return_value=850)
        
        result = await hybrid_manager._should_trigger_summarization(conversation_id)
        
        assert result is True

    @pytest.mark.asyncio
    async def test_should_trigger_summarization_false(self, hybrid_manager):
        """Test summarization trigger returns False when below threshold."""
        conversation_id = "test-conv-123"
        
        # Mock token count below warning threshold (800)
        hybrid_manager._calculate_conversation_tokens = AsyncMock(return_value=700)
        
        result = await hybrid_manager._should_trigger_summarization(conversation_id)
        
        assert result is False

    @pytest.mark.asyncio
    async def test_is_critical_token_limit_true(self, hybrid_manager):
        """Test critical limit check returns True when exceeded."""
        conversation_id = "test-conv-123"
        
        # Mock token count above critical threshold (900)
        hybrid_manager._calculate_conversation_tokens = AsyncMock(return_value=950)
        
        result = await hybrid_manager._is_critical_token_limit(conversation_id)
        
        assert result is True

    @pytest.mark.asyncio
    async def test_is_critical_token_limit_false(self, hybrid_manager):
        """Test critical limit check returns False when below threshold."""
        conversation_id = "test-conv-123"
        
        # Mock token count below critical threshold (900)
        hybrid_manager._calculate_conversation_tokens = AsyncMock(return_value=850)
        
        result = await hybrid_manager._is_critical_token_limit(conversation_id)
        
        assert result is False

    @pytest.mark.asyncio
    async def test_identify_important_messages(self, hybrid_manager):
        """Test identification of important messages."""
        messages = [
            {"role": "user", "content": "Hello", "token_count": 5},
            {"role": "assistant", "content": "This is a very detailed response with lots of important information that should be preserved", "token_count": 50},
            {"role": "user", "content": "I have an error in my code", "token_count": 10},
            {"role": "assistant", "content": "Short reply", "token_count": 8},
            {"role": "user", "content": "Recent message 1", "token_count": 12},
            {"role": "assistant", "content": "Recent message 2", "token_count": 15},
            {"role": "user", "content": "Most recent message", "token_count": 10}
        ]
        
        important_indices = await hybrid_manager._identify_important_messages(messages)
        
        # Should identify:
        # - Index 1: High token count (50 >= 30)
        # - Index 2: Contains "error" keyword
        # - Index 4, 5, 6: Recent messages (last 3)
        expected_indices = [1, 2, 4, 5, 6]
        
        assert set(important_indices) == set(expected_indices)

    @pytest.mark.asyncio
    async def test_create_intelligent_summary(self, hybrid_manager):
        """Test creation of intelligent summary."""
        conversation_id = "test-conv-123"
        messages = [
            {"role": "user", "content": "Hello", "token_count": 5},
            {"role": "assistant", "content": "Hi there! How can I help you today?", "token_count": 25}
        ]
        
        # Mock LLM response
        mock_response = MagicMock()
        mock_response.content = "User greeted and assistant offered help."
        hybrid_manager.llm.ainvoke = AsyncMock(return_value=mock_response)
        
        # Mock important message identification
        hybrid_manager._identify_important_messages = AsyncMock(return_value=[0, 1])
        
        result = await hybrid_manager._create_intelligent_summary(conversation_id, messages)
        
        assert result == "User greeted and assistant offered help."
        assert conversation_id in hybrid_manager._conversation_summaries
        assert conversation_id in hybrid_manager._last_summarization
        
        # Verify LLM was called with proper prompt
        hybrid_manager.llm.ainvoke.assert_called_once()
        call_args = hybrid_manager.llm.ainvoke.call_args[0][0]
        assert "[IMPORTANT]" in call_args  # Important messages should be marked

    @pytest.mark.asyncio
    async def test_create_intelligent_summary_with_existing_summary(self, hybrid_manager):
        """Test creating summary with existing summary."""
        conversation_id = "test-conv-123"
        messages = [
            {"role": "user", "content": "New question", "token_count": 10}
        ]
        
        # Set existing summary
        hybrid_manager._conversation_summaries[conversation_id] = "Previous conversation summary"
        
        # Mock LLM response
        mock_response = MagicMock()
        mock_response.content = "Updated summary with new information."
        hybrid_manager.llm.ainvoke = AsyncMock(return_value=mock_response)
        
        # Mock important message identification
        hybrid_manager._identify_important_messages = AsyncMock(return_value=[0])
        
        result = await hybrid_manager._create_intelligent_summary(conversation_id, messages)
        
        assert result == "Updated summary with new information."
        
        # Verify existing summary was included in prompt
        call_args = hybrid_manager.llm.ainvoke.call_args[0][0]
        assert "Previous conversation summary" in call_args

    @pytest.mark.asyncio
    async def test_create_intelligent_summary_llm_failure(self, hybrid_manager):
        """Test summary creation with LLM failure."""
        conversation_id = "test-conv-123"
        messages = [
            {"role": "user", "content": "Hello", "token_count": 5}
        ]
        
        # Mock LLM failure
        hybrid_manager.llm.ainvoke = AsyncMock(side_effect=Exception("LLM API error"))
        hybrid_manager._identify_important_messages = AsyncMock(return_value=[0])
        
        result = await hybrid_manager._create_intelligent_summary(conversation_id, messages)
        
        # Should return fallback summary
        assert "Summary of 1 messages from conversation." in result

    @pytest.mark.asyncio
    async def test_compress_conversation_history_redis(self, hybrid_manager):
        """Test conversation compression with Redis messages."""
        conversation_id = "test-conv-123"
        
        # Mock messages (15 messages, should keep 5 and summarize 10)
        messages = []
        for i in range(15):
            messages.append({
                "role": "user" if i % 2 == 0 else "assistant",
                "content": f"Message {i}",
                "token_count": 10,
                "timestamp": datetime.utcnow().isoformat()
            })
        
        # Mock Redis operations
        hybrid_manager.session_manager.session_exists = AsyncMock(return_value=True)
        hybrid_manager.session_manager.get_messages = AsyncMock(return_value=messages)
        hybrid_manager.session_manager.delete_session = AsyncMock()
        hybrid_manager.session_manager.get_session = AsyncMock(return_value={"user_id": "test-user"})
        hybrid_manager.session_manager.create_session = AsyncMock()
        hybrid_manager.session_manager.add_message = AsyncMock()
        
        # Mock summary creation
        hybrid_manager._create_intelligent_summary = AsyncMock(return_value="Conversation summary")
        
        result = await hybrid_manager._compress_conversation_history(conversation_id)
        
        assert result["messages_before"] == 15
        assert result["messages_after"] == 5  # Keep 1/3 of messages
        assert result["tokens_before"] == 150  # 15 * 10
        assert result["tokens_after"] == 50   # 5 * 10
        assert result["summary_created"] is True
        
        # Verify Redis operations
        hybrid_manager.session_manager.delete_session.assert_called_once()
        hybrid_manager.session_manager.create_session.assert_called_once()
        assert hybrid_manager.session_manager.add_message.call_count == 5

    @pytest.mark.asyncio
    async def test_compress_conversation_history_database_fallback(self, hybrid_manager):
        """Test conversation compression with database fallback."""
        conversation_id = str(uuid4())
        
        # Mock database messages
        mock_messages = []
        for i in range(12):
            mock_msg = MagicMock()
            mock_msg.role = "user" if i % 2 == 0 else "assistant"
            mock_msg.content = f"Message {i}"
            mock_msg.token_count = 8
            mock_msg.created_at = datetime.utcnow()
            mock_messages.append(mock_msg)
        
        # Mock Redis not existing, database exists
        hybrid_manager.session_manager.session_exists = AsyncMock(return_value=False)
        hybrid_manager.db_store.get_conversation_messages = AsyncMock(return_value=mock_messages)
        
        # Mock summary creation
        hybrid_manager._create_intelligent_summary = AsyncMock(return_value="Database summary")
        
        result = await hybrid_manager._compress_conversation_history(conversation_id)
        
        assert result["messages_before"] == 12
        assert result["messages_after"] == 5  # Keep max(5, 12//3) = max(5, 4) = 5
        assert result["tokens_before"] == 96  # 12 * 8
        assert result["summary_created"] is True

    @pytest.mark.asyncio
    async def test_compress_conversation_history_insufficient_messages(self, hybrid_manager):
        """Test compression with insufficient messages."""
        conversation_id = "test-conv-123"
        
        # Mock few messages (below batch size)
        messages = [
            {"role": "user", "content": "Hello", "token_count": 5},
            {"role": "assistant", "content": "Hi", "token_count": 3}
        ]
        
        hybrid_manager.session_manager.session_exists = AsyncMock(return_value=True)
        hybrid_manager.session_manager.get_messages = AsyncMock(return_value=messages)
        
        result = await hybrid_manager._compress_conversation_history(conversation_id)
        
        # Should not compress
        assert result["messages_before"] == 0
        assert result["summary_created"] is False

    @pytest.mark.asyncio
    async def test_cleanup_old_database_messages(self, hybrid_manager):
        """Test cleanup of old database messages."""
        conversation_id = str(uuid4())
        
        # Mock database cleanup
        hybrid_manager.db_store.delete_old_messages = AsyncMock(return_value=5)
        
        result = await hybrid_manager._cleanup_old_database_messages(conversation_id, keep_recent=10)
        
        assert result == 5
        hybrid_manager.db_store.delete_old_messages.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_old_database_messages_invalid_uuid(self, hybrid_manager):
        """Test cleanup with invalid UUID."""
        conversation_id = "invalid-uuid"
        
        result = await hybrid_manager._cleanup_old_database_messages(conversation_id)
        
        assert result == 0

    @pytest.mark.asyncio
    async def test_intelligent_token_management_standard_compression(self, hybrid_manager):
        """Test intelligent token management with standard compression."""
        conversation_id = "test-conv-123"
        
        # Mock warning threshold exceeded but not critical
        hybrid_manager._calculate_conversation_tokens = AsyncMock(side_effect=[850, 400])  # Before and after
        hybrid_manager._should_trigger_summarization = AsyncMock(return_value=True)
        hybrid_manager._is_critical_token_limit = AsyncMock(return_value=False)
        hybrid_manager._compress_conversation_history = AsyncMock(return_value={
            "messages_before": 10,
            "messages_after": 5,
            "tokens_before": 850,
            "tokens_after": 400,
            "summary_created": True
        })
        
        result = await hybrid_manager.intelligent_token_management(conversation_id)
        
        assert result["conversation_id"] == conversation_id
        assert result["initial_tokens"] == 850
        assert result["final_tokens"] == 400
        assert result["action_taken"] == "standard_compression"
        assert result["warning_triggered"] is True
        assert result["critical_triggered"] is False
        
        hybrid_manager._compress_conversation_history.assert_called_once()

    @pytest.mark.asyncio
    async def test_intelligent_token_management_critical_compression(self, hybrid_manager):
        """Test intelligent token management with critical compression."""
        conversation_id = "test-conv-123"
        
        # Mock critical threshold exceeded
        hybrid_manager._calculate_conversation_tokens = AsyncMock(side_effect=[950, 300])  # Before and after
        hybrid_manager._should_trigger_summarization = AsyncMock(return_value=True)
        hybrid_manager._is_critical_token_limit = AsyncMock(return_value=True)
        hybrid_manager._compress_conversation_history = AsyncMock(return_value={
            "messages_before": 15,
            "messages_after": 3,
            "tokens_before": 950,
            "tokens_after": 300,
            "summary_created": True
        })
        hybrid_manager._cleanup_old_database_messages = AsyncMock(return_value=8)
        
        result = await hybrid_manager.intelligent_token_management(conversation_id)
        
        assert result["action_taken"] == "critical_compression"
        assert result["critical_triggered"] is True
        assert result["cleanup_stats"]["deleted_messages"] == 8
        
        hybrid_manager._compress_conversation_history.assert_called_once()
        hybrid_manager._cleanup_old_database_messages.assert_called_once()

    @pytest.mark.asyncio
    async def test_intelligent_token_management_no_action_needed(self, hybrid_manager):
        """Test token management when no action is needed."""
        conversation_id = "test-conv-123"
        
        # Mock below warning threshold
        hybrid_manager._calculate_conversation_tokens = AsyncMock(return_value=500)
        hybrid_manager._should_trigger_summarization = AsyncMock(return_value=False)
        hybrid_manager._is_critical_token_limit = AsyncMock(return_value=False)
        
        result = await hybrid_manager.intelligent_token_management(conversation_id)
        
        assert result["action_taken"] == "none"
        assert result["warning_triggered"] is False
        assert result["critical_triggered"] is False

    @pytest.mark.asyncio
    async def test_get_prioritized_context(self, hybrid_manager):
        """Test getting prioritized context."""
        conversation_id = "test-conv-123"
        
        # Mock messages with different priorities
        messages = [
            {"role": "user", "content": "Old message", "token_count": 10},
            {"role": "assistant", "content": "This is a very important detailed response with critical information", "token_count": 60},
            {"role": "user", "content": "I have an error", "token_count": 15},
            {"role": "assistant", "content": "Recent 1", "token_count": 8},
            {"role": "user", "content": "Recent 2", "token_count": 10},
            {"role": "assistant", "content": "Most recent", "token_count": 12}
        ]
        
        # Mock summary
        hybrid_manager._conversation_summaries[conversation_id] = "Previous summary"
        
        # Mock token counter to return reasonable values
        def mock_count_tokens(text):
            if "Previous summary" in text:
                return 20
            elif "Most recent" in text:
                return 15
            elif "Recent" in text:
                return 12
            elif "error" in text:
                return 18
            elif "important" in text:
                return 25
            else:
                return 10
        
        hybrid_manager.token_counter.count_tokens = MagicMock(side_effect=mock_count_tokens)
        
        hybrid_manager.get_messages = AsyncMock(return_value=messages)
        hybrid_manager._identify_important_messages = AsyncMock(return_value=[1, 2, 3, 4, 5])
        
        result = await hybrid_manager.get_prioritized_context(conversation_id, max_tokens=200)
        
        assert "Previous summary" in result
        assert "Most recent" in result  # Recent messages should be included
        # Note: [Important] marking depends on the prioritization logic

    @pytest.mark.asyncio
    async def test_get_prioritized_context_no_summary(self, hybrid_manager):
        """Test prioritized context without summary."""
        conversation_id = "test-conv-123"
        
        messages = [
            {"role": "user", "content": "Hello", "token_count": 5},
            {"role": "assistant", "content": "Hi there", "token_count": 8}
        ]
        
        hybrid_manager.get_messages = AsyncMock(return_value=messages)
        hybrid_manager._identify_important_messages = AsyncMock(return_value=[0, 1])
        hybrid_manager.token_counter.count_tokens = MagicMock(return_value=15)
        
        result = await hybrid_manager.get_prioritized_context(conversation_id, max_tokens=100, include_summary=False)
        
        assert "Hello" in result
        assert "Hi there" in result
        assert "Previous summary" not in result

    @pytest.mark.asyncio
    async def test_auto_manage_conversation_tokens_needed(self, hybrid_manager):
        """Test automatic token management when needed."""
        conversation_id = "test-conv-123"
        
        hybrid_manager._should_trigger_summarization = AsyncMock(return_value=True)
        hybrid_manager.intelligent_token_management = AsyncMock(return_value={
            "action_taken": "standard_compression"
        })
        
        result = await hybrid_manager.auto_manage_conversation_tokens(conversation_id)
        
        assert result is True
        hybrid_manager.intelligent_token_management.assert_called_once()

    @pytest.mark.asyncio
    async def test_auto_manage_conversation_tokens_not_needed(self, hybrid_manager):
        """Test automatic token management when not needed."""
        conversation_id = "test-conv-123"
        
        hybrid_manager._should_trigger_summarization = AsyncMock(return_value=False)
        
        result = await hybrid_manager.auto_manage_conversation_tokens(conversation_id)
        
        assert result is False

    @pytest.mark.asyncio
    async def test_get_conversation_summary(self, hybrid_manager):
        """Test getting conversation summary."""
        conversation_id = "test-conv-123"
        
        # Set a summary
        hybrid_manager._conversation_summaries[conversation_id] = "Test summary"
        
        result = await hybrid_manager.get_conversation_summary(conversation_id)
        
        assert result == "Test summary"

    @pytest.mark.asyncio
    async def test_get_conversation_summary_not_exists(self, hybrid_manager):
        """Test getting summary when it doesn't exist."""
        conversation_id = "test-conv-123"
        
        result = await hybrid_manager.get_conversation_summary(conversation_id)
        
        assert result is None

    @pytest.mark.asyncio
    async def test_force_conversation_summarization(self, hybrid_manager):
        """Test forcing conversation summarization."""
        conversation_id = "test-conv-123"
        
        messages = [
            {"role": "user", "content": "Hello", "token_count": 5},
            {"role": "assistant", "content": "Hi there", "token_count": 8}
        ]
        
        hybrid_manager.get_messages = AsyncMock(return_value=messages)
        hybrid_manager._create_intelligent_summary = AsyncMock(return_value="Forced summary")
        
        result = await hybrid_manager.force_conversation_summarization(conversation_id)
        
        assert result == "Forced summary"
        hybrid_manager._create_intelligent_summary.assert_called_once_with(conversation_id, messages)

    @pytest.mark.asyncio
    async def test_force_conversation_summarization_no_messages(self, hybrid_manager):
        """Test forcing summarization with no messages."""
        conversation_id = "test-conv-123"
        
        hybrid_manager.get_messages = AsyncMock(return_value=[])
        
        result = await hybrid_manager.force_conversation_summarization(conversation_id)
        
        assert result == ""


class TestTokenManagementIntegration:
    """Test integration of token management with existing functionality."""

    @pytest.fixture
    def hybrid_manager(self):
        """Create hybrid manager for integration testing."""
        mock_session_manager = MagicMock()
        with patch('app.services.memory_manager.ChatOpenAI'):
            return HybridMemoryManager(
                mock_session_manager,
                max_token_limit=1000,
                token_warning_threshold=0.8
            )

    @pytest.mark.asyncio
    async def test_add_user_message_triggers_token_management(self, hybrid_manager):
        """Test that adding messages triggers token management."""
        conversation_id = str(uuid4())
        user_id = "test-user"
        message = "Hello, world!"
        
        # Mock dependencies
        hybrid_manager.session_manager.add_message = AsyncMock()
        hybrid_manager._should_promote_session = AsyncMock(return_value=False)
        hybrid_manager.auto_manage_conversation_tokens = AsyncMock(return_value=True)
        
        # Initialize memory
        hybrid_manager._get_memory_instance(conversation_id)
        
        await hybrid_manager.add_user_message(conversation_id, message, user_id)
        
        # Verify token management was called
        hybrid_manager.auto_manage_conversation_tokens.assert_called_once_with(conversation_id)

    @pytest.mark.asyncio
    async def test_add_ai_message_triggers_token_management(self, hybrid_manager):
        """Test that adding AI messages triggers token management."""
        conversation_id = str(uuid4())
        user_id = "test-user"
        message = "Hello there!"
        
        # Mock dependencies
        hybrid_manager.session_manager.add_message = AsyncMock()
        hybrid_manager._should_promote_session = AsyncMock(return_value=False)
        hybrid_manager.auto_manage_conversation_tokens = AsyncMock(return_value=False)
        
        # Initialize memory
        hybrid_manager._get_memory_instance(conversation_id)
        
        await hybrid_manager.add_ai_message(conversation_id, message, user_id)
        
        # Verify token management was called
        hybrid_manager.auto_manage_conversation_tokens.assert_called_once_with(conversation_id)

    @pytest.mark.asyncio
    async def test_get_memory_context_with_intelligent_prioritization(self, hybrid_manager):
        """Test memory context retrieval with intelligent prioritization."""
        conversation_id = "test-conv-123"
        
        # Mock prioritized context
        hybrid_manager.get_prioritized_context = AsyncMock(return_value="Prioritized context")
        
        result = await hybrid_manager.get_memory_context(conversation_id, max_tokens=500)
        
        assert result == "Prioritized context"
        hybrid_manager.get_prioritized_context.assert_called_once_with(conversation_id, 500)

    @pytest.mark.asyncio
    async def test_get_memory_context_triggers_management(self, hybrid_manager):
        """Test memory context triggers token management when needed."""
        conversation_id = "test-conv-123"
        
        # Mock memory instance
        memory = hybrid_manager._get_memory_instance(conversation_id)
        
        # Add some messages to create a buffer
        memory.add_user_message("This is a long message that will contribute to token count")
        memory.add_ai_message("This is another long response that adds to the total token count")
        
        # Mock token counting to exceed limit
        hybrid_manager.token_counter.count_tokens = MagicMock(return_value=1200)  # Exceeds limit
        hybrid_manager.intelligent_token_management = AsyncMock()
        
        await hybrid_manager.get_memory_context(conversation_id)
        
        # Should trigger token management
        hybrid_manager.intelligent_token_management.assert_called_once_with(conversation_id)

    @pytest.mark.asyncio
    async def test_clear_memory_clears_token_data(self, hybrid_manager):
        """Test that clearing memory also clears token management data."""
        conversation_id = "test-conv-123"
        
        # Set up token management data
        hybrid_manager._conversation_summaries[conversation_id] = "Test summary"
        hybrid_manager._last_summarization[conversation_id] = datetime.utcnow()
        
        # Mock session manager
        hybrid_manager.session_manager.delete_session = AsyncMock()
        
        await hybrid_manager.clear_memory(conversation_id)
        
        # Verify token management data was cleared
        assert conversation_id not in hybrid_manager._conversation_summaries
        assert conversation_id not in hybrid_manager._last_summarization

    @pytest.mark.asyncio
    async def test_get_session_info_includes_token_management(self, hybrid_manager):
        """Test session info includes token management information."""
        conversation_id = "test-conv-123"
        
        # Mock dependencies
        hybrid_manager.session_manager.get_session_stats = AsyncMock(return_value={
            "message_count": 10,
            "total_tokens": 500
        })
        hybrid_manager.db_store.conversation_exists = AsyncMock(return_value=True)
        hybrid_manager._calculate_conversation_tokens = AsyncMock(return_value=600)
        hybrid_manager._should_trigger_summarization = AsyncMock(return_value=True)
        hybrid_manager._is_critical_token_limit = AsyncMock(return_value=False)
        
        # Set summary
        hybrid_manager._conversation_summaries[conversation_id] = "Test summary"
        hybrid_manager.token_counter.count_tokens = MagicMock(return_value=50)
        
        result = await hybrid_manager.get_session_info(conversation_id)
        
        # Verify token management info is included
        assert "token_management" in result
        token_mgmt = result["token_management"]
        assert token_mgmt["has_summary"] is True
        assert token_mgmt["needs_management"] is True
        assert token_mgmt["is_critical"] is False
        assert token_mgmt["summary_tokens"] == 50
        assert token_mgmt["warning_threshold"] == 800
        assert token_mgmt["critical_threshold"] == 900


class TestTokenManagementErrorHandling:
    """Test error handling in token management functionality."""

    @pytest.fixture
    def hybrid_manager(self):
        """Create hybrid manager for error testing."""
        mock_session_manager = MagicMock()
        with patch('app.services.memory_manager.ChatOpenAI'):
            return HybridMemoryManager(mock_session_manager)

    @pytest.mark.asyncio
    async def test_calculate_tokens_error_handling(self, hybrid_manager):
        """Test error handling in token calculation."""
        conversation_id = "test-conv-123"
        
        # Mock session manager failure
        hybrid_manager.session_manager.get_session_stats = AsyncMock(side_effect=Exception("Redis error"))
        
        result = await hybrid_manager._calculate_conversation_tokens(conversation_id)
        
        # Should return 0 on error
        assert result == 0

    @pytest.mark.asyncio
    async def test_summarization_trigger_error_handling(self, hybrid_manager):
        """Test error handling in summarization trigger check."""
        conversation_id = "test-conv-123"
        
        # Mock calculation failure
        hybrid_manager._calculate_conversation_tokens = AsyncMock(side_effect=Exception("Calculation error"))
        
        result = await hybrid_manager._should_trigger_summarization(conversation_id)
        
        # Should return False on error
        assert result is False

    @pytest.mark.asyncio
    async def test_compression_error_handling(self, hybrid_manager):
        """Test error handling in conversation compression."""
        conversation_id = "test-conv-123"
        
        # Mock session manager failure
        hybrid_manager.session_manager.session_exists = AsyncMock(side_effect=Exception("Redis error"))
        
        result = await hybrid_manager._compress_conversation_history(conversation_id)
        
        # Should return empty stats on error
        assert result["messages_before"] == 0
        assert result["summary_created"] is False

    @pytest.mark.asyncio
    async def test_intelligent_management_error_handling(self, hybrid_manager):
        """Test error handling in intelligent token management."""
        conversation_id = "test-conv-123"
        
        # Mock calculation failure
        hybrid_manager._calculate_conversation_tokens = AsyncMock(side_effect=Exception("Token calc error"))
        
        result = await hybrid_manager.intelligent_token_management(conversation_id)
        
        # Should return error info
        assert "error" in result
        assert result["conversation_id"] == conversation_id

    @pytest.mark.asyncio
    async def test_prioritized_context_error_handling(self, hybrid_manager):
        """Test error handling in prioritized context retrieval."""
        conversation_id = "test-conv-123"
        
        # Mock get_messages failure
        hybrid_manager.get_messages = AsyncMock(side_effect=Exception("Message retrieval error"))
        
        result = await hybrid_manager.get_prioritized_context(conversation_id)
        
        # Should return empty string on error
        assert result == ""

    @pytest.mark.asyncio
    async def test_auto_management_error_handling(self, hybrid_manager):
        """Test error handling in automatic token management."""
        conversation_id = "test-conv-123"
        
        # Mock trigger check failure
        hybrid_manager._should_trigger_summarization = AsyncMock(side_effect=Exception("Trigger error"))
        
        result = await hybrid_manager.auto_manage_conversation_tokens(conversation_id)
        
        # Should return False on error
        assert result is False

    @pytest.mark.asyncio
    async def test_force_summarization_error_handling(self, hybrid_manager):
        """Test error handling in forced summarization."""
        conversation_id = "test-conv-123"
        
        # Mock get_messages failure
        hybrid_manager.get_messages = AsyncMock(side_effect=Exception("Message error"))
        
        result = await hybrid_manager.force_conversation_summarization(conversation_id)
        
        # Should return empty string on error
        assert result == ""