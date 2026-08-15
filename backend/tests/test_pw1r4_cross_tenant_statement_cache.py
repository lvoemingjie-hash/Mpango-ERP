"""PW1-R4-A — Cross-tenant prepared-statement runtime closure.

Root cause (reproduced empirically on real PG16, pool_size=1):
the SQLAlchemy asyncpg dialect keeps a per-pool LRU of server prepared
statements keyed ONLY by SQL text. Tenant routing is per-transaction
``SET LOCAL search_path`` on a SHARED pool, so when any tenant's
provisioning/migration DDL invalidates the relations a pooled statement was
planned against, the next request reusing that statement raises
``asyncpg.exceptions.InvalidCachedStatementError`` (surfaced as 500).

Closure: ``prepared_statement_cache_size=0`` on the production engine
(``database/session.py``) — the MINIMAL setting that closes the real RED.
Empirically (pw1r4a-evidence/probe_fix_candidates.py):
  - prepared_statement_cache_size=0  -> RED closed
  - statement_cache_size=0 (asyncpg) -> BufferError (invalid; not used)
  - both                             -> RED closed (no better than #1)
  - control (defaults)               -> RED alive (InvalidCachedStatementError)

This suite proves, with REAL artifacts:
  1. HTTP-level GREEN — real contextual routes through configure_app +
     JwtAuthStrategy on the PRODUCTION AsyncSessionLocal, A->B->A and B->A
     cycles with an interleaved DDL storm on tenant A's table: every request
     succeeds and returns the CORRECT tenant's data (no error, no leak).
  2. Engine-level GREEN — get_tenant_db cycles on the production engine.
  3. Causal RED — a LEGACY engine (production config minus the fix,
     pool_size=1) reproduces InvalidCachedStatementError on the same cycle.
     This is the sensitivity/mutation proof: if the fix were removed from
     the production engine, the HTTP legs would fail the same way.
  4. No-leak — each tenant always observes its own rows across all cycles.

Formal bootstrap: both tenant schemas are created with the product's own
``scripts.bootstrap_tenant_schema.bootstrap`` (the same module
TenantProvisioningService loads). The per-tenant user rows are synthetic
direct inserts (sufficient and exact for resolve_tenant_context's lookup);
no formal owner lifecycle is claimed for them.

Forbidden techniques NOT used: no route retries, no swallowed exceptions
re-packed as 200, no per-request engine disposal, no per-tenant engines.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import uuid
from unittest import mock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

from core.config import get_settings
from core.security import create_contextual_token, hash_password
from database.session import AsyncSessionLocal, async_engine, get_tenant_db

pytestmark = pytest.mark.asyncio

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


def _async_db_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL", "")
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql+asyncpg://"):
        return url
    raise RuntimeError("TEST_DATABASE_URL/DATABASE_URL must be a PostgreSQL URL")


def _load_formal_bootstrap():
    """Load scripts.bootstrap_tenant_schema.bootstrap (formal tenant DDL)."""
    spec = importlib.util.spec_from_file_location(
        "pw1r4_bootstrap", os.path.join(BACKEND_DIR, "scripts", "bootstrap_tenant_schema.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.bootstrap


@pytest_asyncio.fixture(scope="module")
async def two_tenants():
    """Two tenant schemas via the FORMAL bootstrap + synthetic active users."""
    bootstrap = _load_formal_bootstrap()
    url = _async_db_url()
    suffix = uuid.uuid4().hex[:8]
    a = f"t_r4a_a_{suffix}"
    b = f"t_r4a_b_{suffix}"

    await bootstrap(a, url)
    await bootstrap(b, url)

    user_a, user_b = str(uuid.uuid4()), str(uuid.uuid4())
    async with AsyncSessionLocal() as s:
        for sch, uid in ((a, user_a), (b, user_b)):
            await s.execute(text(f'SET LOCAL search_path TO "{sch}", public'))
            await s.execute(
                text(
                    f'INSERT INTO "{sch}".users (id, email, password_hash, full_name, is_active) '
                    "VALUES (:id, :email, :pw, :name, true)"
                ),
                {"id": uid, "email": f"r4a-{sch[-6:]}@test.dev",
                 "pw": hash_password("pw1r4a-not-a-real-credential"), "name": "PW1-R4-A"},
            )
        await s.commit()

    yield {"a": {"schema": a, "tenant_id": str(uuid.uuid4()), "user_id": user_a},
           "b": {"schema": b, "tenant_id": str(uuid.uuid4()), "user_id": user_b}}

    async with AsyncSessionLocal() as s:
        for sch in (a, b):
            await s.execute(text(f'DROP SCHEMA IF EXISTS "{sch}" CASCADE'))
        await s.commit()
    await async_engine.dispose()


@pytest_asyncio.fixture
async def ddl_engine():
    """Dedicated connection for the DDL storm (provisioning-shaped, separate
    from the shared pool so invalidation arrives from OUTSIDE the pool)."""
    engine = create_async_engine(_async_db_url(), pool_size=1)
    yield engine
    await engine.dispose()


def build_app() -> FastAPI:
    """Real middleware/app wiring with the production JwtAuthStrategy."""
    from api.app import configure_app
    from auth.strategies.jwt import JwtAuthStrategy
    from core.error_codes import register_exception_handlers

    app = FastAPI()
    with mock.patch("auth.factory.get_auth_strategy", return_value=JwtAuthStrategy()):
        configure_app(app, get_settings())
    register_exception_handlers(app)
    return app


def token_for(tenant: dict) -> str:
    return create_contextual_token(
        user_id=tenant["user_id"],
        roles=["admin"],
        tenant_id=tenant["tenant_id"],
        tenant_schema=tenant["schema"],
        token_type="access",
    )


async def _ddl_storm(engine, schema: str) -> None:
    """Provisioning-shaped DDL: ALTER COLUMN TYPE to the OPPOSITE type
    (text <-> varchar) so every storm is a genuine type-OID change and the
    prepared-statement invalidation actually fires. A repeated same-type
    ALTER would be a typmod no-op and would NOT invalidate anything
    (verified empirically: typmod-only changes never reproduce the RED)."""
    async with engine.connect() as c:
        current = (
            await c.execute(
                text(
                    "SELECT data_type FROM information_schema.columns "
                    "WHERE table_schema = :s AND table_name = 'users' "
                    "AND column_name = 'full_name'"
                ),
                {"s": schema},
            )
        ).scalar()
        target = "varchar(500)" if current == "text" else "text"
        await c.execute(
            text(
                f'ALTER TABLE "{schema}".users '
                f"ALTER COLUMN full_name TYPE {target} "
                f"USING full_name::{target}"
            )
        )
        await c.commit()


# ---------------------------------------------------------------------------
# 1. HTTP-level GREEN: real contextual routes, A->B->A and B->A cycles
# ---------------------------------------------------------------------------
async def test_http_abab_cycles_survive_ddl_storm(two_tenants, ddl_engine):
    app = build_app()
    ta = token_for(two_tenants["a"])
    tb = token_for(two_tenants["b"])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        async def me(token):
            r = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
            assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:200]}"
            data = r.json()["data"]
            return data["tenant_id"]

        # A -> B -> A cycle
        assert await me(ta) == two_tenants["a"]["tenant_id"]
        assert await me(tb) == two_tenants["b"]["tenant_id"]
        # DDL storm on tenant A's table between cycles (tenant-B provisioning shape)
        await _ddl_storm(ddl_engine, two_tenants["a"]["schema"])
        assert await me(ta) == two_tenants["a"]["tenant_id"]

        # B -> A cycle after the storm
        assert await me(tb) == two_tenants["b"]["tenant_id"]
        assert await me(ta) == two_tenants["a"]["tenant_id"]


# ---------------------------------------------------------------------------
# 2. Engine-level GREEN: production AsyncSessionLocal via get_tenant_db
# ---------------------------------------------------------------------------
async def test_engine_aba_cycles_survive_ddl_storm(two_tenants, ddl_engine):
    a, b = two_tenants["a"], two_tenants["b"]

    async def user_full_name(t):
        # SELECT the storm-altered column (full_name) so this leg depends on
        # exactly the relation the DDL invalidates — an untouched-column
        # SELECT would be a false-green under the fix-removed mutation.
        out = None
        async for session in get_tenant_db(t["schema"]):
            result = await session.execute(
                text('SELECT full_name FROM users WHERE id = :i'), {"i": t["user_id"]}
            )
            out = result.scalar()
        return out

    email_a = await user_full_name(a)
    email_b = await user_full_name(b)
    await _ddl_storm(ddl_engine, a["schema"])
    # A after its own DDL storm, then B -> A
    assert await user_full_name(a) == email_a
    assert await user_full_name(b) == email_b
    assert await user_full_name(a) == email_a


# ---------------------------------------------------------------------------
# 3. Causal RED: legacy engine (production config minus the fix)
# ---------------------------------------------------------------------------
async def test_legacy_engine_without_fix_reproduces_invalid_cached_statement(two_tenants, ddl_engine):
    a = two_tenants["a"]
    legacy = create_async_engine(
        _async_db_url(),
        pool_pre_ping=True,
        pool_size=1,
        max_overflow=0,
        connect_args={
            # production config MINUS prepared_statement_cache_size=0
            "server_settings": {"application_name": "pw1r4a_legacy_red", "jit": "off"},
        },
    )
    try:
        # The plan must REFERENCE the column the DDL storm alters (full_name):
        # PostgreSQL invalidates prepared plans by dependency, so selecting an
        # untouched column would NOT reproduce the failure (verified empirically).
        sql = 'SELECT full_name FROM users WHERE id = :i'

        async def run():
            out = None
            async with AsyncSession(legacy) as s:
                s.info["tenant_schema"] = a["schema"]
                await s.execute(text(f'SET LOCAL search_path TO "{a["schema"]}", public'))
                result = await s.execute(text(sql), {"i": a["user_id"]})
                out = result.scalar()
                await s.commit()
            return out

        assert await run() is not None          # plan cached on the pooled conn
        await _ddl_storm(ddl_engine, a["schema"])  # DDL invalidates the plan
        with pytest.raises(Exception) as exc_info:
            await run()                          # must raise — same cycle shape

        chain: list[str] = []
        cur: BaseException | None = exc_info.value
        seen: set[int] = set()
        while cur is not None and id(cur) not in seen:
            seen.add(id(cur))
            chain.append(f"{type(cur).__module__}.{type(cur).__name__}")
            cur = cur.__cause__ or cur.__context__
        assert any("InvalidCachedStatement" in c for c in chain), (
            f"expected InvalidCachedStatementError in chain, got: {' -> '.join(chain)}"
        )
    finally:
        await legacy.dispose()


# ---------------------------------------------------------------------------
# 4. No-leak guard: correct tenant data across cycles
# ---------------------------------------------------------------------------
async def test_no_cross_tenant_leak_across_cycles(two_tenants, ddl_engine):
    a, b = two_tenants["a"], two_tenants["b"]

    async def who(t):
        out = None
        async for session in get_tenant_db(t["schema"]):
            result = await session.execute(
                text('SELECT id FROM users LIMIT 1'))
            out = str(result.scalar())
        return out

    for _ in range(2):  # repeated A/B alternation on the shared pool
        assert await who(a) == a["user_id"]
        assert await who(b) == b["user_id"]
    await _ddl_storm(ddl_engine, a["schema"])
    assert await who(a) == a["user_id"]
    assert await who(b) == b["user_id"]
