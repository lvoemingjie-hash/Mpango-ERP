"""
P21-C1 G1: Durable Approval Store schema tests (real ephemeral PostgreSQL).

Group G1 from the accepted P21-B plan (section 9). Verifies the exact schema created by
migration 020_durable_approval_store against the real migrated database:
  - each of the five durable tables has EXACTLY its declared columns (extra = forbid);
  - key column types / nullability / defaults are correct;
  - the no-execution defaults hold (execution_allowed = false, executed = false,
    execution_gate = 'blocked') and redaction_applied = true by default;
  - every planned index and unique constraint exists in the public schema;
  - every durable enum type exists in public with its exact closed value set.

These tests drive Alembic and inspect the live schema with psycopg2. They run ONLY against
an explicit ephemeral database (TEST_DATABASE_URL / DATABASE_URL) and REFUSE to run against
the developer mpango_erp database or any unset/shared target. Public mode only: no command
passes -x tenant_schema. A session bootstrap fixture applies the test-only DB prerequisites
(pgcrypto, widened public.alembic_version, t_dev) so the tests reproduce from a clean
throwaway container with only the DB URL set -- no manual SQL required.
"""
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[1]
BASE_REV = "019_platform_audit_logs"
PUBLIC = "public"


# ---------------------------------------------------------------------------
# Ephemeral-DB guard. Never run against shared / production / developer DBs.
# ---------------------------------------------------------------------------
def _ephemeral_url():
    u = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not u:
        pytest.skip("no TEST_DATABASE_URL/DATABASE_URL set; refusing without an explicit ephemeral DB")
    if "mpango_erp" in u.lower():
        pytest.skip("refusing to run against the developer mpango_erp database; point TEST_DATABASE_URL at an ephemeral DB")
    return u


def _psql(url):
    # psycopg2 uses the postgresql:// (sync) form; env.py / alembic rewrite to asyncpg.
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
def db(_boot):
    """Bootstrap the ephemeral DB, upgrade to head, and yield a sync connection."""
    import psycopg2  # noqa: delayed import so module collection never needs a live DB
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(cfg, "head")

    conn = psycopg2.connect(_psql(_boot))
    try:
        yield conn
    finally:
        conn.close()


def _fetchall(cur, sql, params=None):
    cur.execute(sql, params or ())
    return cur.fetchall()


# ---------------------------------------------------------------------------
# Expected columns per table (exact set; extra = forbid). Names from P21-B section 3.
# ---------------------------------------------------------------------------
EXPECTED_COLUMNS = {
    "durable_approval_requests": [
        "approval_id", "action_id", "tenant_id", "action_type", "action_class", "state",
        "maker_actor_id", "maker_at", "quorum_required", "quorum_met", "decision",
        "reason_redacted", "metadata_redacted", "request_digest", "idempotency_key_digest",
        "source_status", "validation_status", "execution_allowed", "execution_gate",
        "executed", "redaction_applied", "storage_class", "retention_class", "expires_at",
        "durable_retain_until", "superseded_by", "previous_state", "last_audit_event_id",
        "correlation_id", "store_version", "created_at", "updated_at",
    ],
    "durable_approval_decisions": [
        "decision_id", "approval_id", "checker_actor_id", "decision", "reason_redacted",
        "metadata_redacted", "idempotency_key_digest", "decision_digest", "confirm",
        "audit_event_id", "correlation_id", "created_at",
    ],
    "durable_approval_audit_events": [
        "event_id", "approval_id", "action_id", "actor_id", "actor_role",
        "identity_context", "event_type", "decision", "audit_result", "previous_status",
        "next_status", "reason_redacted", "metadata_redacted", "request_digest",
        "redaction_applied", "tenant_id", "quorum_required", "quorum_met", "source_status",
        "validation_status", "correlation_id", "sequence_no", "created_at",
    ],
    "durable_approval_idempotency_keys": [
        "idempotency_id", "scope_key", "scope_id", "idempotency_key_digest",
        "payload_digest", "result_ref", "first_seen_at", "last_seen_at", "created_at",
    ],
    "durable_approval_retention_jobs": [
        "job_id", "job_type", "target_approval_id", "retention_class", "eligible_at",
        "locked_by", "locked_at", "status", "audit_event_id", "attempts", "created_at",
        "updated_at",
    ],
}

