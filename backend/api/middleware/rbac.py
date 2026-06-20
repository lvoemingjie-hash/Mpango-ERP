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


class RequirePlatformAdmin:
    """
    Platform-level dependency that ONLY accepts identity-only super admin tokens.

    S2-R1 boundary fix: ``RequirePermission("system:admin")`` is insufficient
    for ``/api/v1/platform/**`` routes because a contextual tenant admin whose
    tenant role grants ``system:admin`` permission can access cross-tenant
    platform data.  This dependency closes that gap by requiring **both**:

    - ``token.is_identity_only == True``  (no tenant selected)
    - ``token.is_super_admin == True``    (carries the ``super_admin`` role)

    A contextual super admin (one who has selected a tenant) is rejected
    because platform endpoints expose cross-tenant data that must only be
    accessed from the platform scope, not from within a tenant boundary.
    """

    def __init__(self):
        self.permission = "platform:admin"

    async def __call__(self, request: Request) -> TokenPayload:
        """Validate that the caller is a platform super admin with identity-only JWT."""
        auth_ctx = get_auth_context(request)
        token = auth_ctx.token

        if not (token.is_identity_only and token.is_super_admin):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "PLATFORM_ADMIN_REQUIRED",
                    "message": (
                        "Platform endpoints require an identity-only super admin "
                        "token (no tenant context)."
                    ),
                },
            )

        return token
