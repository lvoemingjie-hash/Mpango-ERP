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
    Platform-level dependency that ONLY accepts strict identity-only super admin tokens.

    S2-R1 boundary fix: ``RequirePermission("system:admin")`` is insufficient
    for ``/api/v1/platform/**`` routes because a contextual tenant admin whose
    tenant role grants ``system:admin`` permission can access cross-tenant
    platform data.  This dependency closes that gap by requiring **all**:

    - ``token.tenant_id is None``       (no tenant selected)
    - ``token.tenant_schema is None``   (no tenant schema)
    - ``token.is_super_admin == True``  (carries the ``super_admin`` role)

    S2-R2 strict identity context fix: We do NOT use ``TokenPayload.is_identity_only``
    because that property uses OR semantics (``tenant_id is None OR tenant_schema is
    None``).  A partial-context token where one field is set and the other is None
    would incorrectly pass that check.  For a platform security boundary we require
    strict AND semantics: **both** ``tenant_id`` and ``tenant_schema`` must be None.

    A contextual super admin (one who has selected a tenant) is rejected
    because platform endpoints expose cross-tenant data that must only be
    accessed from the platform scope, not from within a tenant boundary.
    """

    def __init__(self):
        self.permission = "platform:admin"

    async def __call__(self, request: Request) -> TokenPayload:
        """Validate that the caller is a platform super admin with strict identity-only JWT."""
        auth_ctx = get_auth_context(request)
        token = auth_ctx.token

        # S2-R2: Use explicit field checks, NOT token.is_identity_only.
        #
        # TokenPayload.is_identity_only is defined as:
        #   tenant_id is None OR tenant_schema is None
        # This OR semantics is designed for the legacy identity/context token
        # distinction, where it signals "this token may not have full tenant
        # context." For a PLATFORM SECURITY BOUNDARY, OR is dangerous: a
        # crafted or malformed token with tenant_id set but tenant_schema None
        # (or vice versa) would pass is_identity_only and bypass the gate.
        #
        # We require strict AND: both fields must be None.
        is_strict_identity = (
            token.tenant_id is None and token.tenant_schema is None
        )

        if not (is_strict_identity and token.is_super_admin):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "PLATFORM_ADMIN_REQUIRED",
                    "message": (
                        "Platform endpoints require a strict identity-only "
                        "super admin token (no tenant context)."
                    ),
                },
            )

        return token
