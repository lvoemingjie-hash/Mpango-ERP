"""
CRUD operations for Role model.
Operates on tenant schema.
"""
from typing import List, Optional
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.user import Role


async def get_all_roles(db: AsyncSession) -> List[Role]:
    """
    Get all roles.
    
    Args:
        db: Database session (tenant schema)
        
    Returns:
        List of all roles
    """
    result = await db.execute(
        select(Role)
        .where(Role.is_deleted == False)
        .order_by(Role.name)
    )
    return list(result.scalars().all())


async def get_role_by_id(
    db: AsyncSession,
    role_id: str
) -> Optional[Role]:
    """
    Get role by ID.
    
    Args:
        db: Database session (tenant schema)
        role_id: Role UUID as string
        
    Returns:
        Role if found, None otherwise
    """
    try:
        role_uuid = UUID(role_id)
    except ValueError:
        return None
    
    result = await db.execute(
        select(Role)
        .where(Role.id == role_uuid)
        .where(Role.is_deleted == False)
    )
    return result.scalar_one_or_none()


async def get_role_by_name(
    db: AsyncSession,
    name: str
) -> Optional[Role]:
    """
    Get role by name.
    
    Args:
        db: Database session (tenant schema)
        name: Role name
        
    Returns:
        Role if found, None otherwise
    """
    result = await db.execute(
        select(Role)
        .where(Role.name == name)
        .where(Role.is_deleted == False)
    )
    return result.scalar_one_or_none()
