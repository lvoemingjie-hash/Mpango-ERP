"""030: P17-D-C - Backup / Status Source (additive, public-schema-only)

Revision ID: 030_platform_backup_status_source
Revises: 029_durable_approval_store
Create Date: 2026-07-03

P17-D-C implements the accepted P17-D-A backup / status source contract and the
P17-D-B schema + model + test plan as an ADDITIVE, PUBLIC-SCHEMA-ONLY migration.
It creates the two durable backup / status source tables and their enum types /
indexes / uniqueness / CHECK constraints, all in the public schema. No existing
product, tenant, payment, auth, or RBAC object is altered. No tenant schema is
migrated (this migration is public-mode only and must never be run with
-x tenant_schema). No P22 seam / adapter is touched, no backup.check is wired,
and no backup or restore is executed.

Tables (all schema = 'public'):
  platform_backup_outcome  (append-only backup-job / restore-test-job outcomes)
  platform_backup_policy   (optional per-tenant / platform-default config)

Enum types (public):
  platform_backup_job_kind        ('backup_job', 'restore_test_job')
  platform_backup_outcome_status  ('success', 'partial', 'failed', 'in_progress')

Stored status deliberately EXCLUDES 'stale' and 'unknown' -- those are read-time
DERIVATIONS the P17 registry adapter computes (a job cannot "be" stale; only a
rendered status can be stale relative to a freshness window). This separation is
the core honesty mechanism: the table cannot lie that a stale backup is fresh,
because freshness is never stored.

tenant_id is a scoped identifier ONLY -- NEVER a foreign key into any tenant
business table (orders / payments / invoices / customers / inventory / ledgers).
The runtime read path (P17 services.py) only SELECTs outcome rows; mutations are
writer-only (the operational backup process or a recorder it calls). This
migration creates the source tables only; it does NOT add a writer, does NOT
wire backup.check, and does NOT touch P22.

failure_reason_code is text + CHECK (not a Postgres enum) so the closed
vocabulary stays editable in lock-step with the Python BACKUP_FAILURE_REASONS
frozenset (backend/api/v1/platform/p17/schemas.py) without an enum-type
migration; the CHECK and the frozenset MUST stay in sync.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '030_platform_backup_status_source'
down_revision = '029_durable_approval_store'
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# Additive STORED enum types (public schema). Created explicitly and referenced
# below with create_type=False so Alembic never emits a redundant CREATE TYPE /
# DROP TYPE during table DDL. New values are appended in future revisions;
# existing values are not removed or reordered (Postgres ENUM ordering is
# load-bearing).
# ---------------------------------------------------------------------------
ENUM_TYPES = [
    ("platform_backup_job_kind", ["backup_job", "restore_test_job"]),
    ("platform_backup_outcome_status", ["success", "partial", "failed", "in_progress"]),
]

# Closed failure-reason vocabulary mirrored EXACTLY from
# backend/api/v1/platform/p17/schemas.py BACKUP_FAILURE_REASONS. Stored as text
# + CHECK (not an enum) so it tracks the Python allowlist without an enum
# migration; the CHECK and the frozenset MUST stay in sync.
_FAILURE_REASONS = (
    "backup_job_timeout",
    "restore_checksum_mismatch",
    "backup_source_unreachable",
    "restore_test_failed",
    "backup_incomplete",
    "unknown",
)


def _enum(name):
    """Reference an already-created public enum type (no implicit create/drop)."""
    return postgresql.ENUM(name=name, create_type=False)


def upgrade() -> None:
    # 1. Enum types (public schema).
    for name, values in ENUM_TYPES:
        quoted_values = ", ".join("'%s'" % v for v in values)
        op.execute(
            "CREATE TYPE public.%s AS ENUM (%s)" % (name, quoted_values)
        )

    # 2. platform_backup_outcome (append-only outcome rows; no outbound FK).
    #    tenant_id is a scoped identifier, NOT a foreign key.
    op.create_table(
        'platform_backup_outcome',
        sa.Column('outcome_id', postgresql.UUID(as_uuid=True),
                  server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('job_kind', _enum('platform_backup_job_kind'), nullable=False),
        sa.Column('status', _enum('platform_backup_outcome_status'), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('bytes_written', sa.BigInteger, nullable=True),
        sa.Column('failure_reason_code', sa.Text, nullable=True),
        sa.Column('source_writer_id', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('outcome_id'),
        # CHECK constraints encode the honesty invariants at the DB layer
        # (defense in depth under the Python validators / freshness helper).
        sa.CheckConstraint(
            "(status = 'in_progress') = (completed_at IS NULL)",
            name='ck_pbo_completed_iff_not_in_progress',
        ),
        sa.CheckConstraint(
            "(failure_reason_code IS NOT NULL) = (status IN ('failed', 'partial'))",
            name='ck_pbo_failure_reason_scope',
        ),
        sa.CheckConstraint(
            "(bytes_written IS NULL) OR (status IN ('success', 'partial'))",
            name='ck_pbo_bytes_scope',
        ),
        sa.CheckConstraint(
            "(status <> 'success') OR (bytes_written IS NOT NULL AND bytes_written > 0)",
            name='ck_pbo_success_has_bytes',
        ),
        sa.CheckConstraint(
            "failure_reason_code IS NULL OR failure_reason_code IN (%s)"
            % ", ".join("'%s'" % r for r in _FAILURE_REASONS),
            name='ck_pbo_failure_reason_allowlist',
        ),
        schema='public',
    )
    # Recency index: backs the "latest COMPLETED outcome per
    # (tenant|platform-wide) per job_kind" read without a full scan. NULLS LAST
    # keeps in_progress rows (completed_at IS NULL) off the top of a DESC scan.
    # Created via explicit DDL so the DESC NULLS LAST semantics are exact.
    op.execute(
        "CREATE INDEX idx_pbo_tenant_kind_completed "
        "ON public.platform_backup_outcome "
        "(tenant_id, job_kind, completed_at DESC NULLS LAST)"
    )

    # 3. platform_backup_policy (optional admin-managed config; no outbound FK).
    op.create_table(
        'platform_backup_policy',
        sa.Column('policy_id', postgresql.UUID(as_uuid=True),
                  server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('retention_policy', sa.Text, nullable=True),
        sa.Column('export_enabled', sa.Boolean, nullable=True),
        sa.Column('restore_test_cadence_hours', sa.Integer, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('policy_id'),
        schema='public',
    )
    # At most one policy per (non-null) tenant. Postgres UNIQUE treats multiple
    # NULLs as distinct, so this alone cannot enforce a single platform-default
    # row -- the partial unique index below does that.
    op.create_index(
        'uq_pbp_tenant', 'platform_backup_policy', ['tenant_id'],
        unique=True, schema='public',
    )
    # At most one platform-default row (tenant_id IS NULL). Postgres treats NULLs
    # as distinct in unique indexes, so a partial UNIQUE (tenant_id) WHERE
    # tenant_id IS NULL would NOT prevent multiple NULL rows; indexing a constant
    # expression for the NULL rows makes them all collide on a single key. Created
    # via explicit DDL so the constant-expression key is exact.
    op.execute(
        "CREATE UNIQUE INDEX uq_pbp_platform_default "
        "ON public.platform_backup_policy ((1)) WHERE tenant_id IS NULL"
    )


def downgrade() -> None:
    # Drop tables (dependents first; there are no cross-FKs here), then enum
    # types. op.drop_table removes the table together with its indexes /
    # constraints, so no separate index / check drops are needed. Because both
    # tables are additive and hold only platform-operational data, downgrade
    # loses no tenant or business data.
    op.drop_table('platform_backup_policy', schema='public')
    op.drop_table('platform_backup_outcome', schema='public')
    for name, _values in reversed(ENUM_TYPES):
        op.execute("DROP TYPE IF EXISTS public.%s" % name)
