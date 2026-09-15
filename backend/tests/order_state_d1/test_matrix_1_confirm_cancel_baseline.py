"""MPANGO-ORDER-STATE-AUTHORITY-D1 matrix group 1 — confirm/cancel baseline.

Real HTTP truth on real PostgreSQL 16 (ASGI app + JWT tenant context, real
``finalize_tenant_context`` commit). Establishes the CURRENT behavior every
later group races against:

- HTTP confirm keeps its inventory reservation side effect (never described
  as "all side effects bypassed") and posts NO ledger entries — the service
  path (OrderService.transition) does post ``post_order_confirmation``; the
  divergence is asserted here, not assumed equivalent.
- Cancel from confirmed releases owned reservations; cancel from draft is a
  pure status write (nothing to release).
- The CRUD matrix difference vs the domain matrix: HTTP cancel allows
  DRAFT->CANCELLED (domain matrix only allows DRAFT->VOIDED) and HTTP cancel
  is unreachable for PAID/PARTIALLY_PAID (domain matrix allows both).
- Duplicate-effect negative controls: second confirm and second cancel are
  409 (an oracle that cannot detect duplicates is not evidence).
"""
from __future__ import annotations

import pytest
from decimal import Decimal
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


async def _confirm(client, token, order_id):
    return await http_action(client, token, order_id, "confirm")


async def _cancel(client, token, order_id):
    return await http_action(client, token, order_id, "cancel")


async def test_confirm_happy_path_reserves_stock_and_posts_no_ledger(
    osd1_client, s2_clean_db, provisioned_pool, osd1_cashier
):
    db, _reg = s2_clean_db
    token = await osd1_cashier_token(osd1_client, osd1_cashier)
    async with bound_retailer(db, provisioned_pool, _reg) as (ret_id, schema, _ws):
        sku, _sid = await seed_sku_with_stock(db, schema, ret_id, quantity=100, price="50.00")
        order = await http_create_wholesaler_order(osd1_client, token, ret_id, sku, 4)
        oid = order["id"]

        resp = await _confirm(osd1_client, token, oid)
        assert resp.status_code == HTTPStatus.OK, resp.text
        assert resp.json()["data"]["status"] == "confirmed"

        state = await fetch_order_state(db, schema, oid)
        assert state["status"] == "confirmed"

        facts = await fetch_reservation_facts(db, schema, oid)
        assert facts["reserved_rows"] == 1, f"expected one owned reservation: {facts}"
        assert Decimal(facts["reserved_total"]) == Decimal("4")

        row = (await db.execute(text(
            f'SELECT quantity_reserved, quantity_on_hand FROM "{schema}".inventory_stocks '
            "WHERE sku_id = (SELECT sellable_unit_id FROM \"" + schema + "\".order_items "
            "WHERE order_id = :oid LIMIT 1)"), {"oid": oid})).fetchone()
        assert Decimal(str(row.quantity_reserved)) == Decimal("4")
        assert Decimal(str(row.quantity_on_hand)) == Decimal("100")

        # Divergence asserted, not assumed: HTTP confirm posts NO ledger.
        money = await fetch_payment_ledger_facts(db, schema, oid)
        assert money["payments"] == []
        assert money["ledger"] == [], (
            "HTTP confirm posted ledger entries; matrix claimed none — "
            "update BEHAVIOR-MATRIX.csv before any unification decision")


async def test_cancel_from_confirmed_releases_owned_reservations(
    osd1_client, s2_clean_db, provisioned_pool, osd1_cashier
):
    db, _reg = s2_clean_db
    token = await osd1_cashier_token(osd1_client, osd1_cashier)
    async with bound_retailer(db, provisioned_pool, _reg) as (ret_id, schema, _ws):
        sku, _sid = await seed_sku_with_stock(db, schema, ret_id)
        order = await http_create_wholesaler_order(osd1_client, token, ret_id, sku, 3)
        oid = order["id"]
        assert (await _confirm(osd1_client, token, oid)).status_code == HTTPStatus.OK

        resp = await _cancel(osd1_client, token, oid)
        assert resp.status_code == HTTPStatus.OK, resp.text
        assert resp.json()["data"]["status"] == "cancelled"

        facts = await fetch_reservation_facts(db, schema, oid)
        assert facts["reserved_rows"] == 0
        assert all(r["status"] == "released" for r in facts["rows"]), facts

        row = (await db.execute(text(
            f'SELECT quantity_reserved FROM "{schema}".inventory_stocks '
            "WHERE sku_id = (SELECT sellable_unit_id FROM \"" + schema + "\".order_items "
            "WHERE order_id = :oid LIMIT 1)"), {"oid": oid})).fetchone()
        assert Decimal(str(row.quantity_reserved)) == Decimal("0")


