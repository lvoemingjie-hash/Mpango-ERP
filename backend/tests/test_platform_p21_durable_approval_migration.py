"""
P21-C1 G2: Durable Approval Store migration tests (real ephemeral PostgreSQL).

Group G2 from the accepted P21-B plan (section 9). Drives the real Alembic migration
020_durable_approval_store against an ephemeral PostgreSQL database and proves:
  - the migration is ADDITIVE-ONLY: upgrading from the base revision (019) to head (020)
    adds ONLY the five durable tables, their indexes / constraints, and the durable enum
    types in public; no existing object is altered or removed, and NO new schema is created;
  - the DOWNGRADE drops only P21-C1 objects (five tables + enum types + their indexes /
    constraints) and leaves every base object intact;
  - RE-UPGRADE recreates the five tables cleanly;
  - CATALOG PROOF: no durable_approval_* object exists in any tenant (non-public) schema and
    the set of schemas is unchanged by the upgrade (public-mode only, no -x tenant_schema).

These tests REFUSE to run against the developer mpango_erp database or any unset / shared
target. Public mode only: no Alembic command passes -x tenant_schema. A session bootstrap
fixture applies the test-only DB prerequisites (pgcrypto, widened public.alembic_version,
t_dev) so the tests reproduce from a clean throwaway container with only the DB URL set --
no manual SQL required.
"""
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[1]
BASE_REV = "019_platform_audit_logs"
PUBLIC = "public"

DURABLE_TABLES = {
    "durable_approval_requests", "durable_approval_decisions",
    "durable_approval_audit_events", "durable_approval_idempotency_keys",
    "durable_approval_retention_jobs",
}
DURABLE_ENUMS = {
    "durable_approval_state", "durable_approval_action_class", "durable_approval_execution_gate",
    "durable_approval_source_status", "durable_approval_validation_status",
    "durable_approval_retention_class", "durable_approval_decision", "durable_approval_actor_role",
    "durable_approval_identity_context", "durable_approval_event_type",
    "durable_approval_audit_result", "durable_approval_storage_class",
    "durable_approval_scope_key", "durable_approval_job_type", "durable_approval_job_status",
}


def _ephemeral_url():
    u = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not u:
        pytest.skip("no TEST_DATABASE_URL/DATABASE_URL set; refusing without an explicit ephemeral DB")
    if "mpango_erp" in u.lower():
        pytest.skip("refusing to run against the developer mpango_erp database; point TEST_DATABASE_URL at an ephemeral DB")
    return u


def _psql(url):
    return url.replace("postgresql+asyncpg://", "postgresql://")


