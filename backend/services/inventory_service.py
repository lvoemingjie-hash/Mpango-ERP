from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import InventoryShortageError
from models.inventory_stock import InventoryStock
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

