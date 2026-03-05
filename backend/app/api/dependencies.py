"""
FastAPI dependencies for authentication and role-based access control.

User identity comes via the X-User-ID header. Role checking looks up
the user's role from the database.

Requirements: 9.1, 9.3, 9.5
"""

import logging
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.base import get_db
from app.models.environment import Environment
from app.models.user_role import RoleType, UserRole

logger = logging.getLogger(__name__)


async def get_user_id(
    x_user_id: str = Header(..., description="User identifier"),
) -> str:
    """Extract user ID from the X-User-ID request header."""
    if not x_user_id.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-User-ID header is required",
        )
    return x_user_id.strip()


async def require_global_admin(
    user_id: str = Depends(get_user_id),
) -> str:
    """Require the caller to be a global admin.

    Global admins are defined in the ADMIN_USER_IDS config setting.
    Raises 403 if the user is not a global admin.
    """
    if user_id not in settings.ADMIN_USER_IDS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Global admin access required",
        )
    return user_id


async def get_user_role(
    environment_id: UUID,
    user_id: str = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
) -> UserRole:
    """Look up the user's role for a given environment.

    Returns the UserRole record or raises 403 if no role is assigned.
    """
    result = await db.execute(
        select(UserRole).where(
            UserRole.user_id == user_id,
            UserRole.environment_id == environment_id,
        )
    )
    role = result.scalar_one_or_none()
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No access to this environment",
        )
    return role


async def require_admin(
    environment_id: UUID,
    user_id: str = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
) -> UserRole:
    """Require the caller to have admin role for the environment.

    Raises 403 if the user is not an admin.
    """
    result = await db.execute(
        select(UserRole).where(
            UserRole.user_id == user_id,
            UserRole.environment_id == environment_id,
            UserRole.role == RoleType.ADMIN.value,
        )
    )
    role = result.scalar_one_or_none()
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required for this environment",
        )
    return role


async def require_environment_access(
    environment_id: UUID,
    user_id: str = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
) -> UserRole:
    """Require the caller to have any role (admin or chat_user) for the environment.

    Used to gate chat endpoints so users can only access their assigned
    environments (Req 9.5).
    """
    result = await db.execute(
        select(UserRole).where(
            UserRole.user_id == user_id,
            UserRole.environment_id == environment_id,
        )
    )
    role = result.scalar_one_or_none()
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No access to this environment",
        )
    return role


async def validate_environment_exists(
    environment_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Environment:
    """Validate that an environment exists, raising 404 otherwise."""
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
