"""
RBAC (Role-Based Access Control) middleware for Mpango ERP.
Enforces permission-based access control per rbac_matrix.md.

Per requirements REQ-5 and REQ-8:
- Checks user permissions against required Permission.code
- Admin role bypasses all permission checks
- Returns 403 PERMISSION_DENIED if user lacks permission
"""
from typing import List
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user_context, get_tenant_db_session
from core.security import TokenPayload
from crud.user import get_user_with_permissions


class RequirePermission:
    """
    Dependency that checks user has required permission.
    
    Usage:
        @router.get("/users", dependencies=[Depends(RequirePermission("users:read"))])
        async def list_users():
            # Only users with users:read permission can access
    
    Or with token access:
        @router.get("/users")
        async def list_users(token: TokenPayload = Depends(RequirePermission("users:read"))):
            # token contains user_id, tenant_id, tenant_schema
    """
    
    def __init__(self, permission: str):
        """
        Initialize permission checker.
        
        Args:
            permission: Required permission code (e.g., "users:read", "orders:create")
        """
        self.permission = permission
    
    async def __call__(
        self,
        token: TokenPayload = Depends(get_current_user_context),
        db: AsyncSession = Depends(get_tenant_db_session)
    ) -> TokenPayload:
        """
        Check if user has required permission.
        
        Args:
            token: JWT payload with user context
            db: Tenant-scoped database session
            
        Returns:
            TokenPayload if permission check passes
            
        Raises:
            HTTPException 401: If user not found in database
            HTTPException 403: If user lacks required permission
        """
        # Load user with roles and permissions
        user = await get_user_with_permissions(db, token.user_id)
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "USER_NOT_FOUND", "message": "User not found"}
            )
        
        # Admin role has all permissions (bypass check)
        role_names = [role.name for role in user.roles]
        if "admin" in role_names:
            return token
        
        # Collect all permissions from user's roles
        user_permissions = set()
        for role in user.roles:
            for perm in role.permissions:
                user_permissions.add(perm.code)
        
        # Check if user has required permission
        if self.permission not in user_permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "PERMISSION_DENIED",
                    "message": f"Permission '{self.permission}' required"
                }
            )
        
        return token