def _bootstrap_ephemeral(url):
    """Test-only initialization mirroring database/init.sql (self-contained repro).

    The base Alembic chain assumes three prerequisites a bare throwaway Postgres lacks: the
    pgcrypto extension, a wide-enough public.alembic_version (this project uses long revision
    ids), and the t_dev schema. This runs ONLY against the explicit ephemeral DB and is
    idempotent, so the tests reproduce from a clean container with only the DB URL set.
    """
    import psycopg2
    conn = psycopg2.connect(_psql(url))
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute('CREATE EXTENSION IF NOT EXISTS pgcrypto')
        cur.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'alembic_version'
            )
        """)
        has_av = cur.fetchone()[0]
        if has_av:
            cur.execute("""
                SELECT character_maximum_length FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'alembic_version'
                  AND column_name = 'version_num'
            """)
            row = cur.fetchone()
            length = row[0] if row else 0
            if length is None or length < 128:
                cur.execute(
                    "ALTER TABLE public.alembic_version "
                    "ALTER COLUMN version_num TYPE varchar(128)"
                )
        else:
            cur.execute("""
                CREATE TABLE public.alembic_version (
                    version_num varchar(128) NOT NULL,
                    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
                )
            """)
        cur.execute('CREATE SCHEMA IF NOT EXISTS t_dev')
    finally:
        cur.close()
        conn.close()


@pytest.fixture(scope="module")
def _boot():
    """Resolve the ephemeral URL, set env, and run test-only DB initialization once."""
    url = _ephemeral_url()
    os.environ["DATABASE_URL"] = url
    os.environ.setdefault("REPORTING_USER_PASSWORD", "ephemeral_reporting_pw")
    _bootstrap_ephemeral(url)
    return url


@pytest.fixture(scope="module")
def alembic_cfg(_boot):
    from alembic.config import Config
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return cfg


@pytest.fixture(scope="module")
def conn(_boot):
    import psycopg2
    c = psycopg2.connect(_psql(_boot))
    try:
        yield c
    finally:
        c.close()


def _snapshot(cur):
    """Capture all user objects, table-aware so durable ownership is filterable.

    indexes / constraints are 3-tuples (schema, table, name); tables are (schema, table);
    enums are (schema, name).
    """
    cur.execute("""
        SELECT schema_name FROM information_schema.schemata
        WHERE schema_name NOT IN ('pg_catalog', 'information_schema')
          AND schema_name NOT LIKE 'pg_toast%' AND schema_name NOT LIKE 'pg_temp_%'
        ORDER BY schema_name
    """)
    schemas = tuple(r[0] for r in cur.fetchall())

    cur.execute("""
        SELECT table_schema, table_name FROM information_schema.tables
        WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
          AND table_schema NOT LIKE 'pg_toast%' AND table_schema NOT LIKE 'pg_temp_%'
          AND table_name NOT LIKE 'pg_%'
        ORDER BY table_schema, table_name
    """)
    tables = tuple((r[0], r[1]) for r in cur.fetchall())

    cur.execute("""
        SELECT schemaname, tablename, indexname FROM pg_indexes
        WHERE schemaname NOT IN ('pg_catalog','information_schema') AND schemaname NOT LIKE 'pg_toast%'
        ORDER BY schemaname, tablename, indexname
    """)
    indexes = tuple((r[0], r[1], r[2]) for r in cur.fetchall())

    cur.execute("""
        SELECT n2.nspname, cls.relname, c.conname FROM pg_constraint c
        JOIN pg_class cls ON c.conrelid = cls.oid
        JOIN pg_namespace n2 ON cls.relnamespace = n2.oid
        JOIN pg_namespace n ON c.connamespace = n.oid
        WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_toast%'
        ORDER BY n2.nspname, cls.relname, c.conname
    """)
    constraints = tuple((r[0], r[1], r[2]) for r in cur.fetchall())

    cur.execute("""
        SELECT n.nspname, t.typname FROM pg_type t
        JOIN pg_namespace n ON t.typnamespace = n.oid
        WHERE t.typtype = 'e' AND n.nspname NOT IN ('pg_catalog','information_schema')
        ORDER BY n.nspname, t.typname
    """)
    enums = tuple((r[0], r[1]) for r in cur.fetchall())

    return {"schemas": schemas, "tables": tables, "indexes": indexes,
            "constraints": constraints, "enums": enums}


def _durable_in(snap):
    """True sets of durable objects present in a snapshot."""
    return {
        "tables": {t for _, t in snap["tables"] if t in DURABLE_TABLES},
        "indexes": {(s, t, i) for s, t, i in snap["indexes"] if t in DURABLE_TABLES},
        "constraints": {(s, t, c) for s, t, c in snap["constraints"] if t in DURABLE_TABLES},
        "enums": {n for _, n in snap["enums"] if n in DURABLE_ENUMS},
    }


def _base_only(snap):
    """Snapshot sets with all durable objects removed (the pre-existing base inventory)."""
    return {
        "tables": {x for x in snap["tables"] if x[1] not in DURABLE_TABLES},
        "indexes": {x for x in snap["indexes"] if x[1] not in DURABLE_TABLES},
        "constraints": {x for x in snap["constraints"] if x[1] not in DURABLE_TABLES},
        "enums": {x for x in snap["enums"] if x[1] not in DURABLE_ENUMS},
    }


def test_additions_only_from_base_to_head(alembic_cfg, conn):
    """Upgrade base(019) -> head(020) adds ONLY durable tables / indexes / constraints / enums."""
    from alembic import command
    command.upgrade(alembic_cfg, "head")          # ensure at least at 020
    command.downgrade(alembic_cfg, BASE_REV)      # -> 019
    cur = conn.cursor()
    before = _snapshot(cur)
    command.upgrade(alembic_cfg, "head")          # -> 020
    after = _snapshot(cur)

    # 1. No schema created by the upgrade (public-mode only).
    assert before["schemas"] == after["schemas"], (
        f"upgrade changed schemas: before={before['schemas']} after={after['schemas']}"
    )

    # 2. Nothing removed or altered: every prior object still present.
    assert set(before["tables"]) <= set(after["tables"]), "upgrade dropped/changed a table"
    assert set(before["indexes"]) <= set(after["indexes"]), "upgrade dropped/changed an index"
    assert set(before["constraints"]) <= set(after["constraints"]), "upgrade dropped/changed a constraint"
    assert set(before["enums"]) <= set(after["enums"]), "upgrade dropped/changed an enum"

    # 3. New tables are EXACTLY the five durable tables, all in public.
    new_tables = set(after["tables"]) - set(before["tables"])
    assert new_tables == {(PUBLIC, t) for t in DURABLE_TABLES}, f"unexpected new tables: {new_tables}"

    # 4. New enums are EXACTLY the durable enum types, all in public.
    new_enums = set(after["enums"]) - set(before["enums"])
    assert new_enums == {(PUBLIC, e) for e in DURABLE_ENUMS}, f"unexpected new enums: {new_enums}"

    # 5. New indexes / constraints all belong to durable tables in public (no base object touched).
    new_indexes = set(after["indexes"]) - set(before["indexes"])
    new_constraints = set(after["constraints"]) - set(before["constraints"])
    assert new_indexes == _durable_in(after)["indexes"], (
        f"new indexes are not exactly the durable indexes: {new_indexes ^ _durable_in(after)['indexes']}"
    )
    assert all(s == PUBLIC for s, _, _ in new_constraints), f"non-public new constraint: {new_constraints}"
    assert all(t in DURABLE_TABLES for _, t, _ in new_constraints), (
        f"new constraint on a non-durable table: {new_constraints}"
    )


def test_downgrade_drops_only_p21_objects(alembic_cfg, conn):
    """downgrade -1 from head removes only the five tables + enums + their indexes/constraints."""
    from alembic import command
    command.upgrade(alembic_cfg, "head")          # -> 020
    cur = conn.cursor()
    at_head = _snapshot(cur)
    command.downgrade(alembic_cfg, BASE_REV)      # -> 019
    after_down = _snapshot(cur)

    # 1. Every durable object is gone.
    dur = _durable_in(after_down)
    for kind in ("tables", "indexes", "constraints", "enums"):
        assert not dur[kind], f"durable {kind} still present after downgrade: {dur[kind]}"

    # 2. Base inventory identical (downgrade touched nothing pre-existing).
    head_base = _base_only(at_head)
    for kind in ("tables", "indexes", "constraints", "enums"):
        assert _base_only(after_down)[kind] == head_base[kind], (
            f"downgrade altered base {kind}"
        )
    # 3. Schemas unchanged.
    assert after_down["schemas"] == at_head["schemas"]


def test_reupgrade_recreates_tables(alembic_cfg, conn):
    """After downgrade, re-running upgrade recreates all five tables cleanly."""
    from alembic import command
    command.downgrade(alembic_cfg, BASE_REV)      # -> 019
    command.upgrade(alembic_cfg, "head")          # -> 020 again
    cur = conn.cursor()
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = %s AND table_name LIKE 'durable_approval_%%'
    """, (PUBLIC,))
    found = {r[0] for r in cur.fetchall()}
    assert found == DURABLE_TABLES, f"re-upgrade did not recreate all tables: {found}"


