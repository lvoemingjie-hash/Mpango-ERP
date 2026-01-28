from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.wholesaler import Wholesaler


class WholesalerRepository:
    async def get_by_id(self, db: AsyncSession, *, wholesaler_id: uuid.UUID) -> Optional[Wholesaler]:
        result = await db.execute(select(Wholesaler).where(Wholesaler.id == wholesaler_id))
        return result.scalar_one_or_none()
