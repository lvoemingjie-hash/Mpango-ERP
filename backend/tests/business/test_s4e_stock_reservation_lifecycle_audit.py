"""S4-E1 stock reservation lifecycle audit gate.

This file is intentionally test-only. It documents the expected reservation
lifecycle for quantity_on_hand, quantity_reserved, and available stock using
real tenant DB sessions and real order route handlers.
"""

from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.orders import cancel_order, confirm_order, fulfill_order, return_order
from core.security import TokenPayload
from database.session import AsyncSessionLocal
from models.inventory_movement import InventoryMovement
from models.inventory_stock import InventoryStock
from models.order import Order, OrderItem, OrderStatus
from models.sku import SKU


CONFIRM_RESERVATION_GAP = (
    "S4-E2 required: confirmed orders should reserve stock, but current confirm "
    "flow only changes order status and leaves quantity_reserved unchanged."
)
CANCEL_RELEASE_GAP = (
    "S4-E2 required: cancel should release previously reserved stock, but current "
    "cancel flow only changes order status."
)
FULFILL_RESERVATION_GAP = (
    "S4-E2 required: fulfillment should consume an existing reservation by reducing "
    "quantity_reserved as it deducts quantity_on_hand."
)
CONCURRENT_CONFIRM_GAP = (
    "S4-E2 required: concurrent confirmation should not over-reserve stock or allow "
    "more confirmed demand than available stock."
)


def _tenant_id(async_session: AsyncSession) -> uuid.UUID:
    return uuid.UUID(str(async_session.info["tenant_id"]))


def _token(async_session: AsyncSession) -> TokenPayload:
    return TokenPayload(
        user_id=str(uuid.uuid4()),
        tenant_id=str(async_session.info["tenant_id"]),
        tenant_schema=str(async_session.info["tenant_schema"]),
        roles=["admin"],
    )


def _token_for(*, tenant_id: str, tenant_schema: str) -> TokenPayload:
    return TokenPayload(
        user_id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        tenant_schema=tenant_schema,
        roles=["admin"],
    )


async def _prepare_inventory_schema(async_session: AsyncSession) -> None:
    schema = async_session.info["tenant_schema"]
    await async_session.execute(
        text(
            f'ALTER TABLE "{schema}".inventory_stocks '
            'ADD COLUMN IF NOT EXISTS quantity_reserved NUMERIC(12, 2) NOT NULL DEFAULT 0'
        )
    )
    await async_session.execute(
        text(
            f'''
            CREATE TABLE IF NOT EXISTS "{schema}".inventory_movements (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                sku_id UUID NOT NULL,
                movement_type VARCHAR(32) NOT NULL,
                quantity NUMERIC(12, 2) NOT NULL,
                quantity_before NUMERIC(12, 2) NOT NULL,
                quantity_after NUMERIC(12, 2) NOT NULL,
                reason TEXT,
                reference_type VARCHAR(50),
                reference_id UUID,
                is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
                deleted_at TIMESTAMP WITH TIME ZONE,
                created_by UUID,
                updated_by UUID,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            '''
        )
    )
    await async_session.execute(
        text(
            f'TRUNCATE TABLE "{schema}".inventory_movements, '
            f'"{schema}".inventory_stocks, "{schema}".skus RESTART IDENTITY CASCADE'
        )
    )
    await async_session.commit()


async def _create_sku_with_stock(
    async_session: AsyncSession,
    *,
    sku_code: str,
    on_hand: Decimal,
    reserved: Decimal = Decimal("0.00"),
) -> SKU:
    sku = SKU(sku_code=sku_code, name=f"SKU {sku_code}", unit="piece", is_active=True)
    async_session.add(sku)
    await async_session.flush()
    async_session.add(
        InventoryStock(
            sku_id=sku.id,
            quantity_on_hand=on_hand,
            quantity_reserved=reserved,
        )
    )
    await async_session.flush()
    return sku


