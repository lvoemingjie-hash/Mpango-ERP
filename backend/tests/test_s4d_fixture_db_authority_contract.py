"""S4-D fixture DB-authority contract (permanent).

CTO-AUTH-REVOCATION-STOCK-R1-S4D-TOPOLOGY-HARNESS-CLOSURE-20260923.

The shared ``async_session`` fixture used to ``CREATE OR REPLACE FUNCTION
public.prevent_ledger_modification()`` as the test runtime role.  In the
formal three-identity topology that statement is a privilege error: the
migration authority (the database owner) exclusively owns the shared guard,
and the runtime role only ever EXECUTEs it from tenant triggers.  The fixture
now asserts that authority contract fail-closed, read-only, BEFORE any DDL,
and this file locks that closure in permanently:

  1. the fixture source no longer contains the runtime-executed public
     ``CREATE OR REPLACE FUNCTION``;
  2. the read-only authority assertion is the FIRST statement of the fixture
     (statically, via AST), before any tenant or public DDL;
  3. positive control: the formal topology passes the live assertion;
  4. the runtime role holds no CREATE on schema public but does hold EXECUTE
     on the guard;
  5. a missing guard function fails with the named authority error and ZERO
     tenant DDL (no schema, no tables);
  6. a wrong-owner guard fails with the named authority error and ZERO
     tenant DDL;
  7. a runtime without guard EXECUTE fails with the named authority error;
  8. a runtime granted CREATE on schema public is refused per the
     least-privilege contract;
  9. the guard's OID, owner and function-body digest are stable across a
     full fixture bootstrap;
  10. the tenant trigger's catalog function IS the migration-owned public
      guard (same OID, same owner).

Negative topologies 5-8 are prepared by the ADMINISTRATOR and MIGRATION
AUTHORITY identities in unique, disposable per-test databases (opt-in via
``MPANGO_ALLOW_TEMP_DB_CREATE=1``) and dropped again in ``finally``; the
shared formal database is only ever read.
"""
from __future__ import annotations

import ast
import os
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.conftest import (
    TEST_TENANT_SCHEMA,
    TestLedgerGuardAuthorityError,
    _assert_test_ledger_guard_contract,
    _bootstrap_tenant_test_schema,
)

# The imported exception matches pytest's Test* collection pattern; it is a
# class contract, not a test class.
TestLedgerGuardAuthorityError.__test__ = False

CONFTEST_SOURCE_PATH = Path(__file__).resolve().parent / "conftest.py"
MIGRATION_010_GUARD_DDL = """
    CREATE OR REPLACE FUNCTION public.prevent_ledger_modification()
    RETURNS TRIGGER AS $$
    BEGIN
        -- Block UPDATE operations
        IF TG_OP = 'UPDATE' THEN
            RAISE EXCEPTION 'Ledger entries are immutable. UPDATE operations are not allowed.'
                USING ERRCODE = 'integrity_constraint_violation',
                      HINT = 'Ledger entries cannot be modified after creation. Create a correction entry instead.';
        END IF;

        -- Block DELETE operations
        IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'Ledger entries are immutable. DELETE operations are not allowed.'
                USING ERRCODE = 'integrity_constraint_violation',
                      HINT = 'Ledger entries cannot be deleted. Create a reversal entry instead.';
        END IF;

        -- This should never be reached, but return OLD for safety
        RETURN OLD;
    END;
    $$ LANGUAGE plpgsql;
"""

GUARD_IDENTITY_SQL = """
    SELECT p.oid::text AS function_oid,
           pg_get_userbyid(p.proowner) AS owner,
           md5(pg_get_functiondef(p.oid)) AS body_md5
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'public'
      AND p.proname = 'prevent_ledger_modification'
"""

_requires_temp_db = pytest.mark.skipif(
    os.environ.get("MPANGO_ALLOW_TEMP_DB_CREATE") != "1",
    reason="set MPANGO_ALLOW_TEMP_DB_CREATE=1 for disposable-database "
    "authority-contract negatives",
)


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        pytest.fail(
            f"missing required environment {name}: the fixture authority "
            "contract only runs against a declared three-identity topology"
        )
    return value


def _runtime_role() -> str:
    return urlsplit(_require_env("TEST_DATABASE_URL")).username or ""


