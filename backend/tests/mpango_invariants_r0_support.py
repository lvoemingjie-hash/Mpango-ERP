"""Shared fixtures/helpers for MPANGO-MVP-INVARIANTS-R0(-R1) regression candidates.

R1 revision (branch zcode/mpango-mvp-invariants-r0-r1-2026-09-07) adds, without
changing the product-facing invariants:

- TASK-DATABASE OWNERSHIP PROOF: a run may only write to a database that is
  provably owned by this task. Loopback is necessary but NOT sufficient: the
  run must declare the exact container (MPANGO_INVARIANTS_R0_PG_CONTAINER) and
  its owner label (MPANGO_INVARIANTS_R0_PG_OWNER), and the guard verifies via
  `docker inspect` that the label, image (postgres:16), loopback port mapping
  and POSTGRES_DB/POSTGRES_USER all match the configured URL, that
  TEST_DATABASE_URL and DATABASE_URL name the SAME target, that the live
  engine is bound to that same target, and that a live probe lands on the
  declared database+port. Migrations are run by this module's session fixture
  with that verified URL — never via the alembic.ini default. Any mismatch,
  missing config, or non-task container refuses BEFORE any write.
- JWT STRATEGY PROOF: the guard normalizes MPANGO_ENV exactly like the product
  (strip().lower()) and verifies the strategy instance actually bound to the
  app's AuthenticationMiddleware is JwtAuthStrategy (not any Mock variant).
  Unit-level negative controls cover 'test'/'TEST'/whitespace variants.
- CLEANUP HARDENING: supervised background tasks (timeout -> cancel -> await),
  rollback verified before test data is deleted, and partial tenant creation
  is cleaned up on failure.

Product-facing assertions are unchanged from R0: the known product defects
must keep failing (named RED), and assertions must accept correct behavior.
"""
from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import subprocess
import sys
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import text

from database.session import AsyncSessionLocal, async_engine

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
BASELINE_MIGRATION_HEAD = "037_payment_declarations_schema"
SUPERVISE_TIMEOUT_S = 30.0

CONTAINER_ENV_VAR = "MPANGO_INVARIANTS_R0_PG_CONTAINER"
OWNER_LABEL_ENV_VAR = "MPANGO_INVARIANTS_R0_PG_OWNER"
OWNER_LABEL_PREFIX = "zcode-mvp-invariants"
REDIS_CONTAINER_ENV_VAR = "MPANGO_INVARIANTS_R0_REDIS_CONTAINER"
# F1 role-closure contract: the migration identity gets its own explicit
# connection declaration. It must never fall back to the run-session URL,
# the run user, alembic.ini, or any host default.
MIGRATION_URL_ENV_VAR = "MPANGO_INVARIANTS_R0_MIGRATION_DATABASE_URL"
# Optional task-evidence capture of the sanitized real migration output
# (off by default; never read by the product, only by the task env).
MIGRATION_LOG_ENV_VAR = "MPANGO_INVARIANTS_R0_MIGRATION_LOG"


@dataclass(frozen=True)
class RedisTargetBinding:
    """Canonical Redis target binding used by the ownership guard."""

    scheme: str
    host: str
    port: int
    db: int


def _coerce_int_field(
    value: object,
    *,
    field_name: str,
    context: str,
    minimum: int,
) -> int:
    try:
        coerced = int(value)
    except (TypeError, ValueError) as exc:
        raise GuardRefused(
            f"GUARD_REFUSED_REDIS_OWNERSHIP: {context} {field_name} "
            f"{value!r} is not a valid integer."
        ) from exc
    if coerced < minimum:
        raise GuardRefused(
            f"GUARD_REFUSED_REDIS_OWNERSHIP: {context} {field_name} "
            f"{coerced} is below the minimum allowed value {minimum}."
        )
    return coerced


