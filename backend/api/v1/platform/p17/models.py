"""P17-D-C backup / status source -- SQLAlchemy ORM models (read-path substrate).

Read ORM mapping for the two public backup / status source tables created by
migration ``030_platform_backup_status_source`` (P17-D-C):
``platform_backup_outcome`` (append-only) and ``platform_backup_policy``
(optional config), both in the ``public`` schema.

These models are a faithful, column-for-column mapping of migration 021. They
exist so the P17 registry READ path (``services.py``) can SELECT the latest
outcome rows + policy through the ORM. The read path is READ-ONLY: it never
INSERTs / UPDATEs / DELETEs outcome rows (mutations are writer-only).

Design choices (documented for the ledger):
  - The models extend ``models.base.Base`` (the project's shared DeclarativeBase)
    directly, NOT ``PublicBaseModel``. ``PublicBaseModel`` injects a hard-coded
    ``id`` primary key plus, via ``AuditMixin``, ``is_deleted`` / ``deleted_at``
    soft-delete columns. The backup tables have domain-specific primary keys
    (``outcome_id`` / ``policy_id``) and carry NO soft-delete columns, so
    ``PublicBaseModel`` cannot be reused without producing incorrect column
    mappings and Alembic drift. This mirrors the P21 durable-model precedent.
  - Every column matches migration 021 exactly (name, type, nullability, and the
    ``gen_random_uuid()`` / ``now()`` server defaults). ``created_at`` /
    ``updated_at`` mirror the migration (``server_default = func.now()``) and
    intentionally do NOT carry ``AuditMixin``'s ``onupdate``.
  - Enum columns reference the already-created public enum types with
    ``postgresql.ENUM(create_type=False)`` and supply the closed value symbols so
    SQLAlchemy can DECODE rows on read (a ``postgresql.ENUM`` created with
    ``create_type=False`` and no symbols otherwise raises LookupError at
    row-load time -- the P21 ORM-enum lesson). This is a Python-side decode
    detail only; it emits no DDL.
  - Index / unique-constraint / CHECK-constraint DDL is intentionally NOT
    redeclared here. Ownership stays with migration 021 (the source of truth);
    the ORM layer is a read/write column mapping only, which avoids duplicated,
    drift-prone constraint definitions.
  - ``tenant_id`` is a scoped identifier column, NOT a foreign key. No outbound
    foreign key is declared (consistent with the contract: tenant_id is never
    joinable to tenant business tables).

These models are deliberately NOT registered in ``models/__init__.py`` (so they
do not enter the shared ``Base.metadata`` used by Alembic autogenerate or by
``onboard_tenant``'s ``metadata.create_all``) -- the same discipline the P21
durable models follow. Importing this module therefore has no migration,
autogenerate, or runtime-storage side effect; the P17 services read path imports
it directly to map the rows it SELECTs.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Integer,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


# ---------------------------------------------------------------------------
# Public enum type references (already created by migration 021). create_type
# = False guarantees SQLAlchemy never tries to CREATE / DROP these types.
# ---------------------------------------------------------------------------


def _enum(name: str) -> ENUM:
    """Reference an already-created public backup enum type.

    Mirrors migration 021's ``_enum`` helper with the closed value symbols
    supplied (from ``_ENUM_VALUE_MAP``) so SQLAlchemy can decode rows on read.
    This is a Python-side decode detail only; ``create_type=False`` is preserved
    and no DDL is ever emitted.
    """
    return ENUM(*_ENUM_VALUE_MAP.get(name, ()), name=name, create_type=False)


# ---------------------------------------------------------------------------
# Closed enum / vocabulary sets (single source of truth for the ORM layer;
# mirrored from migration 021 ENUM_TYPES and the p17 schemas allowlist, and
# cross-checked in tests/test_platform_p17dc_backup_models.py).
#
# Stored status EXCLUDES 'stale' and 'unknown' -- those are read-time
# derivations the adapter computes, never stored facts about a job.
# ---------------------------------------------------------------------------

JOB_KIND_VALUES = frozenset(("backup_job", "restore_test_job"))
OUTCOME_STATUS_VALUES = frozenset(("success", "partial", "failed", "in_progress"))
# Closed failure-reason vocabulary mirrored EXACTLY from
# backend/api/v1/platform/p17/schemas.py BACKUP_FAILURE_REASONS.
FAILURE_REASON_VALUES = frozenset(
    (
        "backup_job_timeout",
        "restore_checksum_mismatch",
        "backup_source_unreachable",
        "restore_test_failed",
        "backup_incomplete",
        "unknown",
    )
)

# Map each public backup enum TYPE NAME to its closed symbol tuple, so the ORM
# ``_enum`` helper can supply the symbols for Python-side row decode. This only
# affects decode; create_type=False is preserved and no DDL is ever emitted.
_ENUM_VALUE_MAP: dict[str, tuple[str, ...]] = {
    "platform_backup_job_kind": tuple(JOB_KIND_VALUES),
    "platform_backup_outcome_status": tuple(OUTCOME_STATUS_VALUES),
}


# ---------------------------------------------------------------------------
# platform_backup_outcome -- append-only backup-job / restore-test-job outcome.
# ---------------------------------------------------------------------------


class PlatformBackupOutcome(Base):
    """One backup-job or restore-test-job run outcome (append-only).

    ``outcome_id`` is the primary key. ``tenant_id`` is a scoped identifier only
    (NULL = platform-wide); it is NOT a foreign key and is never joinable to
    tenant business tables. ``status`` is the stored job verdict
    (success / partial / failed / in_progress); the read-time DERIVED values
    ``stale`` and ``unknown`` are NEVER stored here. ``bytes_written`` is a
    magnitude only (never a path). ``failure_reason_code`` is the closed
    ``BACKUP_FAILURE_REASONS`` vocabulary only (never the raw exception / log /
    command line). Mutations are writer-only; the registry read path SELECTs.
    """

    __tablename__ = "platform_backup_outcome"
    __table_args__ = {"schema": "public"}

    outcome_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True), nullable=True
    )
    job_kind: Mapped[str] = mapped_column(
        _enum("platform_backup_job_kind"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        _enum("platform_backup_outcome_status"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    bytes_written: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    failure_reason_code: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_writer_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# ---------------------------------------------------------------------------
# platform_backup_policy -- optional per-tenant / platform-default config.
# ---------------------------------------------------------------------------


class PlatformBackupPolicy(Base):
    """Optional admin-managed backup policy for a tenant or the platform default.

    ``policy_id`` is the primary key. ``tenant_id`` is a scoped identifier (NULL
    = platform default); NOT a foreign key. At most one row per tenant plus at
    most one platform-default row is enforced by migration 021's uniqueness
    indexes. ``restore_test_cadence_hours`` overrides the default restore-test
    cadence window for this tenant (NULL = use the platform default cadence).
    """

    __tablename__ = "platform_backup_policy"
    __table_args__ = {"schema": "public"}

    policy_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True), nullable=True
    )
    retention_policy: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    export_enabled: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    restore_test_cadence_hours: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


__all__ = [
    # ORM models
    "PlatformBackupOutcome",
    "PlatformBackupPolicy",
    # Closed enum / vocabulary sets
    "JOB_KIND_VALUES",
    "OUTCOME_STATUS_VALUES",
    "FAILURE_REASON_VALUES",
]
