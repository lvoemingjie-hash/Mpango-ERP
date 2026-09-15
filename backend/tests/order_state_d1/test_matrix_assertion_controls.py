"""MPANGO-ORDER-STATE-AUTHORITY-D1 — assertion-helper controls.

Every oracle used by the six matrix groups must prove it can pass on a
legitimate state (positive control) and fire on a planted duplicate/forbidden
effect (negative control). A helper that cannot fire is not evidence.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from tests.order_state_d1.support import (
    assert_no_orphan_reservations,
    assert_no_paid_cancelled_combo,
    bound_retailer,
    http_action,
    http_create_wholesaler_order,
    linearizable_final,
    osd1_cashier_token,
    seed_sku_with_stock,
)

pytestmark = pytest.mark.asyncio


async def _paid_cancelled_combo_planted(db, schema, oid, sid):
    await db.execute(text(
        f'INSERT INTO "{schema}".payments '
        "(order_id, retailer_id, amount, method, status, idempotency_key) "
        "VALUES (:oid, (SELECT retailer_id FROM \"" + schema + "\".orders WHERE id = :oid), "
        "40, 'cash', 'completed', :key)"),
        {"oid": oid, "key": f"ctl-{uuid.uuid4().hex[:12]}"},
    )
    await db.execute(text(
        f'INSERT INTO "{schema}".ledger_entries '
        "(transaction_date, account_type, amount, reference_type, reference_id, description) "
        "VALUES (now(), 'cash', 80, 'order', :oid, 'planted control')"),
        {"oid": oid},
    )
    await db.commit()


async def test_no_paid_cancelled_combo_passes_on_clean_cancel(
    osd1_client, s2_clean_db, provisioned_pool, osd1_cashier
):
    db, reg = s2_clean_db
    token = await osd1_cashier_token(osd1_client, osd1_cashier)
    async with bound_retailer(db, provisioned_pool, reg) as (ret_id, schema, _ws):
        sku, sid = await seed_sku_with_stock(db, schema, ret_id)
        order = await http_create_wholesaler_order(osd1_client, token, ret_id, sku, 1)
        oid = order["id"]
        assert (await http_action(osd1_client, token, oid, "cancel")).status_code == 200
        await assert_no_paid_cancelled_combo(db, schema, oid)  # positive control


async def test_no_paid_cancelled_combo_fires_on_planted_combo(
    osd1_client, s2_clean_db, provisioned_pool, osd1_cashier
):
    db, reg = s2_clean_db
    token = await osd1_cashier_token(osd1_client, osd1_cashier)
    async with bound_retailer(db, provisioned_pool, reg) as (ret_id, schema, _ws):
        sku, sid = await seed_sku_with_stock(db, schema, ret_id)
        order = await http_create_wholesaler_order(osd1_client, token, ret_id, sku, 1)
        oid = order["id"]
        assert (await http_action(osd1_client, token, oid, "cancel")).status_code == 200

        await _paid_cancelled_combo_planted(db, schema, oid, sid)
        await db.rollback()

        with pytest.raises(AssertionError, match="cancelled order holds"):
            await assert_no_paid_cancelled_combo(db, schema, oid)


async def test_no_orphan_reservations_helper_controls(
    osd1_client, s2_clean_db, provisioned_pool, osd1_cashier
):
    """Positive + negative control in one scenario (the negative-control
    variant of group 4's residue oracle, against released-row planting)."""
    db, reg = s2_clean_db
    token = await osd1_cashier_token(osd1_client, osd1_cashier)
    async with bound_retailer(db, provisioned_pool, reg) as (ret_id, schema, _ws):
        sku, sid = await seed_sku_with_stock(db, schema, ret_id)
        order = await http_create_wholesaler_order(osd1_client, token, ret_id, sku, 1)
        oid = order["id"]
        # confirm then cancel leaves zero reserved — positive control
        assert (await http_action(osd1_client, token, oid, "confirm")).status_code == 200
        assert (await http_action(osd1_client, token, oid, "cancel")).status_code == 200
        await assert_no_orphan_reservations(db, schema, oid, expect_status="cancelled")

        # plant an extra reserved row — negative control must fire
        await db.execute(text(
            f'INSERT INTO "{schema}".inventory_reservations '
            "(order_id, order_item_id, sku_id, sku_code, quantity, status, reference_type, reference_id) "
            "SELECT :oid, oi.id, :sid, oi.sku_code, 1, 'reserved', 'order', :oid "
            f'FROM "{schema}".order_items oi WHERE oi.order_id = :oid LIMIT 1'
        ), {"oid": oid, "sid": sid})
        await db.commit()
        await db.rollback()
        with pytest.raises(AssertionError, match="orphan reservations"):
            await assert_no_orphan_reservations(db, schema, oid, expect_status="cancelled")


async def test_linearizable_final_matches_and_mismatch_controls():
    histories = [
        {"status": "paid", "payments": 1},
        {"status": "cancelled", "payments": 0},
    ]
    assert linearizable_final({"status": "paid", "payments": 1}, histories) is True
    assert linearizable_final({"status": "cancelled", "payments": 1}, histories) is False