def _coerce_bool_field(value: object, *, field_name: str, context: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    raise GuardRefused(
        f"GUARD_REFUSED_REDIS_OWNERSHIP: {context} {field_name} {value!r} "
        "is not a valid boolean flag."
    )


def _normalize_loopback_host(host: object, *, context: str) -> str:
    raw = str(host or "").strip()
    if not raw:
        raise GuardRefused(
            f"GUARD_REFUSED_REDIS_OWNERSHIP: {context} host is missing."
        )
    lowered = raw.lower()
    if lowered == "localhost":
        return "127.0.0.1"
    try:
        ip = ipaddress.ip_address(lowered)
    except ValueError as exc:
        raise GuardRefused(
            f"GUARD_REFUSED_REDIS_OWNERSHIP: {context} host {raw!r} is not "
            "loopback; use an explicit loopback literal or localhost."
        ) from exc
    if not ip.is_loopback:
        raise GuardRefused(
            f"GUARD_REFUSED_REDIS_OWNERSHIP: {context} host {raw!r} is not loopback."
        )
    return "127.0.0.1" if ip.version == 4 else "::1"


def _describe_redis_url_target(redis_url: str) -> RedisTargetBinding:
    parsed = urlparse(redis_url.strip())
    scheme = (parsed.scheme or "").strip().lower()
    if scheme not in {"redis", "rediss", "redis+ssl"}:
        raise GuardRefused(
            "GUARD_REFUSED_REDIS_OWNERSHIP: REDIS_URL scheme must be "
            "redis:// or rediss://."
        )
    host = parsed.hostname
    if host is None:
        raise GuardRefused(
            "GUARD_REFUSED_REDIS_OWNERSHIP: REDIS_URL host is missing."
        )
    if parsed.port is None:
        raise GuardRefused(
            "GUARD_REFUSED_REDIS_OWNERSHIP: REDIS_URL port is missing."
        )
    db_path = (parsed.path or "").lstrip("/")
    if not db_path:
        raise GuardRefused(
            "GUARD_REFUSED_REDIS_OWNERSHIP: REDIS_URL database index is missing."
        )
    query = parse_qs(parsed.query, keep_blank_values=True)
    tls = scheme in {"rediss", "redis+ssl"}
    if "ssl" in query:
        tls = _coerce_bool_field(
            query["ssl"][-1], field_name="ssl", context="declared REDIS_URL query"
        )
    canonical_scheme = "rediss" if tls else "redis"
    return RedisTargetBinding(
        scheme=canonical_scheme,
        host=_normalize_loopback_host(host, context="declared REDIS_URL"),
        port=_coerce_int_field(
            parsed.port,
            field_name="port",
            context="declared REDIS_URL",
            minimum=1,
        ),
        db=_coerce_int_field(
            db_path,
            field_name="db",
            context="declared REDIS_URL",
            minimum=0,
        ),
    )


def _describe_redis_client_target(client: object) -> RedisTargetBinding:
    pool = getattr(client, "connection_pool", None)
    if pool is None:
        raise GuardRefused(
            "GUARD_REFUSED_REDIS_OWNERSHIP: Redis client has no connection_pool."
        )
    connection_kwargs = getattr(pool, "connection_kwargs", None)
    if not isinstance(connection_kwargs, Mapping):
        raise GuardRefused(
            "GUARD_REFUSED_REDIS_OWNERSHIP: Redis client connection_pool "
            "does not expose readable connection_kwargs."
        )
    missing = [
        name
        for name in ("host", "port", "db")
        if name not in connection_kwargs or connection_kwargs.get(name) in (None, "")
    ]
    if missing:
        raise GuardRefused(
            "GUARD_REFUSED_REDIS_OWNERSHIP: Redis client binding is incomplete; "
            f"missing {', '.join(missing)}."
        )
    connection_class = getattr(pool, "connection_class", None)
    class_name = getattr(connection_class, "__name__", "")
    ssl_flag = None
    if "ssl" in connection_kwargs:
        ssl_flag = _coerce_bool_field(
            connection_kwargs.get("ssl"),
            field_name="ssl",
            context="Redis client binding",
        )
    class_tls = class_name == "SSLConnection"
    if ssl_flag is False and class_tls:
        raise GuardRefused(
            "GUARD_REFUSED_REDIS_OWNERSHIP: Redis client binding connection "
            "class and ssl flag disagree."
        )
    tls = class_tls or bool(ssl_flag)
    return RedisTargetBinding(
        scheme="rediss" if tls else "redis",
        host=_normalize_loopback_host(
            connection_kwargs.get("host"), context="Redis client binding"
        ),
        port=_coerce_int_field(
            connection_kwargs.get("port"),
            field_name="port",
            context="Redis client binding",
            minimum=1,
        ),
        db=_coerce_int_field(
            connection_kwargs.get("db"),
            field_name="db",
            context="Redis client binding",
            minimum=0,
        ),
    )


def _redis_binding_mismatch_message(
    actual: RedisTargetBinding, declared: RedisTargetBinding
) -> str:
    mismatches = []
    for field_name in ("scheme", "host", "port", "db"):
        actual_value = getattr(actual, field_name)
        declared_value = getattr(declared, field_name)
        if actual_value != declared_value:
            mismatches.append(
                f"{field_name}={actual_value!r} does not match declared "
                f"{declared_value!r}"
            )
    if not mismatches:
        return ""
    return (
        "GUARD_REFUSED_REDIS_OWNERSHIP: cached Redis client binding "
        f"{actual!r} does not match declared target {declared!r}; "
        + "; ".join(mismatches)
    )


def verify_task_redis_ownership_sync(client: object) -> str:
    """Pre-deletion ownership proof for the task Redis (CTO R1-R2 remediation).

    Any cache-key deletion must happen ONLY on a provably task-owned Redis.
    The proof binds the actual client/pool that will be used for deletion to
    the declared task target BEFORE any network I/O. Returns the verified
    ``host:port`` of the declared instance. Refuses BEFORE any deletion when:

    1. MPANGO_INVARIANTS_R0_REDIS_CONTAINER / owner label / REDIS_URL missing;
    2. the cached client's actual pool target cannot be resolved or does not
       match the declared target (host, port, db, scheme/TLS);
    3. REDIS_URL host is not loopback;
    4. owner label outside the ``zcode-mvp-invariants`` namespace;
    5. docker inspect: label mismatch, image not ``redis:*``, or the 6379
       mapping is not ``127.0.0.1:<REDIS_URL port>``.

    Same discipline as verify_task_database_ownership_sync: a mismatch,
    missing config, or undeclared container refuses — callers must never
    delete (or scan) keys on an unproven Redis instance.
    """
    container = os.environ.get(REDIS_CONTAINER_ENV_VAR, "").strip()
    owner_label = os.environ.get(OWNER_LABEL_ENV_VAR, "").strip()
    redis_url = os.environ.get("REDIS_URL", "").strip()

    missing = [
        name
        for name, value in (
            (REDIS_CONTAINER_ENV_VAR, container),
            (OWNER_LABEL_ENV_VAR, owner_label),
            ("REDIS_URL", redis_url),
        )
        if not value
    ]
    if missing:
        raise GuardRefused(
            "GUARD_REFUSED_REDIS_OWNERSHIP: missing required environment: "
            f"{', '.join(missing)}. Cache-key deletion requires a declared, "
            "task-owned Redis instance."
        )
    declared = _describe_redis_url_target(redis_url)
    actual = _describe_redis_client_target(client)
    mismatch = _redis_binding_mismatch_message(actual, declared)
    if mismatch:
        raise GuardRefused(mismatch)
    if not owner_label.startswith(OWNER_LABEL_PREFIX):
        raise GuardRefused(
            "GUARD_REFUSED_REDIS_OWNERSHIP: owner label must be a "
            f"{OWNER_LABEL_PREFIX}-* task label, got {owner_label!r}."
        )
    info = _docker_inspect(container)
    labels = (info.get("Config") or {}).get("Labels") or {}
    if labels.get("mpango.owner") != owner_label:
        raise GuardRefused(
            "GUARD_REFUSED_REDIS_OWNERSHIP: container "
            f"'{container}' label mpango.owner={labels.get('mpango.owner')!r} "
            f"does not match declared owner {owner_label!r}."
        )
    image_name = str((info.get("Config") or {}).get("Image") or "")
    if not image_name.startswith("redis:"):
        raise GuardRefused(
            "GUARD_REFUSED_REDIS_OWNERSHIP: container image "
            f"'{image_name}' is not redis:*."
        )
    mapping = (info.get("NetworkSettings") or {}).get("Ports") or {}
    port_bindings = mapping.get("6379/tcp") or []
    mapped = {b.get("HostIp"): b.get("HostPort") for b in port_bindings}
    if mapped.get("127.0.0.1") != str(declared.port):
        raise GuardRefused(
            "GUARD_REFUSED_REDIS_OWNERSHIP: container 6379 mapping "
            f"{mapped} does not match REDIS_URL host/port (127.0.0.1:{declared.port})."
        )
    return f"{declared.host}:{declared.port}"


class GuardRefused(RuntimeError):
    """Raised when the environment fails a pre-write guard. Never retry."""


# ---------------------------------------------------------------------------
# Task-database ownership proof
# ---------------------------------------------------------------------------

def _docker_inspect(container: str) -> dict:
    try:
        raw = subprocess.run(
            ["docker", "inspect", "--format", "{{json .}}", container],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GuardRefused(f"GUARD_REFUSED_DATABASE_OWNERSHIP: docker inspect failed: {exc}") from exc
    if raw.returncode != 0:
        raise GuardRefused(
            "GUARD_REFUSED_DATABASE_OWNERSHIP: declared task container "
            f"'{container}' does not exist (docker inspect rc={raw.returncode})."
        )
    return json.loads(raw.stdout)


def _parse_pg_url(url: str):
    """Parse a postgres URL into (host, port, dbname, username)."""
    parsed = urlparse(url.replace("postgresql+asyncpg://", "postgresql://", 1))
    return (
        parsed.hostname,
        parsed.port or 5432,
        (parsed.path or "").lstrip("/"),
        parsed.username or "",
    )


def _assert_engine_binding(engine_url, *, host: str, port: int, dbname: str, username: str) -> None:
    """The live application/test engine must point at the verified task target
    AS THE DECLARED RUN USER (F1 role closure: an engine bound to the
    bootstrap/migration identity or to an undeclared user must be refused)."""
    if (
        str(engine_url.host) != host
        or int(engine_url.port or 5432) != port
        or str(engine_url.database) != dbname
    ):
        raise GuardRefused(
            "GUARD_REFUSED_DATABASE_OWNERSHIP: live engine target "
            f"({engine_url.host}:{engine_url.port}/{engine_url.database}) does "
            f"not match the verified task target ({host}:{port}/{dbname})."
        )
    if str(engine_url.username or "") != username:
        raise GuardRefused(
            "GUARD_REFUSED_DATABASE_OWNERSHIP: live engine user "
            f"{engine_url.username!r} is not the declared test-session user "
            f"{username!r}; the application engine must never run as the "
            "bootstrap/migration identity or an undeclared role."
        )


def verify_task_database_ownership_sync() -> str:
    """Pre-write ownership proof (sync part). Returns the verified RUN URL.

    F1 role-closure contract (three identities):

    - container bootstrap / migration identity: ``POSTGRES_USER`` of the task
      container, bound to ``MPANGO_INVARIANTS_R0_MIGRATION_DATABASE_URL``;
    - test-session identity: the user in ``TEST_DATABASE_URL`` (==
      ``DATABASE_URL``); must be a DIFFERENT, non-privileged role;
    - reporting identity: ``reporting_role`` / ``reporting_user`` created by
      migration 011 (read-only; not used by this suite's connections).

    Refuses (before any write) when: any declaration missing,
    TEST_DATABASE_URL != DATABASE_URL, non-loopback host, missing db name,
    owner label outside the task namespace, container label/image/port/db
    mismatch, the migration URL does not bind to the same task container
    target (host/port/db) with the container POSTGRES_USER, the run user
    equals the bootstrap/migration user, or the live engine is not bound to
    the declared run user and target.
    """
    container = os.environ.get(CONTAINER_ENV_VAR, "").strip()
    owner_label = os.environ.get(OWNER_LABEL_ENV_VAR, "").strip()
    test_url = os.environ.get("TEST_DATABASE_URL", "").strip()
    db_url = os.environ.get("DATABASE_URL", "").strip()

    missing = [
        name
        for name, value in (
            (CONTAINER_ENV_VAR, container),
            (OWNER_LABEL_ENV_VAR, owner_label),
            ("TEST_DATABASE_URL", test_url),
            ("DATABASE_URL", db_url),
        )
        if not value
    ]
    if missing:
        raise GuardRefused(
            "GUARD_REFUSED_DATABASE_OWNERSHIP: missing required environment: "
            f"{', '.join(missing)}. This suite only runs against a declared, "
            "task-owned disposable database."
        )
    if test_url != db_url:
        raise GuardRefused(
            "GUARD_REFUSED_DATABASE_OWNERSHIP: TEST_DATABASE_URL and "
            "DATABASE_URL name different targets; the test session must use "
            "one explicit target."
        )

    host, port, dbname, run_user = _parse_pg_url(test_url)
    if host not in LOOPBACK_HOSTS:
        raise GuardRefused(
            f"GUARD_REFUSED_DATABASE_OWNERSHIP: URL host '{host}' is not loopback."
        )
    if not dbname:
        raise GuardRefused("GUARD_REFUSED_DATABASE_OWNERSHIP: URL has no database name.")
    if not run_user:
        raise GuardRefused(
            "GUARD_REFUSED_DATABASE_OWNERSHIP: TEST_DATABASE_URL has no user; "
            "the test-session role must be explicitly declared."
        )

    if not owner_label.startswith(OWNER_LABEL_PREFIX):
        raise GuardRefused(
            "GUARD_REFUSED_DATABASE_OWNERSHIP: owner label must be a "
            f"{OWNER_LABEL_PREFIX}-* task label, got {owner_label!r}."
        )

    # --- F1 role closure: the migration identity declaration. These checks
    # deliberately sit after the original refusals (same messages preserved)
    # and before any docker inspect / subprocess work.
    migration_url = os.environ.get(MIGRATION_URL_ENV_VAR, "").strip()
    if not migration_url:
        raise GuardRefused(
            "GUARD_REFUSED_DATABASE_OWNERSHIP: missing required environment: "
            f"{MIGRATION_URL_ENV_VAR}. Migrations must run under an explicit, "
            "declared bootstrap/migration identity URL — never the run "
            "session, alembic.ini or host defaults."
        )
    mig_host, mig_port, mig_dbname, mig_user = _parse_pg_url(migration_url)
    if mig_host not in LOOPBACK_HOSTS:
        raise GuardRefused(
            "GUARD_REFUSED_DATABASE_OWNERSHIP: migration URL host "
            f"'{mig_host}' is not loopback."
        )
    if (mig_host, mig_port, mig_dbname) != (host, port, dbname):
        raise GuardRefused(
            "GUARD_REFUSED_DATABASE_OWNERSHIP: migration URL target "
            f"({mig_host}:{mig_port}/{mig_dbname}) differs from the run "
            f"session target ({host}:{port}/{dbname}); both connections must "
            "bind to the SAME task container, port and database (usernames "
            "may differ)."
        )
    if run_user == mig_user:
        raise GuardRefused(
            "GUARD_REFUSED_DATABASE_OWNERSHIP: the test-session user equals "
            f"the migration/bootstrap user {mig_user!r}; the run identity "
            "must be a separate, non-privileged role."
        )

    info = _docker_inspect(container)
    labels = (info.get("Config") or {}).get("Labels") or {}
    if labels.get("mpango.owner") != owner_label:
        raise GuardRefused(
            "GUARD_REFUSED_DATABASE_OWNERSHIP: container "
            f"'{container}' label mpango.owner={labels.get('mpango.owner')!r} "
            f"does not match declared owner {owner_label!r}."
        )
    config = info.get("Config") or {}
    image_name = str(config.get("Image") or "")
    if not image_name.startswith("postgres:16"):
        raise GuardRefused(
            f"GUARD_REFUSED_DATABASE_OWNERSHIP: container image '{image_name}' "
            "is not postgres:16."
        )
    mapping = (info.get("NetworkSettings") or {}).get("Ports") or {}
    port_bindings = mapping.get("5432/tcp") or []
    mapped = {b.get("HostIp"): b.get("HostPort") for b in port_bindings}
    if mapped.get("127.0.0.1") != str(port):
        raise GuardRefused(
            "GUARD_REFUSED_DATABASE_OWNERSHIP: container 5432 mapping "
            f"{mapped} does not match URL host/port (127.0.0.1:{port})."
        )
    env_pairs = dict(
        item.split("=", 1) for item in (config.get("Env") or []) if "=" in item
    )
    if env_pairs.get("POSTGRES_DB") != dbname:
        raise GuardRefused(
            f"GUARD_REFUSED_DATABASE_OWNERSHIP: container POSTGRES_DB "
            f"{env_pairs.get('POSTGRES_DB')!r} != URL database {dbname!r}; "
            "refusing to write into an unexpected (possibly pre-existing) database."
        )
    if env_pairs.get("POSTGRES_USER") != mig_user:
        raise GuardRefused(
            "GUARD_REFUSED_DATABASE_OWNERSHIP: container POSTGRES_USER "
            f"{env_pairs.get('POSTGRES_USER')!r} must bind the "
            "bootstrap/migration identity, but the migration URL user is "
            f"{mig_user!r}."
        )

    _assert_engine_binding(
        async_engine.url, host=host, port=port, dbname=dbname, username=run_user
    )
    return test_url


def _add_url_password_forms(url: str, forms: set) -> None:
    """Add every redaction-worthy representation of ``url``'s password.

    R2 (CTO F2-R1): ``urlparse(...).password`` PRESERVES percent-encoding.
    The redaction set must therefore contain the URL's own encoded
    representation AND the decoded plaintext (the actual password semantics
    — a driver diagnostic may print the decoded form as bare, non-URL text
    which no URL-shape regex can catch) plus the plaintext's
    ``quote(safe='')`` and ``quote_plus`` forms. Percent-decoding is applied
    exactly once (``unquote`` — ``+`` is a literal character in URL
    userinfo, never a form-space); no recursive decoding.
    """
    from urllib.parse import quote, quote_plus, unquote

    if not url:
        return
    parsed = urlparse(url.replace("postgresql+asyncpg://", "postgresql://", 1))
    encoded = parsed.password
    if not encoded:
        return
    forms.add(encoded)  # the URL's own (possibly percent-encoded) form
    plaintext = unquote(encoded)  # single decode; '+' stays literal
    if plaintext:
        forms.add(plaintext)
        forms.add(quote(plaintext, safe=""))
        forms.add(quote_plus(plaintext))


def _task_known_secrets(migration_url: str | None = None) -> list:
    """Every task-known credential that could appear in migration output.

    R2 (CTO F2-R1): the set covers, per URL — the URL's own encoded password
    representation, the DECODED plaintext, and the plaintext's
    ``quote(safe='')`` / ``quote_plus`` forms — for the ACTUAL
    ``migration_url`` call argument first, then the three environment URLs
    (migration declaration, test-session, run). REPORTING_USER_PASSWORD
    (embedded by migration 011 in ``CREATE USER ... PASSWORD`` SQL) keeps
    its raw/quote/quote_plus handling. Secret values are used for MATCHING
    only; they (and hashes of them) are never emitted as diagnostics.
    """
    from urllib.parse import quote, quote_plus

    forms: set = set()
    urls = []
    if migration_url:
        urls.append(migration_url)  # the actual call argument, not just ambient env
    for env_name in (MIGRATION_URL_ENV_VAR, "TEST_DATABASE_URL", "DATABASE_URL"):
        value = os.environ.get(env_name, "")
        if value:
            urls.append(value)
    for url in urls:
        _add_url_password_forms(url, forms)
    reporting_password = os.environ.get("REPORTING_USER_PASSWORD", "")
    if reporting_password:
        forms.add(reporting_password)
        forms.add(quote(reporting_password, safe=""))
        forms.add(quote_plus(reporting_password))
    # Longest first so overlapping encodings collapse cleanly.
    return sorted((f for f in forms if f), key=len, reverse=True)


def _sanitize_connection_output(raw: str, migration_url: str) -> str:
    """Strip credentials from subprocess output before it enters any message.

    R2 (CTO F2-R1): the redaction set now includes DECODED password
    plaintexts (percent-encoded connection URLs are the norm; a driver may
    print the decoded password as bare text that no URL-shape regex can
    catch) and the ACTUAL ``migration_url`` call argument's secret joins the
    ambient environment's. Every exit (nonzero, timeout, optional evidence
    log) passes through this single strategy. Secret values are matched,
    never echoed.
    """
    sanitized = raw
    for secret in _task_known_secrets(migration_url):
        sanitized = sanitized.replace(secret, "***")
    import re as _re

    sanitized = _re.sub(
        r"(postgresql(\+asyncpg)?://[^:\s/@]+:)[^@\s]+(@)", r"\1***\3", sanitized
    )
    return sanitized


async def _live_identity_probe(db_url: str) -> dict:
    """Open ONE connection on the given URL and return its live identity facts:
    current_database, session_user, current_user, server version."""
    from sqlalchemy.ext.asyncio import create_async_engine

    url = db_url
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    text("SELECT current_database(), session_user, current_user, version()")
                )
            ).one()
        return {
            "database": row[0],
            "session_user": row[1],
            "current_user": row[2],
            "version": str(row[3]),
        }
    finally:
        await engine.dispose()


