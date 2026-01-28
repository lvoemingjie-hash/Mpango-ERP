from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.invitation import Invitation


class InvitationRepository:
    async def create(
        self,
        db: AsyncSession,
        *,
        code: str,
        wholesaler_id: uuid.UUID,
        retailer_phone: Optional[str] = None,
        expires_at: Optional[datetime] = None,
    ) -> Invitation:
        invitation = Invitation(
            code=code,
            wholesaler_id=wholesaler_id,
            retailer_phone=retailer_phone,
            expires_at=expires_at,
            status="active",
        )
        db.add(invitation)
        await db.flush()
        await db.refresh(invitation)
        return invitation

    async def get_by_code(self, db: AsyncSession, *, code: str) -> Optional[Invitation]:
        result = await db.execute(select(Invitation).where(Invitation.code == code))
        return result.scalar_one_or_none()

    async def mark_used(
        self,
        db: AsyncSession,
        *,
        invitation_id: uuid.UUID,
        retailer_id: uuid.UUID,
        used_at: datetime,
    ) -> None:
        await db.execute(
            update(Invitation)
            .where(Invitation.id == invitation_id)
            .values(status="used", used_retailer_id=retailer_id, used_at=used_at)
        )
