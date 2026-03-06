"""
User info API endpoints.

Provides current user identity and their accessible environments.
"""

import logging
from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_user_id
from app.core.config import settings
from app.db.base import get_db
from app.models.environment import Environment
from app.models.user_role import UserRole
from app.schemas.environment import EnvironmentResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/users", tags=["users"])


class UserMeResponse(BaseModel):
    user_id: str
    is_global_admin: bool


class UserEnvironmentResponse(BaseModel):
    environment: EnvironmentResponse
    role: str

    model_config = ConfigDict(from_attributes=True)


@router.get("/me", response_model=UserMeResponse)
async def get_current_user(
    user_id: str = Depends(get_user_id),
):
    """Return current user identity and admin status."""
    return UserMeResponse(
        user_id=user_id,
        is_global_admin=user_id in settings.ADMIN_USER_IDS,
    )


@router.get("/me/environments", response_model=List[UserEnvironmentResponse])
async def get_user_environments(
    user_id: str = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Return environments accessible to the current user.

    Global admins get all environments (with role='admin').
    Regular users get only environments where they have an assigned role.
    """
    if user_id in settings.ADMIN_USER_IDS:
        # Global admin sees all environments
        result = await db.execute(
            select(Environment).order_by(Environment.created_at.desc())
        )
        envs = result.scalars().all()

        # Look up any explicit roles the admin has
        roles_result = await db.execute(
            select(UserRole).where(UserRole.user_id == user_id)
        )
        role_map = {r.environment_id: r.role for r in roles_result.scalars().all()}

        return [
            UserEnvironmentResponse(
                environment=EnvironmentResponse.model_validate(env),
                role=role_map.get(env.id, "admin"),
            )
            for env in envs
        ]

    # Regular user: only environments with explicit role assignment
    result = await db.execute(
        select(UserRole, Environment)
        .join(Environment, UserRole.environment_id == Environment.id)
        .where(UserRole.user_id == user_id)
        .order_by(Environment.created_at.desc())
    )
    rows = result.all()

    return [
        UserEnvironmentResponse(
            environment=EnvironmentResponse.model_validate(env),
            role=role.role,
        )
        for role, env in rows
    ]
