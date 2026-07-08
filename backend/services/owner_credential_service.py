"""Owner credential setup token service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings, get_settings
from core.security import hash_password
from models.tenant_onboarding import (
    OWNER_CREDENTIAL_SETUP_TOKEN_PURPOSE,
    OwnerCredentialSetupToken,
    TenantRegistration,
)
from services.onboarding_service import generate_verification_token, hash_token


OWNER_CREDENTIAL_SETUP_TOKEN_TTL = timedelta(hours=24)
INVALID_OR_EXPIRED_OWNER_CREDENTIAL_SETUP_TOKEN = "INVALID_OR_EXPIRED_OWNER_CREDENTIAL_SETUP_TOKEN"


class OwnerCredentialSetupTokenInvalidError(Exception):
    """Raised for invalid, expired, used, revoked, or non-actionable setup tokens."""


@dataclass(frozen=True)
class OwnerCredentialSetupTokenIssueResult:
    """Result for owner credential setup token issuance."""

    action: str
    registration_id: UUID
    raw_token: str | None = None
    expires_at: datetime | None = None
    reason: str | None = None


@dataclass(frozen=True)
class OwnerCredentialSetupConsumeResult:
    """Prepared owner credential data for the admin-creation slice."""

    registration_id: UUID
    tenant_schema: str
    owner_email: str
    password_hash: str


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
        existing = await self._active_token(registration.id, now)
        if existing is not None:
            return OwnerCredentialSetupTokenIssueResult(
                action="existing",
                registration_id=registration.id,
                expires_at=existing.expires_at,
            )

        await self._close_expired_tokens(registration.id, now)

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

    async def consume_setup_token(
        self, raw_token: str | None, password: str
    ) -> OwnerCredentialSetupConsumeResult:
        if raw_token is None or not raw_token.strip():
            _raise_invalid_setup_token()

        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(OwnerCredentialSetupToken, TenantRegistration)
            .join(TenantRegistration, OwnerCredentialSetupToken.registration_id == TenantRegistration.id)
            .where(OwnerCredentialSetupToken.token_hash == hash_token(raw_token.strip(), self.settings))
            .with_for_update()
            .execution_options(ignore_tenant=True)
        )
        row = result.one_or_none()
        if row is None:
            _raise_invalid_setup_token()

        setup_token, registration = row
        if not _is_actionable_setup_token(setup_token, now):
            _raise_invalid_setup_token()
        if registration.tenant_schema is None:
            _raise_invalid_setup_token()

        setup_token.used_at = now
        await self.db.flush()
        password_hash = hash_password(password)

        return OwnerCredentialSetupConsumeResult(
            registration_id=registration.id,
            tenant_schema=registration.tenant_schema,
            owner_email=registration.owner_email,
            password_hash=password_hash,
        )

    async def _get_registration(self, registration_id: UUID) -> TenantRegistration | None:
        result = await self.db.execute(
            select(TenantRegistration)
            .where(TenantRegistration.id == registration_id)
            .with_for_update()
            .execution_options(ignore_tenant=True)
        )
        return result.scalar_one_or_none()

    async def _active_token(
        self, registration_id: UUID, now: datetime
    ) -> OwnerCredentialSetupToken | None:
        result = await self.db.execute(
            select(OwnerCredentialSetupToken)
            .where(OwnerCredentialSetupToken.registration_id == registration_id)
            .where(OwnerCredentialSetupToken.used_at.is_(None))
            .where(OwnerCredentialSetupToken.revoked_at.is_(None))
            .where(OwnerCredentialSetupToken.is_deleted.is_(False))
            .where(OwnerCredentialSetupToken.expires_at > now)
            .order_by(OwnerCredentialSetupToken.created_at.desc())
            .limit(1)
            .execution_options(ignore_tenant=True)
        )
        return result.scalar_one_or_none()

    async def _close_expired_tokens(self, registration_id: UUID, now: datetime) -> None:
        await self.db.execute(
            update(OwnerCredentialSetupToken)
            .where(OwnerCredentialSetupToken.registration_id == registration_id)
            .where(OwnerCredentialSetupToken.used_at.is_(None))
            .where(OwnerCredentialSetupToken.revoked_at.is_(None))
            .where(OwnerCredentialSetupToken.is_deleted.is_(False))
            .where(OwnerCredentialSetupToken.expires_at <= now)
            .values(revoked_at=now)
            .execution_options(ignore_tenant=True)
        )


def _is_eligible(registration: TenantRegistration) -> bool:
    return (
        registration.status == "active"
        and registration.wholesaler_id is not None
        and registration.tenant_schema is not None
        and registration.provisioning_completed_at is not None
    )


def _is_actionable_setup_token(
    setup_token: OwnerCredentialSetupToken, now: datetime
) -> bool:
    return (
        setup_token.purpose == OWNER_CREDENTIAL_SETUP_TOKEN_PURPOSE
        and setup_token.used_at is None
        and setup_token.revoked_at is None
        and not setup_token.is_deleted
        and setup_token.expires_at > now
    )


def _raise_invalid_setup_token() -> None:
    raise OwnerCredentialSetupTokenInvalidError(
        INVALID_OR_EXPIRED_OWNER_CREDENTIAL_SETUP_TOKEN
    )
