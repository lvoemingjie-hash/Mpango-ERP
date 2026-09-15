"""MPANGO-ORDER-STATE-AUTHORITY-D1 matrix group 5 — identity snapshots and
packaging protection.

Identity contract under test: ``order_items.sellable_unit_id -> skus.id`` is
THE identity field. State operations must never reprice an order item,
overwrite its snapshots (product_name/sku_code/unit_snapshot/unit_price), or
rewrite a legacy item's identity. The first SKU reference (order creation)
freezes package identity (BC-06 history lock); packaging modification after
use must fail closed with SKU_PACKAGE_QUANTITY_IMMUTABLE_AFTER_USE.

Mixed HTTP + direct-service boundary: creation/confirm/cancel run over real
HTTP; the packaging-modification attempt calls the real SKUService guard
(the same code the PUT /skus/{sku_code} route invokes).
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi import HTTPException
from http import HTTPStatus
from sqlalchemy import text

from tests.order_state_d1.support import (
    bound_retailer,
    http_action,
    http_create_wholesaler_order,
    osd1_cashier_token,
    seed_sku_with_stock,
    snapshot_order_items,
)

pytestmark = pytest.mark.asyncio


def _errcode(resp) -> str:
    body = resp.json()
    detail = body.get("detail") or body.get("error") or {}
    return (detail.get("code") or body.get("code") or "")


async def test_state_operations_never_touch_item_snapshots(
    osd1_client, s2_clean_db, provisioned_pool, osd1_cashier
):
    db, reg = s2_clean_db
    token = await osd1_cashier_token(osd1_client, osd1_cashier)
    async with bound_retailer(db, provisioned_pool, reg) as (ret_id, schema, _ws):
        sku, sid = await seed_sku_with_stock(db, schema, ret_id, quantity=50, price="12.50")
        order = await http_create_wholesaler_order(osd1_client, token, ret_id, sku, 3)
        oid = order["id"]

        before = await snapshot_order_items(db, schema, oid)
        assert len(before) == 1
        assert before[0]["identity_status"] == "stable"
        assert before[0]["sellable_unit_id"] == sid
        assert before[0]["unit_snapshot"] == "piece"
        assert Decimal(before[0]["unit_price"]) == Decimal("12.50")

        # Move the order through confirm -> pay so both state writers run.
        assert (await http_action(osd1_client, token, oid, "confirm")).status_code == 200
        pay = await http_action(osd1_client, token, oid, "pay",
                                {"amount": 37.50, "method": "cash"})
        assert pay.status_code == 200, pay.text

        # Even a retailer-price change must not reprice the confirmed item.
        await db.execute(text(
            f'UPDATE "{schema}".retailer_prices SET price = 99.00 '
            "WHERE sku_id = :s AND retailer_id = :r"),
            {"s": sid, "r": ret_id})
        await db.commit()

        cancel = await http_action(osd1_client, token, oid, "cancel")
        # paid cancel is (correctly) unreachable over HTTP; the snapshot
        # invariant is checked regardless of the transition outcome
        assert cancel.status_code in (HTTPStatus.CONFLICT,), cancel.text

        after = await snapshot_order_items(db, schema, oid)
        assert after == before, (
            "state operations mutated item identity/pricing snapshots: "
            f"{before} -> {after}")


async def test_first_sku_reference_freezes_package_identity(
    osd1_client, s2_clean_db, provisioned_pool, osd1_cashier
):
    """Order creation is the first SKU reference: after it, ANY package_quantity
    change must fail closed through the shared guard (history lock)."""
    from services.package_identity import (
        CODE_IMMUTABLE_AFTER_USE,
        ensure_package_quantity_change_allowed,
        lock_sku_row,
    )

    db, reg = s2_clean_db
    token = await osd1_cashier_token(osd1_client, osd1_cashier)
    async with bound_retailer(db, provisioned_pool, reg) as (ret_id, schema, ws_id):
        sku, sid = await seed_sku_with_stock(db, schema, ret_id)
        order = await http_create_wholesaler_order(osd1_client, token, ret_id, sku, 1)
        assert order["id"]

        session = await _bound_session(schema, ws_id)
        try:
            locked = await lock_sku_row(session, sku_id=uuid.UUID(sid))
            assert locked is not None
            with pytest.raises(HTTPException) as excinfo:
                await ensure_package_quantity_change_allowed(
                    session,
                    sku=locked,
                    new_package_quantity=Decimal("12"),
                )
            assert excinfo.value.detail["code"] == CODE_IMMUTABLE_AFTER_USE, (
                excinfo.value.detail)
        finally:
            await session.rollback()
            await session.close()


async def test_unreferenced_sku_can_still_repackage_positive_control(
    osd1_client, s2_clean_db, provisioned_pool, osd1_cashier
):
    """Legitimate-order positive control: a SKU with NO order reference
    accepts a package_quantity change (the guard is use-based, not absolute)."""
    from services.package_identity import (
        ensure_package_quantity_change_allowed,
        lock_sku_row,
    )

    db, reg = s2_clean_db
    token = await osd1_cashier_token(osd1_client, osd1_cashier)
    async with bound_retailer(db, provisioned_pool, reg) as (ret_id, schema, ws_id):
        # bare seed: no stock row, no retailer price — only the all-zero
        # placeholder exemption keeps this SKU out of identity-use history
        product = (await db.execute(text(
            f'INSERT INTO "{schema}".catalog_products (name, is_active, is_deleted) '
            "VALUES ('OSD1Bare', true, false) RETURNING id"
        ))).fetchone()
        row = (await db.execute(text(
            f'INSERT INTO "{schema}".skus '
            "(sku_code, name, unit, is_active, is_deleted, catalog_product_id, package_quantity) "
            "VALUES (:c, 'OSD1Bare', 'piece', true, false, :p, 1.000) RETURNING id"),
            {"c": f"OSD1BARE{uuid.uuid4().hex[:6].upper()}", "p": product.id},
        )).fetchone()
        sid = str(row.id)
        await db.commit()
        session = await _bound_session(schema, ws_id)
        try:
            locked = await lock_sku_row(session, sku_id=uuid.UUID(sid))
            assert locked is not None
            result = await ensure_package_quantity_change_allowed(
                session,
                sku=locked,
                new_package_quantity=Decimal("12"),
            )
            assert result is None
        finally:
            await session.rollback()
            await session.close()


async def test_legacy_item_blocks_confirm_and_keeps_identity(
    osd1_client, s2_clean_db, provisioned_pool, osd1_cashier
):
    """A legacy-shaped item (sellable_unit_id NULL, identity_status legacy)
    fails confirm closed (ORDER_ITEM_SELLABLE_ID_REQUIRED) and — because the
    whole request rolls back — its legacy identity is NOT rewritten."""
    db, reg = s2_clean_db
    token = await osd1_cashier_token(osd1_client, osd1_cashier)
    async with bound_retailer(db, provisioned_pool, reg) as (ret_id, schema, ws_id):
        sku, sid = await seed_sku_with_stock(db, schema, ret_id)
        order = await http_create_wholesaler_order(osd1_client, token, ret_id, sku, 1)
        oid = order["id"]

        # Degrade the item to legacy shape out-of-band (pre-MVP rows look
        # exactly like this).
        session = await _bound_session(schema, ws_id)
        try:
            await session.execute(text(
                f'UPDATE "{schema}".order_items SET sellable_unit_id = NULL, '
                "identity_status = 'legacy', unit_snapshot = NULL "
                "WHERE order_id = :oid"), {"oid": oid})
            await session.commit()
        finally:
            await session.close()
        await db.rollback()

        resp = await http_action(osd1_client, token, oid, "confirm")
        assert resp.status_code == HTTPStatus.CONFLICT, resp.text
        assert _errcode(resp) == "ORDER_ITEM_SELLABLE_ID_REQUIRED", resp.text

        items = await snapshot_order_items(db, schema, oid)
        assert items[0]["identity_status"] == "legacy"
        assert items[0]["sellable_unit_id"] is None
        assert items[0]["unit_snapshot"] is None, (
            "the failed confirm must not rewrite legacy identity shape")


async def _bound_session(schema: str, tenant_id: str):
    from database.session import AsyncSessionLocal

    session = AsyncSessionLocal()
    session.info["tenant_schema"] = schema
    session.info["tenant_id"] = tenant_id
    await session.execute(text(f'SET search_path TO "{schema}", public'))
    return session
