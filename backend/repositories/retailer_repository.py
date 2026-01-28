from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.retailer import Retailer


class RetailerRepository:
    async def get_by_phone(self, db: AsyncSession, *, phone: str) -> Optional[Retailer]:
        result = await db.execute(select(Retailer).where(Retailer.phone == phone))
        return result.scalar_one_or_none()

    async def get_by_id(self, db: AsyncSession, *, retailer_id: uuid.UUID) -> Optional[Retailer]:
        result = await db.execute(select(Retailer).where(Retailer.id == retailer_id))
        return result.scalar_one_or_none()

    async def create(
        self,
        db: AsyncSession,
        *,
        phone: str,
        name: Optional[str] = None,
        email: Optional[str] = None,
        address: Optional[str] = None,
    ) -> Retailer:
        retailer = Retailer(phone=phone, name=name, email=email, address=address)
        db.add(retailer)
        await db.flush()
        await db.refresh(retailer)
        return retailer