def _migration_role() -> str:
    return (
        urlsplit(_require_env("MPANGO_INVARIANTS_R0_MIGRATION_DATABASE_URL")).username
        or ""
    )


def _admin_connect():
    import psycopg2

    conn = psycopg2.connect(_require_env("MPANGO_INVARIANTS_R0_ADMIN_DATABASE_URL"))
    conn.autocommit = True
    return conn


def _mig_connect(database: str):
    import psycopg2

    parsed = urlsplit(_require_env("MPANGO_INVARIANTS_R0_MIGRATION_DATABASE_URL"))
    conn = psycopg2.connect(parsed._replace(path=f"/{database}").geturl())
    conn.autocommit = True
    return conn


def _async_engine_for(database: str):
    parsed = urlsplit(_require_env("TEST_DATABASE_URL"))
    runtime_url = (
        parsed._replace(path=f"/{database}")
        .geturl()
        .replace("postgresql://", "postgresql+asyncpg://", 1)
    )
    return create_async_engine(runtime_url)


class _DisposableTopology:
    """A unique disposable database whose negative state is prepared by the
    declared administrator and migration-authority identities only."""

    def __init__(self) -> None:
        self.admin = _admin_connect()
        self.database = f"mpango_s4dtopo_neg_{uuid.uuid4().hex[:8]}"
        self.owner = _migration_role()

    def admin_exec(self, statement: str, params: tuple = ()) -> None:
        with self.admin.cursor() as cur:
            cur.execute(statement, params)

    def admin_exec_in_database(self, database: str, statement: str) -> None:
        import psycopg2

        parsed = urlsplit(_require_env("MPANGO_INVARIANTS_R0_ADMIN_DATABASE_URL"))
        conn = psycopg2.connect(parsed._replace(path=f"/{database}").geturl())
        try:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(statement)
        finally:
            conn.close()

    def admin_query(self, statement: str, params: tuple = ()):
        with self.admin.cursor() as cur:
            cur.execute(statement, params)
            return cur.fetchone()

    def mig_sql(self, statement: str) -> None:
        conn = _mig_connect(self.database)
        try:
            with conn.cursor() as cur:
                cur.execute(statement)
        finally:
            conn.close()

    def create(self) -> None:
        self.admin_exec(f'CREATE DATABASE "{self.database}" OWNER "{self.owner}"')

    def drop(self) -> None:
        self.admin_exec(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = %s",
            (self.database,),
        )
        self.admin_exec(f'DROP DATABASE IF EXISTS "{self.database}"')

    def tenant_schema_count(self, schema: str) -> int:
        return int(
            self.admin_query(
                "SELECT count(*) FROM pg_namespace WHERE nspname = %s", (schema,)
            )[0]
        )

    def tenant_relation_count(self, schema: str) -> int:
        return int(
            self.admin_query(
                "SELECT count(*) FROM pg_class c JOIN pg_namespace n "
                "ON n.oid = c.relnamespace WHERE n.nspname = %s",
                (schema,),
            )[0]
        )


# ---------------------------------------------------------------------------
# 1 + 2: static contract — source shape and assertion ordering
# ---------------------------------------------------------------------------


def test_fixture_source_has_no_runtime_public_function_replacement():
    source = CONFTEST_SOURCE_PATH.read_text(encoding="utf-8")
    normalized = " ".join(source.upper().split())
    forbidden = "CREATE OR REPLACE FUNCTION PUBLIC.PREVENT_LEDGER_MODIFICATION"
    assert forbidden not in normalized, (
        "the test fixture must never create or replace the migration-owned "
        "public guard; it is provided by migration 010 and owned by the "
        "migration authority"
    )