def test_no_durable_objects_in_tenant_schemas(alembic_cfg, conn):
    """Catalog proof: no durable_approval_* table/type exists outside the public schema."""
    from alembic import command
    command.upgrade(alembic_cfg, "head")
    cur = conn.cursor()
    cur.execute("""
        SELECT table_schema, table_name FROM information_schema.tables
        WHERE table_name LIKE 'durable_approval_%%' AND table_schema <> %s
    """, (PUBLIC,))
    stray_tables = cur.fetchall()
    assert stray_tables == [], f"durable tables leaked into tenant schemas: {stray_tables}"
    cur.execute("""
        SELECT n.nspname, t.typname FROM pg_type t
        JOIN pg_namespace n ON t.typnamespace = n.oid
        WHERE t.typtype = 'e' AND t.typname LIKE 'durable_approval_%%' AND n.nspname <> %s
    """, (PUBLIC,))
    stray_enums = cur.fetchall()
    assert stray_enums == [], f"durable enums leaked into tenant schemas: {stray_enums}"


def test_upgrade_does_not_create_tenant_schema(alembic_cfg, conn):
    """Public-mode upgrade must not create any tenant schema (env.py side-effect avoidance)."""
    from alembic import command
    command.downgrade(alembic_cfg, BASE_REV)      # -> 019
    cur = conn.cursor()
    before = _snapshot(cur)["schemas"]
    command.upgrade(alembic_cfg, "head")          # -> 020
    after = _snapshot(cur)["schemas"]
    assert before == after, (
        f"public-mode upgrade changed the schema set: before={before} after={after}"
    )


def test_base_revision_is_019_before_upgrade(alembic_cfg, conn):
    """Preflight: before applying 020, the public head is the 019 base revision."""
    from alembic import command
    command.downgrade(alembic_cfg, BASE_REV)      # -> 019
    cur = conn.cursor()
    cur.execute("SELECT version_num FROM public.alembic_version")
    rev = cur.fetchone()[0]
    assert rev == BASE_REV, f"expected public head {BASE_REV} before upgrade, got {rev}"
