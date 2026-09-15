"""Pure SMTP auth-mode / loopback-guard tests (no database dependency).

Authorization: CTO-AUTH-SKU-PUBLIC-PROVISIONING-SMTP-KIMI-R1-2026-09-15
(successor round of CTO-AUTH-SKU-PUBLIC-PROVISIONING-SMTP-KIMI-V1-2026-09-15).

This module is deliberately database-free: it imports only
``core.config`` and ``services.email_delivery``, requests no database
fixtures, and never constructs an engine, session, or API app. It must pass
even when ``TEST_DATABASE_URL`` points at an unreachable database. The
database-backed public lifecycle tests live in
``test_smtp_loopback_noauth_contract.py``.

Covered required paths (R1 items 1-3):

1. ``SMTP_AUTH_MODE`` default is authenticated ``login``; ``none`` is rejected
   for every non-loopback ``SMTP_HOST`` and accepted only for literal loopback
   hosts;
2. guard rejections fail closed (config completeness false / delivery raises
   ``EmailDeliveryNotConfiguredError``) *before any transport work*;
3. zero-connection assertions: neither ``smtplib.SMTP`` nor
   ``smtplib.SMTP_SSL`` is ever constructed on any guard-rejection path
   (including the implicit-TLS variant), proven with tripwire spies.
"""

from __future__ import annotations

import os
import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from core.config import Settings, is_loopback_smtp_host
from services import email_delivery


# Kept in sync with the database-backed module; these are task-local
# placeholders and never real credentials.
SMTP_PASSWORD_VALUE = "smtp-provider-app-password"  # pragma: allowlist secret
TEST_SECRET_KEY = "Z9vLk8mN4pQ7rS2tU5wX8yB3cD6fG0hJ"  # pragma: allowlist secret
NOAUTH_PUBLIC_ORIGIN = "https://kimi-smtp-links.invalid"

NON_LOOPBACK_HOSTS = (
    "smtp.example.invalid",
    "127.0.0.1.evil.invalid",
    "127.0.0.1.nip.io",  # resolves to loopback but is not a literal IP
    "10.0.0.5",
    "0.0.0.0",
    "::ffff:8.8.8.8",
    "mail.internal.invalid",
)

LITERAL_LOOPBACK_HOSTS = ("127.0.0.1", "127.9.9.9", "localhost", "LOCALHOST", "::1", "[::1]")


def _production_settings(**overrides: Any) -> Settings:
    """Real Settings instance in production mode (no database touched)."""
    values: dict[str, Any] = {
        "MPANGO_ENV": "production",
        "SECRET_KEY": os.environ.get("SECRET_KEY") or TEST_SECRET_KEY,
        "DATABASE_URL": os.environ.get("DATABASE_URL") or "postgresql://127.0.0.1:5432/taskdb",
        "REDIS_URL": "redis://127.0.0.1:6379/15",
        "PUBLIC_FRONTEND_URL": NOAUTH_PUBLIC_ORIGIN,
        "EMAIL_PROVIDER": "smtp",
        "EMAIL_DELIVERY_MODE": "smtp",
        "SMTP_HOST": "127.0.0.1",
        "SMTP_PORT": 2525,
        "SMTP_USER": "mailer@example.invalid",
        "SMTP_PASSWORD": SMTP_PASSWORD_VALUE,
        "EMAIL_FROM": "no-reply@example.invalid",
        "SMTP_USE_TLS": False,
        "SMTP_STARTTLS": False,
        "SMTP_AUTH_MODE": "login",
    }
    values.update(overrides)
    return Settings(**values)