async def _create_order(
    async_session: AsyncSession,
    *,
    status: OrderStatus,
    items: list[tuple[str, int, Decimal]],
) -> Order:
    total = sum(Decimal(quantity) * unit_price for _, quantity, unit_price in items)
    order = Order(
        wholesaler_id=_tenant_id(async_session),
        retailer_id=uuid.uuid4(),
        status=status,
        total_amount=total,
        notes="S4-E1 stock reservation lifecycle audit",
    )
    order.items = [
        OrderItem(
            product_name=f"Product {sku_code}",
            sku_code=sku_code,
            quantity=quantity,
            unit_price=unit_price,
            subtotal=Decimal(quantity) * unit_price,
        )
        for sku_code, quantity, unit_price in items
    ]
    async_session.add(order)
    await async_session.commit()
    await async_session.refresh(order)
    return order


async def _stock_snapshot(
    async_session: AsyncSession, sku_id: uuid.UUID
) -> tuple[Decimal, Decimal, Decimal]:
    result = await async_session.execute(
        select(InventoryStock).where(InventoryStock.sku_id == sku_id)
    )
    stock = result.scalar_one()
    return (
        stock.quantity_on_hand,
        stock.quantity_reserved,
        stock.quantity_on_hand - stock.quantity_reserved,
    )


async def _movement_count(async_session: AsyncSession, *, sku_id: uuid.UUID) -> int:
    result = await async_session.execute(
        select(InventoryMovement).where(InventoryMovement.sku_id == sku_id)
    )
    return len(result.scalars().all())


async def _order_status(async_session: AsyncSession, order_id: uuid.UUID) -> str:
    result = await async_session.execute(
        text("SELECT status::text FROM orders WHERE id = :order_id"),
        {"order_id": order_id},
    )
    return result.scalar_one()


async def _set_reserved(
    async_session: AsyncSession, *, sku_id: uuid.UUID, quantity: Decimal
) -> None:
    result = await async_session.execute(
        select(InventoryStock).where(InventoryStock.sku_id == sku_id)
    )
    stock = result.scalar_one()
    stock.quantity_reserved = quantity
    await async_session.commit()


@asynccontextmanager
async def _tenant_session(tenant_schema: str, tenant_id: str):
    async with AsyncSessionLocal() as session:
        session.info["tenant_schema"] = tenant_schema
        session.info["tenant_id"] = tenant_id
        await session.execute(text(f'SET LOCAL search_path TO "{tenant_schema}", public'))
        yield session


async def _confirm_in_independent_session(
    *, order_id: uuid.UUID, tenant_schema: str, tenant_id: str
) -> dict[str, Any]:
    try:
        async with _tenant_session(tenant_schema, tenant_id) as session:
            response = await confirm_order(
                str(order_id),
                token=_token_for(tenant_id=tenant_id, tenant_schema=tenant_schema),
                db=session,
            )
            await session.commit()
            return {"ok": True, "status": response.data["status"]}
    except HTTPException as exc:
        return {"ok": False, "status_code": exc.status_code, "detail": exc.detail}


async def _reset_reader(async_session: AsyncSession) -> None:
    await async_session.rollback()
    await async_session.execute(
        text(f'SET LOCAL search_path TO "{async_session.info["tenant_schema"]}", public')
    )


@pytest.mark.asyncio
@pytest.mark.xfail(strict=True, reason=CONFIRM_RESERVATION_GAP)
async def test_confirmed_order_reserves_stock_and_reduces_available(async_session):
    await _prepare_inventory_schema(async_session)
    sku = await _create_sku_with_stock(
        async_session, sku_code="S4E-CONFIRM", on_hand=Decimal("10.00")
    )
    order = await _create_order(
        async_session,
        status=OrderStatus.DRAFT,
        items=[("S4E-CONFIRM", 3, Decimal("25.00"))],
    )

    await confirm_order(str(order.id), token=_token(async_session), db=async_session)
    await async_session.commit()

    assert await _stock_snapshot(async_session, sku.id) == (
        Decimal("10.00"),
        Decimal("3.00"),
        Decimal("7.00"),
    )