EXPECTED_INDEXES = {
    "durable_approval_requests": [
        "uq_requests_active_digest", "uq_requests_open_action_maker", "ix_requests_state",
        "ix_requests_tenant_state", "ix_requests_purge_scan", "ix_requests_expire_scan",
        "ix_requests_source_val", "ix_requests_action",
    ],
    "durable_approval_decisions": [
        "uq_decisions_approval_checker", "uq_decisions_approval_idem",
        "ix_decisions_approval", "ix_decisions_checker",
    ],
    "durable_approval_audit_events": [
        "uq_audit_approval_seq", "ix_audit_approval_time", "ix_audit_event_type",
        "ix_audit_actor", "ix_audit_time",
    ],
    "durable_approval_idempotency_keys": ["uq_idem_scope", "ix_idem_digest"],
    "durable_approval_retention_jobs": [
        "uq_jobs_active_target_type", "ix_jobs_dequeue", "ix_jobs_retention",
    ],
}

# (table, column) -> substring that must appear in the column DEFAULT expression.
EXPECTED_DEFAULTS = {
    ("durable_approval_requests", "execution_allowed"): "false",
    ("durable_approval_requests", "executed"): "false",
    ("durable_approval_requests", "execution_gate"): "blocked",
    ("durable_approval_requests", "redaction_applied"): "true",
    ("durable_approval_requests", "quorum_met"): "false",
    ("durable_approval_requests", "store_version"): "1",
    ("durable_approval_audit_events", "redaction_applied"): "true",
    ("durable_approval_retention_jobs", "status"): "pending",
    ("durable_approval_retention_jobs", "attempts"): "0",
}

# (table, column) -> (data_type, char_length or None, udt_name or None).
# 'USER-DEFINED' covers uuid / jsonb / native enums; udt_name disambiguates them.
EXPECTED_TYPES = {
    ("durable_approval_requests", "approval_id"): ("uuid", None, None),
    ("durable_approval_requests", "tenant_id"): ("uuid", None, None),
    ("durable_approval_requests", "action_type"): ("character varying", 255, None),
    ("durable_approval_requests", "action_class"): ("USER-DEFINED", None, "durable_approval_action_class"),
    ("durable_approval_requests", "state"): ("USER-DEFINED", None, "durable_approval_state"),
    ("durable_approval_requests", "execution_gate"): ("USER-DEFINED", None, "durable_approval_execution_gate"),
    ("durable_approval_requests", "request_digest"): ("character", 64, None),
    ("durable_approval_requests", "idempotency_key_digest"): ("character", 64, None),
    ("durable_approval_requests", "store_version"): ("integer", None, None),
    ("durable_approval_requests", "execution_allowed"): ("boolean", None, None),
    ("durable_approval_decisions", "decision_digest"): ("character", 64, None),
    ("durable_approval_decisions", "approval_id"): ("uuid", None, None),
    ("durable_approval_audit_events", "sequence_no"): ("bigint", None, None),
    ("durable_approval_audit_events", "request_digest"): ("character", 64, None),
    ("durable_approval_idempotency_keys", "idempotency_key_digest"): ("character", 64, None),
    ("durable_approval_idempotency_keys", "payload_digest"): ("character", 64, None),
    ("durable_approval_retention_jobs", "attempts"): ("integer", None, None),
}

