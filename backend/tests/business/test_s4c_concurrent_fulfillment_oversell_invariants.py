"""S4-C1 audit tests for concurrent fulfillment oversell invariants.

These tests use real database sessions. Each concurrent fulfillment call uses an
independent AsyncSession so row locks, transaction rollback, and movement writes
exercise the production database path.
"""

from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.orders import fulfill_order
from core.security import TokenPayload
from database.session import AsyncSessionLocal
from models.inventory_stock import InventoryStock
from models.order import Order, OrderItem, OrderStatus
from models.sku import SKU
from tests.catalog_identity_helpers import create_sku_with_catalog, stable_order_items


def _tenant_id(async_session: AsyncSession) -> uuid.UUID:
    return uuid.UUID(str(async_session.info["tenant_id"]))


def _token(*, tenant_id: str, tenant_schema: str) -> TokenPayload:
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
        notes="S4-C1 concurrent fulfillment oversell invariant audit",
    )
    order.items = await stable_order_items(async_session, items)
    async_session.add(order)
    await async_session.commit()
    await async_session.refresh(order)
    return order


@asynccontextmanager
async def _tenant_session(tenant_schema: str, tenant_id: str):
    async with AsyncSessionLocal() as session:
        session.info["tenant_schema"] = tenant_schema
        session.info["tenant_id"] = tenant_id
        await session.execute(text(f'SET LOCAL search_path TO "{tenant_schema}", public'))
        yield session


async def _fulfill_in_independent_session(
    *,
    order_id: uuid.UUID,
    tenant_schema: str,
    tenant_id: str,
) -> dict[str, Any]:
    try:
        async with _tenant_session(tenant_schema, tenant_id) as session:
            response = await fulfill_order(
                str(order_id),
                token=_token(tenant_id=tenant_id, tenant_schema=tenant_schema),
                db=session,
            )
            await session.commit()
            return {"ok": True, "status": response.data["status"]}
    except HTTPException as exc:
        return {"ok": False, "status_code": exc.status_code, "detail": exc.detail}


async def _run_concurrent_fulfillments(
    *,
    order_ids: list[uuid.UUID],
    tenant_schema: str,
    tenant_id: str,
) -> list[dict[str, Any]]:
    return await asyncio.gather(
        *[
            _fulfill_in_independent_session(
                order_id=order_id,
                tenant_schema=tenant_schema,
                tenant_id=tenant_id,
            )
            for order_id in order_ids
        ]
    )


async def _stock_quantity(async_session: AsyncSession, sku_id: uuid.UUID) -> Decimal:
    result = await async_session.execute(
        text("SELECT quantity_on_hand FROM inventory_stocks WHERE sku_id = :sku_id"),
        {"sku_id": sku_id},
    )
    return result.scalar_one()


async def _order_status(async_session: AsyncSession, order_id: uuid.UUID) -> str:
    result = await async_session.execute(
        text("SELECT status::text FROM orders WHERE id = :order_id"),
        {"order_id": order_id},
    )
    return result.scalar_one()


async def _deduction_movements(
    async_session: AsyncSession,
    *,
    order_ids: list[uuid.UUID] | None = None,
    sku_id: uuid.UUID | None = None,
) -> list[tuple[uuid.UUID, Decimal]]:
    filters = ["movement_type = 'deduction'"]
    params: dict[str, Any] = {}
    if order_ids is not None:
        filters.append("reference_id = ANY(:order_ids)")
        params["order_ids"] = order_ids
    if sku_id is not None:
        filters.append("sku_id = :sku_id")
        params["sku_id"] = sku_id

    result = await async_session.execute(
        text(
            "SELECT reference_id, quantity FROM inventory_movements "
            f"WHERE {' AND '.join(filters)} "
            "ORDER BY created_at ASC, id ASC"
        ),
        params,
    )
    return [(row.reference_id, row.quantity) for row in result.fetchall()]


async def _reset_reader(async_session: AsyncSession) -> None:
    await async_session.rollback()
    await async_session.execute(
        text(f'SET LOCAL search_path TO "{async_session.info["tenant_schema"]}", public')
    )


def _success_count(results: list[dict[str, Any]]) -> int:
    return sum(1 for result in results if result["ok"])