@pytest.mark.asyncio
@pytest.mark.xfail(strict=True, reason=CANCEL_RELEASE_GAP)
async def test_cancel_releases_existing_reservation(async_session):
    await _prepare_inventory_schema(async_session)
    sku = await _create_sku_with_stock(
        async_session, sku_code="S4E-CANCEL", on_hand=Decimal("10.00")
    )
    order = await _create_order(
        async_session,
        status=OrderStatus.CONFIRMED,
        items=[("S4E-CANCEL", 3, Decimal("25.00"))],
    )
    await _set_reserved(async_session, sku_id=sku.id, quantity=Decimal("3.00"))

    await cancel_order(str(order.id), token=_token(async_session), db=async_session)
    await async_session.commit()

    assert await _stock_snapshot(async_session, sku.id) == (
        Decimal("10.00"),
        Decimal("0.00"),
        Decimal("10.00"),
    )


@pytest.mark.asyncio
@pytest.mark.xfail(strict=True, reason=FULFILL_RESERVATION_GAP)
async def test_fulfillment_consumes_existing_reservation_without_double_counting(async_session):
    await _prepare_inventory_schema(async_session)
    sku = await _create_sku_with_stock(
        async_session, sku_code="S4E-FULFILL", on_hand=Decimal("10.00")
    )
    order = await _create_order(
        async_session,
        status=OrderStatus.PAID,
        items=[("S4E-FULFILL", 3, Decimal("25.00"))],
    )
    await _set_reserved(async_session, sku_id=sku.id, quantity=Decimal("3.00"))

    await fulfill_order(str(order.id), token=_token(async_session), db=async_session)
    await async_session.commit()

    assert await _stock_snapshot(async_session, sku.id) == (
        Decimal("7.00"),
        Decimal("0.00"),
        Decimal("7.00"),
    )


@pytest.mark.asyncio
@pytest.mark.xfail(strict=True, reason=CONCURRENT_CONFIRM_GAP)
async def test_concurrent_confirm_does_not_over_reserve_or_accept_excess_demand(async_session):
    await _prepare_inventory_schema(async_session)
    tenant_schema = async_session.info["tenant_schema"]
    tenant_id = str(async_session.info["tenant_id"])
    sku = await _create_sku_with_stock(
        async_session, sku_code="S4E-CONCURRENT", on_hand=Decimal("5.00")
    )
    order_a = await _create_order(
        async_session,
        status=OrderStatus.DRAFT,
        items=[("S4E-CONCURRENT", 5, Decimal("25.00"))],
    )
    order_b = await _create_order(
        async_session,
        status=OrderStatus.DRAFT,
        items=[("S4E-CONCURRENT", 5, Decimal("25.00"))],
    )

    results = await asyncio.gather(
        _confirm_in_independent_session(
            order_id=order_a.id, tenant_schema=tenant_schema, tenant_id=tenant_id
        ),
        _confirm_in_independent_session(
            order_id=order_b.id, tenant_schema=tenant_schema, tenant_id=tenant_id
        ),
    )

    await _reset_reader(async_session)
    assert sum(1 for result in results if result["ok"]) == 1
    assert await _stock_snapshot(async_session, sku.id) == (
        Decimal("5.00"),
        Decimal("5.00"),
        Decimal("0.00"),
    )
    statuses = {
        await _order_status(async_session, order_a.id),
        await _order_status(async_session, order_b.id),
    }
    assert statuses == {OrderStatus.CONFIRMED.value, OrderStatus.DRAFT.value}


@pytest.mark.asyncio
@pytest.mark.xfail(strict=True, reason=CONFIRM_RESERVATION_GAP)
async def test_duplicate_confirm_does_not_double_reserve(async_session):
    await _prepare_inventory_schema(async_session)
    sku = await _create_sku_with_stock(
        async_session, sku_code="S4E-DUP-CONFIRM", on_hand=Decimal("10.00")
    )
    order = await _create_order(
        async_session,
        status=OrderStatus.DRAFT,
        items=[("S4E-DUP-CONFIRM", 3, Decimal("25.00"))],
    )

    await confirm_order(str(order.id), token=_token(async_session), db=async_session)
    await async_session.commit()
    with pytest.raises(HTTPException):
        await confirm_order(str(order.id), token=_token(async_session), db=async_session)

    assert await _stock_snapshot(async_session, sku.id) == (
        Decimal("10.00"),
        Decimal("3.00"),
        Decimal("7.00"),
    )


