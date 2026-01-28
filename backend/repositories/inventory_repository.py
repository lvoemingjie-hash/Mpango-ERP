from __future__ import annotations

from typing import Optional, Sequence

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from models.inventory_stock import InventoryStock
from models.sku import SKU
from models.order import OrderItem


class InventoryRepository:
    async def ensure_stock_row(self, db: AsyncSession, *, sku_id) -> InventoryStock:
        result = await db.execute(select(InventoryStock).where(InventoryStock.sku_id == sku_id, InventoryStock.is_deleted.is_(False)))
        stock = result.scalar_one_or_none()
        if stock:
            return stock
        stock = InventoryStock(sku_id=sku_id)
        db.add(stock)
        await db.flush()
        await db.refresh(stock)
        return stock

    async def get_stock_by_sku_code(self, db: AsyncSession, *, sku_code: str) -> Optional[tuple[SKU, Optional[InventoryStock]]]:
        stmt = (
            select(SKU, InventoryStock)
            .outerjoin(InventoryStock, (InventoryStock.sku_id == SKU.id) & (InventoryStock.is_deleted.is_(False)))
            .where(SKU.sku_code == sku_code, SKU.is_deleted.is_(False))
        )
        result = await db.execute(stmt)
        row = result.first()
        if not row:
            return None
        return row[0], row[1]

    async def list_stock_paginated(
        self,
        db: AsyncSession,
        *,
        page: int,
        size: int,
        sku_code: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> tuple[Sequence[tuple[SKU, Optional[InventoryStock]]], int]:
        stmt = (
            select(SKU, InventoryStock)
            .outerjoin(InventoryStock, (InventoryStock.sku_id == SKU.id) & (InventoryStock.is_deleted.is_(False)))
            .where(SKU.is_deleted.is_(False))
        )
        if sku_code:
            stmt = stmt.where(SKU.sku_code == sku_code)
        if is_active is not None:
            stmt = stmt.where(SKU.is_active.is_(is_active))

        count_stmt = stmt.with_only_columns(func.count()).order_by(None)
        total = int((await db.execute(count_stmt)).scalar() or 0)

        stmt = stmt.order_by(SKU.sku_code.asc()).offset((page - 1) * size).limit(size)
        result = await db.execute(stmt)
        return result.all(), total

    async def list_sku_codes_for_order(self, db: AsyncSession, *, order_id) -> list[str]:
        result = await db.execute(
            select(OrderItem.sku_code)
            .where(OrderItem.order_id == order_id, OrderItem.is_deleted.is_(False))
        )
        return [r[0] for r in result.all()]
