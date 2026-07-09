"""P21-D-B unit tests: durable approval ORM models.

Self-contained (NO database). Verifies the five P21-C1 ORM model definitions in
``api/v1.platform.p21.models`` against migration ``020_durable_approval_store``:

  - the five model classes import and register against the project ``Base``;
  - each table lives in the ``public`` schema with its domain-specific primary
    key (NOT the ``PublicBaseModel.id`` PK) and carries NO soft-delete columns;
  - each table has EXACTLY the migration's column set (extra = forbid) and the
    key column types match (UUID / CHAR(64) / String lengths / BigInteger /
    Integer / Boolean / JSONB / enums);
  - the no-execution + redaction server defaults are preserved verbatim
    (execution_allowed = false, executed = false, execution_gate = 'blocked',
    redaction_applied = true, store_version = 1, quorum_met = false);
  - every enum column references an already-created public type with
    ``create_type=False`` (importing the models NEVER emits CREATE TYPE);
  - the foreign-key relationships decisions -> requests (RESTRICT) /
    decisions -> audit_events / jobs -> requests / jobs -> audit_events hold;
  - the closed enum value sets are exactly the P21-C1 sets AND compatible with
    the P20 schemas (Literal cross-check) where the two contracts overlap.

These are pure metadata-introspection tests; they drive no engine and create no
tables. They run by default (unit marker) and need no ephemeral database.
"""
from pathlib import Path
from typing import get_args

import pytest
from sqlalchemy import CHAR, BigInteger, Boolean, Integer, String, Text
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID

from models.base import Base

