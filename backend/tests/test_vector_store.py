"""
Integration tests for vector storage operations.
Tests PostgreSQL vector storage, similarity search, and document management.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4, UUID
from datetime import datetime

from app.services.vector_store import (
    VectorStoreService,
    PostgreSQLVectorStore,
    VectorStoreError,
    ChunkData,
    DocumentMetadata,
    SearchResult,
    SearchQuery
)
from app.services.embedding_service import EmbeddingResult, BatchEmbeddingResult


class TestChunkData:
    """Test ChunkData data class."""
    
    def test_chunk_data_creation(self):
        """Test creating chunk data."""
        chunk_id = uuid4()
        doc_id = uuid4()
        
        chunk = ChunkData(
            id=chunk_id,
            document_id=doc_id,
            chunk_index=0,
            content="Test content",
            start_position=0,
            end_position=12,
            token_count=3,
            embedding=[0.1, 0.2, 0.3],
            metadata={"source": "test"}
        )
        
        assert chunk.id == chunk_id
        assert chunk.document_id == doc_id
        assert chunk.content == "Test content"
        assert chunk.embedding == [0.1, 0.2, 0.3]
    
    def test_chunk_data_to_dict(self):
        """Test converting chunk data to dictionary."""
        chunk_id = uuid4()
        doc_id = uuid4()
        
        chunk = ChunkData(
            id=chunk_id,
            document_id=doc_id,
            chunk_index=0,
            content="Test content",
            start_position=0,
            end_position=12,
            token_count=3
        )
        
        chunk_dict = chunk.to_dict()
        
        assert chunk_dict["id"] == str(chunk_id)
        assert chunk_dict["document_id"] == str(doc_id)
        assert chunk_dict["content"] == "Test content"
        assert chunk_dict["metadata"] == {}


class TestDocumentMetadata:
    """Test DocumentMetadata data class."""
    
    def test_document_metadata_creation(self):
        """Test creating document metadata."""
        doc_id = uuid4()
        
        metadata = DocumentMetadata(
            id=doc_id,
            filename="test.txt",
            user_id="user123",
            upload_date="2024-01-01T00:00:00",
            file_size=1024,
            content_type="text/plain",
            processing_status="completed",
            chunk_count=5
        )
        
        assert metadata.id == doc_id
        assert metadata.filename == "test.txt"
        assert metadata.chunk_count == 5
    
    def test_document_metadata_to_dict(self):
        """Test converting document metadata to dictionary."""
        doc_id = uuid4()
        
        metadata = DocumentMetadata(
            id=doc_id,
            filename="test.txt",
            user_id="user123",
            upload_date="2024-01-01T00:00:00",
            file_size=1024,
            content_type="text/plain",
            processing_status="completed"
        )
        
        metadata_dict = metadata.to_dict()
        
        assert metadata_dict["id"] == str(doc_id)
        assert metadata_dict["filename"] == "test.txt"
        assert metadata_dict["chunk_count"] == 0  # Default value


class TestSearchQuery:
    """Test SearchQuery data class."""
    
    def test_valid_search_query(self):
        """Test creating a valid search query."""
        query = SearchQuery(
            query_text="test query",
            user_id="user123",
            limit=10,
            similarity_threshold=0.5
        )
        
        assert query.query_text == "test query"
        assert query.user_id == "user123"
        assert query.limit == 10
        assert query.similarity_threshold == 0.5
    
    def test_invalid_limit_zero(self):
        """Test that zero limit raises error."""
        with pytest.raises(ValueError, match="Limit must be positive"):
            SearchQuery(query_text="test", limit=0)
    
    def test_invalid_limit_too_high(self):
        """Test that limit over 100 raises error."""
        with pytest.raises(ValueError, match="Limit cannot exceed 100"):
            SearchQuery(query_text="test", limit=101)
    
    def test_invalid_similarity_threshold(self):
        """Test that invalid similarity threshold raises error."""
        with pytest.raises(ValueError, match="Similarity threshold must be between"):
            SearchQuery(query_text="test", similarity_threshold=1.5)


class TestPostgreSQLVectorStore:
    """Test PostgreSQL vector store implementation."""
    
    @pytest.fixture
    def mock_session(self):
        """Mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        session.execute = AsyncMock()
        return session
    
    @pytest.fixture
    def mock_session_factory(self, mock_session):
        """Mock session factory."""
        class MockSessionFactory:
            def __init__(self, session):
                self.session = session
            
            async def __aenter__(self):
                return self.session
            
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass
        
        def factory():
            return MockSessionFactory(mock_session)
        return factory
    
    @pytest.fixture
    def vector_store(self, mock_session_factory):
        """Create vector store with mocked session."""
        return PostgreSQLVectorStore(session_factory=mock_session_factory)
    
    @pytest.mark.asyncio
    async def test_store_chunks_success(self, vector_store, mock_session):
        """Test successful chunk storage."""
        doc_id = uuid4()
        chunk_id = uuid4()
        
        chunks = [
            ChunkData(
                id=chunk_id,
                document_id=doc_id,
                chunk_index=0,
                content="Test content",
                start_position=0,
                end_position=12,
                token_count=3,
                embedding=[0.1] * 1536
            )
        ]
        
        metadata = DocumentMetadata(
            id=doc_id,
            filename="test.txt",
            user_id="user123",
            upload_date="2024-01-01T00:00:00",
            file_size=1024,
            content_type="text/plain",
            processing_status="completed"
        )
        
        await vector_store.store_chunks(chunks, metadata)
        
        # Verify session operations
        assert mock_session.add.call_count == 1  # Document only
        mock_session.add_all.assert_called_once()  # Chunks added via add_all
        mock_session.commit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_store_chunks_empty_list(self, vector_store):
        """Test error when storing empty chunks list."""
        metadata = DocumentMetadata(
            id=uuid4(),
            filename="test.txt",
            user_id="user123",
            upload_date="2024-01-01T00:00:00",
            file_size=1024,
            content_type="text/plain",
            processing_status="completed"
        )
        
        with pytest.raises(VectorStoreError, match="Cannot store empty chunks list"):
            await vector_store.store_chunks([], metadata)
    
    @pytest.mark.asyncio
    async def test_store_chunks_missing_embedding(self, vector_store):
        """Test error when chunk is missing embedding."""
        doc_id = uuid4()
        
        chunks = [
            ChunkData(
                id=uuid4(),
                document_id=doc_id,
                chunk_index=0,
                content="Test content",
                start_position=0,
                end_position=12,
                token_count=3,
                embedding=None  # Missing embedding
            )
        ]
        
        metadata = DocumentMetadata(
            id=doc_id,
            filename="test.txt",
            user_id="user123",
            upload_date="2024-01-01T00:00:00",
            file_size=1024,
            content_type="text/plain",
            processing_status="completed"
        )
        
        with pytest.raises(VectorStoreError, match="missing embedding"):
            await vector_store.store_chunks(chunks, metadata)
    
    @pytest.mark.asyncio
    async def test_search_similar_success(self, vector_store, mock_session):
        """Test successful similarity search."""
        query = SearchQuery(
            query_text="test query",
            user_id="user123",
            limit=5
        )
        
        query_embedding = [0.1] * 1536
        
        # Mock database result
        mock_chunk = Mock()
        mock_chunk.id = uuid4()
        mock_chunk.document_id = uuid4()
        mock_chunk.chunk_index = 0
        mock_chunk.content = "Test content"
        mock_chunk.start_position = 0
        mock_chunk.end_position = 12
        mock_chunk.token_count = 3
        mock_chunk.embedding = [0.1] * 1536
        
        mock_document = Mock()
        mock_document.id = mock_chunk.document_id
        mock_document.filename = "test.txt"
        mock_document.user_id = "user123"
        mock_document.upload_date = datetime.now()
        mock_document.file_size = 1024
        mock_document.content_type = "text/plain"
        mock_document.processing_status = "completed"
        
        mock_result = Mock()
        mock_result.fetchall.return_value = [
            (mock_chunk, mock_document, 0.95, 1)
        ]
        
        mock_session.execute.return_value = mock_result
        
        results = await vector_store.search_similar(query, query_embedding)
        
        assert len(results) == 1
        assert isinstance(results[0], SearchResult)
        assert results[0].similarity_score == 0.95
        assert results[0].rank == 1
        assert results[0].chunk.content == "Test content"
    
    @pytest.mark.asyncio
    async def test_delete_document_success(self, vector_store, mock_session):
        """Test successful document deletion."""
        doc_id = uuid4()
        
        # Mock successful deletion
        mock_result = Mock()
        mock_result.rowcount = 1
        mock_session.execute.return_value = mock_result
        
        result = await vector_store.delete_document(doc_id, "user123")
        
        assert result is True
        mock_session.commit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_delete_document_not_found(self, vector_store, mock_session):
        """Test document deletion when document not found."""
        doc_id = uuid4()
        
        # Mock no deletion
        mock_result = Mock()
        mock_result.rowcount = 0
        mock_session.execute.return_value = mock_result
        
        result = await vector_store.delete_document(doc_id, "user123")
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_get_document_chunks_success(self, vector_store, mock_session):
        """Test successful retrieval of document chunks."""
        doc_id = uuid4()
        
        # Mock chunk results
        mock_chunk = Mock()
        mock_chunk.id = uuid4()
        mock_chunk.document_id = doc_id
        mock_chunk.chunk_index = 0
        mock_chunk.content = "Test content"
        mock_chunk.start_position = 0
        mock_chunk.end_position = 12
        mock_chunk.token_count = 3
        mock_chunk.embedding = [0.1] * 1536
        
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [mock_chunk]
        mock_session.execute.return_value = mock_result
        
        chunks = await vector_store.get_document_chunks(doc_id, "user123")
        
        assert len(chunks) == 1
        assert isinstance(chunks[0], ChunkData)
        assert chunks[0].content == "Test content"
    
    @pytest.mark.asyncio
    async def test_get_document_metadata_success(self, vector_store, mock_session):
        """Test successful retrieval of document metadata."""
        doc_id = uuid4()
        
        # Mock document result
        mock_document = Mock()
        mock_document.id = doc_id
        mock_document.filename = "test.txt"
        mock_document.user_id = "user123"
        mock_document.upload_date = datetime.now()
        mock_document.file_size = 1024
        mock_document.content_type = "text/plain"
        mock_document.processing_status = "completed"
        
        mock_result = Mock()
        mock_result.first.return_value = (mock_document, 5)  # 5 chunks
        mock_session.execute.return_value = mock_result
        
        metadata = await vector_store.get_document_metadata(doc_id, "user123")
        
        assert metadata is not None
        assert isinstance(metadata, DocumentMetadata)
        assert metadata.filename == "test.txt"
        assert metadata.chunk_count == 5
    
    @pytest.mark.asyncio
    async def test_get_document_metadata_not_found(self, vector_store, mock_session):
        """Test document metadata retrieval when document not found."""
        doc_id = uuid4()
        
        mock_result = Mock()
        mock_result.first.return_value = None
        mock_session.execute.return_value = mock_result
        
        metadata = await vector_store.get_document_metadata(doc_id, "user123")
        
        assert metadata is None
    
    @pytest.mark.asyncio
    async def test_get_storage_stats(self, vector_store, mock_session):
        """Test getting storage statistics."""
        # Mock count results
        doc_count_result = Mock()
        doc_count_result.scalar.return_value = 10
        
        chunk_count_result = Mock()
        chunk_count_result.scalar.return_value = 50
        
        mock_session.execute.side_effect = [doc_count_result, chunk_count_result]
        
        stats = await vector_store.get_storage_stats("user123")
        
        assert stats["total_documents"] == 10
        assert stats["total_chunks"] == 50
        assert stats["average_chunks_per_document"] == 5.0


