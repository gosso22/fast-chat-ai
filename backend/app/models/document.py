"""
Document and chunk models for vector storage.
"""

from uuid import uuid4

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID, JSONB
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector

from app.db.base import Base


class Document(Base):
    """Document model for storing uploaded files metadata."""
    
    __tablename__ = "documents"
    
    id = Column(
        PostgresUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        index=True
    )
    user_id = Column(String(255), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    file_size = Column(Integer, nullable=False)
    content_type = Column(String(100), nullable=False)
    upload_date = Column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False
    )
    processing_status = Column(
        String(50),
        default="pending",
        nullable=False
    )
    extraction_metadata = Column(JSONB, nullable=True)
    environment_id = Column(
        PostgresUUID(as_uuid=True),
        ForeignKey("environments.id"),
        nullable=True,
        index=True,
    )
    
    # Relationships
    chunks = relationship(
        "DocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan"
    )
    environment = relationship(
        "Environment",
        back_populates="documents",
    )

    __table_args__ = (
        Index("idx_documents_environment", "environment_id"),
    )
    
    def __repr__(self) -> str:
        return f"<Document(id={self.id}, filename='{self.filename}')>"


class DocumentChunk(Base):
    """Document chunk model with vector embeddings."""
    
    __tablename__ = "document_chunks"
    
    id = Column(
        PostgresUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        index=True
    )
    document_id = Column(
        PostgresUUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    start_position = Column(Integer, nullable=False)
    end_position = Column(Integer, nullable=False)
    token_count = Column(Integer, nullable=False)
    embedding = Column(
        Vector(1536),  # OpenAI embedding dimension
        nullable=True
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False
    )
    
    # Relationship to document
    document = relationship(
        "Document",
        back_populates="chunks"
    )
    
    def __repr__(self) -> str:
        return f"<DocumentChunk(id={self.id}, document_id={self.document_id}, chunk_index={self.chunk_index})>"