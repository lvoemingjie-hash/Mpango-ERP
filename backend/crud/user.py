"""
CRUD operations for User model.
Operates on tenant schema.
"""
from typing import Optional
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.user import User


async def get_user_by_email(
    db: AsyncSession,
    email: str
) -> Optional[User]:
    """
    Get user by email.
    
    Queries tenant schema (search_path must be set).
    Used during login to find user by email.
    
    Args:
        db: Database session (tenant schema)
        email: User email
        
    Returns:
        User if found, None otherwise
    """
    result = await db.execute(
        select(User).where(User.email == email)
    )
    return result.scalar_one_or_none()


async def get_user_with_permissions(
    db: AsyncSession,
    user_id: str
) -> Optional[User]:
    """
    Get user with roles and permissions loaded.
    
    Eagerly loads:
    - user.roles (list of Role)
    - role.permissions (list of Permission for each role)
    
    Used by RBAC middleware to check permissions.
    
    Args:
        db: Database session (tenant schema)
        user_id: User UUID as string
        
    Returns:
        User with roles and permissions loaded, None if not found
    """
    try:
        user_uuid = UUID(user_id)
    except ValueError:
        return None
    
    from models.user import Role
    
    result = await db.execute(
        select(User)
        .where(User.id == user_uuid)
        .options(
            selectinload(User.roles).selectinload(Role.permissions)
        )
    )
    return result.scalar_one_or_none()
