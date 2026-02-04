"""
Role management API endpoints.
Implements openapi.yaml /roles/* endpoints.

RBAC permissions enforced per rbac_matrix.md.
Tenant isolation enforced via JWT-derived search_path.
"""
from datetime import datetime
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_tenant_db_session
from api.middleware.rbac import RequirePermission
from core.security import TokenPayload
from crud.role import get_all_roles
from schemas.user import RoleListResponse, RoleRead

router = APIRouter()


@router.get("", response_model=RoleListResponse, status_code=status.HTTP_200_OK)
async def list_roles(
    token: TokenPayload = Depends(RequirePermission("roles:read")),
    db: AsyncSession = Depends(get_tenant_db_session)
):
    """
    List all roles.

    Implements openapi.yaml GET /roles

    Requires: roles:read permission

    Returns:
        RoleListResponse with all roles
    """
    roles = await get_all_roles(db)

    return RoleListResponse(
        success=True,
        data=[
            RoleRead(
                id=str(role.id),
                name=role.name,
                description=role.description
            )
            for role in roles
        ],
        timestamp=datetime.utcnow()
    )
