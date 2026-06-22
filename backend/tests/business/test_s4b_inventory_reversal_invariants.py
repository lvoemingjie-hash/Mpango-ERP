"""S4-B2 tests for return/cancel inventory reversal invariants."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text

from api.v1.orders import cancel_order, fulfill_order, return_order
from core.security import TokenPayload
from models.inventory_movement import InventoryMovement
from models.inventory_stock import InventoryStock
from models.ledger import AccountType, LedgerEntry
from models.order import Order, OrderItem, OrderStatus
from models.sku import SKU


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
    sku = SKU(sku_code=sku_code, name=f"SKU {sku_code}", unit="piece", is_active=True)
    async_session.add(sku)
    await async_session.flush()
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
        notes="S4-B1 inventory reversal invariant audit",
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


async def _stock_for(async_session, sku_id: uuid.UUID) -> InventoryStock:
    result = await async_session.execute(
        select(InventoryStock).where(InventoryStock.sku_id == sku_id)
    )
    return result.scalar_one()


async def _movements_for(async_session, order_id: uuid.UUID) -> list[InventoryMovement]:
    result = await async_session.execute(
        select(InventoryMovement)
        .where(InventoryMovement.reference_id == order_id)
        .order_by(InventoryMovement.created_at.asc(), InventoryMovement.id.asc())
    )
    return list(result.scalars().all())


async def _ledger_entries_for(
    async_session, *, reference_type: str, reference_id: uuid.UUID
) -> list[LedgerEntry]:
    result = await async_session.execute(
        select(LedgerEntry)
        .where(LedgerEntry.reference_type == reference_type)
        .where(LedgerEntry.reference_id == reference_id)
        .order_by(LedgerEntry.created_at.asc(), LedgerEntry.id.asc())
    )
    return list(result.scalars().all())


async def _create_paid_order_with_stock(
    async_session,
    *,
    sku_code: str,
    on_hand: Decimal = Decimal("10.00"),
    quantity: int = 3,
) -> tuple[SKU, Order]:
    sku = await _create_sku_with_stock(async_session, sku_code=sku_code, on_hand=on_hand)
    order = await _create_order(
        async_session,
        status=OrderStatus.PAID,
        items=[(sku_code, quantity, Decimal("25.00"))],
    )
    return sku, order


async def _create_fulfilled_order_with_deducted_stock(
    async_session,
    *,
    sku_code: str,
    on_hand: Decimal = Decimal("10.00"),
    quantity: int = 3,
) -> tuple[SKU, Order]:
    sku, order = await _create_paid_order_with_stock(
        async_session, sku_code=sku_code, on_hand=on_hand, quantity=quantity
    )
    await fulfill_order(str(order.id), token=_token(async_session), db=async_session)
    await async_session.commit()
    await async_session.refresh(order)
    return sku, order


@pytest.mark.asyncio
async def test_return_after_fulfillment_restores_stock_and_writes_restock_movement(async_session):
    await _prepare_inventory_schema(async_session)
    sku, order = await _create_fulfilled_order_with_deducted_stock(
        async_session, sku_code="S4B-RETURN"
    )

    response = await return_order(str(order.id), token=_token(async_session), db=async_session)
    await async_session.commit()

    stock = await _stock_for(async_session, sku.id)
    movements = await _movements_for(async_session, order.id)
    assert response.data["status"] == OrderStatus.RETURNED.value
    assert stock.quantity_on_hand == Decimal("10.00")
    assert len(movements) == 2
    assert movements[0].movement_type == "deduction"
    assert movements[1].movement_type == "restock"
    assert movements[1].quantity == Decimal("3.00")
    assert movements[1].quantity_before == Decimal("7.00")
    assert movements[1].quantity_after == Decimal("10.00")
    assert movements[1].reference_type == "order"
    assert movements[1].reference_id == order.id


@pytest.mark.asyncio
async def test_duplicate_return_restores_inventory_exactly_once(async_session):
    await _prepare_inventory_schema(async_session)
    sku, order = await _create_fulfilled_order_with_deducted_stock(
        async_session, sku_code="S4B-DUP-RETURN"
    )

    await return_order(str(order.id), token=_token(async_session), db=async_session)
    await async_session.commit()

    with pytest.raises(HTTPException) as exc:
        await return_order(str(order.id), token=_token(async_session), db=async_session)

    assert exc.value.status_code == 409
    stock = await _stock_for(async_session, sku.id)
    movements = await _movements_for(async_session, order.id)
    assert stock.quantity_on_hand == Decimal("10.00")
    assert [movement.movement_type for movement in movements] == ["deduction", "restock"]


@pytest.mark.asyncio
async def test_confirmed_cancel_does_not_change_stock_or_write_inventory_movement(async_session):
    await _prepare_inventory_schema(async_session)
    sku = await _create_sku_with_stock(
        async_session, sku_code="S4B-CANCEL-CONF", on_hand=Decimal("10.00")
    )
    order = await _create_order(
        async_session,
        status=OrderStatus.CONFIRMED,
        items=[("S4B-CANCEL-CONF", 3, Decimal("25.00"))],
    )

    response = await cancel_order(str(order.id), token=_token(async_session), db=async_session)
    await async_session.commit()

    stock = await _stock_for(async_session, sku.id)
    movements = await _movements_for(async_session, order.id)
    refund_entries = await _ledger_entries_for(
        async_session, reference_type="refund", reference_id=order.id
    )
    assert response.data["status"] == OrderStatus.CANCELLED.value
    assert stock.quantity_on_hand == Decimal("10.00")
    assert movements == []
    assert refund_entries == []


@pytest.mark.asyncio
async def test_paid_cancel_is_rejected_and_does_not_change_stock(async_session):
    await _prepare_inventory_schema(async_session)
    sku, order = await _create_paid_order_with_stock(
        async_session, sku_code="S4B-CANCEL-PAID"
    )

    with pytest.raises(HTTPException) as exc:
        await cancel_order(str(order.id), token=_token(async_session), db=async_session)

    stock = await _stock_for(async_session, sku.id)
    movements = await _movements_for(async_session, order.id)
    assert exc.value.status_code == 409
    assert stock.quantity_on_hand == Decimal("10.00")
    assert movements == []


@pytest.mark.asyncio
async def test_fulfilled_cancel_is_rejected_and_does_not_reverse_inventory(async_session):
    await _prepare_inventory_schema(async_session)
    sku, order = await _create_fulfilled_order_with_deducted_stock(
        async_session, sku_code="S4B-CANCEL-FULFILLED"
    )

    with pytest.raises(HTTPException) as exc:
        await cancel_order(str(order.id), token=_token(async_session), db=async_session)

    stock = await _stock_for(async_session, sku.id)
    movements = await _movements_for(async_session, order.id)
    assert exc.value.status_code == 409
    assert stock.quantity_on_hand == Decimal("7.00")
    assert len(movements) == 1
    assert movements[0].movement_type == "deduction"


@pytest.mark.asyncio
async def test_unfulfilled_return_is_rejected_and_stock_is_unchanged(async_session):
    await _prepare_inventory_schema(async_session)
    sku = await _create_sku_with_stock(
        async_session, sku_code="S4B-RETURN-CONF", on_hand=Decimal("10.00")
    )
    order = await _create_order(
        async_session,
        status=OrderStatus.CONFIRMED,
        items=[("S4B-RETURN-CONF", 3, Decimal("25.00"))],
    )

    with pytest.raises(HTTPException) as exc:
        await return_order(str(order.id), token=_token(async_session), db=async_session)

    stock = await _stock_for(async_session, sku.id)
    movements = await _movements_for(async_session, order.id)
    assert exc.value.status_code == 409
    assert stock.quantity_on_hand == Decimal("10.00")
    assert movements == []


@pytest.mark.asyncio
async def test_return_restock_failure_rolls_back_status_and_refund_ledger(async_session):
    await _prepare_inventory_schema(async_session)
    sku, order = await _create_fulfilled_order_with_deducted_stock(
        async_session, sku_code="S4B-ROLLBACK"
    )
    sku_id = sku.id
    order_id = order.id
    stock = await _stock_for(async_session, sku_id)
    stock.is_deleted = True
    await async_session.commit()

    with pytest.raises(HTTPException) as exc:
        await return_order(str(order_id), token=_token(async_session), db=async_session)

    result = await async_session.execute(select(Order).where(Order.id == order_id))
    persisted_order = result.scalar_one()
    refund_entries = await _ledger_entries_for(
        async_session, reference_type="refund", reference_id=order_id
    )
    movements = await _movements_for(async_session, order_id)

    assert exc.value.status_code == 409
    assert persisted_order.status == OrderStatus.FULFILLED
    assert refund_entries == []
    assert [movement.movement_type for movement in movements] == ["deduction"]


@pytest.mark.asyncio
async def test_return_restock_is_tenant_schema_isolated(async_session):
    await _prepare_inventory_schema(async_session)
    schema_a = async_session.info["tenant_schema"]
    schema_b = "t_s4b_reversal_other"
    sku, order = await _create_fulfilled_order_with_deducted_stock(
        async_session, sku_code="S4B-ISO"
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

    await return_order(str(order.id), token=_token(async_session), db=async_session)
    await async_session.commit()

    stock_a = await _stock_for(async_session, sku.id)
    result_b = await async_session.execute(
        text(f'SELECT quantity_on_hand FROM "{schema_b}".inventory_stocks WHERE sku_id = :sku_id'),
        {"sku_id": sku.id},
    )
    assert stock_a.quantity_on_hand == Decimal("10.00")
    assert result_b.scalar_one() == Decimal("99.00")


@pytest.mark.asyncio
async def test_return_posts_refund_ledger_and_inventory_restock(async_session):
    await _prepare_inventory_schema(async_session)
    sku, order = await _create_fulfilled_order_with_deducted_stock(
        async_session, sku_code="S4B-LEDGER"
    )

    await return_order(str(order.id), token=_token(async_session), db=async_session)
    await async_session.commit()

    stock = await _stock_for(async_session, sku.id)
    order_entries = await _ledger_entries_for(
        async_session, reference_type="order", reference_id=order.id
    )
    refund_entries = await _ledger_entries_for(
        async_session, reference_type="refund", reference_id=order.id
    )
    movements = await _movements_for(async_session, order.id)

    assert stock.quantity_on_hand == Decimal("10.00")
    assert len(movements) == 2
    assert movements[0].movement_type == "deduction"
    assert movements[1].movement_type == "restock"
    assert movements[1].quantity == Decimal("3.00")
    assert movements[1].quantity_before == Decimal("7.00")
    assert movements[1].quantity_after == Decimal("10.00")
    assert len(order_entries) == 0
    assert len(refund_entries) == 2
    assert sum(entry.amount for entry in refund_entries) == Decimal("0.0000")
    assert {entry.account_type for entry in refund_entries} == {
        AccountType.REVENUE,
        AccountType.CASH,
    }
