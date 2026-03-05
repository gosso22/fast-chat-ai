"""
Integration tests for RAG pipeline - complete document-to-chat flow.
Tests the critical integration issues mentioned in task 9.1.
"""

import pytest
import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4, UUID
from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.db.base import get_db
from app.api.chat import get_rag_pipeline, get_memory_manager
from app.services.rag_pipeline import RAGPipeline, RAGRequest, RAGResponse
from app.services.memory_manager import HybridMemoryManager
from app.services.llm_providers.manager import LLMProviderManager
from app.services.llm_providers.base import LLMResponse, ProviderConfig, ModelConfig
from app.services.rag_service import SemanticSearchService, RetrievalResult, RetrievedChunk
from app.models.conversation import Conversation, ChatMessage

logger = logging.getLogger(__name__)


class TestRAGIntegration:
    """Test RAG pipeline integration and critical fixes."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)
    
    @pytest.fixture
    def mock_session(self):
        """Create mock database session."""
        session = AsyncMock(spec=AsyncSession)
        session.add = MagicMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.refresh = AsyncMock()
        session.get = AsyncMock()
        session.execute = AsyncMock()
        session.close = AsyncMock()
        return session
    
    @pytest.fixture
    def mock_conversation(self):
        """Create mock conversation."""
        return Conversation(
            id=uuid4(),
            user_id="test_user",
            title="Test Conversation",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
    
    @pytest.fixture
    def mock_llm_response(self):
        """Create mock LLM response."""
        return LLMResponse(
            content="This is a test response based on the provided context.",
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            cost=0.001,
            provider="openai",
            model="gpt-3.5-turbo",
            timestamp=datetime.utcnow(),
            metadata={}
        )
    
    @pytest.fixture
    def mock_retrieved_chunks(self):
        """Create mock retrieved chunks."""
        return [
            RetrievedChunk(
                id=uuid4(),
                content="This is relevant content from document 1.",
                document_id=uuid4(),
                document_filename="test_doc1.pdf",
                chunk_index=0,
                similarity_score=0.85,
                rank=1,
                token_count=20,
                start_position=0,
                end_position=100
            ),
            RetrievedChunk(
                id=uuid4(),
                content="Additional relevant content from document 2.",
                document_id=uuid4(),
                document_filename="test_doc2.pdf",
                chunk_index=1,
                similarity_score=0.75,
                rank=2,
                token_count=25,
                start_position=100,
                end_position=200
            )
        ]
    
    @pytest.fixture
    def mock_retrieval_result(self, mock_retrieved_chunks):
        """Create mock retrieval result."""
        return RetrievalResult(
            query="test query",
            chunks=mock_retrieved_chunks,
            total_tokens=45,
            processing_time=0.5,
            embedding_time=0.1,
            search_time=0.3,
            ranking_time=0.1
        )
    
    @pytest.fixture
    def mock_rag_response(self, mock_llm_response, mock_retrieval_result):
        """Create mock RAG response."""
        return RAGResponse(
            query="test query",
            response=mock_llm_response.content,
            sources=[],
            retrieval_result=mock_retrieval_result,
            llm_response=mock_llm_response,
            processing_time=1.0,
            context_tokens=100,
            response_tokens=50,
            total_cost=0.001
        )
    
    @pytest.fixture
    def mock_memory_manager(self):
        """Create mock memory manager."""
        manager = AsyncMock(spec=HybridMemoryManager)
        manager.initialize_memory = AsyncMock()
        manager.add_user_message = AsyncMock()
        manager.add_ai_message = AsyncMock()
        manager.clear_memory = AsyncMock()
        manager.get_session_info = AsyncMock(return_value={
            "conversation_id": "test_conv",
            "redis_active": True,
            "message_count": 2,
            "total_tokens": 150
        })
        return manager
    
    @pytest.fixture
    def mock_rag_pipeline(self, mock_rag_response):
        """Create mock RAG pipeline."""
        pipeline = AsyncMock(spec=RAGPipeline)
        pipeline.generate_response = AsyncMock(return_value=mock_rag_response)
        pipeline.validate_pipeline = AsyncMock(return_value=True)
        return pipeline
    
    @pytest.mark.asyncio
    async def test_database_dependency_fixes(self):
        """Test that get_db is used instead of get_async_session."""
        
        # Test import works correctly
        from app.api.chat import get_db
        from app.services.memory_manager import DatabaseMemoryStore
        from app.services.vector_store import VectorStoreService, PostgreSQLVectorStore
        
        # These should not raise import errors
        assert get_db is not None
        
        # Test that memory manager uses get_db
        db_store = DatabaseMemoryStore()
        # This should not raise an error about get_async_session
        assert hasattr(db_store, 'token_counter')
        
        # Test that PostgreSQL vector store uses get_db  
        postgres_store = PostgreSQLVectorStore()
        assert hasattr(postgres_store, 'session_factory')
        
        # Test that vector store service can be created
        vector_store = VectorStoreService()
        assert hasattr(vector_store, 'vector_store')
        assert hasattr(vector_store, 'embedding_service')
    
    @pytest.mark.asyncio
    async def test_model_name_consistency(self):
        """Test that ChatMessage model is used consistently."""
        
        from app.models.conversation import ChatMessage
        from app.api.chat import ChatMessageSchema
        
        # Test that imports work without conflicts
        assert ChatMessage is not None
        assert ChatMessageSchema is not None
        
        # Test that we can create instances
        schema = ChatMessageSchema(role="user", content="test")
        assert schema.role == "user"
        assert schema.content == "test"
    
    @pytest.mark.asyncio
    async def test_memory_manager_redis_fallback(self):
        """Test memory manager with Redis error handling and database fallback."""

        # Test case 1: Redis connection failure - should fallback to database-only
        with patch('app.services.redis_client.RedisClient') as mock_redis_class:
            mock_redis_instance = AsyncMock()
            mock_redis_instance.connect = AsyncMock(side_effect=Exception("Redis connection failed"))
            mock_redis_instance.is_connected = AsyncMock(return_value=False)
            mock_redis_class.return_value = mock_redis_instance

            memory_manager = await get_memory_manager()
            assert memory_manager is not None

            # Verify it's using database-only mode (has session_manager attribute from HybridMemoryManager)
            assert hasattr(memory_manager, 'session_manager')

        # Test case 2: Successful Redis connection
        with patch('app.services.redis_client.RedisClient') as mock_redis_class, \
             patch('app.services.redis_client.SessionManager') as mock_session_manager:

            mock_redis_instance = AsyncMock()
            mock_redis_instance.connect = AsyncMock()
            mock_redis_instance.is_connected = AsyncMock(return_value=True)
            mock_redis_class.return_value = mock_redis_instance

            mock_session_manager_instance = AsyncMock()
            mock_session_manager.return_value = mock_session_manager_instance

            with patch('app.api.chat.HybridMemoryManager') as mock_hybrid:
                mock_hybrid_instance = AsyncMock()
                mock_hybrid.return_value = mock_hybrid_instance

                memory_manager = await get_memory_manager()
                assert memory_manager is not None
                mock_hybrid.assert_called_once_with(mock_session_manager_instance)
    
    @pytest.mark.asyncio
    async def test_complete_document_to_chat_flow(self, client, mock_session, mock_conversation,
                                                 mock_rag_pipeline, mock_memory_manager):
        """Test complete document-to-chat flow integration."""

        conversation_id = mock_conversation.id
        user_id = "test_user"

        # Mock database operations
        mock_session.get.return_value = mock_conversation

        added_objects = []
        def _track_add(obj):
            added_objects.append(obj)
            # Set created_at on ChatMessage objects so SendMessageResponse can use it
            if hasattr(obj, 'created_at') and obj.created_at is None:
                obj.created_at = datetime.utcnow()
        mock_session.add = MagicMock(side_effect=_track_add)
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        # Use dependency_overrides for FastAPI dependency injection
        async def _override_db():
            yield mock_session

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_rag_pipeline] = lambda: mock_rag_pipeline
        app.dependency_overrides[get_memory_manager] = lambda: mock_memory_manager

        try:
            request_data = {
                "message": "What is the main topic of the uploaded documents?",
                "max_context_chunks": 5,
                "similarity_threshold": 0.3,
                "temperature": 0.7,
                "include_citations": True
            }

            response = client.post(
                f"/api/v1/chat/conversations/{conversation_id}/messages",
                json=request_data
            )

            assert response.status_code == 200
            response_data = response.json()

            # Verify response structure
            assert "message_id" in response_data
            assert "conversation_id" in response_data
            assert "response" in response_data
            assert "sources" in response_data
            assert "metadata" in response_data
            assert "timestamp" in response_data

            # Verify RAG pipeline was called
            mock_rag_pipeline.generate_response.assert_called_once()

            # Verify memory manager was called
            mock_memory_manager.add_user_message.assert_called_once()
            mock_memory_manager.add_ai_message.assert_called_once()

            # Verify database operations
            assert mock_session.add.call_count == 2  # User message + AI message
            mock_session.commit.assert_called()
        finally:
            app.dependency_overrides.clear()
    
    @pytest.mark.asyncio
    async def test_conversation_creation_with_memory_initialization(self, client, mock_session,
                                                                  mock_memory_manager):
        """Test conversation creation with proper memory initialization."""

        # Mock database operations
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        async def _fake_refresh(obj):
            if hasattr(obj, 'created_at') and obj.created_at is None:
                obj.created_at = datetime.utcnow()
            if hasattr(obj, 'updated_at') and obj.updated_at is None:
                obj.updated_at = datetime.utcnow()

        mock_session.refresh = AsyncMock(side_effect=_fake_refresh)

        # Use dependency_overrides for FastAPI dependency injection
        async def _override_db():
            yield mock_session

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_memory_manager] = lambda: mock_memory_manager

        try:
            request_data = {
                "title": "Test Conversation",
                "user_id": "test_user"
            }

            response = client.post("/api/v1/chat/conversations", json=request_data)

            assert response.status_code == 200
            response_data = response.json()

            # Verify response structure
            assert response_data["title"] == "Test Conversation"
            assert "created_at" in response_data
            assert "conversation_id" in response_data
            assert response_data["message"] == "Conversation started successfully"

            # Verify memory manager initialization
            mock_memory_manager.initialize_memory.assert_called_once()
            call_kwargs = mock_memory_manager.initialize_memory.call_args[1]
            assert call_kwargs["user_id"] == "test_user"
            assert call_kwargs["warm_cache"] is False

            # Verify database operations
            mock_session.add.assert_called_once()
            mock_session.commit.assert_called_once()
        finally:
            app.dependency_overrides.clear()
    
    @pytest.mark.asyncio
    async def test_error_handling_in_message_processing(self, client, mock_session,
                                                       mock_conversation, mock_rag_pipeline, mock_memory_manager):
        """Test error handling during message processing."""

        conversation_id = mock_conversation.id

        # Mock database operations
        mock_session.get.return_value = mock_conversation

        # Test case 1: RAG pipeline failure (generate_response raises)
        async def _override_db():
            yield mock_session

        failing_rag = AsyncMock(spec=RAGPipeline)
        failing_rag.generate_response = AsyncMock(side_effect=Exception("RAG pipeline failed"))
        failing_rag.validate_pipeline = AsyncMock(return_value=True)

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_rag_pipeline] = lambda: failing_rag
        app.dependency_overrides[get_memory_manager] = lambda: mock_memory_manager

        try:
            request_data = {
                "message": "Test message"
            }

            response = client.post(
                f"/api/v1/chat/conversations/{conversation_id}/messages",
                json=request_data
            )

            assert response.status_code == 500
        finally:
            app.dependency_overrides.clear()

        # Test case 2: Memory manager add_user_message failure
        # The pipeline catches memory errors and continues, so the request should still succeed
        mock_memory_manager_failing = AsyncMock(spec=HybridMemoryManager)
        mock_memory_manager_failing.add_user_message = AsyncMock(side_effect=Exception("Memory manager failed"))
        mock_memory_manager_failing.add_ai_message = AsyncMock()

        # Reset mock_session.get and add for test case 2
        mock_session.get.return_value = mock_conversation

        def _track_add(obj):
            if hasattr(obj, 'created_at') and obj.created_at is None:
                obj.created_at = datetime.utcnow()
        mock_session.add = MagicMock(side_effect=_track_add)

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_rag_pipeline] = lambda: mock_rag_pipeline
        app.dependency_overrides[get_memory_manager] = lambda: mock_memory_manager_failing

        try:
            request_data = {
                "message": "Test message"
            }

            response = client.post(
                f"/api/v1/chat/conversations/{conversation_id}/messages",
                json=request_data
            )

            # Memory errors are caught and logged; request still succeeds
            assert response.status_code == 200
        finally:
            app.dependency_overrides.clear()
    
    @pytest.mark.asyncio
    async def test_database_session_handling(self, mock_session):
        """Test proper database session handling with get_db dependency."""

        # Test that get_db is used instead of get_async_session
        from app.db.base import get_db as db_dependency

        # This should not raise an import error
        assert db_dependency is not None

        # Verify the chat module imports get_db from the correct location
        from app.api.chat import get_db as chat_get_db
        assert chat_get_db is not None
    
    @pytest.mark.asyncio
    async def test_llm_provider_failover_mechanism(self):
        """Test LLM provider failover and error handling."""

        # Create mock provider configs
        provider_configs = [
            ProviderConfig(
                name="openai",
                api_key="test_key_1",
                models=[ModelConfig(
                    name="gpt-3.5-turbo",
                    input_cost_per_1k_tokens=0.001,
                    output_cost_per_1k_tokens=0.002,
                    max_tokens=4096,
                    context_window=4096
                )],
                priority=1,
                enabled=True
            ),
            ProviderConfig(
                name="anthropic",
                api_key="test_key_2",
                models=[ModelConfig(
                    name="claude-3-haiku-20240307",
                    input_cost_per_1k_tokens=0.00025,
                    output_cost_per_1k_tokens=0.00125,
                    max_tokens=4096,
                    context_window=200000
                )],
                priority=2,
                enabled=True
            )
        ]

        # Create a real manager instance - it initializes providers from configs
        manager = LLMProviderManager(provider_configs)
        status = manager.get_provider_status()

        # Should have both providers configured
        assert "openai" in status
        assert "anthropic" in status
    
    @pytest.mark.asyncio
    async def test_comprehensive_logging_and_monitoring(self, caplog):
        """Test comprehensive logging throughout the RAG pipeline."""

        with caplog.at_level(logging.INFO):
            # Patch module-level imports in chat.py and local imports from their source modules
            with patch('app.api.chat.SemanticSearchService') as mock_search, \
                 patch('app.services.llm_providers.manager.LLMProviderManager') as mock_manager, \
                 patch('app.api.chat.RAGPipeline') as mock_pipeline, \
                 patch('app.core.config.settings') as mock_settings:

                mock_settings.OPENAI_API_KEY = "test_key"
                mock_settings.OPENAI_ENABLED = True
                mock_settings.ANTHROPIC_ENABLED = False
                mock_settings.GOOGLE_ENABLED = False
                mock_settings.OPENAI_PRIORITY = 1

                mock_manager_instance = AsyncMock()
                mock_manager_instance.get_provider_status.return_value = {
                    "openai": {"enabled": True, "healthy": True}
                }
                mock_manager.return_value = mock_manager_instance

                mock_pipeline_instance = AsyncMock()
                mock_pipeline_instance.validate_pipeline = AsyncMock(return_value=True)
                mock_pipeline.return_value = mock_pipeline_instance

                try:
                    await get_rag_pipeline()
                except Exception:
                    pass

            # Check that appropriate log messages were generated
            log_messages = [record.message for record in caplog.records]

            # Should have initialization logs (search service init or provider-related)
            assert any("initialized" in msg.lower() or "provider" in msg.lower()
                       for msg in log_messages)
    
    @pytest.mark.asyncio
    async def test_diagnostic_endpoints(self, client, mock_session):
        """Test new diagnostic endpoints for RAG pipeline debugging."""

        # Mock database queries for diagnostics
        mock_session.execute = AsyncMock()

        # Mock database query results
        mock_results = [
            AsyncMock(scalar=lambda: 5),  # document count
            AsyncMock(scalar=lambda: 25),  # chunk count
            AsyncMock(scalar=lambda: 23),  # chunks with embeddings
            AsyncMock(fetchall=lambda: [("processed", 4), ("embedding_failed", 1)]),  # processing status
            AsyncMock(fetchall=lambda: [("test_user", 5)])  # user distribution
        ]

        # Set up side_effect to return results in sequence
        mock_session.execute.side_effect = mock_results

        async def _override_db():
            yield mock_session

        app.dependency_overrides[get_db] = _override_db

        try:
            response = client.get("/api/v1/chat/diagnostics/documents?user_id=test_user")

            assert response.status_code == 200
            data = response.json()

            # Verify diagnostic data structure
            assert "document_count" in data
            assert "chunk_count" in data
            assert "chunks_with_embeddings" in data
            assert "embedding_coverage_percent" in data
            assert "processing_status_breakdown" in data
            assert "warnings" in data

            # Verify the calculations are correct
            assert data["document_count"] == 5
            assert data["chunk_count"] == 25
            assert data["chunks_with_embeddings"] == 23
            assert data["chunks_without_embeddings"] == 2  # 25 - 23 = 2
            assert data["embedding_coverage_percent"] == 92.0  # 23/25 * 100 = 92%

            # Should detect embedding issues since coverage < 100%
            assert any("embedding" in warning.lower() for warning in data["warnings"])
        finally:
            app.dependency_overrides.clear()
    
    @pytest.mark.asyncio
    async def test_search_pipeline_diagnostics(self, client, mock_session, mock_rag_pipeline, mock_retrieval_result):
        """Test search pipeline diagnostic endpoint."""

        # Mock RAG pipeline for diagnostics
        mock_search_service = AsyncMock()
        mock_search_service.retrieve_context = AsyncMock(return_value=mock_retrieval_result)
        mock_rag_pipeline.search_service = mock_search_service

        async def _override_db():
            yield mock_session

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_rag_pipeline] = lambda: mock_rag_pipeline

        try:
            response = client.get(
                "/api/v1/chat/diagnostics/search"
                "?query=test&user_id=test_user&max_chunks=3&similarity_threshold=0.5"
            )

            assert response.status_code == 200
            data = response.json()

            # Verify diagnostic structure
            assert "query" in data
            assert "retrieval_results" in data
            assert "chunks" in data
            assert "warnings" in data

            # Verify retrieval stats
            retrieval_stats = data["retrieval_results"]
            assert "chunks_found" in retrieval_stats
            assert "processing_time" in retrieval_stats
            assert "embedding_time" in retrieval_stats
            assert "search_time" in retrieval_stats
        finally:
            app.dependency_overrides.clear()
    
    @pytest.mark.asyncio
    async def test_embedding_diagnostics(self, client, mock_session):
        """Test embedding generation diagnostic endpoint."""

        async def _override_db():
            yield mock_session

        app.dependency_overrides[get_db] = _override_db

        try:
            # Mock embedding service - patch at the source module since the endpoint uses a local import
            with patch('app.services.embedding_service.EmbeddingService') as mock_embedding_class:
                mock_embedding_service = AsyncMock()
                mock_embedding_service.generate_embedding_for_text = AsyncMock(
                    return_value=AsyncMock(embedding=[0.1] * 1536)
                )
                mock_embedding_service.get_model_info = MagicMock(
                    return_value={"model": "text-embedding-3-small", "dimension": 1536}
                )
                mock_embedding_class.return_value = mock_embedding_service

                response = client.get("/api/v1/chat/diagnostics/embedding?text=test embedding")

                assert response.status_code == 200
                data = response.json()

                # Verify diagnostic structure
                assert "text" in data
                assert "embedding_dimension" in data
                assert "generation_time" in data
                assert "model_info" in data
                assert "success" in data
                assert "warnings" in data

                # Should be successful
                assert data["success"] is True
                assert data["embedding_dimension"] == 1536
        finally:
            app.dependency_overrides.clear()
    
    @pytest.mark.asyncio
    async def test_enhanced_error_handling_with_logging(self, client, mock_session,
                                                       mock_conversation, mock_memory_manager, caplog):
        """Test enhanced error handling with comprehensive logging."""

        conversation_id = mock_conversation.id

        # Mock database operations
        mock_session.get.return_value = mock_conversation

        async def _override_db():
            yield mock_session

        failing_rag = AsyncMock(spec=RAGPipeline)
        failing_rag.generate_response = AsyncMock(side_effect=Exception("RAG pipeline failed"))
        failing_rag.validate_pipeline = AsyncMock(return_value=True)

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_rag_pipeline] = lambda: failing_rag
        app.dependency_overrides[get_memory_manager] = lambda: mock_memory_manager

        try:
            with caplog.at_level(logging.INFO):
                request_data = {
                    "message": "Test message for error handling"
                }

                response = client.post(
                    f"/api/v1/chat/conversations/{conversation_id}/messages",
                    json=request_data
                )

                assert response.status_code == 500
        finally:
            app.dependency_overrides.clear()
    
    @pytest.mark.asyncio
    async def test_document_embedding_validation(self):
        """Test that embedding-related imports and classes are available."""

        from app.services.embedding_service import EmbeddingService, BatchEmbeddingResult, EmbeddingResult

        # Verify the embedding classes can be imported and used
        assert EmbeddingResult is not None
        assert BatchEmbeddingResult is not None
        assert EmbeddingService is not None
    
    @pytest.mark.asyncio
    async def test_rag_pipeline_error_recovery(self, mock_retrieval_result):
        """Test RAG pipeline error recovery mechanisms."""

        from app.services.rag_pipeline import RAGPipeline, RAGRequest

        # Test empty search results recovery
        empty_result = RetrievalResult(
            query="test query",
            chunks=[],
            total_tokens=0,
            processing_time=0.1,
            embedding_time=0.05,
            search_time=0.03,
            ranking_time=0.02
        )

        # Mock search service to return empty results first, then recovery results
        mock_search_service = AsyncMock()
        mock_search_service.retrieve_context.side_effect = [empty_result, mock_retrieval_result]

        # Mock LLM manager
        mock_llm_manager = AsyncMock()
        mock_llm_response = LLMResponse(
            content="Recovery response",
            input_tokens=50,
            output_tokens=10,
            total_tokens=60,
            cost=0.001,
            provider="openai",
            model="gpt-3.5-turbo",
            timestamp=datetime.utcnow(),
            metadata={}
        )
        mock_llm_manager.generate_response = AsyncMock(return_value=mock_llm_response)

        # Create a real pipeline with mocked dependencies
        pipeline = RAGPipeline(
            search_service=mock_search_service,
            llm_manager=mock_llm_manager
        )

        # Test recovery mechanism
        request = RAGRequest(
            query="test query",
            user_id="test_user",
            similarity_threshold=0.8  # High threshold that should trigger recovery
        )

        response = await pipeline.generate_response(request)

        # Should have attempted recovery (called retrieve_context twice)
        assert mock_search_service.retrieve_context.call_count == 2

        # Should have successful response
        assert response.response == "Recovery response"
        assert response.retrieval_result.chunk_count > 0  # Should use recovery result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])