async def verify_migration_identity_live(migration_url: str) -> dict:
    """Live proof that the migration connection really is the declared
    bootstrap/migration identity on the declared task database (F1 role
    closure). Returns the identity facts (also used as evidence in the
    integration test / ledger)."""
    _, _, dbname, mig_user = _parse_pg_url(migration_url)
    facts = await _live_identity_probe(migration_url)
    if facts["database"] != dbname:
        raise GuardRefused(
            "GUARD_REFUSED_MIGRATION_IDENTITY: migration connection landed on "
            f"db={facts['database']!r}, expected {dbname!r}."
        )
    if facts["session_user"] != mig_user or facts["current_user"] != mig_user:
        raise GuardRefused(
            "GUARD_REFUSED_MIGRATION_IDENTITY: migration connection identity "
            f"is session_user={facts['session_user']!r} "
            f"current_user={facts['current_user']!r}, expected the declared "
            f"bootstrap/migration user {mig_user!r}."
        )
    if not facts["version"].startswith("PostgreSQL 16."):
        raise GuardRefused(
            "GUARD_REFUSED_MIGRATION_IDENTITY: server is "
            f"{facts['version'].split(',')[0]!r}, expected a PostgreSQL 16 "
            "cluster matching the declared postgres:16 task container."
        )
    return facts


