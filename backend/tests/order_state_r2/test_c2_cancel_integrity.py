"""C2 cancel integrity — cancel must verify the full reservation snapshot
before releasing, and release stock+hold+binding atomically.

Counterexamples (product-RED on the parent commit):
  - C2-RED-1  CONFIRMED cancel must release the hold exactly once (parent:
              binding keeps the confirm-time reservation — Face 1 gap).
  - C2-RED-2  CONFIRMED cancel with remaining != amount must be refused with
              zero writes (parent: no snapshot to corrupt, cancels blindly).
  - C2-RED-3  DRAFT cancel with any lifecycle row must be refused (parent:
              cannot even represent the row; cancels blindly).
  - C2-RED-4  fully-settled (PAID) order leaves binding at zero, not a
              stranded confirm-time reservation (parent: binding stays +total).
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from tests.order_state_r2.support import (
    binding_balance,
    errcode,
    fetch_holds,
    http_action,
    http_create_order,
    insert_hold,
    inventory_vector,
    make_bound_retailer,
    order_vector,
    osd1_cashier_token,
    reservation_vector,
    seed_sku_with_stock,
    tamper_hold,
)

pytestmark = pytest.mark.asyncio

INTEGRITY_CODE = "CREDIT_HOLD_MISMATCH"


async def test_c2_confirmed_cancel_releases_hold_exactly_once(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity,
):
    """C2-RED-1 (counterexample on parent): confirmed cancel releases stock
    reservations, sets the hold released/remaining=0, restores the binding and
    cancels the order — all in the caller's single transaction."""
    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    ret_id, schema, ws_id = await make_bound_retailer(db, provisioned_pool, reg)
    sku, sid = await seed_sku_with_stock(db, schema, ret_id, price="30.00")
    oid = await http_create_order(r1_client, token, ret_id,
                                  [{"sku_code": sku, "quantity": 2}])
    assert (await http_action(r1_client, token, oid, "confirm")).status_code == 200
    held = await binding_balance(db, ws_id, ret_id)
    assert held == Decimal("60.00"), held

    resp = await http_action(r1_client, token, oid, "cancel")
    assert resp.status_code == 200, resp.text

    assert (await order_vector(db, schema, oid))["status"] == "cancelled"
    assert await binding_balance(db, ws_id, ret_id) == Decimal("0.00"), (
        "C2-RED-1 cancel must release the confirm-time credit hold "
        "(parent keeps the aggregate stranded)")
    holds = await fetch_holds(db, schema, oid)
    assert len(holds) == 1, f"expected one released lifecycle row, got {holds}"
    assert holds[0]["status"] == "released" and holds[0]["remaining"] == "0.00", holds
    assert holds[0]["amount"] == "60.00", holds
    inv = await inventory_vector(db, schema, [sid])
    assert inv[sid] == "100/0", inv
    resv = await reservation_vector(db, schema, oid)
    assert all(r["status"] == "released" for r in resv), resv

    second = await http_action(r1_client, token, oid, "cancel")
    assert second.status_code == 409, second.text
    assert await fetch_holds(db, schema, oid) == holds, "terminal row mutated"


async def test_c2_confirmed_cancel_remaining_mismatch_rejected(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity,
):
    """C2-RED-2 (counterexample on parent): CONFIRMED cancel requires the
    unique active hold with remaining == amount == order.total; corruption is
    refused with zero writes (order/binding/stock/hold all unchanged)."""
    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    ret_id, schema, ws_id = await make_bound_retailer(db, provisioned_pool, reg)
    sku, sid = await seed_sku_with_stock(db, schema, ret_id, price="30.00")
    oid = await http_create_order(r1_client, token, ret_id,
                                  [{"sku_code": sku, "quantity": 2}])
    assert (await http_action(r1_client, token, oid, "confirm")).status_code == 200
    await tamper_hold(db, schema, oid, remaining_amount="30.00")

    resp = await http_action(r1_client, token, oid, "cancel")
    assert resp.status_code == 409, (
        f"C2-RED-2 cancel accepted with hold.remaining != amount "
        f"({resp.status_code}): {resp.text}")
    assert errcode(resp) == INTEGRITY_CODE, resp.text
    assert (await order_vector(db, schema, oid))["status"] == "confirmed"
    assert await binding_balance(db, ws_id, ret_id) == Decimal("60.00")
    inv = await inventory_vector(db, schema, [sid])
    assert inv[sid] == "100/2", inv
    holds = await fetch_holds(db, schema, oid)
    assert len(holds) == 1 and holds[0]["remaining"] == "30.00", holds


async def test_c2_draft_cancel_with_hold_row_rejected(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity,
):
    """C2-RED-3 (counterexample on parent): a DRAFT order with any lifecycle
    row is corruption — cancel must refuse, not auto-clean."""
    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    ret_id, schema, ws_id = await make_bound_retailer(db, provisioned_pool, reg)
    sku, _sid = await seed_sku_with_stock(db, schema, ret_id, price="10.00")
    oid = await http_create_order(r1_client, token, ret_id,
                                  [{"sku_code": sku, "quantity": 1}])
    inserted = await insert_hold(db, schema, oid, amount="10.00",
                                 remaining="10.00", status="active")

    resp = await http_action(r1_client, token, oid, "cancel")
    assert resp.status_code == 409, (
        f"C2-RED-3 DRAFT cancel with a lifecycle row accepted "
        f"({resp.status_code}, row_inserted={inserted}): {resp.text}")
    assert errcode(resp) == INTEGRITY_CODE, resp.text
    assert (await order_vector(db, schema, oid))["status"] == "draft"
    assert await binding_balance(db, ws_id, ret_id) == Decimal("0.00")


async def test_c2_paid_cancel_fail_closed_and_binding_settled(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity,
):
    """C2-RED-4 (counterexample on parent): PAID cancel stays fail-closed
    (refund workflow frozen) AND a fully cash-settled order leaves the
    binding at zero — the parent strands the confirm-time reservation."""
    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    ret_id, schema, ws_id = await make_bound_retailer(db, provisioned_pool, reg)
    sku, _sid = await seed_sku_with_stock(db, schema, ret_id, price="30.00")
    oid = await http_create_order(r1_client, token, ret_id,
                                  [{"sku_code": sku, "quantity": 2}])
    assert (await http_action(r1_client, token, oid, "confirm")).status_code == 200
    pay = await http_action(r1_client, token, oid, "pay",
                            {"amount": 60.0, "method": "cash"})
    assert pay.status_code == 200, pay.text
    assert await binding_balance(db, ws_id, ret_id) == Decimal("0.00"), (
        "C2-RED-4 full cash settlement must reduce the hold to zero "
        "(parent strands the reservation in the aggregate)")

    resp = await http_action(r1_client, token, oid, "cancel")
    assert resp.status_code == 409, resp.text
    assert errcode(resp) == "REFUND_WORKFLOW_NOT_IMPLEMENTED", resp.text
    holds = await fetch_holds(db, schema, oid)
    assert len(holds) == 1 and holds[0]["status"] == "settled", holds
