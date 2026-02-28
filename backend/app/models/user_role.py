"""
User role model for role-based access control.
"""

from enum import Enum
from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class RoleType(str, Enum):
    """Enum for user role types."""
    ADMIN = "admin"
    CHAT_USER = "chat_user"


class UserRole(Base):
    """User role model mapping users to environments with specific roles."""

    __tablename__ = "user_roles"

    id = Column(
        PostgresUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        index=True,
    )
    user_id = Column(String(255), nullable=False, index=True)
    role = Column(String(50), nullable=False)
    environment_id = Column(
        PostgresUUID(as_uuid=True),
        ForeignKey("environments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )

    # Relationships
    environment = relationship(
        "Environment",
        back_populates="user_roles",
    )

    __table_args__ = (
        UniqueConstraint("user_id", "environment_id", name="uq_user_environment"),
    )

    def __repr__(self) -> str:
        return f"<UserRole(id={self.id}, user_id='{self.user_id}', role='{self.role}')>"
