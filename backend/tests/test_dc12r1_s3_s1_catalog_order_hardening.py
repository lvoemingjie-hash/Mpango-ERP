"""DC-12R1-S3-S1-R1: Catalog/Order Authorization & Dual-Key Hardening.

Proves the hardened retailer catalog/order boundary on real PostgreSQL 16:

- Route-specific permission enforcement (client:catalog:read / client:orders:read /
  client:orders:create) layered on resolve_client_identity.
- Dual-key order scoping at DB-query level (mandatory wholesaler_id + retailer_id);
  wrong-wholesaler and wrong-retailer rows in the same schema are excluded.
- Fail-closed: malformed UUID, inactive/deleted/missing binding, deleted order/SKU,
  stale/identity-only JWT, missing permission → controlled 401/403/404, never 500,
  no internal detail, denial before route-body SQL.
- GAP-07 governance freeze via registered FastAPI route/dependency inventory (not
  text scanning): no route consumes client:payments:create; no payment/ledger/
  receivable mutation.
- Provisioning PG-catalog assertion: admin gets only ADMIN_PERMISSIONS;
  retailer_operator gets exactly RETAILER_OPERATOR_PERMISSIONS.

Reuses the S2 test infrastructure (provisioned_pool, two_tenants, JwtAuthStrategy
client, seeding helpers).
"""
from __future__ import annotations

import uuid
from http import HTTPStatus
from typing import Any
from unittest import mock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient

from api.app import configure_app
from auth.strategies.jwt import JwtAuthStrategy
from core.config import get_settings
from core.error_codes import register_exception_handlers
from core.security import TokenPayload

# Reuse S2 helpers + fixtures.
from tests.test_dc12r1_s2_supplier_scoped_retailer_login import (  # noqa: E402
    _TWO_TENANT_PW,
    _create_binding,
    _create_retailer,
    _create_retailer_user,
    _grant_retailer_operator,
)
from tests.test_dc12r1_s2_supplier_scoped_retailer_login import (  # noqa: E402
    provisioned_pool,
    s2_clean_db,
    two_tenants,
)

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(autouse=True)
async def _reset_shared_engine_pool():
    """Dispose the shared async_engine between tests to avoid stale prepared
    statements when switching tenant contexts."""
    from database.session import async_engine
    yield
    await async_engine.dispose()


@pytest_asyncio.fixture
async def s3_client():
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _assert_controlled_envelope(resp, *, allow=(HTTPStatus.FORBIDDEN, HTTPStatus.NOT_FOUND, HTTPStatus.UNAUTHORIZED)):
    assert resp.status_code in allow, f"expected denial, got {resp.status_code}: {resp.text}"
    text = resp.text
    for marker in ("postgresql://", "'code'", "{'", "'}", "Traceback", "SELECT ", "INSERT "):
        assert marker not in text, f"leak ({marker!r}): {text}"


async def _login_retailer(client: AsyncClient, two_tenants) -> str:
    code_a, _b, _sb, email, password, _a, _b2 = two_tenants
    resp = await client.post(
        "/api/v1/client/auth/login",
        json={"email": email, "password": password, "wholesaler_code": code_a},
    )
    assert resp.status_code == HTTPStatus.OK, resp.text
    return resp.json()["data"]["tokens"]["access_token"]


async def _login_code(client: AsyncClient, code: str, email: str, password: str) -> str:
    resp = await client.post(
        "/api/v1/client/auth/login",
        json={"email": email, "password": password, "wholesaler_code": code},
    )
    assert resp.status_code == HTTPStatus.OK, resp.text
    return resp.json()["data"]["tokens"]["access_token"]


async def _resolve_binding(db, ws_id: str, uid: str) -> str:
    from sqlalchemy import text
    row = (await db.execute(
        text("SELECT retailer_id FROM public.wholesaler_retailer_bindings "
             "WHERE wholesaler_id = :ws AND tenant_user_id = :u AND is_deleted IS FALSE"),
        {"ws": ws_id, "u": uid},
    )).fetchone()
    return str(row.retailer_id)


async def _seed_sku(db, schema: str, retailer_id: str) -> str:
    from sqlalchemy import text
    code = f"S3{uuid.uuid4().hex[:8]}"
    row = (await db.execute(
        text(f'INSERT INTO "{schema}".skus (sku_code, name, is_active, is_deleted) '
             "VALUES (:c, 'S3', true, false) RETURNING id"),
        {"c": code},
    )).fetchone()
    sid = str(row.id)
    await db.execute(text(
        f'INSERT INTO "{schema}".inventory_stocks (sku_id, quantity_on_hand, is_deleted) '
        "VALUES (:s, 100, false)"), {"s": sid})
    await db.execute(text(
        f'INSERT INTO "{schema}".retailer_prices (sku_id, retailer_id, price, is_deleted) '
        "VALUES (:s, :r, 50, false)"), {"s": sid, "r": retailer_id})
    await db.commit()
    return code