class TestVectorStoreService:
    """Test VectorStoreService main service class."""
    
    @pytest.fixture
    def mock_vector_store(self):
        """Mock vector store."""
        return AsyncMock()
    
    @pytest.fixture
    def mock_embedding_service(self):
        """Mock embedding service."""
        service = AsyncMock()
        
        # Mock batch embedding generation to return embeddings for any chunk ID
        async def mock_generate_embeddings_for_chunks(chunks, batch_size=50):
            results = []
            for chunk in chunks:
                embedding_result = EmbeddingResult(
                    id=chunk["id"],
                    embedding=[0.1] * 1536,
                    token_count=10,
                    model="test-model"
                )
                results.append(embedding_result)
            
            return BatchEmbeddingResult(
                results=results,
                total_tokens=len(chunks) * 10,
                total_processing_time=1.0,
                failed_requests=[]
            )
        
        service.generate_embeddings_for_chunks.side_effect = mock_generate_embeddings_for_chunks
        
        # Mock single embedding result
        embedding_result = EmbeddingResult(
            id="query",
            embedding=[0.1] * 1536,
            token_count=10,
            model="test-model"
        )
        service.generate_embedding_for_text.return_value = embedding_result
        
        return service
    
    @pytest.fixture
    def service(self, mock_vector_store, mock_embedding_service):
        """Create service with mocked dependencies."""
        return VectorStoreService(
            vector_store=mock_vector_store,
            embedding_service=mock_embedding_service
        )
    
    @pytest.mark.asyncio
    async def test_store_document_chunks_success(
        self,
        service,
        mock_vector_store,
        mock_embedding_service
    ):
        """Test successful document chunk storage."""
        doc_id = uuid4()
        chunk_id = uuid4()
        
        chunks = [
            {
                "id": chunk_id,
                "document_id": doc_id,
                "chunk_index": 0,
                "content": "Test content",
                "start_position": 0,
                "end_position": 12,
                "token_count": 3
            }
        ]
        
        document_metadata = {
            "id": doc_id,
            "filename": "test.txt",
            "user_id": "user123",
            "file_size": 1024,
            "content_type": "text/plain"
        }
        
        await service.store_document_chunks(chunks, document_metadata)
        
        # Verify embedding generation was called
        mock_embedding_service.generate_embeddings_for_chunks.assert_called_once()
        
        # Verify vector store was called
        mock_vector_store.store_chunks.assert_called_once()
        
        # Check the arguments passed to store_chunks
        call_args = mock_vector_store.store_chunks.call_args
        stored_chunks, stored_metadata = call_args[0]
        
        assert len(stored_chunks) == 1
        assert stored_chunks[0].embedding == [0.1] * 1536
        assert stored_metadata.filename == "test.txt"
    
    @pytest.mark.asyncio
    async def test_store_document_chunks_embedding_failures(
        self,
        service,
        mock_vector_store,
        mock_embedding_service
    ):
        """Test handling of embedding generation failures."""
        # Override the mock to return failures
        batch_result = BatchEmbeddingResult(
            results=[],
            total_tokens=0,
            total_processing_time=1.0,
            failed_requests=["chunk-1"]
        )
        
        # Clear the side_effect and set return_value
        mock_embedding_service.generate_embeddings_for_chunks.side_effect = None
        mock_embedding_service.generate_embeddings_for_chunks.return_value = batch_result
        
        chunks = [
            {
                "id": uuid4(),
                "document_id": uuid4(),
                "chunk_index": 0,
                "content": "Test content",
                "start_position": 0,
                "end_position": 12,
                "token_count": 3
            }
        ]
        
        document_metadata = {
            "id": uuid4(),
            "filename": "test.txt",
            "user_id": "user123",
            "file_size": 1024,
            "content_type": "text/plain"
        }
        
        with pytest.raises(VectorStoreError, match="No chunks have embeddings"):
            await service.store_document_chunks(chunks, document_metadata)
    
    @pytest.mark.asyncio
    async def test_search_documents_success(
        self,
        service,
        mock_vector_store,
        mock_embedding_service
    ):
        """Test successful document search."""
        # Mock search results
        search_result = SearchResult(
            chunk=ChunkData(
                id=uuid4(),
                document_id=uuid4(),
                chunk_index=0,
                content="Test content",
                start_position=0,
                end_position=12,
                token_count=3
            ),
            document=DocumentMetadata(
                id=uuid4(),
                filename="test.txt",
                user_id="user123",
                upload_date="2024-01-01T00:00:00",
                file_size=1024,
                content_type="text/plain",
                processing_status="completed"
            ),
            similarity_score=0.95,
            rank=1
        )
        
        mock_vector_store.search_similar.return_value = [search_result]
        
        results = await service.search_documents(
            query_text="test query",
            user_id="user123",
            limit=5
        )
        
        assert len(results) == 1
        assert results[0].similarity_score == 0.95
        
        # Verify embedding generation was called
        mock_embedding_service.generate_embedding_for_text.assert_called_once_with(
            "test query"
        )
        
        # Verify search was called
        mock_vector_store.search_similar.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_delete_document(self, service, mock_vector_store):
        """Test document deletion."""
        doc_id = uuid4()
        mock_vector_store.delete_document.return_value = True
        
        result = await service.delete_document(doc_id, "user123")
        
        assert result is True
        mock_vector_store.delete_document.assert_called_once_with(doc_id, "user123")
    
    @pytest.mark.asyncio
    async def test_get_document_chunks(self, service, mock_vector_store):
        """Test getting document chunks."""
        doc_id = uuid4()
        
        chunk_data = ChunkData(
            id=uuid4(),
            document_id=doc_id,
            chunk_index=0,
            content="Test content",
            start_position=0,
            end_position=12,
            token_count=3
        )
        
        mock_vector_store.get_document_chunks.return_value = [chunk_data]
        
        chunks = await service.get_document_chunks(doc_id, "user123")
        
        assert len(chunks) == 1
        assert chunks[0].content == "Test content"
        mock_vector_store.get_document_chunks.assert_called_once_with(doc_id, "user123")
    
    @pytest.mark.asyncio
    async def test_get_document_metadata(self, service, mock_vector_store):
        """Test getting document metadata."""
        doc_id = uuid4()
        
        metadata = DocumentMetadata(
            id=doc_id,
            filename="test.txt",
            user_id="user123",
            upload_date="2024-01-01T00:00:00",
            file_size=1024,
            content_type="text/plain",
            processing_status="completed"
        )
        
        mock_vector_store.get_document_metadata.return_value = metadata
        
        result = await service.get_document_metadata(doc_id, "user123")
        
        assert result.filename == "test.txt"
        mock_vector_store.get_document_metadata.assert_called_once_with(doc_id, "user123")
    
    @pytest.mark.asyncio
    async def test_get_storage_stats(self, service, mock_vector_store):
        """Test getting storage statistics."""
        stats = {
            "total_documents": 10,
            "total_chunks": 50,
            "average_chunks_per_document": 5.0
        }
        
        mock_vector_store.get_storage_stats.return_value = stats
        
        result = await service.get_storage_stats("user123")
        
        assert result == stats
        mock_vector_store.get_storage_stats.assert_called_once_with("user123")