async def test_cancel_from_draft_is_pure_status_write(
    osd1_client, s2_clean_db, provisioned_pool, osd1_cashier
):
    db, _reg = s2_clean_db
    token = await osd1_cashier_token(osd1_client, osd1_cashier)
    async with bound_retailer(db, provisioned_pool, _reg) as (ret_id, schema, _ws):
        sku, _sid = await seed_sku_with_stock(db, schema, ret_id)
        order = await http_create_wholesaler_order(osd1_client, token, ret_id, sku, 2)
        oid = order["id"]

        resp = await _cancel(osd1_client, token, oid)
        assert resp.status_code == HTTPStatus.OK, resp.text

        facts = await fetch_reservation_facts(db, schema, oid)
        assert facts["rows"] == [], "draft cancel must not create or release reservations"

        # CRUD-matrix difference #1 (asserted current behavior): the HTTP
        # entry allows DRAFT->CANCELLED although the domain matrix only
        # allows DRAFT->VOIDED for pre-payment cancellation.
        state = await fetch_order_state(db, schema, oid)
        assert state["status"] == "cancelled"


async def test_cancel_from_paid_is_unreachable_via_http(
    osd1_client, s2_clean_db, provisioned_pool, osd1_cashier
):
    """CRUD-matrix difference #2: PAID->CANCELLED exists ONLY in the domain
    matrix; the HTTP cancel endpoint 409s because crud allowed_from is
    draft/confirmed only."""
    db, _reg = s2_clean_db
    token = await osd1_cashier_token(osd1_client, osd1_cashier)
    async with bound_retailer(db, provisioned_pool, _reg) as (ret_id, schema, _ws):
        sku, _sid = await seed_sku_with_stock(db, schema, ret_id)
        order = await http_create_wholesaler_order(osd1_client, token, ret_id, sku, 1)
        oid = order["id"]
        assert (await _confirm(osd1_client, token, oid)).status_code == HTTPStatus.OK
        pay = await http_action(osd1_client, token, oid, "pay",
                                {"amount": 50.00, "method": "cash"})
        assert pay.status_code == HTTPStatus.OK, pay.text

        resp = await _cancel(osd1_client, token, oid)
        assert resp.status_code == HTTPStatus.CONFLICT, resp.text
        code = resp.json().get("detail", {}).get("code") or resp.json().get("code")
        assert code == "INVALID_STATE_TRANSITION", resp.text
        state = await fetch_order_state(db, schema, oid)
        assert state["status"] == "paid"


async def test_double_confirm_is_409_duplicate_control(
    osd1_client, s2_clean_db, provisioned_pool, osd1_cashier
):
    """Duplicate-effect negative control: the second confirm must not
    double-reserve (DUPLICATE_RESERVATION guard) nor succeed again."""
    db, _reg = s2_clean_db
    token = await osd1_cashier_token(osd1_client, osd1_cashier)
    async with bound_retailer(db, provisioned_pool, _reg) as (ret_id, schema, _ws):
        sku, _sid = await seed_sku_with_stock(db, schema, ret_id)
        order = await http_create_wholesaler_order(osd1_client, token, ret_id, sku, 5)
        oid = order["id"]
        assert (await _confirm(osd1_client, token, oid)).status_code == HTTPStatus.OK

        second = await _confirm(osd1_client, token, oid)
        assert second.status_code == HTTPStatus.CONFLICT, second.text
        code = second.json().get("detail", {}).get("code") or second.json().get("code")
        assert code in {"INVALID_STATE_TRANSITION", "DUPLICATE_RESERVATION"}, code

        facts = await fetch_reservation_facts(db, schema, oid)
        assert facts["reserved_rows"] == 1, facts


async def test_double_cancel_sequential_is_409_control(
    osd1_client, s2_clean_db, provisioned_pool, osd1_cashier
):
    """Legitimate-order positive control for the race oracles: sequential
    cancel-then-cancel is deterministic 200 then 409 (the racing cancel||cancel
    group must never accept MORE than this)."""
    db, _reg = s2_clean_db
    token = await osd1_cashier_token(osd1_client, osd1_cashier)
    async with bound_retailer(db, provisioned_pool, _reg) as (ret_id, schema, _ws):
        sku, _sid = await seed_sku_with_stock(db, schema, ret_id)
        order = await http_create_wholesaler_order(osd1_client, token, ret_id, sku, 1)
        oid = order["id"]
        assert (await _cancel(osd1_client, token, oid)).status_code == HTTPStatus.OK

        second = await _cancel(osd1_client, token, oid)
        assert second.status_code == HTTPStatus.CONFLICT, second.text
