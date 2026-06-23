from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import InventoryShortageError
from models.inventory_stock import InventoryStock
from models.inventory_movement import InventoryMovement, MovementType
from models.sku import SKU
from repositories.inventory_repository import InventoryRepository


class InventoryService:
    def __init__(self, inventory_repo: InventoryRepository | None = None) -> None:
        self._inventory_repo = inventory_repo or InventoryRepository()

    @staticmethod
    def _available(on_hand: Decimal, reserved: Decimal) -> Decimal:
        return on_hand - reserved

    async def get_stock_by_sku_code(self, db: AsyncSession, *, sku_code: str):
        row = await self._inventory_repo.get_stock_by_sku_code(db, sku_code=sku_code)
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "SKU_NOT_FOUND", "message": f"SKU '{sku_code}' not found"},
            )
        sku, stock = row
        if stock is None:
            stock = await self._inventory_repo.ensure_stock_row(db, sku_id=sku.id)
        return sku, stock

    async def list_stock(self, db: AsyncSession, *, page: int, size: int, sku_code: str | None, is_active: bool | None):
        rows, total = await self._inventory_repo.list_stock_paginated(db, page=page, size=size, sku_code=sku_code, is_active=is_active)
        normalized = []
        for sku, stock in rows:
            if stock is None:
                stock = await self._inventory_repo.ensure_stock_row(db, sku_id=sku.id)
            normalized.append((sku, stock))
        return normalized, total

    async def stock_view_for_order(self, db: AsyncSession, *, order_id: str):
        try:
            oid = uuid.UUID(order_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_ORDER_ID", "message": "Invalid order_id"},
            )

        sku_codes = await self._inventory_repo.list_sku_codes_for_order(db, order_id=oid)
        unique_codes = sorted({c for c in sku_codes if c})

        items = []
        for code in unique_codes:
            sku, stock = await self.get_stock_by_sku_code(db, sku_code=code)
            items.append((sku, stock))
        return items

    # ------------------------------------------------------------------
    # GAP 5 §3: Concurrency-safe stock deduction (SELECT FOR UPDATE)
    # ------------------------------------------------------------------

    async def deduct_stock(
        self,
        db: AsyncSession,
        *,
        sku_id: uuid.UUID,
        quantity: Decimal,
        sku_code: str = "UNKNOWN",
    ) -> InventoryStock:
        """
        Atomically deduct stock.  Must be called inside a transaction.

        Uses SELECT FOR UPDATE to acquire a row-level lock, preventing
        concurrent overselling.

        Raises:
            InventoryShortageError  when available < quantity
        """
        result = await db.execute(
            select(InventoryStock)
            .where(InventoryStock.sku_id == sku_id)
            .where(InventoryStock.is_deleted.is_(False))
            .with_for_update()
        )
        stock = result.scalar_one_or_none()

        if stock is None:
            stock = await self._inventory_repo.ensure_stock_row(db, sku_id=sku_id)
            # Re-lock the newly created row
            result = await db.execute(
                select(InventoryStock)
                .where(InventoryStock.id == stock.id)
                .with_for_update()
            )
            stock = result.scalar_one()

        available = stock.quantity_on_hand - stock.quantity_reserved
        if available < quantity:
            raise InventoryShortageError(
                sku_code=sku_code,
                available=float(available),
                requested=float(quantity),
            )

        stock.quantity_reserved = stock.quantity_reserved + quantity
        await db.flush()
        return stock

    async def deduct_on_fulfillment(
        self,
        db: AsyncSession,
        *,
        sku_code: str,
        quantity: Decimal,
        order_id: uuid.UUID,
        fulfilled_by: str | None = None,
    ) -> tuple[InventoryStock, InventoryMovement]:
        """Deduct on-hand stock for a fulfilled order and write a journal entry."""
        row = await self._inventory_repo.get_stock_by_sku_code(db, sku_code=sku_code)
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "SKU_NOT_FOUND", "message": f"SKU '{sku_code}' not found"},
            )

        sku, stock = row
        if stock is None:
            stock = await self._inventory_repo.ensure_stock_row(db, sku_id=sku.id)

        result = await db.execute(
            select(InventoryStock)
            .where(InventoryStock.id == stock.id)
            .where(InventoryStock.is_deleted.is_(False))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        stock = result.scalar_one()

        quantity = Decimal(str(quantity))
        quantity_before = stock.quantity_on_hand
        quantity_after = quantity_before - quantity
        if quantity_after < Decimal("0.00"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "INSUFFICIENT_STOCK",
                    "message": (
                        f"Insufficient stock for '{sku_code}': "
                        f"requested {quantity}, available {quantity_before}"
                    ),
                },
            )

        stock.quantity_on_hand = quantity_after

        fulfilled_by_uuid = None
        if fulfilled_by:
            try:
                fulfilled_by_uuid = uuid.UUID(str(fulfilled_by))
            except Exception:
                pass

        movement = InventoryMovement(
            sku_id=sku.id,
            movement_type="deduction",
            quantity=-quantity,
            quantity_before=quantity_before,
            quantity_after=quantity_after,
            reason=f"Order fulfillment for order {order_id} SKU {sku_code}",
            reference_type="order",
            reference_id=order_id,
            created_by=fulfilled_by_uuid,
        )
        db.add(movement)
        await db.flush()
        return stock, movement

    async def adjust_stock(
        self,
        db: AsyncSession,
        *,
        sku_code: str,
        quantity: Decimal,
        reason: str,
        adjusted_by: str | None = None,
    ) -> tuple["InventoryStock", "InventoryMovement"]:
        """
        Manual stock adjustment (stocktake / damage / correction).
        Positive quantity = add stock, negative = remove stock.
        Creates a movement journal entry for audit trail.
        Uses SELECT FOR UPDATE to prevent concurrent issues.
        """
        # Look up SKU
        row = await self._inventory_repo.get_stock_by_sku_code(db, sku_code=sku_code)
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "SKU_NOT_FOUND", "message": f"SKU '{sku_code}' not found"},
            )
        sku, stock = row
        if stock is None:
            stock = await self._inventory_repo.ensure_stock_row(db, sku_id=sku.id)

        # Lock row
        result = await db.execute(
            select(InventoryStock)
            .where(InventoryStock.id == stock.id)
            .with_for_update()
        )
        stock = result.scalar_one()

        qty_before = stock.quantity_on_hand
        qty_after = qty_before + quantity

        if qty_after < Decimal("0.00"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "NEGATIVE_STOCK",
                    "message": f"Adjustment would result in negative stock ({qty_after})",
                },
            )

        stock.quantity_on_hand = qty_after

        # Create movement log
        adjusted_by_uuid = None
        if adjusted_by:
            try:
                adjusted_by_uuid = uuid.UUID(adjusted_by)
            except Exception:
                pass

        movement = InventoryMovement(
            sku_id=sku.id,
            movement_type="adjustment",
            quantity=quantity,
            quantity_before=qty_before,
            quantity_after=qty_after,
            reason=reason,
            reference_type="manual",
            created_by=adjusted_by_uuid,
        )
        db.add(movement)
        await db.flush()

        return stock, movement

    async def list_movements(
        self,
        db: AsyncSession,
        *,
        page: int = 1,
        size: int = 20,
        sku_code: str | None = None,
        movement_type: str | None = None,
    ) -> tuple[list, int]:
        """
        Paginated inventory movement log with optional filters.
        """
        from sqlalchemy import func as sa_func

        stmt = (
            select(InventoryMovement, SKU.sku_code)
            .join(SKU, SKU.id == InventoryMovement.sku_id)
            .where(InventoryMovement.is_deleted.is_(False))
        )

        if sku_code:
            stmt = stmt.where(SKU.sku_code == sku_code)
        if movement_type:
            stmt = stmt.where(InventoryMovement.movement_type == movement_type)

        count_stmt = select(sa_func.count()).select_from(stmt.subquery())
        total = int((await db.execute(count_stmt)).scalar() or 0)

        stmt = (
            stmt
            .order_by(InventoryMovement.created_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        result = await db.execute(stmt)
        rows = result.all()
        return rows, total

    async def restock(
        self,
        db: AsyncSession,
        *,
        sku_id: uuid.UUID,
        quantity: Decimal,
    ) -> InventoryStock:
        """
        Atomically restock (e.g. after a return).  Uses SELECT FOR UPDATE.
        Increases on_hand, decreases reserved.
        """
        result = await db.execute(
            select(InventoryStock)
            .where(InventoryStock.sku_id == sku_id)
            .where(InventoryStock.is_deleted.is_(False))
            .with_for_update()
        )
        stock = result.scalar_one_or_none()
        if stock is None:
            stock = await self._inventory_repo.ensure_stock_row(db, sku_id=sku_id)

        stock.quantity_on_hand = stock.quantity_on_hand + quantity
        await db.flush()
        return stock

    async def restock_on_return(
        self,
        db: AsyncSession,
        *,
        sku_code: str,
        quantity: Decimal,
        order_id: uuid.UUID,
        returned_by: str | None = None,
    ) -> tuple[InventoryStock, InventoryMovement]:
        """Restore on-hand stock for a returned fulfilled order and journal it."""
        row = await self._inventory_repo.get_stock_by_sku_code(db, sku_code=sku_code)
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "SKU_NOT_FOUND", "message": f"SKU '{sku_code}' not found"},
            )

        sku, stock = row
        if stock is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "STOCK_NOT_FOUND",
                    "message": f"Stock row for SKU '{sku_code}' not found",
                },
            )

        result = await db.execute(
            select(InventoryStock)
            .where(InventoryStock.id == stock.id)
            .where(InventoryStock.is_deleted.is_(False))
            .with_for_update()
        )
        stock = result.scalar_one_or_none()
        if stock is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "STOCK_NOT_FOUND",
                    "message": f"Stock row for SKU '{sku_code}' not found",
                },
            )

        quantity = Decimal(str(quantity))
        if quantity <= Decimal("0.00"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "INVALID_RESTOCK_QUANTITY",
                    "message": f"Return quantity for SKU '{sku_code}' must be positive",
                },
            )

        quantity_before = stock.quantity_on_hand
        quantity_after = quantity_before + quantity
        stock.quantity_on_hand = quantity_after

        returned_by_uuid = None
        if returned_by:
            try:
                returned_by_uuid = uuid.UUID(str(returned_by))
            except Exception:
                pass

        movement = InventoryMovement(
            sku_id=sku.id,
            movement_type=MovementType.RESTOCK.value,
            quantity=quantity,
            quantity_before=quantity_before,
            quantity_after=quantity_after,
            reason=f"Order return for order {order_id} SKU {sku_code}",
            reference_type="order",
            reference_id=order_id,
            created_by=returned_by_uuid,
        )
        db.add(movement)
        await db.flush()
        return stock, movement
