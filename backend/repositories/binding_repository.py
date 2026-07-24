from __future__ import annotations

import uuid
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import select, text
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

    async def get_by_tenant_user(
        self,
        db: AsyncSession,
        *,
        wholesaler_id: uuid.UUID,
        tenant_user_id: uuid.UUID,
    ) -> Optional[WholesalerRetailerBinding]:
        """DC-12R1-S1: resolve a binding by the authoritative tenant_user_id mapping.

        This is the identity-resolution path used after authentication
        (token.user_id -> binding.tenant_user_id -> retailer_id). Never key on email.
        """
        result = await db.execute(
            select(WholesalerRetailerBinding).where(
                WholesalerRetailerBinding.wholesaler_id == wholesaler_id,
                WholesalerRetailerBinding.tenant_user_id == tenant_user_id,
                WholesalerRetailerBinding.is_deleted.is_(False),
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
        tenant_user_id: Optional[uuid.UUID] = None,
    ) -> WholesalerRetailerBinding:
        binding = WholesalerRetailerBinding(
            wholesaler_id=wholesaler_id,
            retailer_id=retailer_id,
            status=status,
            outstanding_balance=Decimal("0.00"),
            tenant_user_id=tenant_user_id,
        )
        db.add(binding)
        await db.flush()
        await db.refresh(binding)
        return binding

    async def set_tenant_user_id(
        self,
        db: AsyncSession,
        *,
        binding_id: uuid.UUID,
        tenant_user_id: uuid.UUID,
    ) -> None:
        """DC-12R1-S1: write back the authoritative tenant_user_id mapping."""
        await db.execute(
            text(
                "UPDATE public.wholesaler_retailer_bindings "
                "SET tenant_user_id = :tenant_user_id, updated_at = now() "
                "WHERE id = :binding_id"
            ),
            {"binding_id": binding_id, "tenant_user_id": tenant_user_id},
        )

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
