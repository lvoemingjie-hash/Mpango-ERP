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
    EmailVerificationToken,
    TenantRegistration,
)
from schemas.auth_signup import SignupRequest
from services.email_delivery import record_verification_email


NEUTRAL_SIGNUP_MESSAGE = "If this email can be used, verification instructions will be sent."
SIGNUP_VERIFICATION_TTL = timedelta(hours=24)


class IdempotencyConflictError(Exception):
    """Raised when an idempotency key is reused with a different payload."""


@dataclass(frozen=True)
class SignupResult:
    """Result returned by the signup service."""

    registration_id: UUID | None
    status: str
    email_verification_required: bool = True
    resend_available_at: datetime | None = None


def normalize_email(email: str) -> str:
    """Normalize email at the public signup boundary."""
    return email.strip().lower()


def validate_signup_password(password: str) -> None:
    """Validate the U6-C password policy before bcrypt hashing."""
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")


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
        await db.flush()
    except IntegrityError:
        await db.rollback()
        return SignupResult(registration_id=None, status="pending_email_verification")

    record_verification_email(
        settings=settings,
        registration_id=registration.id,
        to_email=owner_email,
        token=raw_token,
        verification_link=build_verification_link(raw_token),
    )

    return SignupResult(registration_id=registration.id, status=registration.status)


def generate_verification_token() -> str:
    """Generate an opaque high-entropy verification token."""
    return secrets.token_urlsafe(32)


def hash_token(token: str, settings: Settings | None = None) -> str:
    """Hash opaque tokens with HMAC-SHA256 using existing app secret material."""
    settings = settings or get_settings()
    _assert_token_hash_key(settings)
    return _hmac_sha256(token, settings)


def build_verification_link(token: str) -> str:
    """Build the frontend verification link stored by the dev/test sink."""
    return f"/verify-email?token={quote(token, safe='')}"


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
