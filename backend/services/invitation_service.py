from __future__ import annotations

import secrets
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from repositories.invitation_repository import InvitationRepository
from repositories.wholesaler_repository import WholesalerRepository


class InvitationService:
    def __init__(
        self,
        invitation_repo: InvitationRepository | None = None,
        wholesaler_repo: WholesalerRepository | None = None,
    ) -> None:
        self._invitation_repo = invitation_repo or InvitationRepository()
        self._wholesaler_repo = wholesaler_repo or WholesalerRepository()

    async def create_invitation(
        self,
        db: AsyncSession,
        *,
        wholesaler_id: uuid.UUID,
        retailer_phone: Optional[str] = None,
        expires_at: Optional[datetime] = None,
    ):
        code = secrets.token_urlsafe(24)
        invitation = await self._invitation_repo.create(
            db,
            code=code,
            wholesaler_id=wholesaler_id,
            retailer_phone=retailer_phone,
            expires_at=expires_at,
        )
        return invitation

    async def get_wholesaler(self, db: AsyncSession, *, wholesaler_id: uuid.UUID):
        return await self._wholesaler_repo.get_by_id(db, wholesaler_id=wholesaler_id)

    async def get_invitation_status(
        self,
        db: AsyncSession,
        *,
        code: str,
    ):
        invitation = await self._invitation_repo.get_by_code(db, code=code)
        if not invitation:
            return None, False, "INVITATION_NOT_FOUND"

        now = datetime.utcnow()
        if invitation.status != "active":
            return invitation, False, "INVITATION_NOT_ACTIVE"

        if invitation.expires_at and invitation.expires_at < now:
            return invitation, False, "INVITATION_EXPIRED"

        return invitation, True, None
