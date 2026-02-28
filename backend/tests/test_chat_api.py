"""
Integration tests for chat API endpoints.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime
from httpx import AsyncClient

from app.main import app
from app.services.rag_pipeline import RAGResponse, RAGRequest
from app.services.rag_service import RetrievalResult
from app.services.llm_providers.base import LLMResponse
from app.models.conversation import Conversation, ChatMessage


class TestChatAPI:
    """Test chat API endpoints."""
    
    @pytest.fixture
    async def client(self):
        """Create test client."""
        from httpx import ASGITransport
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac
    
    @pytest.fixture
    def mock_rag_pipeline(self):
        """Mock RAG pipeline."""
        return AsyncMock()
    
    @pytest.fixture
    def mock_memory_manager(self):
        """Mock memory manager."""
        return AsyncMock()
    
    @pytest.fixture
    def mock_session(self):
        """Mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.add = MagicMock()
        session.get = AsyncMock()
        session.execute = AsyncMock()
        session.refresh = AsyncMock()
        session.delete = AsyncMock()
        return session
    
    def create_mock_rag_response(self) -> RAGResponse:
        """Create mock RAG response."""
        retrieval_result = RetrievalResult(
            query="test query",
            chunks=[],
            total_tokens=100,
            processing_time=1.0,
            embedding_time=0.2,
            search_time=0.6,
            ranking_time=0.2
        )
        
        llm_response = LLMResponse(
            content="Test response",
            input_tokens=50,
            output_tokens=30,
            total_tokens=80,
            cost=0.002,
            provider="openai",
            model="gpt-3.5-turbo"
        )
        
        return RAGResponse(
            query="test query",
            response="Test response",
            sources=[],
            retrieval_result=retrieval_result,
            llm_response=llm_response,
            processing_time=2.0,
            context_tokens=50,
            response_tokens=30,
            total_cost=0.002
        )
    
    @pytest.mark.asyncio
    async def test_chat_health_check(self, client):
        """Test chat health check endpoint."""
        with patch('app.api.chat.get_rag_pipeline') as mock_get_rag, \
             patch('app.api.chat.get_memory_manager') as mock_get_memory:
            
            mock_get_rag.return_value = AsyncMock()
            mock_get_memory.return_value = AsyncMock()
            
            response = await client.get("/api/v1/chat/health")
            
            assert response.status_code == 200
            data = response.json()
            assert "status" in data
            assert "components" in data
            assert "timestamp" in data
    
    @pytest.mark.asyncio
    async def test_start_conversation_success(self, client, mock_session, mock_memory_manager):
        """Test successful conversation creation."""
        # Mock database session
        conversation_id = uuid4()
        mock_conversation = Conversation(
            id=conversation_id,
            user_id="user123",
            title="Test Conversation",
            created_at=datetime.utcnow()
        )
        mock_session.refresh.return_value = None
        
        with patch('app.api.chat.get_async_session', return_value=mock_session), \
             patch('app.api.chat.get_memory_manager', return_value=mock_memory_manager), \
             patch('app.api.chat.uuid4', return_value=conversation_id), \
             patch('app.api.chat.Conversation', return_value=mock_conversation):
            
            request_data = {
                "title": "Test Conversation",
                "user_id": "user123"
            }
            
            response = await client.post("/api/v1/chat/conversations", json=request_data)
            
            assert response.status_code == 200
            data = response.json()
            assert "conversation_id" in data
            assert "title" in data
            assert "created_at" in data
            assert data["message"] == "Conversation started successfully"
    
    @pytest.mark.asyncio
    async def test_start_conversation_missing_user_id(self, client):
        """Test conversation creation with missing user_id."""
        request_data = {
            "title": "Test Conversation"
            # Missing user_id
        }
        
        response = await client.post("/api/v1/chat/conversations", json=request_data)
        
        assert response.status_code == 422  # Validation error
    
    @pytest.mark.asyncio
    async def test_send_message_success(self, client, mock_session, mock_rag_pipeline, mock_memory_manager):
        """Test successful message sending."""
        conversation_id = uuid4()
        
        # Mock conversation exists
        mock_conversation = Conversation(
            id=conversation_id,
            user_id="user123",
            title="Test Conversation"
        )
        mock_session.get.return_value = mock_conversation
        
        # Mock RAG response
        mock_rag_response = self.create_mock_rag_response()
        mock_rag_pipeline.generate_response.return_value = mock_rag_response
        
        # Mock message creation
        message_id = uuid4()
        mock_message = ChatMessage(
            id=message_id,
            conversation_id=conversation_id,
            role="assistant",
            content="Test response",
            token_count=10,
            created_at=datetime.utcnow()
        )
        
        with patch('app.api.chat.get_async_session', return_value=mock_session), \
             patch('app.api.chat.get_rag_pipeline', return_value=mock_rag_pipeline), \
             patch('app.api.chat.get_memory_manager', return_value=mock_memory_manager), \
             patch('app.api.chat.uuid4', return_value=message_id), \
             patch('app.api.chat.ChatMessage', return_value=mock_message):
            
            request_data = {
                "message": "What is machine learning?",
                "max_context_chunks": 5,
                "similarity_threshold": 0.3,
                "temperature": 0.7,
                "include_citations": True
            }
            
            response = await client.post(
                f"/api/v1/chat/conversations/{conversation_id}/messages",
                json=request_data
            )
            
            assert response.status_code == 200
            data = response.json()
            assert "message_id" in data
            assert "conversation_id" in data
            assert "response" in data
            assert "sources" in data
            assert "metadata" in data
            assert "timestamp" in data
    
    @pytest.mark.asyncio
    async def test_send_message_conversation_not_found(self, client, mock_session):
        """Test sending message to non-existent conversation."""
        conversation_id = uuid4()
        
        # Mock conversation not found
        mock_session.get.return_value = None
        
        with patch('app.api.chat.get_async_session', return_value=mock_session):
            request_data = {
                "message": "Test message"
            }
            
            response = await client.post(
                f"/api/v1/chat/conversations/{conversation_id}/messages",
                json=request_data
            )
            
            assert response.status_code == 404
            data = response.json()
            assert data["detail"] == "Conversation not found"
    
    @pytest.mark.asyncio
    async def test_send_message_invalid_request(self, client):
        """Test sending message with invalid request data."""
        conversation_id = uuid4()
        
        request_data = {
            "message": "",  # Empty message
            "temperature": 3.0  # Invalid temperature
        }
        
        response = await client.post(
            f"/api/v1/chat/conversations/{conversation_id}/messages",
            json=request_data
        )
        
        assert response.status_code == 422  # Validation error
    
    @pytest.mark.asyncio
    async def test_list_conversations_success(self, client, mock_session):
        """Test successful conversation listing."""
        user_id = "user123"
        
        # Mock conversation data
        mock_conversations = [
            Conversation(
                id=uuid4(),
                user_id=user_id,
                title="Conversation 1",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            ),
            Conversation(
                id=uuid4(),
                user_id=user_id,
                title="Conversation 2",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
        ]
        
        # Mock database queries
        mock_session.execute.side_effect = [
            # Total count query
            MagicMock(scalar=lambda: 2),
            # Conversations query
            MagicMock(scalars=lambda: MagicMock(all=lambda: mock_conversations)),
            # Message count queries
            MagicMock(scalar=lambda: 5),
            MagicMock(scalar=lambda: 3),
            # Last message queries
            MagicMock(scalar=lambda: "Last message 1"),
            MagicMock(scalar=lambda: "Last message 2")
        ]
        
        with patch('app.api.chat.get_async_session', return_value=mock_session):
            response = await client.get(f"/api/v1/chat/conversations?user_id={user_id}")
            
            assert response.status_code == 200
            data = response.json()
            assert "conversations" in data
            assert "total" in data
            assert "page" in data
            assert "page_size" in data
            assert len(data["conversations"]) == 2
    
    @pytest.mark.asyncio
    async def test_list_conversations_pagination(self, client, mock_session):
        """Test conversation listing with pagination."""
        user_id = "user123"
        
        # Mock empty result for page 2
        mock_session.execute.side_effect = [
            MagicMock(scalar=lambda: 0),  # Total count
            MagicMock(scalars=lambda: MagicMock(all=lambda: []))  # Empty conversations
        ]
        
        with patch('app.api.chat.get_async_session', return_value=mock_session):
            response = await client.get(
                f"/api/v1/chat/conversations?user_id={user_id}&page=2&page_size=10"
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["page"] == 2
            assert data["page_size"] == 10
            assert len(data["conversations"]) == 0
    
    @pytest.mark.asyncio
    async def test_get_conversation_success(self, client, mock_session):
        """Test successful conversation retrieval."""
        conversation_id = uuid4()
        user_id = "user123"
        
        # Mock conversation with messages
        mock_messages = [
            ChatMessage(
                id=uuid4(),
                conversation_id=conversation_id,
                role="user",
                content="Hello",
                token_count=5,
                created_at=datetime.utcnow()
            ),
            ChatMessage(
                id=uuid4(),
                conversation_id=conversation_id,
                role="assistant",
                content="Hi there!",
                token_count=8,
                created_at=datetime.utcnow()
            )
        ]
        
        mock_conversation = Conversation(
            id=conversation_id,
            user_id=user_id,
            title="Test Conversation",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            messages=mock_messages
        )
        
        mock_session.execute.return_value = MagicMock(
            scalar_one_or_none=lambda: mock_conversation
        )
        
        with patch('app.api.chat.get_async_session', return_value=mock_session):
            response = await client.get(
                f"/api/v1/chat/conversations/{conversation_id}?user_id={user_id}"
            )
            
            assert response.status_code == 200
            data = response.json()
            assert "id" in data
            assert "title" in data
            assert "messages" in data
            assert len(data["messages"]) == 2
    
    @pytest.mark.asyncio
    async def test_get_conversation_not_found(self, client, mock_session):
        """Test getting non-existent conversation."""
        conversation_id = uuid4()
        user_id = "user123"
        
        mock_session.execute.return_value = MagicMock(
            scalar_one_or_none=lambda: None
        )
        
        with patch('app.api.chat.get_async_session', return_value=mock_session):
            response = await client.get(
                f"/api/v1/chat/conversations/{conversation_id}?user_id={user_id}"
            )
            
            assert response.status_code == 404
            data = response.json()
            assert data["detail"] == "Conversation not found"
    
    @pytest.mark.asyncio
    async def test_delete_conversation_success(self, client, mock_session, mock_memory_manager):
        """Test successful conversation deletion."""
        conversation_id = uuid4()
        user_id = "user123"
        
        # Mock conversation exists and belongs to user
        mock_conversation = Conversation(
            id=conversation_id,
            user_id=user_id,
            title="Test Conversation"
        )
        mock_session.get.return_value = mock_conversation
        
        with patch('app.api.chat.get_async_session', return_value=mock_session), \
             patch('app.api.chat.get_memory_manager', return_value=mock_memory_manager):
            
            response = await client.delete(
                f"/api/v1/chat/conversations/{conversation_id}?user_id={user_id}"
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["message"] == "Conversation deleted successfully"
    
    @pytest.mark.asyncio
    async def test_delete_conversation_not_found(self, client, mock_session):
        """Test deleting non-existent conversation."""
        conversation_id = uuid4()
        user_id = "user123"
        
        mock_session.get.return_value = None
        
        with patch('app.api.chat.get_async_session', return_value=mock_session):
            response = await client.delete(
                f"/api/v1/chat/conversations/{conversation_id}?user_id={user_id}"
            )
            
            assert response.status_code == 404
            data = response.json()
            assert data["detail"] == "Conversation not found"
    
    @pytest.mark.asyncio
    async def test_delete_conversation_unauthorized(self, client, mock_session):
        """Test deleting conversation owned by different user."""
        conversation_id = uuid4()
        user_id = "user123"
        
        # Mock conversation belongs to different user
        mock_conversation = Conversation(
            id=conversation_id,
            user_id="different_user",
            title="Test Conversation"
        )
        mock_session.get.return_value = mock_conversation
        
        with patch('app.api.chat.get_async_session', return_value=mock_session):
            response = await client.delete(
                f"/api/v1/chat/conversations/{conversation_id}?user_id={user_id}"
            )
            
            assert response.status_code == 403
            data = response.json()
            assert data["detail"] == "Not authorized to delete this conversation"
    
    @pytest.mark.asyncio
    async def test_get_memory_stats_success(self, client, mock_memory_manager):
        """Test successful memory stats retrieval."""
        conversation_id = uuid4()
        user_id = "user123"
        
        mock_stats = {
            "total_tokens": 1500,
            "message_count": 10,
            "memory_usage": "active",
            "last_optimization": "2024-01-01T12:00:00"
        }
        mock_memory_manager.get_conversation_stats.return_value = mock_stats
        
        with patch('app.api.chat.get_memory_manager', return_value=mock_memory_manager):
            response = await client.get(
                f"/api/v1/chat/conversations/{conversation_id}/memory/stats?user_id={user_id}"
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data == mock_stats
    
    @pytest.mark.asyncio
    async def test_get_memory_stats_not_found(self, client, mock_memory_manager):
        """Test memory stats for non-existent conversation."""
        conversation_id = uuid4()
        user_id = "user123"
        
        mock_memory_manager.get_conversation_stats.return_value = None
        
        with patch('app.api.chat.get_memory_manager', return_value=mock_memory_manager):
            response = await client.get(
                f"/api/v1/chat/conversations/{conversation_id}/memory/stats?user_id={user_id}"
            )
            
            assert response.status_code == 404
            data = response.json()
            assert data["detail"] == "Conversation memory not found"
    
    @pytest.mark.asyncio
    async def test_send_message_stream_not_implemented(self, client):
        """Test that streaming endpoint returns not implemented."""
        conversation_id = uuid4()
        
        request_data = {
            "message": "Test message",
            "stream": True
        }
        
        response = await client.post(
            f"/api/v1/chat/conversations/{conversation_id}/messages/stream",
            json=request_data
        )
        
        assert response.status_code == 501
        data = response.json()
        assert data["detail"] == "Streaming responses not yet implemented"


class TestChatAPIValidation:
    """Test chat API request validation."""
    
    @pytest.fixture
    async def client(self):
        """Create test client."""
        from httpx import ASGITransport
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac
    
    @pytest.mark.asyncio
    async def test_start_conversation_validation(self, client):
        """Test start conversation request validation."""
        # Test missing required fields
        response = await client.post("/api/v1/chat/conversations", json={})
        assert response.status_code == 422
        
        # Test invalid user_id
        response = await client.post("/api/v1/chat/conversations", json={
            "user_id": "",  # Empty user_id
            "title": "Test"
        })
        assert response.status_code == 422
        
        # Test title too long
        response = await client.post("/api/v1/chat/conversations", json={
            "user_id": "user123",
            "title": "x" * 300  # Too long
        })
        assert response.status_code == 422
    
    @pytest.mark.asyncio
    async def test_send_message_validation(self, client):
        """Test send message request validation."""
        conversation_id = uuid4()
        
        # Test empty message
        response = await client.post(
            f"/api/v1/chat/conversations/{conversation_id}/messages",
            json={"message": ""}
        )
        assert response.status_code == 422
        
        # Test message too long
        response = await client.post(
            f"/api/v1/chat/conversations/{conversation_id}/messages",
            json={"message": "x" * 10001}
        )
        assert response.status_code == 422
        
        # Test invalid temperature
        response = await client.post(
            f"/api/v1/chat/conversations/{conversation_id}/messages",
            json={
                "message": "test",
                "temperature": 3.0  # Too high
            }
        )
        assert response.status_code == 422
        
        # Test invalid similarity threshold
        response = await client.post(
            f"/api/v1/chat/conversations/{conversation_id}/messages",
            json={
                "message": "test",
                "similarity_threshold": 1.5  # Too high
            }
        )
        assert response.status_code == 422
        
        # Test invalid max_context_chunks
        response = await client.post(
            f"/api/v1/chat/conversations/{conversation_id}/messages",
            json={
                "message": "test",
                "max_context_chunks": 0  # Too low
            }
        )
        assert response.status_code == 422
    
    @pytest.mark.asyncio
    async def test_list_conversations_validation(self, client):
        """Test list conversations parameter validation."""
        # Test missing user_id
        response = await client.get("/api/v1/chat/conversations")
        assert response.status_code == 422
        
        # Test invalid pagination parameters (should be handled gracefully)
        response = await client.get("/api/v1/chat/conversations?user_id=test&page=-1&page_size=200")
        # Should still work but with corrected parameters
        assert response.status_code in [200, 422]  # Depends on implementation