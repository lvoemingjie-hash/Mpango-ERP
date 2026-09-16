"""F3 faces: legacy DRAFT cancel; legacy-with-reservations cancel releases
by reservation.sku_id; fulfill/return NULL identity controlled 409."""
from __future__ import annotations

import uuid
from decimal import Decimal
from http import HTTPStatus

import pytest
from sqlalchemy import text

from tests.order_state_r1.support import (
    _second_session,
    order_items_snapshot,
    errcode,
    http_action,
    http_create_order,
    inventory_vector,
    make_bound_retailer,
    order_vector,
    osd1_cashier_token,
    reservation_vector,
    seed_sku_with_stock,
)

pytestmark = pytest.mark.asyncio


async def _make_legacy(r1_client, token, db, pool, reg, *, confirm_first: bool):
    """Create a real order then degrade its item to legacy shape
    (sellable_unit_id NULL, identity_status legacy, snapshot NULL)."""
    ret_id, schema, ws_id = await make_bound_retailer(db, pool, reg)
    sku, sid = await seed_sku_with_stock(db, schema, ret_id, price="25.00")
    oid = await http_create_order(r1_client, token, ret_id,
                                  [{"sku_code": sku, "quantity": 2}])
    if confirm_first:
        assert (await http_action(r1_client, token, oid, "confirm")).status_code == 200
    session = await _second_session(schema, ws_id)
    try:
        await session.execute(text(
            f'UPDATE "{schema}".order_items SET sellable_unit_id = NULL, '
            "identity_status = 'legacy', unit_snapshot = NULL "
            "WHERE order_id = :oid"), {"oid": oid})
        await session.commit()
    finally:
        await session.close()
    await db.rollback()
    return oid, schema, sid


async def test_legacy_draft_cancel_pure_status_write(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity
):
    """Legacy DRAFT (no reservations) cancels cleanly to CANCELLED with
    zero reservation/stock side effects."""
    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    oid, schema, sid = await _make_legacy(
        r1_client, token, db, provisioned_pool, reg, confirm_first=False)

    items_before = await order_items_snapshot(db, schema, oid)

    resp = await http_action(r1_client, token, oid, "cancel")
    assert resp.status_code == HTTPStatus.OK, (
        f"OSR1-F3-LEGACY-DRAFT-CANCEL-OK expected 200, got "
        f"{resp.status_code}: {resp.text}")
    assert (await order_vector(db, schema, oid))["status"] == "cancelled"
    assert await reservation_vector(db, schema, oid) == []
    assert (await inventory_vector(db, schema, [sid]))[sid] == "100/0"

    items_after = await order_items_snapshot(db, schema, oid)
    assert items_after == items_before, (
        f"OSR1-F3-DRAFT-SNAPSHOT legacy order-item rows changed by cancel: "
        f"before={items_before} after={items_after}")


async def test_legacy_with_reservations_cancel_releases_by_reservation_sku_id(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity
):
    """Confirm reserves (real identity), THEN the item degrades to legacy;
    cancel must still find the active reservation, pre-lock by
    reservation.sku_id, release it fully (aggregate back to zero) and
    leave snapshots/identity untouched."""
    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    oid, schema, sid = await _make_legacy(
        r1_client, token, db, provisioned_pool, reg, confirm_first=True)

    # precondition: the reservation exists with the ORIGINAL sku_id
    resv = await reservation_vector(db, schema, oid)
    assert len(resv) == 1 and resv[0]["status"] == "reserved"
    assert resv[0]["sku"] == sid

    # entire legacy order-item snapshot captured immediately before cancel
    items_before = await order_items_snapshot(db, schema, oid)
    assert items_before and all(
        i["identity_status"] == "legacy" and i["sellable_unit_id"] is None
        for i in items_before), items_before

    try:
        resp = await http_action(r1_client, token, oid, "cancel")
    except Exception as exc:  # uncontrolled failure escaped the ASGI app
        raise AssertionError(
            f"OSR1-F3-LEGACY-RESV-CANCEL-OK cancel raised an uncontrolled "
            f"transport exception {type(exc).__name__}: {exc}") from exc
    assert resp.status_code == HTTPStatus.OK, (
        f"OSR1-F3-LEGACY-RESV-CANCEL-OK expected 200, got "
        f"{resp.status_code}: {resp.text}")

    assert (await order_vector(db, schema, oid))["status"] == "cancelled"
    resv = await reservation_vector(db, schema, oid)
    assert all(r["status"] == "released" for r in resv), resv
    assert (await inventory_vector(db, schema, [sid]))[sid] == "100/0"

    # exact snapshot equality: the cancel left every legacy order-item
    # column (identity, snapshot, pricing) untouched
    items_after = await order_items_snapshot(db, schema, oid)
    assert items_after == items_before, (
        f"OSR1-F3-RESV-SNAPSHOT legacy order-item rows changed by cancel: "
        f"before={items_before} after={items_after}")


