"""
Conversation and message models for chat functionality.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import uuid4

from sqlalchemy import (
    DECIMAL,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class MessageRole(str, Enum):
    """Enum for message roles."""
    USER = "user"
    ASSISTANT = "assistant"


class Conversation(Base):
    """Conversation model for chat sessions."""
    
    __tablename__ = "conversations"
    
    id = Column(
        PostgresUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        index=True
    )
    user_id = Column(String(255), nullable=False, index=True)
    title = Column(String(255), nullable=True)
    environment_id = Column(
        PostgresUUID(as_uuid=True),
        ForeignKey("environments.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
    
    # Relationships
    environment = relationship("Environment")
    messages = relationship(
        "ChatMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at"
    )
    llm_usage = relationship(
        "LLMUsage",
        back_populates="conversation",
        cascade="all, delete-orphan"
    )
    
    def __repr__(self) -> str:
        return f"<Conversation(id={self.id}, user_id='{self.user_id}', title='{self.title}')>"


class ChatMessage(Base):
    """Chat message model."""
    
    __tablename__ = "chat_messages"
    
    id = Column(
        PostgresUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        index=True
    )
    conversation_id = Column(
        PostgresUUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    role = Column(
        String(20),
        nullable=False
    )
    content = Column(Text, nullable=False)
    token_count = Column(Integer, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    
    # Relationship to conversation
    conversation = relationship(
        "Conversation",
        back_populates="messages"
    )
    
    # Add constraint for role values
    __table_args__ = (
        CheckConstraint(
            "role IN ('user', 'assistant')",
            name="check_message_role"
        ),
    )
    
    def __repr__(self) -> str:
        return f"<ChatMessage(id={self.id}, conversation_id={self.conversation_id}, role='{self.role}')>"


class LLMUsage(Base):
    """LLM usage tracking model for cost monitoring."""
    
    __tablename__ = "llm_usage"
    
    id = Column(
        PostgresUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        index=True
    )
    conversation_id = Column(
        PostgresUUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    provider = Column(String(50), nullable=False)
    model = Column(String(100), nullable=False)
    input_tokens = Column(Integer, nullable=False)
    output_tokens = Column(Integer, nullable=False)
    cost = Column(DECIMAL(10, 6), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    
    # Relationship to conversation
    conversation = relationship(
        "Conversation",
        back_populates="llm_usage"
    )
    
    def __repr__(self) -> str:
        return f"<LLMUsage(id={self.id}, provider='{self.provider}', model='{self.model}', cost={self.cost})>"