def test_read_only_authority_assertion_precedes_all_tenant_ddl():
    tree = ast.parse(CONFTEST_SOURCE_PATH.read_text(encoding="utf-8"))
    fixture = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "_bootstrap_tenant_test_schema"
    )
    statements = list(fixture.body)
    if (
        statements
        and isinstance(statements[0], ast.Expr)
        and isinstance(statements[0].value, ast.Constant)
    ):
        statements = statements[1:]  # drop the docstring
    assert statements, "fixture body must not be empty"
    first = statements[0]
    assert isinstance(first, ast.Expr) and isinstance(first.value, ast.Await), (
        "the first fixture statement must await the read-only authority "
        "assertion"
    )
    awaited = first.value.value
    assert isinstance(awaited, ast.Call), (
        "the awaited expression must be the read-only authority assertion call"
    )
    assert (
        ast.unparse(awaited) == "_assert_test_ledger_guard_contract(session)"
    ), (
        "the read-only authority assertion must run before CREATE SCHEMA, "
        "tenant DDL, trigger DDL and any data write"
    )


# ---------------------------------------------------------------------------
# 3 + 4 + 9 + 10: live formal-topology contract (shared database, read-only
# apart from the fixture's own idempotent tenant bootstrap, rolled back)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_formal_topology_passes_read_only_authority_assertion(async_session):
    await _assert_test_ledger_guard_contract(async_session)


@pytest.mark.asyncio
async def test_runtime_has_no_public_create_but_guard_execute(async_session):
    runtime = (await async_session.execute(text("SELECT current_user"))).scalar_one()
    public_create = (
        await async_session.execute(
            text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")
        )
    ).scalar_one()
    guard_execute = (
        await async_session.execute(
            text(
                "SELECT has_function_privilege("
                "current_user, 'public.prevent_ledger_modification()', 'EXECUTE')"
            )
        )
    ).scalar_one()
    db_owner = (
        await async_session.execute(
            text(
                "SELECT pg_get_userbyid(datdba) FROM pg_database "
                "WHERE datname = current_database()"
            )
        )
    ).scalar_one()
    assert runtime != db_owner, "runtime must differ from the migration authority"
    assert public_create is False, (
        "the runtime role must not hold CREATE on schema public "
        "(drop+create substitution path)"
    )
    assert guard_execute is True, (
        "the runtime role must hold EXECUTE on the guard for tenant triggers"
    )


@pytest.mark.asyncio
async def test_guard_oid_owner_body_digest_stable_across_fixture_bootstrap():
    engine = _async_engine_for(urlsplit(_require_env("TEST_DATABASE_URL")).path.lstrip("/"))
    probe_schema = "t_s4d_fixture_contract_probe"
    try:
        async with engine.connect() as conn:
            before = (await conn.execute(text(GUARD_IDENTITY_SQL))).mappings().one()
            # Full fixture bootstrap against a dedicated probe schema inside
            # one transaction; the rollback leaves zero residue while still
            # exercising every fixture statement around the guard.
            await _bootstrap_tenant_test_schema(conn, probe_schema)
            await conn.rollback()
            after = (await conn.execute(text(GUARD_IDENTITY_SQL))).mappings().one()
        assert after == before, (
            "the fixture must not alter the migration-owned guard: "
            f"before={dict(before)} after={dict(after)}"
        )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_tenant_trigger_targets_migration_owned_public_guard(async_session):
    row = (
        await async_session.execute(
            text(
                """
                SELECT t.tgname,
                       t.tgfoid::text AS trigger_target_oid,
                       p.oid::text AS public_guard_oid,
                       pg_get_userbyid(p.proowner) AS guard_owner,
                       (SELECT pg_get_userbyid(datdba) FROM pg_database
                        WHERE datname = current_database()) AS database_owner
                FROM pg_trigger t
                JOIN pg_class c ON c.oid = t.tgrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                JOIN pg_proc p ON p.oid = t.tgfoid
                JOIN pg_namespace pn ON pn.oid = p.pronamespace
                WHERE n.nspname = :schema
                  AND c.relname = 'ledger_entries'
                  AND NOT t.tgisinternal
                  AND pn.nspname = 'public'
                  AND p.proname = 'prevent_ledger_modification'
                """
            ),
            {"schema": TEST_TENANT_SCHEMA},
        )
    ).mappings().all()
    assert len(row) == 1, "exactly one guard trigger expected on ledger_entries"
    trigger = row[0]
    assert trigger["tgname"] == "prevent_ledger_modification_trigger"
    # The trigger's catalog function IS the unique migration-owned public
    # guard (identity by OID, immune to search_path rendering).
    guard_oid = (
        await async_session.execute(
            text(
                """
                SELECT p.oid::text FROM pg_proc p
                JOIN pg_namespace n ON n.oid = p.pronamespace
                WHERE n.nspname = 'public'
                  AND p.proname = 'prevent_ledger_modification'
                """
            )
        )
    ).scalar_one()
    assert trigger["trigger_target_oid"] == guard_oid
    assert trigger["public_guard_oid"] == guard_oid
    assert trigger["guard_owner"] == trigger["database_owner"], (
        "the trigger's catalog function must be the migration-owned public "
        "guard, not a runtime-owned copy"
    )


