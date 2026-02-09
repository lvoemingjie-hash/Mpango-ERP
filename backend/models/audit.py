"""
S7-3: BI Access Audit Log Model — The Recorder.

🔒 Constraint S7-3-C1 (CTO Mandate, Frozen):
    All Audit / Compliance / Security Logs MUST reside in the public schema.
    Tenant is a data dimension (column), NOT a schema boundary.

🔒 Constraint S7-3-C2 (CTO Mandate, Frozen):
    This is an APPEND-ONLY semantic object.
    - No updated_at, is_deleted, deleted_at columns.
    - No soft_delete(), restore(), update() methods.
    - ORM declares confirm_deleted_rows=False.
    - DB-level REVOKE UPDATE/DELETE is a Phase 8 ops task.

Design Decisions:
    - Inherits from Base directly (NOT AuditMixin, NOT BaseModel).
    - Only id (UUID) + created_at — immutable fact records.
    - JSONB metadata for extensibility without schema migration.
    - Index on (tenant_id, created_at) for compliance queries.
    - Partitioning: deferred until >10M rows (documented in S7-3 ledger).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from models.base import Base


class SysAuditLog(Base):
    """
    Append-only audit log for BI access policy decisions.

    Every call to enforce_bi_access() or RequireBIPermission produces
    exactly one row in this table, regardless of allow/deny outcome.

    This table lives in the PUBLIC schema (🔒 S7-3-C1).
    It is an immutable fact record (🔒 S7-3-C2).

    Columns:
        id:          UUID primary key (gen_random_uuid).
        created_at:  Timestamp of the policy decision (server-generated).
        actor_id:    The user_id from PolicySubject (who acted).
        tenant_id:   The tenant_id from PolicySubject (which tenant).
        action:      The BIAction attempted (view/interact/export/manage).
        asset_urn:   The full URN of the target asset.
        allowed:     Whether the policy allowed the action.
        policy_name: Which policy rule produced the decision.
        reason:      Sanitized reason string (no PII — 🔒 S7-3-C2).
        metadata:    JSONB for extensibility (request_id, IP, etc.).

    Partitioning Strategy (deferred):
        When sys_audit_logs > 10M rows → Ops must enable monthly
        range partitioning on created_at + retention policy.
    """

    __tablename__ = "sys_audit_logs"
    __table_args__ = (
        Index(
            "ix_sys_audit_logs_tenant_created",
            "tenant_id",
            "created_at",
        ),
        Index(
            "ix_sys_audit_logs_actor",
            "actor_id",
        ),
        Index(
            "ix_sys_audit_logs_asset_urn",
            "asset_urn",
        ),
        Index(
            "ix_sys_audit_logs_allowed",
            "allowed",
        ),
        {"schema": None, "comment": "S7-3: Append-only BI access audit trail (public schema)"},
    )

    # 🔒 S7-3-C2: Append-only ORM declaration
    __mapper_args__ = {"confirm_deleted_rows": False}

    # ── Primary Key ──────────────────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )

    # ── Timestamp (immutable, server-generated) ──────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=False,  # Covered by composite index
    )

    # ── Subject Context ──────────────────────────────────────────────
    actor_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="user_id from PolicySubject",
    )
    tenant_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="tenant_id from PolicySubject",
    )

    # ── Action & Asset ───────────────────────────────────────────────
    action: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="BIAction value: view/interact/export/manage",
    )
    asset_urn: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        comment="Full URN of the target BI asset",
    )

    # ── Decision ─────────────────────────────────────────────────────
    allowed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        comment="True if policy allowed the action",
    )
    policy_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Policy rule that produced the decision",
    )
    reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Sanitized reason (no PII)",
    )

    # ── Extensibility ────────────────────────────────────────────────
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
        default=None,
        comment="Extensible context: request_id, IP, user_agent, etc.",
    )

    def __repr__(self) -> str:
        return (
            f"SysAuditLog(id={self.id}, actor={self.actor_id}, "
            f"action={self.action}, asset={self.asset_urn}, "
            f"allowed={self.allowed})"
        )