EXPECTED_ENUM_VALUES = {
    "durable_approval_state": [
        "pending_review", "approved_execution_blocked", "rejected", "expired", "cancelled",
        "superseded", "failed_validation",
    ],
    "durable_approval_action_class": ["read", "write", "write_request"],
    "durable_approval_execution_gate": ["blocked", "not_authorized"],
    "durable_approval_source_status": ["valid", "unknown", "unavailable", "degraded"],
    "durable_approval_validation_status": ["valid", "source_unknown", "superseded_scope", "stale"],
    "durable_approval_retention_class": ["standard", "long", "legal_hold"],
    "durable_approval_decision": ["approve", "reject"],
    "durable_approval_event_type": [
        "approval_opened", "approval_decision_recorded", "approval_quorum_met",
        "approval_rejected", "approval_expired", "approval_cancelled",
        "approval_superseded", "approval_failed_validation", "approval_read",
        "approval_exported", "approval_denied", "approval_purged",
    ],
    "durable_approval_audit_result": ["success", "denied", "idempotent", "conflict", "expired", "error"],
    "durable_approval_actor_role": ["super_admin", "support_operator", "engineering_operator", "system"],
    "durable_approval_identity_context": [
        "identity_only", "tenant_contextual", "tenant_scoped_token", "tenant_admin", "system", "unknown",
    ],
    "durable_approval_storage_class": ["durable", "existing_safe", "memory"],
    "durable_approval_scope_key": ["open", "decide"],
    "durable_approval_job_type": ["retention_purge", "retention_export", "revalidation_sweep"],
    "durable_approval_job_status": ["pending", "running", "completed", "failed", "skipped"],
}


def _columns(cur, table):
    return _fetchall(cur, """
        SELECT column_name, data_type, character_maximum_length, udt_name, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s
        ORDER BY ordinal_position
    """, (PUBLIC, table))


def test_tables_exist_in_public(db):
    cur = db.cursor()
    rows = _fetchall(cur, """
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = %s AND table_name LIKE 'durable_approval_%%'
    """, (PUBLIC,))
    found = {r[0] for r in rows}
    assert found == set(EXPECTED_COLUMNS.keys())


@pytest.mark.parametrize("table,expected", sorted(EXPECTED_COLUMNS.items()))
def test_exact_columns_extra_forbid(db, table, expected):
    """Each table has exactly its declared columns -- no more, no fewer (extra = forbid)."""
    cur = db.cursor()
    actual = [r[0] for r in _columns(cur, table)]
    assert set(actual) == set(expected), (
        f"{table}: missing={set(expected) - set(actual)} extra={set(actual) - set(expected)}"
    )


def test_key_types(db):
    cur = db.cursor()
    # Gather columns for all durable tables once.
    cols = {}
    for table in EXPECTED_COLUMNS:
        for col_name, dt, clen, udt, nullable, default in _columns(cur, table):
            cols[(table, col_name)] = (dt, clen, udt, nullable, default)
    for (table, col), (exp_dt, exp_len, exp_udt) in EXPECTED_TYPES.items():
        dt, clen, udt, _, _ = cols[(table, col)]
        assert dt == exp_dt, f"{table}.{col}: data_type {dt!r} != {exp_dt!r}"
        if exp_len is not None:
            assert clen == exp_len, f"{table}.{col}: length {clen!r} != {exp_len!r}"
        if exp_udt is not None:
            assert udt == exp_udt, f"{table}.{col}: udt {udt!r} != {exp_udt!r}"


def test_no_execution_and_redaction_defaults(db):
    """No-execution defaults: execution_allowed=false, executed=false, gate=blocked; redaction=true."""
    cur = db.cursor()
    cols = {}
    for table in EXPECTED_COLUMNS:
        for col_name, dt, clen, udt, nullable, default in _columns(cur, table):
            cols[(table, col_name)] = (dt, clen, udt, nullable, default)
    for (table, col), needle in EXPECTED_DEFAULTS.items():
        _, _, _, _, default = cols[(table, col)]
        assert default is not None and needle in default, (
            f"{table}.{col}: default {default!r} does not contain {needle!r}"
        )
    # execution_allowed / executed must be NOT NULL (cannot be unset).
    assert cols[("durable_approval_requests", "execution_allowed")][3] == "NO"
    assert cols[("durable_approval_requests", "executed")][3] == "NO"
    assert cols[("durable_approval_requests", "execution_gate")][3] == "NO"