async def _create_order(client: AsyncClient, token: str, sku_code: str) -> str:
    resp = await client.post("/api/v1/client/orders",
        json={"items": [{"sku_code": sku_code, "quantity": 2}], "notes": "s3"},
        headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == HTTPStatus.CREATED, resp.text
    return resp.json()["data"]["id"]


# ===========================================================================
# §1 Happy-path preserved
# ===========================================================================


class TestHappyPathPreserved:
    async def test_catalog_readable(self, s3_client, two_tenants):
        token = await _login_retailer(s3_client, two_tenants)
        resp = await s3_client.get("/api/v1/client/products",
            headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == HTTPStatus.OK

    async def test_order_lifecycle(self, s3_client, two_tenants, s2_clean_db):
        from tests.test_dc12r1_s2_supplier_scoped_retailer_login import _pool_instance
        db, reg = s2_clean_db
        code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ws_a = _pool_instance.tenants["a"]["ws_id"]
        sch_a = _pool_instance.tenants["a"]["schema"]
        ret_a = await _resolve_binding(db, ws_a, uid_a)
        sku = await _seed_sku(db, sch_a, ret_a)
        token = await _login_retailer(s3_client, two_tenants)
        oid = await _create_order(s3_client, token, sku)
        assert (await s3_client.get("/api/v1/client/orders",
            headers={"Authorization": f"Bearer {token}"})).status_code == HTTPStatus.OK
        assert (await s3_client.get(f"/api/v1/client/orders/{oid}",
            headers={"Authorization": f"Bearer {token}"})).status_code == HTTPStatus.OK
        assert (await s3_client.post(f"/api/v1/client/orders/{oid}/cancel",
            headers={"Authorization": f"Bearer {token}"})).status_code == HTTPStatus.OK


# ===========================================================================
# §2 Dual-key DB-level scoping (wrong-wholesaler / wrong-retailer excluded)
# ===========================================================================


class TestDualKeyDbScoping:
    """Wrong-wholesaler and wrong-retailer rows in the SAME schema are excluded
    by the DB query — not just post-fetch in the handler."""

    async def test_list_excludes_wrong_retailer(
        self, s3_client, two_tenants, s2_clean_db
    ):
        from sqlalchemy import text
        from tests.test_dc12r1_s2_supplier_scoped_retailer_login import _pool_instance
        db, reg = s2_clean_db
        code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ws_a = _pool_instance.tenants["a"]["ws_id"]
        sch_a = _pool_instance.tenants["a"]["schema"]
        ret_a = await _resolve_binding(db, ws_a, uid_a)
        sku = await _seed_sku(db, sch_a, ret_a)
        token = await _login_retailer(s3_client, two_tenants)
        my_oid = await _create_order(s3_client, token, sku)
        # Insert a foreign retailer + order in the SAME schema.
        foreign_ret = await _create_retailer(db, name="ForeignRet", registry=reg)
        foreign_uid = await _create_retailer_user(db, tenant_schema=sch_a, email=f"fr_{uuid.uuid4().hex[:6]}@x.com", password=_TWO_TENANT_PW, registry=reg)
        await _grant_retailer_operator(db, tenant_schema=sch_a, user_id=foreign_uid)
        await _create_binding(db, wholesaler_id=ws_a, retailer_id=foreign_ret, tenant_user_id=foreign_uid, registry=reg)
        await _seed_sku(db, sch_a, str(foreign_ret))
        await db.execute(text(
            f'INSERT INTO "{sch_a}".orders (id, wholesaler_id, retailer_id, status, total_amount, notes, is_deleted) '
            "VALUES (:id, :ws, :ret, 'draft', 999, 'foreign', false)"),
            {"id": uuid.uuid4(), "ws": ws_a, "ret": str(foreign_ret)})
        await db.commit()
        resp = await s3_client.get("/api/v1/client/orders",
            headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == HTTPStatus.OK
        items = resp.json()["data"]["items"]
        assert all(i["notes"] != "foreign" for i in items), "foreign order leaked"

    async def test_detail_wrong_retailer_404(self, s3_client, two_tenants, s2_clean_db):
        from sqlalchemy import text
        from tests.test_dc12r1_s2_supplier_scoped_retailer_login import _pool_instance
        db, reg = s2_clean_db
        code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ws_a = _pool_instance.tenants["a"]["ws_id"]
        sch_a = _pool_instance.tenants["a"]["schema"]
        ret_a = await _resolve_binding(db, ws_a, uid_a)
        sku = await _seed_sku(db, sch_a, ret_a)
        token = await _login_retailer(s3_client, two_tenants)
        foreign_ret = await _create_retailer(db, name="FR2", registry=reg)
        foreign_uid = await _create_retailer_user(db, tenant_schema=sch_a, email=f"fr2_{uuid.uuid4().hex[:6]}@x.com", password=_TWO_TENANT_PW, registry=reg)
        await _grant_retailer_operator(db, tenant_schema=sch_a, user_id=foreign_uid)
        await _create_binding(db, wholesaler_id=ws_a, retailer_id=foreign_ret, tenant_user_id=foreign_uid, registry=reg)
        foreign_oid = uuid.uuid4()
        await db.execute(text(
            f'INSERT INTO "{sch_a}".orders (id, wholesaler_id, retailer_id, status, total_amount, is_deleted) '
            "VALUES (:id, :ws, :ret, 'draft', 100, false)"),
            {"id": foreign_oid, "ws": ws_a, "ret": str(foreign_ret)})
        await db.commit()
        resp = await s3_client.get(f"/api/v1/client/orders/{foreign_oid}",
            headers={"Authorization": f"Bearer {token}"})
        _assert_controlled_envelope(resp)
        assert resp.status_code == HTTPStatus.NOT_FOUND

    async def test_cross_supplier_order_404(self, s3_client, two_tenants, s2_clean_db):
        from tests.test_dc12r1_s2_supplier_scoped_retailer_login import _pool_instance
        db, reg = s2_clean_db
        code_a, code_b, _sb, email, password, _ua, uid_b = two_tenants
        ws_b = _pool_instance.tenants["b"]["ws_id"]
        sch_b = _pool_instance.tenants["b"]["schema"]
        ret_b = await _resolve_binding(db, ws_b, uid_b)
        sku_b = await _seed_sku(db, sch_b, ret_b)
        tok_b = await _login_code(s3_client, code_b, email, password)
        order_b = await _create_order(s3_client, tok_b, sku_b)
        tok_a = await _login_code(s3_client, code_a, email, password)
        resp = await s3_client.get(f"/api/v1/client/orders/{order_b}",
            headers={"Authorization": f"Bearer {tok_a}"})
        _assert_controlled_envelope(resp)
        assert resp.status_code == HTTPStatus.NOT_FOUND

    async def test_cancel_cross_supplier_404(self, s3_client, two_tenants, s2_clean_db):
        from tests.test_dc12r1_s2_supplier_scoped_retailer_login import _pool_instance
        db, reg = s2_clean_db
        code_a, code_b, _sb, email, password, _ua, uid_b = two_tenants
        ws_b = _pool_instance.tenants["b"]["ws_id"]
        sch_b = _pool_instance.tenants["b"]["schema"]
        ret_b = await _resolve_binding(db, ws_b, uid_b)
        sku_b = await _seed_sku(db, sch_b, ret_b)
        tok_b = await _login_code(s3_client, code_b, email, password)
        order_b = await _create_order(s3_client, tok_b, sku_b)
        tok_a = await _login_code(s3_client, code_a, email, password)
        resp = await s3_client.post(f"/api/v1/client/orders/{order_b}/cancel",
            headers={"Authorization": f"Bearer {tok_a}"})
        _assert_controlled_envelope(resp)
        assert resp.status_code == HTTPStatus.NOT_FOUND

    async def test_malformed_uuid_404(self, s3_client, two_tenants):
        token = await _login_retailer(s3_client, two_tenants)
        resp = await s3_client.get("/api/v1/client/orders/not-a-uuid",
            headers={"Authorization": f"Bearer {token}"})
        _assert_controlled_envelope(resp)
        assert resp.status_code == HTTPStatus.NOT_FOUND


# ===========================================================================
# §3 Inactive / deleted / missing binding, deleted order/SKU
# ===========================================================================


class TestBindingFailClosed:
    async def test_inactive_binding_denied(self, s3_client, two_tenants, s2_clean_db):
        from sqlalchemy import text
        from tests.test_dc12r1_s2_supplier_scoped_retailer_login import _pool_instance
        db, reg = s2_clean_db
        code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ws_a = _pool_instance.tenants["a"]["ws_id"]
        # Login FIRST (before mutating the binding), then flip it to inactive.
        token = await _login_retailer(s3_client, two_tenants)
        await db.execute(text(
            "UPDATE public.wholesaler_retailer_bindings SET status = 'inactive' "
            "WHERE wholesaler_id = :ws AND tenant_user_id = :u"),
            {"ws": ws_a, "u": uid_a})
        await db.commit()
        resp = await s3_client.get("/api/v1/client/products",
            headers={"Authorization": f"Bearer {token}"})
        _assert_controlled_envelope(resp)
        assert resp.status_code == HTTPStatus.FORBIDDEN

    async def test_soft_deleted_binding_denied(self, s3_client, two_tenants, s2_clean_db):
        from sqlalchemy import text
        from tests.test_dc12r1_s2_supplier_scoped_retailer_login import _pool_instance
        db, reg = s2_clean_db
        code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ws_a = _pool_instance.tenants["a"]["ws_id"]
        token = await _login_retailer(s3_client, two_tenants)
        await db.execute(text(
            "UPDATE public.wholesaler_retailer_bindings SET is_deleted = true "
            "WHERE wholesaler_id = :ws AND tenant_user_id = :u"),
            {"ws": ws_a, "u": uid_a})
        await db.commit()
        resp = await s3_client.get("/api/v1/client/orders",
            headers={"Authorization": f"Bearer {token}"})
        _assert_controlled_envelope(resp)
        assert resp.status_code == HTTPStatus.FORBIDDEN

    async def test_soft_deleted_order_404(self, s3_client, two_tenants, s2_clean_db):
        from sqlalchemy import text
        from tests.test_dc12r1_s2_supplier_scoped_retailer_login import _pool_instance
        db, reg = s2_clean_db
        code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ws_a = _pool_instance.tenants["a"]["ws_id"]
        sch_a = _pool_instance.tenants["a"]["schema"]
        ret_a = await _resolve_binding(db, ws_a, uid_a)
        sku = await _seed_sku(db, sch_a, ret_a)
        token = await _login_retailer(s3_client, two_tenants)
        oid = await _create_order(s3_client, token, sku)
        await db.execute(text(
            f'UPDATE "{sch_a}".orders SET is_deleted = true WHERE id = :id'),
            {"id": oid})
        await db.commit()
        resp = await s3_client.get(f"/api/v1/client/orders/{oid}",
            headers={"Authorization": f"Bearer {token}"})
        _assert_controlled_envelope(resp)
        assert resp.status_code == HTTPStatus.NOT_FOUND

    async def test_deleted_sku_rejected_on_create(self, s3_client, two_tenants, s2_clean_db):
        from sqlalchemy import text
        from tests.test_dc12r1_s2_supplier_scoped_retailer_login import _pool_instance
        db, reg = s2_clean_db
        code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ws_a = _pool_instance.tenants["a"]["ws_id"]
        sch_a = _pool_instance.tenants["a"]["schema"]
        ret_a = await _resolve_binding(db, ws_a, uid_a)
        sku_code = await _seed_sku(db, sch_a, ret_a)
        await db.execute(text(
            f'UPDATE "{sch_a}".skus SET is_deleted = true WHERE sku_code = :c'),
            {"c": sku_code})
        await db.commit()
        token = await _login_retailer(s3_client, two_tenants)
        resp = await s3_client.post("/api/v1/client/orders",
            json={"items": [{"sku_code": sku_code, "quantity": 1}]},
            headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == HTTPStatus.BAD_REQUEST
        assert resp.json()["code"] == "ORDER_VALIDATION_FAILED"


# ===========================================================================
# §4 Identity / token fail-closed
# ===========================================================================


class TestTokenFailClosed:
    async def test_identity_only_jwt_denied(self, s3_client, two_tenants):
        from core.security import create_identity_token
        tok = create_identity_token(user_id=str(uuid.uuid4()), roles=["retailer_operator"])
        resp = await s3_client.get("/api/v1/client/products",
            headers={"Authorization": f"Bearer {tok}"})
        _assert_controlled_envelope(resp)
        assert resp.status_code == HTTPStatus.FORBIDDEN

    async def test_missing_token_denied(self, s3_client):
        resp = await s3_client.get("/api/v1/client/products")
        _assert_controlled_envelope(resp)
        assert resp.status_code == HTTPStatus.UNAUTHORIZED

    async def test_malformed_token_denied(self, s3_client):
        resp = await s3_client.get("/api/v1/client/products",
            headers={"Authorization": "Bearer not.a.jwt"})
        _assert_controlled_envelope(resp)
        assert resp.status_code == HTTPStatus.UNAUTHORIZED


# ===========================================================================
# §5 Permission enforcement + zero route-body SQL on denial
# ===========================================================================


class TestPermissionDenial:
    @staticmethod
    async def _strip_perm(db, schema: str, code: str):
        from sqlalchemy import text
        await db.execute(text(
            f'DELETE FROM "{schema}".role_permissions rp '
            f'USING "{schema}".permissions p, "{schema}".roles r '
            "WHERE rp.permission_id = p.id AND rp.role_id = r.id "
            f"AND p.code = :code AND r.name = 'retailer_operator'"), {"code": code})
        await db.commit()

    @staticmethod
    async def _restore_perm(db, schema: str, code: str):
        from sqlalchemy import text
        await db.execute(text(
            f'INSERT INTO "{schema}".role_permissions (role_id, permission_id) '
            f'SELECT r.id, p.id FROM "{schema}".roles r, "{schema}".permissions p '
            "WHERE r.name = 'retailer_operator' AND p.code = :code "
            "AND NOT EXISTS (SELECT 1 FROM "
            f'"{schema}".role_permissions rp WHERE rp.role_id = r.id AND rp.permission_id = p.id)'),
            {"code": code})
        await db.commit()

    async def test_catalog_denied(self, s3_client, two_tenants, s2_clean_db):
        from tests.test_dc12r1_s2_supplier_scoped_retailer_login import _pool_instance
        db, reg = s2_clean_db
        code_a, _b, _sb, _e, _p, _ua, _ub = two_tenants
        sch_a = _pool_instance.tenants["a"]["schema"]
        try:
            await self._strip_perm(db, sch_a, "client:catalog:read")
            token = await _login_retailer(s3_client, two_tenants)
            resp = await s3_client.get("/api/v1/client/products",
                headers={"Authorization": f"Bearer {token}"})
            _assert_controlled_envelope(resp)
            assert resp.status_code == HTTPStatus.FORBIDDEN
            assert resp.json()["code"] == "PERMISSION_DENIED"
        finally:
            await self._restore_perm(db, sch_a, "client:catalog:read")

    async def test_orders_read_denied(self, s3_client, two_tenants, s2_clean_db):
        from tests.test_dc12r1_s2_supplier_scoped_retailer_login import _pool_instance
        db, reg = s2_clean_db
        code_a, _b, _sb, _e, _p, _ua, _ub = two_tenants
        sch_a = _pool_instance.tenants["a"]["schema"]
        try:
            await self._strip_perm(db, sch_a, "client:orders:read")
            token = await _login_retailer(s3_client, two_tenants)
            resp = await s3_client.get("/api/v1/client/orders",
                headers={"Authorization": f"Bearer {token}"})
            _assert_controlled_envelope(resp)
            assert resp.status_code == HTTPStatus.FORBIDDEN
        finally:
            await self._restore_perm(db, sch_a, "client:orders:read")

    async def test_orders_create_denied(self, s3_client, two_tenants, s2_clean_db):
        from tests.test_dc12r1_s2_supplier_scoped_retailer_login import _pool_instance
        db, reg = s2_clean_db
        code_a, _b, _sb, _e, _p, _ua, _ub = two_tenants
        sch_a = _pool_instance.tenants["a"]["schema"]
        try:
            await self._strip_perm(db, sch_a, "client:orders:create")
            token = await _login_retailer(s3_client, two_tenants)
            resp = await s3_client.post("/api/v1/client/orders",
                json={"items": [{"sku_code": "X", "quantity": 1}]},
                headers={"Authorization": f"Bearer {token}"})
            _assert_controlled_envelope(resp)
            assert resp.status_code == HTTPStatus.FORBIDDEN
        finally:
            await self._restore_perm(db, sch_a, "client:orders:create")

    async def test_missing_perm_zero_body_sql(
        self, s3_client, two_tenants, s2_clean_db
    ):
        """When client:orders:read is absent, NO orders-table SELECT executes."""
        from sqlalchemy import event
        from database.session import async_engine
        from tests.test_dc12r1_s2_supplier_scoped_retailer_login import _pool_instance
        db, reg = s2_clean_db
        code_a, _b, _sb, _e, _p, _ua, _ub = two_tenants
        sch_a = _pool_instance.tenants["a"]["schema"]
        try:
            await self._strip_perm(db, sch_a, "client:orders:read")
            token = await _login_retailer(s3_client, two_tenants)
            captured: list[str] = []

            def _cap(conn, cursor, statement, parameters, context, executemany):
                captured.append(statement)

            event.listen(async_engine.sync_engine, "before_cursor_execute", _cap)
            try:
                resp = await s3_client.get("/api/v1/client/orders",
                    headers={"Authorization": f"Bearer {token}"})
            finally:
                event.remove(async_engine.sync_engine, "before_cursor_execute", _cap)
            assert resp.status_code == HTTPStatus.FORBIDDEN
            offending = [s for s in captured if "orders" in s.lower() and "select" in s.lower()]
            assert not offending, f"denied route executed orders SQL: {offending}"
        finally:
            await self._restore_perm(db, sch_a, "client:orders:read")


# ===========================================================================
# §6 Generic routes remain denied
# ===========================================================================


class TestGenericRoutesDenied:
    async def test_generic_orders_denied(self, s3_client, two_tenants):
        token = await _login_retailer(s3_client, two_tenants)
        resp = await s3_client.get("/api/v1/orders",
            headers={"Authorization": f"Bearer {token}"})
        _assert_controlled_envelope(resp)
        assert resp.status_code == HTTPStatus.FORBIDDEN

    async def test_generic_payments_denied(self, s3_client, two_tenants):
        token = await _login_retailer(s3_client, two_tenants)
        resp = await s3_client.get("/api/v1/payments",
            headers={"Authorization": f"Bearer {token}"})
        _assert_controlled_envelope(resp)
        assert resp.status_code == HTTPStatus.FORBIDDEN

    async def test_generic_finance_denied(self, s3_client, two_tenants):
        token = await _login_retailer(s3_client, two_tenants)
        resp = await s3_client.get("/api/v1/finance/receivables",
            headers={"Authorization": f"Bearer {token}"})
        _assert_controlled_envelope(resp)
        assert resp.status_code == HTTPStatus.FORBIDDEN


# ===========================================================================
# §7 GAP-07 governance freeze — registered route/dependency inventory proof
# ===========================================================================


class TestGap07GovernanceFreeze:
    """No registered FastAPI route under /api/v1/client/ consumes
    client:payments:create; no payment/ledger/receivable mutation. Proven via
    the registered route dependency tree, not text scanning."""

    @staticmethod
    def _collect_client_route_perms() -> set[tuple[frozenset[str], str]]:
        """Collect (methods, permission) for every registered client route."""
        from api.middleware.rbac import RequirePermission
        app = FastAPI()
        with mock.patch("auth.factory.get_auth_strategy", return_value=JwtAuthStrategy()):
            configure_app(app, get_settings())
        results: set[tuple[frozenset[str], str]] = set()
        for route in app.routes:
            if not isinstance(route, APIRoute):
                continue
            if not route.path.startswith("/api/v1/client/"):
                continue
            if not (hasattr(route, "dependant") and route.dependant):
                continue
            for dep in route.dependant.dependencies:
                call = getattr(dep, "call", None)
                if isinstance(call, RequirePermission):
                    results.add((frozenset(route.methods or set()), call.permission))
        return results

    def test_no_client_route_requires_client_payments_create(self):
        perms = self._collect_client_route_perms()
        payment_routes = {(m, p) for m, p in perms if p == "client:payments:create"}
        assert not payment_routes, f"GAP-07 violation: {payment_routes}"

    def test_no_unexpected_client_mutation_route(self):
        perms = self._collect_client_route_perms()
        mutation_methods = {"POST", "PUT", "PATCH", "DELETE"}
        unexpected = {
            (m, p) for m, p in perms
            if m & mutation_methods and p not in ("client:orders:create", "client:payments:declare")
        }
        assert not unexpected, f"unexpected client mutation: {unexpected}"


# ===========================================================================
# §8 Provisioning PG-catalog assertion
# ===========================================================================


class TestProvisioningRolePermissions:
    """After provisioning: admin has only ADMIN_PERMISSION_CODES;
    retailer_operator has exactly RETAILER_OPERATOR_PERMISSION_CODES.

    Uses the migration-provisioned tenant (which seeds roles + perms via
    migration 036) and asserts the PG catalog directly."""

    async def test_provisioned_tenant_role_permissions(self, s2_clean_db):
        from sqlalchemy import text
        from core.permission_registry import (
            ADMIN_PERMISSION_CODES,
            RETAILER_OPERATOR_PERMISSION_CODES,
        )
        from tests.test_dc12r1_s2_supplier_scoped_retailer_login import _pool_instance

        db, reg = s2_clean_db
        sch = _pool_instance.tenants["a"]["schema"]

        retailer_perms = set(r.code for r in (await db.execute(text(
            f'SELECT p.code FROM "{sch}".role_permissions rp '
            f'JOIN "{sch}".permissions p ON rp.permission_id = p.id '
            f'JOIN "{sch}".roles r ON rp.role_id = r.id '
            "WHERE r.name = 'retailer_operator'"
        ))).fetchall())

        # Migration 036 seeds retailer_operator with exactly client:* perms.
        assert retailer_perms == set(RETAILER_OPERATOR_PERMISSION_CODES), (
            f"retailer drift: {retailer_perms ^ set(RETAILER_OPERATOR_PERMISSION_CODES)}")

        # If an admin role exists, it must NOT overlap with retailer_operator.
        admin_perms = set(r.code for r in (await db.execute(text(
            f'SELECT p.code FROM "{sch}".role_permissions rp '
            f'JOIN "{sch}".permissions p ON rp.permission_id = p.id '
            f'JOIN "{sch}".roles r ON rp.role_id = r.id '
            "WHERE r.name = 'admin'"
        ))).fetchall())
        if admin_perms:
            assert admin_perms == set(ADMIN_PERMISSION_CODES), (
                f"admin drift: {admin_perms ^ set(ADMIN_PERMISSION_CODES)}")
            assert not (admin_perms & retailer_perms), "roles overlap"


# ===========================================================================
# §9 R2: Exact client route allowlist + payment/finance mutation rejection
# ===========================================================================


class TestClientRouteAllowlist:
    """Enumerate EVERY registered /api/v1/client route and enforce an exact
    method/path/permission allowlist. No route may consume
    client:payments:create or be a payment/finance mutation."""

    def test_exact_client_route_inventory(self):
        from api.middleware.rbac import RequirePermission

        app = FastAPI()
        with mock.patch("auth.factory.get_auth_strategy", return_value=JwtAuthStrategy()):
            configure_app(app, get_settings())

        expected = {
            ("POST", "/api/v1/client/auth/forgot-password"): None,
            ("POST", "/api/v1/client/auth/login"): None,
            ("POST", "/api/v1/client/auth/reset-password"): None,
            ("POST", "/api/v1/client/orders"): "client:orders:create",
            ("GET", "/api/v1/client/orders"): "client:orders:read",
            ("GET", "/api/v1/client/orders/{order_id}"): "client:orders:read",
            ("POST", "/api/v1/client/orders/{order_id}/cancel"): "client:orders:create",
            ("GET", "/api/v1/client/payments"): "client:payments:read",
            ("GET", "/api/v1/client/finance/balance"): "client:finance:read",
            ("GET", "/api/v1/client/products"): "client:catalog:read",
            ("GET", "/api/v1/client/products/{product_id}"): "client:catalog:read",
            # DC-12R1-S3-S2B-I2B: declaration submission + retailer views + statement.
            ("POST", "/api/v1/client/orders/{order_id}/declare"): "client:payments:declare",
            ("GET", "/api/v1/client/declarations"): "client:payments:read",
            ("GET", "/api/v1/client/declarations/{declaration_id}"): "client:payments:read",
            ("GET", "/api/v1/client/statements"): "client:payments:read",
            # DC-12R1-S3-S2B-I2C-I1: printable records (Contracts A-C).
            ("GET", "/api/v1/client/orders/{order_id}/print"): "client:orders:read",
            ("GET", "/api/v1/client/declarations/{declaration_id}/print"): "client:payments:read",
            ("GET", "/api/v1/client/declarations/{declaration_id}/receipt"): "client:payments:read",
            # DC-12R1-S3-S2B-I2C-I2B (Contract D): printable relationship statement.
            ("GET", "/api/v1/client/statements/print"): "client:finance:read",
        }

        actual: dict[tuple[str, str], str | None] = {}
        for route in app.routes:
            if not isinstance(route, APIRoute):
                continue
            if not route.path.startswith("/api/v1/client"):
                continue
            methods = sorted(route.methods - {"HEAD", "OPTIONS"}) if route.methods else []
            perm = None
            if hasattr(route, "dependant") and route.dependant:
                for dep in route.dependant.dependencies:
                    call = getattr(dep, "call", None)
                    if isinstance(call, RequirePermission):
                        perm = call.permission
            for method in methods:
                actual[(method, route.path)] = perm

        assert set(actual.keys()) == set(expected.keys()), (
            f"route drift:\n  extra: {set(actual) - set(expected)}\n"
            f"  missing: {set(expected) - set(actual)}"
        )
        for key, exp_perm in expected.items():
            assert actual[key] == exp_perm, (
                f"permission drift for {key}: expected {exp_perm}, got {actual[key]}"
            )

    def test_client_payment_and_finance_routes_are_get_only(self):
        """Client payment and finance visibility routes are read-only."""
        app = FastAPI()
        with mock.patch("auth.factory.get_auth_strategy", return_value=JwtAuthStrategy()):
            configure_app(app, get_settings())
        financial_routes = []
        for route in app.routes:
            if not isinstance(route, APIRoute):
                continue
            if route.path.startswith(("/api/v1/client/payments", "/api/v1/client/finance")):
                financial_routes.append((route.path, route.methods - {"HEAD", "OPTIONS"}))
        assert financial_routes == [
            ("/api/v1/client/payments", {"GET"}),
            ("/api/v1/client/finance/balance", {"GET"}),
        ]


# ===========================================================================
# §10 R2: Same-schema wrong-wholesaler + wrong-retailer cancel
# ===========================================================================


class TestSameSchemaWrongEntityExclusion:
    """Wrong-wholesaler and wrong-retailer rows in the same schema are excluded
    at the DB-query level for list, detail AND cancel."""

    async def test_list_excludes_wrong_wholesaler(
        self, s3_client, two_tenants, s2_clean_db
    ):
        """LIST: an order with a different wholesaler_id (same retailer) is
        excluded from the retailer's order list."""
        from sqlalchemy import text
        from tests.test_dc12r1_s2_supplier_scoped_retailer_login import _pool_instance
        db, reg = s2_clean_db
        code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ws_a = _pool_instance.tenants["a"]["ws_id"]
        sch_a = _pool_instance.tenants["a"]["schema"]
        ret_a = await _resolve_binding(db, ws_a, uid_a)
        sku = await _seed_sku(db, sch_a, ret_a)
        token = await _login_retailer(s3_client, two_tenants)
        oid = await _create_order(s3_client, token, sku)
        # Insert a wrong-wholesaler order with same retailer_id.
        fake_ws = uuid.uuid4()
        wrong_oid = uuid.uuid4()
        try:
            await db.execute(text(
                f'INSERT INTO "{sch_a}".orders (id, wholesaler_id, retailer_id, status, total_amount, is_deleted) '
                "VALUES (:id, :ws, :ret, 'draft', 100, false)"),
                {"id": wrong_oid, "ws": str(fake_ws), "ret": ret_a})
            await db.commit()
            resp = await s3_client.get("/api/v1/client/orders",
                headers={"Authorization": f"Bearer {token}"})
            assert resp.status_code == HTTPStatus.OK
            items = resp.json()["data"]["items"]
            assert all(str(i["id"]) != str(wrong_oid) for i in items), "wrong-wholesaler order leaked into list"
        finally:
            await db.execute(text(f'DELETE FROM "{sch_a}".orders WHERE id = :id'), {"id": str(wrong_oid)})
            await db.commit()

    async def test_detail_wrong_wholesaler_404(
        self, s3_client, two_tenants, s2_clean_db
    ):
        """DETAIL: GET /api/v1/client/orders/{wrong_wholesaler_oid} → 404."""
        from sqlalchemy import text
        from tests.test_dc12r1_s2_supplier_scoped_retailer_login import _pool_instance
        db, reg = s2_clean_db
        code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ws_a = _pool_instance.tenants["a"]["ws_id"]
        sch_a = _pool_instance.tenants["a"]["schema"]
        ret_a = await _resolve_binding(db, ws_a, uid_a)
        fake_ws = uuid.uuid4()
        wrong_oid = uuid.uuid4()
        try:
            await db.execute(text(
                f'INSERT INTO "{sch_a}".orders (id, wholesaler_id, retailer_id, status, total_amount, is_deleted) '
                "VALUES (:id, :ws, :ret, 'draft', 100, false)"),
                {"id": wrong_oid, "ws": str(fake_ws), "ret": ret_a})
            await db.commit()
            token = await _login_retailer(s3_client, two_tenants)
            resp = await s3_client.get(f"/api/v1/client/orders/{wrong_oid}",
                headers={"Authorization": f"Bearer {token}"})
            _assert_controlled_envelope(resp)
            assert resp.status_code == HTTPStatus.NOT_FOUND
        finally:
            await db.execute(text(f'DELETE FROM "{sch_a}".orders WHERE id = :id'), {"id": str(wrong_oid)})
            await db.commit()

    async def test_cancel_wrong_wholesaler_404(
        self, s3_client, two_tenants, s2_clean_db
    ):
        """CANCEL: POST /api/v1/client/orders/{wrong_wholesaler_oid}/cancel → 404."""
        from sqlalchemy import text
        from tests.test_dc12r1_s2_supplier_scoped_retailer_login import _pool_instance
        db, reg = s2_clean_db
        code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ws_a = _pool_instance.tenants["a"]["ws_id"]
        sch_a = _pool_instance.tenants["a"]["schema"]
        ret_a = await _resolve_binding(db, ws_a, uid_a)
        fake_ws = uuid.uuid4()
        wrong_oid = uuid.uuid4()
        try:
            await db.execute(text(
                f'INSERT INTO "{sch_a}".orders (id, wholesaler_id, retailer_id, status, total_amount, is_deleted) '
                "VALUES (:id, :ws, :ret, 'draft', 100, false)"),
                {"id": wrong_oid, "ws": str(fake_ws), "ret": ret_a})
            await db.commit()
            token = await _login_retailer(s3_client, two_tenants)
            resp = await s3_client.post(f"/api/v1/client/orders/{wrong_oid}/cancel",
                headers={"Authorization": f"Bearer {token}"})
            _assert_controlled_envelope(resp)
            assert resp.status_code == HTTPStatus.NOT_FOUND
        finally:
            await db.execute(text(f'DELETE FROM "{sch_a}".orders WHERE id = :id'), {"id": str(wrong_oid)})
            await db.commit()

    async def test_cancel_wrong_retailer_same_supplier_404(
        self, s3_client, two_tenants, s2_clean_db
    ):
        """Cancelling another retailer's order in the same supplier → 404."""
        from sqlalchemy import text
        from tests.test_dc12r1_s2_supplier_scoped_retailer_login import _pool_instance
        db, reg = s2_clean_db
        code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ws_a = _pool_instance.tenants["a"]["ws_id"]
        sch_a = _pool_instance.tenants["a"]["schema"]
        foreign_ret = await _create_retailer(db, name="CancelFR", registry=reg)
        foreign_uid = await _create_retailer_user(db, tenant_schema=sch_a,
            email=f"cfr_{uuid.uuid4().hex[:6]}@x.com", password=_TWO_TENANT_PW, registry=reg)
        foreign_ret_id = str(foreign_ret)
        foreign_oid = uuid.uuid4()
        try:
            await _grant_retailer_operator(db, tenant_schema=sch_a, user_id=foreign_uid)
            await _create_binding(db, wholesaler_id=ws_a, retailer_id=foreign_ret_id,
                tenant_user_id=foreign_uid, registry=reg)
            await db.execute(text(
                f'INSERT INTO "{sch_a}".orders (id, wholesaler_id, retailer_id, status, total_amount, is_deleted) '
                "VALUES (:id, :ws, :ret, 'draft', 100, false)"),
                {"id": foreign_oid, "ws": ws_a, "ret": foreign_ret_id})
            await db.commit()
            token = await _login_retailer(s3_client, two_tenants)
            resp = await s3_client.post(f"/api/v1/client/orders/{foreign_oid}/cancel",
                headers={"Authorization": f"Bearer {token}"})
            _assert_controlled_envelope(resp)
            assert resp.status_code == HTTPStatus.NOT_FOUND
        finally:
            await db.execute(text(f'DELETE FROM "{sch_a}".orders WHERE id = :id'), {"id": str(foreign_oid)})
            # Delete binding, retailer, user in FK-safe order
            await db.execute(text(
                "DELETE FROM public.wholesaler_retailer_bindings "
                "WHERE tenant_user_id = :uid"), {"uid": str(foreign_uid)})
            await db.execute(text(
                f'DELETE FROM "{sch_a}".user_roles WHERE user_id = :uid'), {"uid": str(foreign_uid)})
            await db.execute(text(
                f'DELETE FROM "{sch_a}".users WHERE id = :uid'), {"uid": str(foreign_uid)})
            await db.execute(text(
                "DELETE FROM public.retailers WHERE id = :rid AND name = 'CancelFR'"),
                {"rid": foreign_ret_id})
            await db.commit()


# ===========================================================================
# §11 Malformed UUID → controlled fail-closed with zero order query
# ===========================================================================


class TestMalformedUuidFailClosed:
    async def test_malformed_uuid_zero_order_query(
        self, s3_client, two_tenants, s2_clean_db
    ):
        """A malformed UUID on detail must return 404 without executing
        any orders-table SELECT."""
        from sqlalchemy import event
        from database.session import async_engine
        token = await _login_retailer(s3_client, two_tenants)
        captured: list[str] = []

        def _cap(conn, cursor, statement, parameters, context, executemany):
            captured.append(statement)

        event.listen(async_engine.sync_engine, "before_cursor_execute", _cap)
        try:
            resp = await s3_client.get("/api/v1/client/orders/not-a-valid-uuid",
                headers={"Authorization": f"Bearer {token}"})
        finally:
            event.remove(async_engine.sync_engine, "before_cursor_execute", _cap)
        assert resp.status_code == HTTPStatus.NOT_FOUND
        offending = [s for s in captured if "orders" in s.lower() and "select" in s.lower()]
        assert not offending, f"malformed-UUID request executed orders SQL: {offending}"


# ===========================================================================
# §11b R3-R1: Malformed wholesaler_id / retailer_id repository proof
# ===========================================================================


class TestMalformedIdentity:
    """Direct repository tests for malformed wholesaler_id and retailer_id.

    The R3 change to crud.order.get_orders_for_retailer catches ValueError/
    TypeError from UUID() and returns ([], 0) with zero SQL queries.
    """

    async def test_malformed_wholesaler_id_returns_empty(
        self, s2_clean_db
    ):
        """get_orders_for_retailer with invalid wholesaler_id → ([], 0), no SQL."""
        from unittest.mock import AsyncMock
        from crud.order import get_orders_for_retailer

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()

        result, count = await get_orders_for_retailer(
            mock_db,
            wholesaler_id="not-a-valid-uuid-for-wholesaler",
            retailer_id="550e8400-e29b-41d4-a716-446655440000",
        )
        assert result == [], f"expected [], got {result}"
        assert count == 0, f"expected 0, got {count}"
        mock_db.execute.assert_not_called()

    async def test_malformed_retailer_id_returns_empty(
        self, s2_clean_db
    ):
        """get_orders_for_retailer with invalid retailer_id → ([], 0), no SQL."""
        from unittest.mock import AsyncMock
        from crud.order import get_orders_for_retailer

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()

        result, count = await get_orders_for_retailer(
            mock_db,
            wholesaler_id="550e8400-e29b-41d4-a716-446655440000",
            retailer_id="not-a-valid-uuid-for-retailer",
        )
        assert result == [], f"expected [], got {result}"
        assert count == 0, f"expected 0, got {count}"
        mock_db.execute.assert_not_called()


# ===========================================================================
# §12 R3-R1: Real-PG dirty-state reconciliation proof for ALL 4 seeder paths
# ===========================================================================


class _ContaminationHelper:
    """Shared helpers for dirty-state RBAC tests."""

    @staticmethod
    async def role_perms(db, schema: str, role_name: str) -> set[str]:
        from sqlalchemy import text
        rows = (await db.execute(text(
            f'SELECT p.code FROM "{schema}".role_permissions rp '
            f'JOIN "{schema}".permissions p ON rp.permission_id = p.id '
            f'JOIN "{schema}".roles r ON rp.role_id = r.id '
            f"WHERE r.name = '{role_name}'"
        ))).fetchall()
        return set(r.code for r in rows)

    @staticmethod
    async def contaminate(db, schema: str, role_name: str, perm_code: str) -> None:
        """Grant a foreign permission to a role. Ensures the permission code
        exists in the permissions table first."""
        from sqlalchemy import text
        await db.execute(text(
            f'INSERT INTO "{schema}".permissions (code, description) '
            "VALUES (:code, :desc) ON CONFLICT (code) DO NOTHING"),
            {"code": perm_code, "desc": "contamination test"})
        await db.execute(text(
            f'INSERT INTO "{schema}".role_permissions (role_id, permission_id) '
            f'SELECT r.id, p.id FROM "{schema}".roles r, "{schema}".permissions p '
            f"WHERE r.name = :role AND p.code = :code "
            f'AND NOT EXISTS (SELECT 1 FROM "{schema}".role_permissions rp '
            f'WHERE rp.role_id = r.id AND rp.permission_id = p.id)'),
            {"role": role_name, "code": perm_code})

    @staticmethod
    async def strip_perm(db, schema: str, role_name: str, perm_code: str) -> None:
        """Remove a canonical permission from a role to simulate missing grant."""
        from sqlalchemy import text
        await db.execute(text(
            f'DELETE FROM "{schema}".role_permissions rp '
            f'USING "{schema}".permissions p, "{schema}".roles r '
            "WHERE rp.permission_id = p.id AND rp.role_id = r.id "
            f"AND p.code = :code AND r.name = :role"),
            {"code": perm_code, "role": role_name})

    @staticmethod
    async def cleanup_perms(db, schema: str, *perm_codes: str) -> None:
        """Remove contamination permission codes from permissions table."""
        from sqlalchemy import text
        for code in perm_codes:
            await db.execute(text(
                f'DELETE FROM "{schema}".permissions WHERE code = :code AND description = \'contamination test\''),
                {"code": code})

    @staticmethod
    async def cleanup_users(db, schema: str, *emails: str) -> None:
        """Delete test users and their role assignments."""
        from sqlalchemy import text
        for email in emails:
            uid = (await db.execute(text(
                f'SELECT id FROM "{schema}".users WHERE email = :e'), {"e": email})).scalar()
            if uid:
                await db.execute(text(
                    f'DELETE FROM "{schema}".user_roles WHERE user_id = :u'), {"u": uid})
                await db.execute(text(
                    f'DELETE FROM "{schema}".users WHERE id = :u'), {"u": uid})


class TestRealPgSeederPaths:
    """Each test exercises a real production seeder callable on real PG16 with
    deliberately contaminated RBAC state, then proves exact canonical
    reconciliation and second-run idempotency."""

    # ------------------------------------------------------------------
    # Seeder 1: onboard_tenant.setup_admin
    # ------------------------------------------------------------------

    async def test_seeder1_onboard_tenant(
        self, s2_clean_db
    ):
        from core.permission_registry import (
            ADMIN_PERMISSION_CODES,
            RETAILER_OPERATOR_PERMISSION_CODES,
        )
        from scripts.onboard_tenant import setup_admin
        from tests.test_dc12r1_s2_supplier_scoped_retailer_login import _pool_instance

        db, reg = s2_clean_db
        sch = _pool_instance.tenants["a"]["schema"]
        email_base = f"r3r1_seed1_{uuid.uuid4().hex[:8]}"
        email1 = f"{email_base}@cleanup.local"
        email2 = f"{email_base}2@cleanup.local"
        email3 = f"{email_base}3@cleanup.local"
        owned_emails = [email1, email2, email3]

        try:
            # Run seeder once to establish baseline
            await setup_admin(db, sch, email1, "TestPass1!")
            await db.commit()

            # Contaminate: admin gets client:* ; retailer gets admin perm ; missing canonical
            await _ContaminationHelper.contaminate(db, sch, "admin", "client:catalog:read")
            await _ContaminationHelper.contaminate(db, sch, "retailer_operator", "orders:read")
            await _ContaminationHelper.strip_perm(db, sch, "retailer_operator", "client:orders:read")
            await db.commit()

            # Verify contamination took hold
            assert "client:catalog:read" in await _ContaminationHelper.role_perms(db, sch, "admin")
            assert "orders:read" in await _ContaminationHelper.role_perms(db, sch, "retailer_operator")
            assert "client:orders:read" not in await _ContaminationHelper.role_perms(db, sch, "retailer_operator")

            # Run seeder again with different user — should reconcile
            await setup_admin(db, sch, email2, "TestPass1!")
            await db.commit()

            admin_perms = await _ContaminationHelper.role_perms(db, sch, "admin")
            retailer_perms = await _ContaminationHelper.role_perms(db, sch, "retailer_operator")

            assert admin_perms == set(ADMIN_PERMISSION_CODES), (
                f"admin not reconciled: extra={admin_perms - set(ADMIN_PERMISSION_CODES)}, "
                f"missing={set(ADMIN_PERMISSION_CODES) - admin_perms}")
            assert retailer_perms == set(RETAILER_OPERATOR_PERMISSION_CODES), (
                f"retailer not reconciled: extra={retailer_perms - set(RETAILER_OPERATOR_PERMISSION_CODES)}, "
                f"missing={set(RETAILER_OPERATOR_PERMISSION_CODES) - retailer_perms}")
            assert "client:catalog:read" not in admin_perms, "client perm leaked into admin"
            assert "orders:read" not in retailer_perms, "admin perm leaked into retailer"
            assert "client:orders:read" in retailer_perms, "canonical perm still missing after reconcile"

            # Prove third run is idempotent
            await setup_admin(db, sch, email3, "TestPass1!")
            await db.commit()

            admin_perms2 = await _ContaminationHelper.role_perms(db, sch, "admin")
            retailer_perms2 = await _ContaminationHelper.role_perms(db, sch, "retailer_operator")

            assert admin_perms2 == admin_perms, "admin fingerprint changed on re-run"
            assert retailer_perms2 == retailer_perms, "retailer fingerprint changed on re-run"

        finally:
            await _ContaminationHelper.cleanup_users(db, sch, *owned_emails)
            await _ContaminationHelper.cleanup_perms(db, sch, "client:catalog:read")
            await db.commit()

    # ------------------------------------------------------------------
    # Seeder 2: create_wholesaler.assign_all_permissions_to_admin
    # ------------------------------------------------------------------

    async def test_seeder2_create_wholesaler(
        self, s2_clean_db
    ):
        """assign_all_permissions_to_admin reconciles only the admin role
        (this seeder does not touch retailer_operator)."""
        from sqlalchemy import text
        from core.permission_registry import ADMIN_PERMISSION_CODES
        from scripts.create_wholesaler import assign_all_permissions_to_admin
        from tests.test_dc12r1_s2_supplier_scoped_retailer_login import _pool_instance

        db, reg = s2_clean_db
        sch = _pool_instance.tenants["a"]["schema"]

        try:
            # Record pre-seeder retailer perms (should not change)
            retailer_before = await _ContaminationHelper.role_perms(db, sch, "retailer_operator")

            # Contaminate admin with a client:* perm
            await _ContaminationHelper.contaminate(db, sch, "admin", "client:catalog:read")
            await db.commit()
            assert "client:catalog:read" in await _ContaminationHelper.role_perms(db, sch, "admin")

            # Run the production seeder
            await assign_all_permissions_to_admin(db, sch)
            await db.commit()

            admin_perms = await _ContaminationHelper.role_perms(db, sch, "admin")
            assert admin_perms == set(ADMIN_PERMISSION_CODES), (
                f"admin not reconciled after seeder2: {admin_perms ^ set(ADMIN_PERMISSION_CODES)}")
            assert "client:catalog:read" not in admin_perms

            # Retailer operator must be unchanged by this seeder
            retailer_after = await _ContaminationHelper.role_perms(db, sch, "retailer_operator")
            assert retailer_after == retailer_before, "retailer_operator was modified by create_wholesaler seeder"

            # Second run: idempotent
            await assign_all_permissions_to_admin(db, sch)
            await db.commit()
            admin_perms2 = await _ContaminationHelper.role_perms(db, sch, "admin")
            assert admin_perms2 == admin_perms, "admin fingerprint changed on re-run"

        finally:
            await _ContaminationHelper.cleanup_perms(db, sch, "client:catalog:read")
            await db.commit()

    # ------------------------------------------------------------------
    # Seeder 3: seed_test_tenant._seed_admin_rbac
    # ------------------------------------------------------------------

    async def test_seeder3_seed_test_tenant(
        self, s2_clean_db
    ):
        from core.permission_registry import (
            ADMIN_PERMISSION_CODES,
            ADMIN_PERMISSIONS,
            RETAILER_OPERATOR_PERMISSION_CODES,
            RETAILER_OPERATOR_PERMISSIONS,
        )
        from scripts.seed_test_tenant import _seed_admin_rbac
        from tests.test_dc12r1_s2_supplier_scoped_retailer_login import _pool_instance

        db, reg = s2_clean_db
        sch = _pool_instance.tenants["a"]["schema"]
        email_base = f"r3r1_seed3_{uuid.uuid4().hex[:8]}"
        email1 = f"{email_base}@cleanup.local"
        email2 = f"{email_base}2@cleanup.local"
        owned_emails = [email1, email2]
        all_permissions = ADMIN_PERMISSIONS + RETAILER_OPERATOR_PERMISSIONS
        admin_codes = tuple(code for code, _ in ADMIN_PERMISSIONS)

        try:
            # Run seeder once
            await _seed_admin_rbac(
                db,
                tenant_schema=sch,
                admin_email=email1,
                admin_password="TestPass1!",  # pragma: allowlist secret
                admin_full_name="Seeder3 Admin",
                permission_codes=all_permissions,
                admin_role_codes=admin_codes,
            )
            await db.commit()

            # Contaminate admin with a client:* perm
            await _ContaminationHelper.contaminate(db, sch, "admin", "client:catalog:read")
            await db.commit()
            assert "client:catalog:read" in await _ContaminationHelper.role_perms(db, sch, "admin")

            # Run seeder second time — should reconcile
            await _seed_admin_rbac(
                db,
                tenant_schema=sch,
                admin_email=email2,
                admin_password="TestPass1!",  # pragma: allowlist secret
                admin_full_name="Seeder3 Admin 2",
                permission_codes=all_permissions,
                admin_role_codes=admin_codes,
            )
            await db.commit()

            admin_perms = await _ContaminationHelper.role_perms(db, sch, "admin")
            assert admin_perms == set(ADMIN_PERMISSION_CODES), (
                f"admin not reconciled: {admin_perms ^ set(ADMIN_PERMISSION_CODES)}")
            assert "client:catalog:read" not in admin_perms

            # Third run idempotent
            await _seed_admin_rbac(
                db,
                tenant_schema=sch,
                admin_email=email1,
                admin_password="TestPass1!",  # pragma: allowlist secret
                admin_full_name="Seeder3 Admin",
                permission_codes=all_permissions,
                admin_role_codes=admin_codes,
            )
            await db.commit()
            admin_perms2 = await _ContaminationHelper.role_perms(db, sch, "admin")
            assert admin_perms2 == admin_perms, "admin fingerprint changed on re-run"

        finally:
            await _ContaminationHelper.cleanup_users(db, sch, *owned_emails)
            await _ContaminationHelper.cleanup_perms(db, sch, "client:catalog:read")
            await db.commit()

    # ------------------------------------------------------------------
    # Seeder 4: seed_demo_data._seed_rbac
    # ------------------------------------------------------------------

    async def test_seeder4_seed_demo_data(
        self, s2_clean_db
    ):
        from sqlalchemy import text
        from core.permission_registry import (
            ADMIN_PERMISSION_CODES,
            RETAILER_OPERATOR_PERMISSION_CODES,
        )
        from core.security import hash_password
        from scripts.seed_demo_data import _seed_rbac
        from tests.test_dc12r1_s2_supplier_scoped_retailer_login import _pool_instance

        db, reg = s2_clean_db
        sch = _pool_instance.tenants["a"]["schema"]
        demo_email = "admin@mpango.demo"

        try:
            # _seed_rbac expects the demo admin user to exist
            existing = (await db.execute(text(
                f'SELECT id FROM "{sch}".users WHERE email = :e'), {"e": demo_email})).scalar()
            if not existing:
                await db.execute(text(
                    f'INSERT INTO "{sch}".users (email, password_hash, full_name, is_active) '
                    "VALUES (:e, :p, :n, true) ON CONFLICT (email) DO NOTHING"),
                    {"e": demo_email, "p": hash_password("TestPass1!"), "n": "Demo Admin"})
                await db.commit()

            # Run seeder once to establish baseline
            await _seed_rbac(db, sch)
            await db.commit()

            # Contaminate: admin gets client:* perm; retailer gets admin perm; missing canonical
            await _ContaminationHelper.contaminate(db, sch, "admin", "client:catalog:read")
            await _ContaminationHelper.contaminate(db, sch, "retailer_operator", "orders:read")
            await _ContaminationHelper.strip_perm(db, sch, "retailer_operator", "client:orders:read")
            await db.commit()

            assert "client:catalog:read" in await _ContaminationHelper.role_perms(db, sch, "admin")
            assert "orders:read" in await _ContaminationHelper.role_perms(db, sch, "retailer_operator")
            assert "client:orders:read" not in await _ContaminationHelper.role_perms(db, sch, "retailer_operator")

            # Run seeder second time — should reconcile
            await _seed_rbac(db, sch)
            await db.commit()

            admin_perms = await _ContaminationHelper.role_perms(db, sch, "admin")
            retailer_perms = await _ContaminationHelper.role_perms(db, sch, "retailer_operator")

            assert admin_perms == set(ADMIN_PERMISSION_CODES), (
                f"admin not reconciled: extra={admin_perms - set(ADMIN_PERMISSION_CODES)}, "
                f"missing={set(ADMIN_PERMISSION_CODES) - admin_perms}")
            assert retailer_perms == set(RETAILER_OPERATOR_PERMISSION_CODES), (
                f"retailer not reconciled: extra={retailer_perms - set(RETAILER_OPERATOR_PERMISSION_CODES)}, "
                f"missing={set(RETAILER_OPERATOR_PERMISSION_CODES) - retailer_perms}")
            assert "client:catalog:read" not in admin_perms
            assert "orders:read" not in retailer_perms
            assert "client:orders:read" in retailer_perms

            # Third run idempotent
            await _seed_rbac(db, sch)
            await db.commit()
            admin_perms2 = await _ContaminationHelper.role_perms(db, sch, "admin")
            retailer_perms2 = await _ContaminationHelper.role_perms(db, sch, "retailer_operator")
            assert admin_perms2 == admin_perms, "admin fingerprint changed on re-run"
            assert retailer_perms2 == retailer_perms, "retailer fingerprint changed on re-run"

        finally:
            await _ContaminationHelper.cleanup_perms(db, sch, "client:catalog:read")
            await db.commit()


# ===========================================================================
# §13 R3-R1: Malformed identity HTTP route tests
# ===========================================================================


class TestMalformedIdentityHttp:
    """Registered HTTP routes with malformed ClientIdentity (wholesaler_id or
    retailer_id set to non-UUID strings) must return controlled responses
    (never 500, no internal detail leak).

    Injects malformed identity via FastAPI app.dependency_overrides to
    bypass the real resolve_client_identity — this is a test-only mechanism;
    in production the UUID columns in the binding table prevent such values.

    Zero-SQL proof is at the repository level (§11b); HTTP-level proof here
    is that no 500 or internal detail leaks through the route handler.
    """

    @staticmethod
    def _app_with_malformed_identity(
        malformed_wholesaler: bool = False,
        malformed_retailer: bool = False,
    ):
        """Build a FastAPI app where resolve_client_identity returns a
        ClientIdentity with one malformed (non-UUID) ID."""
        from unittest.mock import MagicMock
        from fastapi import FastAPI
        from api.v1.client.dependencies import ClientIdentity, resolve_client_identity
        from api.app import configure_app
        from core.config import get_settings

        tid = "not-a-uuid-tenant" if malformed_wholesaler else "550e8400-e29b-41d4-a716-446655440000"
        rid = "not-a-uuid-retailer" if malformed_retailer else "660e8400-e29b-41d4-a716-446655440000"

        app = FastAPI()
        with mock.patch("auth.factory.get_auth_strategy", return_value=JwtAuthStrategy()):
            configure_app(app, get_settings())
        register_exception_handlers(app)

        malformed = ClientIdentity(
            user_id="770e8400-e29b-41d4-a716-446655440000",
            retailer_id=rid,
            tenant_id=tid,
            token=MagicMock(),
        )
        app.dependency_overrides[resolve_client_identity] = lambda: malformed
        return app

    async def test_list_malformed_wholesaler_id(
        self, s3_client, two_tenants
    ):
        """GET /api/v1/client/orders with malformed wholesaler_id gets fail-closed."""
        token = await _login_retailer(s3_client, two_tenants)
        app = self._app_with_malformed_identity(malformed_wholesaler=True)
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            resp = await client.get("/api/v1/client/orders")
        assert resp.status_code != HTTPStatus.INTERNAL_SERVER_ERROR, resp.text
        _assert_controlled_envelope(resp, allow=(HTTPStatus.OK, HTTPStatus.NOT_FOUND, HTTPStatus.FORBIDDEN))

    async def test_detail_malformed_wholesaler_id(
        self, s3_client, two_tenants, s2_clean_db
    ):
        """GET /api/v1/client/orders/{id} with malformed wholesaler_id."""
        from tests.test_dc12r1_s2_supplier_scoped_retailer_login import _pool_instance
        db, reg = s2_clean_db
        sch = _pool_instance.tenants["a"]["schema"]
        code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ws_a = _pool_instance.tenants["a"]["ws_id"]
        ret_a = await _resolve_binding(db, ws_a, uid_a)
        sku = await _seed_sku(db, sch, ret_a)
        token = await _login_retailer(s3_client, two_tenants)
        oid = await _create_order(s3_client, token, sku)
        app = self._app_with_malformed_identity(malformed_wholesaler=True)
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            resp = await client.get(f"/api/v1/client/orders/{oid}")
        assert resp.status_code != HTTPStatus.INTERNAL_SERVER_ERROR, resp.text

    async def test_cancel_malformed_wholesaler_id(
        self, s3_client, two_tenants, s2_clean_db
    ):
        """POST /api/v1/client/orders/{id}/cancel with malformed wholesaler_id."""
        from tests.test_dc12r1_s2_supplier_scoped_retailer_login import _pool_instance
        db, reg = s2_clean_db
        sch = _pool_instance.tenants["a"]["schema"]
        code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ws_a = _pool_instance.tenants["a"]["ws_id"]
        ret_a = await _resolve_binding(db, ws_a, uid_a)
        sku = await _seed_sku(db, sch, ret_a)
        token = await _login_retailer(s3_client, two_tenants)
        oid = await _create_order(s3_client, token, sku)
        app = self._app_with_malformed_identity(malformed_wholesaler=True)
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            resp = await client.post(f"/api/v1/client/orders/{oid}/cancel")
        assert resp.status_code != HTTPStatus.INTERNAL_SERVER_ERROR, resp.text

    async def test_list_malformed_retailer_id(
        self, s3_client, two_tenants
    ):
        """GET /api/v1/client/orders with malformed retailer_id gets fail-closed."""
        token = await _login_retailer(s3_client, two_tenants)
        app = self._app_with_malformed_identity(malformed_retailer=True)
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            resp = await client.get("/api/v1/client/orders")
        assert resp.status_code != HTTPStatus.INTERNAL_SERVER_ERROR, resp.text
        _assert_controlled_envelope(resp, allow=(HTTPStatus.OK, HTTPStatus.NOT_FOUND, HTTPStatus.FORBIDDEN))

    async def test_detail_malformed_retailer_id(
        self, s3_client, two_tenants, s2_clean_db
    ):
        """GET /api/v1/client/orders/{id} with malformed retailer_id."""
        from tests.test_dc12r1_s2_supplier_scoped_retailer_login import _pool_instance
        db, reg = s2_clean_db
        sch = _pool_instance.tenants["a"]["schema"]
        code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ws_a = _pool_instance.tenants["a"]["ws_id"]
        ret_a = await _resolve_binding(db, ws_a, uid_a)
        sku = await _seed_sku(db, sch, ret_a)
        token = await _login_retailer(s3_client, two_tenants)
        oid = await _create_order(s3_client, token, sku)
        app = self._app_with_malformed_identity(malformed_retailer=True)
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            resp = await client.get(f"/api/v1/client/orders/{oid}")
        assert resp.status_code != HTTPStatus.INTERNAL_SERVER_ERROR, resp.text

    async def test_cancel_malformed_retailer_id(
        self, s3_client, two_tenants, s2_clean_db
    ):
        """POST /api/v1/client/orders/{id}/cancel with malformed retailer_id."""
        from tests.test_dc12r1_s2_supplier_scoped_retailer_login import _pool_instance
        db, reg = s2_clean_db
        sch = _pool_instance.tenants["a"]["schema"]
        code_a, _b, _sb, _e, _p, uid_a, _ub = two_tenants
        ws_a = _pool_instance.tenants["a"]["ws_id"]
        ret_a = await _resolve_binding(db, ws_a, uid_a)
        sku = await _seed_sku(db, sch, ret_a)
        token = await _login_retailer(s3_client, two_tenants)
        oid = await _create_order(s3_client, token, sku)
        app = self._app_with_malformed_identity(malformed_retailer=True)
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            resp = await client.post(f"/api/v1/client/orders/{oid}/cancel")
        assert resp.status_code != HTTPStatus.INTERNAL_SERVER_ERROR, resp.text
