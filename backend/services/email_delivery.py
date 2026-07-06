"""Development/test email delivery sink for onboarding flows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from core.config import Settings


@dataclass(frozen=True)
class VerificationEmailDelivery:
    """Captured verification delivery for non-production tests."""

    registration_id: UUID
    to_email: str
    verification_link: str
    token: str
    created_at: datetime


_DEV_EMAIL_DELIVERIES: list[VerificationEmailDelivery] = []


def record_verification_email(
    *,
    settings: Settings,
    registration_id: UUID,
    to_email: str,
    token: str,
    verification_link: str,
) -> None:
    """Capture verification email only in test/staging-safe runtime modes."""
    if settings.MPANGO_ENV == "production":
        return

    _DEV_EMAIL_DELIVERIES.append(
        VerificationEmailDelivery(
            registration_id=registration_id,
            to_email=to_email,
            token=token,
            verification_link=verification_link,
            created_at=datetime.now(timezone.utc),
        )
    )


def get_dev_email_deliveries(email: str | None = None) -> list[VerificationEmailDelivery]:
    """Return captured non-production verification deliveries for tests."""
    if email is None:
        return list(_DEV_EMAIL_DELIVERIES)
    normalized = email.strip().lower()
    return [delivery for delivery in _DEV_EMAIL_DELIVERIES if delivery.to_email == normalized]


def clear_dev_email_deliveries() -> None:
    """Clear captured deliveries between tests."""
    _DEV_EMAIL_DELIVERIES.clear()
