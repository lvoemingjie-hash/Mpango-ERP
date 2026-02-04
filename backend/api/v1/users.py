"""
User management API endpoints.
Implements openapi.yaml /users/* endpoints.

RBAC permissions enforced per rbac_matrix.md.
Tenant isolation enforced via JWT-derived search_path.
"""
from datetime import datetime
from math import ceil
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_tenant_db_session
from api.middleware.rbac import RequirePermission
from core.security import TokenPayload
from crud.user import (
    get_user_by_id,
    get_users_paginated,
    create_user,
    update_user,
    soft_delete_user,
    assign_roles_to_user,
    email_exists
)
from schemas.user import (
    UserCreateRequest,
    UserUpdateRequest,
    UserResponse,
    UserListResponse,
    UserRead,
    RoleRead,
    AssignRolesRequest
)
from schemas.common import Pagination

router = APIRouter()


def user_to_read(user) -> UserRead:
    """Convert User model to UserRead schema."""
    return UserRead(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        roles=[
            RoleRead(
                id=str(role.id),
                name=role.name,
                description=role.description
            )
            for role in user.roles
        ],
        created_at=user.created_at,
        updated_at=user.updated_at
    )


@router.get("", response_model=UserListResponse, status_code=status.HTTP_200_OK)
async def list_users(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(10, ge=1, le=100, description="Items per page"),
    token: TokenPayload = Depends(RequirePermission("users:read")),
    db: AsyncSession = Depends(get_tenant_db_session)
):
    """
    List users with pagination.

    Implements openapi.yaml GET /users

    Requires: users:read permission

    Returns:
        UserListResponse with paginated users
    """
    users, total = await get_users_paginated(db, page=page, size=size)

    pages = ceil(total / size) if total > 0 else 0

    return UserListResponse(
        success=True,
        data={
            "items": [user_to_read(u) for u in users],
            "pagination": Pagination(
                page=page,
                size=size,
                total=total,
                pages=pages
            ).model_dump()
        },
        timestamp=datetime.utcnow()
    )


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user_endpoint(
    request: UserCreateRequest,
    token: TokenPayload = Depends(RequirePermission("users:create")),
    db: AsyncSession = Depends(get_tenant_db_session)
):
    """
    Create a new user.

    Implements openapi.yaml POST /users

    Requires: users:create permission

    Returns:
        UserResponse with created user
    """
    # Check if email already exists
    if await email_exists(db, request.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "EMAIL_EXISTS",
                "message": f"Email '{request.email}' is already registered"
            }
        )

    user = await create_user(
        db=db,
        email=request.email,
        password=request.password,
        full_name=request.full_name,
        created_by=token.user_id
    )

    return UserResponse(
        success=True,
        data=user_to_read(user),
        message="User created successfully",
        timestamp=datetime.utcnow()
    )


@router.get("/{user_id}", response_model=UserResponse, status_code=status.HTTP_200_OK)
async def get_user_endpoint(
    user_id: str,
    token: TokenPayload = Depends(RequirePermission("users:read")),
    db: AsyncSession = Depends(get_tenant_db_session)
):
    """
    Get user by ID.

    Implements openapi.yaml GET /users/{user_id}

    Requires: users:read permission

    Returns:
        UserResponse with user data
    """
    user = await get_user_by_id(db, user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "USER_NOT_FOUND",
                "message": f"User with ID '{user_id}' not found"
            }
        )

    return UserResponse(
        success=True,
        data=user_to_read(user),
        timestamp=datetime.utcnow()
    )


@router.put("/{user_id}", response_model=UserResponse, status_code=status.HTTP_200_OK)
async def update_user_endpoint(
    user_id: str,
    request: UserUpdateRequest,
    token: TokenPayload = Depends(RequirePermission("users:update")),
    db: AsyncSession = Depends(get_tenant_db_session)
):
    """
    Update user.

    Implements openapi.yaml PUT /users/{user_id}

    Requires: users:update permission

    Returns:
        UserResponse with updated user
    """
    user = await get_user_by_id(db, user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "USER_NOT_FOUND",
                "message": f"User with ID '{user_id}' not found"
            }
        )

    # Check email uniqueness if changing email
    if request.email and request.email != user.email:
        if await email_exists(db, request.email, exclude_user_id=user_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "EMAIL_EXISTS",
                    "message": f"Email '{request.email}' is already registered"
                }
            )

    user = await update_user(
        db=db,
        user=user,
        email=request.email,
        full_name=request.full_name,
        is_active=request.is_active,
        updated_by=token.user_id
    )

    return UserResponse(
        success=True,
        data=user_to_read(user),
        message="User updated successfully",
        timestamp=datetime.utcnow()
    )


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_endpoint(
    user_id: str,
    token: TokenPayload = Depends(RequirePermission("users:deactivate")),
    db: AsyncSession = Depends(get_tenant_db_session)
):
    """
    Soft delete user (deactivate).

    Implements openapi.yaml DELETE /users/{user_id}

    Requires: users:deactivate permission

    Returns:
        204 No Content on success
    """
    user = await get_user_by_id(db, user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "USER_NOT_FOUND",
                "message": f"User with ID '{user_id}' not found"
            }
        )

    # Prevent self-deletion
    if user_id == token.user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "CANNOT_DELETE_SELF",
                "message": "Cannot delete your own account"
            }
        )

    await soft_delete_user(db, user, deleted_by=token.user_id)

    return None


@router.put("/{user_id}/roles", response_model=UserResponse, status_code=status.HTTP_200_OK)
async def assign_user_roles_endpoint(
    user_id: str,
    request: AssignRolesRequest,
    token: TokenPayload = Depends(RequirePermission("roles:assign")),
    db: AsyncSession = Depends(get_tenant_db_session)
):
    """
    Assign roles to user.

    Implements openapi.yaml PUT /users/{user_id}/roles

    Requires: roles:assign permission

    Returns:
        UserResponse with updated user roles
    """
    user = await get_user_by_id(db, user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "USER_NOT_FOUND",
                "message": f"User with ID '{user_id}' not found"
            }
        )

    try:
        user = await assign_roles_to_user(
            db=db,
            user=user,
            role_ids=request.role_ids,
            updated_by=token.user_id
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_ROLE",
                "message": str(e)
            }
        )

    return UserResponse(
        success=True,
        data=user_to_read(user),
        message="Roles assigned successfully",
        timestamp=datetime.utcnow()
    )
