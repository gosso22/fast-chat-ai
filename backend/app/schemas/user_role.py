"""
User role schemas for API requests and responses.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class UserRoleCreate(BaseModel):
    """Request schema for assigning a role to a user."""

    user_id: str = Field(
        ..., min_length=1, max_length=255, description="User identifier"
    )
    role: str = Field(
        ..., pattern="^(admin|chat_user)$", description="Role type"
    )
    environment_id: UUID = Field(
        ..., description="Environment to assign the role in"
    )


class UserRoleUpdate(BaseModel):
    """Request schema for updating a user role."""

    role: str = Field(
        ..., pattern="^(admin|chat_user)$", description="New role type"
    )


class UserRoleResponse(BaseModel):
    """Response schema for a user role."""

    id: UUID
    user_id: str
    role: str
    environment_id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserRoleDeleteResponse(BaseModel):
    """Response schema for role deletion."""

    message: str
    deleted_role_id: UUID
