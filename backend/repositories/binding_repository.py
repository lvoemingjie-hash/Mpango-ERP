from __future__ import annotations

import uuid
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.binding import WholesalerRetailerBinding


class BindingRepository:
    async def get_binding(
        self,
        db: AsyncSession,
        *,
        wholesaler_id: uuid.UUID,
        retailer_id: uuid.UUID,
    ) -> Optional[WholesalerRetailerBinding]:
        result = await db.execute(
            select(WholesalerRetailerBinding).where(
                WholesalerRetailerBinding.wholesaler_id == wholesaler_id,
                WholesalerRetailerBinding.retailer_id == retailer_id,
            )
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        db: AsyncSession,
        *,
        wholesaler_id: uuid.UUID,
        retailer_id: uuid.UUID,
        status: str = "active",
    ) -> WholesalerRetailerBinding:
        binding = WholesalerRetailerBinding(
            wholesaler_id=wholesaler_id,
            retailer_id=retailer_id,
            status=status,
            outstanding_balance=Decimal("0.00"),
        )
        db.add(binding)
        await db.flush()
        await db.refresh(binding)
        return binding

    async def list_by_wholesaler(
        self,
        db: AsyncSession,
        *,
        wholesaler_id: uuid.UUID,
    ) -> List[WholesalerRetailerBinding]:
        result = await db.execute(
            select(WholesalerRetailerBinding).where(
                WholesalerRetailerBinding.wholesaler_id == wholesaler_id
            )
        )
        return list(result.scalars().all())