async def test_fulfill_null_identity_controlled_409(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity
):
    """Confirm (real identity, reserves), pay, degrade item to legacy
    (NULL sellable_unit_id): fulfill must return a CONTROLLED 409
    ORDER_ITEM_SELLABLE_ID_REQUIRED — never ValueError/500."""
    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    ret_id, schema, ws_id = await make_bound_retailer(db, provisioned_pool, reg)
    sku, _sid = await seed_sku_with_stock(db, schema, ret_id, price="20.00")
    oid = await http_create_order(r1_client, token, ret_id,
                                  [{"sku_code": sku, "quantity": 2}])
    assert (await http_action(r1_client, token, oid, "confirm")).status_code == 200
    pay = await http_action(r1_client, token, oid, "pay",
                            {"amount": 40.00, "method": "cash"})
    assert pay.status_code == 200, pay.text

    session = await _second_session(schema, ws_id)
    try:
        await session.execute(text(
            f'UPDATE "{schema}".order_items SET sellable_unit_id = NULL, '
            "identity_status = 'legacy', unit_snapshot = NULL "
            "WHERE order_id = :oid"), {"oid": oid})
        await session.commit()
    finally:
        await session.close()
    await db.rollback()

    # probe: what does the DB actually hold for this order?
    probe = (await db.execute(text(
        f'SELECT identity_status, sellable_unit_id IS NULL AS isnull '
        f'FROM "{schema}".order_items WHERE order_id = :oid'
    ), {"oid": oid})).fetchall()
    assert all(r.isnull and r.identity_status == "legacy" for r in probe), (
        f"degrade did not persist: {probe}")

    try:
        resp = await http_action(r1_client, token, oid, "fulfill")
    except Exception as exc:  # uncontrolled failure escaped the ASGI app
        raise AssertionError(
            f"OSR1-F3-FULFILL-NULL-409 fulfill raised an uncontrolled "
            f"transport exception {type(exc).__name__}: {exc}") from exc
    assert resp.status_code == HTTPStatus.CONFLICT, (
        f"OSR1-F3-FULFILL-NULL-409 expected controlled 409, got "
        f"{resp.status_code}: {resp.text}")
    body = resp.json()
    code = (body.get("detail") or {}).get("code") or body.get("code")
    assert code == "ORDER_ITEM_SELLABLE_ID_REQUIRED", (
        f"OSR1-F3-FULFILL-NULL-409 wrong error code: {body}")


async def test_return_null_identity_controlled_409(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity
):
    """Return on a FULFILLED order whose items degraded to NULL identity
    must be a controlled 409, never ValueError/500."""
    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    ret_id, schema, ws_id = await make_bound_retailer(db, provisioned_pool, reg)
    sku, _sid = await seed_sku_with_stock(db, schema, ret_id, price="20.00")
    oid = await http_create_order(r1_client, token, ret_id,
                                  [{"sku_code": sku, "quantity": 2}])
    assert (await http_action(r1_client, token, oid, "confirm")).status_code == 200
    paid = await http_action(r1_client, token, oid, "pay",
                             {"amount": 40.00, "method": "cash"})
    assert paid.status_code == 200, paid.text
    assert (await http_action(r1_client, token, oid, "fulfill")).status_code == 200

    session = await _second_session(schema, ws_id)
    try:
        await session.execute(text(
            f'UPDATE "{schema}".order_items SET sellable_unit_id = NULL, '
            "identity_status = 'legacy', unit_snapshot = NULL "
            "WHERE order_id = :oid"), {"oid": oid})
        await session.commit()
    finally:
        await session.close()
    await db.rollback()

    try:
        resp = await http_action(r1_client, token, oid, "return")
    except Exception as exc:  # uncontrolled failure escaped the ASGI app
        raise AssertionError(
            f"OSR1-F3-RETURN-NULL-409 return raised an uncontrolled "
            f"transport exception {type(exc).__name__}: {exc}") from exc
    assert resp.status_code == HTTPStatus.CONFLICT, (
        f"OSR1-F3-RETURN-NULL-409 expected controlled 409, got "
        f"{resp.status_code}: {resp.text}")
    body = resp.json()
    code = (body.get("detail") or {}).get("code") or body.get("code")
    assert code == "ORDER_ITEM_SELLABLE_ID_REQUIRED", (
        f"OSR1-F3-RETURN-NULL-409 wrong error code: {body}")
