"""DC-2H static production SMTP compose wiring tests."""

from __future__ import annotations

import re
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPO_ROOT / "docker-compose.prod.yml"

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
