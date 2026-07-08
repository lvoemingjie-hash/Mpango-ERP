"""Email delivery for onboarding flows."""

from __future__ import annotations

import smtplib
import ssl
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
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


class EmailDeliveryNotConfiguredError(RuntimeError):
    """Raised when signup email delivery cannot run safely."""


def is_verification_email_delivery_configured(*, settings: Settings) -> bool:
    """Return whether verification delivery can be performed in this runtime."""
    if settings.MPANGO_ENV != "production":
        return True
    return _smtp_config_complete(settings)


def record_verification_email(
    *,
    settings: Settings,
    registration_id: UUID,
    to_email: str,
    token: str,
    verification_link: str,
) -> None:
    """Deliver verification email or capture it in non-production sink."""
    if not is_verification_email_delivery_configured(settings=settings):
        raise EmailDeliveryNotConfiguredError("EMAIL_DELIVERY_NOT_CONFIGURED")

    if settings.MPANGO_ENV == "production":
        _send_smtp_verification_email(
            settings=settings,
            to_email=to_email,
            verification_link=verification_link,
        )
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


def _smtp_config_complete(settings: Settings) -> bool:
    provider = (getattr(settings, "EMAIL_PROVIDER", None) or "").strip().lower()
    mode = (getattr(settings, "EMAIL_DELIVERY_MODE", None) or "").strip().lower()
    if provider != "smtp" or mode != "smtp":
        return False
    required_values = (
        getattr(settings, "SMTP_HOST", None),
        getattr(settings, "SMTP_USER", None),
        getattr(settings, "SMTP_PASSWORD", None),
        getattr(settings, "EMAIL_FROM", None),
    )
    if any(value is None or not str(value).strip() for value in required_values):
        return False
    try:
        return int(getattr(settings, "SMTP_PORT", 0)) > 0
    except (TypeError, ValueError):
        return False


def _send_smtp_verification_email(
    *,
    settings: Settings,
    to_email: str,
    verification_link: str,
) -> None:
    message = EmailMessage()
    message["Subject"] = "Verify your Mpango ERP email"
    message["From"] = str(settings.EMAIL_FROM).strip()
    message["To"] = to_email
    message.set_content(
        "Welcome to Mpango ERP.\n\n"
        "Use this verification link to continue onboarding:\n"
        f"{verification_link}\n\n"
        "If you did not request this signup, ignore this email."
    )

    context = ssl.create_default_context()
    host = str(settings.SMTP_HOST).strip()
    port = int(settings.SMTP_PORT)
    use_tls = bool(getattr(settings, "SMTP_USE_TLS", False))
    use_starttls = bool(getattr(settings, "SMTP_STARTTLS", True))

    try:
        if use_tls:
            client_factory = smtplib.SMTP_SSL
            client_kwargs = {"context": context}
        else:
            client_factory = smtplib.SMTP
            client_kwargs = {}
        with client_factory(host, port, timeout=15, **client_kwargs) as client:
            if use_starttls and not use_tls:
                client.starttls(context=context)
            client.login(str(settings.SMTP_USER).strip(), str(settings.SMTP_PASSWORD))
            client.send_message(message)
    except Exception as exc:
        raise EmailDeliveryNotConfiguredError("EMAIL_DELIVERY_NOT_CONFIGURED") from exc
