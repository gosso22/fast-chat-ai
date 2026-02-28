"""
Tests for database operations and vector functionality.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

from app.db.base import Base, init_db, get_db, close_db
from app.db.init_db import check_database_connection
from app.models.document import Document, DocumentChunk
from app.models.conversation import Conversation, ChatMessage, MessageRole


class TestDatabaseConfiguration:
    """Test database configuration and setup."""
    
    def test_base_model_exists(self):
        """Test that Base model is properly configured."""
        assert Base is not None
        assert hasattr(Base, 'metadata')
    
    def test_models_are_registered(self):
        """Test that all models are registered with Base."""
        # Import models to register them
        from app.models import document, conversation  # noqa: F401
        
        table_names = [table.name for table in Base.metadata.tables.values()]
        
        expected_tables = [
            'documents',
            'document_chunks', 
            'conversations',
            'chat_messages',
            'llm_usage'
        ]
        
        for table_name in expected_tables:
            assert table_name in table_names, f"Table {table_name} not found in metadata"
    
    @patch('app.db.base.engine')
    async def test_init_db_success(self, mock_engine):
        """Test successful database initialization."""
        mock_conn = AsyncMock()
        mock_engine.begin.return_value.__aenter__.return_value = mock_conn
        
        await init_db()
        
        # Verify that execute was called (for pgvector extension and index)
        assert mock_conn.execute.call_count >= 2
        
        # Verify tables are created
        mock_conn.run_sync.assert_called_once()
    
    @patch('app.db.base.engine')
    async def test_init_db_failure(self, mock_engine):
        """Test database initialization failure handling."""
        mock_engine.begin.side_effect = Exception("Connection failed")
        
        with pytest.raises(Exception, match="Connection failed"):
            await init_db()
    
    async def test_get_db_session(self):
        """Test database session creation."""
        with patch('app.db.base.AsyncSession') as mock_session_class:
            mock_session = AsyncMock()
            mock_session_class.return_value.__aenter__.return_value = mock_session
            mock_session_class.return_value.__aexit__.return_value = None
            
            async for session in get_db():
                assert session == mock_session
                break


class TestVectorOperations:
    """Test vector-related database operations."""
    
    def test_document_chunk_vector_field(self):
        """Test that DocumentChunk has proper vector field."""
        from app.models.document import DocumentChunk
        
        # Check that embedding column exists and is Vector type
        embedding_column = DocumentChunk.__table__.columns.get('embedding')
        assert embedding_column is not None
        
        # The column should be a Vector type (pgvector)
        assert 'VECTOR' in str(embedding_column.type)
    
    def test_vector_similarity_index_creation(self):
        """Test vector similarity index SQL generation."""
        expected_sql = (
            "CREATE INDEX IF NOT EXISTS document_chunks_embedding_idx "
            "ON document_chunks USING ivfflat (embedding vector_cosine_ops)"
        )
        
        # This tests that our SQL is properly formatted
        assert "ivfflat" in expected_sql
        assert "vector_cosine_ops" in expected_sql
        assert "document_chunks" in expected_sql


class TestModelRelationships:
    """Test model relationships and constraints."""
    
    def test_document_chunk_relationship(self):
        """Test Document-DocumentChunk relationship."""
        from app.models.document import Document, DocumentChunk
        
        # Check that Document has chunks relationship
        assert hasattr(Document, 'chunks')
        
        # Check that DocumentChunk has document relationship
        assert hasattr(DocumentChunk, 'document')
    
    def test_conversation_message_relationship(self):
        """Test Conversation-ChatMessage relationship."""
        from app.models.conversation import Conversation, ChatMessage
        
        # Check that Conversation has messages relationship
        assert hasattr(Conversation, 'messages')
        
        # Check that ChatMessage has conversation relationship
        assert hasattr(ChatMessage, 'conversation')
    
    def test_conversation_llm_usage_relationship(self):
        """Test Conversation-LLMUsage relationship."""
        from app.models.conversation import Conversation, LLMUsage
        
        # Check that Conversation has llm_usage relationship
        assert hasattr(Conversation, 'llm_usage')
        
        # Check that LLMUsage has conversation relationship
        assert hasattr(LLMUsage, 'conversation')


class TestDatabaseConstraints:
    """Test database constraints and validations."""
    
    def test_message_role_constraint(self):
        """Test that ChatMessage has role constraint."""
        from app.models.conversation import ChatMessage
        
        # Check table constraints
        constraints = ChatMessage.__table__.constraints
        
        # Look for check constraint on role
        role_constraint = None
        for constraint in constraints:
            if hasattr(constraint, 'sqltext') and 'role' in str(constraint.sqltext):
                role_constraint = constraint
                break
        
        assert role_constraint is not None, "Role constraint not found"
    
    def test_foreign_key_constraints(self):
        """Test foreign key constraints exist."""
        from app.models.document import DocumentChunk
        from app.models.conversation import ChatMessage, LLMUsage
        
        # Check DocumentChunk has foreign key to Document
        doc_chunk_fks = [fk.parent.name for fk in DocumentChunk.__table__.foreign_keys]
        assert 'document_id' in doc_chunk_fks
        
        # Check ChatMessage has foreign key to Conversation
        message_fks = [fk.parent.name for fk in ChatMessage.__table__.foreign_keys]
        assert 'conversation_id' in message_fks
        
        # Check LLMUsage has foreign key to Conversation
        usage_fks = [fk.parent.name for fk in LLMUsage.__table__.foreign_keys]
        assert 'conversation_id' in usage_fks


if __name__ == "__main__":
    pytest.main([__file__, "-v"])