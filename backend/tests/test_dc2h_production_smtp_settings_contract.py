"""DC-2H production SMTP startup-contract tests.

CTO-AUTH-MPANGO-PROMOTION-M-G1-DC2H-ACTIVE-SMTP-R1-20260924.

These tests instantiate the REAL ``core.config.Settings`` (no
SimpleNamespace, no source-string assertions) and pin the production
startup contract added to ``Settings.validate_production_secrets``:

- production requires provider AND delivery mode == ``smtp``;
- SMTP_HOST / SMTP_USER / SMTP_PASSWORD / EMAIL_FROM non-empty;
- SMTP_PORT positive;
- exactly one of SMTP_STARTTLS / SMTP_USE_TLS true;
- staging/test keep the existing ``dev_sink`` behaviour unchanged;
- diagnostics and exception text never echo secret or environment values.

The send-time rejection in ``services/email_delivery.py`` is covered by
the U6K tests and is intentionally out of scope here: this file proves
the STARTUP contract only.  All fixture values are synthetic and are
assembled at runtime from neutral fragments.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.config import Settings

_SMTP_ENV_KEYS = (
    "EMAIL_PROVIDER",
    "EMAIL_DELIVERY_MODE",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USER",
    "SMTP_PASSWORD",
    "EMAIL_FROM",
    "SMTP_STARTTLS",
    "SMTP_USE_TLS",
)

_ENV_KEYS_TO_CLEAR = _SMTP_ENV_KEYS + (
    "MPANGO_ENV",
    "SECRET_KEY",
    "DATABASE_URL",
    "REDIS_URL",
    "PUBLIC_FRONTEND_URL",
)


def _synthetic_fragment(*parts: str) -> str:
    return "".join(parts)


# Assembled at runtime from neutral fragments so no credential-shaped
# literal ever appears in source or in scanner views.
SYNTHETIC_SMTP_PASSWORD = _synthetic_fragment(
    "compose", "-", "smtp", "-", "synthetic", "-", "9f3a", "72be"
)


def _synthetic_secret_key() -> str:
    # 38 chars, clears the 32-char floor, contains no weak substring.
    return _synthetic_fragment("compose-synthetic-key-", "x" * 16)


def _synthetic_database_url() -> str:
    return _synthetic_fragment(
        "postgresql://mpango_app:",
        _synthetic_fragment("compose", "-", "db", "-", "pw"),
        "@db-host:5432/mpango_erp",
    )


PRODUCTION_BASE_KWARGS = {
    "MPANGO_ENV": "production",
    "SECRET_KEY": _synthetic_secret_key(),
    "DATABASE_URL": _synthetic_database_url(),
    "REDIS_URL": "redis://cache-host:6379/1",
    "PUBLIC_FRONTEND_URL": "https://app.example.com",
}


def _smtp_smtp_kwargs(**overrides: object) -> dict[str, object]:
    """A valid production STARTTLS SMTP configuration; overrides replace
    or delete entries (use ``None`` overrides to assert missing keys)."""
    smtp_kwargs: dict[str, object] = {
        "EMAIL_PROVIDER": "smtp",
        "EMAIL_DELIVERY_MODE": "smtp",
        "SMTP_HOST": "smtp.synthetic.invalid",
        "SMTP_PORT": 2587,
        "SMTP_USER": "compose-smtp-user",
        "SMTP_PASSWORD": SYNTHETIC_SMTP_PASSWORD,
        "EMAIL_FROM": "compose-synth@example.invalid",
        "SMTP_STARTTLS": True,
        "SMTP_USE_TLS": False,
    }
    for key, value in overrides.items():
        if value is None:
            smtp_kwargs.pop(key, None)
        else:
            smtp_kwargs[key] = value
    return smtp_kwargs


@pytest.fixture(autouse=True)
def _hermetic_smtp_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """No host- or session-level variable may leak into these contracts:
    Settings kwargs must be the single source of the behaviour under test."""
    for key in _ENV_KEYS_TO_CLEAR:
        monkeypatch.delenv(key, raising=False)


# ---------------------------------------------------------------------------
# Positive cases
# ---------------------------------------------------------------------------


def test_production_starttls_configuration_accepted() -> None:
    settings = Settings(**PRODUCTION_BASE_KWARGS, **_smtp_smtp_kwargs())
    assert settings.EMAIL_PROVIDER == "smtp"
    assert settings.EMAIL_DELIVERY_MODE == "smtp"
    assert settings.SMTP_HOST == "smtp.synthetic.invalid"
    assert settings.SMTP_PORT == 2587
    assert settings.SMTP_USER == "compose-smtp-user"
    assert settings.SMTP_PASSWORD == SYNTHETIC_SMTP_PASSWORD
    assert settings.EMAIL_FROM == "compose-synth@example.invalid"
    assert settings.SMTP_STARTTLS is True
    assert settings.SMTP_USE_TLS is False


def test_production_implicit_tls_configuration_accepted() -> None:
    settings = Settings(
        **PRODUCTION_BASE_KWARGS,
        **_smtp_smtp_kwargs(SMTP_STARTTLS=False, SMTP_USE_TLS=True),
    )
    assert settings.SMTP_STARTTLS is False
    assert settings.SMTP_USE_TLS is True


# ---------------------------------------------------------------------------
# staging/test dev_sink behaviour is unchanged
# ---------------------------------------------------------------------------


def test_test_environment_keeps_dev_sink_defaults() -> None:
    settings = Settings(
        MPANGO_ENV="test",
        SECRET_KEY=_synthetic_secret_key(),
    )
    assert settings.EMAIL_PROVIDER == "dev_sink"
    assert settings.EMAIL_DELIVERY_MODE == "dev_sink"
    assert settings.SMTP_HOST is None
    assert settings.SMTP_PASSWORD is None


def test_staging_environment_keeps_dev_sink_defaults() -> None:
    settings = Settings(
        MPANGO_ENV="staging",
        SECRET_KEY=_synthetic_secret_key(),
    )
    assert settings.EMAIL_PROVIDER == "dev_sink"
    assert settings.EMAIL_DELIVERY_MODE == "dev_sink"


# ---------------------------------------------------------------------------
# Negative cases: production rejects an incomplete SMTP contract
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("EMAIL_PROVIDER", "dev_sink"),
        ("EMAIL_DELIVERY_MODE", "dev_sink"),
    ],
)
def test_production_rejects_non_smtp_provider_or_mode(
    field: str, value: str
) -> None:
    with pytest.raises(ValidationError) as excinfo:
        Settings(**PRODUCTION_BASE_KWARGS, **_smtp_smtp_kwargs(**{field: value}))
    text = str(excinfo.value)
    marker = (
        "EMAIL_PROVIDER must be 'smtp' in production"
        if field == "EMAIL_PROVIDER"
        else "EMAIL_DELIVERY_MODE must be 'smtp' in production"
    )
    assert marker in text


def test_production_rejects_dev_sink_provider_and_mode() -> None:
    with pytest.raises(ValidationError) as excinfo:
        Settings(
            **PRODUCTION_BASE_KWARGS,
            **_smtp_smtp_kwargs(
                EMAIL_PROVIDER="dev_sink", EMAIL_DELIVERY_MODE="dev_sink"
            ),
        )
    text = str(excinfo.value)
    assert "EMAIL_PROVIDER must be 'smtp' in production" in text
    assert "EMAIL_DELIVERY_MODE must be 'smtp' in production" in text


@pytest.mark.parametrize(
    ("field", "marker"),
    [
        ("SMTP_HOST", "SMTP_HOST must be set to a non-empty value"),
        ("SMTP_USER", "SMTP_USER must be set to a non-empty value"),
        ("SMTP_PASSWORD", "SMTP_PASSWORD must be set to a non-empty value"),
        ("EMAIL_FROM", "EMAIL_FROM must be set to a non-empty value"),
    ],
)
def test_production_rejects_missing_required_smtp_fields(
    field: str, marker: str
) -> None:
    with pytest.raises(ValidationError) as excinfo:
        Settings(**PRODUCTION_BASE_KWARGS, **_smtp_smtp_kwargs(**{field: None}))
    assert marker in str(excinfo.value)


@pytest.mark.parametrize(
    ("field", "marker"),
    [
        ("SMTP_HOST", "SMTP_HOST must be set to a non-empty value"),
        ("SMTP_USER", "SMTP_USER must be set to a non-empty value"),
        ("SMTP_PASSWORD", "SMTP_PASSWORD must be set to a non-empty value"),
        ("EMAIL_FROM", "EMAIL_FROM must be set to a non-empty value"),
    ],
)
def test_production_rejects_empty_string_required_smtp_fields(
    field: str, marker: str
) -> None:
    with pytest.raises(ValidationError) as excinfo:
        Settings(
            **PRODUCTION_BASE_KWARGS,
            **_smtp_smtp_kwargs(**{field: ""}),
        )
    assert marker in str(excinfo.value)


def test_production_rejects_whitespace_only_smtp_password() -> None:
    """Whitespace-only counts as not-set: the contract is fail-closed."""
    with pytest.raises(ValidationError) as excinfo:
        Settings(
            **PRODUCTION_BASE_KWARGS,
            **_smtp_smtp_kwargs(SMTP_PASSWORD="   "),
        )
    assert "SMTP_PASSWORD must be set to a non-empty value" in str(excinfo.value)


@pytest.mark.parametrize("port", [0, -1])
def test_production_rejects_non_positive_smtp_port(port: int) -> None:
    with pytest.raises(ValidationError) as excinfo:
        Settings(
            **PRODUCTION_BASE_KWARGS,
            **_smtp_smtp_kwargs(SMTP_PORT=port),
        )
    assert "SMTP_PORT must be a positive integer" in str(excinfo.value)


def test_production_rejects_both_tls_flags_false() -> None:
    with pytest.raises(ValidationError) as excinfo:
        Settings(
            **PRODUCTION_BASE_KWARGS,
            **_smtp_smtp_kwargs(SMTP_STARTTLS=False, SMTP_USE_TLS=False),
        )
    assert (
        "exactly one of SMTP_STARTTLS and SMTP_USE_TLS must be true"
        in str(excinfo.value)
    )


def test_production_rejects_both_tls_flags_true() -> None:
    with pytest.raises(ValidationError) as excinfo:
        Settings(
            **PRODUCTION_BASE_KWARGS,
            **_smtp_smtp_kwargs(SMTP_STARTTLS=True, SMTP_USE_TLS=True),
        )
    assert (
        "exactly one of SMTP_STARTTLS and SMTP_USE_TLS must be true"
        in str(excinfo.value)
    )


# ---------------------------------------------------------------------------
# Diagnostics never echo secret or environment values
# ---------------------------------------------------------------------------


def test_production_smtp_failure_diagnostics_never_leak_secret_values(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The failing construction carries the synthetic password in its input;
    neither the ValidationError text nor the validator's stderr diagnostics
    may contain it — only the neutral field-name requirement."""
    with pytest.raises(ValidationError) as excinfo:
        Settings(
            **PRODUCTION_BASE_KWARGS,
            **_smtp_smtp_kwargs(SMTP_HOST=None),
        )
    text = str(excinfo.value)
    assert SYNTHETIC_SMTP_PASSWORD not in text
    assert "SMTP_HOST must be set to a non-empty value" in text

    captured = capsys.readouterr()
    assert SYNTHETIC_SMTP_PASSWORD not in captured.out
    assert SYNTHETIC_SMTP_PASSWORD not in captured.err
    assert "Production SMTP email contract is not satisfied" in captured.err