def _loose_settings(**overrides: Any) -> SimpleNamespace:
    """Loosely constructed settings object (bypasses Settings validation)."""
    values: dict[str, Any] = {
        "MPANGO_ENV": "production",
        "SECRET_KEY": os.environ.get("SECRET_KEY") or TEST_SECRET_KEY,
        "DATABASE_URL": os.environ.get("DATABASE_URL")
        or "postgresql://127.0.0.1:5432/taskdb",
        "PUBLIC_FRONTEND_URL": NOAUTH_PUBLIC_ORIGIN,
        "EMAIL_PROVIDER": "smtp",
        "EMAIL_DELIVERY_MODE": "smtp",
        "SMTP_HOST": "127.0.0.1",
        "SMTP_PORT": 2525,
        "SMTP_USER": "mailer@example.invalid",
        "SMTP_PASSWORD": SMTP_PASSWORD_VALUE,
        "EMAIL_FROM": "no-reply@example.invalid",
        "SMTP_USE_TLS": False,
        "SMTP_STARTTLS": False,
        "SMTP_AUTH_MODE": "login",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class _TransportTripwire:
    """Spy that records any construction attempt of a real SMTP client.

    Performs no SMTP protocol work. Used only on guard-rejection paths, where
    the assertion is that the list stays empty -- i.e. zero connections.
    """

    constructed: list[tuple] = []

    def __init__(self, *args, **kwargs):  # noqa: D107
        type(self).constructed.append((args, kwargs))
        raise AssertionError("SMTP transport must not be constructed")

    @classmethod
    def reset(cls) -> None:
        cls.constructed = []


# ---------------------------------------------------------------------------
# 1. Auth-mode policy (real Settings)
# ---------------------------------------------------------------------------


async def test_login_remains_the_default_auth_mode():
    settings = _production_settings()
    assert settings.SMTP_AUTH_MODE == "login"
    assert Settings.model_fields["SMTP_AUTH_MODE"].default == "login"


@pytest.mark.parametrize("host", NON_LOOPBACK_HOSTS)
async def test_noauth_mode_is_rejected_for_non_loopback_host(host: str):
    with pytest.raises(ValidationError):
        _production_settings(SMTP_AUTH_MODE="none", SMTP_HOST=host)


@pytest.mark.parametrize("host", LITERAL_LOOPBACK_HOSTS)
async def test_noauth_mode_is_accepted_only_for_literal_loopback_hosts(host: str):
    settings = _production_settings(SMTP_AUTH_MODE="none", SMTP_HOST=host)
    assert settings.SMTP_AUTH_MODE == "none"


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("127.0.0.1", True),
        ("127.5.5.5", True),
        ("localhost", True),
        ("::1", True),
        ("[::1]", True),
        ("127.0.0.1.nip.io", False),
        ("smtp.example.invalid", False),
        ("0.0.0.0", False),
        ("", False),
        (None, False),
    ],
)
async def test_loopback_detection_never_resolves_names(host, expected: bool):
    assert is_loopback_smtp_host(host) is expected


# ---------------------------------------------------------------------------
# 2. Config-completeness guard (no transport)
# ---------------------------------------------------------------------------


async def test_config_completeness_rejects_offloopback_noauth():
    off_loopback = _loose_settings(SMTP_HOST="mail.internal.invalid", SMTP_AUTH_MODE="none")
    assert email_delivery._smtp_config_complete(off_loopback) is False
    assert email_delivery.is_verification_email_delivery_configured(settings=off_loopback) is False


async def test_config_completeness_accepts_loopback_noauth_without_credentials():
    loopback = _loose_settings(
        SMTP_HOST="127.0.0.1",
        SMTP_USER=None,
        SMTP_PASSWORD=None,
        SMTP_AUTH_MODE="none",
    )
    assert email_delivery._smtp_config_complete(loopback) is True


async def test_config_completeness_still_requires_credentials_in_login_mode():
    login_without_credentials = _loose_settings(SMTP_AUTH_MODE="login", SMTP_USER=None)
    assert email_delivery._smtp_config_complete(login_without_credentials) is False


