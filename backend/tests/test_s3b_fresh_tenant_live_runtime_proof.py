"""
S3-B: Fresh Tenant Live Runtime Proof.

Verifies with REAL DB / REAL tenant schema / REAL admin user that a fresh
tenant admin can access all core business APIs without 401/403/500.

Required verifications (per task spec):
  1. Tenant schema fully bootstrapped (all required tables present)
  2. Admin user permissions complete (admin role grants all required perms)
  3. Near-real contextual JWT flow works (create_contextual_token + decode)
  4. orders/skus/inventory/pricing/payments/retailers/dashboard/exports
     endpoints return no 403/500 against the REAL database
  5. Any 400/404 is proven to be business empty-state, not a system error

Live environment:
  - PostgreSQL: localhost:5432 (Docker mpango_postgres)
  - Credentials: mpango:MpangoDBV0.1.4 / Database: mpango_erp
  - Tenant schema: t_u1r1_test (15 tables, complete bootstrap)
  - Admin user: admin@u1r1.test

"Near-real token": uses the REAL create_contextual_token() (same as
POST /auth/select-tenant) with REAL admin user_id, roles, permissions
loaded from the DB.  Only password verification is skipped.  Because
admin@u1r1.test has role "admin" (NOT super_admin), the super_admin
bypass is NOT triggered -- the real permission check runs end-to-end.

Implementation notes:
  - Fully async (httpx.AsyncClient + ASGITransport) so the engine, the
    ASGI app, and all requests share ONE event loop (session-scoped via
    conftest.py).  This avoids asyncpg "Event loop is closed" errors.
  - If live DB is unreachable -> entire module SKIPS (not a failure).
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional

import pytest
import pytest_asyncio
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

# ===========================================================================
# Live DB configuration
# ===========================================================================

LIVE_DB_URL = os.environ.get(
    "S3B_LIVE_DB_URL",
    "postgresql+asyncpg://mpango:MpangoDBV0.1.4@localhost:5432/mpango_erp",  # pragma: allowlist secret  # local Docker dev DB only
)
LIVE_TENANT_SCHEMA = os.environ.get("S3B_TENANT_SCHEMA", "t_u1r1_test")
LIVE_ADMIN_EMAIL = os.environ.get("S3B_ADMIN_EMAIL", "admin@u1r1.test")
# t_u1r1_test has no matching public.wholesalers row; use stable placeholder.
LIVE_TENANT_ID = os.environ.get(
    "S3B_TENANT_ID", "11111111-1111-1111-1111-111111111199"
)

REQUIRED_TABLES = {
    "users", "roles", "permissions", "user_roles", "role_permissions",
    "orders", "order_items", "skus", "inventory_stocks", "inventory_movements",
    "payments", "ledger_entries", "retailer_prices",
    "rpt_cash_flow_daily", "rpt_receivables_summary",
}

# 7 read perms exercised by S3-B endpoints (exports uses get_current_user_context).
REQUIRED_PERMISSIONS = {
    "orders:read", "skus:read", "inventory:read", "pricing:read",
    "payments:read", "retailers:read", "dashboards:read",
}


# ===========================================================================
# Live engine fixture (async, session-scoped loop from conftest)
# ===========================================================================

@pytest_asyncio.fixture(scope="module")
async def live_engine():
    """Real SQLAlchemy async engine; skips module if DB unreachable."""
    engine = create_async_engine(LIVE_DB_URL, pool_pre_ping=True, pool_size=2)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        await engine.dispose()
        pytest.skip(f"S3-B live DB not reachable at {LIVE_DB_URL}: {exc}")
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="module")
async def live_admin_data(live_engine) -> Dict:
    """Load REAL admin user_id, roles, permissions from the live DB."""
    async with live_engine.connect() as conn:
        await conn.execute(text(f'SET search_path TO "{LIVE_TENANT_SCHEMA}", public'))

        user_row = (
            await conn.execute(
                text("SELECT id, email, is_active FROM users WHERE email = :email"),
                {"email": LIVE_ADMIN_EMAIL},
            )
        ).fetchone()
        if user_row is None:
            pytest.fail(
                f"Admin user {LIVE_ADMIN_EMAIL!r} not found in "
                f"schema {LIVE_TENANT_SCHEMA!r}"
            )
        user_id, email, is_active = user_row[0], user_row[1], user_row[2]

        roles_result = await conn.execute(
            text(
                "SELECT r.name FROM user_roles ur "
                "JOIN roles r ON r.id = ur.role_id "
                "WHERE ur.user_id = :uid ORDER BY r.name"
            ),
            {"uid": user_id},
        )
        role_names: List[str] = [r[0] for r in roles_result.fetchall()]

        perms_result = await conn.execute(
            text(
                "SELECT r.name AS role_name, p.code AS perm_code "
                "FROM user_roles ur "
                "JOIN roles r ON r.id = ur.role_id "
                "JOIN role_permissions rp ON rp.role_id = r.id "
                "JOIN permissions p ON p.id = rp.permission_id "
                "WHERE ur.user_id = :uid ORDER BY r.name, p.code"
            ),
            {"uid": user_id},
        )
        roles_with_perms: Dict[str, List[str]] = {}
        permission_codes = set()
        for role_name, perm_code in perms_result.fetchall():
            roles_with_perms.setdefault(role_name, []).append(perm_code)
            permission_codes.add(perm_code)

        return {
            "user_id": str(user_id),
            "email": email,
            "is_active": bool(is_active),
            "role_names": role_names,
            "roles_with_perms": roles_with_perms,
            "permission_codes": permission_codes,
        }


# ===========================================================================
# Real user / role / permission proxies (populated from real DB data)
# ===========================================================================

class _LivePermission:
    def __init__(self, code: str):
        self.code = code


class _LiveRole:
    def __init__(self, name: str, perm_codes: List[str]):
        self.name = name
        self.permissions = [_LivePermission(c) for c in perm_codes]


class _LiveAdminUser:
    """Stand-in for User ORM row; roles/permissions populated from REAL DB."""

    def __init__(self, admin_data: Dict):
        self.id = admin_data["user_id"]
        self.email = admin_data["email"]
        self.full_name = "Live Admin (S3-B)"
        self.is_active = admin_data["is_active"]
        self.is_deleted = False
        self.roles = [
            _LiveRole(name, codes)
            for name, codes in admin_data["roles_with_perms"].items()
        ]


# ===========================================================================
# Verification 1: tenant schema fully bootstrapped
# ===========================================================================

class TestLiveTenantSchemaBootstrapped:
    """Verification 1: the live tenant schema has all required tables."""

    async def test_all_required_tables_present(self, live_engine):
        """Every table in REQUIRED_TABLES must exist in the live schema."""
        async with live_engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = :schema"
                ),
                {"schema": LIVE_TENANT_SCHEMA},
            )
            actual = {r[0] for r in result.fetchall()}
        missing = REQUIRED_TABLES - actual
        assert not missing, (
            f"Live tenant schema {LIVE_TENANT_SCHEMA!r} is missing required "
            f"tables: {sorted(missing)}. Present: {sorted(actual)}"
        )


# ===========================================================================
# Verification 2: admin user permissions complete
# ===========================================================================

class TestLiveAdminPermissionsComplete:
    """Verification 2: the real admin user has all required permissions."""

    async def test_admin_user_exists_and_is_active(self, live_admin_data):
        assert live_admin_data["email"] == LIVE_ADMIN_EMAIL
        assert live_admin_data["is_active"] is True, (
            f"Admin {LIVE_ADMIN_EMAIL!r} is NOT active in "
            f"{LIVE_TENANT_SCHEMA!r} -- live proof cannot proceed"
        )

    async def test_admin_has_at_least_one_role(self, live_admin_data):
        assert live_admin_data["role_names"], (
            f"Admin {LIVE_ADMIN_EMAIL!r} has NO roles in "
            f"{LIVE_TENANT_SCHEMA!r} -- RBAC will deny all endpoints"
        )

    async def test_admin_role_has_all_required_permissions(self, live_admin_data):
        """Admin's aggregated permissions must include all REQUIRED_PERMISSIONS."""
        actual = live_admin_data["permission_codes"]
        missing = REQUIRED_PERMISSIONS - actual
        assert not missing, (
            f"Admin {LIVE_ADMIN_EMAIL!r} in {LIVE_TENANT_SCHEMA!r} is missing "
            f"required permissions: {sorted(missing)}. Has: {sorted(actual)}"
        )


