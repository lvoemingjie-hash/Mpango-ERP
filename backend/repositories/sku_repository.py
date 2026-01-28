from __future__ import annotations

from typing import Optional, Sequence

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from models.sku import SKU


class SKURepository:
    async def get_by_id(self, db: AsyncSession, *, sku_id) -> Optional[SKU]:
        result = await db.execute(select(SKU).where(SKU.id == sku_id, SKU.is_deleted.is_(False)))
        return result.scalar_one_or_none()

    async def get_by_code(self, db: AsyncSession, *, sku_code: str) -> Optional[SKU]:
        result = await db.execute(select(SKU).where(SKU.sku_code == sku_code, SKU.is_deleted.is_(False)))
        return result.scalar_one_or_none()

    async def list_paginated(
        self,
        db: AsyncSession,
        *,
        page: int,
        size: int,
        is_active: Optional[bool] = None,
        q: Optional[str] = None,
    ) -> tuple[Sequence[SKU], int]:
        stmt = select(SKU).where(SKU.is_deleted.is_(False))
        if is_active is not None:
            stmt = stmt.where(SKU.is_active.is_(is_active))
        if q:
            like = f"%{q.strip()}%"
            stmt = stmt.where((SKU.sku_code.ilike(like)) | (SKU.name.ilike(like)))

        count_stmt = stmt.with_only_columns(func.count()).order_by(None)
        total = int((await db.execute(count_stmt)).scalar() or 0)

        stmt = stmt.order_by(SKU.created_at.desc()).offset((page - 1) * size).limit(size)
        result = await db.execute(stmt)
        return result.scalars().all(), total

    async def create(self, db: AsyncSession, *, sku: SKU) -> SKU:
        db.add(sku)
        await db.flush()
        await db.refresh(sku)
        return sku

    async def save(self, db: AsyncSession, *, sku: SKU) -> SKU:
        await db.flush()
        await db.refresh(sku)
        return sku