async def verify_run_identity_live(db_url: str) -> dict:
    """Pre-migration readiness: the RUN connection must really be the declared
    test-session role, non-privileged, with no role memberships (so it can
    never SET ROLE into the bootstrap identity). pg_roles does not depend on
    migrations, so this runs before the migration step."""
    _, _, dbname, run_user = _parse_pg_url(db_url)
    facts = await _live_identity_probe(db_url)
    if facts["database"] != dbname:
        raise GuardRefused(
            "GUARD_REFUSED_DATABASE_OWNERSHIP: live connection landed on "
            f"db={facts['database']!r}, expected {dbname!r}."
        )
    if not facts["version"].startswith("PostgreSQL 16."):
        raise GuardRefused(
            "GUARD_REFUSED_DATABASE_OWNERSHIP: server is "
            f"{facts['version'].split(',')[0]!r}, expected a PostgreSQL 16 "
            "cluster matching the declared postgres:16 task container."
        )
    if facts["session_user"] != run_user or facts["current_user"] != run_user:
        raise GuardRefused(
            "GUARD_REFUSED_RUN_ROLE: run connection identity is "
            f"session_user={facts['session_user']!r} "
            f"current_user={facts['current_user']!r}, expected the declared "
            f"test-session user {run_user!r} (no SET ROLE / identity switch "
            "is permitted)."
        )
    async with AsyncSessionLocal() as probe:
        role = (
            await probe.execute(
                text(
                    "SELECT rolcanlogin, rolsuper, rolcreatedb, "
                    "rolcreaterole, rolreplication FROM pg_roles "
                    "WHERE rolname = :u"
                ),
                {"u": run_user},
            )
        ).first()
        if role is None:
            raise GuardRefused(
                f"GUARD_REFUSED_RUN_ROLE: declared run user {run_user!r} has "
                "no pg_roles row."
            )
        caps = dict(zip(("login", "super", "createdb", "createrole", "replication"), role))
        if not caps["login"]:
            raise GuardRefused(
                f"GUARD_REFUSED_RUN_ROLE: run user {run_user!r} cannot log in."
            )
        forbidden = [k for k in ("super", "createdb", "createrole", "replication") if caps[k]]
        if forbidden:
            raise GuardRefused(
                f"GUARD_REFUSED_RUN_ROLE: run user {run_user!r} must not hold "
                f"privileged attributes {forbidden}; the test session must be "
                "an ordinary role."
            )
        memberships = (
            await probe.execute(
                text(
                    "SELECT r.rolname FROM pg_auth_members m "
                    "JOIN pg_roles r ON r.oid = m.roleid "
                    "JOIN pg_roles ru ON ru.oid = m.member "
                    "WHERE ru.rolname = :u"
                ),
                {"u": run_user},
            )
        ).scalars().all()
        if memberships:
            raise GuardRefused(
                f"GUARD_REFUSED_RUN_ROLE: run user {run_user!r} must have no "
                f"role memberships (found {sorted(memberships)!r}); a "
                "membership (e.g. in the bootstrap role) would allow SET "
                "ROLE privilege escalation."
            )
    facts["capabilities"] = caps
    facts["memberships"] = []
    return facts


