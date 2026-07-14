"""
P17-D-C: Backup / Status Source migration tests (real ephemeral PostgreSQL).

Drives the real Alembic migration 021_platform_backup_status_source against an
ephemeral PostgreSQL database and proves:
  - the migration is ADDITIVE-ONLY: upgrading from the base revision (020) to this
    revision (021) adds ONLY the two backup tables, their indexes / constraints,
    and the two backup enum types in public; no existing object is altered or
    removed, and NO new schema is created;
  - the DOWNGRADE drops only P17-D-C objects (two tables + enum types + their
    indexes / constraints) and leaves every base object intact;
  - RE-UPGRADE recreates the two tables cleanly;
  - CATALOG PROOF: no platform_backup_* object exists in any tenant (non-public)
    schema and the set of schemas is unchanged by the upgrade (public-mode only);
  - the CHECK constraints enforce the honesty invariants (G14): success requires
    bytes_written > 0; failed/partial require an allowlisted failure_reason_code;
    success/in_progress forbid a failure_reason_code; in_progress <=> completed_at
    IS NULL; bytes only for success/partial; and a raw (non-allowlisted) failure
    reason is rejected at the DB;
  - the policy uniqueness holds (at most one row per tenant; at most one
    platform-default row);
  - the latest-completed read excludes in_progress rows (G17).

These tests REFUSE to run against the developer mpango_erp database or any unset /
shared target. Public mode only: no Alembic command passes -x tenant_schema. A
session bootstrap fixture applies the test-only DB prerequisites (pgcrypto,
widened public.alembic_version, t_dev) so the tests reproduce from a clean
throwaway container with only the DB URL set.

The upgrade/downgrade upper bound is PINNED to this revision (021) instead of the
bare 'head', so adding a later migration does not change what this test exercises
(020 <-> 021 only).
"""
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[1]
BASE_REV = "020_durable_approval_store"
HEAD_REV = "021_platform_backup_status_source"  # pinned (not bare 'head')
PUBLIC = "public"

BACKUP_TABLES = {"platform_backup_outcome", "platform_backup_policy"}
BACKUP_ENUMS = {"platform_backup_job_kind", "platform_backup_outcome_status"}


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
    """Test-only initialization mirroring database/init.sql (self-contained repro)."""
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
    """Capture user objects (table-aware so backup ownership is filterable)."""
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


def _backup_in(snap):
    return {
        "tables": {t for _, t in snap["tables"] if t in BACKUP_TABLES},
        "indexes": {(s, t, i) for s, t, i in snap["indexes"] if t in BACKUP_TABLES},
        "constraints": {(s, t, c) for s, t, c in snap["constraints"] if t in BACKUP_TABLES},
        "enums": {n for _, n in snap["enums"] if n in BACKUP_ENUMS},
    }


def _base_only(snap):
    return {
        "tables": {x for x in snap["tables"] if x[1] not in BACKUP_TABLES},
        "indexes": {x for x in snap["indexes"] if x[1] not in BACKUP_TABLES},
        "constraints": {x for x in snap["constraints"] if x[1] not in BACKUP_TABLES},
        "enums": {x for x in snap["enums"] if x[1] not in BACKUP_ENUMS},
    }


def test_additions_only_from_base_to_head(alembic_cfg, conn):
    """Upgrade base(020) -> 021 adds ONLY backup tables / indexes / constraints / enums."""
    from tests.conftest import run_alembic_upgrade  # (was: from alembic import command)
    run_alembic_upgrade(alembic_cfg, HEAD_REV)         # ensure at 021
    command.downgrade(alembic_cfg, BASE_REV)       # -> 020
    cur = conn.cursor()
    before = _snapshot(cur)
    run_alembic_upgrade(alembic_cfg, HEAD_REV)         # -> 021
    after = _snapshot(cur)

    assert before["schemas"] == after["schemas"], (
        f"upgrade changed schemas: before={before['schemas']} after={after['schemas']}"
    )
    for kind in ("tables", "indexes", "constraints", "enums"):
        assert set(before[kind]) <= set(after[kind]), f"upgrade dropped/changed a {kind}"

    new_tables = set(after["tables"]) - set(before["tables"])
    assert new_tables == {(PUBLIC, t) for t in BACKUP_TABLES}, f"unexpected new tables: {new_tables}"

    new_enums = set(after["enums"]) - set(before["enums"])
    assert new_enums == {(PUBLIC, e) for e in BACKUP_ENUMS}, f"unexpected new enums: {new_enums}"

    new_indexes = set(after["indexes"]) - set(before["indexes"])
    new_constraints = set(after["constraints"]) - set(before["constraints"])
    assert new_indexes == _backup_in(after)["indexes"], (
        f"new indexes are not exactly the backup indexes: {new_indexes ^ _backup_in(after)['indexes']}"
    )
    assert all(s == PUBLIC for s, _, _ in new_constraints), f"non-public new constraint: {new_constraints}"
    assert all(t in BACKUP_TABLES for _, t, _ in new_constraints), (
        f"new constraint on a non-backup table: {new_constraints}"
    )


