"""S4-F business invariant closeout gate.

This suite uses real PostgreSQL tenant schemas and route/service handlers. It is
intentionally test-only: failures here should be reviewed as product invariant
findings rather than patched inside this closeout task.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.orders import cancel_order, confirm_order, fulfill_order, pay_order, return_order
from core.config import get_settings
from core.security import TokenPayload
from database.session import AsyncSessionLocal
from models.inventory_movement import InventoryMovement
from models.inventory_reservation import InventoryReservation
from models.inventory_stock import InventoryStock
from models.ledger import AccountType, LedgerEntry
from models.order import Order, OrderItem, OrderStatus
from models.sku import SKU
from scripts.bootstrap_tenant_schema import bootstrap


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


async def _prepare_closeout_schema(async_session: AsyncSession) -> None:
    schema = async_session.info["tenant_schema"]
    await async_session.execute(
        text(
            f'TRUNCATE TABLE "{schema}".inventory_movements, '
            f'"{schema}".inventory_reservations, '
            f'"{schema}".inventory_stocks, '
            f'"{schema}".ledger_entries, '
            f'"{schema}".order_items, '
            f'"{schema}".orders, '
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
        notes="S4-F business invariant closeout",
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


async def _reservations_for_order(
    async_session: AsyncSession, order_id: uuid.UUID
) -> list[InventoryReservation]:
    result = await async_session.execute(
        select(InventoryReservation)
        .where(InventoryReservation.order_id == order_id)
        .order_by(InventoryReservation.created_at.asc(), InventoryReservation.id.asc())
    )
    return list(result.scalars().all())


async def _movements_for_order(
    async_session: AsyncSession, order_id: uuid.UUID
) -> list[InventoryMovement]:
    result = await async_session.execute(
        select(InventoryMovement)
        .where(InventoryMovement.reference_id == order_id)
        .order_by(InventoryMovement.created_at.asc(), InventoryMovement.id.asc())
    )
    return list(result.scalars().all())


async def _ledger_entries_for_order(
    async_session: AsyncSession, order_id: uuid.UUID
) -> list[LedgerEntry]:
    return await _ledger_entries_for(async_session, reference_type="order", reference_id=order_id)


async def _ledger_entries_for(
    async_session: AsyncSession, *, reference_type: str, reference_id: uuid.UUID
) -> list[LedgerEntry]:
    result = await async_session.execute(
        select(LedgerEntry)
        .where(LedgerEntry.reference_type == reference_type)
        .where(LedgerEntry.reference_id == reference_id)
        .order_by(LedgerEntry.created_at.asc(), LedgerEntry.id.asc())
    )
    return list(result.scalars().all())


async def _ledger_signature(async_session: AsyncSession) -> list[tuple[str, Decimal, str, uuid.UUID]]:
    result = await async_session.execute(
        select(LedgerEntry).order_by(LedgerEntry.created_at.asc(), LedgerEntry.id.asc())
    )
    return [
        (entry.account_type.value, entry.amount, entry.reference_type, entry.reference_id)
        for entry in result.scalars().all()
    ]


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


async def _insert_sku_order_in_schema(
    *,
    tenant_schema: str,
    tenant_id: str,
    sku_code: str,
    quantity: int,
    on_hand: Decimal,
) -> tuple[uuid.UUID, uuid.UUID]:
    async with _tenant_session(tenant_schema, tenant_id) as session:
        sku_result = await session.execute(
            text(
                f'INSERT INTO "{tenant_schema}".skus '
                "(sku_code, name, unit, is_active) "
                "VALUES (:sku_code, :name, 'piece', true) RETURNING id"
            ),
            {"sku_code": sku_code, "name": f"SKU {sku_code}"},
        )
        sku_id = sku_result.scalar_one()
        await session.execute(
            text(
                f'INSERT INTO "{tenant_schema}".inventory_stocks '
                "(sku_id, quantity_on_hand, quantity_reserved) "
                "VALUES (:sku_id, :on_hand, 0.00)"
            ),
            {"sku_id": sku_id, "on_hand": on_hand},
        )
        order_result = await session.execute(
            text(
                f'INSERT INTO "{tenant_schema}".orders '
                "(wholesaler_id, retailer_id, status, total_amount, notes) "
                f"VALUES (:wholesaler_id, :retailer_id, 'draft'::\"{tenant_schema}\".order_status, "
                ":total_amount, 'S4-F tenant isolation invariant') RETURNING id"
            ),
            {
                "wholesaler_id": uuid.UUID(tenant_id),
                "retailer_id": uuid.uuid4(),
                "total_amount": Decimal(quantity) * Decimal("25.00"),
            },
        )
        order_id = order_result.scalar_one()
        await session.execute(
            text(
                f'INSERT INTO "{tenant_schema}".order_items '
                "(order_id, product_name, sku_code, quantity, unit_price, subtotal) "
                "VALUES (:order_id, :product_name, :sku_code, :quantity, 25.00, :subtotal)"
            ),
            {
                "order_id": order_id,
                "product_name": f"Product {sku_code}",
                "sku_code": sku_code,
                "quantity": quantity,
                "subtotal": Decimal(quantity) * Decimal("25.00"),
            },
        )
        await session.commit()
        return sku_id, order_id


async def _schema_stock_snapshot(
    *, tenant_schema: str, tenant_id: str, sku_id: uuid.UUID
) -> tuple[Decimal, Decimal, Decimal]:
    async with _tenant_session(tenant_schema, tenant_id) as session:
        result = await session.execute(
            text(
                f'SELECT quantity_on_hand, quantity_reserved, '
                f'quantity_on_hand - quantity_reserved AS available '
                f'FROM "{tenant_schema}".inventory_stocks WHERE sku_id = :sku_id'
            ),
            {"sku_id": sku_id},
        )
        row = result.one()
        return row.quantity_on_hand, row.quantity_reserved, row.available


async def _schema_reservation_count(
    *, tenant_schema: str, tenant_id: str, order_id: uuid.UUID
) -> int:
    async with _tenant_session(tenant_schema, tenant_id) as session:
        result = await session.execute(
            text(
                f'SELECT count(*) FROM "{tenant_schema}".inventory_reservations '
                "WHERE order_id = :order_id"
            ),
            {"order_id": order_id},
        )
        return result.scalar_one()


async def _confirm_in_tenant_schema(*, tenant_schema: str, tenant_id: str, order_id: uuid.UUID) -> None:
    for attempt in range(2):
        try:
            async with _tenant_session(tenant_schema, tenant_id) as session:
                await confirm_order(
                    str(order_id),
                    token=_token_for(tenant_id=tenant_id, tenant_schema=tenant_schema),
                    db=session,
                )
                await session.commit()
            return
        except Exception as exc:
            if attempt == 0 and "InvalidCachedStatementError" in str(exc):
                continue
            raise


@pytest.mark.asyncio
async def test_confirm_creates_reservation_and_insufficient_confirm_rolls_back(async_session):
    await _prepare_closeout_schema(async_session)
    sku = await _create_sku_with_stock(
        async_session, sku_code="S4F-CONFIRM", on_hand=Decimal("10.00")
    )
    order = await _create_order(
        async_session,
        status=OrderStatus.DRAFT,
        items=[("S4F-CONFIRM", 3, Decimal("25.00"))],
    )

    await confirm_order(str(order.id), token=_token(async_session), db=async_session)
    await async_session.commit()

    reservations = await _reservations_for_order(async_session, order.id)
    assert len(reservations) == 1
    assert reservations[0].status == "reserved"
    assert reservations[0].quantity == Decimal("3.00")
    assert await _stock_snapshot(async_session, sku.id) == (
        Decimal("10.00"),
        Decimal("3.00"),
        Decimal("7.00"),
    )

    short_sku = await _create_sku_with_stock(
        async_session, sku_code="S4F-CONFIRM-SHORT", on_hand=Decimal("2.00")
    )
    short_order = await _create_order(
        async_session,
        status=OrderStatus.DRAFT,
        items=[("S4F-CONFIRM-SHORT", 3, Decimal("25.00"))],
    )
    short_order_id = short_order.id
    short_sku_id = short_sku.id

    with pytest.raises(HTTPException) as exc:
        await confirm_order(str(short_order_id), token=_token(async_session), db=async_session)

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "INSUFFICIENT_AVAILABLE_STOCK"
    assert await _order_status(async_session, short_order_id) == OrderStatus.DRAFT.value
    assert await _reservations_for_order(async_session, short_order_id) == []
    assert await _stock_snapshot(async_session, short_sku_id) == (
        Decimal("2.00"),
        Decimal("0.00"),
        Decimal("2.00"),
    )


@pytest.mark.asyncio
async def test_pay_preserves_inventory_reservation_and_existing_phase5_ledger_semantics(async_session):
    await _prepare_closeout_schema(async_session)
    sku = await _create_sku_with_stock(
        async_session, sku_code="S4F-PAY", on_hand=Decimal("10.00")
    )
    order = await _create_order(
        async_session,
        status=OrderStatus.DRAFT,
        items=[("S4F-PAY", 3, Decimal("25.00"))],
    )

    await confirm_order(str(order.id), token=_token(async_session), db=async_session)
    await async_session.commit()
    before_stock = await _stock_snapshot(async_session, sku.id)
    before_reservations = await _reservations_for_order(async_session, order.id)

    await pay_order(str(order.id), token=_token(async_session), db=async_session)
    await async_session.commit()

    after_reservations = await _reservations_for_order(async_session, order.id)
    assert await _stock_snapshot(async_session, sku.id) == before_stock
    assert [(r.id, r.status, r.quantity) for r in after_reservations] == [
        (r.id, r.status, r.quantity) for r in before_reservations
    ]

    entries = await _ledger_entries_for_order(async_session, order.id)
    assert {entry.account_type: entry.amount for entry in entries} == {
        AccountType.CASH: Decimal("75.0000"),
        AccountType.RECEIVABLE: Decimal("-75.0000"),
    }


@pytest.mark.asyncio
async def test_unpaid_order_cannot_fulfill_and_inventory_is_unchanged(async_session):
    await _prepare_closeout_schema(async_session)
    sku = await _create_sku_with_stock(
        async_session, sku_code="S4F-UNPAID", on_hand=Decimal("10.00")
    )
    order = await _create_order(
        async_session,
        status=OrderStatus.DRAFT,
        items=[("S4F-UNPAID", 3, Decimal("25.00"))],
    )

    before_stock = await _stock_snapshot(async_session, sku.id)
    before_ledger = await _ledger_signature(async_session)
    with pytest.raises(HTTPException) as exc:
        await fulfill_order(str(order.id), token=_token(async_session), db=async_session)

    assert exc.value.status_code == 409
    assert await _order_status(async_session, order.id) == OrderStatus.DRAFT.value
    assert await _stock_snapshot(async_session, sku.id) == before_stock
    assert await _movements_for_order(async_session, order.id) == []
    assert await _ledger_signature(async_session) == before_ledger


@pytest.mark.asyncio
async def test_fulfill_consumes_owned_reservation_writes_movement_and_duplicate_is_stable(async_session):
    await _prepare_closeout_schema(async_session)
    sku = await _create_sku_with_stock(
        async_session, sku_code="S4F-FULFILL", on_hand=Decimal("10.00")
    )
    order = await _create_order(
        async_session,
        status=OrderStatus.DRAFT,
        items=[("S4F-FULFILL", 3, Decimal("25.00"))],
    )
    await confirm_order(str(order.id), token=_token(async_session), db=async_session)
    await async_session.commit()
    await pay_order(str(order.id), token=_token(async_session), db=async_session)
    await async_session.commit()
    ledger_before_fulfill = await _ledger_signature(async_session)

    await fulfill_order(str(order.id), token=_token(async_session), db=async_session)
    await async_session.commit()

    reservations = await _reservations_for_order(async_session, order.id)
    assert [reservation.status for reservation in reservations] == ["consumed"]
    assert await _stock_snapshot(async_session, sku.id) == (
        Decimal("7.00"),
        Decimal("0.00"),
        Decimal("7.00"),
    )
    movements = await _movements_for_order(async_session, order.id)
    assert len(movements) == 1
    assert movements[0].movement_type == "deduction"
    assert movements[0].quantity == Decimal("-3.00")
    assert movements[0].quantity_before == Decimal("10.00")
    assert movements[0].quantity_after == Decimal("7.00")
    assert await _ledger_signature(async_session) == ledger_before_fulfill

    before_duplicate_stock = await _stock_snapshot(async_session, sku.id)
    before_duplicate_movements = await _movements_for_order(async_session, order.id)
    with pytest.raises(HTTPException):
        await fulfill_order(str(order.id), token=_token(async_session), db=async_session)
    assert await _stock_snapshot(async_session, sku.id) == before_duplicate_stock
    assert await _movements_for_order(async_session, order.id) == before_duplicate_movements


@pytest.mark.asyncio
async def test_return_restores_on_hand_without_re_reserving_and_duplicate_is_stable(async_session):
    await _prepare_closeout_schema(async_session)
    sku = await _create_sku_with_stock(
        async_session, sku_code="S4F-RETURN", on_hand=Decimal("10.00")
    )
    order = await _create_order(
        async_session,
        status=OrderStatus.DRAFT,
        items=[("S4F-RETURN", 3, Decimal("25.00"))],
    )
    await confirm_order(str(order.id), token=_token(async_session), db=async_session)
    await async_session.commit()
    await pay_order(str(order.id), token=_token(async_session), db=async_session)
    await async_session.commit()
    await fulfill_order(str(order.id), token=_token(async_session), db=async_session)
    await async_session.commit()

    await return_order(str(order.id), token=_token(async_session), db=async_session)
    await async_session.commit()

    reservations = await _reservations_for_order(async_session, order.id)
    assert [reservation.status for reservation in reservations] == ["consumed"]
    assert await _stock_snapshot(async_session, sku.id) == (
        Decimal("10.00"),
        Decimal("0.00"),
        Decimal("10.00"),
    )
    movements = await _movements_for_order(async_session, order.id)
    assert [movement.movement_type for movement in movements] == ["deduction", "restock"]
    assert movements[1].quantity == Decimal("3.00")
    assert movements[1].quantity_before == Decimal("7.00")
    assert movements[1].quantity_after == Decimal("10.00")
    refund_entries = await _ledger_entries_for(
        async_session, reference_type="refund", reference_id=order.id
    )
    assert {entry.account_type: entry.amount for entry in refund_entries} == {
        AccountType.REVENUE: Decimal("75.0000"),
        AccountType.CASH: Decimal("-75.0000"),
    }

    before_duplicate_stock = await _stock_snapshot(async_session, sku.id)
    before_duplicate_movements = await _movements_for_order(async_session, order.id)
    before_duplicate_ledger = await _ledger_signature(async_session)
    with pytest.raises(HTTPException):
        await return_order(str(order.id), token=_token(async_session), db=async_session)
    assert await _stock_snapshot(async_session, sku.id) == before_duplicate_stock
    assert await _movements_for_order(async_session, order.id) == before_duplicate_movements
    assert await _ledger_signature(async_session) == before_duplicate_ledger


@pytest.mark.asyncio
async def test_cancel_confirmed_releases_reservation_and_paid_or_fulfilled_cancel_is_rejected(async_session):
    await _prepare_closeout_schema(async_session)
    confirmed_sku = await _create_sku_with_stock(
        async_session, sku_code="S4F-CANCEL-CONFIRMED", on_hand=Decimal("10.00")
    )
    confirmed_order = await _create_order(
        async_session,
        status=OrderStatus.DRAFT,
        items=[("S4F-CANCEL-CONFIRMED", 3, Decimal("25.00"))],
    )
    await confirm_order(str(confirmed_order.id), token=_token(async_session), db=async_session)
    await async_session.commit()

    await cancel_order(str(confirmed_order.id), token=_token(async_session), db=async_session)
    await async_session.commit()

    reservations = await _reservations_for_order(async_session, confirmed_order.id)
    assert [reservation.status for reservation in reservations] == ["released"]
    assert await _stock_snapshot(async_session, confirmed_sku.id) == (
        Decimal("10.00"),
        Decimal("0.00"),
        Decimal("10.00"),
    )
    assert await _movements_for_order(async_session, confirmed_order.id) == []

    paid_sku = await _create_sku_with_stock(
        async_session, sku_code="S4F-CANCEL-PAID", on_hand=Decimal("10.00")
    )
    paid_order = await _create_order(
        async_session,
        status=OrderStatus.DRAFT,
        items=[("S4F-CANCEL-PAID", 3, Decimal("25.00"))],
    )
    await confirm_order(str(paid_order.id), token=_token(async_session), db=async_session)
    await async_session.commit()
    await pay_order(str(paid_order.id), token=_token(async_session), db=async_session)
    await async_session.commit()
    paid_stock_before = await _stock_snapshot(async_session, paid_sku.id)
    paid_ledger_before = await _ledger_signature(async_session)
    with pytest.raises(HTTPException):
        await cancel_order(str(paid_order.id), token=_token(async_session), db=async_session)
    assert await _order_status(async_session, paid_order.id) == OrderStatus.PAID.value
    assert await _stock_snapshot(async_session, paid_sku.id) == paid_stock_before
    assert await _ledger_signature(async_session) == paid_ledger_before

    await fulfill_order(str(paid_order.id), token=_token(async_session), db=async_session)
    await async_session.commit()
    fulfilled_stock_before = await _stock_snapshot(async_session, paid_sku.id)
    fulfilled_ledger_before = await _ledger_signature(async_session)
    with pytest.raises(HTTPException):
        await cancel_order(str(paid_order.id), token=_token(async_session), db=async_session)
    assert await _order_status(async_session, paid_order.id) == OrderStatus.FULFILLED.value
    assert await _stock_snapshot(async_session, paid_sku.id) == fulfilled_stock_before
    assert await _ledger_signature(async_session) == fulfilled_ledger_before


@pytest.mark.asyncio
async def test_multi_item_confirm_and_fulfill_failures_roll_back_all_side_effects(async_session):
    await _prepare_closeout_schema(async_session)
    ok_sku = await _create_sku_with_stock(
        async_session, sku_code="S4F-MULTI-CONFIRM-OK", on_hand=Decimal("10.00")
    )
    short_sku = await _create_sku_with_stock(
        async_session, sku_code="S4F-MULTI-CONFIRM-SHORT", on_hand=Decimal("0.00")
    )
    ok_sku_id = ok_sku.id
    short_sku_id = short_sku.id
    confirm_order_with_shortage = await _create_order(
        async_session,
        status=OrderStatus.DRAFT,
        items=[
            ("S4F-MULTI-CONFIRM-OK", 2, Decimal("25.00")),
            ("S4F-MULTI-CONFIRM-SHORT", 1, Decimal("25.00")),
        ],
    )
    confirm_order_id = confirm_order_with_shortage.id

    with pytest.raises(HTTPException):
        await confirm_order(str(confirm_order_id), token=_token(async_session), db=async_session)
    assert await _order_status(async_session, confirm_order_id) == OrderStatus.DRAFT.value
    assert await _reservations_for_order(async_session, confirm_order_id) == []
    assert await _stock_snapshot(async_session, ok_sku_id) == (
        Decimal("10.00"),
        Decimal("0.00"),
        Decimal("10.00"),
    )
    assert await _stock_snapshot(async_session, short_sku_id) == (
        Decimal("0.00"),
        Decimal("0.00"),
        Decimal("0.00"),
    )

    first_sku = await _create_sku_with_stock(
        async_session, sku_code="S4F-MULTI-FULFILL-FIRST", on_hand=Decimal("10.00")
    )
    second_sku = await _create_sku_with_stock(
        async_session, sku_code="S4F-MULTI-FULFILL-SECOND", on_hand=Decimal("0.00")
    )
    first_sku_id = first_sku.id
    second_sku_id = second_sku.id
    fulfill_order_with_shortage = await _create_order(
        async_session,
        status=OrderStatus.PAID,
        items=[
            ("S4F-MULTI-FULFILL-FIRST", 2, Decimal("25.00")),
            ("S4F-MULTI-FULFILL-SECOND", 1, Decimal("25.00")),
        ],
    )
    fulfill_order_id = fulfill_order_with_shortage.id
    ledger_before = await _ledger_signature(async_session)

    with pytest.raises(HTTPException):
        await fulfill_order(str(fulfill_order_id), token=_token(async_session), db=async_session)
    assert await _order_status(async_session, fulfill_order_id) == OrderStatus.PAID.value
    assert await _stock_snapshot(async_session, first_sku_id) == (
        Decimal("10.00"),
        Decimal("0.00"),
        Decimal("10.00"),
    )
    assert await _stock_snapshot(async_session, second_sku_id) == (
        Decimal("0.00"),
        Decimal("0.00"),
        Decimal("0.00"),
    )
    assert await _movements_for_order(async_session, fulfill_order_id) == []
    assert await _ledger_signature(async_session) == ledger_before


@pytest.mark.asyncio
async def test_same_sku_code_isolated_across_two_tenant_schemas(async_session):
    await _prepare_closeout_schema(async_session)
    tenant_a_schema = async_session.info["tenant_schema"]
    tenant_a_id = str(async_session.info["tenant_id"])
    tenant_b_schema = f"t_s4f_iso_{uuid.uuid4().hex[:12]}"
    tenant_b_id = str(uuid.uuid4())
    settings = get_settings()

    try:
        await bootstrap(tenant_b_schema, settings.DATABASE_URL)
        sku_a_id, order_a_id = await _insert_sku_order_in_schema(
            tenant_schema=tenant_a_schema,
            tenant_id=tenant_a_id,
            sku_code="S4F-SAME-SKU",
            quantity=3,
            on_hand=Decimal("10.00"),
        )
        sku_b_id, order_b_id = await _insert_sku_order_in_schema(
            tenant_schema=tenant_b_schema,
            tenant_id=tenant_b_id,
            sku_code="S4F-SAME-SKU",
            quantity=4,
            on_hand=Decimal("20.00"),
        )

        await _confirm_in_tenant_schema(
            tenant_schema=tenant_a_schema, tenant_id=tenant_a_id, order_id=order_a_id
        )
        await _confirm_in_tenant_schema(
            tenant_schema=tenant_b_schema, tenant_id=tenant_b_id, order_id=order_b_id
        )

        assert await _schema_stock_snapshot(
            tenant_schema=tenant_a_schema, tenant_id=tenant_a_id, sku_id=sku_a_id
        ) == (Decimal("10.00"), Decimal("3.00"), Decimal("7.00"))
        assert await _schema_stock_snapshot(
            tenant_schema=tenant_b_schema, tenant_id=tenant_b_id, sku_id=sku_b_id
        ) == (Decimal("20.00"), Decimal("4.00"), Decimal("16.00"))

        count_a = await _schema_reservation_count(
            tenant_schema=tenant_a_schema, tenant_id=tenant_a_id, order_id=order_a_id
        )
        count_b = await _schema_reservation_count(
            tenant_schema=tenant_b_schema, tenant_id=tenant_b_id, order_id=order_b_id
        )
        assert count_a == 1
        assert count_b == 1
    finally:
        async with AsyncSessionLocal() as cleanup:
            await cleanup.execute(text(f'DROP SCHEMA IF EXISTS "{tenant_b_schema}" CASCADE'))
            await cleanup.commit()
