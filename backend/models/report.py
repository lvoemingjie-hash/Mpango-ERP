"""
S7-4-T3: Tenant-Scoped Report Model — sys_reports table.

This model stores user-created BI reports in the TENANT schema.
Each report is a governed BIAsset with an auto-generated URN,
an owner (the creating user), and an optional ACL for sharing.

🔒 S7-4-C1: URN format is urn:bi:report:<domain>:<id>.
    tenant_id is NOT embedded in the URN — it is derived from the
    tenant schema context at query time.

🔒 S7-4-C4: Any mutation (create/update/delete/ACL change) MUST
    trigger cache invalidation via invalidate_asset(urn).

Design Decisions:
- Inherits from BaseModel (UUID PK, audit columns, user tracking).
- Lives in tenant schema (same as orders, users, etc.).
- config is JSONB but validated at the application layer via Pydantic.
- acl is JSONB array of strings (same format as BIAsset.acl).
- domain defaults to "custom" for user-created reports.
"""
from __future__ import annotations

from typing import Optional
import uuid

from sqlalchemy import Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from models.base import BaseModel


class SysReport(BaseModel):
    """
    Tenant-scoped report asset — stored in tenant schema.

    Each row represents a user-created BI report that is registered
    as a governed BIAsset in the GovernanceRegistry via DbAssetResolver.

    URN is auto-generated: urn:bi:report:<domain>:<id>

    Columns:
        id:          UUID primary key (inherited from BaseModel).
        title:       Human-readable report name (1-256 chars).
        description: Optional business description.
        domain:      BI domain for URN generation (default: "custom").
        config:      JSONB report configuration (layout, widgets, etc.).
        owner_id:    UUID of the creating user (🔒 forced server-side).
        acl:         JSONB array of ACL entries (user:<id>, role:<name>, tenant:*).
        created_at:  Inherited from AuditMixin.
        updated_at:  Inherited from AuditMixin.
    """

    __tablename__ = "sys_reports"
    __table_args__ = (
        Index("ix_sys_reports_owner_id", "owner_id"),
        Index("ix_sys_reports_domain", "domain"),
    )

    title: Mapped[str] = mapped_column(
        String(256),
        nullable=False,
        comment="Human-readable report name",
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Business-level description of the report",
    )
    domain: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="custom",
        server_default="custom",
        comment="BI domain for URN generation (e.g., sales, finance, custom)",
    )
    config: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Report configuration: layout, widgets, data sources",
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        comment="UUID of the creating user (forced server-side, not user-supplied)",
    )
    acl: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
        comment="ACL entries: user:<id>, role:<name>, tenant:*",
    )

    # ── Helpers ────────────────────────────────────────────────────────

    def to_urn(self) -> str:
        """Generate the governance URN for this report."""
        return f"urn:bi:report:{self.domain}:{self.id}"

    def __repr__(self) -> str:
        return (
            f"SysReport(id={self.id}, title='{self.title}', "
            f"owner={self.owner_id}, domain={self.domain})"
        )
