from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.catalog_product import CatalogProduct
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
        catalog_product_id: str | None,
        sku_code: str,
        name: str,
        description: str | None,
        unit: str,
        package_quantity,
        category: str | None,
        is_active: bool,
        created_by: str | None,
    ) -> SKU:
        existing = await self._sku_repo.get_any_by_code(db, sku_code=sku_code)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "SKU_EXISTS", "message": f"SKU '{sku_code}' already exists"},
            )

        product: CatalogProduct | None = None
        if catalog_product_id:
            try:
                product_uuid = uuid.UUID(catalog_product_id)
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"code": "PRODUCT_NOT_FOUND", "message": "Catalog product not found"},
                ) from exc
            product = (
                await db.execute(
                    select(CatalogProduct).where(
                        CatalogProduct.id == product_uuid,
                        CatalogProduct.is_deleted.is_(False),
                    )
                )
            ).scalar_one_or_none()
            if product is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"code": "PRODUCT_NOT_FOUND", "message": "Catalog product not found"},
                )
        else:
            product = CatalogProduct(
                name=name,
                description=description,
                category=category,
                is_active=is_active,
                created_by=uuid.UUID(created_by) if created_by else None,
            )
            db.add(product)
            await db.flush()

        sku = SKU(
            catalog_product_id=product.id,
            sku_code=sku_code,
            name=product.name,
            description=product.description,
            unit=unit,
            package_quantity=package_quantity,
            category=product.category,
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
        package_quantity,
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
            sku.catalog_product.name = name
        if description is not None:
            sku.catalog_product.description = description
        if unit is not None:
            sku.unit = unit
        if package_quantity is not None:
            sku.package_quantity = package_quantity
        if category is not None:
            sku.catalog_product.category = category
        if is_active is not None:
            sku.is_active = is_active
        for sibling in sku.catalog_product.sellable_units:
            sibling.name = sku.catalog_product.name
            sibling.description = sku.catalog_product.description
            sibling.category = sku.catalog_product.category
            sibling.updated_by = uuid.UUID(updated_by) if updated_by else None
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
