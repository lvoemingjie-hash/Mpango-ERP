"""
CRUD operations for User model.
Operates on tenant schema.
"""
from typing import Optional, List, Tuple
from uuid import UUID
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.user import User, Role
from core.security import hash_password


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
    
    result = await db.execute(
        select(User)
        .where(User.id == user_uuid)
        .options(
            selectinload(User.roles).selectinload(Role.permissions)
        )
    )
    return result.scalar_one_or_none()


async def get_user_by_id(
    db: AsyncSession,
    user_id: str
) -> Optional[User]:
    """
    Get user by ID with roles loaded.
    
    Args:
        db: Database session (tenant schema)
        user_id: User UUID as string
        
    Returns:
        User with roles loaded, None if not found
    """
    try:
        user_uuid = UUID(user_id)
    except ValueError:
        return None
    
    result = await db.execute(
        select(User)
        .where(User.id == user_uuid)
        .where(User.is_deleted == False)
        .options(selectinload(User.roles))
    )
    return result.scalar_one_or_none()


async def get_users_paginated(
    db: AsyncSession,
    page: int = 1,
    size: int = 10
) -> Tuple[List[User], int]:
    """
    Get paginated list of users.
    
    Args:
        db: Database session (tenant schema)
        page: Page number (1-based)
        size: Items per page
        
    Returns:
        Tuple of (users list, total count)
    """
    # Get total count
    count_result = await db.execute(
        select(func.count(User.id)).where(User.is_deleted == False)
    )
    total = count_result.scalar_one()
    
    # Get paginated users
    offset = (page - 1) * size
    result = await db.execute(
        select(User)
        .where(User.is_deleted == False)
        .options(selectinload(User.roles))
        .order_by(User.created_at.desc())
        .offset(offset)
        .limit(size)
    )
    users = list(result.scalars().all())
    
    return users, total


async def create_user(
    db: AsyncSession,
    email: str,
    password: str,
    full_name: Optional[str] = None,
    created_by: Optional[str] = None
) -> User:
    """
    Create a new user.
    
    Args:
        db: Database session (tenant schema)
        email: User email
        password: Plain text password (will be hashed)
        full_name: Optional full name
        created_by: UUID of user creating this user
        
    Returns:
        Created User object
    """
    user = User(
        email=email,
        password_hash=hash_password(password),
        full_name=full_name,
        is_active=True
    )
    
    if created_by:
        try:
            user.created_by = UUID(created_by)
        except ValueError:
            pass
    
    db.add(user)
    await db.flush()
    await db.refresh(user, ["roles"])
    
    return user


async def update_user(
    db: AsyncSession,
    user: User,
    email: Optional[str] = None,
    full_name: Optional[str] = None,
    is_active: Optional[bool] = None,
    updated_by: Optional[str] = None
) -> User:
    """
    Update user fields.
    
    Args:
        db: Database session (tenant schema)
        user: User object to update
        email: New email (optional)
        full_name: New full name (optional)
        is_active: New active status (optional)
        updated_by: UUID of user making the update
        
    Returns:
        Updated User object
    """
    if email is not None:
        user.email = email
    if full_name is not None:
        user.full_name = full_name
    if is_active is not None:
        user.is_active = is_active
    
    if updated_by:
        try:
            user.updated_by = UUID(updated_by)
        except ValueError:
            pass
    
    await db.flush()
    await db.refresh(user, ["roles"])
    
    return user


async def soft_delete_user(
    db: AsyncSession,
    user: User,
    deleted_by: Optional[str] = None
) -> User:
    """
    Soft delete a user (set is_deleted=True).
    
    Args:
        db: Database session (tenant schema)
        user: User object to delete
        deleted_by: UUID of user performing deletion
        
    Returns:
        Deleted User object
    """
    user.soft_delete()
    
    if deleted_by:
        try:
            user.updated_by = UUID(deleted_by)
        except ValueError:
            pass
    
    await db.flush()
    
    return user


async def assign_roles_to_user(
    db: AsyncSession,
    user: User,
    role_ids: List[str],
    updated_by: Optional[str] = None
) -> User:
    """
    Assign roles to a user (replaces existing roles).
    
    Args:
        db: Database session (tenant schema)
        user: User object
        role_ids: List of role UUIDs to assign
        updated_by: UUID of user making the change
        
    Returns:
        Updated User object with new roles
        
    Raises:
        ValueError: If any role_id is invalid
    """
    # Convert and validate role IDs
    role_uuids = []
    for rid in role_ids:
        try:
            role_uuids.append(UUID(rid))
        except ValueError:
            raise ValueError(f"Invalid role ID: {rid}")
    
    # Fetch roles
    result = await db.execute(
        select(Role).where(Role.id.in_(role_uuids))
    )
    roles = list(result.scalars().all())
    
    # Check all roles were found
    found_ids = {role.id for role in roles}
    missing = [str(rid) for rid in role_uuids if rid not in found_ids]
    if missing:
        raise ValueError(f"Roles not found: {', '.join(missing)}")
    
    # Assign roles
    user.roles = roles
    
    if updated_by:
        try:
            user.updated_by = UUID(updated_by)
        except ValueError:
            pass
    
    await db.flush()
    await db.refresh(user, ["roles"])
    
    return user


async def email_exists(
    db: AsyncSession,
    email: str,
    exclude_user_id: Optional[str] = None
) -> bool:
    """
    Check if email already exists.
    
    Args:
        db: Database session (tenant schema)
        email: Email to check
        exclude_user_id: User ID to exclude from check (for updates)
        
    Returns:
        True if email exists, False otherwise
    """
    query = select(User.id).where(User.email == email)
    
    if exclude_user_id:
        try:
            user_uuid = UUID(exclude_user_id)
            query = query.where(User.id != user_uuid)
        except ValueError:
            pass
    
    result = await db.execute(query)
    return result.scalar_one_or_none() is not None
