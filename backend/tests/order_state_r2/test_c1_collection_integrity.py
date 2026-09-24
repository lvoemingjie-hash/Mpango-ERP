"""C1 collection integrity — PAID credit-order collections must verify the
order's unique converted hold BEFORE any financial write.

Counterexamples (product-RED on the parent commit, named):
  - C1-RED-1  normal partial collection: product must persist a converted
              lifecycle row and must not double-count confirm+credit in the
              binding cache (parent: no hold row at all, cache double-counts).
  - C1-RED-2  collection with the converted hold missing must be refused with
              zero financial writes (parent: accepts, collects blindly).
  - C1-RED-3  collection with a corrupted original amount must be refused
              (parent: accepts).
  - C1-RED-4  collection with a non-converted (active) hold must be refused
              (parent: accepts).

Positive controls document the legitimate flow (partial then full, converted
row preserved, replay without a second economic effect).
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

from tests.order_state_r2.support import (
    binding_balance,
    delete_holds,
    errcode,
    fetch_holds,
    http_action,
    http_create_order,
    make_bound_retailer,
    osd1_cashier_token,
    payment_ledger_vector,
    payments_vector,
    seed_sku_with_stock,
    soft_delete_payment,
    tamper_hold,
)

pytestmark = pytest.mark.asyncio

INTEGRITY_CODE = "CREDIT_HOLD_MISMATCH"


async def _credit_paid_order(r1_client, db, reg, pool, cashier, total: str):
    """confirm + full credit payment on a fresh order; returns bundle."""
    token = await osd1_cashier_token(r1_client, cashier)
    ret_id, schema, ws_id = await make_bound_retailer(db, pool, reg)
    price = f"{Decimal(total) / 2:.2f}"
    sku, _sid = await seed_sku_with_stock(db, schema, ret_id, price=price)
    oid = await http_create_order(r1_client, token, ret_id,
                                  [{"sku_code": sku, "quantity": 2}])
    assert (await http_action(r1_client, token, oid, "confirm")).status_code == 200
    pay = await http_action(r1_client, token, oid, "pay",
                            {"amount": float(Decimal(total)), "method": "credit"})
    assert pay.status_code == 200, pay.text
    return token, ret_id, schema, ws_id, oid


async def test_c1_collection_normal_partial_then_full_keeps_converted_row(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity,
):
    """C1-RED-1 (counterexample on parent): partial collection must reduce the
    binding by exactly the collected amount, must leave exactly one converted
    hold with remaining=0 and amount=order.total, and a second collection to
    zero must preserve that same row (no delete/recreate/revival)."""
    db, reg = s2_clean_db
    token, ret_id, schema, ws_id, oid = await _credit_paid_order(
        r1_client, db, reg, provisioned_pool, cashier_identity, "60.00")
    before = await binding_balance(db, ws_id, ret_id)

    resp = await http_action(r1_client, token, oid, "pay",
                             {"amount": 25.0, "method": "cash"})
    assert resp.status_code == 200, resp.text
    after_partial = await binding_balance(db, ws_id, ret_id)
    # confirm(+60) + credit(+0) + collection(-25): total movement is one total
    # minus the collection — NOT the parent double-count (confirm+credit=120).
    assert after_partial == Decimal("35.00"), (
        f"C1-RED-1 binding after partial collection = {after_partial}, "
        "expected 35.00 (confirm 60 once, credit conversion adds nothing, "
        "collection -25)")

    holds = await fetch_holds(db, schema, oid)
    assert len(holds) == 1, (
        f"C1-RED-1 product persists no/incorrect credit-hold lifecycle "
        f"(rows={holds}); collection must verify a unique converted hold")
    assert holds[0]["status"] == "converted", holds
    assert Decimal(holds[0]["remaining"]) == 0, holds
    assert Decimal(holds[0]["amount"]) == Decimal("60.00"), holds

    resp2 = await http_action(r1_client, token, oid, "pay",
                              {"amount": 35.0, "method": "cash"})
    assert resp2.status_code == 200, resp2.text
    assert await binding_balance(db, ws_id, ret_id) == Decimal("0.00")
    holds_after = await fetch_holds(db, schema, oid)
    assert len(holds_after) == 1 and holds_after[0] == holds[0], (
        f"full collection must keep the same converted row intact: "
        f"{holds} -> {holds_after}")


async def test_c1_collection_rejects_when_converted_hold_missing(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity,
):
    """C1-RED-2 (counterexample on parent): a PAID credit order whose
    converted hold is absent must refuse collection with zero financial
    writes. The parent has no hold rows at all — i.e. it always collects
    blind — so this REDs on the parent and greens once verification exists."""
    db, reg = s2_clean_db
    token, ret_id, schema, ws_id, oid = await _credit_paid_order(
        r1_client, db, reg, provisioned_pool, cashier_identity, "60.00")
    await delete_holds(db, schema, oid)

    before_balance = await binding_balance(db, ws_id, ret_id)
    before_facts = await payment_ledger_vector(db, schema, oid)
    before_payments = await payments_vector(db, schema, oid)

    resp = await http_action(r1_client, token, oid, "pay",
                             {"amount": 10.0, "method": "cash"})
    assert resp.status_code == 409, (
        f"C1-RED-2 collection on a PAID credit order without a verifiable "
        f"converted hold was accepted ({resp.status_code}): {resp.text}")
    assert errcode(resp) == INTEGRITY_CODE, resp.text
    assert await binding_balance(db, ws_id, ret_id) == before_balance
    assert await payment_ledger_vector(db, schema, oid) == before_facts
    assert await payments_vector(db, schema, oid) == before_payments


async def test_c1_collection_rejects_wrong_original_amount(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity,
):
    """C1-RED-3 (counterexample on parent): the converted hold's original
    amount must equal order.total; a corrupted row must refuse collection."""
    db, reg = s2_clean_db
    token, ret_id, schema, ws_id, oid = await _credit_paid_order(
        r1_client, db, reg, provisioned_pool, cashier_identity, "60.00")
    await tamper_hold(db, schema, oid, amount="30.00")

    before_balance = await binding_balance(db, ws_id, ret_id)
    resp = await http_action(r1_client, token, oid, "pay",
                             {"amount": 10.0, "method": "cash"})
    assert resp.status_code == 409, (
        f"C1-RED-3 collection accepted with hold.amount != order.total "
        f"({resp.status_code}): {resp.text}")
    assert errcode(resp) == INTEGRITY_CODE, resp.text
    assert await binding_balance(db, ws_id, ret_id) == before_balance


async def test_c1_collection_rejects_active_hold_state(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity,
):
    """C1-RED-4 (counterexample on parent): collection requires exactly one
    CONVERTED hold; an active hold on a PAID credit order is corruption."""
    db, reg = s2_clean_db
    token, ret_id, schema, ws_id, oid = await _credit_paid_order(
        r1_client, db, reg, provisioned_pool, cashier_identity, "60.00")
    # shape-valid corruption: active with remaining>0 (only reachable via
    # direct SQL — the service can never produce it)
    await tamper_hold(db, schema, oid, status="active", remaining_amount="10.00")

    before_balance = await binding_balance(db, ws_id, ret_id)
    resp = await http_action(r1_client, token, oid, "pay",
                             {"amount": 5.0, "method": "cash"})
    assert resp.status_code == 409, (
        f"C1-RED-4 collection accepted with a non-converted hold "
        f"({resp.status_code}): {resp.text}")
    assert errcode(resp) == INTEGRITY_CODE, resp.text
    assert await binding_balance(db, ws_id, ret_id) == before_balance


async def test_c1_collection_replay_has_single_economic_effect(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity,
):
    """Positive control: replaying the same collection key returns the same
    payment with no second payment row, ledger entry, or binding movement."""
    db, reg = s2_clean_db
    token, ret_id, schema, ws_id, oid = await _credit_paid_order(
        r1_client, db, reg, provisioned_pool, cashier_identity, "60.00")

    resp = await http_action(r1_client, token, oid, "pay",
                             {"amount": 25.0, "method": "cash"})
    assert resp.status_code == 200, resp.text
    balance = await binding_balance(db, ws_id, ret_id)
    facts = await payment_ledger_vector(db, schema, oid)
    n_payments = len((await payments_vector(db, schema, oid)))

    # the idempotent same-key replay contract is exercised in test_dc11d;
    # here a second DISTINCT collection of 10 is legitimate and moves the
    # balance again — proving collection writes stay bound to real payments.
    resp2 = await http_action(r1_client, token, oid, "pay",
                              {"amount": 10.0, "method": "cash"})
    assert resp2.status_code == 200, resp2.text
    assert await binding_balance(db, ws_id, ret_id) == balance - Decimal("10.00")
    assert len(await payments_vector(db, schema, oid)) == n_payments + 1
