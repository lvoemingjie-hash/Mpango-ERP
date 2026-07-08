"""P21-C1 durable approval store -- SQLAlchemy ORM models (P21-D-B substrate).

Read/write ORM mapping for the five public durable approval tables created by
migration ``029_durable_approval_store`` (P21-C1): ``durable_approval_requests``,
``durable_approval_decisions``, ``durable_approval_audit_events``,
``durable_approval_idempotency_keys``, and ``durable_approval_retention_jobs``,
all in the ``public`` schema.

These models are a faithful, column-for-column mapping of migration 020. They
exist so a future P21-D-1 adapter can read/write the durable tables through the
ORM. They are NOT yet registered in ``models/__init__.py`` (so they do not enter
the shared ``Base.metadata`` used by Alembic autogenerate or by
``onboard_tenant``'s ``metadata.create_all``); registration is deferred to the
separately CTO-gated P21-D-1 runtime slice, exactly as the P21-D design lock
layers it (P21-D-a is docs-only; P21-D-1 is model registration + adapter
implementation). Importing this module therefore has no migration, autogenerate,
or runtime-storage side effect.

Design choices (documented for the ledger):
  - The models extend ``models.base.Base`` (the project's shared DeclarativeBase)
    directly, NOT ``PublicBaseModel``. ``PublicBaseModel`` injects a hard-coded
    ``id`` primary key plus, via ``AuditMixin``, ``is_deleted`` / ``deleted_at``
    soft-delete columns. The durable tables have domain-specific primary keys
    (``approval_id`` / ``event_id`` / ``decision_id`` / ``idempotency_id`` /
    ``job_id``) and carry NO soft-delete columns, so ``PublicBaseModel`` cannot
    be reused without producing incorrect column mappings and Alembic drift.
  - Every column matches migration 020 exactly (name, type, nullability, and the
    no-execution / redaction server defaults). ``created_at`` / ``updated_at``
    mirror the migration (``server_default = now()``) and intentionally do NOT
    carry ``AuditMixin``'s ``onupdate``.
  - Enum columns reference the already-created public enum types with
    ``postgresql.ENUM(create_type=False)`` -- identical to the migration -- so
    SQLAlchemy NEVER emits CREATE TYPE / DROP TYPE for them.
  - Index and unique-constraint DDL is intentionally NOT redeclared here. Index /
    constraint ownership stays with migration 020 (the source of truth); the ORM
    layer is a read/write column mapping only, which avoids duplicated,
    drift-prone index definitions. (Foreign-key constraints ARE declared, since
    they are structural relationships the ORM mapping should carry.)

The closed enum value sets are mirrored below as module-level ``frozenset``
constants. They are the ORM layer's declaration of the closed vocabularies and
are cross-checked against migration 020 and the P20 schemas in
``tests/test_platform_p21_durable_approval_models.py``.

Approval is not execution, and durability is not execution. The no-execution
defaults (``execution_allowed = false``, ``executed = false``,
``execution_gate = 'blocked'``) and ``redaction_applied = true`` are preserved
verbatim from the migration.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CHAR,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


# ---------------------------------------------------------------------------
# Public enum type references (already created by migration 020). create_type
# = False guarantees SQLAlchemy never tries to CREATE / DROP these types.
# ---------------------------------------------------------------------------


def _enum(name: str) -> ENUM:
    """Reference an already-created public durable approval enum type.

    Mirrors migration 020's ``_enum`` helper: the type is referenced by name with
    ``create_type=False`` so importing this module never emits DDL. The closed
    value symbols (``_ENUM_VALUE_MAP``) are supplied so SQLAlchemy can decode rows
    on read (a postgresql.ENUM created with create_type=False and no symbols
    otherwise raises LookupError at row-load time). This is a Python-side decode
    detail only; it emits no DDL and does not alter any column / type / migration.
    """
    return ENUM(*_ENUM_VALUE_MAP.get(name, ()), name=name, create_type=False)


# ---------------------------------------------------------------------------
# Closed enum value sets (single source of truth for the ORM layer; mirrored
# from migration 020 ENUM_TYPES and cross-checked against the P20 schemas).
# ---------------------------------------------------------------------------

STATE_VALUES = frozenset(
    (
        "pending_review",
        "approved_execution_blocked",
        "rejected",
        "expired",
        "cancelled",
        "superseded",
        "failed_validation",
    )
)
ACTION_CLASS_VALUES = frozenset(("read", "write", "write_request"))
EXECUTION_GATE_VALUES = frozenset(("blocked", "not_authorized"))
SOURCE_STATUS_VALUES = frozenset(("valid", "unknown", "unavailable", "degraded"))
VALIDATION_STATUS_VALUES = frozenset(
    ("valid", "source_unknown", "superseded_scope", "stale")
)
RETENTION_CLASS_VALUES = frozenset(("standard", "long", "legal_hold"))
DECISION_VALUES = frozenset(("approve", "reject"))
ACTOR_ROLE_VALUES = frozenset(
    ("super_admin", "support_operator", "engineering_operator", "system")
)
IDENTITY_CONTEXT_VALUES = frozenset(
    (
        "identity_only",
        "tenant_contextual",
        "tenant_scoped_token",
        "tenant_admin",
        "system",
        "unknown",
    )
)
EVENT_TYPE_VALUES = frozenset(
    (
        "approval_opened",
        "approval_decision_recorded",
        "approval_quorum_met",
        "approval_rejected",
        "approval_expired",
        "approval_cancelled",
        "approval_superseded",
        "approval_failed_validation",
        "approval_read",
        "approval_exported",
        "approval_denied",
        "approval_purged",
    )
)
AUDIT_RESULT_VALUES = frozenset(
    ("success", "denied", "idempotent", "conflict", "expired", "error")
)
STORAGE_CLASS_VALUES = frozenset(("durable", "existing_safe", "memory"))
SCOPE_KEY_VALUES = frozenset(("open", "decide"))
JOB_TYPE_VALUES = frozenset(
    ("retention_purge", "retention_export", "revalidation_sweep")
)
JOB_STATUS_VALUES = frozenset(("pending", "running", "completed", "failed", "skipped"))


# Map each public durable enum TYPE NAME to its closed symbol tuple, so the ORM
# ``_enum`` helper can supply the symbols for Python-side row decode. This only
# affects decode; create_type=False is preserved and no DDL is ever emitted.
_ENUM_VALUE_MAP: dict[str, tuple[str, ...]] = {
    "durable_approval_state": tuple(STATE_VALUES),
    "durable_approval_action_class": tuple(ACTION_CLASS_VALUES),
    "durable_approval_execution_gate": tuple(EXECUTION_GATE_VALUES),
    "durable_approval_source_status": tuple(SOURCE_STATUS_VALUES),
    "durable_approval_validation_status": tuple(VALIDATION_STATUS_VALUES),
    "durable_approval_retention_class": tuple(RETENTION_CLASS_VALUES),
    "durable_approval_decision": tuple(DECISION_VALUES),
    "durable_approval_actor_role": tuple(ACTOR_ROLE_VALUES),
    "durable_approval_identity_context": tuple(IDENTITY_CONTEXT_VALUES),
    "durable_approval_event_type": tuple(EVENT_TYPE_VALUES),
    "durable_approval_audit_result": tuple(AUDIT_RESULT_VALUES),
    "durable_approval_storage_class": tuple(STORAGE_CLASS_VALUES),
    "durable_approval_scope_key": tuple(SCOPE_KEY_VALUES),
    "durable_approval_job_type": tuple(JOB_TYPE_VALUES),
    "durable_approval_job_status": tuple(JOB_STATUS_VALUES),
}


# ---------------------------------------------------------------------------
# T1 durable_approval_requests -- the persisted durable approval record.
# ---------------------------------------------------------------------------


class DurableApprovalRequest(Base):
    """Persisted durable approval record (P20 ``ApprovalRecord``, restart-safe).

    ``approval_id`` is the primary key. ``execution_allowed`` / ``executed`` /
    ``execution_gate`` carry the no-execution defaults; ``redaction_applied`` is
    true; ``store_version`` is the optimistic-lock version (1 at create). No
    outbound foreign key: ``action_id`` references a P18 request logically and
    ``tenant_id`` is a scoped identifier only (never an FK into business tables).
    """

    __tablename__ = "durable_approval_requests"
    __table_args__ = {"schema": "public"}

    approval_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    action_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    tenant_id: Mapped[Optional[UUID]] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    action_type: Mapped[str] = mapped_column(String(255), nullable=False)
    action_class: Mapped[str] = mapped_column(
        _enum("durable_approval_action_class"), nullable=False
    )
    state: Mapped[str] = mapped_column(_enum("durable_approval_state"), nullable=False)
    maker_actor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    maker_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    quorum_required: Mapped[int] = mapped_column(Integer, nullable=False)
    quorum_met: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    decision: Mapped[Optional[str]] = mapped_column(
        _enum("durable_approval_decision"), nullable=True
    )
    reason_redacted: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_redacted: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    request_digest: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    idempotency_key_digest: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    source_status: Mapped[str] = mapped_column(
        _enum("durable_approval_source_status"), nullable=False
    )
    validation_status: Mapped[str] = mapped_column(
        _enum("durable_approval_validation_status"), nullable=False
    )
    execution_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    execution_gate: Mapped[str] = mapped_column(
        _enum("durable_approval_execution_gate"),
        nullable=False,
        server_default=text("'blocked'"),
    )
    executed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    redaction_applied: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    storage_class: Mapped[str] = mapped_column(
        _enum("durable_approval_storage_class"), nullable=False
    )
    retention_class: Mapped[str] = mapped_column(
        _enum("durable_approval_retention_class"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    durable_retain_until: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    superseded_by: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True), nullable=True
    )
    previous_state: Mapped[Optional[str]] = mapped_column(
        _enum("durable_approval_state"), nullable=True
    )
    last_audit_event_id: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True), nullable=True
    )
    correlation_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    store_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# ---------------------------------------------------------------------------
# T3 durable_approval_audit_events -- append-only durable audit log.
# ---------------------------------------------------------------------------


class DurableApprovalAuditEvent(Base):
    """Append-only durable audit event row (P20 audit event, restart-safe).

    No UPDATE path; DELETE only via whole-record retention purge (P21-A 7.3).
    ``sequence_no`` is the monotonic per-approval audit sequence.
    ``audit_result`` carries the durable audit outcome (derived by the adapter).
    No outbound foreign key. ``approval_id`` / ``action_id`` are nullable for
    pre-record / no-action events.
    """

    __tablename__ = "durable_approval_audit_events"
    __table_args__ = {"schema": "public"}

    event_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    approval_id: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True), nullable=True
    )
    action_id: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True), nullable=True
    )
    actor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    actor_role: Mapped[str] = mapped_column(
        _enum("durable_approval_actor_role"), nullable=False
    )
    identity_context: Mapped[str] = mapped_column(
        _enum("durable_approval_identity_context"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(
        _enum("durable_approval_event_type"), nullable=False
    )
    decision: Mapped[Optional[str]] = mapped_column(
        _enum("durable_approval_decision"), nullable=True
    )
    audit_result: Mapped[str] = mapped_column(
        _enum("durable_approval_audit_result"), nullable=False
    )
    previous_status: Mapped[Optional[str]] = mapped_column(
        _enum("durable_approval_state"), nullable=True
    )
    next_status: Mapped[Optional[str]] = mapped_column(
        _enum("durable_approval_state"), nullable=True
    )
    reason_redacted: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_redacted: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    request_digest: Mapped[Optional[str]] = mapped_column(CHAR(64), nullable=True)
    redaction_applied: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    tenant_id: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True), nullable=True
    )
    quorum_required: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    quorum_met: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    source_status: Mapped[Optional[str]] = mapped_column(
        _enum("durable_approval_source_status"), nullable=True
    )
    validation_status: Mapped[Optional[str]] = mapped_column(
        _enum("durable_approval_validation_status"), nullable=True
    )
    correlation_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    sequence_no: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# ---------------------------------------------------------------------------
# T4 durable_approval_idempotency_keys -- digest-only idempotency dedup.
# ---------------------------------------------------------------------------


class DurableApprovalIdempotencyKey(Base):
    """Digest-only idempotency row. The raw idempotency key is never stored.

    ``scope_key`` (open | decide) generalizes P20-B's two dedup maps. Only the
    SHA-256 ``idempotency_key_digest`` and the canonical ``payload_digest`` are
    persisted; a replay returns the prior ``result_ref`` on a payload match and
    is a conflict on a mismatch. No outbound foreign key.
    """

    __tablename__ = "durable_approval_idempotency_keys"
    __table_args__ = {"schema": "public"}

    idempotency_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    scope_key: Mapped[str] = mapped_column(
        _enum("durable_approval_scope_key"), nullable=False
    )
    scope_id: Mapped[str] = mapped_column(String(512), nullable=False)
    idempotency_key_digest: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    payload_digest: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    result_ref: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True), nullable=True
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# ---------------------------------------------------------------------------
# T2 durable_approval_decisions -- each checker decision materialized as a row.
# ---------------------------------------------------------------------------


class DurableApprovalDecision(Base):
    """One checker's recorded decision (the P20 ``checkers`` log, made durable).

    ``checker_actor_id`` MUST differ from the request maker (maker-checker). The
    ``approval_id`` FK is ON DELETE RESTRICT (purge is whole-record, P21-A 7.3).
    ``decision_digest`` drives per-approval decide idempotency.
    """

    __tablename__ = "durable_approval_decisions"
    __table_args__ = {"schema": "public"}

    decision_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    approval_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("public.durable_approval_requests.approval_id", ondelete="RESTRICT"),
        nullable=False,
    )
    checker_actor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    decision: Mapped[str] = mapped_column(
        _enum("durable_approval_decision"), nullable=False
    )
    reason_redacted: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_redacted: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    idempotency_key_digest: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    decision_digest: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    confirm: Mapped[bool] = mapped_column(Boolean, nullable=False)
    audit_event_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("public.durable_approval_audit_events.event_id"),
        nullable=False,
    )
    correlation_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# ---------------------------------------------------------------------------
# T5 durable_approval_retention_jobs -- future SYSTEM-driven retention queue.
# ---------------------------------------------------------------------------


class DurableApprovalRetentionJob(Base):
    """Future retention / purge / revalidation / export job queue row.

    Driven by a SYSTEM actor only; never an operator; never a dispatch of
    execution (P21-A 7, C19). ``status`` defaults to pending; ``attempts`` to 0.
    """

    __tablename__ = "durable_approval_retention_jobs"
    __table_args__ = {"schema": "public"}

    job_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    job_type: Mapped[str] = mapped_column(
        _enum("durable_approval_job_type"), nullable=False
    )
    target_approval_id: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("public.durable_approval_requests.approval_id"),
        nullable=True,
    )
    retention_class: Mapped[Optional[str]] = mapped_column(
        _enum("durable_approval_retention_class"), nullable=True
    )
    eligible_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    locked_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    locked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(
        _enum("durable_approval_job_status"),
        nullable=False,
        server_default=text("'pending'"),
    )
    audit_event_id: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("public.durable_approval_audit_events.event_id"),
        nullable=True,
    )
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


__all__ = [
    # ORM models
    "DurableApprovalRequest",
    "DurableApprovalDecision",
    "DurableApprovalAuditEvent",
    "DurableApprovalIdempotencyKey",
    "DurableApprovalRetentionJob",
    # Closed enum value sets
    "STATE_VALUES",
    "ACTION_CLASS_VALUES",
    "EXECUTION_GATE_VALUES",
    "SOURCE_STATUS_VALUES",
    "VALIDATION_STATUS_VALUES",
    "RETENTION_CLASS_VALUES",
    "DECISION_VALUES",
    "ACTOR_ROLE_VALUES",
    "IDENTITY_CONTEXT_VALUES",
    "EVENT_TYPE_VALUES",
    "AUDIT_RESULT_VALUES",
    "STORAGE_CLASS_VALUES",
    "SCOPE_KEY_VALUES",
    "JOB_TYPE_VALUES",
    "JOB_STATUS_VALUES",
]
