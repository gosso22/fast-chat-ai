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

from app.db.base import get_db
from app.models.document import Document
from app.models.environment import Environment
from app.schemas.environment import (
    EnvironmentCreate,
    EnvironmentDeleteResponse,
    EnvironmentResponse,
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
    user_id: str = Header(
        default="default_admin", alias="X-User-ID"
    ),
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
