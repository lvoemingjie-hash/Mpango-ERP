"""MPANGO-ORDER-STATE-AUTHORITY-D1 matrix group 4 — whole-request rollback.

Real HTTP surface: when the state write or its inventory side effect fails
mid-request, NOTHING of that request may persist (the tenant-context
middleware owns the single whole-request transaction; endpoint-level
``db.rollback()`` and the middleware status>=400 rollback must agree).

- Confirm against insufficient available stock: 409 INSUFFICIENT_AVAILABLE_
  STOCK; order stays draft; zero reservations; zero aggregate reserved;
  zero movements; zero ledger.
- Fulfill against on-hand reduced below the reserved quantity after
  confirmation: 409 INSUFFICIENT_STOCK; order stays PAID (the FULFILLED
  status write made by OrderService.transition inside the same request is
  rolled back); reservations stay reserved-but-intact; no deduction
  movement.
- Pay above the remaining balance: 400 PAYMENT_EXCEEDS_REMAINING; status
  unchanged; zero payment rows; zero ledger.

Helper negative control: the residue oracle must actually fire when a row
is planted (a checker that cannot detect residue is not evidence).
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from http import HTTPStatus
from sqlalchemy import text

from tests.order_state_d1.support import (
    bound_retailer,
    make_tenant_cashier,
    fetch_order_state,
    fetch_payment_ledger_facts,
    fetch_reservation_facts,
    http_action,
    http_create_wholesaler_order,
    osd1_cashier_token,
    seed_sku_with_stock,
)

pytestmark = pytest.mark.asyncio


def _errcode(resp) -> str:
    body = resp.json()
    detail = body.get("detail") or body.get("error") or {}
    return (detail.get("code") or body.get("code") or "")


async def _movement_count(db, schema: str, oid) -> int:
    return int((await db.execute(text(
        f'SELECT count(*) FROM "{schema}".inventory_movements '
        "WHERE reference_id = :oid"), {"oid": oid}
    )).scalar_one())


async def test_confirm_insufficient_stock_rolls_back_whole_request(
    osd1_client, s2_clean_db, provisioned_pool, osd1_cashier
):
    db, reg = s2_clean_db
    token = await osd1_cashier_token(osd1_client, osd1_cashier)
    async with bound_retailer(db, provisioned_pool, reg) as (ret_id, schema, _ws):
        sku, sid = await seed_sku_with_stock(db, schema, ret_id, quantity=10)
        order = await http_create_wholesaler_order(osd1_client, token, ret_id, sku, 5)
        oid = order["id"]

        # shrink available stock below the ordered quantity AFTER creation
        ext = await _second_session(schema)
        try:
            await ext.execute(text(
                f'UPDATE "{schema}".inventory_stocks SET quantity_on_hand = 3 '
                "WHERE sku_id = :s"), {"s": sid})
            await ext.commit()
        finally:
            await ext.close()
        await db.rollback()

        resp = await http_action(osd1_client, token, oid, "confirm")
        assert resp.status_code == HTTPStatus.CONFLICT, resp.text
        assert _errcode(resp) == "INSUFFICIENT_AVAILABLE_STOCK", resp.text

        state = await fetch_order_state(db, schema, oid)
        assert state["status"] == "draft", state
        facts = await fetch_reservation_facts(db, schema, oid)
        assert facts["rows"] == [], facts
        reserved = (await db.execute(text(
            f'SELECT quantity_reserved FROM "{schema}".inventory_stocks '
            "WHERE sku_id = :s"), {"s": sid}
        )).scalar_one()
        assert Decimal(str(reserved)) == Decimal("0")
        assert await _movement_count(db, schema, oid) == 0
        money = await fetch_payment_ledger_facts(db, schema, oid)
        assert money["payments"] == [] and money["ledger"] == []


async def test_fulfill_insufficient_stock_rolls_back_transition_too(
    osd1_client, s2_clean_db, provisioned_pool, osd1_cashier
):
    db, reg = s2_clean_db
    token = await osd1_cashier_token(osd1_client, osd1_cashier)
    async with bound_retailer(db, provisioned_pool, reg) as (ret_id, schema, _ws):
        sku, sid = await seed_sku_with_stock(db, schema, ret_id, quantity=10, price="20.00")
        order = await http_create_wholesaler_order(osd1_client, token, ret_id, sku, 4)
        oid = order["id"]
        assert (await http_action(osd1_client, token, oid, "confirm")).status_code == 200
        pay = await http_action(osd1_client, token, oid, "pay",
                                {"amount": 80.00, "method": "cash"})
        assert pay.status_code == 200, pay.text

        # External shrink below the reserved quantity (damage/adjustment).
        # Keep reservations intact so only the deduction step fails.
        ext = await _second_session(schema)
        try:
            await ext.execute(text(
                f'UPDATE "{schema}".inventory_stocks SET quantity_on_hand = 1 '
                "WHERE sku_id = :s"), {"s": sid})
            await ext.commit()
        finally:
            await ext.close()
        await db.rollback()  # refresh snapshot for the assertions below

        resp = await http_action(osd1_client, token, oid, "fulfill")
        assert resp.status_code == HTTPStatus.CONFLICT, resp.text
        assert _errcode(resp) == "INSUFFICIENT_STOCK", resp.text

        state = await fetch_order_state(db, schema, oid)
        assert state["status"] == "paid", (
            f"FULFILLED write from the failed request must roll back: {state}")
        facts = await fetch_reservation_facts(db, schema, oid)
        assert facts["reserved_rows"] == 1 and facts["rows"][0]["status"] == "reserved"
        assert await _movement_count(db, schema, oid) == 0


async def test_pay_over_remaining_rolls_back_payment_row(
    osd1_client, s2_clean_db, provisioned_pool, osd1_cashier
):
    db, reg = s2_clean_db
    token = await osd1_cashier_token(osd1_client, osd1_cashier)
    async with bound_retailer(db, provisioned_pool, reg) as (ret_id, schema, _ws):
        sku, _sid = await seed_sku_with_stock(db, schema, ret_id, price="30.00")
        order = await http_create_wholesaler_order(osd1_client, token, ret_id, sku, 2)
        oid = order["id"]
        assert (await http_action(osd1_client, token, oid, "confirm")).status_code == 200

        resp = await http_action(osd1_client, token, oid, "pay",
                                 {"amount": 999.00, "method": "cash"})
        assert resp.status_code == HTTPStatus.BAD_REQUEST, resp.text
        assert _errcode(resp) == "PAYMENT_EXCEEDS_REMAINING", resp.text

        state = await fetch_order_state(db, schema, oid)
        assert state["status"] == "confirmed"
        money = await fetch_payment_ledger_facts(db, schema, oid)
        assert money["payments"] == [] and money["ledger"] == []


async def test_residue_oracle_negative_control_fires_on_planted_row(
    osd1_client, s2_clean_db, provisioned_pool, osd1_cashier
):
    """Duplicate-effect negative control for the residue oracle: plant one
    reserved row on a cancelled order; ``assert_no_orphan_reservations``
    MUST fail. A silent oracle would make every rollback claim above
    unfalsifiable."""
    from tests.order_state_d1.support import assert_no_orphan_reservations

    db, reg = s2_clean_db
    token = await osd1_cashier_token(osd1_client, osd1_cashier)
    async with bound_retailer(db, provisioned_pool, reg) as (ret_id, schema, _ws):
        sku, sid = await seed_sku_with_stock(db, schema, ret_id)
        order = await http_create_wholesaler_order(osd1_client, token, ret_id, sku, 1)
        oid = order["id"]
        assert (await http_action(osd1_client, token, oid, "cancel")).status_code == 200

        # positive control first: clean cancel passes
        await assert_no_orphan_reservations(db, schema, oid, expect_status="cancelled")

        # plant the duplicate residue the oracle must catch
        ext = await _second_session(schema)
        try:
            await ext.execute(text(
                f'INSERT INTO "{schema}".inventory_reservations '
                "(order_id, order_item_id, sku_id, sku_code, quantity, status, reference_type, reference_id) "
                "SELECT :oid, oi.id, :sid, oi.sku_code, 1, 'reserved', 'order', :oid "
                f'FROM "{schema}".order_items oi WHERE oi.order_id = :oid LIMIT 1'
            ), {"oid": oid, "sid": sid})
            await ext.commit()
        finally:
            await ext.close()
        await db.rollback()

        with pytest.raises(AssertionError, match="orphan reservations"):
            await assert_no_orphan_reservations(db, schema, oid, expect_status="cancelled")



async def _second_session(schema: str):
    """A second tenant-bound session for external (out-of-request) writes."""
    from database.session import AsyncSessionLocal

    session = AsyncSessionLocal()
    session.info["tenant_schema"] = schema
    await session.execute(text(f'SET search_path TO "{schema}", public'))
    return session


# ---------------------------------------------------------------------------
# R1 additions: unknown-exception rollback + notification suppression +
# permission-denied / cross-tenant controls (Codex-L finding 3)
# ---------------------------------------------------------------------------


async def test_unknown_exception_after_state_write_rolls_back_everything(
    osd1_client, s2_clean_db, provisioned_pool, osd1_cashier, monkeypatch
):
    """A NON-domain exception (RuntimeError) injected AFTER the FULFILLED
    status write and reservation consumption, during deduction, must roll
    back the WHOLE request: status stays paid, reservations stay reserved,
    zero movements, zero ledger, and NO success notification may observe the
    uncommitted state (CTO: 未知异常不得提交，回滚请求不得携带成功事实)."""
    db, reg = s2_clean_db
    token = await osd1_cashier_token(osd1_client, osd1_cashier)
    async with bound_retailer(db, provisioned_pool, reg) as (ret_id, schema, _ws):
        sku, sid = await seed_sku_with_stock(db, schema, ret_id, quantity=10, price="20.00")
        order = await http_create_wholesaler_order(osd1_client, token, ret_id, sku, 4)
        oid = order["id"]
        assert (await http_action(osd1_client, token, oid, "confirm")).status_code == 200
        pay = await http_action(osd1_client, token, oid, "pay",
                                {"amount": 80.00, "method": "cash"})
        assert pay.status_code == 200, pay.text

        notification_calls: list[str] = []
        from services import notification_service as ns_module

        real_sms = ns_module.notification_service.send_sms

        async def counting_sms(*args, **kwargs):
            notification_calls.append("sms")
            return await real_sms(*args, **kwargs)

        monkeypatch.setattr(ns_module.notification_service, "send_sms", counting_sms)

        from services import inventory_service as inv_module
        from services.inventory_service import InventoryService

        real_deduct = InventoryService.deduct_on_fulfillment

        async def exploding_deduct(self, db_, **kwargs):
            # state write + reservation consumption already flushed by the
            # service transition above; now blow up with a NON-domain error
            raise RuntimeError("OSD1 fault injection after state writes")

        monkeypatch.setattr(InventoryService, "deduct_on_fulfillment", exploding_deduct)

        # ASGITransport surfaces non-HTTP exceptions to the caller (a real
        # uvicorn server would translate them to a 500); the rollback truth
        # is read from the database below either way.
        with pytest.raises(RuntimeError, match="OSD1 fault injection"):
            await http_action(osd1_client, token, oid, "fulfill")

        state = await fetch_order_state(db, schema, oid)
        facts = await fetch_reservation_facts(db, schema, oid)
        money = await fetch_payment_ledger_facts(db, schema, oid)
        movements = await _movement_count(db, schema, oid)

        # facts first; contract assertions carry them on failure
        assert state["status"] == "paid", (
            f"RED_OR_DEFECT: FULFILLED write survived a fault-injected "
            f"request: state={state} facts={facts} money={money}")
        assert facts["reserved_rows"] == 1 and facts["rows"][0]["status"] == "reserved", facts
        assert movements == 0
        assert money["payments"][0]["status"] in {"completed", "pending"}, money

        # CTO contract: a rolled-back request must not emit success facts
        assert notification_calls == [], (
            f"RED: fulfill SMS dispatched inside the transaction that later "
            f"rolled back (success fact before commit): {notification_calls}")


async def test_confirm_permission_denied_control(
    osd1_client, s2_clean_db, provisioned_pool, osd1_cashier
):
    """Minimal permission control: a valid JWT WITHOUT orders:update must be
    denied before any state write (403), leaving the order draft."""
    from tests.test_dc12r1_s2_supplier_scoped_retailer_login import (
        _create_retailer_user,
        _grant_retailer_operator,
        _TWO_TENANT_PW,
    )

    db, reg = s2_clean_db
    a = provisioned_pool.tenants["a"]
    uid = await _create_retailer_user(db, tenant_schema=a["schema"],
                                      email="osd1.rbac@example.com",
                                      password=_TWO_TENANT_PW, registry=reg)
    await _grant_retailer_operator(db, tenant_schema=a["schema"], user_id=uid)

    resp = await osd1_client.post("/api/v1/auth/login",
                                  json={"email": "osd1.rbac@example.com",
                                        "password": _TWO_TENANT_PW})
    assert resp.status_code == 200, resp.text
    identity_token = resp.json()["data"]["access_token"]
    sel = await osd1_client.post("/api/v1/auth/select-tenant",
                                 json={"tenant_id": a["ws_id"]},
                                 headers={"Authorization": f"Bearer {identity_token}"})
    assert sel.status_code == 200, sel.text
    limited_token = sel.json()["data"]["access_token"]

    admin_token = await osd1_cashier_token(osd1_client, osd1_cashier)
    async with bound_retailer(db, provisioned_pool, reg) as (ret_id, schema, _ws):
        sku, _sid = await seed_sku_with_stock(db, schema, ret_id)
        order = await http_create_wholesaler_order(osd1_client, admin_token, ret_id, sku, 1)
        oid = order["id"]

        denied = await http_action(osd1_client, limited_token, oid, "confirm")
        assert denied.status_code in (HTTPStatus.FORBIDDEN, HTTPStatus.UNAUTHORIZED), (
            f"RBAC did not deny orders:update-less token: {denied.status_code} {denied.text}")

        state = await fetch_order_state(db, schema, oid)
        assert state["status"] == "draft", state


async def test_confirm_cross_tenant_isolation_control(
    osd1_client, s2_clean_db, provisioned_pool, osd1_cashier
):
    """Minimal cross-tenant control: tenant B's valid token cannot confirm
    tenant A's order (schema-scoped session) — clean 404, order untouched."""
    db, reg = s2_clean_db
    token_a = await osd1_cashier_token(osd1_client, osd1_cashier)
    async with bound_retailer(db, provisioned_pool, reg) as (ret_id, schema, _ws):
        sku, _sid = await seed_sku_with_stock(db, schema, ret_id)
        order = await http_create_wholesaler_order(osd1_client, token_a, ret_id, sku, 1)
        oid = order["id"]

        # a REAL tenant-B cashier via the canonical owner lifecycle
        b_cashier = await make_tenant_cashier(
            db, reg, provisioned_pool.tenants["b"])
        b_token = await osd1_cashier_token(osd1_client, b_cashier)

        resp = await http_action(osd1_client, b_token, oid, "confirm")
        assert resp.status_code == HTTPStatus.NOT_FOUND, (
            f"cross-tenant confirm must be schema-blind 404: {resp.status_code} {resp.text}")

        state = await fetch_order_state(db, schema, oid)
        assert state["status"] == "draft", state