@pytest.mark.asyncio
@pytest.mark.xfail(strict=True, reason=CANCEL_RELEASE_GAP)
async def test_duplicate_cancel_does_not_double_release_reservation(async_session):
    await _prepare_inventory_schema(async_session)
    sku = await _create_sku_with_stock(
        async_session, sku_code="S4E-DUP-CANCEL", on_hand=Decimal("10.00")
    )
    order = await _create_order(
        async_session,
        status=OrderStatus.CONFIRMED,
        items=[("S4E-DUP-CANCEL", 3, Decimal("25.00"))],
    )
    await _set_reserved(async_session, sku_id=sku.id, quantity=Decimal("3.00"))

    await cancel_order(str(order.id), token=_token(async_session), db=async_session)
    await async_session.commit()
    with pytest.raises(HTTPException):
        await cancel_order(str(order.id), token=_token(async_session), db=async_session)

    assert await _stock_snapshot(async_session, sku.id) == (
        Decimal("10.00"),
        Decimal("0.00"),
        Decimal("10.00"),
    )


@pytest.mark.asyncio
async def test_return_restores_on_hand_without_creating_reserved_stock(async_session):
    await _prepare_inventory_schema(async_session)
    sku = await _create_sku_with_stock(
        async_session, sku_code="S4E-RETURN", on_hand=Decimal("10.00")
    )
    order = await _create_order(
        async_session,
        status=OrderStatus.PAID,
        items=[("S4E-RETURN", 3, Decimal("25.00"))],
    )
    await fulfill_order(str(order.id), token=_token(async_session), db=async_session)
    await async_session.commit()

    await return_order(str(order.id), token=_token(async_session), db=async_session)
    await async_session.commit()

    assert await _stock_snapshot(async_session, sku.id) == (
        Decimal("10.00"),
        Decimal("0.00"),
        Decimal("10.00"),
    )


@pytest.mark.asyncio
@pytest.mark.xfail(strict=True, reason=CONFIRM_RESERVATION_GAP)
async def test_reservation_is_tenant_schema_isolated(async_session):
    await _prepare_inventory_schema(async_session)
    tenant_schema = async_session.info["tenant_schema"]
    shadow_schema = "t_s4e_reservation_other"
    sku = await _create_sku_with_stock(
        async_session, sku_code="S4E-ISO", on_hand=Decimal("10.00")
    )
    order = await _create_order(
        async_session,
        status=OrderStatus.DRAFT,
        items=[("S4E-ISO", 3, Decimal("25.00"))],
    )
    await async_session.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{shadow_schema}"'))
    await async_session.execute(
        text(
            f'CREATE TABLE IF NOT EXISTS "{shadow_schema}".inventory_stocks '
            '('
            'sku_id UUID PRIMARY KEY, '
            'quantity_on_hand NUMERIC(12, 2) NOT NULL, '
            'quantity_reserved NUMERIC(12, 2) NOT NULL DEFAULT 0'
            ')'
        )
    )
    await async_session.execute(text(f'TRUNCATE TABLE "{shadow_schema}".inventory_stocks'))
    await async_session.execute(
        text(
            f'INSERT INTO "{shadow_schema}".inventory_stocks '
            '(sku_id, quantity_on_hand, quantity_reserved) '
            'VALUES (:sku_id, :on_hand, :reserved)'
        ),
        {"sku_id": sku.id, "on_hand": Decimal("99.00"), "reserved": Decimal("0.00")},
    )
    await async_session.commit()
    await async_session.execute(text(f'SET LOCAL search_path TO "{tenant_schema}", public'))

    await confirm_order(str(order.id), token=_token(async_session), db=async_session)
    await async_session.commit()

    tenant_a = await _stock_snapshot(async_session, sku.id)
    tenant_b = await async_session.execute(
        text(
            f'SELECT quantity_on_hand, quantity_reserved '
            f'FROM "{shadow_schema}".inventory_stocks WHERE sku_id = :sku_id'
        ),
        {"sku_id": sku.id},
    )
    row_b = tenant_b.one()
    assert tenant_a == (Decimal("10.00"), Decimal("3.00"), Decimal("7.00"))
    assert (row_b.quantity_on_hand, row_b.quantity_reserved) == (
        Decimal("99.00"),
        Decimal("0.00"),
    )


