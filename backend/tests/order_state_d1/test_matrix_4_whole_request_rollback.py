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