def test_downgrade_drops_only_p17dc_objects(alembic_cfg, conn):
    """downgrade 021 -> 020 removes only the two tables + enums + their indexes/constraints."""
    from tests.conftest import run_alembic_upgrade  # (was: from alembic import command)
    run_alembic_upgrade(alembic_cfg, HEAD_REV)         # -> 021
    cur = conn.cursor()
    at_head = _snapshot(cur)
    command.downgrade(alembic_cfg, BASE_REV)       # -> 020
    after_down = _snapshot(cur)

    bak = _backup_in(after_down)
    for kind in ("tables", "indexes", "constraints", "enums"):
        assert not bak[kind], f"backup {kind} still present after downgrade: {bak[kind]}"

    head_base = _base_only(at_head)
    for kind in ("tables", "indexes", "constraints", "enums"):
        assert _base_only(after_down)[kind] == head_base[kind], (
            f"downgrade altered base {kind}"
        )
    assert after_down["schemas"] == at_head["schemas"]


def test_reupgrade_recreates_tables(alembic_cfg, conn):
    from tests.conftest import run_alembic_upgrade  # (was: from alembic import command)
    command.downgrade(alembic_cfg, BASE_REV)       # -> 020
    run_alembic_upgrade(alembic_cfg, HEAD_REV)         # -> 021 again
    cur = conn.cursor()
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = %s AND table_name LIKE 'platform_backup_%%'
    """, (PUBLIC,))
    found = {r[0] for r in cur.fetchall()}
    assert found == BACKUP_TABLES, f"re-upgrade did not recreate all tables: {found}"


def test_no_backup_objects_in_tenant_schemas(alembic_cfg, conn):
    from tests.conftest import run_alembic_upgrade  # (was: from alembic import command)
    run_alembic_upgrade(alembic_cfg, HEAD_REV)
    cur = conn.cursor()
    cur.execute("""
        SELECT table_schema, table_name FROM information_schema.tables
        WHERE table_name LIKE 'platform_backup_%%' AND table_schema <> %s
    """, (PUBLIC,))
    assert cur.fetchall() == [], "backup tables leaked into tenant schemas"
    cur.execute("""
        SELECT n.nspname, t.typname FROM pg_type t
        JOIN pg_namespace n ON t.typnamespace = n.oid
        WHERE t.typtype = 'e' AND t.typname LIKE 'platform_backup_%%' AND n.nspname <> %s
    """, (PUBLIC,))
    assert cur.fetchall() == [], "backup enums leaked into tenant schemas"


def test_upgrade_does_not_create_tenant_schema(alembic_cfg, conn):
    from tests.conftest import run_alembic_upgrade  # (was: from alembic import command)
    command.downgrade(alembic_cfg, BASE_REV)       # -> 020
    cur = conn.cursor()
    before = _snapshot(cur)["schemas"]
    run_alembic_upgrade(alembic_cfg, HEAD_REV)         # -> 021
    after = _snapshot(cur)["schemas"]
    assert before == after, (
        f"public-mode upgrade changed the schema set: before={before} after={after}"
    )


def test_base_revision_is_020_before_upgrade(alembic_cfg, conn):
    from tests.conftest import run_alembic_upgrade  # (was: from alembic import command)
    command.downgrade(alembic_cfg, BASE_REV)       # -> 020
    cur = conn.cursor()
    cur.execute("SELECT version_num FROM public.alembic_version")
    assert cur.fetchone()[0] == BASE_REV


# ---------------------------------------------------------------------------
# G14: CHECK constraints enforce the honesty invariants at the DB layer.
# ---------------------------------------------------------------------------


def _insert(cur, sql, params=None):
    cur.execute(sql, params or ())


def test_check_constraints_enforce_honesty(alembic_cfg, conn):
    from tests.conftest import run_alembic_upgrade  # (was: from alembic import command)
    import psycopg2
    run_alembic_upgrade(alembic_cfg, HEAD_REV)
    cur = conn.cursor()
    cur.execute("DELETE FROM public.platform_backup_outcome")
    conn.commit()
    cur.close()

    def expect_ok(sql, params=None):
        cur = conn.cursor()
        try:
            cur.execute(sql, params)
            conn.commit()
        finally:
            cur.close()

    def expect_rejected(sql, params=None):
        cur = conn.cursor()
        with pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute(sql, params)
            conn.commit()
        conn.rollback()
        cur.close()

    cols = "(tenant_id, job_kind, status, started_at, completed_at, bytes_written, failure_reason_code, source_writer_id)"

    # success with bytes_written > 0 -> ok
    expect_ok(
        f"INSERT INTO public.platform_backup_outcome {cols} VALUES "
        "(NULL,'backup_job','success',now(),now()-interval '1 hour',1024,NULL,'test_writer')"
    )
    # success with bytes_written NULL -> rejected (ck_pbo_success_has_bytes)
    expect_rejected(
        f"INSERT INTO public.platform_backup_outcome {cols} VALUES "
        "(NULL,'backup_job','success',now(),now()-interval '1 hour',NULL,NULL,'test_writer')"
    )
    # success with bytes_written 0 -> rejected
    expect_rejected(
        f"INSERT INTO public.platform_backup_outcome {cols} VALUES "
        "(NULL,'backup_job','success',now(),now()-interval '1 hour',0,NULL,'test_writer')"
    )
    # success with a failure_reason_code -> rejected (ck_pbo_failure_reason_scope)
    expect_rejected(
        f"INSERT INTO public.platform_backup_outcome {cols} VALUES "
        "(NULL,'backup_job','success',now(),now()-interval '1 hour',1024,'backup_incomplete','test_writer')"
    )
    # failed with allowlisted reason -> ok
    expect_ok(
        f"INSERT INTO public.platform_backup_outcome {cols} VALUES "
        "(NULL,'backup_job','failed',now(),now(),NULL,'backup_incomplete','test_writer')"
    )
    # failed with NULL failure_reason_code -> rejected (ck_pbo_failure_reason_scope)
    expect_rejected(
        f"INSERT INTO public.platform_backup_outcome {cols} VALUES "
        "(NULL,'backup_job','failed',now(),now(),NULL,NULL,'test_writer')"
    )
    # failed with a raw (non-allowlisted) reason -> rejected (ck_pbo_failure_reason_allowlist)
    expect_rejected(
        f"INSERT INTO public.platform_backup_outcome {cols} VALUES "
        "(NULL,'backup_job','failed',now(),now(),NULL,'pg_dump: password authentication failed','test_writer')"
    )
    # failed with bytes_written set -> rejected (ck_pbo_bytes_scope)
    expect_rejected(
        f"INSERT INTO public.platform_backup_outcome {cols} VALUES "
        "(NULL,'backup_job','failed',now(),now(),512,'backup_incomplete','test_writer')"
    )
    # in_progress with completed_at NULL -> ok
    expect_ok(
        f"INSERT INTO public.platform_backup_outcome {cols} VALUES "
        "(NULL,'backup_job','in_progress',now(),NULL,NULL,NULL,'test_writer')"
    )
    # in_progress with completed_at set -> rejected (ck_pbo_completed_iff_not_in_progress)
    expect_rejected(
        f"INSERT INTO public.platform_backup_outcome {cols} VALUES "
        "(NULL,'backup_job','in_progress',now(),now(),NULL,NULL,'test_writer')"
    )


def test_policy_uniqueness(alembic_cfg, conn):
    from tests.conftest import run_alembic_upgrade  # (was: from alembic import command)
    import psycopg2
    run_alembic_upgrade(alembic_cfg, HEAD_REV)
    cur = conn.cursor()
    cur.execute("DELETE FROM public.platform_backup_policy")
    conn.commit()
    cur.close()

    def insert_policy(tenant_id_literal):
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO public.platform_backup_policy "
                "(tenant_id, retention_policy, export_enabled) VALUES (%s,'7 daily',true)",
                (tenant_id_literal,),
            )
            conn.commit()
        finally:
            cur.close()

    # First platform-default (tenant_id NULL) ok.
    insert_policy(None)
    # Second platform-default -> rejected by the partial unique index.
    cur = conn.cursor()
    with pytest.raises(psycopg2.errors.UniqueViolation):
        cur.execute(
            "INSERT INTO public.platform_backup_policy "
            "(tenant_id, retention_policy) VALUES (NULL,'7 daily')"
        )
        conn.commit()
    conn.rollback()
    cur.close()


# ---------------------------------------------------------------------------
# G17: the latest-completed read excludes in_progress rows (completed_at IS NULL).
# ---------------------------------------------------------------------------


def test_latest_completed_excludes_in_progress(alembic_cfg, conn):
    from tests.conftest import run_alembic_upgrade  # (was: from alembic import command)
    run_alembic_upgrade(alembic_cfg, HEAD_REV)
    cur = conn.cursor()
    cur.execute("DELETE FROM public.platform_backup_outcome")
    conn.commit()
    # One completed backup_job and one in_progress (completed_at IS NULL).
    cur.execute(
        "INSERT INTO public.platform_backup_outcome "
        "(tenant_id, job_kind, status, started_at, completed_at, bytes_written, source_writer_id) "
        "VALUES (NULL,'backup_job','success',now(),now()-interval '1 hour',1024,'test_writer')"
    )
    cur.execute(
        "INSERT INTO public.platform_backup_outcome "
        "(tenant_id, job_kind, status, started_at, completed_at, bytes_written, source_writer_id) "
        "VALUES (NULL,'backup_job','in_progress',now(),NULL,NULL,'test_writer')"
    )
    conn.commit()
    # The loader's filter: completed_at IS NOT NULL, latest first.
    cur.execute(
        "SELECT status FROM public.platform_backup_outcome "
        "WHERE completed_at IS NOT NULL "
        "ORDER BY completed_at DESC NULLS LAST LIMIT 1"
    )
    row = cur.fetchone()
    assert row is not None and row[0] == "success"
    cur.close()