class TestVectorStoreError:
    """Test VectorStoreError exception class."""
    
    def test_basic_error(self):
        """Test basic error creation."""
        error = VectorStoreError("Test error message")
        
        assert str(error) == "Test error message"
        assert error.message == "Test error message"
        assert error.operation is None
        assert error.document_id is None
        assert error.original_error is None
    
    def test_full_error(self):
        """Test error with all parameters."""
        doc_id = uuid4()
        original = ValueError("Original error")
        
        error = VectorStoreError(
            message="Wrapper error",
            operation="store_chunks",
            document_id=doc_id,
            original_error=original
        )
        
        assert error.message == "Wrapper error"
        assert error.operation == "store_chunks"
        assert error.document_id == doc_id
        assert error.original_error == original


class TestIntegrationScenarios:
    """Test integration scenarios combining multiple operations."""
    
    @pytest.fixture
    def mock_dependencies(self):
        """Mock all dependencies for integration tests."""
        vector_store = AsyncMock()
        embedding_service = AsyncMock()
        
        # Mock batch embedding generation to return embeddings for any chunk ID
        async def mock_generate_embeddings_for_chunks(chunks, batch_size=50):
            results = []
            for chunk in chunks:
                embedding_result = EmbeddingResult(
                    id=chunk["id"],
                    embedding=[0.1] * 1536,
                    token_count=10,
                    model="test-model"
                )
                results.append(embedding_result)
            
            return BatchEmbeddingResult(
                results=results,
                total_tokens=len(chunks) * 10,
                total_processing_time=1.0,
                failed_requests=[]
            )
        
        embedding_service.generate_embeddings_for_chunks.side_effect = mock_generate_embeddings_for_chunks
        
        # Mock single embedding result
        embedding_result = EmbeddingResult(
            id="query",
            embedding=[0.1] * 1536,
            token_count=10,
            model="test-model"
        )
        embedding_service.generate_embedding_for_text.return_value = embedding_result
        
        return vector_store, embedding_service
    
    @pytest.mark.asyncio
    async def test_full_document_lifecycle(self, mock_dependencies):
        """Test complete document lifecycle: store, search, retrieve, delete."""
        vector_store, embedding_service = mock_dependencies
        service = VectorStoreService(
            vector_store=vector_store,
            embedding_service=embedding_service
        )
        
        doc_id = uuid4()
        chunk_id = uuid4()
        
        # 1. Store document chunks
        chunks = [
            {
                "id": chunk_id,
                "document_id": doc_id,
                "chunk_index": 0,
                "content": "Test content for search",
                "start_position": 0,
                "end_position": 23,
                "token_count": 5
            }
        ]
        
        document_metadata = {
            "id": doc_id,
            "filename": "test.txt",
            "user_id": "user123",
            "file_size": 1024,
            "content_type": "text/plain"
        }
        
        await service.store_document_chunks(chunks, document_metadata)
        
        # 2. Search for similar content
        search_result = SearchResult(
            chunk=ChunkData(
                id=chunk_id,
                document_id=doc_id,
                chunk_index=0,
                content="Test content for search",
                start_position=0,
                end_position=23,
                token_count=5
            ),
            document=DocumentMetadata(
                id=doc_id,
                filename="test.txt",
                user_id="user123",
                upload_date="2024-01-01T00:00:00",
                file_size=1024,
                content_type="text/plain",
                processing_status="completed"
            ),
            similarity_score=0.95,
            rank=1
        )
        
        vector_store.search_similar.return_value = [search_result]
        
        search_results = await service.search_documents(
            query_text="search content",
            user_id="user123"
        )
        
        assert len(search_results) == 1
        assert search_results[0].chunk.content == "Test content for search"
        
        # 3. Get document chunks
        vector_store.get_document_chunks.return_value = [search_result.chunk]
        
        retrieved_chunks = await service.get_document_chunks(doc_id, "user123")
        assert len(retrieved_chunks) == 1
        
        # 4. Delete document
        vector_store.delete_document.return_value = True
        
        deleted = await service.delete_document(doc_id, "user123")
        assert deleted is True
        
        # Verify all operations were called
        vector_store.store_chunks.assert_called_once()
        vector_store.search_similar.assert_called_once()
        vector_store.get_document_chunks.assert_called_once()
        vector_store.delete_document.assert_called_once()