"""Tenant-local catalog product and sellable-unit operations."""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.catalog_product import CatalogProduct
from models.sku import SKU
from repositories.inventory_repository import InventoryRepository
from schemas.catalog import CatalogProductCreate, CatalogProductUpdate, SellableUnitCreate, SellableUnitUpdate
from services.sku_integrity import flush_skus_or_409


class CatalogProductService:
    def __init__(self, inventory_repo: InventoryRepository | None = None) -> None:
        self._inventory_repo = inventory_repo or InventoryRepository()

    async def _assert_codes_available(self, db: AsyncSession, codes: list[str]) -> None:
        existing = await db.execute(select(SKU.sku_code).where(SKU.sku_code.in_(codes)))
        collision = existing.scalars().first()
        if collision is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "SKU_EXISTS", "message": f"SKU code '{collision}' already exists"},
            )

    async def _reload_product_graph(self, db: AsyncSession, *, product_id) -> CatalogProduct:
        """Awaited post-flush reload of the full product graph.

        AuditMixin.updated_at carries ``onupdate=func.now()``, so a flush
        EXPIRES the updated_at scalar on every mutated row; touching it outside
        an awaited boundary raises MissingGreenlet. This explicit SELECT
        refreshes product and unit scalar state (including updated_at) and
        materializes the sellable_units collection in the same awaited
        database boundary, so the route serializer stays pure synchronous
        mapping with zero implicit SQL.
        """
        result = await db.execute(
            select(CatalogProduct)
            .options(selectinload(CatalogProduct.sellable_units))
            .where(CatalogProduct.id == product_id, CatalogProduct.is_deleted.is_(False))
            .execution_options(populate_existing=True)
        )
        product = result.scalar_one()
        # selectinload+populate_existing refreshes the parent; expired unit
        # scalars (server-onupdate updated_at) are refreshed here in the same
        # awaited boundary.
        for unit in product.sellable_units:
            import sqlalchemy as _sa

            if _sa.inspect(unit).expired:
                await db.refresh(unit)
        return product

    async def create_product(
        self, db: AsyncSession, *, request: CatalogProductCreate, actor_id: str | None
    ) -> CatalogProduct:
        await self._assert_codes_available(db, [unit.sku_code for unit in request.sellable_units])
        product = CatalogProduct(
            name=request.name,
            description=request.description,
            category=request.category,
            is_active=request.is_active,
            created_by=actor_id,
        )
        db.add(product)
        await db.flush()
        created_units = [
            SKU(
                catalog_product_id=product.id,
                sku_code=unit.sku_code,
                name=product.name,
                description=product.description,
                category=product.category,
                unit=unit.unit,
                package_quantity=unit.package_quantity,
                is_active=unit.is_active,
                created_by=actor_id,
            )
            for unit in request.sellable_units
        ]
        db.add_all(created_units)
        # R1: concurrent duplicate-code race surfaces here — map the named
        # unique-index violation to SKU_EXISTS/409 (rollback inside the guard);
        # never a 500.
        await flush_skus_or_409(db, sku_code=request.sellable_units[0].sku_code)
        for unit in created_units:
            await self._inventory_repo.ensure_stock_row(db, sku_id=unit.id)
        return await self._reload_product_graph(db, product_id=product.id)

    async def list_products(
        self, db: AsyncSession, *, page: int, size: int, is_active: Optional[bool], q: Optional[str]
    ) -> tuple[list[CatalogProduct], int]:
        filters = [CatalogProduct.is_deleted.is_(False)]
        if is_active is not None:
            filters.append(CatalogProduct.is_active.is_(is_active))
        if q:
            pattern = f"%{q}%"
            filters.append(
                or_(
                    CatalogProduct.name.ilike(pattern),
                    CatalogProduct.category.ilike(pattern),
                    CatalogProduct.sellable_units.any(SKU.sku_code.ilike(pattern)),
                )
            )
        total = int((await db.execute(select(func.count(CatalogProduct.id)).where(*filters))).scalar_one())
        result = await db.execute(
            select(CatalogProduct)
            .where(*filters)
            .options(selectinload(CatalogProduct.sellable_units))
            .order_by(CatalogProduct.name.asc(), CatalogProduct.id.asc())
            .offset((page - 1) * size)
            .limit(size)
        )
        return list(result.scalars().all()), total

    async def get_product(self, db: AsyncSession, *, product_id: str) -> CatalogProduct:
        try:
            product_uuid = uuid.UUID(product_id)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=404, detail={"code": "PRODUCT_NOT_FOUND", "message": "Product not found"}) from exc
        result = await db.execute(
            select(CatalogProduct)
            .where(CatalogProduct.id == product_uuid, CatalogProduct.is_deleted.is_(False))
            .options(selectinload(CatalogProduct.sellable_units))
            .execution_options(populate_existing=True)
        )
        product = result.scalar_one_or_none()
        if product is None:
            raise HTTPException(status_code=404, detail={"code": "PRODUCT_NOT_FOUND", "message": "Product not found"})
        return product

    async def update_product(
        self,
        db: AsyncSession,
        *,
        product_id: str,
        request: CatalogProductUpdate,
        actor_id: str | None,
    ) -> CatalogProduct:
        product = await self.get_product(db, product_id=product_id)
        updates = request.model_dump(exclude_unset=True)
        for field, value in updates.items():
            setattr(product, field, value)
        product.updated_by = actor_id
        for unit in product.sellable_units:
            if "name" in updates:
                unit.name = product.name
            if "description" in updates:
                unit.description = product.description
            if "category" in updates:
                unit.category = product.category
            unit.updated_by = actor_id
        await db.flush()
        return await self._reload_product_graph(db, product_id=product.id)

    async def add_sellable_unit(
        self,
        db: AsyncSession,
        *,
        product_id: str,
        request: SellableUnitCreate,
        actor_id: str | None,
    ) -> CatalogProduct:
        product = await self.get_product(db, product_id=product_id)
        await self._assert_codes_available(db, [request.sku_code])
        unit = SKU(
            catalog_product_id=product.id,
            sku_code=request.sku_code,
            name=product.name,
            description=product.description,
            category=product.category,
            unit=request.unit,
            package_quantity=request.package_quantity,
            is_active=request.is_active,
            created_by=actor_id,
        )
        db.add(unit)
        # R1: concurrent duplicate-code race surfaces here — mapped to
        # SKU_EXISTS/409 by the named-constraint guard (never a 500).
        await flush_skus_or_409(db, sku_code=request.sku_code)
        await self._inventory_repo.ensure_stock_row(db, sku_id=unit.id)
        return await self._reload_product_graph(db, product_id=product.id)

    async def update_sellable_unit(
        self,
        db: AsyncSession,
        *,
        product_id: str,
        sellable_unit_id: str,
        request: SellableUnitUpdate,
        actor_id: str | None,
    ) -> CatalogProduct:
        product = await self.get_product(db, product_id=product_id)
        try:
            unit_uuid = uuid.UUID(sellable_unit_id)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=404, detail={"code": "SELLABLE_UNIT_NOT_FOUND", "message": "Sellable unit not found"}) from exc
        unit = next((item for item in product.sellable_units if item.id == unit_uuid), None)
        if unit is None:
            raise HTTPException(status_code=404, detail={"code": "SELLABLE_UNIT_NOT_FOUND", "message": "Sellable unit not found"})
        for field, value in request.model_dump(exclude_unset=True).items():
            setattr(unit, field, value)
        unit.updated_by = actor_id
        await db.flush()
        return await self._reload_product_graph(db, product_id=product.id)
