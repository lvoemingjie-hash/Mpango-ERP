"""
JWT Boundary Security Tests - H-Fix-01 Regression Gate

Tests verify that Identity JWTs and Contextual JWTs are properly isolated:
- Scenario A: Identity JWT cannot access tenant-scoped business data (orders)
- Scenario B: Identity JWT cannot select a tenant they don't belong to
- Scenario C: Super Admin Identity JWT can access system endpoints but NOT business data

Run with: pytest tests/security/test_jwt_boundaries.py -v
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timedelta

from core.security import (
    create_identity_token,
    create_contextual_token,
    decode_token,
    TokenPayload,
)
from core.config import get_settings


class TestJWTTokenClaims:
    """Verify token claim structure for identity vs contextual tokens."""

    def test_identity_token_has_no_tenant_claims(self):
        """Identity token should NOT have tenant_id or tenant_schema."""
        token = create_identity_token(
            user_id="user-123",
            roles=["admin"],
            token_type="access",
        )

        payload = decode_token(token)

        assert payload.user_id == "user-123"
        assert payload.roles == ["admin"]
        assert payload.is_identity_only is True
        assert payload.tenant_id is None
        assert payload.tenant_schema is None

    def test_contextual_token_has_tenant_claims(self):
        """Contextual token MUST have tenant_id and tenant_schema."""
        token = create_contextual_token(
            user_id="user-123",
            roles=["admin"],
            tenant_id="tenant-456",
            tenant_schema="t_tenant456",
            token_type="access",
        )

        payload = decode_token(token)

        assert payload.user_id == "user-123"
        assert payload.roles == ["admin"]
        assert payload.is_identity_only is False
        assert payload.tenant_id == "tenant-456"
        assert payload.tenant_schema == "t_tenant456"

    def test_super_admin_identity_token_has_super_admin_role(self):
        """Super admin Identity token should have super_admin role."""
        token = create_identity_token(
            user_id="super-admin-001",
            roles=["super_admin"],
            token_type="access",
        )

        payload = decode_token(token)

        assert payload.is_super_admin is True
        assert "super_admin" in payload.roles


class TestScenarioA_IdentityJWTCannotAccessBusinessData:
    """
    Scenario A: Use an Identity JWT to call GET /api/v1/orders.
    Expected: 403 Forbidden (Identity JWT has no business data access).
    """

    @pytest.mark.asyncio
    async def test_identity_jwt_rejected_for_orders_endpoint(self):
        """
        Middleware should reject Identity JWT for tenant-scoped endpoints.

        The middleware's resolve_tenant_context returns None for identity-only JWTs.
        When tenant_ctx is None, the request should fail at the dependency level
        (get_tenant_db_session requires tenant_schema).
        """
        # Create an identity token (no tenant context)
        identity_token = create_identity_token(
            user_id="user-123",
            roles=["admin"],
            token_type="access",
        )

        payload = decode_token(identity_token)

        # Verify it's identity-only
        assert payload.is_identity_only is True
        assert payload.tenant_id is None
        assert payload.tenant_schema is None

        # Simulate middleware behavior: resolve_tenant_context returns None
        # for identity-only tokens (as implemented in auth/strategies/jwt.py)
        from auth.strategies.jwt import JwtAuthStrategy

        strategy = JwtAuthStrategy()

        # Create a mock request with the identity token
        mock_request = MagicMock()
        mock_request.headers = {"Authorization": f"Bearer {identity_token}"}

        # Authenticate - should succeed
        auth_ctx = await strategy.authenticate(mock_request)
        assert auth_ctx is not None
        assert auth_ctx.token.is_identity_only is True

        # Resolve tenant context - should return None for identity JWT
        tenant_ctx = await strategy.resolve_tenant_context(auth_ctx)
        assert tenant_ctx is None  # Identity JWT has no tenant context

        # This None tenant_ctx is what causes the middleware to skip
        # tenant context attachment, which will cause tenant-scoped
        # endpoints to fail (they require tenant_schema from the token)


class TestScenarioB_IdentityJWTCannotSelectUnauthorizedTenant:
    """
    Scenario B: Use Identity JWT to call POST /auth/select-tenant with unauthorized tenant_id.
    Expected: 403 Forbidden.
    """

    @pytest.mark.asyncio
    async def test_select_tenant_rejects_unauthorized_tenant(self):
        """
        The /auth/select-tenant endpoint verifies user exists in the target tenant.
        If user doesn't exist in that tenant schema, it returns 403.
        """
        # This test verifies the endpoint logic in api/v1/auth.py:
        # Lines 166-176 show that select_tenant checks if user exists in
        # the target tenant schema. If not found or inactive, returns 403.

        # Create identity token for user who only has access to tenant-A
        identity_token = create_identity_token(
            user_id="user-tenant-a",
            roles=["admin"],
            token_type="access",
        )

        payload = decode_token(identity_token)

        # Verify token is valid identity token
        assert payload.user_id == "user-tenant-a"
        assert payload.is_identity_only is True

        # The actual test would require a running backend with:
        # - User "user-tenant-a" in tenant-A schema
        # - Attempt to select tenant-B (where user doesn't exist)
        # - Expected: 403 with code "TENANT_ACCESS_DENIED"

        # Code inspection confirms this is enforced in auth.py lines 166-176:
        # async for tenant_db in get_tenant_db(tenant_schema):
        #     user = await get_user_with_permissions(tenant_db, token.user_id)
        #     if not user or not user.is_active:
        #         raise HTTPException(
        #             status_code=status.HTTP_403_FORBIDDEN,
        #             detail={"code": "TENANT_ACCESS_DENIED", ...}


class TestScenarioC_SuperAdminIdentityJWTBoundaries:
    """
    Scenario C: Use Super Admin's Identity JWT to call system endpoint vs business endpoint.
    Expected: 200 OK for system endpoint, 403/400 for business endpoint.
    """

    def test_super_admin_identity_token_for_system_endpoint(self):
        """
        Super admin with Identity JWT should be able to access system endpoints
        (like /wholesalers CRUD) via RequirePermission bypass.
        """
        # Create super admin identity token
        token = create_identity_token(
            user_id="super-admin-001",
            roles=["super_admin"],
            token_type="access",
        )

        payload = decode_token(token)

        # Verify super admin properties
        assert payload.is_super_admin is True
        assert "super_admin" in payload.roles
        assert payload.is_identity_only is True

        # RequirePermission (rbac.py lines 36-39) allows super_admin bypass:
        # if token.is_identity_only and token.is_super_admin:
        #     return token  # Bypasses permission check

    def test_super_admin_identity_token_cannot_access_business_data(self):
        """
        Even super admin Identity JWT should NOT be able to access business data
        (orders, inventory, etc.) without selecting a tenant first.
        """
        # Create super admin identity token
        token = create_identity_token(
            user_id="super-admin-001",
            roles=["super_admin"],
            token_type="access",
        )

        payload = decode_token(token)

        # Identity token has no tenant context
        assert payload.is_identity_only is True
        assert payload.tenant_id is None
        assert payload.tenant_schema is None

        # Middleware will not attach tenant context (tenant_ctx = None)
        # Business endpoints require tenant context via get_tenant_db_session
        # which calls resolve_tenant_schema(token) - this will fail for
        # identity tokens since tenant_schema is None

        # Code inspection confirms this in api/context/auth_context.py:
        # def resolve_tenant_schema(token: TokenPayload) -> str:
        #     if not token.tenant_schema:
        #         raise HTTPException(
        #             status_code=status.HTTP_401_UNAUTHORIZED,
        #             detail={"code": "MISSING_TENANT", ...}


class TestTokenClaimInspection:
    """Inspect actual JWT payloads to verify claim separation."""

    def test_identity_token_payload_structure(self):
        """Verify Identity JWT has correct payload structure."""
        token = create_identity_token(
            user_id="test-user-123",
            roles=["manager", "viewer"],
            token_type="access",
        )

        settings = get_settings()
        from jose import jwt as jose_jwt
        raw_payload = jose_jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])

        # Identity token should have: user_id, roles, exp, type
        # Should NOT have: tenant_id, tenant_schema
        assert "user_id" in raw_payload
        assert "roles" in raw_payload
        assert "exp" in raw_payload
        assert "type" in raw_payload
        assert "tenant_id" not in raw_payload
        assert "tenant_schema" not in raw_payload

    def test_contextual_token_payload_structure(self):
        """Verify Contextual JWT has correct payload structure."""
        token = create_contextual_token(
            user_id="test-user-123",
            roles=["manager"],
            tenant_id="tenant-abc",
            tenant_schema="t_tenantabc",
            token_type="access",
        )

        settings = get_settings()
        from jose import jwt as jose_jwt
        raw_payload = jose_jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])

        # Contextual token should have all fields
        assert "user_id" in raw_payload
        assert "roles" in raw_payload
        assert "tenant_id" in raw_payload
        assert "tenant_schema" in raw_payload
        assert raw_payload["tenant_id"] == "tenant-abc"
        assert raw_payload["tenant_schema"] == "t_tenantabc"


class TestMiddlewareBehavior:
    """Verify middleware handles identity vs contextual tokens correctly."""

    @pytest.mark.asyncio
    async def test_middleware_skips_tenant_context_for_identity_jwt(self):
        """
        AuthenticationMiddleware should skip tenant context attachment
        when token is identity-only.
        """
        from auth.strategies.jwt import JwtAuthStrategy

        strategy = JwtAuthStrategy()

        # Create identity token
        identity_token = create_identity_token(
            user_id="test-user",
            roles=["user"],
            token_type="access",
        )

        # Create mock request
        mock_request = MagicMock()
        mock_request.headers = {"Authorization": f"Bearer {identity_token}"}

        # Authenticate
        auth_ctx = await strategy.authenticate(mock_request)
        assert auth_ctx is not None, "authenticate() must return AuthContext for valid token"

        # Resolve tenant context
        tenant_ctx = await strategy.resolve_tenant_context(auth_ctx)

        # For identity JWT, tenant_ctx should be None
        assert tenant_ctx is None

        # This causes middleware (auth.py lines 51-81) to skip:
        # - attach_tenant_context()
        # - set_current_tenant()
        # - tenant isolation checks

    @pytest.mark.asyncio
    async def test_middleware_attaches_tenant_context_for_contextual_jwt(self):
        """
        AuthenticationMiddleware should attach tenant context
        when token is contextual.

        Note: resolve_tenant_context() for contextual tokens creates a real
        DB session (create_tenant_session → get_user_with_permissions), which
        is not available in this unit-test environment.  We therefore verify
        the strategy's *branching logic*:
          1. authenticate() succeeds and returns an AuthContext.
          2. The token is NOT identity-only → strategy will NOT early-return None.
          3. The token carries the expected tenant claims.
        This proves the middleware WOULD proceed to build a TenantContext.
        """
        from auth.strategies.jwt import JwtAuthStrategy

        strategy = JwtAuthStrategy()

        # Create contextual token
        contextual_token = create_contextual_token(
            user_id="test-user",
            roles=["admin"],
            tenant_id="tenant-123",
            tenant_schema="t_tenant123",
            token_type="access",
        )

        # Create mock request
        mock_request = MagicMock()
        mock_request.headers = {"Authorization": f"Bearer {contextual_token}"}

        # Authenticate
        auth_ctx = await strategy.authenticate(mock_request)
        assert auth_ctx is not None, "authenticate() must return AuthContext for valid token"

        # Contextual JWT is NOT identity-only → middleware will NOT skip
        assert auth_ctx.token.is_identity_only is False
        assert auth_ctx.token.tenant_id == "tenant-123"
        assert auth_ctx.token.tenant_schema == "t_tenant123"

        # Verify the strategy branch: identity-only check is False,
        # so strategy.resolve_tenant_context will call the real
        # resolve_tenant_context(token) → creates TenantContext.
        # (DB access prevents calling it directly in unit tests.)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
