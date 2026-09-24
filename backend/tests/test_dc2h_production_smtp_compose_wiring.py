"""DC-2H production SMTP compose wiring tests.

CTO-AUTH-MPANGO-PROMOTION-M-G1-DC2H-ACTIVE-SMTP-R1-20260924: the earlier
DC-2H draft bound the RETIRED docker-compose.prod.yml; that path is
decommissioned (R1-R4) and must stay absent.  The production entry is the
ACTIVE docker-compose.yml (with its default override), so the contract is
bound there:

1. the backend service carries EXACTLY the nine SMTP keys, each as required
   same-named `${KEY:?...}` interpolation with NO `:-` fallback;
2. no other EMAIL_*/SMTP_* mapping reaches the backend service;
3. no literal provider host or credential appears in the wiring;
4. the retired prod compose stays absent (audit artifact retained).
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"
RETIRED_COMPOSE_FILE = REPO_ROOT / "docker-compose.prod.yml"
DECOMMISSIONED_ARTIFACT = RETIRED_COMPOSE_FILE.with_name(
    RETIRED_COMPOSE_FILE.name + ".decommissioned-r1r4"
)

EXPECTED_SMTP_ENV = {
    "EMAIL_PROVIDER": "${EMAIL_PROVIDER:?EMAIL_PROVIDER must be set}",
    "EMAIL_DELIVERY_MODE": "${EMAIL_DELIVERY_MODE:?EMAIL_DELIVERY_MODE must be set}",
    "SMTP_HOST": "${SMTP_HOST:?SMTP_HOST must be set}",
    "SMTP_PORT": "${SMTP_PORT:?SMTP_PORT must be set}",
    "SMTP_USER": "${SMTP_USER:?SMTP_USER must be set}",
    "SMTP_PASSWORD": "${SMTP_PASSWORD:?SMTP_PASSWORD must be set}",
    "EMAIL_FROM": "${EMAIL_FROM:?EMAIL_FROM must be set}",
    "SMTP_STARTTLS": "${SMTP_STARTTLS:?SMTP_STARTTLS must be set}",
    "SMTP_USE_TLS": "${SMTP_USE_TLS:?SMTP_USE_TLS must be set}",
}

FORBIDDEN_PROVIDER_SNIPPETS = (
    "smtp.126",
    "smtp.gmail",
    "gmail.com",
    "@126.com",
    "@163.com",
    "@gmail.com",
    "@qq.com",
)

EMAIL_LITERAL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _compose_text() -> str:
    return COMPOSE_FILE.read_text(encoding="utf-8")


def _backend_environment() -> dict[str, str]:
    data = yaml.safe_load(_compose_text())
    environment = data["services"]["backend"]["environment"]
    assert isinstance(environment, list)

    entries: dict[str, str] = {}
    for item in environment:
        assert isinstance(item, str)
        key, value = item.split("=", 1)
        entries[key] = value
    return entries


def _smtp_compose_lines() -> list[str]:
    keys = tuple(f"- {key}=" for key in EXPECTED_SMTP_ENV)
    return [
        line.strip()
        for line in _compose_text().splitlines()
        if line.strip().startswith(keys)
    ]


def test_dc2h_backend_environment_contains_exact_smtp_keys() -> None:
    environment = _backend_environment()
    actual = {key: environment.get(key) for key in EXPECTED_SMTP_ENV}
    assert actual == EXPECTED_SMTP_ENV


def test_dc2h_backend_receives_no_other_email_or_smtp_keys() -> None:
    """Of the EMAIL_*/SMTP_* namespace the backend service must receive
    EXACTLY the nine contracted keys — no aliases, no extras, no
    setup-only credential keys smuggled under the email namespace."""
    environment = _backend_environment()
    email_namespace_keys = {
        key for key in environment
        if key.startswith("EMAIL_") or key.startswith("SMTP_")
    }
    assert email_namespace_keys == set(EXPECTED_SMTP_ENV)


def test_dc2h_smtp_values_are_env_refs_only_and_fail_closed() -> None:
    environment = _backend_environment()

    for key, expected in EXPECTED_SMTP_ENV.items():
        value = environment[key]
        assert value == expected
        assert re.fullmatch(rf"\$\{{{key}:\?[^}}]+\}}", value)
        assert ":-" not in value

    assert environment["SMTP_PASSWORD"] == EXPECTED_SMTP_ENV["SMTP_PASSWORD"]
    assert ":-" not in environment["SMTP_PASSWORD"]


def test_dc2h_compose_contains_no_literal_smtp_provider_or_credentials() -> None:
    for line in _smtp_compose_lines():
        lowered = line.lower()
        for forbidden in FORBIDDEN_PROVIDER_SNIPPETS:
            assert forbidden not in lowered

        assert EMAIL_LITERAL_RE.search(line) is None
        assert "password=" not in lowered or line.startswith("- SMTP_PASSWORD=${SMTP_PASSWORD:?")
        assert "token=" not in lowered


def test_dc2h_retired_prod_compose_stays_absent() -> None:
    """The R1-R4 decommissioned path must never come back; the wiring lives
    only on the ACTIVE compose.  Locale-independent facts: the original
    path is absent, the decommissioned audit artifact remains."""
    assert not RETIRED_COMPOSE_FILE.exists(), (
        "docker-compose.prod.yml must stay decommissioned")
    assert DECOMMISSIONED_ARTIFACT.is_file(), (
        "the decommissioned audit artifact must remain as the audit trail")
