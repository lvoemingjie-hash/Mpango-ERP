"""U6-H1 tenant provisioning claim service skeleton."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.tenant_onboarding import TenantRegistration


@dataclass(frozen=True)
class TenantProvisioningClaimResult:
    """Result for the first safe provisioning claim step."""

    action: str
    registration_id: UUID
    status: str | None
    wholesaler_id: UUID | None = None
    tenant_schema: str | None = None
    provisioning_started_at: datetime | None = None
    provisioning_completed_at: datetime | None = None
    reason: str | None = None


class TenantProvisioningService:
    """Claim verified onboarding rows before later tenant creation slices."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def claim_registration_for_provisioning(
        self, registration_id: UUID
    ) -> TenantProvisioningClaimResult:
        result = await self.db.execute(
            select(TenantRegistration)
            .where(TenantRegistration.id == registration_id)
            .with_for_update()
            .execution_options(ignore_tenant=True)
        )
        registration = result.scalar_one_or_none()

        if registration is None:
            return TenantProvisioningClaimResult(
                action="blocked",
                registration_id=registration_id,
                status=None,
                reason="not_found",
            )

        if _has_existing_active_assignment(registration):
            return _result("existing", registration)

        if not _can_claim(registration):
            return _result("blocked", registration, reason="not_claimable")

        now = datetime.now(timezone.utc)
        registration.status = "provisioning"
        registration.provisioning_started_at = now
        await self.db.flush()

        return _result("claimed", registration)


def _has_existing_active_assignment(registration: TenantRegistration) -> bool:
    return (
        registration.status == "active"
        and registration.wholesaler_id is not None
        and registration.tenant_schema is not None
    )


def _can_claim(registration: TenantRegistration) -> bool:
    return (
        registration.status == "email_verified"
        and registration.wholesaler_id is None
        and registration.tenant_schema is None
        and registration.provisioning_completed_at is None
    )


def _result(
    action: str,
    registration: TenantRegistration,
    *,
    reason: str | None = None,
) -> TenantProvisioningClaimResult:
    return TenantProvisioningClaimResult(
        action=action,
        registration_id=registration.id,
        status=registration.status,
        wholesaler_id=registration.wholesaler_id,
        tenant_schema=registration.tenant_schema,
        provisioning_started_at=registration.provisioning_started_at,
        provisioning_completed_at=registration.provisioning_completed_at,
        reason=reason,
    )
