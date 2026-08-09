"""DC-12R1-S3-S2: Read-only retailer payment and finance visibility.

Proves the client financial surface is strictly read-only and scoped by the
server-resolved supplier/retailer relationship.
"""
from __future__ import annotations

import uuid
from http import HTTPStatus
from unittest import mock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, text

from api.app import configure_app
from auth.strategies.jwt import JwtAuthStrategy
from core.config import get_settings
from core.error_codes import register_exception_handlers
from tests.test_dc12r1_s2_supplier_scoped_retailer_login import (  # noqa: E402
    _TWO_TENANT_PW,
    _create_binding,
    _create_retailer,
    _create_retailer_user,
    _grant_retailer_operator,
    provisioned_pool,
    s2_clean_db,
    two_tenants,
)
from tests.test_dc12r1_s3_s1_catalog_order_hardening import (  # noqa: E402
    _assert_controlled_envelope,
    _login_code,
    _login_retailer,
    _resolve_binding,
)

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(autouse=True)
async def _reset_shared_engine_pool():
    from database.session import async_engine

    yield
    await async_engine.dispose()


@pytest_asyncio.fixture
async def s3_s2_client():
    app = FastAPI()
    with mock.patch("auth.factory.get_auth_strategy", return_value=JwtAuthStrategy()):
        configure_app(app, get_settings())
    register_exception_handlers(app)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as ac:
        yield ac


async def _seed_order(db, schema: str, *, wholesaler_id: str, retailer_id: str, total="100.00", deleted=False) -> str:
    order_id = uuid.uuid4()
    await db.execute(
        text(
            f'INSERT INTO "{schema}".orders '
            "(id, wholesaler_id, retailer_id, status, total_amount, notes, is_deleted) "
            "VALUES (:id, :ws, :ret, 'confirmed', :total, 's3-s2', :deleted)"
        ),
        {"id": order_id, "ws": wholesaler_id, "ret": retailer_id, "total": total, "deleted": deleted},
    )
    return str(order_id)


async def _seed_payment(
    db,
    schema: str,
    *,
    order_id: str,
    retailer_id: str,
    amount="25.00",
    method="cash",
    status="completed",
    deleted=False,
) -> str:
    payment_id = uuid.uuid4()
    await db.execute(
        text(
            f'INSERT INTO "{schema}".payments '
            "(id, order_id, retailer_id, transaction_id, idempotency_key, amount, method, status, is_deleted) "
            "VALUES (:id, :order_id, :retailer_id, :tx, :ik, :amount, :method, :status, :deleted)"
        ),
        {
            "id": payment_id,
            "order_id": order_id,
            "retailer_id": retailer_id,
            "tx": f"TX-{payment_id.hex[:10]}",
            "ik": f"IK-{payment_id.hex[:10]}",
            "amount": amount,
            "method": method,
            "status": status,
            "deleted": deleted,
        },
    )
    return str(payment_id)


async def _set_balance(db, *, wholesaler_id: str, retailer_id: str, balance: str, deleted=False, active=True):
    await db.execute(
        text(
            "UPDATE public.wholesaler_retailer_bindings "
            "SET outstanding_balance = :balance, is_deleted = :deleted, status = :status "
            "WHERE wholesaler_id = :ws AND retailer_id = :ret"
        ),
        {
            "balance": balance,
            "deleted": deleted,
            "status": "active" if active else "inactive",
            "ws": wholesaler_id,
            "ret": retailer_id,
        },
    )


def _visible_payment_fields(item: dict) -> set[str]:
    return {"id", "order_id", "amount", "method", "status", "created_at"} & set(item)


