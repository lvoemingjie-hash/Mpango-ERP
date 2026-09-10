"""Alembic percent-encoded DATABASE_URL compatibility tests (F1-PCT, R2-ALEMBIC).

Directive: CTO-AUTH-MPANGO-F1-DB-ROLE-R2-ALEMBIC-PERCENT-URL-COMPAT-2026-09-10.

The defect (pre-fix): ``backend/alembic/env.py`` passed a DATABASE_URL whose
password may legitimately contain percent-triplets (``%23``/``%25``/``%2B``)
straight into ``config.set_main_option()``. Alembic's Config interpolates on
READ, so the first read raised ``ValueError: invalid interpolation syntax``
BEFORE any database connection.

The fix under test: ``env._sqlalchemy_url_for_alembic(database_url)`` applies
the async driver prefix and escapes ``%`` as ``%%`` (ConfigParser-safe), so
reading the option back returns the ORIGINAL converted URL byte-for-byte.
``+`` and every percent-triplet keep their URL semantics — nothing is decoded.

These tests load the REAL ``backend/alembic/env.py`` module (no copied
implementation). The only substitution is the ``alembic.context`` runtime
proxy — which cannot exist outside a live ``alembic upgrade`` process —
replaced by a stub holding a REAL ``alembic.config.Config`` bound to the
repo's real ``alembic.ini``. The module's real top-level code then runs the
real fixed path (helper -> set_main_option) at import time, and every node
asserts against genuine ConfigParser/Alembic read-back semantics.

Node map:
- no-percent URL round-trips unchanged (behavior preserved);
- percent-triplet passwords (%23/%25/%2B and friends) round-trip exactly;
- a malformed/incomplete URL is passed through unchanged (validation stays
  where it always lived: at connection time) — pinned, not added;
- a missing DATABASE_URL leaves the ini default in place (existing rule);
- END-TO-END: a REAL ``python -m alembic upgrade head`` subprocess against a
  task-exclusive PostgreSQL 16, using a connection URL whose password needs
  percent-encoding (contains literal ``#``, ``%``, ``+``), migrates an empty
  database to head 037.

All URLs in this file are synthetic. No real credentials appear anywhere.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import textwrap
import types
from pathlib import Path

import pytest
from sqlalchemy import text

BACKEND_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = BACKEND_DIR / "alembic" / "env.py"
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"

# Synthetic password built so its URL encoding exercises the named
# percent-triplets. PLAINTEXT is what a driver/CLI may print; ENCODED is what
# a legitimate connection URL carries.
_PCT_PW_PLAIN = "p#x%+q"                      # literal #, %, +
_PCT_PW_ENCODED = "p%23x%25%2Bq"              # quote(p, safe="") == encoded form
_ORIG_MARKERS = ("%23", "%25", "%2B")


def _load_env_module(monkeypatch, database_url: str | None):
    """Import the REAL env.py with a stubbed alembic.context proxy.

    The stub's ``config`` is a REAL ``alembic.config.Config`` bound to the
    repo's real alembic.ini, so env.py's real ``set_main_option`` call runs
    against genuine ConfigParser semantics. Everything else in env.py
    (models import, helpers) is real.
    """
    import alembic
    from alembic.config import Config

    ini_config = Config(str(ALEMBIC_INI))

    class _AlembicContextStub:
        """Replaces the alembic RUNTIME proxy (unreachable outside a real
        ``alembic upgrade``): exposes the real Config, and stops env.py's
        import exactly at the runtime-dispatch line (is_offline_mode) —
        everything the tests need (the fixed helper, set_main_option
        effects, runner definitions) is already in the module dict."""

        class _StopImport(Exception):
            pass

        def __init__(self, config):
            self._config = config

        @property
        def config(self):
            return self._config

        def __getattr__(self, name):
            raise self._StopImport

    stub = _AlembicContextStub(ini_config)
    # The alembic package imports the real context module eagerly, so the
    # stub must be bound BOTH as the package attribute (what
    # ``from alembic import context`` resolves first) and in sys.modules.
    monkeypatch.setattr(alembic, "context", stub, raising=False)
    monkeypatch.setitem(sys.modules, "alembic.context", stub)
    if database_url is None:
        monkeypatch.delenv("DATABASE_URL", raising=False)
    else:
        monkeypatch.setenv("DATABASE_URL", database_url)
    spec = importlib.util.spec_from_file_location(
        f"f1_alembic_env_{uuid4_hex()}", ENV_PATH
    )
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except _AlembicContextStub._StopImport:
        pass  # controlled stop at the runtime-dispatch line
    return module, ini_config


def uuid4_hex() -> str:
    import uuid

    return uuid.uuid4().hex[:10]


# ---------------------------------------------------------------------------
# 1. URL without percent signs: behavior unchanged
# ---------------------------------------------------------------------------

def test_pct_compat_url_without_percent_roundtrips_unchanged(monkeypatch):
    """[COMPAT — expected PASS] A plain URL (no ``%``) round-trips exactly as
    before the fix: async driver prefix applied, nothing else altered, and
    the real Config read-back equals the converted URL."""
    url = "postgresql://inv_f1_run:plainpw@127.0.0.1:5432/inv_f1_lab"  # pragma: allowlist secret
    module, ini_config = _load_env_module(monkeypatch, url)
    expected = "postgresql+asyncpg://inv_f1_run:plainpw@127.0.0.1:5432/inv_f1_lab"  # pragma: allowlist secret
    assert module._sqlalchemy_url_for_alembic(url) == expected
    stored = ini_config.get_main_option("sqlalchemy.url")
    assert stored == expected, (
        "PCT COMPAT: the plain URL must read back exactly as converted "
        f"(got {stored!r})."
    )


# ---------------------------------------------------------------------------
# 2. Percent-encoded passwords: write + read-back through the REAL Config
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("marker", _ORIG_MARKERS)
def test_pct_compat_encoded_password_roundtrip_exact(monkeypatch, marker):
    """[COMPAT — expected PASS] A URL whose password contains the named
    percent-triplet is accepted by the real set_main_option (the pre-fix
    code raised ValueError: invalid interpolation syntax HERE) and the
    engine-facing section read-back is byte-for-byte the converted URL.

    Real Alembic 1.18 semantics (discovered empirically, pinned here):
    set_main_option VALIDATES interpolation syntax (raw '%' raises) but
    stores raw; get_main_option returns the raw stored value (escaped
    '%'->'%%'); get_section/items INTERPOLATES ('%%'->'%') — and the
    section view is exactly what async_engine_from_config consumes, so the
    engine receives the original URL."""
    # Passwords chosen so the URL contains the marker literally:
    #   %23 -> '#', %25 -> '%', %2B -> '+'
    plain = {"%23": "p#x", "%25": "p%x", "%2B": "p+x"}[marker]
    from urllib.parse import quote

    encoded = quote(plain, safe="")
    assert marker in encoded, f"fixture: {marker} must appear in the encoded password"
    url = f"postgresql://mig:{encoded}@127.0.0.1:5432/inv_f1_lab"  # pragma: allowlist secret
    module, ini_config = _load_env_module(monkeypatch, url)
    expected = "postgresql+asyncpg://" + url.split("://", 1)[1]
    escaped = expected.replace("%", "%%")
    assert module._sqlalchemy_url_for_alembic(url) == escaped, (
        "PCT COMPAT: the helper must produce the ConfigParser-safe (escaped) "
        f"value for set_main_option; got {module._sqlalchemy_url_for_alembic(url)!r}."
    )
    stored = ini_config.get_main_option("sqlalchemy.url")
    assert stored == expected, (
        f"PCT COMPAT: get_main_option must restore the ORIGINAL converted "
        f"URL (ConfigParser collapses '%%' back to '%'); got {stored!r}, "
        f"expected {expected!r}."
    )
    section = ini_config.get_section(ini_config.config_ini_section)
    assert section["sqlalchemy.url"] == expected, (
        f"PCT COMPAT: the engine-facing section value must be the ORIGINAL "
        f"converted URL (got {section['sqlalchemy.url']!r}, expected "
        f"{expected!r})."
    )


def test_pct_compat_full_url_with_all_triplets_roundtrip(monkeypatch):
    """[COMPAT — expected PASS] One URL carrying all three triplets (plus a
    percent-encoded database name position is out of scope — password only,
    per the connection contract): write + read-back equality."""
    url = (
        "postgresql://mig:p%23x%25%2Bq@127.0.0.1:5432/inv_f1_lab"  # pragma: allowlist secret
        "?application_name=f1pct"
    )
    module, ini_config = _load_env_module(monkeypatch, url)
    expected = "postgresql+asyncpg://mig:p%23x%25%2Bq@127.0.0.1:5432/inv_f1_lab?application_name=f1pct"  # pragma: allowlist secret
    section = ini_config.get_section(ini_config.config_ini_section)
    assert section["sqlalchemy.url"] == expected, (
        f"PCT COMPAT: full-URL round-trip must be exact "
        f"(got {section['sqlalchemy.url']!r}, expected {expected!r})."
    )


def test_pct_compat_plus_semantics_never_decoded(monkeypatch):
    """[COMPAT — expected PASS] A RAW '+' in the URL stays a literal '+'
    through helper and Config round-trip (no decoding is introduced)."""
    url = "postgresql://mig:pw+ith+plus@127.0.0.1:5432/inv_f1_lab"  # pragma: allowlist secret
    module, ini_config = _load_env_module(monkeypatch, url)
    expected = "postgresql+asyncpg://mig:pw+ith+plus@127.0.0.1:5432/inv_f1_lab"
    assert module._sqlalchemy_url_for_alembic(url) == expected
    section = ini_config.get_section(ini_config.config_ini_section)
    assert section["sqlalchemy.url"] == expected


# ---------------------------------------------------------------------------
# 3. Wrong / incomplete URLs keep their existing failure semantics
# ---------------------------------------------------------------------------

def test_pct_compat_incomplete_url_passed_through_unchanged(monkeypatch):
    """[PINNED — expected PASS] A malformed/incomplete URL is NOT validated
    or repaired here: the helper passes it through unchanged and the real
    Config accepts the write/read (failures happen at connection time, as
    they always have). This pins that no new validation was added."""
    module, ini_config = _load_env_module(monkeypatch, "not-a-valid-url")
    assert module._sqlalchemy_url_for_alembic("not-a-valid-url") == (
        "not-a-valid-url"
    )
    section = ini_config.get_section(ini_config.config_ini_section)
    assert section["sqlalchemy.url"] == "not-a-valid-url"


def test_pct_compat_missing_database_url_keeps_ini_default(monkeypatch):
    """[PINNED — expected PASS] Missing DATABASE_URL: the override is skipped
    entirely and the ini default remains in place (existing rule)."""
    module, ini_config = _load_env_module(monkeypatch, None)
    default_url = ini_config.get_main_option("sqlalchemy.url")
    assert default_url == (
        "postgresql+asyncpg://mpango:MpangoDBV0.1.4@127.0.0.1:5432/mpango_erp"  # pragma: allowlist secret (verbatim quote of the committed alembic.ini default)
    ), "PCT COMPAT: the alembic.ini default must remain untouched."
    # And the real helper still exists and behaves.
    assert module._sqlalchemy_url_for_alembic(
        "postgresql://u:p@h/db"
    ) == "postgresql+asyncpg://u:p@h/db"


# ---------------------------------------------------------------------------
# 4. END-TO-END: real alembic upgrade head with a percent-encoded URL
# ---------------------------------------------------------------------------

PG16_AVAILABLE = os.environ.get("PCT_COMPAT_TASK_PG_URL", "").strip() != ""


@pytest.mark.integration
@pytest.mark.skipif(
    not PG16_AVAILABLE,
    reason="PCT_COMPAT_TASK_PG_URL not declared: real-migration e2e needs the "
    "task-exclusive PG16 with the percent-encoded-role provisioning",
)
def test_pct_compat_real_alembic_upgrade_head_with_encoded_url():
    """[E2E — expected PASS] A REAL ``python -m alembic upgrade head``
    subprocess, with DATABASE_URL whose password needs percent-encoding
    (literal #, %, + -> %23, %25, %2B), migrates an empty task database to
    head 037 through the fixed env.py — the pre-fix code fails this with
    ValueError before connecting. Provisioning SQL for the role is in the
    task evidence root (synthetic credentials)."""
    database_url = os.environ["PCT_COMPAT_TASK_PG_URL"]
    assert any(m in database_url for m in _ORIG_MARKERS), (
        "e2e fixture: the declared URL must contain a percent-triplet."
    )
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(BACKEND_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
        env={**os.environ, "DATABASE_URL": database_url},
    )
    assert result.returncode == 0, (
        "PCT COMPAT E2E: real alembic upgrade with a percent-encoded URL "
        f"must succeed (rc={result.returncode}).\n"
        f"stdout tail: {result.stdout[-400:]!r}\n"
        f"stderr tail: {result.stderr[-400:]!r}"
    )
    combined = (result.stdout or "") + "\n" + (result.stderr or "")
    assert "Running upgrade 036_retailer_mvp_identity -> 037_payment_declarations_schema" in combined, (
        "PCT COMPAT E2E: the upgrade chain must reach the 037 step "
        f"(combined output tail: {combined[-400:]!r})."
    )
    # Independent head probe against the SAME database via the migration URL.
    from sqlalchemy.ext.asyncio import create_async_engine

    async def _head():
        url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        engine = create_async_engine(url)
        try:
            async with engine.connect() as conn:
                return (
                    await conn.execute(text("SELECT version_num FROM public.alembic_version"))
                ).scalar_one()
        finally:
            await engine.dispose()

    import asyncio

    head = asyncio.run(_head())
    assert head == "037_payment_declarations_schema", (
        f"PCT COMPAT E2E: database head must be 037, got {head!r}."
    )
