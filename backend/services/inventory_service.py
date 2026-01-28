from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

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
