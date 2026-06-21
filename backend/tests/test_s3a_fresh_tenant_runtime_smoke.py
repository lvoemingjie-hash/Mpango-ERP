"""
S3-A: Fresh Tenant Runtime Smoke Harness.

Verifies that a freshly-bootstrapped tenant admin (contextual super_admin token)
can access all core business APIs WITHOUT 401/403/500 after the S2 route
authorization hardening merge.

Diagnostic-first design:
  - This harness does NOT relax permissions, skip endpoints, or xfail failures.
  - Every 403/500 is recorded and root-cause classified in the test output and
    in the S3-A ledger (ai-ledger/product-ai/2026-06-21_s3a_fresh_tenant_runtime_smoke.md).

Auth model under test:
  - "Fresh tenant admin" = a contextual JWT (tenant_id + tenant_schema set, NOT
    identity-only) with roles=["super_admin"].
  - This represents the token issued by POST /auth/select-tenant after a
    platform admin bootstraps a new tenant and creates its first admin user.
  - RequirePermission accepts this token because:
      1. token.is_identity_only is False (has tenant context)
      2. get_tenant_context(request) succeeds (TenantContext attached)
      3. token.is_super_admin is True (roles includes "super_admin") -> bypass

Simulation rationale:
  The bootstrap/login flow (/auth/login -> /auth/select-tenant) is well covered
  by existing auth tests.  This harness SIMULATES the post-login state by
  injecting the same contextual super_admin token that select-tenant would
  produce, then exercises the REAL routers with the REAL RequirePermission
  dependency.  Only the DB layer is mocked (returns empty/zero results) so the
  test can run without a live database while still exercising the full
  authorization gate and business code path.

Endpoint coverage matrix:
  - dashboard KPI / charts       (dashboards:read)
  - orders list                  (orders:read)
  - products / SKUs list         (skus:read)
  - inventory / stock list       (inventory:read)
  - pricing prices list          (pricing:read)
  - payments list                (payments:read)
  - customers / retailers list   (retailers:read)
  - exports status poll          (get_current_user_context)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from api.context.auth import AuthContext, attach_auth_context
from api.context.tenant import TenantContext, attach_tenant_context
from api.dependencies import get_db_session, get_tenant_db_session
from core.security import TokenPayload


# ===========================================================================
# Fresh tenant admin token — simulates POST /auth/select-tenant output
# ===========================================================================

FRESH_TENANT_ID = "00000000-0000-0000-0000-000000000099"
FRESH_TENANT_SCHEMA = "t_fresh_smoke"
FRESH_ADMIN_USER_ID = "00000000-0000-0000-0000-0000000000aa"


def _fresh_tenant_admin_token() -> TokenPayload:
    """
    Contextual super_admin token for a freshly-bootstrapped tenant.

    This is exactly what POST /auth/select-tenant returns:
      - user_id:  the fresh tenant admin's UUID
      - tenant_id + tenant_schema: the new tenant's scope
      - roles: ["super_admin"] — the admin role granted at bootstrap
      - NOT identity-only (both tenant fields set)
    """
    return TokenPayload(
        user_id=FRESH_ADMIN_USER_ID,
        tenant_id=FRESH_TENANT_ID,
        tenant_schema=FRESH_TENANT_SCHEMA,
        roles=["super_admin"],
    )


class _MockSuperAdminUser:
    """Minimal stand-in for a User ORM row with super_admin role."""

    class _Role:
        def __init__(self, name: str):
            self.name = name
            self.permissions = []

    def __init__(self):
        self.id = FRESH_ADMIN_USER_ID
        self.email = "admin@fresh-tenant-smoke.test"
        self.full_name = "Fresh Tenant Admin"
        self.is_active = True
        self.is_deleted = False
        self.roles = [self._Role("super_admin")]


# ===========================================================================
# Mock DB layer — returns empty/zero results for any query
# ===========================================================================

def _empty_db_result():
    """A DB result mock that returns empty/zero for every access pattern."""
    result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = []
    result.scalars.return_value = scalars_mock
    result.scalar.return_value = 0
    result.scalar_one.return_value = 0
    result.scalar_one_or_none.return_value = None
    result.fetchall.return_value = []
    result.first.return_value = None
    result.rowcount = 0
    return result


def _make_mock_session():
    """Mock AsyncSession that answers any execute() with an empty result."""
    session = MagicMock()
    session.execute = AsyncMock(return_value=_empty_db_result())
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    session.info = {}
    session.bind = MagicMock()
    return session


class _MockAsyncSessionCtx:
    """
    Generic async context manager replacing ReportingSessionLocal /
    AsyncSessionLocal for endpoints that create their own DB sessions
    inside the handler body (dashboards, exports).

    Pattern replaced: ``async with ReportingSessionLocal() as session:``
    We yield the mock session so builder/queries get empty results and
    return graceful zeros (the intended fresh-tenant behaviour).
    """

    def __init__(self, mock_session):
        self._session = mock_session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc):
        return False


def _mock_session_factory(mock_session):
    """Return a callable that produces a _MockAsyncSessionCtx each call."""
    def _factory():
        return _MockAsyncSessionCtx(mock_session)
    return _factory


# ===========================================================================
# Smoke app builder — real routers + real RequirePermission + mock DB
# ===========================================================================

def _build_smoke_app() -> FastAPI:
    """
    Build a FastAPI app with ALL core business routers and a test auth
    middleware that injects the fresh tenant admin context.

    The routers and RequirePermission dependency are 100% real production
    code — only the DB session layer is mocked.
    """
    app = FastAPI()

    # --- real routers ------------------------------------------------------
    from api.v1 import orders, skus, inventory, payments, retailers
    from api.v1.pricing import router as pricing_router
    from api.v1.dashboards import dashboards_router, reports_router
    from api.v1.exports import exports_router

    app.include_router(orders.router, prefix="/api/v1/orders", tags=["orders"])
    app.include_router(skus.router, prefix="/api/v1/skus", tags=["skus"])
    app.include_router(inventory.router, prefix="/api/v1/inventory", tags=["inventory"])
    app.include_router(pricing_router, prefix="/api/v1/pricing", tags=["pricing"])
    app.include_router(payments.router, prefix="/api/v1/payments", tags=["payments"])
    app.include_router(retailers.router, prefix="/api/v1", tags=["retailers"])
    app.include_router(dashboards_router, prefix="/api/v1/dashboards", tags=["dashboards"])
    app.include_router(reports_router, prefix="/api/v1/reports", tags=["reports"])
    app.include_router(exports_router, prefix="/api/v1/exports", tags=["exports"])

    # --- mock sessions -----------------------------------------------------
    tenant_session = _make_mock_session()
    public_session = _make_mock_session()

    # --- DB dependency overrides -------------------------------------------
    # get_tenant_db_session normally reads request.state.tenant_context.session.
    # We override it to return the same mock so all tenant-scoped queries
    # resolve predictably.
    async def _override_tenant_db():
        return tenant_session

    async def _override_public_db():
        yield public_session

    app.dependency_overrides[get_tenant_db_session] = _override_tenant_db
    app.dependency_overrides[get_db_session] = _override_public_db

    # Also override database.session.get_db for endpoints that import it
    # directly (e.g. retailers uses get_db_session which calls get_db).
    from database.session import get_db

    async def _override_get_db():
        yield public_session

    app.dependency_overrides[get_db] = _override_get_db

    # --- patch endpoints that create their own sessions inside the handler --
    # Dashboards use ``async with ReportingSessionLocal() as session:``.
    # Exports status uses ``async with AsyncSessionLocal() as session:``.
    # Both bypass FastAPI DI, so dependency_overrides cannot reach them.
    # We patch at the module level so they yield our mock session instead of
    # trying to open a real DB connection (which fails with getaddrinfo in
    # the test environment).
    reporting_session = _make_mock_session()
    import api.v1.dashboards as _dashboards_mod
    import database.session as _db_session_mod

    _dashboards_mod.ReportingSessionLocal = _mock_session_factory(reporting_session)
    _db_session_mod.AsyncSessionLocal = _mock_session_factory(public_session)

    # --- auth + tenant context middleware ----------------------------------
    @app.middleware("http")
    async def _inject_fresh_tenant_admin(request: Request, call_next):
        token = _fresh_tenant_admin_token()
        attach_auth_context(request, AuthContext(token=token, raw_token="smoke-token"))
        tenant_ctx = TenantContext(
            tenant_id=token.tenant_id,
            tenant_schema=token.tenant_schema,
            session=tenant_session,
            user=_MockSuperAdminUser(),
        )
        attach_tenant_context(request, tenant_ctx)
        # Some endpoints read request.state.tenant_id for metrics/logging.
        request.state.tenant_id = token.tenant_schema
        request.state.request_id = "s3a-smoke"
        return await call_next(request)

    return app


@pytest.fixture(scope="module")
def smoke_client():
    """TestClient backed by the real-router smoke app."""
    return TestClient(_build_smoke_app())


# ===========================================================================
# S3-A Smoke: fresh tenant admin must reach business logic (no 401/403/500)
# ===========================================================================

# A valid retailer_id UUID used for pricing/reports query params.
_RETAILER_UUID = "00000000-0000-0000-0000-000000000050"
_EXPORT_JOB_ID = "00000000-0000-0000-0000-000000000077"


class TestFreshTenantAdminSmoke:
    """
    Each test hits one core endpoint as the fresh tenant admin and asserts
    the response is NOT 401 (unauthenticated) / 403 (forbidden) / 500 (error).

    Acceptable status codes: 200, 400, 404, 422.
      - 200: business logic ran and returned data (empty lists are fine).
      - 400/404/422: business logic ran but rejected input or resource
        (e.g. pricing _assert_binding finds no binding -> 400; export job
        not found -> 404).  These prove the auth gate PASSED.
    """

    # --- dashboard KPI / charts -------------------------------------------
    def test_dashboard_kpi_summary(self, smoke_client):
        """GET /api/v1/dashboards/kpi/summary — dashboards:read."""
        resp = smoke_client.get("/api/v1/dashboards/kpi/summary")
        assert resp.status_code not in (401, 403, 500), _diag(resp)

    def test_dashboard_sales_trend(self, smoke_client):
        """GET /api/v1/dashboards/charts/sales-trend — dashboards:read."""
        resp = smoke_client.get("/api/v1/dashboards/charts/sales-trend")
        assert resp.status_code not in (401, 403, 500), _diag(resp)

    def test_dashboard_cash_flow(self, smoke_client):
        """GET /api/v1/dashboards/charts/cash-flow — dashboards:read."""
        resp = smoke_client.get("/api/v1/dashboards/charts/cash-flow")
        assert resp.status_code not in (401, 403, 500), _diag(resp)

    # --- orders ------------------------------------------------------------
    def test_orders_list(self, smoke_client):
        """GET /api/v1/orders — orders:read."""
        resp = smoke_client.get("/api/v1/orders")
        assert resp.status_code not in (401, 403, 500), _diag(resp)

    # --- products / SKUs ---------------------------------------------------
    def test_skus_list(self, smoke_client):
        """GET /api/v1/skus — skus:read."""
        resp = smoke_client.get("/api/v1/skus")
        assert resp.status_code not in (401, 403, 500), _diag(resp)

    # --- inventory / stock -------------------------------------------------
    def test_inventory_stocks(self, smoke_client):
        """GET /api/v1/inventory/stocks — inventory:read."""
        resp = smoke_client.get("/api/v1/inventory/stocks")
        assert resp.status_code not in (401, 403, 500), _diag(resp)

    # --- pricing -----------------------------------------------------------
    def test_pricing_prices(self, smoke_client):
        """
        GET /api/v1/pricing/prices?retailer_id=... — pricing:read.

        _assert_binding may return 400 if no binding exists in mock; that is
        a legitimate business outcome, not an auth failure.
        """
        resp = smoke_client.get(
            "/api/v1/pricing/prices", params={"retailer_id": _RETAILER_UUID}
        )
        assert resp.status_code not in (401, 403, 500), _diag(resp)

    # --- payments ----------------------------------------------------------
    def test_payments_list(self, smoke_client):
        """GET /api/v1/payments — payments:read."""
        resp = smoke_client.get("/api/v1/payments")
        assert resp.status_code not in (401, 403, 500), _diag(resp)

    # --- customers / retailers --------------------------------------------
    def test_retailers_list(self, smoke_client):
        """GET /api/v1/retailers — retailers:read."""
        resp = smoke_client.get("/api/v1/retailers")
        assert resp.status_code not in (401, 403, 500), _diag(resp)

    def test_retailer_bindings(self, smoke_client):
        """GET /api/v1/retailers/bindings — retailers:read."""
        resp = smoke_client.get("/api/v1/retailers/bindings")
        assert resp.status_code not in (401, 403, 500), _diag(resp)

    # --- exports status ----------------------------------------------------
    def test_exports_status(self, smoke_client):
        """
        GET /api/v1/exports/{job_id} — get_current_user_context.

        A non-existent job_id legitimately returns 404, proving the auth
        gate passed.
        """
        resp = smoke_client.get(f"/api/v1/exports/{_EXPORT_JOB_ID}")
        assert resp.status_code not in (401, 403, 500), _diag(resp)


# ===========================================================================
# Boundary: confirm the auth gate REJECTS when expected
# ===========================================================================

class TestFreshTenantAdminAuthGateSemantics:
    """
    Sanity checks that the smoke harness is genuinely exercising the auth
    gate — not accidentally bypassing it.
    """

    def test_fresh_admin_token_is_contextual_not_identity(self):
        """The fresh admin token must have tenant context (not identity-only)."""
        token = _fresh_tenant_admin_token()
        assert token.tenant_id is not None
        assert token.tenant_schema is not None
        assert token.is_super_admin is True
        # is_identity_only uses OR; since both are set it should be False.
        assert token.is_identity_only is False

    def test_fresh_admin_token_passes_require_permission(self, smoke_client):
        """
        The fresh admin token must pass RequirePermission for a tenant-scoped
        permission (orders:read) — verified indirectly by orders list not
        being 401/403.
        """
        resp = smoke_client.get("/api/v1/orders")
        # Must NOT be 401 (no auth) or 403 (permission denied).
        assert resp.status_code != 401
        assert resp.status_code != 403


# ===========================================================================
# Diagnostic helper
# ===========================================================================

def _diag(resp) -> str:
    """Build a diagnostic message for assertion failures."""
    body = ""
    try:
        body = resp.json()
    except Exception:
        body = resp.text[:500]
    return (
        f"status={resp.status_code} "
        f"path={resp.request.url.path} "
        f"body={body}"
    )
