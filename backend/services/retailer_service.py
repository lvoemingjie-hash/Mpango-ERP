from __future__ import annotations

from datetime import datetime
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from repositories.binding_repository import BindingRepository
from repositories.invitation_repository import InvitationRepository
from repositories.retailer_repository import RetailerRepository


class RetailerService:
    def __init__(
        self,
        invitation_repo: InvitationRepository | None = None,
        retailer_repo: RetailerRepository | None = None,
        binding_repo: BindingRepository | None = None,
    ) -> None:
        self._invitation_repo = invitation_repo or InvitationRepository()
        self._retailer_repo = retailer_repo or RetailerRepository()
        self._binding_repo = binding_repo or BindingRepository()

    async def register_with_invitation(
        self,
        db: AsyncSession,
        *,
        invitation_code: str,
        phone: str,
        name: str | None = None,
        email: str | None = None,
        address: str | None = None,
    ):
        invitation = await self._invitation_repo.get_by_code(db, code=invitation_code)
        if not invitation:
            return None, None, None, "INVITATION_NOT_FOUND"

        now = datetime.utcnow()

        if invitation.status != "active":
            return invitation, None, None, "INVITATION_NOT_ACTIVE"

        if invitation.expires_at and invitation.expires_at < now:
            return invitation, None, None, "INVITATION_EXPIRED"

        if invitation.retailer_phone and invitation.retailer_phone != phone:
            return invitation, None, None, "INVITATION_PHONE_MISMATCH"

        retailer = await self._retailer_repo.get_by_phone(db, phone=phone)
        if not retailer:
            retailer = await self._retailer_repo.create(
                db,
                phone=phone,
                name=name,
                email=email,
                address=address,
            )

        existing = await self._binding_repo.get_binding(
            db,
            wholesaler_id=invitation.wholesaler_id,
            retailer_id=retailer.id,
        )
        if not existing:
            binding = await self._binding_repo.create(
                db,
                wholesaler_id=invitation.wholesaler_id,
                retailer_id=retailer.id,
                status="active",
            )
        else:
            binding = existing

        await self._invitation_repo.mark_used(
            db,
            invitation_id=invitation.id,
            retailer_id=retailer.id,
            used_at=now,
        )

        return invitation, retailer, binding, None

    async def list_bindings_for_wholesaler(
        self,
        db: AsyncSession,
        *,
        wholesaler_id: uuid.UUID,
    ):
        bindings = await self._binding_repo.list_by_wholesaler(db, wholesaler_id=wholesaler_id)
        return bindings

    async def list_bindings_with_retailers(
        self,
        db: AsyncSession,
        *,
        wholesaler_id: uuid.UUID,
    ):
        bindings = await self._binding_repo.list_by_wholesaler(db, wholesaler_id=wholesaler_id)
        results: list[tuple[object, object | None]] = []
        for binding in bindings:
            retailer = await self._retailer_repo.get_by_id(db, retailer_id=binding.retailer_id)
            results.append((binding, retailer))
        return results
