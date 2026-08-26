"""
CRUD operations for User model.
Operates on tenant schema.

H-Fix-01: Added find_user_across_tenants for tenant-agnostic login.
"""
from dataclasses import dataclass
from typing import Optional, List, Tuple
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.user import User, Role
from models.wholesaler import Wholesaler
from core.security import hash_password, verify_password
from db.tenant_filter import run_as_system, mark_session_as_system


@dataclass
class TenantUserMatch:
    """Result of cross-tenant user lookup."""
    wholesaler: Wholesaler
    user: User
    roles: List[str]


async def find_user_across_tenants(
    db_public: AsyncSession,
    email: str,
    password: str,
) -> Tuple[Optional[str], List[TenantUserMatch]]:
    """
    Scan all active tenant schemas to find a user by email and verify password.

    H-Fix-01: Decouples identity verification from tenant selection.

    Returns:
        Tuple of (verified_user_id, list_of_TenantUserMatch).
        verified_user_id is set once password matches in *any* tenant.
        The list contains every tenant where this email exists.
        If the password is wrong in all tenants, returns (None, []).
    """
    from database.session import get_tenant_db

    # Mark session as system scope to bypass tenant filter for cross-tenant scan
    mark_session_as_system(db_public, reason="cross_tenant_login_scan")

    with run_as_system(reason="cross_tenant_login_scan"):
        # Set execution options on session to bypass tenant filter
        result = await db_public.execute(
            select(Wholesaler)
            .where(Wholesaler.is_deleted == False)
            .order_by(Wholesaler.created_at),
            execution_options={"ignore_tenant": True}
        )
        wholesalers = list(result.scalars().all())

    matches: List[TenantUserMatch] = []
    verified_user_id: Optional[str] = None

    # First pass: collect every active copy of this email across tenant schemas.
    candidate_matches: List[TenantUserMatch] = []
    for ws in wholesalers:
        tenant_schema = ws.get_tenant_schema()
        try:
            async for tenant_db in get_tenant_db(tenant_schema):
                user = await get_user_by_email(tenant_db, email)
                if user is None:
                    continue
                if not user.is_active:
                    continue
                role_names = [r.name for r in user.roles] if user.roles else []
                candidate_matches.append(TenantUserMatch(
                    wholesaler=ws,
                    user=user,
                    roles=role_names,
                ))
        except Exception:
            continue

    if not candidate_matches:
        return (None, [])

    # Second pass: include ONLY copies whose own password_hash verifies.
    # DC-3B-R1 fix: an unverified copy (e.g. same email but a different password
    # in another tenant) must NOT be granted or listed in available_tenants. The
    # verified_user_id is the user_id of the first verified copy; the returned
    # match list contains only verified copies.
    for match in candidate_matches:
        if verify_password(password, match.user.password_hash):
            if verified_user_id is None:
                verified_user_id = str(match.user.id)
            matches.append(match)

    if verified_user_id is None or not matches:
        return (None, [])

    return (verified_user_id, matches)


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

    # H2-B-R3-R1: the flushed UPDATE carries the SQL-expression onupdate
    # (updated_at = now()), which leaves scalar state expired for
    # post-fetch, and the previous partial refresh(user, ["roles"]) never
    # reloaded it — user_to_read then read user.updated_at in synchronous
    # context and hit async implicit lazy-load (MissingGreenlet -> 500).
    # Reload the row explicitly inside this await boundary: populate_existing
    # re-reads ALL scalar state from the flushed UPDATE and selectinload
    # re-binds roles, so the returned User is fully loaded and serialization
    # can never trigger implicit SQL. (identity map: same instance returned)
    refreshed = await db.execute(
        select(User)
        .where(User.id == user.id)
        .options(selectinload(User.roles))
        .execution_options(populate_existing=True)
    )
    return refreshed.scalar_one()


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
