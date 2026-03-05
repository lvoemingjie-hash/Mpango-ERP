"""RBAC (Role-Based Access Control) dependency.

H-Fix-01: Super admins holding an Identity JWT can bypass tenant context
checks for system-level endpoints (e.g., wholesalers CRUD).
"""
from fastapi import HTTPException, Request, status

from api.context import get_auth_context, get_tenant_context
from core.security import TokenPayload


class RequirePermission:
    """
    Dependency that checks user has required permission.

    H-Fix-01 behaviour:
    - If the JWT is identity-only **and** the user has the ``super_admin``
      role, the permission check is bypassed (super admins have all perms).
    - Otherwise, tenant context is required and permissions are checked
      against the user's roles within that tenant.

    Usage:
        @router.get("/users")
        async def list_users(token: TokenPayload = Depends(RequirePermission("users:read"))):
            ...
    """

    def __init__(self, permission: str):
        self.permission = permission

    async def __call__(self, request: Request) -> TokenPayload:
        """Validate that the current user has the required permission."""
        auth_ctx = get_auth_context(request)
        token = auth_ctx.token

        # H-Fix-01: Super admin with identity-only JWT can access system
        # endpoints without selecting a tenant.
        if token.is_identity_only and token.is_super_admin:
            return token

        # For non-super-admin or contextual tokens, require tenant context.
        try:
            tenant_ctx = get_tenant_context(request)
        except HTTPException:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "TENANT_CONTEXT_REQUIRED",
                    "message": "Please select a tenant first (POST /auth/select-tenant)"
                }
            )

        user = tenant_ctx.user

        # Super admin within a tenant context also bypasses permission checks
        if token.is_super_admin:
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
