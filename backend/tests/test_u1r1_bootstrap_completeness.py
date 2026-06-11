"""
U1-R1 — Comprehensive Tenant Bootstrap Completeness Tests.

Validates:
1. Table Completeness — bootstrap creates ALL MVP business tables
2. Permission Completeness — admin role has every API-enforced permission
3. Bootstrap Idempotency — running bootstrap twice is error-free
4. Sidebar API Smoke — sidebar endpoints return 200 (not 403/500) on empty tenant
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest
import pytest_asyncio
from sqlalchemy import text

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TEST_U1R1_SCHEMA = "t_u1r1_test"
TEST_U1R1_TENANT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
TEST_U1R1_USER_ID = "11111111-1111-1111-1111-111111111111"
TEST_U1R1_ADMIN_EMAIL = "admin@u1r1.test"
TEST_U1R1_ADMIN_PASSWORD = "testpassword"

# All MVP tables expected in a fully bootstrapped tenant schema.
# Does NOT include retailers — that's in the public schema.
EXPECTED_MVP_TABLES = {
    "users",
    "roles",
    "permissions",
    "user_roles",
    "role_permissions",
    "skus",
    "inventory_stocks",
    "inventory_movements",
    "orders",
    "order_items",
    "payments",
    "ledger_entries",
    "retailer_prices",
}

# Complete 36-permission set (mirrors seed_test_tenant.py)
U1R1_PERMISSION_CODES: list[tuple[str, str]] = [
    # ── User management ──
    ("users:read", "Read users"),
    ("users:create", "Create users"),
    ("users:update", "Update users"),
    ("users:deactivate", "Deactivate users"),
    # ── Wholesaler ──
    ("wholesalers:read", "Read wholesalers"),
    ("wholesalers:write", "Create/update/delete wholesalers"),
    # ── Role management ──
    ("roles:read", "Read roles"),
    ("roles:create", "Create roles"),
    ("roles:update", "Update roles"),
    ("roles:delete", "Delete roles"),
    ("roles:assign", "Assign roles to users"),
    # ── Order management ──
    ("orders:read", "Read orders"),
    ("orders:create", "Create orders"),
    ("orders:update", "Update orders"),
    ("orders:confirm", "Confirm orders"),
    ("orders:ship", "Ship orders"),
    ("orders:cancel", "Cancel orders"),
    # ── SKU / Product management ──
    ("skus:read", "Read SKUs"),
    ("skus:create", "Create SKUs"),
    ("skus:update", "Update SKUs"),
    # ── Inventory management ──
    ("inventory:read", "Read inventory"),
    ("inventory:write", "Write inventory (legacy alias)"),
    ("inventory:update", "Update inventory (adjustments)"),
    # ── Payment management ──
    ("payments:read", "Read payments"),
    ("payments:create", "Create payments"),
    # ── Retailer management ──
    ("retailers:read", "Read retailers"),
    # ── Invitations ──
    ("invitations:create", "Create invitations"),
    # ── Pricing ──
    ("pricing:read", "Read pricing"),
    ("pricing:write", "Write pricing"),
    # ── Finance ──
    ("finance:read", "View invoices, receivables, financial summary"),
    # ── Dashboards & Reports ──
    ("dashboards:read", "View dashboard KPIs and charts"),
    ("reports:read", "Read reports"),
    ("reports:analyze", "Analyze reports"),
    # ── Exports ──
    ("exports:create", "Request data exports"),
    # ── System ──
    ("system:admin", "Full system administration (job queues, debug endpoints)"),
    ("metrics:admin", "Reset application metrics"),
]


# ---------------------------------------------------------------------------
# Session-scoped fixture: bootstrap tenant ONCE for all U1-R1 tests
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(scope="session")
async def _u1r1_bootstrap():
    """Bootstrap t_u1r1_test schema + seed admin user (session-scoped).

    Runs once for the entire test session.  All U1-R1 tests depend on this.
    """
    from scripts.bootstrap_tenant_schema import bootstrap as bootstrap_schema
    from scripts.seed_test_tenant import _seed_admin_rbac
    from core.config import get_settings
    from database.session import AsyncSessionLocal

    settings = get_settings()

    # 1. Bootstrap full schema (all 13+ tables, enums, indexes, triggers)
    await bootstrap_schema(TEST_U1R1_SCHEMA, settings.DATABASE_URL)

    # 2. Seed admin user with complete permission set
    async with AsyncSessionLocal() as db:
        await _seed_admin_rbac(
            db,
            tenant_schema=TEST_U1R1_SCHEMA,
            admin_email=TEST_U1R1_ADMIN_EMAIL,
            admin_password=TEST_U1R1_ADMIN_PASSWORD,
            admin_full_name="U1R1 Test Admin",
            permission_codes=U1R1_PERMISSION_CODES,
        )
        await db.commit()


# ---------------------------------------------------------------------------
# Test 1: Table Completeness
# ---------------------------------------------------------------------------

class TestTableCompleteness:
    """Verify bootstrap creates ALL MVP business tables."""

    @pytest.mark.asyncio
    async def test_all_mvp_tables_exist(self, _u1r1_bootstrap):
        """Every expected MVP table must exist in the tenant schema."""
        from database.session import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = :schema"
                ),
                {"schema": TEST_U1R1_SCHEMA},
            )
            existing = {row[0] for row in result.fetchall()}

        missing = EXPECTED_MVP_TABLES - existing
        assert not missing, (
            f"Missing {len(missing)} MVP table(s): {sorted(missing)}"
        )

        assert len(existing) >= len(EXPECTED_MVP_TABLES), (
            f"Expected at least {len(EXPECTED_MVP_TABLES)} tables, "
            f"found {len(existing)}: {sorted(existing)}"
        )

    @pytest.mark.asyncio
    async def test_retailers_in_public_not_tenant(self, _u1r1_bootstrap):
        """retailers table must be in public schema, NOT tenant schema."""
        from database.session import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            # Tenant schema must NOT have retailers
            tenant_result = await db.execute(
                text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = :schema AND table_name = 'retailers'"
                ),
                {"schema": TEST_U1R1_SCHEMA},
            )
            assert tenant_result.first() is None, (
                "retailers must NOT exist in tenant schema"
            )

            # Public schema must have retailers
            public_result = await db.execute(
                text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = 'retailers'"
                ),
            )
            assert public_result.first() is not None, (
                "retailers must exist in public schema"
            )


# ---------------------------------------------------------------------------
# Test 2: Permission Completeness
# ---------------------------------------------------------------------------

class TestAdminPermissionCompleteness:
    """Verify admin role has every API-enforced permission."""

    @pytest.mark.asyncio
    async def test_admin_has_all_desired_permissions(self, _u1r1_bootstrap):
        """All 36 permissions from U1R1_PERMISSION_CODES must be assigned
        to the admin role via role_permissions."""
        from database.session import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            await db.execute(
                text(f'SET LOCAL search_path TO "{TEST_U1R1_SCHEMA}", public')
            )

            role_result = await db.execute(
                text("SELECT id FROM roles WHERE name = 'admin'")
            )
            role_id = role_result.scalar()
            assert role_id is not None, "admin role must exist"

            perm_result = await db.execute(
                text(
                    "SELECT p.code FROM permissions p "
                    "JOIN role_permissions rp ON p.id = rp.permission_id "
                    "WHERE rp.role_id = :role_id"
                ),
                {"role_id": role_id},
            )
            assigned_codes = {row[0] for row in perm_result.fetchall()}

        expected_codes = {code for code, _desc in U1R1_PERMISSION_CODES}
        missing = expected_codes - assigned_codes
        assert not missing, (
            f"Admin role missing {len(missing)} permission(s): {sorted(missing)}"
        )

        extra = assigned_codes - expected_codes
        assert not extra, (
            f"Admin role has {len(extra)} unexpected permission(s): {sorted(extra)}"
        )

    @pytest.mark.asyncio
    async def test_admin_user_has_admin_role(self, _u1r1_bootstrap):
        """Admin user must be assigned the admin role."""
        from database.session import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            await db.execute(
                text(f'SET LOCAL search_path TO "{TEST_U1R1_SCHEMA}", public')
            )

            result = await db.execute(
                text(
                    "SELECT 1 FROM user_roles ur "
                    "JOIN users u ON ur.user_id = u.id "
                    "JOIN roles r ON ur.role_id = r.id "
                    "WHERE u.email = :email AND r.name = 'admin'"
                ),
                {"email": TEST_U1R1_ADMIN_EMAIL},
            )
            assert result.first() is not None, (
                f"Admin user {TEST_U1R1_ADMIN_EMAIL} must have admin role"
            )


# ---------------------------------------------------------------------------
# Test 3: Bootstrap Idempotency
# ---------------------------------------------------------------------------

class TestBootstrapIdempotency:
    """Verify running bootstrap twice is safe."""

    @pytest.mark.asyncio
    async def test_double_bootstrap_does_not_error(self, _u1r1_bootstrap):
        """Running bootstrap twice must not raise exceptions."""
        from scripts.bootstrap_tenant_schema import bootstrap as bootstrap_schema
        from core.config import get_settings

        settings = get_settings()
        await bootstrap_schema(TEST_U1R1_SCHEMA, settings.DATABASE_URL)

    @pytest.mark.asyncio
    async def test_table_count_unchanged_after_double_bootstrap(self, _u1r1_bootstrap):
        """Running bootstrap twice must not change the number of tables."""
        from scripts.bootstrap_tenant_schema import bootstrap as bootstrap_schema
        from core.config import get_settings
        from database.session import AsyncSessionLocal

        # Count tables before second bootstrap
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_schema = :schema"
                ),
                {"schema": TEST_U1R1_SCHEMA},
            )
            count_before = result.scalar()

        # Run bootstrap again
        settings = get_settings()
        await bootstrap_schema(TEST_U1R1_SCHEMA, settings.DATABASE_URL)

        # Count after
        async with AsyncSessionLocal() as db2:
            result2 = await db2.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_schema = :schema"
                ),
                {"schema": TEST_U1R1_SCHEMA},
            )
            count_after = result2.scalar()

        assert count_after == count_before, (
            f"Table count changed after second bootstrap: "
            f"{count_before} → {count_after}"
        )


# ---------------------------------------------------------------------------
# Test 4: Sidebar API Smoke
# ---------------------------------------------------------------------------

_SIDEBAR_ENDPOINTS = [
    # (HTTP method, path, description)
    ("GET", "/api/v1/orders", "Orders"),
    ("GET", "/api/v1/skus", "Products/SKUs"),
    ("GET", "/api/v1/inventory/stocks", "Stock"),
    ("GET", "/api/v1/dashboards/kpi/summary", "Dashboard"),
    ("GET", "/api/v1/payments", "Payments"),
    ("GET", "/api/v1/retailers", "Customers"),
    ("GET", "/api/v1/pricing/prices", "Pricing"),
]


@dataclass
class _U1R1FakeToken:
    """Fake token payload for super-admin API smoke tests."""
    user_id: str = TEST_U1R1_USER_ID
    tenant_id: str = TEST_U1R1_TENANT_ID
    tenant_schema: str = TEST_U1R1_SCHEMA
    type: str = "access"

    @property
    def is_identity_only(self) -> bool:
        return False

    @property
    def is_super_admin(self) -> bool:
        return True


class _U1R1FakeAuthContext:
    """Fake auth context with super-admin token."""
    def __init__(self):
        self.token = _U1R1FakeToken()


class _U1R1MockUser:
    """Minimal user object for TenantContext — permissions are bypassed
    because is_super_admin=True in RequirePermission."""
    def __init__(self):
        self.id = uuid.UUID(TEST_U1R1_USER_ID)
        self.email = TEST_U1R1_ADMIN_EMAIL
        self.full_name = "U1R1 Test Admin"
        self.is_active = True
        self.roles = []


class TestSidebarApiSmoke:
    """Verify all sidebar API endpoints return 200 (not 403/500) on empty tenant.

    Uses monkeypatched auth context with super_admin token to bypass
    permission checks, with a real DB session against the bootstrapped
    test tenant.
    """

    @pytest.fixture(autouse=True)
    def _require_u1r1_bootstrap(self, _u1r1_bootstrap):
        """Ensure tenant is bootstrapped before any test runs."""
        pass

    @pytest.mark.asyncio
    @pytest.mark.parametrize("method,path,label", _SIDEBAR_ENDPOINTS)
    async def test_sidebar_endpoint_returns_200(
        self, method, path, label
    ):
        """Each sidebar endpoint must return HTTP 200 on an empty tenant.
        Must NOT return 403 (permission denied) or 500 (server error)."""
        pytest.importorskip("httpx", reason="httpx required for TestClient")

        from fastapi.testclient import TestClient
        from main import app
        from api.middleware import rbac as rbac_module
        from api.dependencies import get_tenant_db_session, get_current_user_context
        from api.context.tenant import TenantContext
        from database.session import AsyncSessionLocal

        # ---- Build a real session with correct search_path ----
        session = AsyncSessionLocal()
        await session.execute(
            text(f'SET LOCAL search_path TO "{TEST_U1R1_SCHEMA}", public')
        )
        session.info["tenant_schema"] = TEST_U1R1_SCHEMA
        session.info["tenant_id"] = TEST_U1R1_TENANT_ID

        # ---- Monkeypatch auth context ----
        fake_auth_ctx = _U1R1FakeAuthContext()
        mock_user = _U1R1MockUser()
        tenant_ctx = TenantContext(
            tenant_id=TEST_U1R1_TENANT_ID,
            tenant_schema=TEST_U1R1_SCHEMA,
            session=session,
            user=mock_user,
        )

        def _fake_auth_context(request):
            return fake_auth_ctx

        def _fake_tenant_context(request):
            return tenant_ctx

        def _session_override(request):
            return session

        def _token_override(request):
            return _U1R1FakeToken()

        # ---- Apply patches ----
        orig_auth = rbac_module.get_auth_context
        orig_tenant = rbac_module.get_tenant_context
        rbac_module.get_auth_context = _fake_auth_context
        rbac_module.get_tenant_context = _fake_tenant_context

        app.dependency_overrides[get_tenant_db_session] = _session_override
        app.dependency_overrides[get_current_user_context] = _token_override

        client = TestClient(app, raise_server_exceptions=False)

        try:
            if method == "GET":
                response = client.get(path)
            elif method == "POST":
                response = client.post(path, json={})
            else:
                response = client.request(method, path)

            assert response.status_code == 200, (
                f"{label} ({method} {path}) returned {response.status_code}, "
                f"expected 200. Body: {response.text[:500]}"
            )

            # Verify response is valid JSON with success=true
            body = response.json()
            assert body.get("success") is True, (
                f"{label} response missing success=true: {body}"
            )

        finally:
            # Clean up patches
            rbac_module.get_auth_context = orig_auth
            rbac_module.get_tenant_context = orig_tenant
            app.dependency_overrides.pop(get_tenant_db_session, None)
            app.dependency_overrides.pop(get_current_user_context, None)

            # Clean up real session
            await session.close()
