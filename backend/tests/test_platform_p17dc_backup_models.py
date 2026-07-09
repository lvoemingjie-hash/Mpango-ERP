"""P17-D-C unit tests: backup / status source ORM models.

Self-contained (NO database). Verifies the two P17-D-C ORM model definitions in
``api.v1.platform.p17.models`` against migration ``021_platform_backup_status_source``:

  - both model classes import and register against the project ``Base``;
  - each table lives in the ``public`` schema with its domain-specific primary
    key (``outcome_id`` / ``policy_id``, NOT the ``PublicBaseModel.id`` PK) and
    carries NO soft-delete columns;
  - each table has EXACTLY the migration's column set (extra = forbid) and the
    key column types match (UUID / BigInteger / Integer / Boolean / Text /
    DateTime);
  - the gen_random_uuid() / now() server defaults are preserved verbatim;
  - every enum column references an already-created public type with
    ``create_type=False`` AND supplies the closed value symbols (so rows decode
    on read -- the P21 ORM-enum lesson), and importing the models NEVER emits
    CREATE TYPE;
  - no column foreign-keys into any tenant business table (tenant_id is a scoped
    identifier only);
  - the closed enum / vocabulary sets are exactly the migration sets AND
    compatible with the P17 schemas (``OUTCOME_STATUS_VALUES`` is the stored
    subset of ``LastBackupStatus`` that excludes the derived ``stale`` /
    ``unknown``; ``FAILURE_REASON_VALUES`` == ``BACKUP_FAILURE_REASONS``).

These are pure metadata-introspection tests; they drive no engine and create no
tables. They run by default (unit marker) and need no ephemeral database.
"""
from typing import get_args

import pytest
from sqlalchemy import BigInteger, Boolean, DateTime, Integer, Text
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.dialects.postgresql import UUID as PgUUID

from models.base import Base