async def verify_run_privileges_post_migration(db_url: str) -> None:
    """Post-migration readiness: prove the run role actually holds every
    privilege the real fixtures consume (CTO: five boolean role flags prove
    nothing about usability). Each probe names the consuming code path; the
    full list and rationale live in REPAIR_LEDGER §privileges. Refusal here
    happens BEFORE any business assertion."""
    _, _, _, run_user = _parse_pg_url(db_url)

    def refuse(detail: str) -> GuardRefused:
        return GuardRefused(
            "GUARD_REFUSED_RUN_ROLE_PRIVILEGES: the run role lacks a "
            "privilege the real fixtures consume; provisioning per "
            "REPAIR_LEDGER §privileges is incomplete — refusing before any "
            f"business write. {detail}"
        )

    async with AsyncSessionLocal() as probe:
        # Database-level CREATE — TenantIdentity.create -> CREATE SCHEMA.
        has = (
            await probe.execute(
                text("SELECT has_database_privilege(:u, current_database(), 'CREATE')"),
                {"u": run_user},
            )
        ).scalar_one()
        if not has:
            raise refuse("missing CREATE on database (tenant schema creation).")

        # public schema USAGE+CREATE — scripts/bootstrap_tenant_schema
        # CREATE OR REPLACE FUNCTION public.prevent_ledger_modification().
        usage, create = (
            await probe.execute(
                text(
                    "SELECT has_schema_privilege(:u, 'public', 'USAGE'), "
                    "has_schema_privilege(:u, 'public', 'CREATE')",
                ),
                {"u": run_user},
            )
        ).one()
        if not (usage and create):
            raise refuse("missing USAGE/CREATE on schema public (bootstrap function replace).")

        # Public rows — support.seed_public_tenant_rows / drop_tenant
        # INSERT/UPDATE/DELETE/SELECT on wholesalers, retailers, bindings.
        for table in (
            "public.wholesalers",
            "public.retailers",
            "public.wholesaler_retailer_bindings",
        ):
            for priv in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                has = (
                    await probe.execute(
                        text(f"SELECT has_table_privilege(:u, '{table}', '{priv}')"),
                        {"u": run_user},
                    )
                ).scalar_one()
                if not has:
                    raise refuse(f"missing {priv} on {table} (public tenant rows).")

        # alembic_version SELECT — the fixture's own head verification.
        has = (
            await probe.execute(
                text("SELECT has_table_privilege(:u, 'public.alembic_version', 'SELECT')"),
                {"u": run_user},
            )
        ).scalar_one()
        if not has:
            raise refuse("missing SELECT on public.alembic_version (head verification).")

        # Public sequences — any serial defaults consumed by writes.
        missing_seqs = (
            await probe.execute(
                text(
                    "SELECT count(*) FROM information_schema.sequences s "
                    "JOIN pg_namespace n ON n.nspname = s.sequence_schema "
                    "WHERE n.nspname = 'public' AND NOT has_sequence_privilege("
                    ":u, quote_ident(s.sequence_schema) || '.' || s.sequence_name, 'USAGE')"
                ),
                {"u": run_user},
            )
        ).scalar_one()
        if missing_seqs:
            raise refuse(f"{missing_seqs} public sequence(s) lack USAGE for the run role.")

        # Ledger-immutability function: bootstrap must be able to CREATE OR
        # REPLACE it, which requires EXECUTE *and* ownership (PG refuses
        # replacement by a non-owner).
        owner = (
            await probe.execute(
                text(
                    "SELECT pg_get_userbyid(p.proowner) FROM pg_proc p "
                    "JOIN pg_namespace n ON n.oid = p.pronamespace "
                    "WHERE n.nspname = 'public' "
                    "AND p.proname = 'prevent_ledger_modification'"
                )
            )
        ).scalar_one_or_none()
        if owner is None:
            raise refuse("public.prevent_ledger_modification() missing after migration.")
        if owner != run_user:
            raise refuse(
                "public.prevent_ledger_modification() is owned by "
                f"{owner!r}; the bootstrap path replaces it via CREATE OR "
                "REPLACE which requires ownership by the run role."
            )
        has = (
            await probe.execute(
                text(
                    "SELECT has_function_privilege(:u, "
                    "'public.prevent_ledger_modification()', 'EXECUTE')",
                ),
                {"u": run_user},
            )
        ).scalar_one()
        if not has:
            raise refuse("missing EXECUTE on public.prevent_ledger_modification().")