@pytest.mark.asyncio
async def test_reserve_and_release_do_not_write_physical_inventory_movements(async_session):
    await _prepare_inventory_schema(async_session)
    sku = await _create_sku_with_stock(
        async_session, sku_code="S4E-MOVEMENT-BOUNDARY", on_hand=Decimal("10.00")
    )
    order = await _create_order(
        async_session,
        status=OrderStatus.DRAFT,
        items=[("S4E-MOVEMENT-BOUNDARY", 3, Decimal("25.00"))],
    )

    await confirm_order(str(order.id), token=_token(async_session), db=async_session)
    await async_session.commit()
    await cancel_order(str(order.id), token=_token(async_session), db=async_session)
    await async_session.commit()

    assert await _movement_count(async_session, sku_id=sku.id) == 0


@pytest.mark.asyncio
async def test_illegal_repeat_cancel_keeps_stock_and_reserved_unchanged(async_session):
    await _prepare_inventory_schema(async_session)
    sku = await _create_sku_with_stock(
        async_session, sku_code="S4E-CANCEL-STABLE", on_hand=Decimal("10.00")
    )
    order = await _create_order(
        async_session,
        status=OrderStatus.CONFIRMED,
        items=[("S4E-CANCEL-STABLE", 3, Decimal("25.00"))],
    )

    await cancel_order(str(order.id), token=_token(async_session), db=async_session)
    await async_session.commit()
    before = await _stock_snapshot(async_session, sku.id)
    with pytest.raises(HTTPException):
        await cancel_order(str(order.id), token=_token(async_session), db=async_session)
    after = await _stock_snapshot(async_session, sku.id)

    assert before == after == (Decimal("10.00"), Decimal("0.00"), Decimal("10.00"))


@pytest.mark.asyncio
async def test_fulfillment_remains_tenant_isolated_for_on_hand_and_reserved(async_session):
    await _prepare_inventory_schema(async_session)
    tenant_schema = async_session.info["tenant_schema"]
    shadow_schema = "t_s4e_fulfillment_other"
    sku = await _create_sku_with_stock(
        async_session, sku_code="S4E-FULFILL-ISO", on_hand=Decimal("10.00")
    )
    order = await _create_order(
        async_session,
        status=OrderStatus.PAID,
        items=[("S4E-FULFILL-ISO", 3, Decimal("25.00"))],
    )
    await async_session.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{shadow_schema}"'))
    await async_session.execute(
        text(
            f'CREATE TABLE IF NOT EXISTS "{shadow_schema}".inventory_stocks '
            '('
            'sku_id UUID PRIMARY KEY, '
            'quantity_on_hand NUMERIC(12, 2) NOT NULL, '
            'quantity_reserved NUMERIC(12, 2) NOT NULL DEFAULT 0'
            ')'
        )
    )
    await async_session.execute(text(f'TRUNCATE TABLE "{shadow_schema}".inventory_stocks'))
    await async_session.execute(
        text(
            f'INSERT INTO "{shadow_schema}".inventory_stocks '
            '(sku_id, quantity_on_hand, quantity_reserved) '
            'VALUES (:sku_id, :on_hand, :reserved)'
        ),
        {"sku_id": sku.id, "on_hand": Decimal("99.00"), "reserved": Decimal("4.00")},
    )
    await async_session.commit()
    await async_session.execute(text(f'SET LOCAL search_path TO "{tenant_schema}", public'))

    await fulfill_order(str(order.id), token=_token(async_session), db=async_session)
    await async_session.commit()

    tenant_a = await _stock_snapshot(async_session, sku.id)
    tenant_b = await async_session.execute(
        text(
            f'SELECT quantity_on_hand, quantity_reserved '
            f'FROM "{shadow_schema}".inventory_stocks WHERE sku_id = :sku_id'
        ),
        {"sku_id": sku.id},
    )
    row_b = tenant_b.one()
    assert tenant_a == (Decimal("7.00"), Decimal("0.00"), Decimal("7.00"))
    assert (row_b.quantity_on_hand, row_b.quantity_reserved) == (
        Decimal("99.00"),
        Decimal("4.00"),
    )
