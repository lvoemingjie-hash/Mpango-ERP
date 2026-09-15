"""F1: fulfill/return pre-lock discipline — ALL distinct stock rows locked
in one global (sorted sku_id) order BEFORE any inventory write."""
from __future__ import annotations

import uuid
from decimal import Decimal
from http import HTTPStatus

import pytest
from sqlalchemy import text

from tests.order_state_r1.support import (
    _second_session,
    http_action,
    http_create_order,
    make_bound_retailer,
    osd1_cashier_token,
    seed_sku_with_stock,
)

pytestmark = pytest.mark.asyncio


async def test_fulfill_prelocks_all_stocks_before_first_write(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity, monkeypatch
):
    """Spy on the lock helper and the deduction: every distinct stock row
    must be locked BEFORE the first deduct_on_fulfillment call, and lock
    order must be the sorted sku_id order."""
    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    ret_id, schema, _ws = await make_bound_retailer(db, provisioned_pool, reg)
    sku_z, sid_z = await seed_sku_with_stock(db, schema, ret_id, price="10.00")
    sku_a, sid_a = await seed_sku_with_stock(db, schema, ret_id, price="20.00")
    # item order in the request is z first then a; global lock order must
    # still be sorted by sku_id (independent of item order)
    oid = await http_create_order(r1_client, token, ret_id,
                                  [{"sku_code": sku_z, "quantity": 1},
                                   {"sku_code": sku_a, "quantity": 2}])
    assert (await http_action(r1_client, token, oid, "confirm")).status_code == 200
    pay = await http_action(r1_client, token, oid, "pay",
                            {"amount": 50.00, "method": "cash"})
    assert pay.status_code == 200, pay.text

    from services.inventory_service import InventoryService

    events: list[tuple[str, str]] = []
    real_lock = InventoryService._locked_stock_by_sku_id
    real_deduct = InventoryService.deduct_on_fulfillment

    async def spy_lock(self, db_, *, sku_id, sku_code, require_active=False):
        events.append(("lock", str(sku_id)))
        return await real_lock(self, db_, sku_id=sku_id, sku_code=sku_code,
                               require_active=require_active)

    async def spy_deduct(self, db_, **kwargs):
        events.append(("deduct", str(kwargs.get("sellable_unit_id"))))
        return await real_deduct(self, db_, **kwargs)

    monkeypatch.setattr(InventoryService, "_locked_stock_by_sku_id", spy_lock)
    monkeypatch.setattr(InventoryService, "deduct_on_fulfillment", spy_deduct)

    resp = await http_action(r1_client, token, oid, "fulfill")
    assert resp.status_code == HTTPStatus.OK, resp.text

    locks = [v for kind, v in events if kind == "lock"]
    first_deduct = next(i for i, (kind, _) in enumerate(events) if kind == "deduct")
    locks_before_first_write = [v for kind, v in events[:first_deduct] if kind == "lock"]

    expected_sorted = sorted({sid_a, sid_z})
    assert sorted(locks_before_first_write) == expected_sorted, (
        f"prelock incomplete before first inventory write: events={events}")
    assert locks_before_first_write == expected_sorted, (
        f"prelock order not global-sorted: {locks_before_first_write}")


async def test_cancel_prelocks_all_stocks_in_global_order(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity, monkeypatch
):
    """F2/M13 oracle: cancel pre-locks every distinct stock row in ONE
    global sorted-sku_id order BEFORE the first reservation-release write."""
    from tests.order_state_r1.support import reservation_vector

    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    ret_id, schema, _ws = await make_bound_retailer(db, provisioned_pool, reg)
    sku_z, sid_z = await seed_sku_with_stock(db, schema, ret_id, price="10.00")
    sku_a, sid_a = await seed_sku_with_stock(db, schema, ret_id, price="20.00")
    oid = await http_create_order(r1_client, token, ret_id,
                                  [{"sku_code": sku_z, "quantity": 1},
                                   {"sku_code": sku_a, "quantity": 2}])
    assert (await http_action(r1_client, token, oid, "confirm")).status_code == 200

    from services.inventory_service import InventoryService
    from services.order_command_service import OrderCommandService

    events: list[tuple[str, str]] = []
    real_lock = InventoryService._locked_stock_by_sku_id
    real_release = OrderCommandService._release_reservations

    async def spy_lock(self, db_, *, sku_id, sku_code, require_active=False):
        events.append(("lock", str(sku_id)))
        return await real_lock(self, db_, sku_id=sku_id, sku_code=sku_code,
                               require_active=require_active)

    async def spy_release(self, order, stocks):
        events.append(("release", "start"))
        return await real_release(self, order, stocks)

    monkeypatch.setattr(InventoryService, "_locked_stock_by_sku_id", spy_lock)
    monkeypatch.setattr(OrderCommandService, "_release_reservations", spy_release)

    resp = await http_action(r1_client, token, oid, "cancel")
    assert resp.status_code == 200, resp.text

    first_write = next((i for i, (kind, _) in enumerate(events)
                        if kind == "release"), None)
    assert first_write is not None, f"no release observed: {events}"
    locks_before = [v for kind, v in events[:first_write] if kind == "lock"]
    expected = sorted({sid_a, sid_z})
    assert locks_before == expected, (
        f"cancel prelock wrong/incomplete: {locks_before} != {expected}; "
        f"events={events}")