def run_public_migrations(migration_url: str) -> None:
    """Upgrade the verified task database to the baseline migration head.

    F1 role closure: migrations run ONLY in a subprocess whose DATABASE_URL
    is the declared migration URL (bootstrap/migration identity). The parent
    process environment, the application engine and AsyncSessionLocal stay
    bound to the test-session role throughout — no global env switching. The
    alembic.ini default address is never used (env.py overrides DATABASE_URL
    from the child env, and the guard refuses to run without the explicit
    migration URL). Subprocess output is sanitized before it can reach any
    exception message or public report.

    R1 (CTO F2): sanitization covers every task-known secret (migration/run
    URL passwords, REPORTING_USER_PASSWORD, URL-encoded forms); the TIMEOUT
    exit follows the same strategy (partial output sanitized); an optional
    off-by-default task-evidence env captures the sanitized real migration
    output for the task's evidence root.
    """
    backend_dir = Path(__file__).resolve().parents[1]
    reporting_password = os.environ.get("REPORTING_USER_PASSWORD", "").strip()
    if not reporting_password:
        raise GuardRefused(
            "GUARD_REFUSED_MIGRATION: REPORTING_USER_PASSWORD must be set for "
            "migration 011; refusing to run migrations with incomplete config."
        )
    migration_log = os.environ.get(MIGRATION_LOG_ENV_VAR, "").strip()
    try:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=str(backend_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=300,
            env={**os.environ, "DATABASE_URL": migration_url},
        )
    except subprocess.TimeoutExpired as expired:
        partial = ""
        for chunk in (getattr(expired, "stdout", None), getattr(expired, "stderr", None)):
            if chunk:
                if isinstance(chunk, bytes):
                    chunk = chunk.decode("utf-8", errors="replace")
                partial += "\n" + chunk
        raise GuardRefused(
            "GUARD_REFUSED_MIGRATION: alembic upgrade head TIMED OUT under "
            "the declared migration identity (connection credentials "
            f"sanitized):{_sanitize_connection_output(partial, migration_url)}"
        ) from expired
    if migration_log:
        try:
            with open(migration_log, "a", encoding="utf-8") as handle:
                handle.write(_sanitize_connection_output(result.stdout or "", migration_url))
                handle.write("\n--- stderr ---\n")
                handle.write(_sanitize_connection_output(result.stderr or "", migration_url))
                handle.write("\n--- rc=%d ---\n" % result.returncode)
        except OSError:
            pass
    if result.returncode != 0:
        raise GuardRefused(
            "GUARD_REFUSED_MIGRATION: alembic upgrade head failed under the "
            "declared migration identity against the declared task target "
            "(connection credentials sanitized):\n"
            f"{_sanitize_connection_output(result.stdout or '', migration_url)}\n"
            f"{_sanitize_connection_output(result.stderr or '', migration_url)}"
        )


async def align_fixture_object_ownership(migration_url: str) -> None:
    """Post-migration ownership alignment on the MIGRATION identity.

    The product tenant bootstrap (running as the test-session role) executes
    ``CREATE OR REPLACE FUNCTION public.prevent_ledger_modification()``;
    PostgreSQL refuses replacement by a non-owner, so the function created
    by migration 010 under the migration identity must be owned by the run
    role before any bootstrap runs. This is the COMPLETE list of public
    objects the bootstrap replaces (scripts/bootstrap_tenant_schema.py has
    exactly one public-function replacement); it is executed idempotently on
    the migration connection right after the real migrations, with the
    rationale recorded in REPAIR_LEDGER §privileges. No REASSIGN OWNED, no
    cross-database shortcuts, no inheritance.
    """
    import re as _re
    from sqlalchemy.ext.asyncio import create_async_engine

    _, _, _, run_user = _parse_pg_url(os.environ["TEST_DATABASE_URL"])
    if not _re.fullmatch(r"[a-z_][a-z0-9_]*", run_user):
        # Identifier-safety gate (the value originates from a declared URL;
        # still refused defensively before it reaches DDL).
        raise GuardRefused(
            f"GUARD_REFUSED_RUN_ROLE: run user {run_user!r} is not a plain "
            "identifier; refusing DDL ownership alignment."
        )
    url = migration_url
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(url)
    try:
        async with engine.begin() as conn:
            exists = (
                await conn.execute(
                    text(
                        "SELECT 1 FROM pg_proc p JOIN pg_namespace n "
                        "ON n.oid = p.pronamespace WHERE n.nspname = 'public' "
                        "AND p.proname = 'prevent_ledger_modification'"
                    )
                )
            ).scalar_one_or_none()
            if exists:
                await conn.execute(
                    text(f'ALTER FUNCTION public.prevent_ledger_modification() OWNER TO "{run_user}"')
                )
    finally:
        await engine.dispose()


async def _r0_task_database_stages():
    """Session fixture: prove ownership + role contract, migrate, verify
    readiness; no business writes before every stage passes.

    Stage order (each failure keeps ALL database-dependent tests out of their
    bodies and is reported as a sanitized GuardRefused category):
    1. verify_task_database_ownership_sync — declarations, container binding,
       migration/run same-target binding, run != bootstrap, engine binding;
    2. verify_migration_identity_live — migration URL really is the declared
       bootstrap identity on the declared database;
    3. verify_run_identity_live — run connection really is the declared
       non-privileged, membership-free test-session role;
    4. run_public_migrations — real 001..037 via the migration subprocess;
    4b. align_fixture_object_ownership — migration identity transfers the
        bootstrap-replaced public function to the run role (idempotent);
    5. head verification via the RUN connection;
    6. verify_run_privileges_post_migration — the run role really holds every
       privilege the fixtures consume.
    """
    db_url = verify_task_database_ownership_sync()
    migration_url = os.environ[MIGRATION_URL_ENV_VAR].strip()
    await verify_migration_identity_live(migration_url)
    await verify_run_identity_live(db_url)
    run_public_migrations(migration_url)
    await align_fixture_object_ownership(migration_url)
    try:
        async with AsyncSessionLocal() as probe:
            head = (
                await probe.execute(text("SELECT version_num FROM public.alembic_version"))
            ).scalar_one()
        if head != BASELINE_MIGRATION_HEAD:
            raise GuardRefused(
                f"GUARD_REFUSED_MIGRATION: task database head is {head!r}, expected "
                f"{BASELINE_MIGRATION_HEAD!r} (baseline mismatch)."
            )
        await verify_run_privileges_post_migration(db_url)
    except GuardRefused:
        raise
    except Exception as exc:
        # A run role that cannot even read alembic_version / probe its own
        # privileges is under-provisioned: refuse with a named category
        # instead of leaking a raw driver error, and keep every business
        # test out of its body.
        raise GuardRefused(
            "GUARD_REFUSED_RUN_ROLE_PRIVILEGES: the run connection could not "
            "complete post-migration readiness (head verification / privilege "
            "probes) — likely missing object privileges; refusing before any "
            f"business write. Driver category: {type(exc).__name__}."
        ) from exc
    yield db_url


# Registered session fixture: the SAME stage function pytest drives (nodeids
# and behavior unchanged; the bare name stays directly drivable for the
# ordering counterexample).
r0_task_database = pytest.fixture(scope="session")(_r0_task_database_stages)


# ---------------------------------------------------------------------------
# JWT strategy proof
# ---------------------------------------------------------------------------

