"""S4-D inventory movement ledger integrity gate.

These tests use the real tenant database path and real route/service handlers.
They verify InventoryMovement is an audit-consistent journal, not only a side
effect that happens to exist.
"""

from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.inventory import adjust_inventory, list_inventory_logs
from api.v1.orders import fulfill_order, return_order
from core.security import TokenPayload
from database.session import AsyncSessionLocal
from models.inventory_movement import InventoryMovement
from models.inventory_stock import InventoryStock
from models.ledger import LedgerEntry
from models.order import Order, OrderItem, OrderStatus
from models.sku import SKU
from schemas.inventory import InventoryAdjustRequest


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


def _request(async_session: AsyncSession):
    return SimpleNamespace(
        state=SimpleNamespace(
            request_id="s4d-inventory-movement-ledger-integrity",
            tenant_id=str(async_session.info["tenant_id"]),
        )
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
        notes="S4-D inventory movement ledger integrity gate",
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


async def _stock_for(async_session: AsyncSession, sku_id: uuid.UUID) -> InventoryStock:
    result = await async_session.execute(
        select(InventoryStock).where(InventoryStock.sku_id == sku_id)
    )
    return result.scalar_one()


async def _movements_for_order(
    async_session: AsyncSession, order_id: uuid.UUID
) -> list[InventoryMovement]:
    result = await async_session.execute(
        select(InventoryMovement)
        .where(InventoryMovement.reference_id == order_id)
        .order_by(InventoryMovement.created_at.asc(), InventoryMovement.id.asc())
    )
    return list(result.scalars().all())


async def _movements_for_sku(
    async_session: AsyncSession, sku_id: uuid.UUID
) -> list[InventoryMovement]:
    result = await async_session.execute(
        select(InventoryMovement)
        .where(InventoryMovement.sku_id == sku_id)
        .order_by(InventoryMovement.created_at.asc(), InventoryMovement.id.asc())
    )
    return list(result.scalars().all())


async def _ledger_entries_for(
    async_session: AsyncSession, *, reference_type: str, reference_id: uuid.UUID
) -> list[LedgerEntry]:
    result = await async_session.execute(
        select(LedgerEntry)
        .where(LedgerEntry.reference_type == reference_type)
        .where(LedgerEntry.reference_id == reference_id)
    )
    return list(result.scalars().all())


def _assert_movement_math(
    movement: InventoryMovement,
    *,
    movement_type: str,
    quantity: Decimal,
    before: Decimal,
    after: Decimal,
    reference_type: str,
    reference_id: uuid.UUID | None,
) -> None:
    assert movement.movement_type == movement_type
    assert movement.quantity == quantity
    assert movement.quantity_before == before
    assert movement.quantity_after == after
    assert movement.quantity_before + movement.quantity == movement.quantity_after
    assert movement.reference_type == reference_type
    assert movement.reference_id == reference_id


async def _create_fulfilled_order(
    async_session: AsyncSession,
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
    await fulfill_order(str(order.id), token=_token(async_session), db=async_session)
    await async_session.commit()
    await async_session.refresh(order)
    return sku, order


@asynccontextmanager
async def _tenant_session(tenant_schema: str, tenant_id: str):
    async with AsyncSessionLocal() as session:
        session.info["tenant_schema"] = tenant_schema
        session.info["tenant_id"] = tenant_id
        await session.execute(text(f'SET LOCAL search_path TO "{tenant_schema}", public'))
        yield session


async def _fulfill_in_independent_session(
    *, order_id: uuid.UUID, tenant_schema: str, tenant_id: str
) -> dict[str, Any]:
    try:
        async with _tenant_session(tenant_schema, tenant_id) as session:
            response = await fulfill_order(
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
async def test_fulfillment_movement_math_reference_and_type(async_session):
    await _prepare_inventory_schema(async_session)
    sku = await _create_sku_with_stock(
        async_session, sku_code="S4D-FULFILL", on_hand=Decimal("10.00")
    )
    order = await _create_order(
        async_session,
        status=OrderStatus.PAID,
        items=[("S4D-FULFILL", 3, Decimal("25.00"))],
    )

    await fulfill_order(str(order.id), token=_token(async_session), db=async_session)
    await async_session.commit()

    stock = await _stock_for(async_session, sku.id)
    movements = await _movements_for_order(async_session, order.id)
    assert stock.quantity_on_hand == Decimal("7.00")
    assert len(movements) == 1
    assert movements[0].sku_id == sku.id
    _assert_movement_math(
        movements[0],
        movement_type="deduction",
        quantity=Decimal("-3.00"),
        before=Decimal("10.00"),
        after=Decimal("7.00"),
        reference_type="order",
        reference_id=order.id,
    )


@pytest.mark.asyncio
async def test_return_movement_math_sequence_reference_and_type(async_session):
    await _prepare_inventory_schema(async_session)
    sku, order = await _create_fulfilled_order(async_session, sku_code="S4D-RETURN")

    await return_order(str(order.id), token=_token(async_session), db=async_session)
    await async_session.commit()

    stock = await _stock_for(async_session, sku.id)
    movements = await _movements_for_order(async_session, order.id)
    assert stock.quantity_on_hand == Decimal("10.00")
    assert [movement.movement_type for movement in movements] == ["deduction", "restock"]
    _assert_movement_math(
        movements[0],
        movement_type="deduction",
        quantity=Decimal("-3.00"),
        before=Decimal("10.00"),
        after=Decimal("7.00"),
        reference_type="order",
        reference_id=order.id,
    )
    _assert_movement_math(
        movements[1],
        movement_type="restock",
        quantity=Decimal("3.00"),
        before=Decimal("7.00"),
        after=Decimal("10.00"),
        reference_type="order",
        reference_id=order.id,
    )


@pytest.mark.asyncio
async def test_manual_adjustment_movements_use_manual_reference_and_math(async_session):
    await _prepare_inventory_schema(async_session)
    sku = await _create_sku_with_stock(
        async_session, sku_code="S4D-ADJUST", on_hand=Decimal("10.00")
    )

    await adjust_inventory(
        InventoryAdjustRequest(
            sku_code="S4D-ADJUST", quantity=Decimal("5.00"), reason="stocktake gain"
        ),
        request=_request(async_session),
        token=_token(async_session),
        db=async_session,
    )
    await adjust_inventory(
        InventoryAdjustRequest(
            sku_code="S4D-ADJUST", quantity=Decimal("-2.00"), reason="damage writeoff"
        ),
        request=_request(async_session),
        token=_token(async_session),
        db=async_session,
    )
    await async_session.commit()

    stock = await _stock_for(async_session, sku.id)
    movements = await _movements_for_sku(async_session, sku.id)
    movement_by_quantity = {movement.quantity: movement for movement in movements}
    assert stock.quantity_on_hand == Decimal("13.00")
    assert len(movements) == 2
    _assert_movement_math(
        movement_by_quantity[Decimal("5.00")],
        movement_type="adjustment",
        quantity=Decimal("5.00"),
        before=Decimal("10.00"),
        after=Decimal("15.00"),
        reference_type="manual",
        reference_id=None,
    )
    _assert_movement_math(
        movement_by_quantity[Decimal("-2.00")],
        movement_type="adjustment",
        quantity=Decimal("-2.00"),
        before=Decimal("15.00"),
        after=Decimal("13.00"),
        reference_type="manual",
        reference_id=None,
    )


@pytest.mark.asyncio
async def test_failed_fulfillment_writes_no_orphan_movement(async_session):
    await _prepare_inventory_schema(async_session)
    sku = await _create_sku_with_stock(
        async_session, sku_code="S4D-SHORT", on_hand=Decimal("2.00")
    )
    order = await _create_order(
        async_session,
        status=OrderStatus.PAID,
        items=[("S4D-SHORT", 3, Decimal("25.00"))],
    )
    sku_id = sku.id
    order_id = order.id

    with pytest.raises(HTTPException) as exc:
        await fulfill_order(str(order_id), token=_token(async_session), db=async_session)

    assert exc.value.status_code == 409
    stock = await _stock_for(async_session, sku_id)
    movements = await _movements_for_order(async_session, order_id)
    assert stock.quantity_on_hand == Decimal("2.00")
    assert movements == []


@pytest.mark.asyncio
async def test_failed_return_writes_no_orphan_restock_or_refund_ledger(async_session):
    await _prepare_inventory_schema(async_session)
    sku, order = await _create_fulfilled_order(async_session, sku_code="S4D-RETURN-FAIL")
    order_id = order.id
    stock = await _stock_for(async_session, sku.id)
    stock.is_deleted = True
    await async_session.commit()

    with pytest.raises(HTTPException) as exc:
        await return_order(str(order_id), token=_token(async_session), db=async_session)

    movements = await _movements_for_order(async_session, order_id)
    refund_entries = await _ledger_entries_for(
        async_session, reference_type="refund", reference_id=order_id
    )
    assert exc.value.status_code == 409
    assert [movement.movement_type for movement in movements] == ["deduction"]
    assert refund_entries == []


@pytest.mark.asyncio
async def test_multi_item_fulfillment_writes_independent_movements(async_session):
    await _prepare_inventory_schema(async_session)
    sku_a = await _create_sku_with_stock(
        async_session, sku_code="S4D-MULTI-A", on_hand=Decimal("10.00")
    )
    sku_b = await _create_sku_with_stock(
        async_session, sku_code="S4D-MULTI-B", on_hand=Decimal("8.00")
    )
    order = await _create_order(
        async_session,
        status=OrderStatus.PAID,
        items=[
            ("S4D-MULTI-A", 3, Decimal("25.00")),
            ("S4D-MULTI-B", 4, Decimal("10.00")),
        ],
    )

    await fulfill_order(str(order.id), token=_token(async_session), db=async_session)
    await async_session.commit()

    movements = await _movements_for_order(async_session, order.id)
    by_sku = {movement.sku_id: movement for movement in movements}
    assert set(by_sku) == {sku_a.id, sku_b.id}
    assert len(movements) == 2
    _assert_movement_math(
        by_sku[sku_a.id],
        movement_type="deduction",
        quantity=Decimal("-3.00"),
        before=Decimal("10.00"),
        after=Decimal("7.00"),
        reference_type="order",
        reference_id=order.id,
    )
    _assert_movement_math(
        by_sku[sku_b.id],
        movement_type="deduction",
        quantity=Decimal("-4.00"),
        before=Decimal("8.00"),
        after=Decimal("4.00"),
        reference_type="order",
        reference_id=order.id,
    )


@pytest.mark.asyncio
async def test_concurrent_fulfillment_writes_one_consistent_deduction(async_session):
    await _prepare_inventory_schema(async_session)
    tenant_schema = async_session.info["tenant_schema"]
    tenant_id = str(async_session.info["tenant_id"])
    sku = await _create_sku_with_stock(
        async_session, sku_code="S4D-CONCURRENT", on_hand=Decimal("5.00")
    )
    order_a = await _create_order(
        async_session,
        status=OrderStatus.PAID,
        items=[("S4D-CONCURRENT", 5, Decimal("25.00"))],
    )
    order_b = await _create_order(
        async_session,
        status=OrderStatus.PAID,
        items=[("S4D-CONCURRENT", 5, Decimal("25.00"))],
    )
    sku_id = sku.id
    order_ids = {order_a.id, order_b.id}

    results = await asyncio.gather(
        _fulfill_in_independent_session(
            order_id=order_a.id, tenant_schema=tenant_schema, tenant_id=tenant_id
        ),
        _fulfill_in_independent_session(
            order_id=order_b.id, tenant_schema=tenant_schema, tenant_id=tenant_id
        ),
    )

    await _reset_reader(async_session)
    stock = await _stock_for(async_session, sku_id)
    movements = await _movements_for_sku(async_session, sku_id)
    assert sum(1 for result in results if result["ok"]) == 1
    assert stock.quantity_on_hand == Decimal("0.00")
    assert len(movements) == 1
    _assert_movement_math(
        movements[0],
        movement_type="deduction",
        quantity=Decimal("-5.00"),
        before=Decimal("5.00"),
        after=Decimal("0.00"),
        reference_type="order",
        reference_id=movements[0].reference_id,
    )
    assert movements[0].reference_id in order_ids
    assert abs(movements[0].quantity) <= Decimal("5.00")


@pytest.mark.asyncio
async def test_tenant_isolation_for_movement_ledger(async_session):
    await _prepare_inventory_schema(async_session)
    tenant_schema = async_session.info["tenant_schema"]
    shadow_schema = "t_s4d_movement_ledger_other"
    sku = await _create_sku_with_stock(
        async_session, sku_code="S4D-ISO", on_hand=Decimal("10.00")
    )
    order = await _create_order(
        async_session,
        status=OrderStatus.PAID,
        items=[("S4D-ISO", 3, Decimal("25.00"))],
    )
    await async_session.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{shadow_schema}"'))
    await async_session.execute(
        text(
            f'''
            CREATE TABLE IF NOT EXISTS "{shadow_schema}".inventory_movements (
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
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            '''
        )
    )
    await async_session.execute(
        text(
            f'CREATE TABLE IF NOT EXISTS "{shadow_schema}".inventory_stocks '
            '(sku_id UUID PRIMARY KEY, quantity_on_hand NUMERIC(12, 2) NOT NULL)'
        )
    )
    await async_session.execute(
        text(
            f'TRUNCATE TABLE "{shadow_schema}".inventory_movements, '
            f'"{shadow_schema}".inventory_stocks'
        )
    )
    await async_session.execute(
        text(
            f'INSERT INTO "{shadow_schema}".inventory_stocks '
            '(sku_id, quantity_on_hand) VALUES (:sku_id, :quantity)'
        ),
        {"sku_id": sku.id, "quantity": Decimal("99.00")},
    )
    await async_session.commit()
    await async_session.execute(text(f'SET LOCAL search_path TO "{tenant_schema}", public'))

    await fulfill_order(str(order.id), token=_token(async_session), db=async_session)
    await async_session.commit()

    stock_a = await _stock_for(async_session, sku.id)
    movements_a = await _movements_for_order(async_session, order.id)
    stock_b = await async_session.execute(
        text(f'SELECT quantity_on_hand FROM "{shadow_schema}".inventory_stocks WHERE sku_id = :sku_id'),
        {"sku_id": sku.id},
    )
    movements_b = await async_session.execute(
        text(f'SELECT count(*) FROM "{shadow_schema}".inventory_movements')
    )
    assert stock_a.quantity_on_hand == Decimal("7.00")
    assert len(movements_a) == 1
    assert stock_b.scalar_one() == Decimal("99.00")
    assert movements_b.scalar_one() == 0


@pytest.mark.asyncio
async def test_movement_list_endpoint_matches_database(async_session):
    await _prepare_inventory_schema(async_session)
    sku = await _create_sku_with_stock(
        async_session, sku_code="S4D-LIST", on_hand=Decimal("10.00")
    )
    await adjust_inventory(
        InventoryAdjustRequest(
            sku_code="S4D-LIST", quantity=Decimal("5.00"), reason="list endpoint audit"
        ),
        request=_request(async_session),
        token=_token(async_session),
        db=async_session,
    )
    await async_session.commit()

    db_movement = (await _movements_for_sku(async_session, sku.id))[0]
    response = await list_inventory_logs(
        request=_request(async_session),
        page=1,
        size=20,
        sku_code="S4D-LIST",
        movement_type="adjustment",
        token=_token(async_session),
        db=async_session,
    )

    assert response.data.pagination["total"] == 1
    assert len(response.data.items) == 1
    item = response.data.items[0]
    assert item.id == str(db_movement.id)
    assert item.sku_id == str(db_movement.sku_id)
    assert item.sku_code == "S4D-LIST"
    assert item.movement_type == db_movement.movement_type
    assert item.quantity == db_movement.quantity
    assert item.quantity_before == db_movement.quantity_before
    assert item.quantity_after == db_movement.quantity_after
    assert item.reference_type == db_movement.reference_type
    assert item.reference_id is None
