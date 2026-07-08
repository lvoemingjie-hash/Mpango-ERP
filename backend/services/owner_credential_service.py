"""Owner credential setup token service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings, get_settings
from models.tenant_onboarding import (
    OWNER_CREDENTIAL_SETUP_TOKEN_PURPOSE,
    OwnerCredentialSetupToken,
    TenantRegistration,
)
from services.onboarding_service import generate_verification_token, hash_token


OWNER_CREDENTIAL_SETUP_TOKEN_TTL = timedelta(hours=24)


@dataclass(frozen=True)
class OwnerCredentialSetupTokenIssueResult:
    """Result for owner credential setup token issuance."""

    action: str
    registration_id: UUID
    raw_token: str | None = None
    expires_at: datetime | None = None
    reason: str | None = None


class OwnerCredentialSetupService:
    """Issue owner credential setup tokens after tenant provisioning completes."""

    def __init__(self, db: AsyncSession, *, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()

    async def issue_setup_token(
        self, registration_id: UUID
    ) -> OwnerCredentialSetupTokenIssueResult:
        registration = await self._get_registration(registration_id)
        if registration is None:
            return OwnerCredentialSetupTokenIssueResult(
                action="blocked",
                registration_id=registration_id,
                reason="not_found",
            )
        if not _is_eligible(registration):
            return OwnerCredentialSetupTokenIssueResult(
                action="blocked",
                registration_id=registration.id,
                reason="not_eligible",
            )

        now = datetime.now(timezone.utc)
        existing = await self._active_token(registration.id)
        if existing is not None:
            return OwnerCredentialSetupTokenIssueResult(
                action="existing",
                registration_id=registration.id,
                expires_at=existing.expires_at,
            )

        raw_token = generate_verification_token()
        token = OwnerCredentialSetupToken(
            registration_id=registration.id,
            token_hash=hash_token(raw_token, self.settings),
            purpose=OWNER_CREDENTIAL_SETUP_TOKEN_PURPOSE,
            expires_at=now + OWNER_CREDENTIAL_SETUP_TOKEN_TTL,
        )
        self.db.add(token)
        try:
            await self.db.flush()
        except IntegrityError:
            await self.db.rollback()
            return OwnerCredentialSetupTokenIssueResult(
                action="existing",
                registration_id=registration.id,
                raw_token=None,
            )

        return OwnerCredentialSetupTokenIssueResult(
            action="issued",
            registration_id=registration.id,
            raw_token=raw_token,
            expires_at=token.expires_at,
        )

    async def _get_registration(self, registration_id: UUID) -> TenantRegistration | None:
        result = await self.db.execute(
            select(TenantRegistration)
            .where(TenantRegistration.id == registration_id)
            .with_for_update()
            .execution_options(ignore_tenant=True)
        )
        return result.scalar_one_or_none()

    async def _active_token(self, registration_id: UUID) -> OwnerCredentialSetupToken | None:
        result = await self.db.execute(
            select(OwnerCredentialSetupToken)
            .where(OwnerCredentialSetupToken.registration_id == registration_id)
            .where(OwnerCredentialSetupToken.used_at.is_(None))
            .where(OwnerCredentialSetupToken.revoked_at.is_(None))
            .where(OwnerCredentialSetupToken.is_deleted.is_(False))
            .order_by(OwnerCredentialSetupToken.created_at.desc())
            .limit(1)
            .execution_options(ignore_tenant=True)
        )
        return result.scalar_one_or_none()


def _is_eligible(registration: TenantRegistration) -> bool:
    return (
        registration.status == "active"
        and registration.wholesaler_id is not None
        and registration.tenant_schema is not None
        and registration.provisioning_completed_at is not None
    )
