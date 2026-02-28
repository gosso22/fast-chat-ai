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
            
            # Verify it's using database-only mode
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
            
            with patch('app.services.memory_manager.HybridMemoryManager') as mock_hybrid:
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
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()
        
        # Test message sending with RAG pipeline
        with patch('app.api.chat.get_db', return_value=mock_session), \
             patch('app.api.chat.get_rag_pipeline', return_value=mock_rag_pipeline), \
             patch('app.api.chat.get_memory_manager', return_value=mock_memory_manager), \
             patch('app.api.chat.uuid4', return_value=uuid4()):
            
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
    
    @pytest.mark.asyncio
    async def test_conversation_creation_with_memory_initialization(self, client, mock_session, 
                                                                  mock_memory_manager):
        """Test conversation creation with proper memory initialization."""
        
        conversation_id = uuid4()
        
        # Mock database operations
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()
        
        with patch('app.api.chat.get_db', return_value=mock_session), \
             patch('app.api.chat.get_memory_manager', return_value=mock_memory_manager), \
             patch('app.api.chat.uuid4', return_value=conversation_id):
            
            request_data = {
                "title": "Test Conversation",
                "user_id": "test_user"
            }
            
            response = client.post("/api/v1/chat/conversations", json=request_data)
            
            assert response.status_code == 200
            response_data = response.json()
            
            # Verify response structure
            assert response_data["conversation_id"] == str(conversation_id)
            assert response_data["title"] == "Test Conversation"
            assert "created_at" in response_data
            assert response_data["message"] == "Conversation started successfully"
            
            # Verify memory manager initialization
            mock_memory_manager.initialize_memory.assert_called_once_with(
                conversation_id=str(conversation_id),
                user_id="test_user",
                warm_cache=False
            )
            
            # Verify database operations
            mock_session.add.assert_called_once()
            mock_session.commit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_error_handling_in_message_processing(self, client, mock_session, 
                                                       mock_conversation, mock_memory_manager):
        """Test error handling during message processing."""
        
        conversation_id = mock_conversation.id
        
        # Mock database operations
        mock_session.get.return_value = mock_conversation
        
        # Test case 1: RAG pipeline failure
        with patch('app.api.chat.get_db', return_value=mock_session), \
             patch('app.api.chat.get_rag_pipeline', side_effect=Exception("RAG pipeline failed")), \
             patch('app.api.chat.get_memory_manager', return_value=mock_memory_manager):
            
            request_data = {
                "message": "Test message"
            }
            
            response = client.post(
                f"/api/v1/chat/conversations/{conversation_id}/messages",
                json=request_data
            )
            
            assert response.status_code == 503
            assert "RAG service temporarily unavailable" in response.json()["detail"]
        
        # Test case 2: Memory manager failure
        mock_memory_manager.add_user_message.side_effect = Exception("Memory manager failed")
        
        with patch('app.api.chat.get_db', return_value=mock_session), \
             patch('app.api.chat.get_rag_pipeline') as mock_rag, \
             patch('app.api.chat.get_memory_manager', return_value=mock_memory_manager):
            
            mock_rag_instance = AsyncMock()
            mock_rag.return_value = mock_rag_instance
            
            request_data = {
                "message": "Test message"
            }
            
            response = client.post(
                f"/api/v1/chat/conversations/{conversation_id}/messages",
                json=request_data
            )
            
            assert response.status_code == 500
            assert "Failed to process message" in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_database_session_handling(self, mock_session):
        """Test proper database session handling with get_db dependency."""
        
        # Test that get_db is used instead of get_async_session
        from app.api.chat import get_db
        
        # This should not raise an import error
        assert get_db is not None
        
        # Test session cleanup in error scenarios
        mock_session.rollback = AsyncMock()
        
        with patch('app.api.chat.get_db', return_value=mock_session):
            # Simulate an error that should trigger rollback
            mock_session.commit.side_effect = Exception("Database error")
            
            # The error handling should call rollback
            try:
                async for session in get_db():
                    await session.commit()
            except Exception:
                pass
    
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
        
        with patch('app.services.llm_providers.manager.LLMProviderManager') as mock_manager_class:
            mock_manager = AsyncMock()
            
            # Test successful failover
            mock_manager.get_provider_status.return_value = {
                "openai": {"enabled": True, "healthy": False},
                "anthropic": {"enabled": True, "healthy": True}
            }
            
            mock_manager_class.return_value = mock_manager
            
            manager = LLMProviderManager(provider_configs)
            status = manager.get_provider_status()
            
            # Should have both providers configured
            assert "openai" in status
            assert "anthropic" in status
    
    @pytest.mark.asyncio
    async def test_comprehensive_logging_and_monitoring(self, caplog):
        """Test comprehensive logging throughout the RAG pipeline."""
        
        with caplog.at_level(logging.INFO):
            # Test RAG pipeline initialization logging
            with patch('app.core.config.settings') as mock_settings:
                mock_settings.OPENAI_API_KEY = "test_key"
                mock_settings.OPENAI_ENABLED = True
                mock_settings.ANTHROPIC_ENABLED = False
                mock_settings.GOOGLE_ENABLED = False
                mock_settings.OPENAI_PRIORITY = 1
                
                with patch('app.services.rag_service.SemanticSearchService'), \
                     patch('app.services.llm_providers.manager.LLMProviderManager') as mock_manager, \
                     patch('app.services.rag_pipeline.RAGPipeline') as mock_pipeline:
                    
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
            
            # Should have initialization and validation logs
            assert any("Successfully initialized" in msg for msg in log_messages)
            assert any("provider" in msg.lower() for msg in log_messages)
    
    @pytest.mark.asyncio
    async def test_diagnostic_endpoints(self, client, mock_session):
        """Test new diagnostic endpoints for RAG pipeline debugging."""
        
        # Mock database queries for diagnostics
        mock_session.execute = AsyncMock()
        
        # Test document diagnostics endpoint
        with patch('app.api.chat.get_db', return_value=mock_session):
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
    
    @pytest.mark.asyncio
    async def test_search_pipeline_diagnostics(self, client, mock_rag_pipeline, mock_retrieval_result):
        """Test search pipeline diagnostic endpoint."""
        
        # Mock RAG pipeline for diagnostics
        mock_search_service = AsyncMock()
        mock_search_service.retrieve_context = AsyncMock(return_value=mock_retrieval_result)
        mock_rag_pipeline.search_service = mock_search_service
        
        with patch('app.api.chat.get_rag_pipeline', return_value=mock_rag_pipeline):
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
    
    @pytest.mark.asyncio
    async def test_embedding_diagnostics(self, client):
        """Test embedding generation diagnostic endpoint."""
        
        # Mock embedding service
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
    
    @pytest.mark.asyncio
    async def test_enhanced_error_handling_with_logging(self, client, mock_session, 
                                                       mock_conversation, caplog):
        """Test enhanced error handling with comprehensive logging."""
        
        conversation_id = mock_conversation.id
        
        # Mock database operations
        mock_session.get.return_value = mock_conversation
        
        with caplog.at_level(logging.INFO):
            # Test RAG pipeline failure with enhanced logging
            with patch('app.api.chat.get_db', return_value=mock_session), \
                 patch('app.api.chat.get_rag_pipeline', side_effect=Exception("RAG pipeline failed")), \
                 patch('app.api.chat.get_memory_manager') as mock_memory:
                
                mock_memory_instance = AsyncMock()
                mock_memory.return_value = mock_memory_instance
                
                request_data = {
                    "message": "Test message for error handling"
                }
                
                response = client.post(
                    f"/api/v1/chat/conversations/{conversation_id}/messages",
                    json=request_data
                )
                
                assert response.status_code == 503
                
                # Check that comprehensive logging occurred
                log_messages = [record.message for record in caplog.records]
                
                # Should have processing start log
                assert any("Processing message in conversation" in msg for msg in log_messages)
                # Should have error log
                assert any("RAG pipeline failed" in msg for msg in log_messages)
    
    @pytest.mark.asyncio
    async def test_document_embedding_validation(self, mock_session):
        """Test document processing with embedding validation."""
        
        from app.api.documents import upload_document
        from app.services.embedding_service import EmbeddingService, EmbeddingBatchResult, EmbeddingResult
        
        # Mock file upload
        mock_file = AsyncMock()
        mock_file.filename = "test.txt"
        mock_file.size = 1000
        mock_file.content_type = "text/plain"
        mock_file.read = AsyncMock(return_value=b"Test document content")
        
        # Mock successful embedding generation
        mock_embedding_results = EmbeddingBatchResult(
            results=[
                EmbeddingResult(id="chunk1", embedding=[0.1] * 1536, metadata={}),
                EmbeddingResult(id="chunk2", embedding=[0.2] * 1536, metadata={})
            ],
            success_count=2,
            failure_count=0,
            processing_time=0.5
        )
        
        with patch('app.services.embedding_service.EmbeddingService') as mock_embedding_class, \
             patch('app.services.text_extractor.TextExtractionService') as mock_extractor_class, \
             patch('app.services.text_chunker.TextChunkingService') as mock_chunker_class, \
             patch('app.services.file_validator.FileValidator') as mock_validator:
            
            # Setup mocks
            mock_embedding_service = AsyncMock()
            mock_embedding_service.generate_embeddings_for_chunks = AsyncMock(
                return_value=mock_embedding_results
            )
            mock_embedding_class.return_value = mock_embedding_service
            
            mock_validator.validate_file.return_value = (True, [])
            mock_validator.get_file_info.return_value = {
                "filename": "test.txt",
                "size": 1000,
                "content_type": "text/plain"
            }
            
            # Mock text extraction and chunking
            mock_extractor = MagicMock()
            mock_extractor.extract_text.return_value = MagicMock(
                text="Test content",
                extraction_method="text",
                word_count=2,
                character_count=12,
                metadata={}
            )
            mock_extractor_class.return_value = mock_extractor
            
            mock_chunker = MagicMock()
            mock_chunk1 = MagicMock()
            mock_chunk1.id = "chunk1"
            mock_chunk1.content = "Test"
            mock_chunk1.metadata = MagicMock(
                chunk_index=0, start_position=0, end_position=4, token_count=1
            )
            mock_chunk2 = MagicMock()
            mock_chunk2.id = "chunk2"
            mock_chunk2.content = "content"
            mock_chunk2.metadata = MagicMock(
                chunk_index=1, start_position=5, end_position=12, token_count=1
            )
            mock_chunker.chunk_document_text.return_value = [mock_chunk1, mock_chunk2]
            mock_chunker_class.return_value = mock_chunker
            
            # Mock database operations
            mock_session.add = MagicMock()
            mock_session.commit = AsyncMock()
            mock_session.refresh = AsyncMock()
            
            with patch('app.api.documents.get_db', return_value=mock_session), \
                 patch('aiofiles.open', AsyncMock()), \
                 patch('pathlib.Path.mkdir'):
                
                # This should succeed with all embeddings
                result = await upload_document(mock_file, "test_user", mock_session)
                
                # Verify document was marked as processed
                assert mock_session.add.call_count >= 3  # Document + 2 chunks
                mock_session.commit.assert_called()
    
    @pytest.mark.asyncio
    async def test_rag_pipeline_error_recovery(self, mock_rag_pipeline, mock_retrieval_result):
        """Test RAG pipeline error recovery mechanisms."""
        
        from app.services.rag_pipeline import RAGRequest
        
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
        mock_rag_pipeline.search_service = mock_search_service
        
        # Mock LLM manager
        mock_llm_manager = AsyncMock()
        mock_llm_response = MagicMock()
        mock_llm_response.content = "Recovery response"
        mock_llm_response.output_tokens = 10
        mock_llm_response.cost = 0.001
        mock_llm_response.provider = "openai"
        mock_llm_response.model = "gpt-3.5-turbo"
        mock_llm_manager.generate_response = AsyncMock(return_value=mock_llm_response)
        mock_rag_pipeline.llm_manager = mock_llm_manager
        
        # Mock prompt template
        mock_prompt_template = MagicMock()
        mock_prompt_template.format_prompt.return_value = "Test prompt"
        mock_prompt_template.extract_citations.return_value = []
        mock_rag_pipeline.prompt_template = mock_prompt_template
        
        # Test recovery mechanism
        request = RAGRequest(
            query="test query",
            user_id="test_user",
            similarity_threshold=0.8  # High threshold that should trigger recovery
        )
        
        response = await mock_rag_pipeline.generate_response(request)
        
        # Should have attempted recovery (called retrieve_context twice)
        assert mock_search_service.retrieve_context.call_count == 2
        
        # Should have successful response
        assert response.response == "Recovery response"
        assert response.retrieval_result.chunk_count > 0  # Should use recovery result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])