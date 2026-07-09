"""020: P21-C1 - Durable Approval Store (additive, public-schema-only)

Revision ID: 020_durable_approval_store
Revises: 019_platform_audit_logs
Create Date: 2026-06-26

P21-C1 implements the accepted P21-A durable approval store contract and P21-B schema
plan as an ADDITIVE, PUBLIC-SCHEMA-ONLY migration. It creates the five durable approval
governance tables and their enum types / indexes / uniqueness constraints, all in the
public schema. No existing product, tenant, payment, auth, or RBAC object is altered.
No tenant schema is migrated (this migration is public-mode only and must never be run
with -x tenant_schema). No runtime P20 storage is switched (that is P21-D). No controlled
action is executed.

Approval is not execution, and durability is not execution. Every created table preserves
execution_allowed = false (default), executed = false (default), execution_gate = 'blocked'
(default), and redaction_applied = true (default) by column default. No permanent DB CHECK
is added that would block a future separately approved execution phase (the column defaults
plus the future adapter invariant hold the line in P21).

Digest-only idempotency: only SHA-256 hex digests (char(64)) are stored; the raw
idempotency key is never persisted. tenant_id is a scoped identifier only and is never a
foreign key into any product business table.

Tables (all schema = 'public'):
  durable_approval_requests         (T1)
  durable_approval_decisions        (T2)  FK -> T1 (RESTRICT), FK -> T3
  durable_approval_audit_events     (T3)  (append-only; no outbound FK)
  durable_approval_idempotency_keys (T4)
  durable_approval_retention_jobs   (T5)  FK -> T1, FK -> T3

Enum types (all in public): durable_approval_state, durable_approval_action_class,
durable_approval_execution_gate, durable_approval_source_status,
durable_approval_validation_status, durable_approval_retention_class,
durable_approval_decision, durable_approval_actor_role, durable_approval_identity_context,
durable_approval_event_type, durable_approval_audit_result, durable_approval_storage_class,
durable_approval_scope_key, durable_approval_job_type, durable_approval_job_status.

Note on action_type: T1.action_type references the P18 controlled-action vocabulary, whose
closed value set is owned by P18 and is not closed inside P21; it is therefore a varchar
reference column, not a P21 enum. This realizes the P21-B plan faithfully (action_type is
the only non-closed identifier column).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '020_durable_approval_store'
down_revision = '019_platform_audit_logs'
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# Enum type definitions (closed value sets from P21-B section 4).
# Created explicitly in the public schema; referenced below with create_type=False
# so Alembic never emits a redundant CREATE TYPE / DROP TYPE during table DDL.
# ---------------------------------------------------------------------------
ENUM_TYPES = [
    ("durable_approval_state", [
        "pending_review", "approved_execution_blocked", "rejected", "expired",
        "cancelled", "superseded", "failed_validation",
    ]),
    ("durable_approval_action_class", ["read", "write", "write_request"]),
    ("durable_approval_execution_gate", ["blocked", "not_authorized"]),
    ("durable_approval_source_status", ["valid", "unknown", "unavailable", "degraded"]),
    ("durable_approval_validation_status", [
        "valid", "source_unknown", "superseded_scope", "stale",
    ]),
    ("durable_approval_retention_class", ["standard", "long", "legal_hold"]),
    ("durable_approval_decision", ["approve", "reject"]),
    ("durable_approval_actor_role", [
        "super_admin", "support_operator", "engineering_operator", "system",
    ]),
    ("durable_approval_identity_context", [
        "identity_only", "tenant_contextual", "tenant_scoped_token", "tenant_admin",
        "system", "unknown",
    ]),
    ("durable_approval_event_type", [
        "approval_opened", "approval_decision_recorded", "approval_quorum_met",
        "approval_rejected", "approval_expired", "approval_cancelled",
        "approval_superseded", "approval_failed_validation", "approval_read",
        "approval_exported", "approval_denied", "approval_purged",
    ]),
    ("durable_approval_audit_result", [
        "success", "denied", "idempotent", "conflict", "expired", "error",
    ]),
    ("durable_approval_storage_class", ["durable", "existing_safe", "memory"]),
    ("durable_approval_scope_key", ["open", "decide"]),
    ("durable_approval_job_type", [
        "retention_purge", "retention_export", "revalidation_sweep",
    ]),
    ("durable_approval_job_status", ["pending", "running", "completed", "failed", "skipped"]),
]

# Terminal approval states (used by the "open request" partial unique index predicate).
_TERMINAL_STATES = (
    "rejected", "expired", "cancelled", "superseded", "failed_validation",
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

    bind = op.get_bind()

    # 2. T1 durable_approval_requests (no outbound FK constraints).
    op.create_table(
        'durable_approval_requests',
        sa.Column('approval_id', postgresql.UUID(as_uuid=True),
                  server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('action_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('action_type', sa.String(255), nullable=False),
        sa.Column('action_class', _enum('durable_approval_action_class'), nullable=False),
        sa.Column('state', _enum('durable_approval_state'), nullable=False),
        sa.Column('maker_actor_id', sa.String(255), nullable=False),
        sa.Column('maker_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('quorum_required', sa.Integer, nullable=False),
        sa.Column('quorum_met', sa.Boolean, nullable=False, server_default=sa.text('false')),
        sa.Column('decision', _enum('durable_approval_decision'), nullable=True),
        sa.Column('reason_redacted', sa.Text, nullable=False),
        sa.Column('metadata_redacted', postgresql.JSONB, nullable=True),
        sa.Column('request_digest', sa.CHAR(64), nullable=False),
        sa.Column('idempotency_key_digest', sa.CHAR(64), nullable=False),
        sa.Column('source_status', _enum('durable_approval_source_status'), nullable=False),
        sa.Column('validation_status', _enum('durable_approval_validation_status'),
                  nullable=False),
        sa.Column('execution_allowed', sa.Boolean, nullable=False,
                  server_default=sa.text('false')),
        sa.Column('execution_gate', _enum('durable_approval_execution_gate'), nullable=False,
                  server_default=sa.text("'blocked'")),
        sa.Column('executed', sa.Boolean, nullable=False, server_default=sa.text('false')),
        sa.Column('redaction_applied', sa.Boolean, nullable=False,
                  server_default=sa.text('true')),
        sa.Column('storage_class', _enum('durable_approval_storage_class'), nullable=False),
        sa.Column('retention_class', _enum('durable_approval_retention_class'),
                  nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('durable_retain_until', sa.DateTime(timezone=True), nullable=False),
        sa.Column('superseded_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('previous_state', _enum('durable_approval_state'), nullable=True),
        sa.Column('last_audit_event_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('correlation_id', sa.String(255), nullable=True),
        sa.Column('store_version', sa.Integer, nullable=False, server_default=sa.text('1')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('approval_id'),
        schema='public',
    )
    op.create_index(
        'uq_requests_active_digest', 'durable_approval_requests', ['request_digest'],
        unique=True, schema='public',
        postgresql_where=sa.text(
            "state IN ('pending_review', 'approved_execution_blocked')"
        ),
    )
    op.create_index(
        'uq_requests_open_action_maker', 'durable_approval_requests',
        ['action_id', 'maker_actor_id'], unique=True, schema='public',
        postgresql_where=sa.text(
            "state NOT IN ('rejected', 'expired', 'cancelled', 'superseded', 'failed_validation')"
        ),
    )
    op.create_index('ix_requests_state', 'durable_approval_requests', ['state'],
                    schema='public')
    op.create_index('ix_requests_tenant_state', 'durable_approval_requests',
                    ['tenant_id', 'state'], schema='public')
    op.create_index('ix_requests_purge_scan', 'durable_approval_requests',
                    ['retention_class', 'durable_retain_until'], schema='public')
    op.create_index(
        'ix_requests_expire_scan', 'durable_approval_requests', ['expires_at'],
        schema='public', postgresql_where=sa.text("state = 'pending_review'"),
    )
    op.create_index('ix_requests_source_val', 'durable_approval_requests',
                    ['source_status', 'validation_status'], schema='public')
    op.create_index('ix_requests_action', 'durable_approval_requests', ['action_id'],
                    schema='public')

    # 3. T3 durable_approval_audit_events (append-only; no outbound FK).
    op.create_table(
        'durable_approval_audit_events',
        sa.Column('event_id', postgresql.UUID(as_uuid=True),
                  server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('approval_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('action_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('actor_id', sa.String(255), nullable=False),
        sa.Column('actor_role', _enum('durable_approval_actor_role'), nullable=False),
        sa.Column('identity_context', _enum('durable_approval_identity_context'),
                  nullable=False),
        sa.Column('event_type', _enum('durable_approval_event_type'), nullable=False),
        sa.Column('decision', _enum('durable_approval_decision'), nullable=True),
        sa.Column('audit_result', _enum('durable_approval_audit_result'), nullable=False),
        sa.Column('previous_status', _enum('durable_approval_state'), nullable=True),
        sa.Column('next_status', _enum('durable_approval_state'), nullable=True),
        sa.Column('reason_redacted', sa.Text, nullable=False),
        sa.Column('metadata_redacted', postgresql.JSONB, nullable=True),
        sa.Column('request_digest', sa.CHAR(64), nullable=True),
        sa.Column('redaction_applied', sa.Boolean, nullable=False,
                  server_default=sa.text('true')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('quorum_required', sa.Integer, nullable=True),
        sa.Column('quorum_met', sa.Boolean, nullable=True),
        sa.Column('source_status', _enum('durable_approval_source_status'), nullable=True),
        sa.Column('validation_status', _enum('durable_approval_validation_status'),
                  nullable=True),
        sa.Column('correlation_id', sa.String(255), nullable=True),
        sa.Column('sequence_no', sa.BigInteger, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('event_id'),
        schema='public',
    )
    op.create_index('uq_audit_approval_seq', 'durable_approval_audit_events',
                    ['approval_id', 'sequence_no'], unique=True, schema='public')
    op.create_index('ix_audit_approval_time', 'durable_approval_audit_events',
                    ['approval_id', 'created_at'], schema='public')
    op.create_index('ix_audit_event_type', 'durable_approval_audit_events', ['event_type'],
                    schema='public')
    op.create_index('ix_audit_actor', 'durable_approval_audit_events', ['actor_id'],
                    schema='public')
    op.create_index('ix_audit_time', 'durable_approval_audit_events', ['created_at'],
                    schema='public')

    # 4. T4 durable_approval_idempotency_keys (digest-only; no outbound FK).
    op.create_table(
        'durable_approval_idempotency_keys',
        sa.Column('idempotency_id', postgresql.UUID(as_uuid=True),
                  server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('scope_key', _enum('durable_approval_scope_key'), nullable=False),
        sa.Column('scope_id', sa.String(512), nullable=False),
        sa.Column('idempotency_key_digest', sa.CHAR(64), nullable=False),
        sa.Column('payload_digest', sa.CHAR(64), nullable=False),
        sa.Column('result_ref', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('first_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('idempotency_id'),
        schema='public',
    )
    op.create_index('uq_idem_scope', 'durable_approval_idempotency_keys',
                    ['scope_key', 'scope_id', 'idempotency_key_digest'], unique=True,
                    schema='public')
    op.create_index('ix_idem_digest', 'durable_approval_idempotency_keys',
                    ['idempotency_key_digest'], schema='public')

    # 5. T2 durable_approval_decisions (FK -> T1 RESTRICT, FK -> T3).
    op.create_table(
        'durable_approval_decisions',
        sa.Column('decision_id', postgresql.UUID(as_uuid=True),
                  server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('approval_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('checker_actor_id', sa.String(255), nullable=False),
        sa.Column('decision', _enum('durable_approval_decision'), nullable=False),
        sa.Column('reason_redacted', sa.Text, nullable=False),
        sa.Column('metadata_redacted', postgresql.JSONB, nullable=True),
        sa.Column('idempotency_key_digest', sa.CHAR(64), nullable=False),
        sa.Column('decision_digest', sa.CHAR(64), nullable=False),
        sa.Column('confirm', sa.Boolean, nullable=False),
        sa.Column('audit_event_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('correlation_id', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('decision_id'),
        sa.ForeignKeyConstraint(
            ['approval_id'],
            ['public.durable_approval_requests.approval_id'],
            ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['audit_event_id'],
            ['public.durable_approval_audit_events.event_id'],
        ),
        schema='public',
    )
    op.create_index('uq_decisions_approval_checker', 'durable_approval_decisions',
                    ['approval_id', 'checker_actor_id'], unique=True, schema='public')
    op.create_index('uq_decisions_approval_idem', 'durable_approval_decisions',
                    ['approval_id', 'idempotency_key_digest'], unique=True, schema='public')
    op.create_index('ix_decisions_approval', 'durable_approval_decisions', ['approval_id'],
                    schema='public')
    op.create_index('ix_decisions_checker', 'durable_approval_decisions', ['checker_actor_id'],
                    schema='public')

    # 6. T5 durable_approval_retention_jobs (FK -> T1, FK -> T3).
    op.create_table(
        'durable_approval_retention_jobs',
        sa.Column('job_id', postgresql.UUID(as_uuid=True),
                  server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('job_type', _enum('durable_approval_job_type'), nullable=False),
        sa.Column('target_approval_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('retention_class', _enum('durable_approval_retention_class'), nullable=True),
        sa.Column('eligible_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('locked_by', sa.String(255), nullable=True),
        sa.Column('locked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', _enum('durable_approval_job_status'), nullable=False,
                  server_default=sa.text("'pending'")),
        sa.Column('audit_event_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('attempts', sa.Integer, nullable=False, server_default=sa.text('0')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('job_id'),
        sa.ForeignKeyConstraint(
            ['target_approval_id'],
            ['public.durable_approval_requests.approval_id'],
        ),
        sa.ForeignKeyConstraint(
            ['audit_event_id'],
            ['public.durable_approval_audit_events.event_id'],
        ),
        schema='public',
    )
    op.create_index(
        'uq_jobs_active_target_type', 'durable_approval_retention_jobs',
        ['target_approval_id', 'job_type'], unique=True, schema='public',
        postgresql_where=sa.text("status IN ('pending', 'running')"),
    )
    op.create_index('ix_jobs_dequeue', 'durable_approval_retention_jobs',
                    ['status', 'eligible_at'], schema='public')
    op.create_index('ix_jobs_retention', 'durable_approval_retention_jobs',
                    ['retention_class'], schema='public')


def downgrade() -> None:
    # Drop tables in reverse dependency order (dependents first), then enum types.
    # op.drop_table removes the table together with its indexes / constraints.
    op.drop_table('durable_approval_retention_jobs', schema='public')
    op.drop_table('durable_approval_decisions', schema='public')
    op.drop_table('durable_approval_idempotency_keys', schema='public')
    op.drop_table('durable_approval_audit_events', schema='public')
    op.drop_table('durable_approval_requests', schema='public')
    for name, _values in reversed(ENUM_TYPES):
        op.execute("DROP TYPE IF EXISTS public.%s" % name)
