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
import json
import os
import subprocess
import sys
import uuid
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse

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


def verify_task_redis_ownership_sync() -> str:
    """Pre-deletion ownership proof for the task Redis (CTO R1-R2 remediation).

    Any cache-key deletion must happen ONLY on a provably task-owned Redis.
    Returns the verified ``host:port`` of the declared instance. Refuses
    BEFORE any deletion when:

    1. MPANGO_INVARIANTS_R0_REDIS_CONTAINER / owner label / REDIS_URL missing;
    2. REDIS_URL host is not loopback;
    3. owner label outside the ``zcode-mvp-invariants`` namespace;
    4. docker inspect: label mismatch, image not ``redis:*``, or the 6379
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
    parsed = urlparse(redis_url)
    host = parsed.hostname
    port = parsed.port or 6379
    if host not in LOOPBACK_HOSTS:
        raise GuardRefused(
            f"GUARD_REFUSED_REDIS_OWNERSHIP: REDIS_URL host {host!r} is not loopback."
        )
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
    if mapped.get("127.0.0.1") != str(port):
        raise GuardRefused(
            "GUARD_REFUSED_REDIS_OWNERSHIP: container 6379 mapping "
            f"{mapped} does not match REDIS_URL host/port (127.0.0.1:{port})."
        )
    return f"{host}:{port}"


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


def verify_task_database_ownership_sync() -> str:
    """Pre-write ownership proof (sync part). Returns the verified DB URL.

    Refuses (before any write) when: config missing, TEST_DATABASE_URL and
    DATABASE_URL disagree, the container is not the declared labeled task
    container, image/port/db/user do not match the URL, or the live engine is
    bound to a different target.
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
            "DATABASE_URL name different targets; migration, bootstrap and "
            "pytest must all use one explicit target."
        )

    parsed = urlparse(test_url.replace("postgresql+asyncpg://", "postgresql://", 1))
    host = parsed.hostname
    port = parsed.port or 5432
    dbname = (parsed.path or "").lstrip("/")
    if host not in LOOPBACK_HOSTS:
        raise GuardRefused(
            f"GUARD_REFUSED_DATABASE_OWNERSHIP: URL host '{host}' is not loopback."
        )
    if not dbname:
        raise GuardRefused("GUARD_REFUSED_DATABASE_OWNERSHIP: URL has no database name.")

    if not owner_label.startswith(OWNER_LABEL_PREFIX):
        raise GuardRefused(
            "GUARD_REFUSED_DATABASE_OWNERSHIP: owner label must be a "
            f"{OWNER_LABEL_PREFIX}-* task label, got {owner_label!r}."
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
    if env_pairs.get("POSTGRES_USER") != (parsed.username or ""):
        raise GuardRefused(
            "GUARD_REFUSED_DATABASE_OWNERSHIP: container POSTGRES_USER does "
            "not match URL user."
        )

    engine_url = async_engine.url
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
    return test_url


async def verify_task_database_live(db_url: str) -> None:
    """Live probe inside the declared database.

    Port identity is established by the docker port-mapping + engine-URL
    checks in verify_task_database_ownership_sync (the only wire path from
    the declared host port leads to the declared container); inside the
    database we verify the database name and the server major version so a
    stale or foreign cluster behind the same port cannot pass silently.
    """
    parsed = urlparse(db_url.replace("postgresql+asyncpg://", "postgresql://", 1))
    dbname = (parsed.path or "").lstrip("/")
    async with AsyncSessionLocal() as probe:
        row = (
            await probe.execute(text("SELECT current_database(), version()"))
        ).one()
        if row[0] != dbname:
            raise GuardRefused(
                "GUARD_REFUSED_DATABASE_OWNERSHIP: live connection landed on "
                f"db={row[0]!r}, expected {dbname!r}."
            )
        if not str(row[1]).startswith("PostgreSQL 16."):
            raise GuardRefused(
                "GUARD_REFUSED_DATABASE_OWNERSHIP: server is "
                f"{str(row[1]).split(',')[0]!r}, expected a PostgreSQL 16 "
                "cluster matching the declared postgres:16 task container."
            )


def run_public_migrations() -> None:
    """Upgrade the verified task database to the baseline migration head.

    The URL comes exclusively from the ownership-verified DATABASE_URL env —
    the alembic.ini default address is never used (env.py overrides from the
    environment, and the guard refuses to run without it).
    """
    backend_dir = Path(__file__).resolve().parents[1]
    reporting_password = os.environ.get("REPORTING_USER_PASSWORD", "").strip()
    if not reporting_password:
        raise GuardRefused(
            "GUARD_REFUSED_MIGRATION: REPORTING_USER_PASSWORD must be set for "
            "migration 011; refusing to run migrations with incomplete config."
        )
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(backend_dir),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
        env={**os.environ, "DATABASE_URL": os.environ["DATABASE_URL"]},
    )
    if result.returncode != 0:
        raise GuardRefused(
            "GUARD_REFUSED_MIGRATION: alembic upgrade head failed against the "
            f"declared task target:\n{result.stdout}\n{result.stderr}"
        )


@pytest.fixture(scope="session")
async def r0_task_database():
    """Session fixture: prove ownership, probe, migrate; no writes before all three."""
    db_url = verify_task_database_ownership_sync()
    await verify_task_database_live(db_url)
    run_public_migrations()
    async with AsyncSessionLocal() as probe:
        head = (
            await probe.execute(text("SELECT version_num FROM public.alembic_version"))
        ).scalar_one()
    if head != BASELINE_MIGRATION_HEAD:
        raise GuardRefused(
            f"GUARD_REFUSED_MIGRATION: task database head is {head!r}, expected "
            f"{BASELINE_MIGRATION_HEAD!r} (baseline mismatch)."
        )
    yield db_url


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
