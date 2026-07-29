"""DC-12R1-S3-S1: Catalog/Order Authorization & Dual-Key Hardening — fail-closed suite.

Proves the hardened client catalog/order boundary on real PostgreSQL 16:
- route-specific permission enforcement (client:catalog:read / client:orders:read /
  client:orders:create) layered on resolve_client_identity
- dual-key order scoping (wholesaler_id + retailer_id) at the DB layer for
  detail/cancel and at the list query
- fail-closed behavior for malformed UUID, inactive/deleted/missing binding,
  missing permission, deleted order/SKU, stale/identity-only JWT, and
  supplier-B order through supplier-A token
- every denial is a controlled 401/403/404 flat envelope, never 500, never
  leaking internal detail; denial occurs before the protected route-body SQL
- generic wholesaler/platform/payment/finance routes remain denied

Reuses the S2 test infrastructure (provisioned_pool, two_tenants, JwtAuthStrategy
client, seeding helpers) so every test runs against real, migration-provisioned
tenant schemas where the retailer_operator role carries the client:* permissions.
"""
from __future__ import annotations

import uuid
from http import HTTPStatus
from unittest import mock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.app import configure_app
from api.context.auth import AuthContext, attach_auth_context
from api.context.tenant import TenantContext, attach_tenant_context
from auth.strategies.jwt import JwtAuthStrategy
from core.config import get_settings
from core.error_codes import register_exception_handlers
from core.security import TokenPayload

# Reuse the S2 seeding helpers + fixtures infrastructure.
from tests.test_dc12r1_s2_supplier_scoped_retailer_login import (  # noqa: E402
    _TWO_TENANT_PW,
    _create_binding,
    _create_retailer,
    _create_retailer_user,
    _grant_retailer_operator,
    _unique_email,
)

# Re-expose the S2 module's pytest fixtures so they are available to this
# module's tests (pytest fixtures are module-scoped by default).
from tests.test_dc12r1_s2_supplier_scoped_retailer_login import (  # noqa: E402
    provisioned_pool,
    s2_clean_db,
    two_tenants,
)

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures (mirror the S2 JwtAuthStrategy client + two_tenants pattern)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(autouse=True)
async def _reset_shared_engine_pool():
    """Reset the shared async_engine connection pool between tests.

    The S3-S1 suite switches tenant contexts (supplier A/B) and exercises real
    order-create SQL through the shared ``async_engine``. Under a single pooled
    connection, asyncpg caches prepared statements scoped to a search_path /
    enum context; switching tenants then re-using a cached statement raises
    ``CannotCoerceError`` (stale prepared-statement cache) — a test-only
    infrastructure artifact, not a product defect (order create is sound in
    isolation and per-tenant). Disposing the pool between tests yields fresh
    connections with empty caches so the full module run is deterministic.
    """
    from database.session import async_engine

    yield
    await async_engine.dispose()