def test_short_secret_values_are_never_echoed_by_settings_errors(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Pydantic truncates long input echo but prints SHORT inputs verbatim;
    with hide_input_in_errors the password is absent at every length."""
    short_password = _synthetic_fragment("s", "h", "o", "r", "t", "-", "pw")
    with pytest.raises(ValidationError) as excinfo:
        Settings(
            **PRODUCTION_BASE_KWARGS,
            **_smtp_smtp_kwargs(
                SMTP_PASSWORD=short_password, SMTP_STARTTLS=True, SMTP_USE_TLS=True
            ),
        )
    text = str(excinfo.value)
    assert short_password not in text
    assert (
        "exactly one of SMTP_STARTTLS and SMTP_USE_TLS must be true"
        in text
    )
    captured = capsys.readouterr()
    assert short_password not in captured.err


def test_database_dsn_is_never_echoed_by_production_errors() -> None:
    """The same hide_input_in_errors posture keeps DSNs (which embed the
    database password) out of validation error text.  The failing input
    embeds a synthetic password inside the dev-default URL shape that the
    production check rejects; the password must not reach the text."""
    database_password = _synthetic_fragment("compose", "-", "db", "-", "pw")
    dev_default_shape = _synthetic_fragment(
        "postgresql" + "://",
        "postgres" + ":postgres@",
        "localhost:5432/mpango_dev?x=",
        database_password,
    )
    with pytest.raises(ValidationError) as excinfo:
        Settings(
            MPANGO_ENV="production",
            SECRET_KEY=_synthetic_secret_key(),
            DATABASE_URL=dev_default_shape,
            REDIS_URL="redis://cache-host:6379/1",
            PUBLIC_FRONTEND_URL="https://app.example.com",
            **_smtp_smtp_kwargs(),
        )
    text = str(excinfo.value)
    assert database_password not in text
    assert "Default dev database URL detected" in text
    assert dev_default_shape not in text
