"""S4 business invariants for order fulfillment inventory safety.

These tests exercise the real tenant DB path. They call the route handler with
real SQLAlchemy sessions to verify committed database state and rollback
behavior without masking mutations behind mocks.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text

from api.v1.orders import fulfill_order
from core.security import TokenPayload
from models.inventory_movement import InventoryMovement
from models.inventory_stock import InventoryStock
from models.order import Order, OrderItem, OrderStatus
from models.sku import SKU
from tests.catalog_identity_helpers import create_sku_with_catalog, stable_order_items


def _tenant_id(async_session) -> uuid.UUID:
    return uuid.UUID(str(async_session.info["tenant_id"]))


def _token(async_session) -> TokenPayload:
    return TokenPayload(
        user_id=str(uuid.uuid4()),
        tenant_id=str(async_session.info["tenant_id"]),
        tenant_schema=str(async_session.info["tenant_schema"]),
        roles=["admin"],
    )


async def _prepare_inventory_schema(async_session) -> None:
    """Bring the lightweight test schema up to the S4 inventory contract."""
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
    async_session,
    *,
    sku_code: str,
    on_hand: Decimal,
) -> SKU:
    sku = await create_sku_with_catalog(
        async_session, sku_code=sku_code, name=f"SKU {sku_code}"
    )
    async_session.add(
        InventoryStock(
            sku_id=sku.id,
            quantity_on_hand=on_hand,
            quantity_reserved=Decimal("0.00"),
        )
    )
    await async_session.flush()
    return sku


async def _create_order(
    async_session,
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
        notes="S4 inventory invariant test",
    )
    order.items = await stable_order_items(async_session, items)
    async_session.add(order)
    await async_session.commit()
    await async_session.refresh(order)
    return order


async def _stock_for(async_session, sku_id: uuid.UUID) -> InventoryStock:
    result = await async_session.execute(
        select(InventoryStock).where(InventoryStock.sku_id == sku_id)
    )
    return result.scalar_one()


async def _movements_for(async_session, order_id: uuid.UUID) -> list[InventoryMovement]:
    result = await async_session.execute(
        select(InventoryMovement).where(InventoryMovement.reference_id == order_id)
    )
    return list(result.scalars().all())


@pytest.mark.asyncio
async def test_paid_fulfillment_decrements_stock_and_writes_movement(async_session):
    await _prepare_inventory_schema(async_session)
    sku = await _create_sku_with_stock(
        async_session, sku_code="S4-OK", on_hand=Decimal("10.00")
    )
    order = await _create_order(
        async_session,
        status=OrderStatus.PAID,
        items=[("S4-OK", 3, Decimal("25.00"))],
    )

    response = await fulfill_order(str(order.id), token=_token(async_session), db=async_session)
    await async_session.commit()

    stock = await _stock_for(async_session, sku.id)
    movements = await _movements_for(async_session, order.id)
    assert response.data["status"] == OrderStatus.FULFILLED.value
    assert stock.quantity_on_hand == Decimal("7.00")
    assert len(movements) == 1
    movement = movements[0]
    assert movement.movement_type == "deduction"
    assert movement.quantity == Decimal("-3.00")
    assert movement.quantity_before == Decimal("10.00")
    assert movement.quantity_after == Decimal("7.00")
    assert movement.reference_type == "order"
    assert movement.reference_id == order.id
    assert "fulfillment" in (movement.reason or "").lower()
    assert str(order.id) in (movement.reason or "")
    assert "S4-OK" in (movement.reason or "")


@pytest.mark.asyncio
async def test_insufficient_stock_rolls_back_order_stock_and_movement(async_session):
    await _prepare_inventory_schema(async_session)
    sku = await _create_sku_with_stock(
        async_session, sku_code="S4-SHORT", on_hand=Decimal("2.00")
    )
    sku_id = sku.id
    order = await _create_order(
        async_session,
        status=OrderStatus.PAID,
        items=[("S4-SHORT", 3, Decimal("25.00"))],
    )
    order_id = order.id

    with pytest.raises(HTTPException) as exc:
        await fulfill_order(str(order_id), token=_token(async_session), db=async_session)

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "INSUFFICIENT_STOCK"

    refreshed = await async_session.get(Order, order_id)
    stock = await _stock_for(async_session, sku_id)
    movements = await _movements_for(async_session, order_id)
    assert refreshed.status == OrderStatus.PAID
    assert stock.quantity_on_hand == Decimal("2.00")
    assert movements == []


@pytest.mark.asyncio
async def test_duplicate_fulfillment_does_not_deduct_twice(async_session):
    await _prepare_inventory_schema(async_session)
    sku = await _create_sku_with_stock(
        async_session, sku_code="S4-DUP", on_hand=Decimal("10.00")
    )
    order = await _create_order(
        async_session,
        status=OrderStatus.PAID,
        items=[("S4-DUP", 3, Decimal("25.00"))],
    )

    await fulfill_order(str(order.id), token=_token(async_session), db=async_session)
    await async_session.commit()

    with pytest.raises(HTTPException) as exc:
        await fulfill_order(str(order.id), token=_token(async_session), db=async_session)

    assert exc.value.status_code == 409
    stock = await _stock_for(async_session, sku.id)
    movements = await _movements_for(async_session, order.id)
    assert stock.quantity_on_hand == Decimal("7.00")
    assert len(movements) == 1


@pytest.mark.asyncio
async def test_multi_item_shortage_rolls_back_all_prior_deductions(async_session):
    await _prepare_inventory_schema(async_session)
    sku_ok = await _create_sku_with_stock(
        async_session, sku_code="S4-MULTI-OK", on_hand=Decimal("10.00")
    )
    sku_ok_id = sku_ok.id
    sku_short = await _create_sku_with_stock(
        async_session, sku_code="S4-MULTI-SHORT", on_hand=Decimal("1.00")
    )
    sku_short_id = sku_short.id
    order = await _create_order(
        async_session,
        status=OrderStatus.PAID,
        items=[
            ("S4-MULTI-OK", 3, Decimal("25.00")),
            ("S4-MULTI-SHORT", 2, Decimal("10.00")),
        ],
    )
    order_id = order.id

    with pytest.raises(HTTPException) as exc:
        await fulfill_order(str(order_id), token=_token(async_session), db=async_session)

    assert exc.value.status_code == 409
    refreshed = await async_session.get(Order, order_id)
    stock_ok = await _stock_for(async_session, sku_ok_id)
    stock_short = await _stock_for(async_session, sku_short_id)
    movements = await _movements_for(async_session, order_id)
    assert refreshed.status == OrderStatus.PAID
    assert stock_ok.quantity_on_hand == Decimal("10.00")
    assert stock_short.quantity_on_hand == Decimal("1.00")
    assert movements == []


@pytest.mark.asyncio
async def test_fulfillment_is_tenant_schema_isolated(async_session):
    await _prepare_inventory_schema(async_session)
    schema_a = async_session.info["tenant_schema"]
    schema_b = "t_s4_inventory_other"
    sku = await _create_sku_with_stock(
        async_session, sku_code="S4-ISO", on_hand=Decimal("10.00")
    )
    order = await _create_order(
        async_session,
        status=OrderStatus.PAID,
        items=[("S4-ISO", 3, Decimal("25.00"))],
    )
    await async_session.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_b}"'))
    await async_session.execute(
        text(
            f'CREATE TABLE IF NOT EXISTS "{schema_b}".inventory_stocks '
            '(sku_id UUID PRIMARY KEY, quantity_on_hand NUMERIC(12, 2) NOT NULL)'
        )
    )
    await async_session.execute(text(f'TRUNCATE TABLE "{schema_b}".inventory_stocks'))
    await async_session.execute(
        text(
            f'INSERT INTO "{schema_b}".inventory_stocks '
            '(sku_id, quantity_on_hand) VALUES (:sku_id, :quantity)'
        ),
        {"sku_id": sku.id, "quantity": Decimal("99.00")},
    )
    await async_session.commit()
    await async_session.execute(text(f'SET LOCAL search_path TO "{schema_a}", public'))

    await fulfill_order(str(order.id), token=_token(async_session), db=async_session)
    await async_session.commit()

    stock_a = await _stock_for(async_session, sku.id)
    result_b = await async_session.execute(
        text(f'SELECT quantity_on_hand FROM "{schema_b}".inventory_stocks WHERE sku_id = :sku_id'),
        {"sku_id": sku.id},
    )
    assert stock_a.quantity_on_hand == Decimal("7.00")
    assert result_b.scalar_one() == Decimal("99.00")


@pytest.mark.asyncio
async def test_unpaid_order_cannot_fulfill_and_stock_is_unchanged(async_session):
    await _prepare_inventory_schema(async_session)
    sku = await _create_sku_with_stock(
        async_session, sku_code="S4-UNPAID", on_hand=Decimal("10.00")
    )
    order = await _create_order(
        async_session,
        status=OrderStatus.CONFIRMED,
        items=[("S4-UNPAID", 3, Decimal("25.00"))],
    )

    with pytest.raises(HTTPException) as exc:
        await fulfill_order(str(order.id), token=_token(async_session), db=async_session)

    assert exc.value.status_code == 409
    refreshed = await async_session.get(Order, order.id)
    stock = await _stock_for(async_session, sku.id)
    movements = await _movements_for(async_session, order.id)
    assert refreshed.status == OrderStatus.CONFIRMED
    assert stock.quantity_on_hand == Decimal("10.00")
    assert movements == []
