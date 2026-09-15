"""R1 baseline: confirm reserves stock + credit and posts NO ledger;
cancel releases; paid cancel is fail-closed 409 with the temporary
workflow-not-implemented code; identity/snapshot preservation (stable and
legacy). Every control here doubles as a mutation oracle."""
from __future__ import annotations

from decimal import Decimal
from http import HTTPStatus

import pytest
from sqlalchemy import text

from tests.order_state_r1.support import (
    binding_balance,
    errcode,
    http_action,
    http_create_order,
    inventory_vector,
    make_bound_retailer,
    order_items_snapshot,
    order_vector,
    osd1_cashier_token,
    payment_ledger_vector,
    reservation_vector,
    seed_sku_with_stock,
)

pytestmark = pytest.mark.asyncio
pytestmark_r1 = None

from tests.order_state_r1.support import osd1_cashier_token as _tok  # noqa: E402


async def test_confirm_reserves_stock_and_credit_and_posts_no_ledger(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity
):
    db, reg = s2_clean_db
    token = await _tok(r1_client, cashier_identity)
    ret_id, schema, ws_id = await make_bound_retailer(db, provisioned_pool, reg)
    sku, sid = await seed_sku_with_stock(db, schema, ret_id, quantity=100, price="50.00")
    balance_before = await binding_balance(db, ws_id, ret_id)
    oid = await http_create_order(r1_client, token, ret_id,
                                  [{"sku_code": sku, "quantity": 4}])  # 4 x 50 = 200

    resp = await http_action(r1_client, token, oid, "confirm")
    assert resp.status_code == HTTPStatus.OK, resp.text

    state = await order_vector(db, schema, oid)
    assert state["status"] == "confirmed"

    resv = await reservation_vector(db, schema, oid)
    assert len(resv) == 1 and resv[0]["status"] == "reserved"
    assert Decimal(resv[0]["qty"]) == Decimal("4")
    inv = await inventory_vector(db, schema, [sid])
    assert inv[sid] == "100/4"

    # credit reservation: binding outstanding balance += order total (200.00)
    balance_after = await binding_balance(db, ws_id, ret_id)
    assert balance_after - balance_before == Decimal("200.00"), (
        balance_before, balance_after)

    # FROZEN DECISION: no receivable/revenue/payment ledger, no payments row
    money = await payment_ledger_vector(db, schema, oid)
    assert money["payments"] == [], money
    assert money["ledger"] == [], (
        "confirmation posted ledger entries — frozen decision violated")

    # movement journal untouched by confirm
    from tests.order_state_r1.support import movement_count
    assert await movement_count(db, schema, oid) == 0


async def test_cancel_from_confirmed_releases_and_keeps_no_ledger(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity
):
    db, reg = s2_clean_db
    token = await _tok(r1_client, cashier_identity)
    ret_id, schema, ws_id = await make_bound_retailer(db, provisioned_pool, reg)
    sku, sid = await seed_sku_with_stock(db, schema, ret_id)
    oid = await http_create_order(r1_client, token, ret_id,
                                  [{"sku_code": sku, "quantity": 3}])
    assert (await http_action(r1_client, token, oid, "confirm")).status_code == 200

    resp = await http_action(r1_client, token, oid, "cancel")
    assert resp.status_code == HTTPStatus.OK, resp.text
    assert (await order_vector(db, schema, oid))["status"] == "cancelled"

    resv = await reservation_vector(db, schema, oid)
    assert resv and all(r["status"] == "released" for r in resv), resv
    inv = await inventory_vector(db, schema, [sid])
    assert inv[sid] == "100/0"


async def test_draft_cancel_returns_cancelled_not_voided(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity
):
    db, reg = s2_clean_db
    token = await _tok(r1_client, cashier_identity)
    ret_id, schema, _ws = await make_bound_retailer(db, provisioned_pool, reg)
    sku, _sid = await seed_sku_with_stock(db, schema, ret_id)
    oid = await http_create_order(r1_client, token, ret_id,
                                  [{"sku_code": sku, "quantity": 1}])
    resp = await http_action(r1_client, token, oid, "cancel")
    assert resp.status_code == HTTPStatus.OK, resp.text
    assert resp.json()["data"]["status"] == "cancelled"
    assert (await order_vector(db, schema, oid))["status"] == "cancelled"