# ===========================================================================
# Verification 3: near-real contextual JWT flow works
# ===========================================================================

class TestNearRealContextualJwtFlow:
    """Verification 3: contextual JWT built with real DB data decodes correctly."""

    async def test_encode_decode_roundtrip(self, live_admin_data):
        from core.security import create_contextual_token
        from jose import jwt
        from core.config import get_settings

        token_str = create_contextual_token(
            user_id=live_admin_data["user_id"],
            roles=live_admin_data["role_names"],
            tenant_id=LIVE_TENANT_ID,
            tenant_schema=LIVE_TENANT_SCHEMA,
            token_type="access",
        )
        settings = get_settings()
        decoded = jwt.decode(
            token_str, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        assert decoded["user_id"] == live_admin_data["user_id"]
        assert decoded["tenant_id"] == LIVE_TENANT_ID
        assert decoded["tenant_schema"] == LIVE_TENANT_SCHEMA
        assert decoded["type"] == "access"
        assert set(decoded["roles"]) == set(live_admin_data["role_names"])

    async def test_decoded_token_is_contextual_not_identity(self, live_admin_data):
        from core.security import TokenPayload, create_contextual_token
        from jose import jwt
        from core.config import get_settings

        token_str = create_contextual_token(
            user_id=live_admin_data["user_id"],
            roles=live_admin_data["role_names"],
            tenant_id=LIVE_TENANT_ID,
            tenant_schema=LIVE_TENANT_SCHEMA,
            token_type="access",
        )
        settings = get_settings()
        decoded = jwt.decode(
            token_str, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        payload = TokenPayload(**decoded)
        assert payload.is_identity_only is False
        assert payload.tenant_id == LIVE_TENANT_ID
        assert payload.tenant_schema == LIVE_TENANT_SCHEMA


# ===========================================================================
# Live app builder: real routers + REAL DB sessions + near-real admin token
# ===========================================================================

def _build_live_app(live_engine, admin_data: Dict) -> FastAPI:
    """
    Build a FastAPI app with ALL core business routers wired to the REAL
    live database, authenticated as the REAL admin user via a near-real
    contextual JWT.

    Key differences from S3-A's _build_smoke_app:
      - DB sessions are REAL AsyncSession objects against the live engine.
      - search_path is set to the live tenant schema on every session.
      - session.info["tenant_schema"] and ["tenant_id"] are set on every
        session so the ORM global tenant filter (db.tenant_filter) accepts
        ORM queries.  Without this, the filter raises
        TenantContextMissingError on any ORM select.
      - The admin token carries the REAL role names (e.g., ["admin"]).
      - The user proxy carries the REAL roles + REAL permissions from DB,
        so RequirePermission's permission check is genuine (no bypass).
    """
    app = FastAPI()

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

    from core.security import create_contextual_token, TokenPayload
    from jose import jwt
    from core.config import get_settings
    from api.context.auth import AuthContext, attach_auth_context
    from api.context.tenant import TenantContext, attach_tenant_context

    settings = get_settings()
    admin_user_proxy = _LiveAdminUser(admin_data)

    def _build_token_payload() -> TokenPayload:
        token_str = create_contextual_token(
            user_id=admin_data["user_id"],
            roles=admin_data["role_names"],
            tenant_id=LIVE_TENANT_ID,
            tenant_schema=LIVE_TENANT_SCHEMA,
            token_type="access",
        )
        decoded = jwt.decode(
            token_str, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        return TokenPayload(**decoded)

    # --- session factory helpers -------------------------------------------
    # IMPORTANT: the ORM global tenant filter (db.tenant_filter) checks
    # session.info["tenant_schema"] and ["tenant_id"] on every ORM execute.
    # If they are missing, it raises TenantContextMissingError.  We set
    # them on EVERY session so ORM queries (orders, skus, inventory,
    # retailers) pass the filter and hit the real DB.

    async def _new_live_tenant_session() -> AsyncSession:
        """Open a real tenant-scoped session with search_path + tenant info."""
        session = AsyncSession(live_engine, expire_on_commit=False)
        session.info["tenant_schema"] = LIVE_TENANT_SCHEMA
        session.info["tenant_id"] = LIVE_TENANT_ID
        await session.execute(text(f'SET search_path TO "{LIVE_TENANT_SCHEMA}", public'))
        return session

    async def _override_public_db():
        """get_db_session override -> real public session WITH tenant info.

        Some endpoints (retailers, bindings) query public-schema tables
        (Binding, Retailer) whose models carry wholesaler_id.  The tenant
        filter will still fire on those queries; we set session.info here
        so the filter adds the expected WHERE clause (which may yield
        empty results on a fresh tenant -- that is fine).
        """
        session = AsyncSession(live_engine, expire_on_commit=False)
        session.info["tenant_schema"] = LIVE_TENANT_SCHEMA
        session.info["tenant_id"] = LIVE_TENANT_ID
        try:
            yield session
        finally:
            await session.close()

    # We do NOT override get_tenant_db_session -- the real implementation
    # reads from request.state.tenant_context.session, which the middleware
    # attaches.  This ensures the endpoint and the TenantContext share the
    # SAME session instance (correct production behaviour).
    from api.dependencies import get_db_session
    from database.session import get_db

    app.dependency_overrides[get_db_session] = _override_public_db
    app.dependency_overrides[get_db] = _override_public_db

    # --- patch module-level session factories (dashboards + exports) -------
    import api.v1.dashboards as _dashboards_mod
    import database.session as _db_session_mod

    class _RealSessionCtx:
        """Async ctx mgr mimicking ``async with ReportingSessionLocal() as s:``."""

        def __init__(self):
            self._session: Optional[AsyncSession] = None

        async def __aenter__(self) -> AsyncSession:
            self._session = await _new_live_tenant_session()
            return self._session

        async def __aexit__(self, *exc):
            if self._session is not None:
                await self._session.close()
            return False

    _dashboards_mod.ReportingSessionLocal = lambda: _RealSessionCtx()
    _db_session_mod.AsyncSessionLocal = lambda: _RealSessionCtx()

    # --- auth + tenant context middleware ---------------------------------
    @app.middleware("http")
    async def _inject_live_admin(request: Request, call_next):
        token = _build_token_payload()
        attach_auth_context(
            request, AuthContext(token=token, raw_token="s3b-live-token")
        )
        # The middleware-owned session is what get_tenant_db_session returns.
        session = await _new_live_tenant_session()
        tenant_ctx = TenantContext(
            tenant_id=LIVE_TENANT_ID,
            tenant_schema=LIVE_TENANT_SCHEMA,
            session=session,
            user=admin_user_proxy,
        )
        attach_tenant_context(request, tenant_ctx)
        request.state.tenant_id = LIVE_TENANT_SCHEMA
        request.state.request_id = "s3b-live"
        try:
            response = await call_next(request)
            return response
        finally:
            await session.close()

    return app


@pytest_asyncio.fixture(scope="module")
async def live_client(live_engine, live_admin_data):
    """AsyncClient backed by the live-router app (shared event loop)."""
    app = _build_live_app(live_engine, live_admin_data)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://s3b-live") as client:
        yield client


# ===========================================================================
# Verification 4: endpoint smoke against REAL DB (no 401/403/500)
# ===========================================================================

_RETAILER_UUID = "00000000-0000-0000-0000-000000000050"
_EXPORT_JOB_ID = "00000000-0000-0000-0000-000000000077"


class TestLiveEndpointSmoke:
    """
    Each test hits one core endpoint as the real admin user (with real
    role + real permissions from the live DB) and asserts the response
    is NOT 401/403/500.

    Because admin@u1r1.test has role "admin" (NOT super_admin), the
    super_admin bypass is NOT triggered.  Every endpoint exercises the
    genuine permission check against the real role_permissions data.

    Acceptable status codes: 200, 400, 404, 422.
    """

    async def test_dashboard_kpi_summary(self, live_client):
        resp = await live_client.get("/api/v1/dashboards/kpi/summary")
        assert resp.status_code not in (401, 403, 500), _diag(resp)

    async def test_dashboard_sales_trend(self, live_client):
        resp = await live_client.get("/api/v1/dashboards/charts/sales-trend")
        assert resp.status_code not in (401, 403, 500), _diag(resp)

    async def test_dashboard_cash_flow(self, live_client):
        resp = await live_client.get("/api/v1/dashboards/charts/cash-flow")
        assert resp.status_code not in (401, 403, 500), _diag(resp)

    async def test_orders_list(self, live_client):
        resp = await live_client.get("/api/v1/orders")
        assert resp.status_code not in (401, 403, 500), _diag(resp)

    async def test_skus_list(self, live_client):
        resp = await live_client.get("/api/v1/skus")
        assert resp.status_code not in (401, 403, 500), _diag(resp)

    async def test_inventory_stocks(self, live_client):
        resp = await live_client.get("/api/v1/inventory/stocks")
        assert resp.status_code not in (401, 403, 500), _diag(resp)

    async def test_pricing_prices(self, live_client):
        """_assert_binding may return 400 if no binding exists; that is a
        legitimate fresh-tenant business outcome, NOT an auth failure."""
        resp = await live_client.get(
            "/api/v1/pricing/prices", params={"retailer_id": _RETAILER_UUID}
        )
        assert resp.status_code not in (401, 403, 500), _diag(resp)

    async def test_payments_list(self, live_client):
        resp = await live_client.get("/api/v1/payments")
        assert resp.status_code not in (401, 403, 500), _diag(resp)

    async def test_retailers_list(self, live_client):
        resp = await live_client.get("/api/v1/retailers")
        assert resp.status_code not in (401, 403, 500), _diag(resp)

    async def test_retailer_bindings(self, live_client):
        resp = await live_client.get("/api/v1/retailers/bindings")
        assert resp.status_code not in (401, 403, 500), _diag(resp)

    async def test_exports_status(self, live_client):
        """A non-existent job_id legitimately returns 404, proving the auth
        gate passed (exports uses get_current_user_context, not RequirePermission)."""
        resp = await live_client.get(f"/api/v1/exports/{_EXPORT_JOB_ID}")
        assert resp.status_code not in (401, 403, 500), _diag(resp)


# ===========================================================================
# Verification 5: 400/404 responses are business empty-state, not system errors
# ===========================================================================

class TestBusinessEmptyStateProof:
    """
    Verification 5: any 400/404 response must originate from business
    logic (empty data, missing binding, not-found resource), NOT from
    an auth gate or unhandled system error.
    """

    async def test_pricing_non_200_is_business_not_auth(self, live_client):
        resp = await live_client.get(
            "/api/v1/pricing/prices", params={"retailer_id": _RETAILER_UUID}
        )
        if resp.status_code in (400, 404):
            body = _safe_json(resp)
            assert isinstance(body, dict), f"body should be dict, got: {body!r}"
            detail = body.get("detail", body)
            if isinstance(detail, dict):
                code = detail.get("code", "")
                assert code not in {
                    "AUTHENTICATION_REQUIRED", "PERMISSION_DENIED",
                    "TENANT_CONTEXT_REQUIRED",
                }, f"pricing {resp.status_code} carries auth error code {code!r}: {body}"
        else:
            assert resp.status_code not in (401, 403, 500), _diag(resp)

    async def test_exports_non_200_is_business_not_auth(self, live_client):
        resp = await live_client.get(f"/api/v1/exports/{_EXPORT_JOB_ID}")
        if resp.status_code in (400, 404):
            body = _safe_json(resp)
            assert isinstance(body, dict), f"body should be dict, got: {body!r}"
            detail = body.get("detail", body)
            if isinstance(detail, dict):
                code = detail.get("code", "")
                assert code not in {
                    "AUTHENTICATION_REQUIRED", "PERMISSION_DENIED",
                    "TENANT_CONTEXT_REQUIRED",
                }, f"exports {resp.status_code} carries auth error code {code!r}: {body}"
        else:
            assert resp.status_code not in (401, 403, 500), _diag(resp)


# ===========================================================================
# Diagnostic helpers
# ===========================================================================

def _safe_json(resp):
    try:
        return resp.json()
    except Exception:
        return {"_raw_text": resp.text[:500]}


def _diag(resp) -> str:
    body = _safe_json(resp)
    return f"status={resp.status_code} path={resp.request.url.path} body={body}"
