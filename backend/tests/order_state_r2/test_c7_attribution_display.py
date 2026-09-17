"""C7 attribution normalisation, terminal guards, and amount display.

Counterexamples (product-RED on the parent commit):
  - C7-RED-1  confirmed 50 order displays reserved 50 / real receivable 0 /
              total occupation 50 — the parent shows 100 (double count).
  - C7-RED-2  confirming an order whose retailer binding is missing must be
              refused (BINDING_NOT_FOUND); the parent silently increments
              nothing and still confirms.
  - C7-RED-3  a tampered cache must remain VISIBLE as drift in the summary
              (total != reserved + receivable in the same payload); the
              parent formula (cache + unpaid) hides drift when cache=0.
  - C7-RED-4  the lifecycle table carries exactly the frozen column set
              (order_id FK only — no denormalised owner columns, no
              soft-delete columns).
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import text

from tests.order_state_r2.support import (
    binding_balance,
    errcode,
    fetch_holds,
    HOLD_COLUMNS,
    http_action,
    http_create_order,
    make_bound_retailer,
    osd1_cashier_token,
    seed_sku_with_stock,
    soft_delete_binding,
    summary_for,
    summary_row,
)

pytestmark = pytest.mark.asyncio


async def test_c7_confirmed_50_displays_50_0_50(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity,
):
    """C7-RED-1: confirmed-but-undelivered 50 order: reserved=50, real
    receivable=0, total occupation=50. Never 100."""
    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    ret_id, schema, ws_id = await make_bound_retailer(db, provisioned_pool, reg)
    sku, _sid = await seed_sku_with_stock(db, schema, ret_id, price="25.00")
    oid = await http_create_order(r1_client, token, ret_id,
                                  [{"sku_code": sku, "quantity": 2}])
    assert (await http_action(r1_client, token, oid, "confirm")).status_code == 200

    assert await binding_balance(db, ws_id, ret_id) == Decimal("50.00")

    from tests.order_state_r1.support import _second_session
    reader = await _second_session(schema, ws_id)
    try:
        summary = await summary_for(reader, ws_id)
    finally:
        await reader.close()
    row = summary_row(summary, ret_id)
    assert row is not None, f"summary lost the retailer row: {summary}"
    total = Decimal(str(row["outstanding_balance"]))
    reserved = Decimal(str(row["unpaid_order_balance"]))
    receivable = Decimal(str(row["credit_receivables"]))
    assert (total, reserved, receivable) == (
        Decimal("50.00"), Decimal("50.00"), Decimal("0.00")), (
        f"C7-RED-1 confirmed-50 display total={total} reserved={reserved} "
        f"receivable={receivable}; expected 50/0/50 (parent double-counts "
        "the hold into 100)")


async def test_c7_confirm_without_binding_refused(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity,
):
    """C7-RED-2: confirm with a missing (soft-deleted) binding must fail
    closed — the parent silently skips the aggregate update and confirms."""
    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    ret_id, schema, ws_id = await make_bound_retailer(db, provisioned_pool, reg)
    sku, _sid = await seed_sku_with_stock(db, schema, ret_id, price="25.00")
    oid = await http_create_order(r1_client, token, ret_id,
                                  [{"sku_code": sku, "quantity": 2}])
    await soft_delete_binding(db, ws_id, ret_id)

    resp = await http_action(r1_client, token, oid, "confirm")
    assert resp.status_code == 409, (
        f"C7-RED-2 confirm accepted without a live binding ({resp.status_code}): "
        f"{resp.text}")
    assert errcode(resp) == "BINDING_NOT_FOUND", resp.text
    assert (await order_vector_status(db, schema, oid)) == "draft"


async def test_c7_cache_tamper_stays_visible_as_drift(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity,
):
    """C7-RED-3: with the cache tampered to 0 under a live 50 hold, the
    summary must still show the retailer row with outstanding=0 but
    reserved=50 — drift observable inside one payload (total != reserved +
    receivable). The parent formula (cache + unpaid) hides the drift."""
    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    ret_id, schema, ws_id = await make_bound_retailer(db, provisioned_pool, reg)
    sku, _sid = await seed_sku_with_stock(db, schema, ret_id, price="25.00")
    oid = await http_create_order(r1_client, token, ret_id,
                                  [{"sku_code": sku, "quantity": 2}])
    assert (await http_action(r1_client, token, oid, "confirm")).status_code == 200
    await db.execute(text(
        "UPDATE public.wholesaler_retailer_bindings SET outstanding_balance = 0 "
        "WHERE wholesaler_id = :w AND retailer_id = :r"),
        {"w": ws_id, "r": ret_id})
    await db.commit()

    from tests.order_state_r1.support import _second_session
    reader = await _second_session(schema, ws_id)
    try:
        summary = await summary_for(reader, ws_id)
    finally:
        await reader.close()
    row = summary_row(summary, ret_id)
    assert row is not None, "summary dropped a drifted retailer row (hiding)"
    total = Decimal(str(row["outstanding_balance"]))
    derived = (Decimal(str(row["unpaid_order_balance"]))
               + Decimal(str(row["credit_receivables"])))
    assert total == Decimal("0.00") and derived == Decimal("50.00"), (
        f"C7-RED-3 drift must stay visible in-payload: row={row}")
    assert total != derived, "drift was flattened — cache corruption hidden"


async def test_c7_hold_columns_frozen_shape(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity,
):
    """C7-RED-4: the lifecycle table carries exactly the frozen columns —
    order_id is the single attribution anchor (no wholesaler_id/retailer_id
    duplication) and soft-delete columns do not exist."""
    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    ret_id, schema, ws_id = await make_bound_retailer(db, provisioned_pool, reg)
    sku, _sid = await seed_sku_with_stock(db, schema, ret_id, price="25.00")
    oid = await http_create_order(r1_client, token, ret_id,
                                  [{"sku_code": sku, "quantity": 2}])
    assert (await http_action(r1_client, token, oid, "confirm")).status_code == 200

    cols = {r[0] for r in (await db.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = :s AND table_name = 'order_credit_holds'"),
        {"s": schema})).fetchall()}
    assert cols == HOLD_COLUMNS, (
        f"C7-RED-4 lifecycle columns drifted: extra={sorted(cols - HOLD_COLUMNS)} "
        f"missing={sorted(HOLD_COLUMNS - cols)}")

    constraints = {r[0] for r in (await db.execute(text(
        "SELECT conname FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid "
        "JOIN pg_namespace n ON n.oid = c.connamespace "
        "WHERE n.nspname = :s AND t.relname = 'order_credit_holds'"),
        {"s": schema})).fetchall()}
    assert "uq_order_credit_holds_order_id" in constraints, constraints
    assert "ck_order_credit_holds_lifecycle_shape" in constraints, constraints

    holds = await fetch_holds(db, schema, oid)
    assert len(holds) == 1 and holds[0]["status"] == "active", holds


async def order_vector_status(db, schema, order_id) -> str:
    from tests.order_state_r2.support import order_vector
    return (await order_vector(db, schema, order_id))["status"]