class TestReadOnlyClientFinanceHappyPath:
    async def test_relationship_a_sees_only_a_payments_and_balance(self, s3_s2_client, two_tenants, s2_clean_db):
        from tests.test_dc12r1_s2_supplier_scoped_retailer_login import _pool_instance

        db, _reg = s2_clean_db
        code_a, code_b, _sb, email, password, uid_a, uid_b = two_tenants
        ws_a = _pool_instance.tenants["a"]["ws_id"]
        ws_b = _pool_instance.tenants["b"]["ws_id"]
        sch_a = _pool_instance.tenants["a"]["schema"]
        sch_b = _pool_instance.tenants["b"]["schema"]
        ret_a = await _resolve_binding(db, ws_a, uid_a)
        ret_b = await _resolve_binding(db, ws_b, uid_b)

        order_a = await _seed_order(db, sch_a, wholesaler_id=ws_a, retailer_id=ret_a)
        pay_a = await _seed_payment(db, sch_a, order_id=order_a, retailer_id=ret_a, amount="75.50", method="credit")
        order_b = await _seed_order(db, sch_b, wholesaler_id=ws_b, retailer_id=ret_b)
        pay_b = await _seed_payment(db, sch_b, order_id=order_b, retailer_id=ret_b, amount="12.00")
        await _set_balance(db, wholesaler_id=ws_a, retailer_id=ret_a, balance="345.67")
        await _set_balance(db, wholesaler_id=ws_b, retailer_id=ret_b, balance="999.99")
        await db.commit()

        token_a = await _login_code(s3_s2_client, code_a, email, password)
        resp = await s3_s2_client.get("/api/v1/client/payments", headers={"Authorization": f"Bearer {token_a}"})
        assert resp.status_code == HTTPStatus.OK, resp.text
        items = resp.json()["data"]["items"]
        assert [item["id"] for item in items] == [pay_a]
        assert pay_b not in {item["id"] for item in items}
        assert items[0]["method"] == "credit"
        assert set(items[0]) == _visible_payment_fields(items[0])

        balance = await s3_s2_client.get("/api/v1/client/finance/balance", headers={"Authorization": f"Bearer {token_a}"})
        assert balance.status_code == HTTPStatus.OK, balance.text
        assert balance.json()["data"]["outstanding_balance"] == "345.67"
        assert balance.json()["data"]["has_outstanding_balance"] is True
        assert "retailer_id" not in balance.json()["data"]
        assert "wholesaler_id" not in balance.json()["data"]