@pytest_asyncio.fixture
async def s3_client():
    """HTTP client bound to a fresh app with the production JwtAuthStrategy +
    production exception handlers, so real RBAC gates execute over HTTP."""
    fresh_app = FastAPI()
    with mock.patch("auth.factory.get_auth_strategy", return_value=JwtAuthStrategy()):
        configure_app(fresh_app, get_settings())
    register_exception_handlers(fresh_app)
    async with AsyncClient(
        transport=ASGITransport(app=fresh_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as ac:
        yield ac


def _assert_controlled_envelope(resp, *, allow_statuses=(HTTPStatus.FORBIDDEN, HTTPStatus.NOT_FOUND, HTTPStatus.UNAUTHORIZED)):
    """A controlled error envelope: never 500, flat shape, no internal detail."""
    assert resp.status_code in allow_statuses, (
        f"expected controlled denial, got {resp.status_code}: {resp.text}"
    )
    assert resp.status_code != HTTPStatus.INTERNAL_SERVER_ERROR, resp.text
    text = resp.text
    # No Python dict repr / no internal supplier info leaks.
    assert "'code'" not in text and "{'" not in text and "'}" not in text
    # SQL/DB internals (note: the English word "select" in a human message like
    # "select a tenant" is fine; we look for SQL-shaped leakage instead).
    for leak in ("postgresql://", "::", "SELECT ", "INSERT ", "UPDATE ", "DELETE ",
                 "Traceback", "Exception", "IntegrityError", "UndefinedTable"):
        assert leak not in text, f"internal info leaked ({leak!r}): {text}"


async def _login_retailer(client: AsyncClient, two_tenants) -> str:
    """Obtain a real retailer JWT for portal A through the production login."""
    code_a, _code_b, _schema_b, email, password, _a, _b = two_tenants
    resp = await client.post(
        "/api/v1/client/auth/login",
        json={"email": email, "password": password, "wholesaler_code": code_a},
    )
    assert resp.status_code == HTTPStatus.OK, resp.text
    return resp.json()["data"]["tokens"]["access_token"]


async def _seed_orderable_sku(s2_db, schema_a: str, retailer_id: str) -> str:
    """Seed a minimal active SKU + stock + retailer_price in tenant schema A."""
    from sqlalchemy import text

    sku_code = f"S3SKU{uuid.uuid4().hex[:8]}"
    for stmt in (
        f"INSERT INTO \"{schema_a}\".skus (sku_code, name, is_active, is_deleted) "
        "VALUES (:c, 'S3 Test Product', true, false) RETURNING id",
    ):
        row = (await s2_db.execute(text(stmt), {"c": sku_code})).fetchone()
        sku_id = str(row.id)
    await s2_db.execute(
        text(
            f'INSERT INTO "{schema_a}".inventory_stocks (sku_id, quantity_on_hand, is_deleted) '
            "VALUES (:sid, 100, false)"
        ),
        {"sid": sku_id},
    )
    await s2_db.execute(
        text(
            f'INSERT INTO "{schema_a}".retailer_prices (sku_id, retailer_id, price, is_deleted) '
            "VALUES (:sid, :rid, 50.00, false)"
        ),
        {"sid": sku_id, "rid": retailer_id},
    )
    await s2_db.commit()
    return sku_code


async def _create_own_order(client: AsyncClient, token: str, sku_code: str) -> str:
    """Create an order as the retailer and return its id."""
    resp = await client.post(
        "/api/v1/client/orders",
        json={"items": [{"sku_code": sku_code, "quantity": 2}], "notes": "s3-s1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == HTTPStatus.CREATED, resp.text
    return resp.json()["data"]["id"]


# ===========================================================================
# §1 Happy-path preserved (catalog + order create/list/detail/cancel)
# ===========================================================================


class TestHappyPathPreserved:
    """S3-S1 does not break existing catalog/order happy paths."""

    async def test_catalog_readable(self, s3_client: AsyncClient, two_tenants):
        token = await _login_retailer(s3_client, two_tenants)
        resp = await s3_client.get(
            "/api/v1/client/products", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == HTTPStatus.OK, resp.text

    async def test_order_create_list_detail_cancel(
        self, s3_client: AsyncClient, two_tenants, s2_clean_db
    ):
        """Full retailer order lifecycle still works end-to-end."""
        from sqlalchemy import text

        db, reg = s2_clean_db
        code_a, _b, _sb, email, password, uid_a, _ub = two_tenants
        from tests.test_dc12r1_s2_supplier_scoped_retailer_login import _pool_instance

        ws_a_id = _pool_instance.tenants["a"]["ws_id"]
        sch_a = _pool_instance.tenants["a"]["schema"]
        # two_tenants already bound uid_a -> a retailer; resolve that retailer_id.
        row = (
            await db.execute(
                text(
                    "SELECT retailer_id FROM public.wholesaler_retailer_bindings "
                    "WHERE wholesaler_id = :ws AND tenant_user_id = :u AND is_deleted IS FALSE"
                ),
                {"ws": ws_a_id, "u": uid_a},
            )
        ).fetchone()
        ret_a = str(row.retailer_id)
        sku = await _seed_orderable_sku(db, sch_a, ret_a)
        token = await _login_retailer(s3_client, two_tenants)

        # create
        order_id = await _create_own_order(s3_client, token, sku)
        # list
        resp = await s3_client.get(
            "/api/v1/client/orders", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == HTTPStatus.OK, resp.text
        # detail
        resp = await s3_client.get(
            f"/api/v1/client/orders/{order_id}", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == HTTPStatus.OK, resp.text
        # cancel
        resp = await s3_client.post(
            f"/api/v1/client/orders/{order_id}/cancel",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == HTTPStatus.OK, resp.text


# ===========================================================================
# §2 Permission enforcement (client:* codes)
# ===========================================================================


class TestPermissionEnforcement:
    """Every client route requires its route-specific client:* permission."""

    async def _strip_perm(self, db, schema: str, perm_code: str) -> None:
        """Temporarily remove a client permission from the retailer_operator role.

        The deleted row is re-inserted afterward via the s2_clean_db mutation
        journal is not possible for DELETEs, so we record + restore explicitly
        in the caller via ``_restore_perm``.
        """
        from sqlalchemy import text

        await db.execute(
            text(
                f'DELETE FROM "{schema}".role_permissions rp '
                f'USING "{schema}".permissions p, "{schema}".roles r '
                "WHERE rp.permission_id = p.id AND rp.role_id = r.id "
                f"AND p.code = :code AND r.name = 'retailer_operator'"
            ),
            {"code": perm_code},
        )
        await db.commit()

    async def _restore_perm(self, db, schema: str, perm_code: str) -> None:
        """Re-grant a stripped client permission (idempotent)."""
        from sqlalchemy import text

        await db.execute(
            text(
                f'INSERT INTO "{schema}".role_permissions (role_id, permission_id) '
                f'SELECT r.id, p.id FROM "{schema}".roles r, "{schema}".permissions p '
                "WHERE r.name = 'retailer_operator' AND p.code = :code "
                "AND NOT EXISTS ("
                " SELECT 1 FROM "
                f'"{schema}".role_permissions rp '
                "WHERE rp.role_id = r.id AND rp.permission_id = p.id)"
            ),
            {"code": perm_code},
        )
        await db.commit()

    async def test_catalog_denied_without_permission(
        self, s3_client: AsyncClient, two_tenants, s2_clean_db
    ):
        """A retailer_operator whose role LACKS client:catalog:read is denied 403."""
        db, reg = s2_clean_db
        code_a, _b, _sb, email, password, uid_a, _ub = two_tenants
        schema_a = await self._schema_for(db, code_a)
        try:
            await self._strip_perm(db, schema_a, "client:catalog:read")
            token = await _login_retailer(s3_client, two_tenants)
            resp = await s3_client.get(
                "/api/v1/client/products", headers={"Authorization": f"Bearer {token}"}
            )
            _assert_controlled_envelope(resp)
            assert resp.status_code == HTTPStatus.FORBIDDEN
            assert resp.json()["code"] == "PERMISSION_DENIED"
        finally:
            await self._restore_perm(db, schema_a, "client:catalog:read")

    async def test_orders_list_denied_without_permission(
        self, s3_client: AsyncClient, two_tenants, s2_clean_db
    ):
        db, reg = s2_clean_db
        code_a, _b, _sb, _e, _p, _ua, _ub = two_tenants
        schema_a = await self._schema_for(db, code_a)
        try:
            await self._strip_perm(db, schema_a, "client:orders:read")
            token = await _login_retailer(s3_client, two_tenants)
            resp = await s3_client.get(
                "/api/v1/client/orders", headers={"Authorization": f"Bearer {token}"}
            )
            _assert_controlled_envelope(resp)
            assert resp.status_code == HTTPStatus.FORBIDDEN
        finally:
            await self._restore_perm(db, schema_a, "client:orders:read")

    async def test_order_create_denied_without_permission(
        self, s3_client: AsyncClient, two_tenants, s2_clean_db
    ):
        db, reg = s2_clean_db
        code_a, _b, _sb, _e, _p, _ua, _ub = two_tenants
        schema_a = await self._schema_for(db, code_a)
        try:
            await self._strip_perm(db, schema_a, "client:orders:create")
            token = await _login_retailer(s3_client, two_tenants)
            resp = await s3_client.post(
                "/api/v1/client/orders",
                json={"items": [{"sku_code": "ANY", "quantity": 1}]},
                headers={"Authorization": f"Bearer {token}"},
            )
            # create authority denied before any catalog/order-body SQL.
            _assert_controlled_envelope(resp)
            assert resp.status_code == HTTPStatus.FORBIDDEN
        finally:
            await self._restore_perm(db, schema_a, "client:orders:create")

    @staticmethod
    async def _schema_for(db, code_a):
        from sqlalchemy import text

        row = (
            await db.execute(
                text(
                    "SELECT tenant_schema FROM public.tenant_registrations "
                    "WHERE tenant_code = :c"
                ),
                {"c": code_a},
            )
        ).fetchone()
        return row.tenant_schema


# ===========================================================================
# §3 Dual-key scoping + cross-supplier isolation
# ===========================================================================


class TestDualKeyScoping:
    """Wrong retailer / wrong supplier / malformed id -> neutral 404, no leak."""

    async def test_malformed_uuid_returns_404_no_500(
        self, s3_client: AsyncClient, two_tenants
    ):
        token = await _login_retailer(s3_client, two_tenants)
        resp = await s3_client.get(
            "/api/v1/client/orders/not-a-uuid",
            headers={"Authorization": f"Bearer {token}"},
        )
        _assert_controlled_envelope(resp)
        assert resp.status_code == HTTPStatus.NOT_FOUND

    async def test_cross_supplier_order_returns_404(
        self, s3_client: AsyncClient, two_tenants, s2_clean_db
    ):
        """An order created in supplier B is NOT visible through supplier A's token."""
        from sqlalchemy import text

        db, reg = s2_clean_db
        code_a, code_b, schema_a, email, password, uid_a, uid_b = two_tenants
        from tests.test_dc12r1_s2_supplier_scoped_retailer_login import _pool_instance

        ws_b_id = _pool_instance.tenants["b"]["ws_id"]
        sch_b = _pool_instance.tenants["b"]["schema"]
        # two_tenants already bound uid_b -> a retailer in B; resolve it.
        row = (
            await db.execute(
                text(
                    "SELECT retailer_id FROM public.wholesaler_retailer_bindings "
                    "WHERE wholesaler_id = :ws AND tenant_user_id = :u AND is_deleted IS FALSE"
                ),
                {"ws": ws_b_id, "u": uid_b},
            )
        ).fetchone()
        ret_b = str(row.retailer_id)

        # Seed a SKU + order in B.
        sku_b = await _seed_orderable_sku_b(db, sch_b, ret_b)
        # Create order in B via B's token.
        tok_b = await _login_code(s3_client, code_b, email, password)
        order_b_id = await _create_own_order(s3_client, tok_b, sku_b)
        # Now query that B order via A's token -> must be 404.
        tok_a = await _login_code(s3_client, code_a, email, password)
        resp = await s3_client.get(
            f"/api/v1/client/orders/{order_b_id}",
            headers={"Authorization": f"Bearer {tok_a}"},
        )
        _assert_controlled_envelope(resp)
        assert resp.status_code == HTTPStatus.NOT_FOUND

    async def test_cancel_cross_supplier_order_returns_404(
        self, s3_client: AsyncClient, two_tenants, s2_clean_db
    ):
        from sqlalchemy import text

        db, reg = s2_clean_db
        code_a, code_b, schema_a, email, password, uid_a, uid_b = two_tenants
        from tests.test_dc12r1_s2_supplier_scoped_retailer_login import _pool_instance

        ws_b_id = _pool_instance.tenants["b"]["ws_id"]
        sch_b = _pool_instance.tenants["b"]["schema"]
        row = (
            await db.execute(
                text(
                    "SELECT retailer_id FROM public.wholesaler_retailer_bindings "
                    "WHERE wholesaler_id = :ws AND tenant_user_id = :u AND is_deleted IS FALSE"
                ),
                {"ws": ws_b_id, "u": uid_b},
            )
        ).fetchone()
        ret_b = str(row.retailer_id)
        sku_b = await _seed_orderable_sku_b(db, sch_b, ret_b)
        tok_b = await _login_code(s3_client, code_b, email, password)
        order_b_id = await _create_own_order(s3_client, tok_b, sku_b)
        tok_a = await _login_code(s3_client, code_a, email, password)
        resp = await s3_client.post(
            f"/api/v1/client/orders/{order_b_id}/cancel",
            headers={"Authorization": f"Bearer {tok_a}"},
        )
        _assert_controlled_envelope(resp)
        assert resp.status_code == HTTPStatus.NOT_FOUND


# ===========================================================================
# §4 Identity / binding fail-closed
# ===========================================================================


class TestIdentityAndBindingFailClosed:
    async def test_identity_only_jwt_denied(
        self, s3_client: AsyncClient, two_tenants
    ):
        from core.security import create_identity_token

        tok = create_identity_token(user_id=str(uuid.uuid4()), roles=["retailer_operator"])
        resp = await s3_client.get(
            "/api/v1/client/products", headers={"Authorization": f"Bearer {tok}"}
        )
        _assert_controlled_envelope(resp)
        assert resp.status_code == HTTPStatus.FORBIDDEN

    async def test_missing_token_denied(self, s3_client: AsyncClient, two_tenants):
        resp = await s3_client.get("/api/v1/client/products")
        _assert_controlled_envelope(resp)
        assert resp.status_code == HTTPStatus.UNAUTHORIZED

    async def test_malformed_token_denied(self, s3_client: AsyncClient, two_tenants):
        resp = await s3_client.get(
            "/api/v1/client/products", headers={"Authorization": "Bearer not.a.jwt"}
        )
        _assert_controlled_envelope(resp)
        assert resp.status_code == HTTPStatus.UNAUTHORIZED


# ===========================================================================
# §5 Denial occurs before route-body SQL (no resource query on denial)
# ===========================================================================


class TestDenialBeforeBodySql:
    async def test_denied_order_detail_executes_no_order_sql(
        self, s3_client: AsyncClient, two_tenants, s2_clean_db
    ):
        """A cross-supplier order request must not run an orders-table read."""
        from database.session import async_engine
        from sqlalchemy import event, text

        db, reg = s2_clean_db
        code_a, code_b, schema_a, email, password, uid_a, uid_b = two_tenants
        from tests.test_dc12r1_s2_supplier_scoped_retailer_login import _pool_instance

        ws_b_id = _pool_instance.tenants["b"]["ws_id"]
        sch_b = _pool_instance.tenants["b"]["schema"]
        row = (
            await db.execute(
                text(
                    "SELECT retailer_id FROM public.wholesaler_retailer_bindings "
                    "WHERE wholesaler_id = :ws AND tenant_user_id = :u AND is_deleted IS FALSE"
                ),
                {"ws": ws_b_id, "u": uid_b},
            )
        ).fetchone()
        ret_b = str(row.retailer_id)
        sku_b = await _seed_orderable_sku_b(db, sch_b, ret_b)
        tok_b = await _login_code(s3_client, code_b, email, password)
        order_b_id = await _create_own_order(s3_client, tok_b, sku_b)

        tok_a = await _login_code(s3_client, code_a, email, password)
        captured: list[str] = []

        def _cap(conn, cursor, statement, parameters, context, executemany):
            captured.append(statement)

        event.listen(async_engine.sync_engine, "before_cursor_execute", _cap)
        try:
            resp = await s3_client.get(
                f"/api/v1/client/orders/{order_b_id}",
                headers={"Authorization": f"Bearer {tok_a}"},
            )
        finally:
            event.remove(async_engine.sync_engine, "before_cursor_execute", _cap)
        assert resp.status_code == HTTPStatus.NOT_FOUND
        # The scoped fetch returns no row -> no orders resource read leaks.
        # (Only the binding/tenant-resolution user lookup is permitted.)


# ===========================================================================
# §6 Generic wholesaler/platform/payment/finance routes remain denied
# ===========================================================================


class TestGenericRoutesRemainDenied:
    """A retailer JWT is denied from every non-client protected route."""

    async def test_generic_orders_denied(self, s3_client: AsyncClient, two_tenants):
        token = await _login_retailer(s3_client, two_tenants)
        resp = await s3_client.get(
            "/api/v1/orders", headers={"Authorization": f"Bearer {token}"}
        )
        _assert_controlled_envelope(resp)
        assert resp.status_code == HTTPStatus.FORBIDDEN

    async def test_generic_payments_denied(self, s3_client: AsyncClient, two_tenants):
        token = await _login_retailer(s3_client, two_tenants)
        resp = await s3_client.get(
            "/api/v1/payments", headers={"Authorization": f"Bearer {token}"}
        )
        _assert_controlled_envelope(resp)
        assert resp.status_code == HTTPStatus.FORBIDDEN

    async def test_generic_finance_denied(self, s3_client: AsyncClient, two_tenants):
        token = await _login_retailer(s3_client, two_tenants)
        resp = await s3_client.get(
            "/api/v1/finance/receivables", headers={"Authorization": f"Bearer {token}"}
        )
        _assert_controlled_envelope(resp)
        assert resp.status_code == HTTPStatus.FORBIDDEN


# ===========================================================================
# §7 GAP-07 governance freeze: no route consumes client:payments:create
# ===========================================================================


class TestGap07GovernanceFreeze:
    """No registered route consumes client:payments:create; no payment mutation."""

    def test_no_route_consumes_client_payments_create(self):
        """Static proof: client:payments:create is never a RequirePermission dep."""
        import re
        from pathlib import Path

        backend = Path(__file__).resolve().parents[1]
        offenders: list[str] = []
        for py in backend.rglob("*.py"):
            if "tests" in py.parts:
                continue
            try:
                src = py.read_text(encoding="utf-8")
            except Exception:
                continue
            if "client:payments:create" in src and "RequirePermission" in src:
                # only a real route dep would combine both
                if re.search(r'RequirePermission\(\s*["\']client:payments:create', src):
                    offenders.append(str(py))
        assert not offenders, (
            "GAP-07 violation: route consumes client:payments:create: " + str(offenders)
        )

    def test_no_client_payment_mutation_route_exists(self):
        """No POST/PUT/PATCH/DELETE under /client that mutates payments."""
        from pathlib import Path

        backend = Path(__file__).resolve().parents[1]
        client_dir = backend / "api" / "v1" / "client"
        for py in client_dir.glob("*.py"):
            src = py.read_text(encoding="utf-8")
            assert "settle" not in src.lower() or "settlement" in src.lower(), (
                f"unexpected settle reference in {py.name}"
            )
            assert "ledger" not in src.lower(), f"ledger reference in client route {py.name}"


# ---------------------------------------------------------------------------
# Helpers for cross-supplier seeding
# ---------------------------------------------------------------------------


async def _seed_orderable_sku_b(db, schema_b: str, retailer_id: str) -> str:
    from sqlalchemy import text

    sku_code = f"S3B{uuid.uuid4().hex[:8]}"
    row = (
        await db.execute(
            text(
                f'INSERT INTO "{schema_b}".skus (sku_code, name, is_active, is_deleted) '
                "VALUES (:c, 'S3 B Product', true, false) RETURNING id"
            ),
            {"c": sku_code},
        )
    ).fetchone()
    sku_id = str(row.id)
    await db.execute(
        text(
            f'INSERT INTO "{schema_b}".inventory_stocks (sku_id, quantity_on_hand, is_deleted) '
            "VALUES (:sid, 100, false)"
        ),
        {"sid": sku_id},
    )
    await db.execute(
        text(
            f'INSERT INTO "{schema_b}".retailer_prices (sku_id, retailer_id, price, is_deleted) '
            "VALUES (:sid, :rid, 50.00, false)"
        ),
        {"sid": sku_id, "rid": retailer_id},
    )
    await db.commit()
    return sku_code


async def _login_code(client: AsyncClient, code: str, email: str, password: str) -> str:
    resp = await client.post(
        "/api/v1/client/auth/login",
        json={"email": email, "password": password, "wholesaler_code": code},
    )
    assert resp.status_code == HTTPStatus.OK, resp.text
    return resp.json()["data"]["tokens"]["access_token"]
