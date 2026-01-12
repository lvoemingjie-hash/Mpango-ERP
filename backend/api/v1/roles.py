"""
Role management API endpoints.
Implements openapi.yaml /roles/* endpoints as stubs.

All endpoints return 501 Not Implemented for skeleton.
RBAC permissions enforced per rbac_matrix.md.
"""
from fastapi import APIRouter, Depends, HTTPException, status

from api.middleware.rbac import RequirePermission
from core.security import TokenPayload
from schemas.user import RoleListResponse

router = APIRouter()


@router.get("", response_model=RoleListResponse, status_code=status.HTTP_200_OK)
async def list_roles(token: TokenPayload = Depends(RequirePermission("roles:read"))):
    """
    List all roles.
    
    Implements openapi.yaml GET /roles
    
    Requires: roles:read permission
    
    Returns:
        501 Not Implemented (skeleton)
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="List roles endpoint not implemented in skeleton"
    )