# ---------------------------------------------------------------------------
# 5 + 6 + 7 + 8: negative topologies in disposable databases
# ---------------------------------------------------------------------------


@_requires_temp_db
@pytest.mark.asyncio
async def test_missing_guard_fails_named_with_zero_tenant_ddl():
    topo = _DisposableTopology()
    topo.create()
    schema = "t_s4d_contract_missing_guard"
    try:
        engine = _async_engine_for(topo.database)
        try:
            async with engine.connect() as conn:
                with pytest.raises(TestLedgerGuardAuthorityError) as excinfo:
                    await _bootstrap_tenant_test_schema(conn, schema)
            assert "missing" in str(excinfo.value)
        finally:
            await engine.dispose()
        assert topo.tenant_schema_count(schema) == 0, "zero tenant DDL expected"
        assert topo.tenant_relation_count(schema) == 0
    finally:
        topo.drop()


@_requires_temp_db
@pytest.mark.asyncio
async def test_wrong_owner_guard_fails_named_with_zero_tenant_ddl():
    topo = _DisposableTopology()
    topo.create()
    schema = "t_s4d_contract_wrong_owner"
    try:
        # Administrator (NOT the migration authority) creates the guard, so
        # the function owner differs from the database owner.
        topo.admin_exec_in_database(topo.database, MIGRATION_010_GUARD_DDL)
        engine = _async_engine_for(topo.database)
        try:
            async with engine.connect() as conn:
                with pytest.raises(TestLedgerGuardAuthorityError) as excinfo:
                    await _bootstrap_tenant_test_schema(conn, schema)
            assert "is not the database owner" in str(excinfo.value)
        finally:
            await engine.dispose()
        assert topo.tenant_schema_count(schema) == 0, "zero tenant DDL expected"
        assert topo.tenant_relation_count(schema) == 0
    finally:
        topo.drop()


@_requires_temp_db
@pytest.mark.asyncio
async def test_runtime_without_guard_execute_fails_named():
    topo = _DisposableTopology()
    topo.create()
    schema = "t_s4d_contract_no_execute"
    try:
        topo.mig_sql(MIGRATION_010_GUARD_DDL)
        # PUBLIC holds EXECUTE on functions by default; the formal shape
        # grants it explicitly.  Revoke both so the runtime truly lacks it.
        topo.mig_sql(
            "REVOKE EXECUTE ON FUNCTION "
            "public.prevent_ledger_modification() FROM PUBLIC"
        )
        engine = _async_engine_for(topo.database)
        try:
            async with engine.connect() as conn:
                with pytest.raises(TestLedgerGuardAuthorityError) as excinfo:
                    await _assert_test_ledger_guard_contract(conn)
            assert "EXECUTE" in str(excinfo.value)
        finally:
            await engine.dispose()
    finally:
        topo.drop()


@_requires_temp_db
@pytest.mark.asyncio
async def test_runtime_with_public_create_refused_by_least_privilege():
    topo = _DisposableTopology()
    topo.create()
    schema = "t_s4d_contract_public_create"
    try:
        topo.mig_sql(MIGRATION_010_GUARD_DDL)
        runtime_role = _runtime_role()
        assert runtime_role, "runtime role missing from TEST_DATABASE_URL"
        topo.mig_sql(f'GRANT CREATE ON SCHEMA public TO "{runtime_role}"')
        engine = _async_engine_for(topo.database)
        try:
            async with engine.connect() as conn:
                with pytest.raises(TestLedgerGuardAuthorityError) as excinfo:
                    await _assert_test_ledger_guard_contract(conn)
            assert "CREATE on schema public" in str(excinfo.value)
        finally:
            await engine.dispose()
    finally:
        topo.drop()
