"""
Environment model for isolated knowledge bases/namespaces.
"""

from uuid import uuid4

from sqlalchemy import Column, DateTime, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgresUUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class Environment(Base):
    """Environment model for isolated knowledge bases."""

    __tablename__ = "environments"

    id = Column(
        PostgresUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        index=True,
    )
    name = Column(String(255), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    system_prompt = Column(Text, nullable=True)
    settings = Column(JSONB, nullable=True, default=dict)
    created_by = Column(String(255), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )

    # Relationships
    documents = relationship(
        "Document",
        back_populates="environment",
        cascade="all, delete-orphan",
    )
    user_roles = relationship(
        "UserRole",
        back_populates="environment",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Environment(id={self.id}, name='{self.name}')>"