def require_jwt_auth_strategy() -> None:
    """Prove the HTTP tests run the real JwtAuthStrategy, not a Mock variant.

    Normalizes MPANGO_ENV exactly like auth.factory (strip().lower()) and then
    inspects the strategy instance actually bound to the app's
    AuthenticationMiddleware.
    """
    env_raw = os.environ.get("MPANGO_ENV", "")
    # auth.factory: os.getenv("MPANGO_ENV", "production").strip().lower()
    if env_raw.strip().lower() == "test":
        pytest.fail(
            f"GUARD_REFUSED_MOCK_AUTH: MPANGO_ENV={env_raw!r} normalizes to "
            "'test' and selects MockAuthStrategy. Run with MPANGO_ENV=staging "
            "so the real JwtAuthStrategy is exercised."
        )
    from api.middleware.auth import AuthenticationMiddleware
    from auth.strategies.mock import MockAuthStrategy
    from main import app

    bound = None
    for middleware in getattr(app, "user_middleware", []):
        if middleware.cls is AuthenticationMiddleware:
            bound = (middleware.kwargs or {}).get("strategy")
            break
    if bound is None:
        pytest.fail(
            "GUARD_REFUSED_MOCK_AUTH: could not locate the strategy instance "
            "bound to AuthenticationMiddleware on the app under test."
        )
    strategy_type = type(bound)
    if isinstance(bound, MockAuthStrategy) or strategy_type.__name__ != "JwtAuthStrategy":
        pytest.fail(
            f"GUARD_REFUSED_MOCK_AUTH: app middleware strategy is "
            f"{strategy_type.__module__}.{strategy_type.__name__}, expected "
            "JwtAuthStrategy. HTTP evidence would not represent real auth."
        )


# ---------------------------------------------------------------------------
# Supervised background execution and cleanup
# ---------------------------------------------------------------------------

async def supervise(awaitable, *, timeout: float = SUPERVISE_TIMEOUT_S, label: str):
    """Run `awaitable` as a task; on timeout cancel it, await its end, fail.

    Ensures no test leaves a running task (holding a session/transaction)
    behind, so teardown never races live work. Expected test-level errors
    (e.g. HTTPException) propagate to the caller for explicit classification.
    """
    task = asyncio.ensure_future(awaitable)
    try:
        return await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
    except asyncio.TimeoutError:
        await cancel_and_wait(task)
        raise AssertionError(
            f"GUARD_HARNESS_TIMEOUT: {label} did not finish within {timeout}s; "
            "the task was cancelled and awaited. The barrier/deadlock is a "
            "harness fault — do not ignore."
        )
    except BaseException:
        await cancel_and_wait(task)
        raise


async def cancel_and_wait(task) -> None:
    """Cancel a task and wait until it fully finishes (best-effort)."""
    if task is None or task.done():
        return
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


# ---------------------------------------------------------------------------
# Tenant fixtures
# ---------------------------------------------------------------------------

class R0Token:
    """Minimal TokenPayload stand-in for direct route-function calls.

    Direct route calls do not resolve Depends(), so no signature check runs
    here (documented limitation, same as external review probes). HTTP tests
    use real signed tokens via core.security.create_contextual_token and the
    real middleware stack.
    """

    def __init__(self, *, tenant_id: uuid.UUID, tenant_schema: str, user_id: uuid.UUID):
        self.tenant_id = str(tenant_id)
        self.tenant_schema = tenant_schema
        self.user_id = str(user_id)
        self.roles = ["invariants_r0_admin"]


async def bootstrap_tenant(schema: str) -> None:
    """Create a full tenant schema via the product's own provisioning DDL."""
    from scripts.bootstrap_tenant_schema import bootstrap

    await bootstrap(schema, os.environ["DATABASE_URL"])


@asynccontextmanager
async def tenant_session(schema: str, tenant_id: uuid.UUID | None = None):
    """Open a tenant-scoped session the same way route dependencies do."""
    async with AsyncSessionLocal() as db:
        db.info["tenant_schema"] = schema
        if tenant_id is not None:
            db.info["tenant_id"] = str(tenant_id)
        await db.execute(text(f'SET search_path TO "{schema}", public'))
        try:
            yield db
            await db.commit()
        except BaseException:
            await db.rollback()
            raise


async def seed_public_tenant_rows(
    *,
    wholesaler_id: uuid.UUID,
    retailer_id: uuid.UUID,
    status: str = "active",
    outstanding: Decimal = Decimal("0.00"),
) -> None:
    """Insert public.wholesalers / retailers / binding rows for one tenant."""
    suffix = uuid.uuid4().hex[:10]
    async with AsyncSessionLocal() as db:
        await db.execute(
            text(
                "INSERT INTO public.wholesalers (id, code, name, status, is_deleted) "
                "VALUES (:wid, :code, :name, :status, FALSE) "
                "ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status, is_deleted = FALSE"
            ),
            {
                "wid": wholesaler_id,
                "code": f"R0{suffix}",
                "name": "Invariants R0 synthetic tenant",
                "status": status,
            },
        )
        await db.execute(
            text(
                "INSERT INTO public.retailers (id, phone, name, is_deleted) "
                "VALUES (:rid, :phone, :name, FALSE) "
                "ON CONFLICT (id) DO UPDATE SET is_deleted = FALSE"
            ),
            {"rid": retailer_id, "phone": f"+254700{suffix}", "name": "Invariants R0 retailer"},
        )
        await db.execute(
            text(
                "INSERT INTO public.wholesaler_retailer_bindings "
                "(wholesaler_id, retailer_id, status, outstanding_balance, is_deleted) "
                "VALUES (:wid, :rid, 'active', :outstanding, FALSE) "
                "ON CONFLICT (wholesaler_id, retailer_id) DO UPDATE "
                "SET status = 'active', outstanding_balance = :outstanding, is_deleted = FALSE"
            ),
            {"wid": wholesaler_id, "rid": retailer_id, "outstanding": outstanding},
        )
        await db.commit()


async def drop_tenant(schema: str, *, wholesaler_id: uuid.UUID, retailer_id: uuid.UUID) -> None:
    """Best-effort teardown of one synthetic tenant (schema + public rows).

    Callers MUST have cancelled/joined all background tasks and closed their
    sessions first (supervise/cancel_and_wait guarantee this) so no live
    transaction can re-create rows after the drop.
    """
    async with AsyncSessionLocal() as db:
        await db.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await db.execute(
            text("DELETE FROM public.wholesaler_retailer_bindings WHERE wholesaler_id = :w"),
            {"w": wholesaler_id},
        )
        await db.execute(text("DELETE FROM public.retailers WHERE id = :r"), {"r": retailer_id})
        await db.execute(text("DELETE FROM public.wholesalers WHERE id = :w"), {"w": wholesaler_id})
        await db.commit()


class TenantIdentity:
    """A tenant identity registered for cleanup BEFORE any creation happens."""

    def __init__(self):
        self.wholesaler_id = uuid.uuid4()
        self.retailer_id = uuid.uuid4()
        self.schema = "t_" + self.wholesaler_id.hex
        self.created = False

    async def create(self) -> "TenantIdentity":
        try:
            await bootstrap_tenant(self.schema)
            await seed_public_tenant_rows(
                wholesaler_id=self.wholesaler_id, retailer_id=self.retailer_id
            )
        except BaseException:
            # Partial bootstrap must not leak: the schema may exist with a
            # subset of tables; public rows may exist. Drop what was created.
            await self.drop()
            raise
        self.created = True
        return self

    async def drop(self) -> None:
        await drop_tenant(
            self.schema, wholesaler_id=self.wholesaler_id, retailer_id=self.retailer_id
        )


# ---------------------------------------------------------------------------
# Seeding / snapshot helpers
# ---------------------------------------------------------------------------

