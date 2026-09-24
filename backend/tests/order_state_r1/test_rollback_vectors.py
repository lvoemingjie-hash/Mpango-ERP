"""R1 rollback vectors: a fault after the state write AND a fault during
the SECOND per-item inventory write must roll the whole request back to
the exact before-vector (state, reservations, stock, movements, ledger,
payments). The second case covers PARTIAL per-item inventory writes."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi import HTTPException
from http import HTTPStatus
from sqlalchemy import text

from tests.order_state_r1.support import (
    _second_session,
    http_action,
    http_create_order,
    inventory_vector,
    make_bound_retailer,
    movement_count,
    order_vector,
    osd1_cashier_token,
    payment_ledger_vector,
    reservation_vector,
    seed_sku_with_stock,
)

pytestmark = pytest.mark.asyncio


def _errcode(resp) -> str:
    body = resp.json()
    detail = body.get("detail") or body.get("error") or {}
    return detail.get("code") or body.get("code") or ""


async def test_confirm_insufficient_stock_rolls_back_to_before_vector(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity
):
    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    ret_id, schema, ws_id = await make_bound_retailer(db, provisioned_pool, reg)
    sku, sid = await seed_sku_with_stock(db, schema, ret_id, quantity=10)
    oid = await http_create_order(r1_client, token, ret_id,
                                  [{"sku_code": sku, "quantity": 5}])
    balance_before = Decimal("0")

    # shrink below the ordered quantity AFTER creation (snapshot read done)
    ext = await _second_session(schema, ws_id)
    try:
        await ext.execute(text(
            f'UPDATE "{schema}".inventory_stocks SET quantity_on_hand = 3 '
            "WHERE sku_id = :s"), {"s": sid})
        await ext.commit()
    finally:
        await ext.close()
    await db.rollback()

    resp = await http_action(r1_client, token, oid, "confirm")
    assert resp.status_code == HTTPStatus.CONFLICT, resp.text
    assert _errcode(resp) == "INSUFFICIENT_AVAILABLE_STOCK", resp.text

    state = await order_vector(db, schema, oid)
    assert state == {"exists": True, "status": "draft",
                     "total_amount": state["total_amount"]}
    assert await reservation_vector(db, schema, oid) == []
    assert (await inventory_vector(db, schema, [sid]))[sid] == "3/0"
    assert await movement_count(db, schema, oid) == 0
    money = await payment_ledger_vector(db, schema, oid)
    assert money["payments"] == [] and money["ledger"] == []


async def test_fulfill_fault_during_second_item_write_rolls_back_all(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity, monkeypatch
):
    """Two-SKU order; the deduction of the FIRST item succeeds and the
    SECOND item's write raises a non-domain error. The whole request must
    roll back to the exact before-vector: status paid, both reservations
    reserved, on-hand untouched, zero movements, payment/ledger intact."""
    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    ret_id, schema, _ws = await make_bound_retailer(db, provisioned_pool, reg)
    sku_a, sid_a = await seed_sku_with_stock(db, schema, ret_id, quantity=10, price="10.00")
    sku_b, sid_b = await seed_sku_with_stock(db, schema, ret_id, quantity=10, price="20.00")
    oid = await http_create_order(r1_client, token, ret_id,
                                  [{"sku_code": sku_a, "quantity": 2},
                                   {"sku_code": sku_b, "quantity": 3}])
    assert (await http_action(r1_client, token, oid, "confirm")).status_code == 200
    pay = await http_action(r1_client, token, oid, "pay",
                            {"amount": 80.00, "method": "cash"})
    assert pay.status_code == 200, pay.text

    before = {
        "state": await order_vector(db, schema, oid),
        "inventory": await inventory_vector(db, schema, [sid_a, sid_b]),
        "reservations": await reservation_vector(db, schema, oid),
        "movements": await movement_count(db, schema, oid),
        "money": await payment_ledger_vector(db, schema, oid),
    }
    assert before["state"]["status"] == "paid"
    assert len(before["reservations"]) == 2
    assert before["movements"] == 0

    from services.inventory_service import InventoryService

    real_deduct = InventoryService.deduct_on_fulfillment
    calls = {"n": 0}

    async def failing_second_deduct(self, db_, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return await real_deduct(self, db_, **kwargs)  # first item commits
        raise RuntimeError("R1 fault during second per-item inventory write")

    monkeypatch.setattr(InventoryService, "deduct_on_fulfillment",
                        failing_second_deduct)

    with pytest.raises(RuntimeError, match="second per-item inventory write"):
        # ASGITransport surfaces non-HTTP exceptions to the caller (a real
        # server would translate them to a 500); rollback truth is read
        # from the database below.
        await http_action(r1_client, token, oid, "fulfill")

    after = {
        "state": await order_vector(db, schema, oid),
        "inventory": await inventory_vector(db, schema, [sid_a, sid_b]),
        "reservations": await reservation_vector(db, schema, oid),
        "movements": await movement_count(db, schema, oid),
        "money": await payment_ledger_vector(db, schema, oid),
    }
    assert after["state"] == before["state"], (before, after)
    assert after["state"]["status"] == "paid", (
        "FULFILLED write survived a fault-injected request")
    assert after["inventory"] == before["inventory"], (before, after)
    assert after["reservations"] == before["reservations"], (before, after)
    assert after["movements"] == before["movements"] == 0, (before, after)
    assert after["money"] == before["money"], (before, after)
