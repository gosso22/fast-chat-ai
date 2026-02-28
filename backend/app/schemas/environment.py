"""
Environment schemas for API requests and responses.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EnvironmentCreate(BaseModel):
    """Request schema for creating an environment."""

    name: str = Field(
        ..., min_length=1, max_length=255, description="Environment name"
    )
    description: Optional[str] = Field(
        None, description="Environment description"
    )


class EnvironmentUpdate(BaseModel):
    """Request schema for updating an environment."""

    name: Optional[str] = Field(
        None, min_length=1, max_length=255, description="Environment name"
    )
    description: Optional[str] = Field(
        None, description="Environment description"
    )


class EnvironmentResponse(BaseModel):
    """Response schema for an environment."""

    id: UUID
    name: str
    description: Optional[str] = None
    created_by: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EnvironmentDeleteResponse(BaseModel):
    """Response schema for environment deletion."""

    message: str
    deleted_environment_id: UUID
    deleted_documents_count: int
