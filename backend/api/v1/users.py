"""
User management API endpoints.
Implements openapi.yaml /users/* endpoints as stubs.

All endpoints return 501 Not Implemented for skeleton.
RBAC permissions enforced per rbac_matrix.md.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query

from api.middleware.rbac import RequirePermission
from core.security import TokenPayload
from schemas.user import (
    UserCreateRequest,
    UserUpdateRequest,
    UserResponse,
    UserListResponse,
    AssignRolesRequest
)

router = APIRouter()


@router.get("", response_model=UserListResponse, status_code=status.HTTP_200_OK)
async def list_users(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(10, ge=1, le=100, description="Items per page"),
    token: TokenPayload = Depends(RequirePermission("users:read"))
):
    """
    List users with pagination.
    
    Implements openapi.yaml GET /users
    
    Requires: users:read permission
    
    Returns:
        501 Not Implemented (skeleton)
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="List users endpoint not implemented in skeleton"
    )


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    request: UserCreateRequest,
    token: TokenPayload = Depends(RequirePermission("users:create"))
):
    """
    Create a new user.
    
    Implements openapi.yaml POST /users
    
    Requires: users:create permission
    
    Returns:
        501 Not Implemented (skeleton)
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Create user endpoint not implemented in skeleton"
    )


@router.get("/{user_id}", response_model=UserResponse, status_code=status.HTTP_200_OK)
async def get_user(
    user_id: str,
    token: TokenPayload = Depends(RequirePermission("users:read"))
):
    """
    Get user by ID.
    
    Implements openapi.yaml GET /users/{user_id}
    
    Requires: users:read permission
    
    Returns:
        501 Not Implemented (skeleton)
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Get user endpoint not implemented in skeleton"
    )


@router.put("/{user_id}", response_model=UserResponse, status_code=status.HTTP_200_OK)
async def update_user(
    user_id: str,
    request: UserUpdateRequest,
    token: TokenPayload = Depends(RequirePermission("users:update"))
):
    """
    Update user.
    
    Implements openapi.yaml PUT /users/{user_id}
    
    Requires: users:update permission
    
    Returns:
        501 Not Implemented (skeleton)
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Update user endpoint not implemented in skeleton"
    )


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: str,
    token: TokenPayload = Depends(RequirePermission("users:deactivate"))
):
    """
    Soft delete user (deactivate).
    
    Implements openapi.yaml DELETE /users/{user_id}
    
    Requires: users:deactivate permission
    
    Returns:
        501 Not Implemented (skeleton)
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Delete user endpoint not implemented in skeleton"
    )


@router.put("/{user_id}/roles", response_model=UserResponse, status_code=status.HTTP_200_OK)
async def assign_user_roles(
    user_id: str,
    request: AssignRolesRequest,
    token: TokenPayload = Depends(RequirePermission("roles:assign"))
):
    """
    Assign roles to user.
    
    Implements openapi.yaml PUT /users/{user_id}/roles
    
    Requires: roles:assign permission
    
    Returns:
        501 Not Implemented (skeleton)
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Assign roles endpoint not implemented in skeleton"
    )
