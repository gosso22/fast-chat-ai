"""
Environment schemas for API requests and responses.
"""

from datetime import datetime
from typing import Dict, List, Optional, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EnvironmentSettings(BaseModel):
    """Per-environment configuration settings."""

    similarity_threshold: Optional[float] = Field(
        None, ge=0.0, le=1.0,
        description="Default similarity threshold for RAG searches",
    )
    max_context_chunks: Optional[int] = Field(
        None, ge=1, le=20,
        description="Maximum context chunks to retrieve per query",
    )
    temperature: Optional[float] = Field(
        None, ge=0.0, le=2.0,
        description="Default LLM temperature",
    )
    max_tokens: Optional[int] = Field(
        None, ge=1,
        description="Default max tokens for LLM responses",
    )
    allowed_providers: Optional[List[str]] = Field(
        None,
        description="Allowed LLM provider names (e.g. ['openai', 'anthropic'])",
    )
    token_budget: Optional[int] = Field(
        None, ge=0,
        description="Monthly token budget limit",
    )


class EnvironmentCreate(BaseModel):
    """Request schema for creating an environment."""

    name: str = Field(
        ..., min_length=1, max_length=255, description="Environment name"
    )
    description: Optional[str] = Field(
        None, description="Environment description"
    )
    system_prompt: Optional[str] = Field(
        None, description="Custom system prompt for this environment's chatbot"
    )
    settings: Optional[EnvironmentSettings] = Field(
        None, description="Per-environment configuration settings"
    )


class EnvironmentUpdate(BaseModel):
    """Request schema for updating an environment."""

    name: Optional[str] = Field(
        None, min_length=1, max_length=255, description="Environment name"
    )
    description: Optional[str] = Field(
        None, description="Environment description"
    )
    system_prompt: Optional[str] = Field(
        None, description="Custom system prompt for this environment's chatbot"
    )
    settings: Optional[EnvironmentSettings] = Field(
        None, description="Per-environment configuration settings"
    )


class EnvironmentResponse(BaseModel):
    """Response schema for an environment."""

    id: UUID
    name: str
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None
    created_by: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EnvironmentStatsResponse(BaseModel):
    """Response schema for environment statistics."""

    environment_id: UUID
    name: str
    document_count: int = 0
    chunk_count: int = 0
    total_tokens: int = 0
    total_storage_bytes: int = 0
    conversation_count: int = 0
    message_count: int = 0
    created_at: datetime
    updated_at: datetime


class EnvironmentDeleteResponse(BaseModel):
    """Response schema for environment deletion."""

    message: str
    deleted_environment_id: UUID
    deleted_documents_count: int