@pytest.mark.parametrize("table,expected", sorted(EXPECTED_INDEXES.items()))
def test_indexes_exist_in_public(db, table, expected):
    cur = db.cursor()
    rows = _fetchall(cur, """
        SELECT indexname FROM pg_indexes WHERE schemaname = %s AND tablename = %s
    """, (PUBLIC, table))
    found = {r[0] for r in rows}
    missing = set(expected) - found
    assert not missing, f"{table}: missing indexes {missing}"


def test_unique_indexes_present(db):
    """The maker-checker / idempotency / sequencing uniqueness constraints exist."""
    cur = db.cursor()
    rows = _fetchall(cur, """
        SELECT indexname FROM pg_indexes
        WHERE schemaname = %s AND indexname IN (
            'uq_requests_active_digest','uq_requests_open_action_maker',
            'uq_decisions_approval_checker','uq_decisions_approval_idem',
            'uq_audit_approval_seq','uq_idem_scope','uq_jobs_active_target_type'
        )
    """, (PUBLIC,))
    found = {r[0] for r in rows}
    expected = {
        "uq_requests_active_digest", "uq_requests_open_action_maker",
        "uq_decisions_approval_checker", "uq_decisions_approval_idem",
        "uq_audit_approval_seq", "uq_idem_scope", "uq_jobs_active_target_type",
    }
    assert found == expected, f"missing unique indexes: {expected - found}"


def test_decision_foreign_keys(db):
    """Decisions reference requests (RESTRICT) and audit_events; jobs reference both."""
    cur = db.cursor()
    rows = _fetchall(cur, """
        SELECT child.relname, parent.relname, c.confdeltype
        FROM pg_constraint c
        JOIN pg_class child ON c.conrelid = child.oid
        JOIN pg_class parent ON c.confrelid = parent.oid
        JOIN pg_namespace cn ON child.relnamespace = cn.oid
        WHERE c.contype = 'f' AND cn.nspname = %s
          AND (child.relname LIKE 'durable_approval_%%' OR parent.relname LIKE 'durable_approval_%%')
    """, (PUBLIC,))
    pairs = {(r[0], r[1], r[2]) for r in rows}  # (child, parent, deltype); 'r'=RESTRICT, 'a'=NO ACTION
    assert any(c == "durable_approval_decisions" and p == "durable_approval_requests"
               and d in ("r", "a") for c, p, d in pairs), \
        f"decisions->requests FK missing: {pairs}"
    assert any(c == "durable_approval_decisions" and p == "durable_approval_audit_events"
               for c, p, _ in pairs), f"decisions->audit FK missing: {pairs}"
    assert any(c == "durable_approval_retention_jobs" and p == "durable_approval_requests"
               for c, p, _ in pairs), f"jobs->requests FK missing: {pairs}"
    assert any(c == "durable_approval_retention_jobs" and p == "durable_approval_audit_events"
               for c, p, _ in pairs), f"jobs->audit FK missing: {pairs}"


@pytest.mark.parametrize("name,expected", sorted(EXPECTED_ENUM_VALUES.items()))
def test_enum_value_sets(db, name, expected):
    cur = db.cursor()
    rows = _fetchall(cur, """
        SELECT e.enumlabel FROM pg_enum e
        JOIN pg_type t ON e.enumtypid = t.oid
        JOIN pg_namespace n ON t.typnamespace = n.oid
        WHERE n.nspname = %s AND t.typname = %s
        ORDER BY e.enumsortorder
    """, (PUBLIC, name))
    actual = [r[0] for r in rows]
    assert actual == expected, f"{name}: {actual} != {expected}"


def test_enum_types_live_in_public(db):
    cur = db.cursor()
    rows = _fetchall(cur, """
        SELECT t.typname FROM pg_type t JOIN pg_namespace n ON t.typnamespace = n.oid
        WHERE n.nspname = %s AND t.typtype = 'e' AND t.typname LIKE 'durable_approval_%%'
    """, (PUBLIC,))
    found = {r[0] for r in rows}
    assert found == set(EXPECTED_ENUM_VALUES.keys()), f"enum types not all in public: {set(EXPECTED_ENUM_VALUES) - found}"