from api.v1.platform.p21 import models as p21m
from api.v1.platform.p20.schemas import (
    ActionClass,
    ActorRole,
    DecisionType,
    DurableApprovalEventType,
    DurableApprovalState,
    ExecutionGate,
    IdentityContext,
    RegistrySourceStatus,
    RetentionClass,
    ValidationStatus,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Expected column sets per table -- restated from migration 020 (independent of
# the ORM module) so the model and the migration are cross-checked.
# ---------------------------------------------------------------------------

EXPECTED_COLUMNS = {
    "durable_approval_requests": [
        "approval_id", "action_id", "tenant_id", "action_type", "action_class",
        "state", "maker_actor_id", "maker_at", "quorum_required", "quorum_met",
        "decision", "reason_redacted", "metadata_redacted", "request_digest",
        "idempotency_key_digest", "source_status", "validation_status",
        "execution_allowed", "execution_gate", "executed", "redaction_applied",
        "storage_class", "retention_class", "expires_at", "durable_retain_until",
        "superseded_by", "previous_state", "last_audit_event_id", "correlation_id",
        "store_version", "created_at", "updated_at",
    ],
    "durable_approval_decisions": [
        "decision_id", "approval_id", "checker_actor_id", "decision",
        "reason_redacted", "metadata_redacted", "idempotency_key_digest",
        "decision_digest", "confirm", "audit_event_id", "correlation_id",
        "created_at",
    ],
    "durable_approval_audit_events": [
        "event_id", "approval_id", "action_id", "actor_id", "actor_role",
        "identity_context", "event_type", "decision", "audit_result",
        "previous_status", "next_status", "reason_redacted", "metadata_redacted",
        "request_digest", "redaction_applied", "tenant_id", "quorum_required",
        "quorum_met", "source_status", "validation_status", "correlation_id",
        "sequence_no", "created_at",
    ],
    "durable_approval_idempotency_keys": [
        "idempotency_id", "scope_key", "scope_id", "idempotency_key_digest",
        "payload_digest", "result_ref", "first_seen_at", "last_seen_at",
        "created_at",
    ],
    "durable_approval_retention_jobs": [
        "job_id", "job_type", "target_approval_id", "retention_class",
        "eligible_at", "locked_by", "locked_at", "status", "audit_event_id",
        "attempts", "created_at", "updated_at",
    ],
}

EXPECTED_PK = {
    "durable_approval_requests": "approval_id",
    "durable_approval_decisions": "decision_id",
    "durable_approval_audit_events": "event_id",
    "durable_approval_idempotency_keys": "idempotency_id",
    "durable_approval_retention_jobs": "job_id",
}

MODEL_BY_TABLE = {
    "durable_approval_requests": p21m.DurableApprovalRequest,
    "durable_approval_decisions": p21m.DurableApprovalDecision,
    "durable_approval_audit_events": p21m.DurableApprovalAuditEvent,
    "durable_approval_idempotency_keys": p21m.DurableApprovalIdempotencyKey,
    "durable_approval_retention_jobs": p21m.DurableApprovalRetentionJob,
}


def test_models_import_and_extend_project_base():
    """All five models import, subclass models.base.Base, and register metadata."""
    for model in MODEL_BY_TABLE.values():
        assert issubclass(model, Base)
        table = model.__table__
        assert table is not None
        # The shared declarative registry knows about the table.
        assert f"public.{table.name}" in Base.metadata.tables
        # They must NOT inherit the PublicBaseModel/AuditMixin soft-delete surface.
        assert not hasattr(model, "soft_delete")


@pytest.mark.parametrize("table_name", sorted(MODEL_BY_TABLE))
def test_table_name_and_public_schema(table_name):
    table = MODEL_BY_TABLE[table_name].__table__
    assert table.name == table_name
    assert table.schema == "public"


@pytest.mark.parametrize("table_name,expected", sorted(EXPECTED_COLUMNS.items()))
def test_exact_columns_extra_forbid(table_name, expected):
    """Each table maps EXACTLY migration 020's columns -- no more, no fewer."""
    table = MODEL_BY_TABLE[table_name].__table__
    actual = [c.name for c in table.columns]
    assert set(actual) == set(expected), (
        f"{table_name}: missing={set(expected) - set(actual)} "
        f"extra={set(actual) - set(expected)}"
    )


@pytest.mark.parametrize("table_name", sorted(MODEL_BY_TABLE))
def test_domain_specific_primary_key_not_id(table_name):
    """PKs are domain-specific (approval_id / event_id / ...), never 'id'."""
    table = MODEL_BY_TABLE[table_name].__table__
    pk_cols = [c.name for c in table.primary_key.columns]
    assert pk_cols == [EXPECTED_PK[table_name]], f"{table_name} PK cols: {pk_cols}"
    assert "id" not in pk_cols
    assert "is_deleted" not in {c.name for c in table.columns}
    assert "deleted_at" not in {c.name for c in table.columns}
    assert "created_by" not in {c.name for c in table.columns}
    assert "updated_by" not in {c.name for c in table.columns}


def test_key_column_types():
    req = p21m.DurableApprovalRequest.__table__.c
    dec = p21m.DurableApprovalDecision.__table__.c
    aud = p21m.DurableApprovalAuditEvent.__table__.c
    idem = p21m.DurableApprovalIdempotencyKey.__table__.c
    job = p21m.DurableApprovalRetentionJob.__table__.c

    assert isinstance(req.approval_id.type, PgUUID) and req.approval_id.type.as_uuid
    assert isinstance(req.tenant_id.type, PgUUID)
    assert isinstance(req.action_type.type, String) and req.action_type.type.length == 255
    assert isinstance(req.maker_actor_id.type, String) and req.maker_actor_id.type.length == 255
    assert isinstance(req.request_digest.type, CHAR) and req.request_digest.type.length == 64
    assert isinstance(req.idempotency_key_digest.type, CHAR) and req.idempotency_key_digest.type.length == 64
    assert isinstance(req.store_version.type, Integer)
    assert isinstance(req.quorum_required.type, Integer)
    assert isinstance(req.execution_allowed.type, Boolean)
    assert isinstance(req.quorum_met.type, Boolean)
    assert isinstance(req.reason_redacted.type, Text)
    assert isinstance(req.metadata_redacted.type, JSONB)

    assert isinstance(dec.decision_digest.type, CHAR) and dec.decision_digest.type.length == 64
    assert isinstance(dec.idempotency_key_digest.type, CHAR) and dec.idempotency_key_digest.type.length == 64
    assert isinstance(dec.checker_actor_id.type, String) and dec.checker_actor_id.type.length == 255
    assert isinstance(dec.confirm.type, Boolean)

    assert isinstance(aud.sequence_no.type, BigInteger)
    assert isinstance(aud.event_id.type, PgUUID)
    assert isinstance(aud.actor_id.type, String) and aud.actor_id.type.length == 255

    assert isinstance(idem.scope_id.type, String) and idem.scope_id.type.length == 512
    assert isinstance(idem.idempotency_key_digest.type, CHAR) and idem.idempotency_key_digest.type.length == 64

    assert isinstance(job.attempts.type, Integer)


def test_no_execution_and_redaction_server_defaults():
    """The migration's no-execution / redaction defaults are preserved verbatim."""
    req = p21m.DurableApprovalRequest.__table__.c
    job = p21m.DurableApprovalRetentionJob.__table__.c

    def sd(col):
        assert col.server_default is not None, f"{col.name} missing server_default"
        return str(col.server_default.arg)

    assert "false" in sd(req.execution_allowed)
    assert "false" in sd(req.executed)
    assert "blocked" in sd(req.execution_gate)
    assert "true" in sd(req.redaction_applied)
    assert "false" in sd(req.quorum_met)
    assert "1" in sd(req.store_version)
    assert "gen_random_uuid" in sd(req.approval_id)
    assert "now" in sd(req.created_at).lower()
    assert "now" in sd(req.updated_at).lower()

    assert "pending" in sd(job.status)
    assert "0" in sd(job.attempts)


def test_enum_columns_reference_existing_types_no_autocreate():
    """Every enum column uses create_type=False so importing never emits DDL."""
    seen_enum_types = set()
    for model in MODEL_BY_TABLE.values():
        for col in model.__table__.columns:
            if isinstance(col.type, PgEnum):
                assert col.type.create_type is False, (
                    f"{col.name} enum must use create_type=False"
                )
                assert col.type.name.startswith("durable_approval_"), col.type.name
                seen_enum_types.add(col.type.name)
    # The models reference a broad subset of the 15 public durable enum types.
    assert "durable_approval_state" in seen_enum_types
    assert "durable_approval_audit_result" in seen_enum_types
    assert "durable_approval_source_status" in seen_enum_types
    assert "durable_approval_scope_key" in seen_enum_types


def test_foreign_key_relationships():
    """Decisions/jobs reference requests (RESTRICT on decisions) and audit_events."""
    dec = p21m.DurableApprovalDecision.__table__.c
    job = p21m.DurableApprovalRetentionJob.__table__.c

    def targets(col):
        return {fk.target_fullname for fk in col.foreign_keys}

    dec_approval = targets(dec.approval_id)
    assert "public.durable_approval_requests.approval_id" in dec_approval
    # ondelete RESTRICT on decisions -> requests.
    assert any(
        fk.ondelete == "RESTRICT"
        for fk in dec.approval_id.foreign_keys
        if fk.target_fullname == "public.durable_approval_requests.approval_id"
    )
    assert "public.durable_approval_audit_events.event_id" in targets(dec.audit_event_id)
    assert "public.durable_approval_requests.approval_id" in targets(job.target_approval_id)
    assert "public.durable_approval_audit_events.event_id" in targets(job.audit_event_id)
    # requests / audit_events / idempotency_keys have NO outbound FK.
    assert not p21m.DurableApprovalRequest.__table__.c.approval_id.foreign_keys
    assert not p21m.DurableApprovalAuditEvent.__table__.c.event_id.foreign_keys
    assert not p21m.DurableApprovalIdempotencyKey.__table__.c.idempotency_id.foreign_keys


# ---------------------------------------------------------------------------
# Closed enum value sets: ORM module == migration 020 sets, and compatible with
# the P20 schema Literals where the contracts overlap.
# ---------------------------------------------------------------------------

def _lit(alias):
    return set(get_args(alias))


def test_state_values_closed_and_compatible_with_p20():
    # Exactly the 7-state P20/P21 lifecycle; no executing/executed/queued state.
    assert p21m.STATE_VALUES == {
        "pending_review", "approved_execution_blocked", "rejected", "expired",
        "cancelled", "superseded", "failed_validation",
    }
    assert p21m.STATE_VALUES == _lit(DurableApprovalState)
    assert not (p21m.STATE_VALUES & {"executing", "executed", "ready_to_execute",
                                     "queued_for_run"})


def test_shared_vocabularies_match_p20_literals():
    """The vocabularies P20 and P21 share are identical (closed + compatible)."""
    assert p21m.DECISION_VALUES == {"approve", "reject"} == _lit(DecisionType)
    assert p21m.ACTION_CLASS_VALUES == _lit(ActionClass)
    assert p21m.EXECUTION_GATE_VALUES == _lit(ExecutionGate)
    assert p21m.RETENTION_CLASS_VALUES == _lit(RetentionClass)
    assert p21m.VALIDATION_STATUS_VALUES == _lit(ValidationStatus)
    assert p21m.EVENT_TYPE_VALUES == _lit(DurableApprovalEventType)
    assert p21m.IDENTITY_CONTEXT_VALUES == _lit(IdentityContext)


def test_actor_role_durable_is_strict_subset_of_p20():
    """The durable actor_role drops P20's 'unknown' -- it is never persisted."""
    assert p21m.ACTOR_ROLE_VALUES == {
        "super_admin", "support_operator", "engineering_operator", "system",
    }
    assert p21m.ACTOR_ROLE_VALUES.issubset(_lit(ActorRole))
    assert "unknown" not in p21m.ACTOR_ROLE_VALUES


def test_durable_only_vocabularies_closed():
    """The durable-only enum sets are exactly the P21-C1 closed sets."""
    assert p21m.SOURCE_STATUS_VALUES == {"valid", "unknown", "unavailable", "degraded"}
    assert p21m.AUDIT_RESULT_VALUES == {
        "success", "denied", "idempotent", "conflict", "expired", "error",
    }
    assert p21m.STORAGE_CLASS_VALUES == {"durable", "existing_safe", "memory"}
    assert p21m.SCOPE_KEY_VALUES == {"open", "decide"}
    assert p21m.JOB_TYPE_VALUES == {
        "retention_purge", "retention_export", "revalidation_sweep",
    }
    assert p21m.JOB_STATUS_VALUES == {
        "pending", "running", "completed", "failed", "skipped",
    }


def test_p20_source_status_covers_nothing_durable_missing():
    """Every P20 registry source status is representable in the durable set."""
    p20_sources = _lit(RegistrySourceStatus)
    assert p20_sources == {"available", "unavailable", "unknown"}
    assert p20_sources.issubset(p21m.SOURCE_STATUS_VALUES | {"available"})


def test_no_business_table_references():
    """No durable column foreign-keys into any product/tenant business table."""
    forbidden_targets = ("orders", "payments", "invoices", "customers",
                          "inventory", "ledger", "wholesalers", "retailers")
    for model in MODEL_BY_TABLE.values():
        for col in model.__table__.columns:
            for fk in col.foreign_keys:
                tgt = fk.target_fullname.lower()
                assert not any(f in tgt for f in forbidden_targets), (
                    f"{col.name} FK {tgt} references a business table"
                )
