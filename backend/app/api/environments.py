"""
Environment management API endpoints (Admin role).
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_global_admin
from app.db.base import get_db
from app.models.conversation import ChatMessage, Conversation
from app.models.document import Document, DocumentChunk
from app.models.environment import Environment
from app.schemas.environment import (
    EnvironmentCreate,
    EnvironmentDeleteResponse,
    EnvironmentResponse,
    EnvironmentStatsResponse,
    EnvironmentUpdate,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/environments", tags=["environments"])


@router.post(
    "",
    response_model=EnvironmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_environment(
    payload: EnvironmentCreate,
    user_id: str = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create a new environment / isolated knowledge base."""
    # Check for duplicate name
    existing = await db.execute(
        select(Environment).where(Environment.name == payload.name)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Environment with name '{payload.name}' already exists",
        )

    environment = Environment(
        name=payload.name,
        description=payload.description,
        system_prompt=payload.system_prompt,
        settings=payload.settings.model_dump(exclude_none=True) if payload.settings else None,
        created_by=user_id,
    )
    db.add(environment)
    await db.commit()
    await db.refresh(environment)

    logger.info("Created environment %s (id=%s)", environment.name, environment.id)
    return environment


@router.get(
    "",
    response_model=List[EnvironmentResponse],
)
async def list_environments(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    """List all environments."""
    result = await db.execute(
        select(Environment)
        .order_by(Environment.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()


@router.get(
    "/{environment_id}",
    response_model=EnvironmentResponse,
)
async def get_environment(
    environment_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a single environment by ID."""
    result = await db.execute(
        select(Environment).where(Environment.id == environment_id)
    )
    environment = result.scalar_one_or_none()
    if environment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Environment not found",
        )
    return environment


@router.put(
    "/{environment_id}",
    response_model=EnvironmentResponse,
)
async def update_environment(
    environment_id: UUID,
    payload: EnvironmentUpdate,
    _admin: str = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing environment."""
    result = await db.execute(
        select(Environment).where(Environment.id == environment_id)
    )
    environment = result.scalar_one_or_none()
    if environment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Environment not found",
        )

    # Check name uniqueness if name is being changed
    if payload.name is not None and payload.name != environment.name:
        dup = await db.execute(
            select(Environment).where(Environment.name == payload.name)
        )
        if dup.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Environment with name '{payload.name}' already exists",
            )
        environment.name = payload.name

    if payload.description is not None:
        environment.description = payload.description

    if payload.system_prompt is not None:
        environment.system_prompt = payload.system_prompt

    if payload.settings is not None:
        existing = environment.settings or {}
        existing.update(payload.settings.model_dump(exclude_none=True))
        environment.settings = existing

    environment.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(environment)

    logger.info("Updated environment %s (id=%s)", environment.name, environment.id)
    return environment


@router.delete(
    "/{environment_id}",
    response_model=EnvironmentDeleteResponse,
)
async def delete_environment(
    environment_id: UUID,
    _admin: str = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete an environment and cascade-delete its documents."""
    result = await db.execute(
        select(Environment).where(Environment.id == environment_id)
    )
    environment = result.scalar_one_or_none()
    if environment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Environment not found",
        )

    # Count associated documents before deletion
    doc_count_result = await db.execute(
        select(func.count(Document.id)).where(
            Document.environment_id == environment_id
        )
    )
    doc_count = doc_count_result.scalar() or 0

    await db.delete(environment)
    await db.commit()

    logger.info(
        "Deleted environment %s (id=%s) with %d documents",
        environment.name,
        environment.id,
        doc_count,
    )
    return EnvironmentDeleteResponse(
        message="Environment deleted successfully",
        deleted_environment_id=environment_id,
        deleted_documents_count=doc_count,
    )


@router.get(
    "/{environment_id}/stats",
    response_model=EnvironmentStatsResponse,
)
async def get_environment_stats(
    environment_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get statistics for an environment."""
    result = await db.execute(
        select(Environment).where(Environment.id == environment_id)
    )
    environment = result.scalar_one_or_none()
    if environment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Environment not found",
        )

    # Document count and total storage
    doc_stats = await db.execute(
        select(
            func.count(Document.id),
            func.coalesce(func.sum(Document.file_size), 0),
        ).where(Document.environment_id == environment_id)
    )
    doc_count, total_storage = doc_stats.one()

    # Chunk count and total tokens
    chunk_stats = await db.execute(
        select(
            func.count(DocumentChunk.id),
            func.coalesce(func.sum(DocumentChunk.token_count), 0),
        )
        .join(Document, DocumentChunk.document_id == Document.id)
        .where(Document.environment_id == environment_id)
    )
    chunk_count, total_tokens = chunk_stats.one()

    # Conversation count
    conv_count_result = await db.execute(
        select(func.count(Conversation.id)).where(
            Conversation.environment_id == environment_id
        )
    )
    conv_count = conv_count_result.scalar() or 0

    # Message count
    msg_count_result = await db.execute(
        select(func.count(ChatMessage.id))
        .join(Conversation, ChatMessage.conversation_id == Conversation.id)
        .where(Conversation.environment_id == environment_id)
    )
    msg_count = msg_count_result.scalar() or 0

    return EnvironmentStatsResponse(
        environment_id=environment_id,
        name=environment.name,
        document_count=doc_count or 0,
        chunk_count=chunk_count or 0,
        total_tokens=total_tokens or 0,
        total_storage_bytes=total_storage or 0,
        conversation_count=conv_count,
        message_count=msg_count,
        created_at=environment.created_at,
        updated_at=environment.updated_at,
    )
