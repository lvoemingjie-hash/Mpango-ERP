from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from models.sku import SKU
from repositories.sku_repository import SKURepository
from repositories.inventory_repository import InventoryRepository


class SKUService:
    def __init__(
        self,
        sku_repo: SKURepository | None = None,
        inventory_repo: InventoryRepository | None = None,
    ) -> None:
        self._sku_repo = sku_repo or SKURepository()
        self._inventory_repo = inventory_repo or InventoryRepository()

    async def create_sku(
        self,
        db: AsyncSession,
        *,
        sku_code: str,
        name: str,
        description: str | None,
        unit: str,
        category: str | None,
        is_active: bool,
        created_by: str | None,
    ) -> SKU:
        existing = await self._sku_repo.get_by_code(db, sku_code=sku_code)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "SKU_EXISTS", "message": f"SKU '{sku_code}' already exists"},
            )

        sku = SKU(
            sku_code=sku_code,
            name=name,
            description=description,
            unit=unit,
            category=category,
            is_active=is_active,
            created_by=uuid.UUID(created_by) if created_by else None,
        )
        sku = await self._sku_repo.create(db, sku=sku)

        await self._inventory_repo.ensure_stock_row(db, sku_id=sku.id)
        return sku

    async def update_sku(
        self,
        db: AsyncSession,
        *,
        sku_code: str,
        name: str | None,
        description: str | None,
        unit: str | None,
        category: str | None,
        is_active: bool | None,
        updated_by: str | None,
    ) -> SKU:
        sku = await self._sku_repo.get_by_code(db, sku_code=sku_code)
        if not sku:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "SKU_NOT_FOUND", "message": f"SKU '{sku_code}' not found"},
            )

        if name is not None:
            sku.name = name
        if description is not None:
            sku.description = description
        if unit is not None:
            sku.unit = unit
        if category is not None:
            sku.category = category
        if is_active is not None:
            sku.is_active = is_active
        sku.updated_by = uuid.UUID(updated_by) if updated_by else None

        sku = await self._sku_repo.save(db, sku=sku)
        await self._inventory_repo.ensure_stock_row(db, sku_id=sku.id)
        return sku

    async def get_sku(self, db: AsyncSession, *, sku_code: str) -> SKU:
        sku = await self._sku_repo.get_by_code(db, sku_code=sku_code)
        if not sku:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "SKU_NOT_FOUND", "message": f"SKU '{sku_code}' not found"},
            )
        return sku

    async def list_skus(self, db: AsyncSession, *, page: int, size: int, is_active, q):
        return await self._sku_repo.list_paginated(db, page=page, size=size, is_active=is_active, q=q)
