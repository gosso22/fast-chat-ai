"""
User role assignment and management API endpoints.

Requirements: 9.1, 9.3, 9.5
"""

import logging
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.models.environment import Environment
from app.models.user_role import UserRole
from app.schemas.user_role import (
    UserRoleCreate,
    UserRoleDeleteResponse,
    UserRoleResponse,
    UserRoleUpdate,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/roles", tags=["roles"])


async def _get_environment_or_404(
    environment_id: UUID, db: AsyncSession
) -> Environment:
    result = await db.execute(
        select(Environment).where(Environment.id == environment_id)
    )
    env = result.scalar_one_or_none()
    if env is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Environment not found",
        )
    return env


@router.post(
    "",
    response_model=UserRoleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def assign_role(
    payload: UserRoleCreate,
    db: AsyncSession = Depends(get_db),
):
    """Assign a role to a user for a specific environment."""
    # Validate environment exists
    await _get_environment_or_404(payload.environment_id, db)

    # Check for existing role assignment
    result = await db.execute(
        select(UserRole).where(
            UserRole.user_id == payload.user_id,
            UserRole.environment_id == payload.environment_id,
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"User '{payload.user_id}' already has role "
                f"'{existing.role}' in this environment"
            ),
        )

    user_role = UserRole(
        user_id=payload.user_id,
        role=payload.role,
        environment_id=payload.environment_id,
    )
    db.add(user_role)
    await db.commit()
    await db.refresh(user_role)

    logger.info(
        "Assigned role %s to user %s in environment %s",
        user_role.role,
        user_role.user_id,
        user_role.environment_id,
    )
    return user_role


@router.get(
    "",
    response_model=List[UserRoleResponse],
)
async def list_roles(
    environment_id: UUID | None = None,
    user_id: str | None = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    """List user roles, optionally filtered by environment or user."""
    query = select(UserRole)

    if environment_id is not None:
        query = query.where(UserRole.environment_id == environment_id)
    if user_id is not None:
        query = query.where(UserRole.user_id == user_id)

    query = (
        query.order_by(UserRole.created_at.desc()).offset(skip).limit(limit)
    )

    result = await db.execute(query)
    return result.scalars().all()


@router.get(
    "/{role_id}",
    response_model=UserRoleResponse,
)
async def get_role(
    role_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a single user role by ID."""
    result = await db.execute(
        select(UserRole).where(UserRole.id == role_id)
    )
    role = result.scalar_one_or_none()
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found",
        )
    return role


@router.put(
    "/{role_id}",
    response_model=UserRoleResponse,
)
async def update_role(
    role_id: UUID,
    payload: UserRoleUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a user's role (e.g. promote chat_user to admin)."""
    result = await db.execute(
        select(UserRole).where(UserRole.id == role_id)
    )
    role = result.scalar_one_or_none()
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found",
        )

    role.role = payload.role
    await db.commit()
    await db.refresh(role)

    logger.info(
        "Updated role %s for user %s to %s",
        role.id,
        role.user_id,
        role.role,
    )
    return role


@router.delete(
    "/{role_id}",
    response_model=UserRoleDeleteResponse,
)
async def delete_role(
    role_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Remove a user's role assignment."""
    result = await db.execute(
        select(UserRole).where(UserRole.id == role_id)
    )
    role = result.scalar_one_or_none()
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found",
        )

    await db.delete(role)
    await db.commit()

    logger.info(
        "Deleted role %s for user %s in environment %s",
        role_id,
        role.user_id,
        role.environment_id,
    )
    return UserRoleDeleteResponse(
        message="Role deleted successfully",
        deleted_role_id=role_id,
    )