class TestReadOnlyClientFinanceIsolation:
    async def test_same_schema_wrong_rows_and_deleted_rows_are_excluded(self, s3_s2_client, two_tenants, s2_clean_db):
        from tests.test_dc12r1_s2_supplier_scoped_retailer_login import _pool_instance

        db, reg = s2_clean_db
        code_a, _b, _sb, _email, _password, uid_a, _uid_b = two_tenants
        ws_a = _pool_instance.tenants["a"]["ws_id"]
        sch_a = _pool_instance.tenants["a"]["schema"]
        ret_a = await _resolve_binding(db, ws_a, uid_a)
        foreign_ret = await _create_retailer(db, name="S3S2Foreign", registry=reg)
        foreign_uid = await _create_retailer_user(db, tenant_schema=sch_a, email=f"s3s2_{uuid.uuid4().hex[:8]}@x.com", password=_TWO_TENANT_PW, registry=reg)
        await _grant_retailer_operator(db, tenant_schema=sch_a, user_id=foreign_uid)
        await _create_binding(db, wholesaler_id=ws_a, retailer_id=foreign_ret, tenant_user_id=foreign_uid, registry=reg)

        visible_order = await _seed_order(db, sch_a, wholesaler_id=ws_a, retailer_id=ret_a)
        visible = await _seed_payment(db, sch_a, order_id=visible_order, retailer_id=ret_a, amount="11.00")
        wrong_retailer_order = await _seed_order(db, sch_a, wholesaler_id=ws_a, retailer_id=str(foreign_ret))
        wrong_retailer = await _seed_payment(db, sch_a, order_id=wrong_retailer_order, retailer_id=str(foreign_ret), amount="22.00")
        wrong_ws_order = await _seed_order(db, sch_a, wholesaler_id=str(uuid.uuid4()), retailer_id=ret_a)
        wrong_ws = await _seed_payment(db, sch_a, order_id=wrong_ws_order, retailer_id=ret_a, amount="33.00")
        deleted_order = await _seed_order(db, sch_a, wholesaler_id=ws_a, retailer_id=ret_a, deleted=True)
        deleted_order_payment = await _seed_payment(db, sch_a, order_id=deleted_order, retailer_id=ret_a, amount="44.00")
        deleted_payment = await _seed_payment(db, sch_a, order_id=visible_order, retailer_id=ret_a, amount="55.00", deleted=True)
        await db.commit()

        token = await _login_retailer(s3_s2_client, two_tenants)
        resp = await s3_s2_client.get("/api/v1/client/payments", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == HTTPStatus.OK, resp.text
        ids = {item["id"] for item in resp.json()["data"]["items"]}
        assert visible in ids
        assert {wrong_retailer, wrong_ws, deleted_order_payment, deleted_payment}.isdisjoint(ids)

    async def test_deleted_binding_blocks_balance_and_payments(self, s3_s2_client, two_tenants, s2_clean_db):
        from tests.test_dc12r1_s2_supplier_scoped_retailer_login import _pool_instance

        db, _reg = s2_clean_db
        _code_a, _b, _sb, _email, _password, uid_a, _uid_b = two_tenants
        ws_a = _pool_instance.tenants["a"]["ws_id"]
        ret_a = await _resolve_binding(db, ws_a, uid_a)
        token = await _login_retailer(s3_s2_client, two_tenants)
        await _set_balance(db, wholesaler_id=ws_a, retailer_id=ret_a, balance="1.00", deleted=True)
        await db.commit()

        for path in ("/api/v1/client/payments", "/api/v1/client/finance/balance"):
            resp = await s3_s2_client.get(path, headers={"Authorization": f"Bearer {token}"})
            _assert_controlled_envelope(resp)
            assert resp.status_code == HTTPStatus.FORBIDDEN


class TestReadOnlyClientFinanceDeniedBeforeFinancialSql:
    async def test_missing_permission_returns_403_before_financial_sql(self, s3_s2_client, two_tenants, s2_clean_db):
        from database.session import async_engine
        from tests.test_dc12r1_s2_supplier_scoped_retailer_login import _pool_instance

        db, _reg = s2_clean_db
        sch_a = _pool_instance.tenants["a"]["schema"]
        try:
            await db.execute(text(f'DELETE FROM "{sch_a}".role_permissions rp USING "{sch_a}".permissions p, "{sch_a}".roles r WHERE rp.permission_id = p.id AND rp.role_id = r.id AND r.name = \'retailer_operator\' AND p.code IN (\'client:payments:read\', \'client:finance:read\')'))
            await db.commit()
            token = await _login_retailer(s3_s2_client, two_tenants)
            captured: list[str] = []

            def _cap(_conn, _cursor, statement, _parameters, _context, _executemany):
                captured.append(statement)

            event.listen(async_engine.sync_engine, "before_cursor_execute", _cap)
            try:
                for path in ("/api/v1/client/payments", "/api/v1/client/finance/balance"):
                    resp = await s3_s2_client.get(path, headers={"Authorization": f"Bearer {token}"})
                    _assert_controlled_envelope(resp)
                    assert resp.status_code == HTTPStatus.FORBIDDEN
            finally:
                event.remove(async_engine.sync_engine, "before_cursor_execute", _cap)
            financial_sql = [s for s in captured if " payments" in s.lower() or " orders" in s.lower()]
            assert not financial_sql
        finally:
            for code in ("client:payments:read", "client:finance:read"):
                await db.execute(text(
                    f'INSERT INTO "{sch_a}".role_permissions (role_id, permission_id) '
                    f'SELECT r.id, p.id FROM "{sch_a}".roles r, "{sch_a}".permissions p '
                    "WHERE r.name = 'retailer_operator' AND p.code = :code "
                    "AND NOT EXISTS (SELECT 1 FROM "
                    f'"{sch_a}".role_permissions rp WHERE rp.role_id = r.id AND rp.permission_id = p.id)'
                ), {"code": code})
            await db.commit()

    async def test_malformed_identity_and_filter_are_controlled_with_zero_financial_sql(self, s3_s2_client, two_tenants):
        from api.v1.client.dependencies import ClientIdentity, resolve_client_identity
        from database.session import async_engine

        token = await _login_retailer(s3_s2_client, two_tenants)
        app = FastAPI()
        with mock.patch("auth.factory.get_auth_strategy", return_value=JwtAuthStrategy()):
            configure_app(app, get_settings())
        register_exception_handlers(app)
        captured: list[str] = []

        def _cap(_conn, _cursor, statement, _parameters, _context, _executemany):
            captured.append(statement)

        event.listen(async_engine.sync_engine, "before_cursor_execute", _cap)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
                app.dependency_overrides[resolve_client_identity] = lambda: ClientIdentity(
                    user_id="770e8400-e29b-41d4-a716-446655440000",
                    retailer_id="660e8400-e29b-41d4-a716-446655440000",
                    tenant_id="550e8400-e29b-41d4-a716-446655440000",
                    token=mock.MagicMock(),
                )
                bad_filter = await client.get(
                    "/api/v1/client/payments?order_id=not-a-uuid",
                    headers={"Authorization": f"Bearer {token}"},
                )
                blank_filters = []
                for blank_path in (
                    "/api/v1/client/payments?order_id=",
                    "/api/v1/client/payments?order_id=%20%20",
                    "/api/v1/client/payments?method=",
                    "/api/v1/client/payments?method=%20",
                    "/api/v1/client/payments?status=",
                    "/api/v1/client/payments?status=%20",
                ):
                    blank_filters.append(
                        await client.get(blank_path, headers={"Authorization": f"Bearer {token}"})
                    )
                app.dependency_overrides[resolve_client_identity] = lambda: ClientIdentity(
                    user_id="770e8400-e29b-41d4-a716-446655440000",
                    retailer_id="not-a-uuid",
                    tenant_id="550e8400-e29b-41d4-a716-446655440000",
                    token=mock.MagicMock(),
                )
                bad_identity = await client.get(
                    "/api/v1/client/finance/balance",
                    headers={"Authorization": f"Bearer {token}"},
                )
        finally:
            event.remove(async_engine.sync_engine, "before_cursor_execute", _cap)
        assert bad_filter.status_code == HTTPStatus.BAD_REQUEST
        for resp in blank_filters:
            _assert_controlled_envelope(resp, allow=(HTTPStatus.BAD_REQUEST,))
            assert resp.status_code == HTTPStatus.BAD_REQUEST
        assert bad_identity.status_code == HTTPStatus.BAD_REQUEST
        assert not [s for s in captured if "payments" in s.lower() or "orders" in s.lower() or "wholesaler_retailer_bindings" in s.lower()]


class TestReadOnlyClientFinanceRoutePolicy:
    async def test_exact_registered_client_route_inventory_is_11_and_get_only_financial_routes(self):
        from api.middleware.rbac import RequirePermission

        app = FastAPI()
        with mock.patch("auth.factory.get_auth_strategy", return_value=JwtAuthStrategy()):
            configure_app(app, get_settings())

        actual: dict[tuple[str, str], str | None] = {}
        for route in app.routes:
            if not isinstance(route, APIRoute) or not route.path.startswith("/api/v1/client"):
                continue
            perm = None
            for dep in route.dependant.dependencies:
                call = getattr(dep, "call", None)
                if isinstance(call, RequirePermission):
                    perm = call.permission
            for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
                actual[(method, route.path)] = perm

        assert len(actual) == 18
        assert actual[("GET", "/api/v1/client/payments")] == "client:payments:read"
        assert actual[("GET", "/api/v1/client/finance/balance")] == "client:finance:read"
        assert not [key for key in actual if key[1].startswith("/api/v1/client/payments") and key[0] != "GET"]
        assert not [key for key in actual if key[1].startswith("/api/v1/client/finance") and key[0] != "GET"]
        assert "client:payments:create" not in set(actual.values())
        # DC-12R1-S3-S2B-I2B: new declaration/statement routes (+4 client routes).
        assert actual[("POST", "/api/v1/client/orders/{order_id}/declare")] == "client:payments:declare"
        assert actual[("GET", "/api/v1/client/declarations")] == "client:payments:read"
        assert actual[("GET", "/api/v1/client/declarations/{declaration_id}")] == "client:payments:read"
        assert actual[("GET", "/api/v1/client/statements")] == "client:payments:read"
        # DC-12R1-S3-S2B-I2C-I1: printable records (+3 client GET routes).
        assert actual[("GET", "/api/v1/client/orders/{order_id}/print")] == "client:orders:read"
        assert actual[("GET", "/api/v1/client/declarations/{declaration_id}/print")] == "client:payments:read"
        assert actual[("GET", "/api/v1/client/declarations/{declaration_id}/receipt")] == "client:payments:read"

    async def test_generic_wholesaler_payment_and_finance_routes_remain_denied(self, s3_s2_client, two_tenants):
        token = await _login_retailer(s3_s2_client, two_tenants)
        for path in ("/api/v1/payments", "/api/v1/finance/receivables"):
            resp = await s3_s2_client.get(path, headers={"Authorization": f"Bearer {token}"})
            _assert_controlled_envelope(resp)
            assert resp.status_code == HTTPStatus.FORBIDDEN