async def seed_sku_with_stock(
    db,
    *,
    sku_code: str,
    quantity_on_hand: Decimal,
    price: Decimal | None = None,
    retailer_id: uuid.UUID | None = None,
    name: str = "Invariants R0 item",
) -> uuid.UUID:
    """Seed one tenant SKU + stock row (+ optional retailer price) via ORM/SQL.

    `name` lets a caller attach a tenant-distinctive marker to an otherwise
    identical record (R1-R1 F1: two tenants hold the SAME sku_code and the
    isolation assertion distinguishes records by id + name).
    """
    from models import SKU
    from models.inventory_stock import InventoryStock

    sku = SKU(sku_code=sku_code, name=name, unit="box", is_active=True)
    db.add(sku)
    await db.flush()
    db.add(
        InventoryStock(
            sku_id=sku.id,
            quantity_on_hand=quantity_on_hand,
            quantity_reserved=Decimal("0.00"),
        )
    )
    if price is not None and retailer_id is not None:
        await db.execute(
            text(
                "INSERT INTO retailer_prices (retailer_id, sku_id, price, is_deleted) "
                "VALUES (:rid, :sid, :price, FALSE)"
            ),
            {"rid": retailer_id, "sid": sku.id, "price": price},
        )
    await db.flush()
    return sku.id


async def stock_on_hand(db, *, sku_code: str) -> Decimal:
    row = (
        await db.execute(
            text(
                "SELECT s.quantity_on_hand FROM inventory_stocks s "
                "JOIN skus k ON k.id = s.sku_id WHERE k.sku_code = :code"
            ),
            {"code": sku_code},
        )
    ).scalar()
    return Decimal(str(row))


async def adjustment_movements(db, *, sku_code: str) -> list[dict]:
    """Raw adjustment movement rows for one SKU (list, never reason-keyed).

    R2 (CTO F2): the rows are returned UNMODIFIED — no dict-by-reason
    construction that would silently collapse duplicate journal rows. Row
    count and per-reason multiplicity are part of the invariant and are
    checked by assert_adjustment_chain, which both the real concurrency test
    and the guard controls call (single shared implementation).
    """
    rows = (
        await db.execute(
            text(
                "SELECT m.quantity::text AS qty, m.quantity_before::text AS q_before, "
                "m.quantity_after::text AS q_after, m.reason, m.id "
                "FROM inventory_movements m JOIN skus k ON k.id = m.sku_id "
                "WHERE k.sku_code = :code AND m.movement_type = 'adjustment' "
                "ORDER BY m.id"
            ),
            {"code": sku_code},
        )
    ).mappings().all()
    return [dict(r) for r in rows]


def assert_adjustment_chain(
    movements: list[dict],
    *,
    initial: Decimal,
    final_observed: Decimal,
    expected: list[tuple[str, Decimal]],
) -> None:
    """Shared inventory-adjustment invariant (CTO F2): single implementation.

    Verifies the journal against the observed final stock WITHOUT inferring
    execution order from timestamps, and WITHOUT collapsing duplicate rows:

    1. raw row count equals the number of expected adjustments (duplicate or
       missing rows rejected);
    2. every expected reason appears exactly once, no unknown reasons
       (duplicate-reason rows rejected);
    3. every row satisfies before + delta == after;
    4. the delta multiset matches;
    5. chain linkage, order-free: exactly one row starts from `initial`; its
       `after` equals `initial + delta` and must equal the other row's
       `before`; the other row ends exactly at `final_observed`. This accepts
       both legal serial orders (A then B: 10→15, 15→22; B then A: 10→17,
       17→22) and rejects the lost-update journal (two rows starting from
       10, neither ending at the observed final);
    6. initial + total raw delta == final_observed.

    Called by the real concurrent-adjustment test (rows from the database)
    and by the guard controls (synthetic rows) so both exercise the exact
    same acceptance/rejection logic.
    """
    from collections import Counter

    expected_reasons = [reason for reason, _ in expected]
    expected_deltas = sorted(delta for _, delta in expected)

    assert len(movements) == len(expected), (
        "INVARIANT_R0_STOCK_MOVEMENT_SET: expected exactly "
        f"{len(expected)} adjustment movements, got {len(movements)} raw rows "
        f"({[str(r.get('reason')) for r in movements]}). Duplicate or missing "
        "journal rows must be rejected, not deduplicated away."
    )
    reason_counts = Counter(str(row.get("reason")) for row in movements)
    assert reason_counts == Counter(expected_reasons), (
        "INVARIANT_R0_STOCK_MOVEMENT_SET: adjustment reasons must each appear "
        f"exactly once {expected_reasons!r}, got {dict(reason_counts)!r}. "
        "Duplicate journal rows for one adjustment identity are a double "
        "economic effect and must be rejected."
    )

    for reason, delta in expected:
        row = next(r for r in movements if str(r.get("reason")) == reason)
        qty, before, after = (
            Decimal(row["qty"]),
            Decimal(row["q_before"]),
            Decimal(row["q_after"]),
        )
        assert qty == delta, (
            f"INVARIANT_R0_STOCK_MOVEMENT_ALGEBRA: {reason!r} journaled delta "
            f"{qty}, expected {delta}."
        )
        assert before + qty == after, (
            f"INVARIANT_R0_STOCK_MOVEMENT_ALGEBRA: {reason!r} row violates "
            f"before+delta=after ({before} + {qty} != {after})."
        )

    deltas = sorted(Decimal(row["qty"]) for row in movements)
    assert deltas == expected_deltas, (
        "INVARIANT_R0_STOCK_MOVEMENT_ALGEBRA: journal delta multiset must be "
        f"{expected_deltas}, got {deltas}."
    )

    starters = [row for row in movements if Decimal(row["q_before"]) == initial]
    assert len(starters) == 1, (
        "INVARIANT_R0_STOCK_MOVEMENT_ALGEBRA: exactly one adjustment may "
        f"compute from the initial value {initial}, got {len(starters)} rows "
        f"starting there ({[str(r['q_before']) for r in movements]}). Two "
        "rows starting from the stale initial value is the lost-update shape."
    )
    first = starters[0]
    second = next(row for row in movements if row is not first)
    assert Decimal(first["q_after"]) == initial + Decimal(first["qty"]), (
        "INVARIANT_R0_STOCK_MOVEMENT_ALGEBRA: the initial-value row must end "
        f"at initial+delta ({initial} + {first['qty']}), got {first['q_after']}."
    )
    assert Decimal(second["q_before"]) == Decimal(first["q_after"]), (
        "INVARIANT_R0_STOCK_MOVEMENT_ALGEBRA: the second adjustment must "
        f"compute from the first row's committed result {first['q_after']}, "
        f"got {second['q_before']}."
    )
    assert Decimal(second["q_after"]) == final_observed, (
        "INVARIANT_R0_STOCK_MOVEMENT_ALGEBRA: the last committed row must end "
        f"at the observed final stock {final_observed}, got "
        f"{second['q_after']}. Journal and current value contradict each "
        "other."
    )
    assert initial + sum(deltas) == final_observed, (
        "INVARIANT_R0_STOCK_MOVEMENT_ALGEBRA: initial + total journal delta "
        f"({initial} + {sum(deltas)}) must equal the observed final stock "
        f"{final_observed}."
    )