async def test_paid_cancel_fail_closed_with_workflow_code(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity
):
    db, reg = s2_clean_db
    token = await _tok(r1_client, cashier_identity)
    ret_id, schema, _ws = await make_bound_retailer(db, provisioned_pool, reg)
    sku, _sid = await seed_sku_with_stock(db, schema, ret_id, price="40.00")
    oid = await http_create_order(r1_client, token, ret_id,
                                  [{"sku_code": sku, "quantity": 2}])
    assert (await http_action(r1_client, token, oid, "confirm")).status_code == 200
    pay = await http_action(r1_client, token, oid, "pay",
                            {"amount": 80.00, "method": "cash"})
    assert pay.status_code == 200, pay.text

    resp = await http_action(r1_client, token, oid, "cancel")
    assert resp.status_code == HTTPStatus.CONFLICT, resp.text
    code = errcode(resp)
    assert code == "REFUND_WORKFLOW_NOT_IMPLEMENTED", code
    assert "refund" in resp.text.lower() and "not implemented" in resp.text.lower()
    assert (await order_vector(db, schema, oid))["status"] == "paid"

    # partially_paid likewise
    oid2 = await http_create_order(r1_client, token, ret_id,
                                   [{"sku_code": sku, "quantity": 2}])
    assert (await http_action(r1_client, token, oid2, "confirm")).status_code == 200
    part = await http_action(r1_client, token, oid2, "pay",
                             {"amount": 30.00, "method": "cash"})
    assert part.status_code == 200, part.text
    resp2 = await http_action(r1_client, token, oid2, "cancel")
    assert resp2.status_code == HTTPStatus.CONFLICT
    assert errcode(resp2) == "REFUND_WORKFLOW_NOT_IMPLEMENTED"
    assert (await order_vector(db, schema, oid2))["status"] == "partially_paid"


async def test_identity_and_snapshots_preserved_stable_and_legacy(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity
):
    db, reg = s2_clean_db
    token = await _tok(r1_client, cashier_identity)
    ret_id, schema, ws_id = await make_bound_retailer(db, provisioned_pool, reg)
    sku, sid = await seed_sku_with_stock(db, schema, ret_id)

    # stable item: full lifecycle, snapshots untouched even after cancel
    oid = await http_create_order(r1_client, token, ret_id,
                                  [{"sku_code": sku, "quantity": 1}])
    before = await order_items_snapshot(db, schema, oid)
    assert before[0]["identity_status"] == "stable"
    assert before[0]["sellable_unit_id"] == sid
    assert (await http_action(r1_client, token, oid, "confirm")).status_code == 200
    # retailer price change must not reprice the confirmed item
    await db.execute(text(
        f'UPDATE "{schema}".retailer_prices SET price = 99.00 '
        "WHERE sku_id = :s"), {"s": sid})
    await db.commit()
    await db.rollback()
    assert (await http_action(r1_client, token, oid, "cancel")).status_code == 200
    after = await order_items_snapshot(db, schema, oid)
    assert after == before, (before, after)

    # legacy-shaped item: confirm fails closed, identity untouched
    oid2 = await http_create_order(r1_client, token, ret_id,
                                   [{"sku_code": sku, "quantity": 1}])
    from tests.order_state_r1.support import _second_session  # type: ignore
    session = await _second_session(schema, ws_id)
    try:
        await session.execute(text(
            f'UPDATE "{schema}".order_items SET sellable_unit_id = NULL, '
            "identity_status = 'legacy', unit_snapshot = NULL "
            "WHERE order_id = :oid"), {"oid": oid2})
        await session.commit()
    finally:
        await session.close()
    await db.rollback()
    legacy_before = await order_items_snapshot(db, schema, oid2)
    resp = await http_action(r1_client, token, oid2, "confirm")
    assert resp.status_code == HTTPStatus.CONFLICT, resp.text
    legacy_after = await order_items_snapshot(db, schema, oid2)
    assert legacy_after == legacy_before, (legacy_before, legacy_after)
