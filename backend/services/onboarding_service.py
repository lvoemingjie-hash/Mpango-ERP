"""U6-C tenant signup and email verification token service."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from core.config import Settings, get_settings
from core.security import hash_password
from models.tenant_onboarding import (
    EMAIL_VERIFICATION_TOKEN_PURPOSE,
    LIVE_REGISTRATION_STATUSES,
    ONBOARDING_STATUS_TOKEN_PURPOSE,
    EmailVerificationToken,
    OnboardingStatusToken,
    OwnerCredentialSetupToken,
    TenantRegistration,
)
from schemas.auth_signup import SignupRequest
from services.email_delivery import (
    EmailDeliveryNotConfiguredError,
    is_verification_email_delivery_configured,
    record_owner_setup_email,
    record_verification_email,
)
from services.tenant_provisioning_service import TenantProvisioningService


NEUTRAL_SIGNUP_MESSAGE = "If this email can be used, verification instructions will be sent."
NEUTRAL_VERIFY_EMAIL_MESSAGE = "If this verification link is valid, the email will be verified."
NEUTRAL_ONBOARDING_STATUS_MESSAGE = "Onboarding status is available."
INVALID_OR_EXPIRED_VERIFICATION_TOKEN = "INVALID_OR_EXPIRED_VERIFICATION_TOKEN"
INVALID_OR_EXPIRED_ONBOARDING_STATUS_TOKEN = "INVALID_OR_EXPIRED_ONBOARDING_STATUS_TOKEN"
SIGNUP_VERIFICATION_TTL = timedelta(hours=24)
PUBLIC_ONBOARDING_STATUSES = {
    "pending_email_verification",
    "email_verified",
    "expired",
    "cancelled",
    "failed",
    "active",
}


class IdempotencyConflictError(Exception):
    """Raised when an idempotency key is reused with a different payload."""


class VerificationTokenInvalidError(Exception):
    """Raised for invalid, expired, used, or non-actionable verification tokens."""


class OnboardingStatusTokenInvalidError(Exception):
    """Raised for invalid, expired, revoked, or non-actionable status tokens."""


class OnboardingOrchestrationError(Exception):
    """Raised when post-verification provisioning/setup orchestration fails."""


@dataclass(frozen=True)
class SignupResult:
    """Result returned by the signup service."""

    registration_id: UUID | None
    status: str
    email_verification_required: bool = True
    resend_available_at: datetime | None = None


@dataclass(frozen=True)
class VerifyEmailResult:
    """Internal email verification result."""

    status: str


@dataclass(frozen=True)
class OnboardingStatusResult:
    """Internal onboarding status result."""

    status: str


def normalize_email(email: str) -> str:
    """Normalize email at the public signup boundary."""
    return email.strip().lower()


def validate_signup_password(password: str) -> None:
    """Validate the U6-C password policy before bcrypt hashing."""
    validate_password_policy(password)


def validate_password_policy(password: str) -> None:
    """Shared backend password policy for signup, setup-credential, and reset.

    Minimal policy (DC-3B): non-blank and length >= 8. Frontend policy is
    intentionally not added in DC-3B. Stronger rules may be layered here later.
    """
    if not isinstance(password, str) or not password or not password.strip():
        raise ValueError("Password must not be blank")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")


async def verify_email_token(
    *,
    db: AsyncSession,
    token: str | None,
    settings: Settings | None = None,
) -> VerifyEmailResult:
    """Mark a pending registration verified when the raw verification token is valid."""
    settings = settings or get_settings()
    _assert_token_hash_key(settings)

    if token is None or not token.strip():
        raise VerificationTokenInvalidError(INVALID_OR_EXPIRED_VERIFICATION_TOKEN)

    token_hash = hash_token(token.strip(), settings)
    now = datetime.now(timezone.utc)

    result = await db.execute(
        select(EmailVerificationToken, TenantRegistration)
        .join(TenantRegistration, EmailVerificationToken.registration_id == TenantRegistration.id)
        .where(EmailVerificationToken.token_hash == token_hash)
        .execution_options(ignore_tenant=True)
    )
    row = result.one_or_none()
    if row is None:
        raise VerificationTokenInvalidError(INVALID_OR_EXPIRED_VERIFICATION_TOKEN)

    verification_token, registration = row
    retryable_after_setup_email_failure = await _is_retryable_setup_email_failure(
        db, registration, now
    )
    if (
        verification_token.used_at is not None
        or verification_token.revoked_at is not None
        or verification_token.expires_at <= now
        or (
            registration.status != "pending_email_verification"
            and not retryable_after_setup_email_failure
        )
    ):
        raise VerificationTokenInvalidError(INVALID_OR_EXPIRED_VERIFICATION_TOKEN)

    if registration.status == "pending_email_verification":
        registration.status = "email_verified"
    if registration.email_verified_at is None:
        registration.email_verified_at = now
    await db.flush()

    await complete_email_verified_onboarding(
        db=db,
        registration_id=registration.id,
        settings=settings,
    )

    verification_token.used_at = datetime.now(timezone.utc)
    await db.flush()

    return VerifyEmailResult(status=registration.status)


async def complete_email_verified_onboarding(
    *,
    db: AsyncSession,
    registration_id: UUID,
    settings: Settings | None = None,
) -> None:
    """Provision tenant and deliver owner setup credential email after verification."""
    settings = settings or get_settings()
    if not is_verification_email_delivery_configured(settings=settings):
        raise EmailDeliveryNotConfiguredError("EMAIL_DELIVERY_NOT_CONFIGURED")

    provisioning = TenantProvisioningService(
        db,
        database_url=getattr(settings, "DATABASE_URL", None),
    )
    claimed = await provisioning.claim_registration_for_provisioning(registration_id)
    if claimed.action not in {"claimed", "existing"}:
        raise OnboardingOrchestrationError("ONBOARDING_ORCHESTRATION_FAILED")

    provisioned = await provisioning.provision_wholesaler_and_schema(registration_id)
    if provisioned.action not in {"provisioned", "reconciled", "existing"}:
        raise OnboardingOrchestrationError("ONBOARDING_ORCHESTRATION_FAILED")
    if provisioned.status != "active":
        raise OnboardingOrchestrationError("ONBOARDING_ORCHESTRATION_FAILED")

    # Real bootstrap can commit tenant schema DDL independently. Persist the
    # public assignment before setup email delivery so SMTP failure can retry
    # against the same wholesaler/schema instead of orphaning the schema.
    await db.commit()

    from services.owner_credential_service import OwnerCredentialSetupService

    issued = await OwnerCredentialSetupService(db, settings=settings).issue_setup_token(
        registration_id
    )
    if issued.action == "blocked":
        raise OnboardingOrchestrationError("ONBOARDING_ORCHESTRATION_FAILED")
    if issued.action == "issued":
        if issued.raw_token is None:
            raise OnboardingOrchestrationError("ONBOARDING_ORCHESTRATION_FAILED")
        registration = await _registration_by_id(db, registration_id)
        if registration is None:
            raise OnboardingOrchestrationError("ONBOARDING_ORCHESTRATION_FAILED")
        record_owner_setup_email(
            settings=settings,
            registration_id=registration_id,
            to_email=registration.owner_email,
            token=issued.raw_token,
            setup_link=build_owner_setup_link(issued.raw_token, settings),
        )


async def get_onboarding_status(
    *,
    db: AsyncSession,
    token: str | None,
    settings: Settings | None = None,
) -> OnboardingStatusResult:
    """Return a coarse public onboarding status for a valid opaque status token."""
    settings = settings or get_settings()
    _assert_token_hash_key(settings)

    if token is None or not token.strip():
        raise OnboardingStatusTokenInvalidError(INVALID_OR_EXPIRED_ONBOARDING_STATUS_TOKEN)

    token_hash = hash_token(token.strip(), settings)
    now = datetime.now(timezone.utc)

    result = await db.execute(
        select(OnboardingStatusToken, TenantRegistration)
        .join(TenantRegistration, OnboardingStatusToken.registration_id == TenantRegistration.id)
        .where(OnboardingStatusToken.token_hash == token_hash)
        .execution_options(ignore_tenant=True)
    )
    row = result.one_or_none()
    if row is None:
        raise OnboardingStatusTokenInvalidError(INVALID_OR_EXPIRED_ONBOARDING_STATUS_TOKEN)

    status_token, registration = row
    if (
        status_token.revoked_at is not None
        or status_token.is_deleted is True
        or status_token.expires_at <= now
    ):
        raise OnboardingStatusTokenInvalidError(INVALID_OR_EXPIRED_ONBOARDING_STATUS_TOKEN)

    return OnboardingStatusResult(status=_public_onboarding_status(registration.status))


async def create_signup_registration(
    *,
    db: AsyncSession,
    request: SignupRequest,
    idempotency_key: str | None = None,
    settings: Settings | None = None,
) -> SignupResult:
    """Create a pending tenant registration and email verification token."""
    settings = settings or get_settings()
    _assert_token_hash_key(settings)
    if not is_verification_email_delivery_configured(settings=settings):
        raise EmailDeliveryNotConfiguredError("EMAIL_DELIVERY_NOT_CONFIGURED")

    owner_email = normalize_email(str(request.email))
    validate_signup_password(request.password)

    fingerprint_hash = _request_fingerprint_hash(request, owner_email, settings)
    idempotency_key_hash = _hash_optional_value(idempotency_key, settings)

    if idempotency_key_hash is not None:
        existing_for_key = await _registration_for_idempotency_key(db, idempotency_key_hash)
        if existing_for_key is not None:
            if existing_for_key.request_fingerprint_hash != fingerprint_hash:
                raise IdempotencyConflictError("Idempotency key reused with different payload")
            return SignupResult(
                registration_id=existing_for_key.id,
                status=existing_for_key.status,
            )

    existing_live = await _live_registration_for_email(db, owner_email)
    if existing_live is not None:
        return SignupResult(registration_id=None, status="pending_email_verification")

    now = datetime.now(timezone.utc)
    expires_at = now + SIGNUP_VERIFICATION_TTL
    registration = TenantRegistration(
        company_name=request.company_name,
        country=request.country,
        business_type=request.business_type,
        phone=request.phone,
        owner_email=owner_email,
        password_hash=hash_password(request.password),
        status="pending_email_verification",
        idempotency_key_hash=idempotency_key_hash,
        request_fingerprint_hash=fingerprint_hash,
        expires_at=expires_at,
    )

    raw_token = generate_verification_token()
    token_hash = hash_token(raw_token, settings)

    try:
        db.add(registration)
        await db.flush()

        db.add(
            EmailVerificationToken(
                registration_id=registration.id,
                token_hash=token_hash,
                purpose=EMAIL_VERIFICATION_TOKEN_PURPOSE,
                expires_at=expires_at,
                sent_to_email=owner_email,
                send_count=1,
                last_sent_at=now,
                request_fingerprint_hash=fingerprint_hash,
            )
        )
        db.add(
            OnboardingStatusToken(
                registration_id=registration.id,
                token_hash=token_hash,
                purpose=ONBOARDING_STATUS_TOKEN_PURPOSE,
                expires_at=expires_at,
            )
        )
        await db.flush()

        record_verification_email(
            settings=settings,
            registration_id=registration.id,
            to_email=owner_email,
            token=raw_token,
            verification_link=build_verification_link(raw_token, settings),
        )
    except IntegrityError:
        await db.rollback()
        return SignupResult(registration_id=None, status="pending_email_verification")
    except EmailDeliveryNotConfiguredError:
        await db.rollback()
        raise

    return SignupResult(registration_id=registration.id, status=registration.status)


def generate_verification_token() -> str:
    """Generate an opaque high-entropy verification token."""
    return secrets.token_urlsafe(32)


def hash_token(token: str, settings: Settings | None = None) -> str:
    """Hash opaque tokens with HMAC-SHA256 using existing app secret material."""
    settings = settings or get_settings()
    _assert_token_hash_key(settings)
    return _hmac_sha256(token, settings)


def build_verification_link(token: str, settings: Settings | None = None) -> str:
    """Build the frontend verification link.

    DC-12A-R2: generates an absolute URL using PUBLIC_FRONTEND_URL.
    Token is in the URL fragment (not query) to avoid proxy access logs.
    Falls back to a relative fragment link if no base URL is configured (test/dev).
    """
    settings = settings or get_settings()
    encoded = quote(token, safe='')
    path = f"/verify-email#token={encoded}"
    base = getattr(settings, "PUBLIC_FRONTEND_URL", None)
    if base:
        return f"{base}{path}"
    return path


def build_owner_setup_link(token: str, settings: Settings | None = None) -> str:
    """Build the owner credential setup link for email delivery.

    DC-12A-R2: generates an absolute URL using PUBLIC_FRONTEND_URL.
    Token is in the URL fragment (not query) to avoid proxy access logs.
    """
    settings = settings or get_settings()
    encoded = quote(token, safe='')
    path = f"/setup-credential#setupToken={encoded}"
    base = getattr(settings, "PUBLIC_FRONTEND_URL", None)
    if base:
        return f"{base}{path}"
    return path


def build_password_reset_link(token: str, settings: Settings | None = None) -> str:
    """Build the password reset link for email delivery.

    DC-12A-R2: generates an absolute URL using PUBLIC_FRONTEND_URL.
    Token is in the URL fragment (not query) to avoid proxy access logs.
    """
    settings = settings or get_settings()
    encoded = quote(token, safe='')
    path = f"/reset-password#resetToken={encoded}"
    base = getattr(settings, "PUBLIC_FRONTEND_URL", None)
    if base:
        return f"{base}{path}"
    return path


def _public_onboarding_status(status: str) -> str:
    if status == "provisioning":
        return "email_verified"
    if status in PUBLIC_ONBOARDING_STATUSES:
        return status
    raise OnboardingStatusTokenInvalidError(INVALID_OR_EXPIRED_ONBOARDING_STATUS_TOKEN)


async def _live_registration_for_email(
    db: AsyncSession, owner_email: str
) -> TenantRegistration | None:
    result = await db.execute(
        select(TenantRegistration)
        .where(TenantRegistration.owner_email == owner_email)
        .where(TenantRegistration.status.in_(LIVE_REGISTRATION_STATUSES))
        .order_by(TenantRegistration.created_at.desc())
        .limit(1)
        .execution_options(ignore_tenant=True)
    )
    return result.scalar_one_or_none()


async def _registration_for_idempotency_key(
    db: AsyncSession, idempotency_key_hash: str
) -> TenantRegistration | None:
    result = await db.execute(
        select(TenantRegistration).where(
            TenantRegistration.idempotency_key_hash == idempotency_key_hash
        )
        .execution_options(ignore_tenant=True)
    )
    return result.scalar_one_or_none()


async def _registration_by_id(db: AsyncSession, registration_id: UUID) -> TenantRegistration | None:
    result = await db.execute(
        select(TenantRegistration)
        .where(TenantRegistration.id == registration_id)
        .execution_options(ignore_tenant=True)
    )
    return result.scalar_one_or_none()


async def _is_retryable_setup_email_failure(
    db: AsyncSession, registration: TenantRegistration, now: datetime
) -> bool:
    if (
        registration.status != "active"
        or registration.email_verified_at is None
        or registration.wholesaler_id is None
        or registration.tenant_schema is None
        or registration.provisioning_completed_at is None
    ):
        return False

    result = await db.execute(
        select(OwnerCredentialSetupToken)
        .where(OwnerCredentialSetupToken.registration_id == registration.id)
        .where(OwnerCredentialSetupToken.used_at.is_(None))
        .where(OwnerCredentialSetupToken.revoked_at.is_(None))
        .where(OwnerCredentialSetupToken.is_deleted.is_(False))
        .where(OwnerCredentialSetupToken.expires_at > now)
        .limit(1)
        .execution_options(ignore_tenant=True)
    )
    return result.scalar_one_or_none() is None


def _request_fingerprint_hash(
    request: SignupRequest, owner_email: str, settings: Settings
) -> str:
    payload: dict[str, Any] = {
        "business_type": request.business_type,
        "company_name": request.company_name,
        "country": request.country,
        "email": owner_email,
        "password": request.password,
        "phone": request.phone,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return _hmac_sha256(canonical, settings)


def _hash_optional_value(value: str | None, settings: Settings) -> str | None:
    if value is None or not value.strip():
        return None
    return _hmac_sha256(value.strip(), settings)


def _hmac_sha256(value: str, settings: Settings) -> str:
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        value.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _assert_token_hash_key(settings: Settings) -> None:
    if not settings.SECRET_KEY or len(settings.SECRET_KEY) < 32:
        raise RuntimeError("SIGNUP_TOKEN_HASH_KEY_MISSING")
