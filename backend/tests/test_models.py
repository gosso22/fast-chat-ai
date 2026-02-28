"""
Tests for database models.
"""

import pytest
from uuid import uuid4
from datetime import datetime
from decimal import Decimal

from app.models.document import Document, DocumentChunk
from app.models.conversation import Conversation, ChatMessage, LLMUsage, MessageRole


class TestDocumentModels:
    """Test document and chunk models."""
    
    def test_document_creation(self):
        """Test document model creation."""
        document = Document(
            user_id="test_user",
            filename="test.pdf",
            file_size=1024,
            content_type="application/pdf",
            processing_status="pending"
        )
        
        assert document.user_id == "test_user"
        assert document.filename == "test.pdf"
        assert document.file_size == 1024
        assert document.content_type == "application/pdf"
        assert document.processing_status == "pending"
    
    def test_document_chunk_creation(self):
        """Test document chunk model creation."""
        document_id = uuid4()
        chunk = DocumentChunk(
            document_id=document_id,
            chunk_index=0,
            content="This is a test chunk",
            start_position=0,
            end_position=20,
            token_count=5,
            embedding=[0.1, 0.2, 0.3] * 512  # Mock embedding vector
        )
        
        assert chunk.document_id == document_id
        assert chunk.chunk_index == 0
        assert chunk.content == "This is a test chunk"
        assert chunk.start_position == 0
        assert chunk.end_position == 20
        assert chunk.token_count == 5
        assert len(chunk.embedding) == 1536


class TestConversationModels:
    """Test conversation and message models."""
    
    def test_conversation_creation(self):
        """Test conversation model creation."""
        conversation = Conversation(
            user_id="test_user",
            title="Test Conversation"
        )
        
        assert conversation.user_id == "test_user"
        assert conversation.title == "Test Conversation"
    
    def test_chat_message_creation(self):
        """Test chat message model creation."""
        conversation_id = uuid4()
        message = ChatMessage(
            conversation_id=conversation_id,
            role=MessageRole.USER,
            content="Hello, how are you?",
            token_count=5
        )
        
        assert message.conversation_id == conversation_id
        assert message.role == MessageRole.USER
        assert message.content == "Hello, how are you?"
        assert message.token_count == 5
    
    def test_llm_usage_creation(self):
        """Test LLM usage model creation."""
        conversation_id = uuid4()
        usage = LLMUsage(
            conversation_id=conversation_id,
            provider="openai",
            model="gpt-3.5-turbo",
            input_tokens=100,
            output_tokens=50,
            cost=Decimal("0.001500")
        )
        
        assert usage.conversation_id == conversation_id
        assert usage.provider == "openai"
        assert usage.model == "gpt-3.5-turbo"
        assert usage.input_tokens == 100
        assert usage.output_tokens == 50
        assert usage.cost == Decimal("0.001500")
    
    def test_message_role_enum(self):
        """Test message role enum values."""
        assert MessageRole.USER == "user"
        assert MessageRole.ASSISTANT == "assistant"