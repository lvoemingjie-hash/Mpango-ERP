"""Import Run model — tenant schema.

U3-B1 Contract Foundation: tracks the 3-phase agent-operable import
contract (preview → validate → apply) for SKU bulk imports.

Each row represents one import session.  The import_id is a stable,
opaque reference that callers (agents, CLI, frontend wizard) use
to chain the three phases.

Status lifecycle:
    previewed → validated | needs_review → applied | failed
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, Index, DateTime, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from models.base import Base, AuditMixin


class ImportRun(Base, AuditMixin):
    """
    Tenant-schema import run tracker.

    NOTE: Does NOT inherit UserTrackingMixin because import runs may be
    initiated by agents (no human user).  The applied_by column is
    explicitly nullable for this reason.
    """

    __tablename__ = "import_runs"
    __table_args__ = (
        Index("ux_import_runs_import_id", "import_id", unique=True),
        Index("ix_import_runs_status", "status"),
        Index("ix_import_runs_tenant_id", "tenant_id"),
        Index("ix_import_runs_created_at", "created_at"),
    )

    # ── Primary Key ──────────────────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )

    # ── Stable import reference ──────────────────────────────────────
    import_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        comment="Opaque import session ID used by callers across phases",
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        comment="Tenant that owns this import run",
    )

    # ── Phase status ─────────────────────────────────────────────────
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="previewed",
        server_default=text("'previewed'"),
        comment="previewed | validated | needs_review | applied | failed",
    )

    # ── Source metadata ──────────────────────────────────────────────
    source_filename: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True,
    )
    source_encoding: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True,
    )
    total_rows: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0"),
    )

    # ── Validation counters ──────────────────────────────────────────
    valid_rows: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_rows: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    warning_rows: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # ── Phase payloads (JSONB snapshots) ─────────────────────────────
    mapping: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True,
        comment="Field mapping used for validate/apply phases",
    )
    validation_result: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True,
        comment="Full validation output snapshot",
    )
    apply_result: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True,
        comment="Full apply output snapshot",
    )

    # ── Apply counters ───────────────────────────────────────────────
    created_rows: Mapped[int] = mapped_column(
        Integer, nullable=True, default=0, server_default=text("0"),
    )
    skipped_rows: Mapped[int] = mapped_column(
        Integer, nullable=True, default=0, server_default=text("0"),
    )
    updated_rows: Mapped[int] = mapped_column(
        Integer, nullable=True, default=0, server_default=text("0"),
    )

    # ── Audit ────────────────────────────────────────────────────────
    applied_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True,
        comment="User UUID who triggered apply (nullable for agent-initiated)",
    )
    applied_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # ── Timestamps (from AuditMixin) ─────────────────────────────────
    # created_at, updated_at inherited from AuditMixin

    def __repr__(self) -> str:
        return (
            f"ImportRun(id={self.id}, import_id={self.import_id!r}, "
            f"status={self.status!r}, total_rows={self.total_rows})"
        )
