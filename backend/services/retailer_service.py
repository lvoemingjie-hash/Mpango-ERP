from __future__ import annotations

from datetime import datetime
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from db.tenant_filter import run_as_system
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
        """Accept an invitation atomically (DC-12R1-S1, CTO order B).

        Delegates to RetailerProvisioningService which runs the full provisioning
        transaction (retailer -> binding -> tenant user -> tenant_user_id mapping
        -> retailer_operator grant -> optional setup token -> SMTP before commit
        -> mark used). Returns the legacy 4-tuple
        (invitation, retailer, binding, error_code); on a controlled failure the
        first three are None and error_code is set. The caller (API) is expected
        to commit/rollback the transaction.
        """
        # Local import avoids a circular dependency at module import time.
        from services.retailer_provisioning_service import (
            RetailerProvisioningError,
            RetailerProvisioningService,
        )

        service = RetailerProvisioningService(db)
        try:
            result = await service.register_with_invitation(
                invitation_code=invitation_code,
                phone=phone,
                name=name,
                email=email,
                address=address,
            )
            return result.invitation, result.retailer, result.binding, None
        except RetailerProvisioningError as exc:
            return None, None, None, exc.code

    async def register_with_join_intent(
        self,
        db: AsyncSession,
        *,
        join_intent_wholesaler_id: uuid.UUID,
        phone: str,
        email: str,
        name: str | None = None,
        address: str | None = None,
    ):
        """Accept a VERIFIED join intent (dual-entry entry B).

        The API layer verifies the signed intent and passes ONLY the
        server-extracted ``join_intent_wholesaler_id`` — a client-submitted
        wholesaler id can never reach this method. Returns a 5-tuple
        (invitation(None), retailer, binding, error_code, wholesaler); on a
        controlled failure the middle three are None. The caller (API) is
        expected to commit/rollback the transaction.
        """
        # Local import avoids a circular dependency at module import time.
        from services.retailer_provisioning_service import (
            RetailerProvisioningError,
            RetailerProvisioningService,
        )

        service = RetailerProvisioningService(db)
        try:
            result = await service.register_with_join_intent(
                wholesaler_id=join_intent_wholesaler_id,
                phone=phone,
                email=email,
                name=name,
                address=address,
            )
            return (
                None,
                result.retailer,
                result.binding,
                None,
                result.wholesaler,
            )
        except RetailerProvisioningError as exc:
            return None, None, None, exc.code, None

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

    async def list_retailers_for_wholesaler(
        self,
        db: AsyncSession,
        *,
        wholesaler_id: uuid.UUID,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[tuple[object, object]], int]:
        """
        Paginated list of retailers bound to a wholesaler.
        Returns list of (retailer, binding) tuples and total count.
        """
        bindings = await self._binding_repo.list_by_wholesaler(db, wholesaler_id=wholesaler_id)
        total = len(bindings)
        start = (page - 1) * size
        page_bindings = bindings[start:start + size]

        results: list[tuple[object, object]] = []
        for binding in page_bindings:
            retailer = await self._retailer_repo.get_by_id(db, retailer_id=binding.retailer_id)
            if retailer:
                results.append((retailer, binding))
        return results, total

    async def get_retailer_for_wholesaler(
        self,
        db: AsyncSession,
        *,
        wholesaler_id: uuid.UUID,
        retailer_id: uuid.UUID,
    ) -> tuple[object, object] | None:
        """
        Get a single retailer detail, only if bound to the given wholesaler.
        Returns (retailer, binding) or None.
        """
        binding = await self._binding_repo.get_binding(
            db, wholesaler_id=wholesaler_id, retailer_id=retailer_id
        )
        if not binding:
            return None
        retailer = await self._retailer_repo.get_by_id(db, retailer_id=retailer_id)
        if not retailer:
            return None
        return retailer, binding
