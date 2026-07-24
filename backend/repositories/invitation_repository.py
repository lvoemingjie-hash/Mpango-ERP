from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select, text
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

    async def get_by_id(self, db: AsyncSession, *, invitation_id: uuid.UUID) -> Optional[Invitation]:
        result = await db.execute(select(Invitation).where(Invitation.id == invitation_id))
        return result.scalar_one_or_none()

    async def lock_by_code(self, db: AsyncSession, *, code: str) -> Optional[Invitation]:
        """SELECT ... FOR UPDATE by code (DC-12R1-S1 atomic consume, CTO order B).

        Caller is responsible for holding an open transaction so the row lock
        survives until commit/rollback.
        """
        result = await db.execute(
            select(Invitation).where(Invitation.code == code).with_for_update()
        )
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
            text(
                "UPDATE public.invitations SET status = 'used', "
                "used_retailer_id = :retailer_id, used_at = :used_at, "
                "updated_at = now() WHERE id = :invitation_id"
            ),
            {
                "invitation_id": invitation_id,
                "retailer_id": retailer_id,
                "used_at": used_at,
            },
        )

    async def revoke(
        self,
        db: AsyncSession,
        *,
        invitation_id: uuid.UUID,
        revoked_by: uuid.UUID,
        revoked_at: datetime,
    ) -> int:
        """Tenant-scoped revoke (DC-12R1-S1 F-04).

        Only the inviting wholesaler's row is revoked: the caller must have
        already verified invitation.wholesaler_id == token.tenant_id at the API
        layer. Idempotent for an already-used/revoked invitation. Returns the
        number of rows transitioned to revoked.
        """
        result = await db.execute(
            text(
                "UPDATE public.invitations SET status = 'revoked', "
                "revoked_at = :revoked_at, revoked_by = :revoked_by, updated_at = now() "
                "WHERE id = :invitation_id AND status = 'active'"
            ),
            {
                "invitation_id": invitation_id,
                "revoked_at": revoked_at,
                "revoked_by": revoked_by,
            },
        )
        return result.rowcount
