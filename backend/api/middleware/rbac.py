"""RBAC (Role-Based Access Control) dependency."""
from fastapi import HTTPException, Request, status

from api.context import get_auth_context, get_tenant_context
from core.security import TokenPayload


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
    
    async def __call__(self, request: Request) -> TokenPayload:
        """Validate that the current user has the required permission."""
        auth_ctx = get_auth_context(request)
        tenant_ctx = get_tenant_context(request)

        user = tenant_ctx.user

        # Admin role has all permissions (bypass check)
        role_names = [role.name for role in user.roles]
        if "admin" in role_names:
            return auth_ctx.token
        
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
        
        return auth_ctx.token