async def _prepare_shadow_tenant_stock(
    async_session: AsyncSession,
    *,
    schema: str,
    sku_code: str,
    on_hand: Decimal,
) -> uuid.UUID:
    await async_session.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
    await async_session.execute(
        text(
            f'''
            CREATE TABLE IF NOT EXISTS "{schema}".skus (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                sku_code VARCHAR(64) NOT NULL UNIQUE,
                name TEXT NOT NULL,
                unit VARCHAR(32) NOT NULL DEFAULT 'piece',
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            '''
        )
    )
    await async_session.execute(
        text(
            f'''
            CREATE TABLE IF NOT EXISTS "{schema}".inventory_stocks (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                sku_id UUID NOT NULL,
                quantity_on_hand NUMERIC(12, 2) NOT NULL DEFAULT 0,
                quantity_reserved NUMERIC(12, 2) NOT NULL DEFAULT 0,
                is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            '''
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
    sku_id = uuid.uuid4()
    await async_session.execute(
        text(
            f'INSERT INTO "{schema}".skus (id, sku_code, name, unit, is_active) '
            "VALUES (:sku_id, :sku_code, :name, 'piece', TRUE)"
        ),
        {"sku_id": sku_id, "sku_code": sku_code, "name": f"SKU {sku_code}"},
    )
    await async_session.execute(
        text(
            f'INSERT INTO "{schema}".inventory_stocks '
            "(sku_id, quantity_on_hand, quantity_reserved) VALUES (:sku_id, :quantity, 0)"
        ),
        {"sku_id": sku_id, "quantity": on_hand},
    )
    await async_session.commit()
    return sku_id


@pytest.mark.asyncio
async def test_same_sku_two_paid_orders_stock_only_enough_for_one(async_session):
    await _prepare_inventory_schema(async_session)
    tenant_schema = async_session.info["tenant_schema"]
    tenant_id = str(async_session.info["tenant_id"])
    sku = await _create_sku_with_stock(
        async_session, sku_code="S4C-ONE", on_hand=Decimal("5.00")
    )
    order_a = await _create_order(
        async_session,
        status=OrderStatus.PAID,
        items=[("S4C-ONE", 5, Decimal("25.00"))],
    )
    order_b = await _create_order(
        async_session,
        status=OrderStatus.PAID,
        items=[("S4C-ONE", 5, Decimal("25.00"))],
    )
    sku_id = sku.id
    order_a_id = order_a.id
    order_b_id = order_b.id

    results = await _run_concurrent_fulfillments(
        order_ids=[order_a_id, order_b_id], tenant_schema=tenant_schema, tenant_id=tenant_id
    )

    await _reset_reader(async_session)
    statuses = [
        await _order_status(async_session, order_a_id),
        await _order_status(async_session, order_b_id),
    ]
    movements = await _deduction_movements(
        async_session, order_ids=[order_a_id, order_b_id], sku_id=sku_id
    )
    assert _success_count(results) == 1
    assert statuses.count(OrderStatus.FULFILLED.value) == 1
    assert statuses.count(OrderStatus.PAID.value) == 1
    assert await _stock_quantity(async_session, sku_id) == Decimal("0.00")
    assert len(movements) == 1
    assert sum(quantity for _, quantity in movements) == Decimal("-5.00")


@pytest.mark.asyncio
async def test_same_sku_two_paid_orders_stock_enough_for_both(async_session):
    await _prepare_inventory_schema(async_session)
    tenant_schema = async_session.info["tenant_schema"]
    tenant_id = str(async_session.info["tenant_id"])
    sku = await _create_sku_with_stock(
        async_session, sku_code="S4C-BOTH", on_hand=Decimal("10.00")
    )
    order_a = await _create_order(
        async_session,
        status=OrderStatus.PAID,
        items=[("S4C-BOTH", 5, Decimal("25.00"))],
    )
    order_b = await _create_order(
        async_session,
        status=OrderStatus.PAID,
        items=[("S4C-BOTH", 5, Decimal("25.00"))],
    )
    sku_id = sku.id
    order_a_id = order_a.id
    order_b_id = order_b.id

    results = await _run_concurrent_fulfillments(
        order_ids=[order_a_id, order_b_id], tenant_schema=tenant_schema, tenant_id=tenant_id
    )

    await _reset_reader(async_session)
    movements = await _deduction_movements(
        async_session, order_ids=[order_a_id, order_b_id], sku_id=sku_id
    )
    assert _success_count(results) == 2
    assert await _order_status(async_session, order_a_id) == OrderStatus.FULFILLED.value
    assert await _order_status(async_session, order_b_id) == OrderStatus.FULFILLED.value
    assert await _stock_quantity(async_session, sku_id) == Decimal("0.00")
    assert len(movements) == 2
    assert sum(quantity for _, quantity in movements) == Decimal("-10.00")


@pytest.mark.asyncio
async def test_multi_item_order_competing_with_single_item_rolls_back_loser(async_session):
    await _prepare_inventory_schema(async_session)
    tenant_schema = async_session.info["tenant_schema"]
    tenant_id = str(async_session.info["tenant_id"])
    sku_a = await _create_sku_with_stock(
        async_session, sku_code="S4C-MULTI-A", on_hand=Decimal("5.00")
    )
    sku_b = await _create_sku_with_stock(
        async_session, sku_code="S4C-MULTI-B", on_hand=Decimal("5.00")
    )
    multi_order = await _create_order(
        async_session,
        status=OrderStatus.PAID,
        items=[
            ("S4C-MULTI-A", 5, Decimal("25.00")),
            ("S4C-MULTI-B", 5, Decimal("10.00")),
        ],
    )
    single_order = await _create_order(
        async_session,
        status=OrderStatus.PAID,
        items=[("S4C-MULTI-A", 5, Decimal("25.00"))],
    )
    sku_a_id = sku_a.id
    sku_b_id = sku_b.id
    multi_order_id = multi_order.id
    single_order_id = single_order.id

    results = await _run_concurrent_fulfillments(
        order_ids=[multi_order_id, single_order_id],
        tenant_schema=tenant_schema,
        tenant_id=tenant_id,
    )

    await _reset_reader(async_session)
    multi_status = await _order_status(async_session, multi_order_id)
    single_status = await _order_status(async_session, single_order_id)
    multi_movements = await _deduction_movements(async_session, order_ids=[multi_order_id])
    single_movements = await _deduction_movements(async_session, order_ids=[single_order_id])
    stock_a = await _stock_quantity(async_session, sku_a_id)
    stock_b = await _stock_quantity(async_session, sku_b_id)

    assert _success_count(results) == 1
    assert {multi_status, single_status} == {OrderStatus.FULFILLED.value, OrderStatus.PAID.value}
    assert stock_a == Decimal("0.00")
    assert stock_b in {Decimal("0.00"), Decimal("5.00")}
    if multi_status == OrderStatus.PAID.value:
        assert multi_movements == []
        assert single_movements == [(single_order_id, Decimal("-5.00"))]
        assert stock_b == Decimal("5.00")
    else:
        assert len(multi_movements) == 2
        assert sum(quantity for _, quantity in multi_movements) == Decimal("-10.00")
        assert single_movements == []
        assert stock_b == Decimal("0.00")


@pytest.mark.asyncio
async def test_duplicate_fulfillment_race_on_same_order_deducts_once(async_session):
    await _prepare_inventory_schema(async_session)
    tenant_schema = async_session.info["tenant_schema"]
    tenant_id = str(async_session.info["tenant_id"])
    sku = await _create_sku_with_stock(
        async_session, sku_code="S4C-DUP", on_hand=Decimal("10.00")
    )
    order = await _create_order(
        async_session,
        status=OrderStatus.PAID,
        items=[("S4C-DUP", 5, Decimal("25.00"))],
    )
    sku_id = sku.id
    order_id = order.id

    results = await _run_concurrent_fulfillments(
        order_ids=[order_id, order_id], tenant_schema=tenant_schema, tenant_id=tenant_id
    )

    await _reset_reader(async_session)
    movements = await _deduction_movements(async_session, order_ids=[order_id], sku_id=sku_id)
    assert _success_count(results) == 1
    assert await _order_status(async_session, order_id) == OrderStatus.FULFILLED.value
    assert await _stock_quantity(async_session, sku_id) == Decimal("5.00")
    assert len(movements) == 1
    assert sum(quantity for _, quantity in movements) == Decimal("-5.00")


@pytest.mark.asyncio
async def test_tenant_isolation_under_concurrent_fulfillment(async_session):
    await _prepare_inventory_schema(async_session)
    tenant_schema = async_session.info["tenant_schema"]
    tenant_id = str(async_session.info["tenant_id"])
    shadow_schema = "t_s4c_concurrent_other"
    sku = await _create_sku_with_stock(
        async_session, sku_code="S4C-ISO", on_hand=Decimal("5.00")
    )
    shadow_sku_id = await _prepare_shadow_tenant_stock(
        async_session,
        schema=shadow_schema,
        sku_code="S4C-ISO",
        on_hand=Decimal("99.00"),
    )
    await async_session.execute(text(f'SET LOCAL search_path TO "{tenant_schema}", public'))
    order_a = await _create_order(
        async_session,
        status=OrderStatus.PAID,
        items=[("S4C-ISO", 5, Decimal("25.00"))],
    )
    order_b = await _create_order(
        async_session,
        status=OrderStatus.PAID,
        items=[("S4C-ISO", 5, Decimal("25.00"))],
    )
    sku_id = sku.id
    order_a_id = order_a.id
    order_b_id = order_b.id

    results = await _run_concurrent_fulfillments(
        order_ids=[order_a_id, order_b_id], tenant_schema=tenant_schema, tenant_id=tenant_id
    )

    await _reset_reader(async_session)
    shadow_stock = await async_session.execute(
        text(
            f'SELECT quantity_on_hand FROM "{shadow_schema}".inventory_stocks '
            "WHERE sku_id = :sku_id"
        ),
        {"sku_id": shadow_sku_id},
    )
    shadow_movements = await async_session.execute(
        text(f'SELECT count(*) FROM "{shadow_schema}".inventory_movements')
    )
    movements = await _deduction_movements(
        async_session, order_ids=[order_a_id, order_b_id], sku_id=sku_id
    )

    assert _success_count(results) == 1
    assert await _stock_quantity(async_session, sku_id) == Decimal("0.00")
    assert len(movements) == 1
    assert shadow_stock.scalar_one() == Decimal("99.00")
    assert shadow_movements.scalar_one() == 0