async def test_unknown_auth_mode_value_and_label_never_infer_noauth():
    unknown_mode = _loose_settings(SMTP_AUTH_MODE="bogus")
    assert email_delivery._smtp_config_complete(unknown_mode) is False
    assert email_delivery._smtp_auth_mode(unknown_mode) == "bogus"  # observed, not honoured

    staging_without_auth_mode = _loose_settings(
        MPANGO_ENV="staging", SMTP_USER=None, SMTP_PASSWORD=None
    )
    assert email_delivery._smtp_auth_mode(staging_without_auth_mode) == "login"
    assert email_delivery._smtp_config_complete(staging_without_auth_mode) is False


# ---------------------------------------------------------------------------
# 3. Zero-connection assertions (SMTP and SMTP_SSL tripwires)
# ---------------------------------------------------------------------------


GUARD_REJECTION_CASES = {
    "unknown_auth_mode": {"SMTP_AUTH_MODE": "bogus"},
    "none_off_loopback": {"SMTP_HOST": "mail.internal.invalid", "SMTP_AUTH_MODE": "none"},
    "none_off_loopback_with_implicit_tls": {
        "SMTP_HOST": "mail.internal.invalid",
        "SMTP_AUTH_MODE": "none",
        "SMTP_USE_TLS": True,
    },
}


@pytest.mark.parametrize("case_name", sorted(GUARD_REJECTION_CASES))
async def test_guard_rejections_open_zero_smtp_connections(monkeypatch, case_name: str):
    """Guard rejections must fail before ANY SMTP/SMTP_SSL construction."""
    settings = _loose_settings(**GUARD_REJECTION_CASES[case_name])
    _TransportTripwire.reset()
    monkeypatch.setattr(email_delivery.smtplib, "SMTP", _TransportTripwire)
    monkeypatch.setattr(email_delivery.smtplib, "SMTP_SSL", _TransportTripwire)

    with pytest.raises(email_delivery.EmailDeliveryNotConfiguredError):
        email_delivery.record_verification_email(
            settings=settings,
            registration_id=uuid.uuid4(),
            to_email="owner@example.invalid",
            token="opaque-token",
            verification_link=f"{NOAUTH_PUBLIC_ORIGIN}/verify-email#token=opaque-token",
        )

    assert _TransportTripwire.constructed == [], (
        f"{case_name}: guard rejection reached the SMTP transport"
    )


async def test_delivery_layer_guard_blocks_offloopback_noauth_before_transport(monkeypatch):
    """Defense in depth: no-auth off-loopback fails closed before any socket opens."""
    settings = _loose_settings(SMTP_HOST="mail.internal.invalid", SMTP_AUTH_MODE="none")
    _TransportTripwire.reset()
    monkeypatch.setattr(email_delivery.smtplib, "SMTP", _TransportTripwire)
    monkeypatch.setattr(email_delivery.smtplib, "SMTP_SSL", _TransportTripwire)

    with pytest.raises(email_delivery.EmailDeliveryNotConfiguredError):
        email_delivery._send_smtp_email(
            settings=settings,
            to_email="owner@example.invalid",
            subject="subject",
            body="body",
        )
    assert _TransportTripwire.constructed == []


async def test_send_layer_unknown_mode_guard_blocks_before_transport(monkeypatch):
    """The send-layer guard itself must reject an unknown mode with zero connections.

    This path is only reachable directly (the config-completeness gate shields
    the API path), so it is asserted directly; mutation M5 removes this guard
    and this node must go RED.
    """
    settings = _loose_settings(SMTP_AUTH_MODE="bogus")
    _TransportTripwire.reset()
    monkeypatch.setattr(email_delivery.smtplib, "SMTP", _TransportTripwire)
    monkeypatch.setattr(email_delivery.smtplib, "SMTP_SSL", _TransportTripwire)

    with pytest.raises(email_delivery.EmailDeliveryNotConfiguredError):
        email_delivery._send_smtp_email(
            settings=settings,
            to_email="owner@example.invalid",
            subject="subject",
            body="body",
        )
    assert _TransportTripwire.constructed == []