from api.v1.platform.p17 import models as p17m
from api.v1.platform.p17.schemas import (
    BACKUP_FAILURE_REASONS,
    LastBackupStatus,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Expected column sets per table -- restated from migration 021 (independent of
# the ORM module) so the model and the migration are cross-checked.
# ---------------------------------------------------------------------------

EXPECTED_COLUMNS = {
    "platform_backup_outcome": [
        "outcome_id", "tenant_id", "job_kind", "status", "started_at",
        "completed_at", "bytes_written", "failure_reason_code",
        "source_writer_id", "created_at",
    ],
    "platform_backup_policy": [
        "policy_id", "tenant_id", "retention_policy", "export_enabled",
        "restore_test_cadence_hours", "created_at", "updated_at",
    ],
}

EXPECTED_PK = {
    "platform_backup_outcome": "outcome_id",
    "platform_backup_policy": "policy_id",
}

MODEL_BY_TABLE = {
    "platform_backup_outcome": p17m.PlatformBackupOutcome,
    "platform_backup_policy": p17m.PlatformBackupPolicy,
}


def test_models_import_and_extend_project_base():
    """Both models import, subclass models.base.Base, and register metadata."""
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
    """Each table maps EXACTLY migration 021's columns -- no more, no fewer."""
    table = MODEL_BY_TABLE[table_name].__table__
    actual = [c.name for c in table.columns]
    assert set(actual) == set(expected), (
        f"{table_name}: missing={set(expected) - set(actual)} "
        f"extra={set(actual) - set(expected)}"
    )


@pytest.mark.parametrize("table_name", sorted(MODEL_BY_TABLE))
def test_domain_specific_primary_key_not_id(table_name):
    """PKs are domain-specific (outcome_id / policy_id), never 'id'."""
    table = MODEL_BY_TABLE[table_name].__table__
    pk_cols = [c.name for c in table.primary_key.columns]
    assert pk_cols == [EXPECTED_PK[table_name]], f"{table_name} PK cols: {pk_cols}"
    assert "id" not in pk_cols
    assert "is_deleted" not in {c.name for c in table.columns}
    assert "deleted_at" not in {c.name for c in table.columns}
    assert "created_by" not in {c.name for c in table.columns}
    assert "updated_by" not in {c.name for c in table.columns}


def test_key_column_types():
    o = p17m.PlatformBackupOutcome.__table__.c
    p = p17m.PlatformBackupPolicy.__table__.c

    assert isinstance(o.outcome_id.type, PgUUID) and o.outcome_id.type.as_uuid
    assert isinstance(o.tenant_id.type, PgUUID)
    assert isinstance(o.started_at.type, DateTime) and o.started_at.type.timezone is True
    assert isinstance(o.completed_at.type, DateTime) and o.completed_at.type.timezone is True
    assert isinstance(o.bytes_written.type, BigInteger)
    assert isinstance(o.failure_reason_code.type, Text)
    assert isinstance(o.source_writer_id.type, Text)

    assert isinstance(p.policy_id.type, PgUUID) and p.policy_id.type.as_uuid
    assert isinstance(p.retention_policy.type, Text)
    assert isinstance(p.export_enabled.type, Boolean)
    assert isinstance(p.restore_test_cadence_hours.type, Integer)
    assert isinstance(p.updated_at.type, DateTime) and p.updated_at.type.timezone is True


def test_server_defaults_preserved():
    """gen_random_uuid() PK + now() timestamp defaults mirror migration 021."""
    o = p17m.PlatformBackupOutcome.__table__.c
    p = p17m.PlatformBackupPolicy.__table__.c

    def sd(col):
        assert col.server_default is not None, f"{col.name} missing server_default"
        return str(col.server_default.arg).lower()

    assert "gen_random_uuid" in sd(o.outcome_id)
    assert "now" in sd(o.created_at)
    assert "gen_random_uuid" in sd(p.policy_id)
    assert "now" in sd(p.created_at)
    assert "now" in sd(p.updated_at)


def test_enum_columns_reference_existing_types_with_symbols_no_autocreate():
    """Every enum column uses create_type=False AND carries decode symbols.

    A postgresql.ENUM with create_type=False and no symbols raises LookupError at
    row-load time (the P21 lesson); the ORM _enum helper supplies the closed
    symbols so rows decode. Importing the models NEVER emits CREATE TYPE.
    """
    seen = {}
    for model in MODEL_BY_TABLE.values():
        for col in model.__table__.columns:
            if isinstance(col.type, PgEnum):
                assert col.type.create_type is False, (
                    f"{col.name} enum must use create_type=False"
                )
                assert col.type.name.startswith("platform_backup_"), col.type.name
                # The decode symbols are present (non-empty) and match the
                # frozenset constants exactly.
                symbols = tuple(sorted(col.type.enums))
                seen[col.type.name] = symbols
    assert seen.get("platform_backup_job_kind") == ("backup_job", "restore_test_job")
    assert seen.get("platform_backup_outcome_status") == (
        "failed", "in_progress", "partial", "success",
    )


def test_no_business_table_references():
    """No backup column foreign-keys into any product / tenant business table."""
    forbidden_targets = (
        "orders", "payments", "invoices", "customers", "inventory",
        "ledger", "wholesalers", "retailers",
    )
    for model in MODEL_BY_TABLE.values():
        for col in model.__table__.columns:
            for fk in col.foreign_keys:
                tgt = fk.target_fullname.lower()
                assert not any(f in tgt for f in forbidden_targets), (
                    f"{col.name} FK {tgt} references a business table"
                )
    # tenant_id is a scoped identifier: it is NOT declared as a foreign key.
    assert not p17m.PlatformBackupOutcome.__table__.c.tenant_id.foreign_keys
    assert not p17m.PlatformBackupPolicy.__table__.c.tenant_id.foreign_keys


def _lit(alias):
    return set(get_args(alias))


def test_job_kind_values_closed():
    assert p17m.JOB_KIND_VALUES == {"backup_job", "restore_test_job"}


def test_outcome_status_is_stored_subset_excludes_derived():
    """Stored status is the success/partial/failed/in_progress subset only.

    'stale' and 'unknown' are read-time DERIVATIONS and must NEVER be stored, so
    they are absent from OUTCOME_STATUS_VALUES. The stored set is a subset of the
    P17 response LastBackupStatus vocabulary.
    """
    assert p17m.OUTCOME_STATUS_VALUES == {
        "success", "partial", "failed", "in_progress",
    }
    assert "stale" not in p17m.OUTCOME_STATUS_VALUES
    assert "unknown" not in p17m.OUTCOME_STATUS_VALUES
    assert p17m.OUTCOME_STATUS_VALUES.issubset(_lit(LastBackupStatus))


def test_failure_reason_values_match_schema_allowlist():
    """ORM failure-reason vocabulary == BACKUP_FAILURE_REASONS exactly."""
    assert p17m.FAILURE_REASON_VALUES == set(BACKUP_FAILURE_REASONS)
    assert p17m.FAILURE_REASON_VALUES == {
        "backup_job_timeout",
        "restore_checksum_mismatch",
        "backup_source_unreachable",
        "restore_test_failed",
        "backup_incomplete",
        "unknown",
    }
