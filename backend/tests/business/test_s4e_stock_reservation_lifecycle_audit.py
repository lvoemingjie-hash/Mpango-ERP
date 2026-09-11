"""S4-E3 stock reservation ownership lifecycle invariants.

These tests exercise real tenant DB sessions and route handlers. The
`inventory_reservations` table is the source of truth for ownership;
`inventory_stocks.quantity_reserved` is the aggregate fast-read projection.
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

from api.v1.orders import cancel_order, confirm_order, fulfill_order, pay_order, return_order
from core.security import TokenPayload
from database.session import AsyncSessionLocal
from models.inventory_movement import InventoryMovement
from models.inventory_reservation import InventoryReservation
from models.inventory_stock import InventoryStock
from models.order import Order, OrderItem, OrderStatus
from models.sku import SKU
from tests.catalog_identity_helpers import create_sku_with_catalog, stable_order_items
from schemas.order import PayOrderRequest


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
            f'TRUNCATE TABLE "{schema}".inventory_movements, '
            f'"{schema}".inventory_reservations, '
            f'"{schema}".inventory_stocks, '
            f'"{schema}".skus RESTART IDENTITY CASCADE'
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
    sku = await create_sku_with_catalog(
        async_session, sku_code=sku_code, name=f"SKU {sku_code}"
    )
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
    updated_by: uuid.UUID | None = None,
) -> Order:
    total = sum(Decimal(quantity) * unit_price for _, quantity, unit_price in items)
    retailer_id = uuid.uuid4()
    await async_session.execute(
        text(
            "INSERT INTO public.wholesalers (id, code, name, status, is_deleted) "
            "VALUES (:id, 'BUSINESSTEST', 'Business Test Wholesaler', "
            "'active', false) ON CONFLICT DO NOTHING"
        ),
        {"id": _tenant_id(async_session)},
    )
    await async_session.execute(
        text(
            "INSERT INTO public.retailers (id, phone, name, is_deleted) "
            "VALUES (:id, :phone, 'S4E Retailer', false)"
        ),
        {"id": retailer_id, "phone": f"+254{str(retailer_id.int)[:10]}"},
    )
    await async_session.execute(
        text(
            "INSERT INTO public.wholesaler_retailer_bindings "
            "(wholesaler_id, retailer_id, status, outstanding_balance, is_deleted) "
            "VALUES (:wholesaler_id, :retailer_id, 'active', :total, false)"
        ),
        {
            "wholesaler_id": _tenant_id(async_session),
            "retailer_id": retailer_id,
            "total": total,
        },
    )
    order = Order(
        wholesaler_id=_tenant_id(async_session),
        retailer_id=retailer_id,
        status=status,
        total_amount=total,
        notes="S4-E3 reservation ownership invariant",
        updated_by=updated_by,
    )
    order.items = await stable_order_items(async_session, items)
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


async def _reservations_for_order(
    async_session: AsyncSession, order_id: uuid.UUID
) -> list[InventoryReservation]:
    result = await async_session.execute(
        select(InventoryReservation)
        .where(InventoryReservation.order_id == order_id)
        .order_by(InventoryReservation.created_at.asc(), InventoryReservation.id.asc())
    )
    return list(result.scalars().all())


async def _reservation_count(
    async_session: AsyncSession,
    *,
    order_id: uuid.UUID | None = None,
    status: str | None = None,
) -> int:
    query = select(InventoryReservation)
    if order_id is not None:
        query = query.where(InventoryReservation.order_id == order_id)
    if status is not None:
        query = query.where(InventoryReservation.status == status)
    result = await async_session.execute(query)
    return len(result.scalars().all())


async def _movement_count(
    async_session: AsyncSession,
    *,
    sku_id: uuid.UUID | None = None,
    order_id: uuid.UUID | None = None,
) -> int:
    query = select(InventoryMovement)
    if sku_id is not None:
        query = query.where(InventoryMovement.sku_id == sku_id)
    if order_id is not None:
        query = query.where(InventoryMovement.reference_id == order_id)
    result = await async_session.execute(query)
    return len(result.scalars().all())


async def _order_status(async_session: AsyncSession, order_id: uuid.UUID) -> str:
    result = await async_session.execute(
        text("SELECT status::text FROM orders WHERE id = :order_id"),
        {"order_id": order_id},
    )
    return result.scalar_one()


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


async def _confirm_pay_fulfill(async_session: AsyncSession, order: Order) -> None:
    await confirm_order(str(order.id), token=_token(async_session), db=async_session)
    await async_session.commit()
    await pay_order(
        str(order.id),
        token=_token(async_session),
        db=async_session,
        payment_input=PayOrderRequest(amount=order.total_amount, method="cash"),
        x_idempotency_key=f"s4e-{order.id}",
    )
    await async_session.commit()
    await fulfill_order(str(order.id), token=_token(async_session), db=async_session)
    await async_session.commit()


@pytest.mark.asyncio
async def test_confirm_creates_owned_reservation_rows_and_updates_aggregate(async_session):
    await _prepare_inventory_schema(async_session)
    sku = await _create_sku_with_stock(
        async_session, sku_code="S4E3-CONFIRM", on_hand=Decimal("10.00")
    )
    order = await _create_order(
        async_session,
        status=OrderStatus.DRAFT,
        items=[("S4E3-CONFIRM", 3, Decimal("25.00"))],
    )

    await confirm_order(str(order.id), token=_token(async_session), db=async_session)
    await async_session.commit()

    reservations = await _reservations_for_order(async_session, order.id)
    assert len(reservations) == 1
    assert reservations[0].order_id == order.id
    assert reservations[0].order_item_id == order.items[0].id
    assert reservations[0].sku_id == sku.id
    assert reservations[0].sku_code == "S4E3-CONFIRM"
    assert reservations[0].quantity == Decimal("3.00")
    assert reservations[0].status == "reserved"
    assert await _stock_snapshot(async_session, sku.id) == (
        Decimal("10.00"),
        Decimal("3.00"),
        Decimal("7.00"),
    )


@pytest.mark.asyncio
async def test_confirm_insufficient_available_rolls_back_order_stock_and_reservations(async_session):
    await _prepare_inventory_schema(async_session)
    sku = await _create_sku_with_stock(
        async_session, sku_code="S4E3-CONFIRM-SHORT", on_hand=Decimal("2.00")
    )
    order = await _create_order(
        async_session,
        status=OrderStatus.DRAFT,
        items=[("S4E3-CONFIRM-SHORT", 3, Decimal("25.00"))],
    )
    order_id = order.id
    sku_id = sku.id

    with pytest.raises(HTTPException) as exc:
        await confirm_order(str(order_id), token=_token(async_session), db=async_session)

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "INSUFFICIENT_AVAILABLE_STOCK"
    assert await _order_status(async_session, order_id) == OrderStatus.DRAFT.value
    assert await _reservation_count(async_session, order_id=order_id) == 0
    assert await _stock_snapshot(async_session, sku_id) == (
        Decimal("2.00"),
        Decimal("0.00"),
        Decimal("2.00"),
    )


@pytest.mark.asyncio
async def test_concurrent_confirm_does_not_over_reserve_or_accept_excess_demand(async_session):
    await _prepare_inventory_schema(async_session)
    tenant_schema = async_session.info["tenant_schema"]
    tenant_id = str(async_session.info["tenant_id"])
    sku = await _create_sku_with_stock(
        async_session, sku_code="S4E3-CONCURRENT", on_hand=Decimal("5.00")
    )
    order_a = await _create_order(
        async_session,
        status=OrderStatus.DRAFT,
        items=[("S4E3-CONCURRENT", 5, Decimal("25.00"))],
    )
    order_b = await _create_order(
        async_session,
        status=OrderStatus.DRAFT,
        items=[("S4E3-CONCURRENT", 5, Decimal("25.00"))],
    )
    sku_id = sku.id

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
    assert await _stock_snapshot(async_session, sku_id) == (
        Decimal("5.00"),
        Decimal("5.00"),
        Decimal("0.00"),
    )
    assert await _reservation_count(async_session, status="reserved") == 1


@pytest.mark.asyncio
async def test_duplicate_confirm_does_not_create_duplicate_reservation_rows(async_session):
    await _prepare_inventory_schema(async_session)
    sku = await _create_sku_with_stock(
        async_session, sku_code="S4E3-DUP-CONFIRM", on_hand=Decimal("10.00")
    )
    order = await _create_order(
        async_session,
        status=OrderStatus.DRAFT,
        items=[("S4E3-DUP-CONFIRM", 3, Decimal("25.00"))],
    )

    await confirm_order(str(order.id), token=_token(async_session), db=async_session)
    await async_session.commit()
    with pytest.raises(HTTPException):
        await confirm_order(str(order.id), token=_token(async_session), db=async_session)

    assert await _reservation_count(async_session, order_id=order.id) == 1
    assert await _stock_snapshot(async_session, sku.id) == (
        Decimal("10.00"),
        Decimal("3.00"),
        Decimal("7.00"),
    )


@pytest.mark.asyncio
async def test_cancel_releases_only_this_order_reservation_rows(async_session):
    await _prepare_inventory_schema(async_session)
    sku = await _create_sku_with_stock(
        async_session, sku_code="S4E3-CANCEL", on_hand=Decimal("10.00")
    )
    order_a = await _create_order(
        async_session,
        status=OrderStatus.DRAFT,
        items=[("S4E3-CANCEL", 3, Decimal("25.00"))],
    )
    order_b = await _create_order(
        async_session,
        status=OrderStatus.DRAFT,
        items=[("S4E3-CANCEL", 2, Decimal("25.00"))],
    )
    await confirm_order(str(order_a.id), token=_token(async_session), db=async_session)
    await async_session.commit()
    await confirm_order(str(order_b.id), token=_token(async_session), db=async_session)
    await async_session.commit()

    await cancel_order(str(order_a.id), token=_token(async_session), db=async_session)
    await async_session.commit()

    reservations_a = await _reservations_for_order(async_session, order_a.id)
    reservations_b = await _reservations_for_order(async_session, order_b.id)
    assert [reservation.status for reservation in reservations_a] == ["released"]
    assert [reservation.status for reservation in reservations_b] == ["reserved"]
    assert await _stock_snapshot(async_session, sku.id) == (
        Decimal("10.00"),
        Decimal("2.00"),
        Decimal("8.00"),
    )


@pytest.mark.asyncio
async def test_duplicate_cancel_does_not_double_release_reservation(async_session):
    await _prepare_inventory_schema(async_session)
    sku = await _create_sku_with_stock(
        async_session, sku_code="S4E3-DUP-CANCEL", on_hand=Decimal("10.00")
    )
    order = await _create_order(
        async_session,
        status=OrderStatus.DRAFT,
        items=[("S4E3-DUP-CANCEL", 3, Decimal("25.00"))],
    )
    await confirm_order(str(order.id), token=_token(async_session), db=async_session)
    await async_session.commit()
    await cancel_order(str(order.id), token=_token(async_session), db=async_session)
    await async_session.commit()

    before = await _stock_snapshot(async_session, sku.id)
    with pytest.raises(HTTPException):
        await cancel_order(str(order.id), token=_token(async_session), db=async_session)

    assert await _reservation_count(async_session, order_id=order.id, status="released") == 1
    assert before == await _stock_snapshot(async_session, sku.id)


@pytest.mark.asyncio
async def test_fulfillment_consumes_only_this_order_reservation_and_deducts_on_hand(async_session):
    await _prepare_inventory_schema(async_session)
    sku = await _create_sku_with_stock(
        async_session, sku_code="S4E3-FULFILL", on_hand=Decimal("10.00")
    )
    fulfilled_order = await _create_order(
        async_session,
        status=OrderStatus.DRAFT,
        items=[("S4E3-FULFILL", 3, Decimal("25.00"))],
    )
    other_order = await _create_order(
        async_session,
        status=OrderStatus.DRAFT,
        items=[("S4E3-FULFILL", 2, Decimal("25.00"))],
    )
    await confirm_order(str(fulfilled_order.id), token=_token(async_session), db=async_session)
    await async_session.commit()
    await confirm_order(str(other_order.id), token=_token(async_session), db=async_session)
    await async_session.commit()
    await pay_order(
        str(fulfilled_order.id),
        token=_token(async_session),
        db=async_session,
        payment_input=PayOrderRequest(amount=fulfilled_order.total_amount, method="cash"),
        x_idempotency_key=f"s4e-{fulfilled_order.id}",
    )
    await async_session.commit()

    await fulfill_order(str(fulfilled_order.id), token=_token(async_session), db=async_session)
    await async_session.commit()

    fulfilled_reservations = await _reservations_for_order(async_session, fulfilled_order.id)
    other_reservations = await _reservations_for_order(async_session, other_order.id)
    assert [reservation.status for reservation in fulfilled_reservations] == ["consumed"]
    assert [reservation.status for reservation in other_reservations] == ["reserved"]
    assert await _stock_snapshot(async_session, sku.id) == (
        Decimal("7.00"),
        Decimal("2.00"),
        Decimal("5.00"),
    )


@pytest.mark.asyncio
async def test_direct_paid_order_with_no_reservation_preserves_unrelated_reservations(async_session):
    await _prepare_inventory_schema(async_session)
    sku = await _create_sku_with_stock(
        async_session, sku_code="S4E3-DIRECT-PAID", on_hand=Decimal("10.00")
    )
    reserved_order = await _create_order(
        async_session,
        status=OrderStatus.DRAFT,
        items=[("S4E3-DIRECT-PAID", 3, Decimal("25.00"))],
    )
    direct_paid_order = await _create_order(
        async_session,
        status=OrderStatus.PAID,
        items=[("S4E3-DIRECT-PAID", 3, Decimal("25.00"))],
        updated_by=uuid.uuid4(),
    )
    await confirm_order(str(reserved_order.id), token=_token(async_session), db=async_session)
    await async_session.commit()

    await fulfill_order(str(direct_paid_order.id), token=_token(async_session), db=async_session)
    await async_session.commit()

    assert await _reservation_count(async_session, order_id=direct_paid_order.id) == 0
    assert await _reservation_count(async_session, order_id=reserved_order.id, status="reserved") == 1
    assert await _stock_snapshot(async_session, sku.id) == (
        Decimal("7.00"),
        Decimal("3.00"),
        Decimal("4.00"),
    )
    assert await _order_status(async_session, reserved_order.id) == OrderStatus.CONFIRMED.value


@pytest.mark.asyncio
async def test_return_restores_on_hand_without_creating_reservation(async_session):
    await _prepare_inventory_schema(async_session)
    sku = await _create_sku_with_stock(
        async_session, sku_code="S4E3-RETURN", on_hand=Decimal("10.00")
    )
    order = await _create_order(
        async_session,
        status=OrderStatus.DRAFT,
        items=[("S4E3-RETURN", 3, Decimal("25.00"))],
    )
    await _confirm_pay_fulfill(async_session, order)

    await return_order(str(order.id), token=_token(async_session), db=async_session)
    await async_session.commit()

    assert await _stock_snapshot(async_session, sku.id) == (
        Decimal("10.00"),
        Decimal("0.00"),
        Decimal("10.00"),
    )
    assert await _reservation_count(async_session, order_id=order.id) == 1


@pytest.mark.asyncio
async def test_concurrent_fulfill_consumes_reservation_once_and_writes_one_movement(async_session):
    await _prepare_inventory_schema(async_session)
    tenant_schema = async_session.info["tenant_schema"]
    tenant_id = str(async_session.info["tenant_id"])
    sku = await _create_sku_with_stock(
        async_session, sku_code="S4E3-CONCURRENT-FULFILL", on_hand=Decimal("10.00")
    )
    order = await _create_order(
        async_session,
        status=OrderStatus.DRAFT,
        items=[("S4E3-CONCURRENT-FULFILL", 3, Decimal("25.00"))],
    )
    await confirm_order(str(order.id), token=_token(async_session), db=async_session)
    await async_session.commit()
    await pay_order(
        str(order.id),
        token=_token(async_session),
        db=async_session,
        payment_input=PayOrderRequest(amount=order.total_amount, method="cash"),
        x_idempotency_key=f"s4e-{order.id}",
    )
    await async_session.commit()

    results = await asyncio.gather(
        _fulfill_in_independent_session(
            order_id=order.id, tenant_schema=tenant_schema, tenant_id=tenant_id
        ),
        _fulfill_in_independent_session(
            order_id=order.id, tenant_schema=tenant_schema, tenant_id=tenant_id
        ),
    )

    await _reset_reader(async_session)
    assert sum(1 for result in results if result["ok"]) == 1
    assert await _reservation_count(async_session, order_id=order.id, status="consumed") == 1
    assert await _movement_count(async_session, order_id=order.id) == 1
    assert await _stock_snapshot(async_session, sku.id) == (
        Decimal("7.00"),
        Decimal("0.00"),
        Decimal("7.00"),
    )


@pytest.mark.asyncio
async def test_reservation_table_and_aggregate_stock_are_tenant_isolated(async_session):
    await _prepare_inventory_schema(async_session)
    tenant_schema = async_session.info["tenant_schema"]
    sku = await _create_sku_with_stock(
        async_session, sku_code="S4E3-ISO", on_hand=Decimal("10.00")
    )
    order = await _create_order(
        async_session,
        status=OrderStatus.DRAFT,
        items=[("S4E3-ISO", 3, Decimal("25.00"))],
    )

    await confirm_order(str(order.id), token=_token(async_session), db=async_session)
    await async_session.commit()

    other_schema = "t_s4e3_reservation_other"
    await async_session.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{other_schema}"'))
    await async_session.execute(text(f'SET LOCAL search_path TO "{tenant_schema}", public'))

    other_count = await async_session.execute(
        text(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema = :schema AND table_name = 'inventory_reservations'"
        ),
        {"schema": other_schema},
    )
    assert other_count.scalar_one() == 0
    assert await _stock_snapshot(async_session, sku.id) == (
        Decimal("10.00"),
        Decimal("3.00"),
        Decimal("7.00"),
    )


@pytest.mark.asyncio
async def test_reserve_release_and_consume_movement_boundaries(async_session):
    await _prepare_inventory_schema(async_session)
    sku = await _create_sku_with_stock(
        async_session, sku_code="S4E3-MOVEMENT-BOUNDARY", on_hand=Decimal("10.00")
    )
    cancel_order_owner = await _create_order(
        async_session,
        status=OrderStatus.DRAFT,
        items=[("S4E3-MOVEMENT-BOUNDARY", 2, Decimal("25.00"))],
    )
    fulfill_order_owner = await _create_order(
        async_session,
        status=OrderStatus.DRAFT,
        items=[("S4E3-MOVEMENT-BOUNDARY", 3, Decimal("25.00"))],
    )

    await confirm_order(str(cancel_order_owner.id), token=_token(async_session), db=async_session)
    await async_session.commit()
    await cancel_order(str(cancel_order_owner.id), token=_token(async_session), db=async_session)
    await async_session.commit()
    assert await _movement_count(async_session, sku_id=sku.id) == 0

    await confirm_order(str(fulfill_order_owner.id), token=_token(async_session), db=async_session)
    await async_session.commit()
    await pay_order(
        str(fulfill_order_owner.id),
        token=_token(async_session),
        db=async_session,
        payment_input=PayOrderRequest(
            amount=fulfill_order_owner.total_amount, method="cash"
        ),
        x_idempotency_key=f"s4e-{fulfill_order_owner.id}",
    )
    await async_session.commit()
    await fulfill_order(str(fulfill_order_owner.id), token=_token(async_session), db=async_session)
    await async_session.commit()

    assert await _movement_count(async_session, sku_id=sku.id) == 1
