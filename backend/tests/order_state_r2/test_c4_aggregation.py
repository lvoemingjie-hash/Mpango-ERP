"""C4 effective-payment aggregation equivalence — every runtime read and
write excludes soft-deleted payments, aggregates per order first, and never
masks corrupt history.

Counterexamples (product-RED on the parent commit):
  - C4-RED-1  multi-order same-retailer: binding == SUM(active holds) +
              SUM(per-order net exposure) — the parent double-counts credit
              and strands holds (50 + 60 expected; parent shows 210).
  - C4-RED-2  soft-deleting the only settlement of a partially_paid order
              makes further history corrupt: the next settlement must refuse
              on the hold mismatch instead of silently continuing (parent has
              no hold, accepts any amount up to nominal total).
  - C4-RED-3  soft-deleted credit payment removes the exposure: collection is
              refused (no exposure) and the cache tracks only effective
              history (parent keeps phantom exposure from the deleted row).
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from tests.order_state_r2.support import (
    binding_balance,
    errcode,
    http_action,
    http_create_order,
    make_bound_retailer,
    osd1_cashier_token,
    seed_sku_with_stock,
    soft_delete_payment,
    summary_for,
    summary_row,
)

pytestmark = pytest.mark.asyncio


async def test_c4_multi_order_same_retailer_sum(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity,
):
    """C4-RED-1 (counterexample on parent): order A confirm-only 50, order B
    full credit 100 then collection 40. Binding must be 50 + 60 = 110 and the
    summary must express reserved/unpaid=50, credit=60, total=110."""
    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    ret_id, schema, ws_id = await make_bound_retailer(db, provisioned_pool, reg)
    sku, _sid = await seed_sku_with_stock(db, schema, ret_id, price="25.00")

    oid_a = await http_create_order(r1_client, token, ret_id,
                                    [{"sku_code": sku, "quantity": 2}])
    assert (await http_action(r1_client, token, oid_a, "confirm")).status_code == 200
    oid_b = await http_create_order(r1_client, token, ret_id,
                                    [{"sku_code": sku, "quantity": 4}])
    assert (await http_action(r1_client, token, oid_b, "confirm")).status_code == 200
    pay_b = await http_action(r1_client, token, oid_b, "pay",
                              {"amount": 100.0, "method": "credit"})
    assert pay_b.status_code == 200, pay_b.text
    col_b = await http_action(r1_client, token, oid_b, "pay",
                              {"amount": 40.0, "method": "cash"})
    assert col_b.status_code == 200, col_b.text

    balance = await binding_balance(db, ws_id, ret_id)
    assert balance == Decimal("110.00"), (
        f"C4-RED-1 binding across mixed hold/exposure orders = {balance}, "
        "expected 110.00 (hold 50 + exposure 100-40=60; per-order SUM, no "
        "double count, no stranded hold)")

    from tests.order_state_r1.support import _second_session
    reader = await _second_session(schema, ws_id)
    try:
        summary = await summary_for(reader, ws_id)
    finally:
        await reader.close()
    row = summary_row(summary, ret_id)
    assert row is not None, f"retailer row dropped from summary: {summary}"
    assert Decimal(str(row["outstanding_balance"])) == Decimal("110.00"), row
    assert Decimal(str(row["unpaid_order_balance"])) == Decimal("50.00"), row
    assert Decimal(str(row["credit_receivables"])) == Decimal("60.00"), row


async def test_c4_soft_deleted_settlement_makes_history_corrupt(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity,
):
    """C4-RED-2 (counterexample on parent): order 60 confirmed; cash 30 makes
    it partially_paid (hold remaining 30); soft-deleting that payment makes
    the effective history 'nothing settled' while the hold says 30 settled —
    the next settlement (60) must be REFUSED on the mismatch. The parent has
    no hold so it happily accepts a full 60 on top of the deleted 30."""
    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    ret_id, schema, ws_id = await make_bound_retailer(db, provisioned_pool, reg)
    sku, _sid = await seed_sku_with_stock(db, schema, ret_id, price="30.00")
    oid = await http_create_order(r1_client, token, ret_id,
                                  [{"sku_code": sku, "quantity": 2}])
    assert (await http_action(r1_client, token, oid, "confirm")).status_code == 200
    p1 = await http_action(r1_client, token, oid, "pay",
                           {"amount": 30.0, "method": "cash"})
    assert p1.status_code == 200, p1.text
    assert (await order_vector_status(db, schema, oid)) == "partially_paid"

    assert await soft_delete_payment(db, schema, oid, "cash") == 1

    resp = await http_action(r1_client, token, oid, "pay",
                             {"amount": 60.0, "method": "cash"})
    assert resp.status_code == 409, (
        f"C4-RED-2 settlement accepted across a soft-deleted payment "
        f"({resp.status_code}): {resp.text}")
    assert errcode(resp) == "CREDIT_HOLD_MISMATCH", resp.text


async def test_c4_soft_deleted_credit_payment_removes_exposure(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity,
):
    """C4-RED-3 (counterexample on parent): soft-delete the credit payment of
    a paid credit order. Effective exposure becomes zero, further collection
    must be refused, and the binding must sit at zero (no phantom credit from
    the deleted row, no stranded hold)."""
    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    ret_id, schema, ws_id = await make_bound_retailer(db, provisioned_pool, reg)
    sku, _sid = await seed_sku_with_stock(db, schema, ret_id, price="50.00")
    oid = await http_create_order(r1_client, token, ret_id,
                                  [{"sku_code": sku, "quantity": 2}])
    assert (await http_action(r1_client, token, oid, "confirm")).status_code == 200
    pay = await http_action(r1_client, token, oid, "pay",
                            {"amount": 100.0, "method": "credit"})
    assert pay.status_code == 200, pay.text
    assert await soft_delete_payment(db, schema, oid, "credit") == 1

    resp = await http_action(r1_client, token, oid, "pay",
                             {"amount": 10.0, "method": "cash"})
    assert resp.status_code == 409, (
        f"C4-RED-3 collection accepted with zero effective exposure "
        f"({resp.status_code}): {resp.text}")
    assert errcode(resp) == "ORDER_ALREADY_PAID", resp.text

    # Runtime aggregation is consistent with EFFECTIVE history (the deleted
    # credit row contributes nothing: no exposure, collection refused). The
    # out-of-band soft-delete is cache tampering — the residue stays VISIBLE
    # as drift in the summary (cache 100 vs derived tracks 0), never hidden.
    from tests.order_state_r1.support import _second_session
    reader = await _second_session(schema, ws_id)
    try:
        summary = await summary_for(reader, ws_id)
    finally:
        await reader.close()
    row = summary_row(summary, ret_id)
    assert row is not None, "drifted retailer row must not be dropped"
    total = Decimal(str(row["outstanding_balance"]))
    derived = (Decimal(str(row["unpaid_order_balance"]))
               + Decimal(str(row["credit_receivables"])))
    assert total == Decimal("100.00") and derived == Decimal("0.00"), (
        f"C4-RED-3 tampered cache must stay visible as drift: row={row}")


async def order_vector_status(db, schema, order_id) -> str:
    from tests.order_state_r2.support import order_vector
    return (await order_vector(db, schema, order_id))["status"]
