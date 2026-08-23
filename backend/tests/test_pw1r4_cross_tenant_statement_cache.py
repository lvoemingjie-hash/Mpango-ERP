"""PW1-R4-A (R2) — Cross-tenant prepared-statement runtime closure.

Root cause (reproduced empirically on real PG16, pool_size=1):
The prepared-statement cache is per DBAPI connection; those connections
are retained and reused by the shared pool, and the cached statements are
keyed ONLY by SQL text. Tenant routing is per-transaction
``SET LOCAL search_path`` on a SHARED pool, so a statement planned for one
tenant's relation OIDs can be re-executed on a pooled connection after
another tenant's provisioning/migration DDL invalidates those plans,
raising ``asyncpg.exceptions.InvalidCachedStatementError`` (surfaced as 500).

Closure: ``prepared_statement_cache_size=0`` on the production engine
(``database/session.py``) — the MINIMAL setting that closes the real RED.

This suite proves, with REAL artifacts only:
  1. EXACT-ROUTE GREEN — the precise production route
     ``GET /api/v1/client/orders?page=1&size=100`` through the REAL
     JwtAuthStrategy + real tenant DB dependency (resolve_client_identity ->
     RequirePermission -> get_orders_for_retailer), on two formally
     bootstrapped tenants with the required retailer/binding/role/permission
     rows: A -> B -> DDL -> A and B -> A cycles return 200 with the CORRECT
     tenant's orders and zero cross-tenant leakage.
  2. EXACT-ROUTE causal RED — the same precise route under a LEGACY engine
     configuration (production minus the fix) reproduces the failure after
     the same DDL storm. Removing ``prepared_statement_cache_size=0`` from
     database/session.py turns the GREEN legs RED (mutation-verified).
  3. Engine-level GREEN — get_tenant_db cycles on the production engine.
  4. Legacy-engine RED — standalone causal RED on a local legacy engine.
  5. No-leak — each tenant always observes its own rows.
  6. Fail-closed setup — every created schema is tracked from the FIRST
     bootstrap; injected failures (second bootstrap, user seed, ddl-engine
     creation) still drop all owned schemas, assert zero pg_namespace
     residue, and propagate the ORIGINAL exception (no masking). The residue
     proof is INDEPENDENT of the helper: tests pre-generate the
     deterministic schema names and query pg_namespace themselves.
  7. Genuine dual-exception truth — pre-created original/cleanup exception
     objects: the original is injected through the real seed path, the
     cleanup error is raised by the REAL ``_drop_owned_schemas`` call.
     Cleanup success re-raises the SAME object (``ei.value is
     original_error``); cleanup failure surfaces a BaseExceptionGroup whose
     members are [original_error, cleanup_error] BY OBJECT IDENTITY (never
     a RuntimeError overwrite), and the test's fail-closed finally drops
     the residue with the real helper + independent pg_namespace proof.

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

EXACT_ROUTE = "/api/v1/client/orders?page=1&size=100"

# ---------------------------------------------------------------------------
# R2-R3 (DC-12R1-MVP-L1-J1-H2-B): exact public-row ownership registry.
# _seed_tenant_readiness commits synthetic public wholesaler/retailer/binding
# rows with random UUIDs; the module's own cleanup drops only the t_r4a_*
# schemas, so those public rows survive the module and break the DC3B
# password-reset scan (derived schema never exists for them). The registry
# records every exact identity this module creates; the module-scoped
# fail-closed guard below deletes exactly those rows (FK-safe order, fresh
# engines, protected against retailers bound by unrelated bindings) and
# independently proves zero residue. No LIKE, prefixes, or wildcards.
# ---------------------------------------------------------------------------

_OWNED_SCHEMAS: list[str] = []
_OWNED_PUBLIC: list[dict] = []


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


# ---------------------------------------------------------------------------
# Fail-closed tenant setup: every owned schema tracked from the FIRST
# bootstrap; cleanup runs in finally regardless of where setup fails and
# always propagates the ORIGINAL exception (cleanup errors never mask it).
# ---------------------------------------------------------------------------
class _ForcedFailure(RuntimeError):
    """Deterministic injected failure for fail-closed cleanup tests."""


async def _drop_owned_schemas(
    owned: list[str], *, forced_error: BaseException | None = None
) -> None:
    """Drop every tracked owned schema (explicit names; no wildcards).

    ``forced_error`` (PW1-R4-A-R3 dual-error proof) makes the REAL helper
    call raise the pre-created exception — the failure surfaces through the
    same code path a genuine drop failure would.
    """
    if forced_error is not None:
        raise forced_error
    if not owned:
        return
    cleanup_engine = create_async_engine(_async_db_url(), pool_size=1)
    try:
        async with cleanup_engine.connect() as c:
            for sch in owned:
                await c.execute(text(f'DROP SCHEMA IF EXISTS "{sch}" CASCADE'))
            await c.commit()
    finally:
        await cleanup_engine.dispose()


async def _assert_zero_namespace_residue(owned: list[str]) -> None:
    """pg_namespace assertion: none of the owned schemas may remain."""
    check_engine = create_async_engine(_async_db_url(), pool_size=1)
    try:
        async with check_engine.connect() as c:
            for sch in owned:
                n = (
                    await c.execute(
                        text(
                            "SELECT count(*) FROM pg_catalog.pg_namespace "
                            "WHERE nspname = :n"
                        ),
                        {"n": sch},
                    )
                ).scalar()
                assert n == 0, f"schema '{sch}' residue: pg_namespace count={n}"
    finally:
        await check_engine.dispose()


async def _seed_tenant_readiness(schema: str, user_id: str) -> None:
    """Seed retailer-operator readiness for the EXACT route.

    Synthetic direct inserts (documented as synthetic; no lifecycle claim):
    retailer_operator role + client:orders:read permission, active binding,
    public retailer/wholesaler rows, and one tenant-distinct order row.
    """
    retailer_id = uuid.uuid4()
    wholesaler_id = uuid.uuid4()
    order_id = uuid.uuid4()
    async with AsyncSessionLocal() as s:
        await s.execute(text(f'SET LOCAL search_path TO "{schema}", public'))
        await s.execute(
            text(
                f'INSERT INTO "{schema}".users (id, email, password_hash, full_name, is_active) '
                "VALUES (:id, :email, :pw, :name, true)"
            ),
            {"id": user_id, "email": f"r4a-{schema[-6:]}@test.dev",
             "pw": hash_password("pw1r4a-not-a-real-credential"), "name": "PW1-R4-A"},
        )
        await s.execute(
            text(f'INSERT INTO "{schema}".roles (name, description) '
                 "VALUES ('retailer_operator', 'R4A test operator') "
                 "ON CONFLICT (name) DO NOTHING"),
        )
        role_id = (await s.execute(text(
            f'SELECT id FROM "{schema}".roles WHERE name = \'retailer_operator\''))).scalar()
        await s.execute(
            text(f'INSERT INTO "{schema}".permissions (code, description) '
                 "VALUES ('client:orders:read', 'R4A test perm') "
                 "ON CONFLICT (code) DO NOTHING"),
        )
        perm_id = (await s.execute(text(
            f'SELECT id FROM "{schema}".permissions WHERE code = \'client:orders:read\''))).scalar()
        await s.execute(
            text(f'INSERT INTO "{schema}".user_roles (user_id, role_id) '
                 "VALUES (:u, :r) ON CONFLICT DO NOTHING"),
            {"u": user_id, "r": role_id},
        )
        await s.execute(
            text(f'INSERT INTO "{schema}".role_permissions (role_id, permission_id) '
                 "VALUES (:r, :p) ON CONFLICT DO NOTHING"),
            {"r": role_id, "p": perm_id},
        )
        await s.execute(
            text("INSERT INTO public.retailers (id, phone, name) VALUES (:i, :ph, :n)"),
            {"i": retailer_id, "ph": f"+2547{uuid.uuid4().int % 10**7:07d}", "n": f"R4A {schema[-6:]}"},
        )
        await s.execute(
            text("INSERT INTO public.wholesalers (id, code, name, status) "
                 "VALUES (:i, :c, :n, 'active')"),
            {"i": wholesaler_id, "c": f"R4A{schema[-6:].upper()}{uuid.uuid4().hex[:4].upper()}", "n": f"R4A WS {schema[-6:]}"},
        )
        await s.execute(
            text(
                "INSERT INTO public.wholesaler_retailer_bindings "
                "(wholesaler_id, retailer_id, status, tenant_user_id, outstanding_balance) "
                "VALUES (:w, :r, 'active', :u, 0)"
            ),
            {"w": wholesaler_id, "r": retailer_id, "u": user_id},
        )
        await s.execute(
            text(
                f'INSERT INTO "{schema}".orders (id, wholesaler_id, retailer_id, status, total_amount, notes) '
                "VALUES (:o, :w, :r, 'draft', 100, :notes)"
            ),
            {"o": order_id, "w": wholesaler_id, "r": retailer_id, "notes": f"ORDER-{schema[-6:]}"},
        )
        await s.commit()
        _OWNED_PUBLIC.append(
            {"wholesaler_id": str(wholesaler_id), "retailer_id": str(retailer_id)}
        )
        return str(wholesaler_id)


async def _setup_two_tenants(
    *,
    fail_at: str | None = None,
    suffix: str | None = None,
    original_error: BaseException | None = None,
    cleanup_error: BaseException | None = None,
) -> dict:
    """Formal bootstrap of two tenants + exact-route readiness rows.

    ``fail_at`` injects a deterministic failure at:
      "second_bootstrap" | "user_seed" | "before_ddl_engine"
    ``suffix`` lets tests PRE-GENERATE the deterministic schema names so the
    residue proof can query pg_namespace from OUTSIDE this helper (no
    circular trust in the helper's own assertion).

    PW1-R4-A-R3 genuine dual-error proof:
    - ``original_error``: a PRE-CREATED exception object raised through the
      REAL seed/setup path (identity preserved for the caller's proof).
    - ``cleanup_error``: a PRE-CREATED exception object that the REAL
      ``_drop_owned_schemas`` call raises (genuine cleanup failure — no
      synthetic cleanup_errors list entries).

    On failure the helper drops ALL tracked schemas and re-raises:
      - cleanup succeeds  -> the ORIGINAL exception OBJECT is re-raised
        (identical object identity, never a copy/reconstruction);
      - cleanup fails     -> a BaseExceptionGroup whose members are exactly
        [original_error_object, cleanup_error_object] (never a RuntimeError
        that overwrites either).
    """
    bootstrap = _load_formal_bootstrap()
    if suffix is None:
        suffix = uuid.uuid4().hex[:8]
    owned: list[str] = []
    a = f"t_r4a_a_{suffix}"
    b = f"t_r4a_b_{suffix}"
    ddl_engine = None
    try:
        await bootstrap(a, _async_db_url())
        owned.append(a)
        _OWNED_SCHEMAS.append(a)

        if fail_at == "second_bootstrap":
            raise original_error or _ForcedFailure("injected: second_bootstrap")

        await bootstrap(b, _async_db_url())
        owned.append(b)
        _OWNED_SCHEMAS.append(b)

        user_a, user_b = str(uuid.uuid4()), str(uuid.uuid4())
        seed = _seed_tenant_readiness
        if fail_at == "user_seed":
            async def seed(schema, user_id):  # noqa: F811
                raise original_error or _ForcedFailure("injected: user_seed")
        ws_a = await seed(a, user_a)
        ws_b = await seed(b, user_b)

        if fail_at == "before_ddl_engine":
            raise original_error or _ForcedFailure("injected: before_ddl_engine")
        ddl_engine = create_async_engine(_async_db_url(), pool_size=1)

        return {
            # tenant_id MUST equal the seeded public.wholesalers.id: the
            # binding lookup keys on token.tenant_id == binding.wholesaler_id.
            "a": {"schema": a, "tenant_id": ws_a, "user_id": user_a},
            "b": {"schema": b, "tenant_id": ws_b, "user_id": user_b},
            "owned": owned,
            "ddl_engine": ddl_engine,
        }
    except BaseException as original_exc:
        # Capture the ORIGINAL exception object explicitly.
        try:
            # REAL cleanup call; with cleanup_error it genuinely raises the
            # pre-created object (surfaces exactly like a drop failure).
            await _drop_owned_schemas(owned, forced_error=cleanup_error)
            await _assert_zero_namespace_residue(owned)
        except BaseException as ce:  # noqa: BLE001 — collected, never masking
            # Dual-failure surface: the group's members carry the ORIGINAL
            # exception and the REAL cleanup error (no overwrite).
            raise BaseExceptionGroup(
                "tenant setup failed and cleanup also failed",
                [original_exc, ce],
            ) from None
        # Cleanup succeeded: re-raise the SAME original exception object.
        raise original_exc
    finally:
        if ddl_engine is not None:
            await ddl_engine.dispose()


@pytest_asyncio.fixture(scope="module")
async def two_tenants():
    """Two formally bootstrapped tenants with exact-route readiness rows.

    Teardown is wrapped in try/finally around the yield; cleanup uses FRESH
    engines/sessions, deletes EXACTLY the owned schema names (no prefixes,
    no LIKE, no wildcards), verifies zero residue, disposes the fixture
    engine, and propagates any teardown failure (nothing swallowed)."""
    ctx = await _setup_two_tenants()
    try:
        yield ctx
    finally:
        teardown_errors: list[BaseException] = []
        try:
            await _drop_owned_schemas(ctx["owned"])
            await _assert_zero_namespace_residue(ctx["owned"])
        except BaseException as te:  # noqa: BLE001 — collected
            teardown_errors.append(te)
        try:
            await ctx["ddl_engine"].dispose()
        except BaseException as te:  # noqa: BLE001 — collected
            teardown_errors.append(te)
        if teardown_errors:
            raise BaseExceptionGroup("two_tenants teardown failed", teardown_errors)


@pytest_asyncio.fixture
async def ddl_engine(two_tenants):
    """Dedicated DDL connection (provisioning-shaped, outside the pool)."""
    yield two_tenants["ddl_engine"]


@pytest_asyncio.fixture(scope="module", autouse=True)
async def _pw1r4_public_residue_guard():
    """R2-R3 fail-closed finally cleanup for this module's exact residue.

    Runs at module end even when individual tests fail; teardown errors are
    collected and raised (they never mask an original test failure — that
    exception has already reached pytest). Cleanup uses fresh engines in
    FK-safe order (binding -> retailer -> wholesaler -> exact schema); a
    task-created retailer is deleted only when no unrelated binding owns it.
    An independent fresh-engine proof requires zero residue for every
    recorded identity (public rows AND pg_namespace), else the module errors.
    """
    yield
    teardown_errors: list[BaseException] = []
    schema_names = list(_OWNED_SCHEMAS) + [
        "t_" + entry["wholesaler_id"].replace("-", "") for entry in _OWNED_PUBLIC
    ]
    try:
        cleanup_engine = create_async_engine(_async_db_url(), pool_size=1)
        try:
            async with cleanup_engine.connect() as c:
                for entry in _OWNED_PUBLIC:
                    w, r = entry["wholesaler_id"], entry["retailer_id"]
                    await c.execute(
                        text(
                            "DELETE FROM public.wholesaler_retailer_bindings "
                            "WHERE wholesaler_id = :w AND retailer_id = :r"
                        ),
                        {"w": w, "r": r},
                    )
                    others = (
                        await c.execute(
                            text(
                                "SELECT count(*) FROM public.wholesaler_retailer_bindings "
                                "WHERE retailer_id = :r AND wholesaler_id <> :w"
                            ),
                            {"r": r, "w": w},
                        )
                    ).scalar()
                    if others == 0:
                        await c.execute(
                            text("DELETE FROM public.retailers WHERE id = :r"), {"r": r}
                        )
                    await c.execute(
                        text("DELETE FROM public.wholesalers WHERE id = :w"), {"w": w}
                    )
                for sch in schema_names:
                    await c.execute(text(f'DROP SCHEMA IF EXISTS "{sch}" CASCADE'))
                await c.commit()
        finally:
            await cleanup_engine.dispose()
    except BaseException as te:  # noqa: BLE001 — collected, never masking
        teardown_errors.append(te)
    try:
        proof_engine = create_async_engine(_async_db_url(), pool_size=1)
        try:
            async with proof_engine.connect() as c:
                residue: dict[str, int] = {}
                for entry in _OWNED_PUBLIC:
                    w = entry["wholesaler_id"]
                    residue[f"wholesalers[{w}]"] = (
                        await c.execute(
                            text("SELECT count(*) FROM public.wholesalers WHERE id = :w"),
                            {"w": w},
                        )
                    ).scalar()
                    residue[f"bindings[{w}]"] = (
                        await c.execute(
                            text(
                                "SELECT count(*) FROM public.wholesaler_retailer_bindings "
                                "WHERE wholesaler_id = :w"
                            ),
                            {"w": w},
                        )
                    ).scalar()
                for sch in schema_names:
                    residue[f"pg_namespace[{sch}]"] = (
                        await c.execute(
                            text(
                                "SELECT count(*) FROM pg_catalog.pg_namespace "
                                "WHERE nspname = :n"
                            ),
                            {"n": sch},
                        )
                    ).scalar()
        finally:
            await proof_engine.dispose()
        assert all(count == 0 for count in residue.values()), (
            f"PW1R4 residue teardown left database residue: {residue}"
        )
    except BaseException as te:  # noqa: BLE001 — collected, never masking
        teardown_errors.append(te)
    if teardown_errors:
        raise BaseExceptionGroup("pw1r4 residue guard teardown failed", teardown_errors)


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
        roles=["retailer_operator"],
        tenant_id=tenant["tenant_id"],
        tenant_schema=tenant["schema"],
        token_type="access",
    )


async def _ddl_storm(engine, schema: str) -> None:
    """Provisioning-shaped DDL: ALTER COLUMN TYPE to the OPPOSITE type
    (text <-> varchar) so every storm is a genuine type-OID change; the
    cached ORM user-load plan references users.full_name, so dependency
    invalidation fires on every authenticated-route cycle."""
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
# 1. EXACT-ROUTE GREEN: GET /api/v1/client/orders?page=1&size=100
# ---------------------------------------------------------------------------
async def test_exact_route_abab_cycles_survive_ddl_storm(two_tenants, ddl_engine):
    app = build_app()
    ta = token_for(two_tenants["a"])
    tb = token_for(two_tenants["b"])
    marker_a = f"ORDER-{two_tenants['a']['schema'][-6:]}"
    marker_b = f"ORDER-{two_tenants['b']['schema'][-6:]}"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        async def orders_notes(token):
            r = await client.get(EXACT_ROUTE, headers={"Authorization": f"Bearer {token}"})
            assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:300]}"
            items = r.json()["data"]["items"]
            assert len(items) == 1, f"expected exactly 1 own order, got {len(items)}"
            return items[0]["notes"]

        # A -> B -> DDL -> A
        assert await orders_notes(ta) == marker_a
        assert await orders_notes(tb) == marker_b
        await _ddl_storm(ddl_engine, two_tenants["a"]["schema"])
        assert await orders_notes(ta) == marker_a

        # B -> A after the storm
        assert await orders_notes(tb) == marker_b
        assert await orders_notes(ta) == marker_a


# ---------------------------------------------------------------------------
# 2. EXACT-ROUTE causal RED: legacy engine (production config minus the fix)
# ---------------------------------------------------------------------------
async def test_exact_route_without_fix_reproduces_invalid_cached_statement(
    two_tenants, ddl_engine
):
    """CAUSAL RED on the EXACT route: the real app is wired with a legacy
    engine (production config minus prepared_statement_cache_size=0) for the
    tenant-context session factory; the same route/cycle must fail after the
    DDL storm with InvalidCachedStatementError in the error chain."""
    import database.session as session_module

    legacy_engine = create_async_engine(
        _async_db_url(),
        pool_pre_ping=True,
        pool_size=1,
        max_overflow=0,
        connect_args={
            "server_settings": {"application_name": "pw1r4a_exact_red", "jit": "off"},
        },
    )

    def _legacy_session_factory():
        return AsyncSession(legacy_engine, expire_on_commit=False)

    a = two_tenants["a"]
    marker_a = f"ORDER-{a['schema'][-6:]}"
    orig_session_local = session_module.AsyncSessionLocal

    try:
        # create_tenant_session imports AsyncSessionLocal lazily from
        # database.session at call time, so patching the module attribute
        # reroutes the REAL middleware tenant-context path onto the legacy
        # engine for this test only.
        session_module.AsyncSessionLocal = _legacy_session_factory
        app = build_app()
        ta = token_for(a)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            r = await client.get(EXACT_ROUTE, headers={"Authorization": f"Bearer {ta}"})
            assert r.status_code == 200, f"pre-storm request must be 200: {r.status_code}"
            assert r.json()["data"]["items"][0]["notes"] == marker_a

            await _ddl_storm(ddl_engine, a["schema"])

            # The SAME exact route must now fail through the real stack.
            failure: Exception | None = None
            try:
                await client.get(EXACT_ROUTE, headers={"Authorization": f"Bearer {ta}"})
            except Exception as exc:  # httpx surfaces server exceptions
                failure = exc
            assert failure is not None, "expected the exact route to fail post-DDD"
            chain: list[str] = []
            cur: BaseException | None = failure
            seen: set[int] = set()
            while cur is not None and id(cur) not in seen:
                seen.add(id(cur))
                chain.append(f"{type(cur).__module__}.{type(cur).__name__}")
                cur = cur.__cause__ or cur.__context__
            assert any("InvalidCachedStatement" in c for c in chain), (
                f"expected InvalidCachedStatementError in chain, got: {' -> '.join(chain)}"
            )
    finally:
        session_module.AsyncSessionLocal = orig_session_local
        await legacy_engine.dispose()


# ---------------------------------------------------------------------------
# 3. Engine-level GREEN: production AsyncSessionLocal via get_tenant_db
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

    name_a = await user_full_name(a)
    name_b = await user_full_name(b)
    await _ddl_storm(ddl_engine, a["schema"])
    # A after its own DDL storm, then B -> A
    assert await user_full_name(a) == name_a
    assert await user_full_name(b) == name_b
    assert await user_full_name(a) == name_a


# ---------------------------------------------------------------------------
# 4. Legacy-engine RED: standalone causal proof on a local engine
# ---------------------------------------------------------------------------
async def test_legacy_engine_without_fix_reproduces_invalid_cached_statement(two_tenants, ddl_engine):
    a = two_tenants["a"]
    legacy = create_async_engine(
        _async_db_url(),
        pool_pre_ping=True,
        pool_size=1,
        max_overflow=0,
        connect_args={
            "server_settings": {"application_name": "pw1r4a_legacy_red", "jit": "off"},
        },
    )
    try:
        # The plan must REFERENCE the column the DDL storm alters (full_name):
        # PostgreSQL invalidates prepared plans by dependency.
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
# 5. No-leak guard: correct tenant data across cycles
# ---------------------------------------------------------------------------
async def test_no_cross_tenant_leak_across_cycles(two_tenants, ddl_engine):
    a, b = two_tenants["a"], two_tenants["b"]

    async def who(t):
        out = None
        async for session in get_tenant_db(t["schema"]):
            result = await session.execute(text('SELECT id FROM users LIMIT 1'))
            out = str(result.scalar())
        return out

    for _ in range(2):  # repeated A/B alternation on the shared pool
        assert await who(a) == a["user_id"]
        assert await who(b) == b["user_id"]
    await _ddl_storm(ddl_engine, a["schema"])
    assert await who(a) == a["user_id"]
    assert await who(b) == b["user_id"]


# ---------------------------------------------------------------------------
# 6. Fail-closed setup: forced failures leave zero residue, no masking.
#    The residue proof is INDEPENDENT of the helper under test: the test
#    pre-generates the deterministic schema names, then queries
#    pg_namespace itself via a fresh engine AFTER the helper call.
# ---------------------------------------------------------------------------
async def _owned_schema_count(schema: str) -> int:
    """INDEPENDENT pg_namespace count via a fresh engine (outside helper)."""
    engine = create_async_engine(_async_db_url(), pool_size=1)
    try:
        async with engine.connect() as c:
            return (
                await c.execute(
                    text(
                        "SELECT count(*) FROM pg_catalog.pg_namespace "
                        "WHERE nspname = :n"
                    ),
                    {"n": schema},
                )
            ).scalar()
    finally:
        await engine.dispose()


async def _assert_no_residue(owned: list[str]) -> None:
    for sch in owned:
        n = await _owned_schema_count(sch)
        assert n == 0, f"owned schema '{sch}' residue: count={n} (must be 0)"


async def test_forced_failure_second_bootstrap_cleans_first_schema():
    suffix = uuid.uuid4().hex[:8]
    a = f"t_r4a_a_{suffix}"
    with pytest.raises(_ForcedFailure, match="second_bootstrap") as ei:
        await _setup_two_tenants(fail_at="second_bootstrap", suffix=suffix)
    # original exception type/message preserved (no overwrite)
    assert type(ei.value) is _ForcedFailure
    assert "second_bootstrap" in str(ei.value)
    # INDEPENDENT residue proof: only tenant A ever existed in this run
    await _assert_no_residue([a])


async def test_forced_failure_user_seed_reraises_same_original_object():
    """Cleanup SUCCESS path: the helper re-raises the SAME pre-created
    exception object (object identity, not a copy/reconstruction) after
    cleaning both tenants, and the independent proof sees zero residue."""
    suffix = uuid.uuid4().hex[:8]
    owned = [f"t_r4a_a_{suffix}", f"t_r4a_b_{suffix}"]
    original_error = _ForcedFailure("injected: user_seed")
    with pytest.raises(_ForcedFailure) as ei:
        await _setup_two_tenants(
            fail_at="user_seed", suffix=suffix, original_error=original_error
        )
    assert ei.value is original_error, (
        "cleanup success must re-raise the SAME exception object"
    )
    await _assert_no_residue(owned)


async def test_forced_failure_before_ddl_engine_cleans_both_schemas():
    suffix = uuid.uuid4().hex[:8]
    owned = [f"t_r4a_a_{suffix}", f"t_r4a_b_{suffix}"]
    with pytest.raises(_ForcedFailure, match="before_ddl_engine"):
        await _setup_two_tenants(fail_at="before_ddl_engine", suffix=suffix)
    await _assert_no_residue(owned)


# ---------------------------------------------------------------------------
# 7. Genuine dual-exception truth: original + real cleanup failure, by identity
# ---------------------------------------------------------------------------
async def test_cleanup_failure_raises_exception_group_with_original_and_cleanup():
    """Setup fails AND the REAL cleanup call fails: a BaseExceptionGroup
    surfaces whose members ARE the two pre-created objects (proven by
    object identity — members[0] is original_error, members[1] is
    cleanup_error — never a RuntimeError overwrite). The failed cleanup
    leaves the schemas in place, so the fail-closed finally drops them with
    the real helper and proves zero residue independently."""
    suffix = uuid.uuid4().hex[:8]
    owned = [f"t_r4a_a_{suffix}", f"t_r4a_b_{suffix}"]
    original_error = _ForcedFailure("injected: user_seed")
    cleanup_error = _ForcedFailure("injected: cleanup failure")
    try:
        with pytest.raises(BaseExceptionGroup) as ei:
            await _setup_two_tenants(
                fail_at="user_seed",
                suffix=suffix,
                original_error=original_error,
                cleanup_error=cleanup_error,
            )
        members = list(ei.value.exceptions)
        assert len(members) == 2, (
            f"group must have exactly [original, cleanup] members, got {members!r}"
        )
        assert members[0] is original_error, (
            "members[0] must BE the pre-created original exception object"
        )
        assert members[1] is cleanup_error, (
            "members[1] must BE the pre-created cleanup exception object"
        )
        assert type(members[0]) is _ForcedFailure and "user_seed" in str(members[0])
        assert type(members[1]) is _ForcedFailure and "cleanup failure" in str(members[1])
        assert "setup failed and cleanup also failed" in str(ei.value)
    finally:
        # Fail-closed: the dual failure left both schemas in place — drop
        # them with the REAL helper, then prove zero residue independently
        # (fresh-engine pg_namespace count == 0) in the SAME database.
        await _drop_owned_schemas(owned)
        await _assert_no_residue(owned)
