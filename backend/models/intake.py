"""U4-C tenant-scoped data intake models."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import CHAR, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from models.base import BaseModel


class IntakeWorkspace(BaseModel):
    """Tenant-owned intake workspace for staged catalog onboarding."""

    __tablename__ = "intake_workspaces"
    __table_args__ = (
        Index("ix_intake_workspaces_tenant_id", "tenant_id"),
        Index("ix_intake_workspaces_status", "status"),
        Index("ix_intake_workspaces_created_at", "created_at"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="OPEN", server_default=text("'OPEN'")
    )
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )


class IntakeUpload(BaseModel):
    """Source file metadata and parser outcome placeholder."""

    __tablename__ = "intake_uploads"
    __table_args__ = (
        Index("ix_intake_uploads_workspace_id", "workspace_id"),
        Index("ix_intake_uploads_tenant_id", "tenant_id"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("intake_workspaces.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    file_ext: Mapped[str] = mapped_column(String(16), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    storage_key: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="RECEIVED", server_default=text("'RECEIVED'")
    )
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    column_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    headers_raw: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    headers_normalized: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    parse_summary: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)


class IntakeProductRow(BaseModel):
    """Normalized staged product row with source provenance."""

    __tablename__ = "intake_product_rows"
    __table_args__ = (
        Index("ix_intake_product_rows_workspace_id", "workspace_id"),
        Index("ix_intake_product_rows_upload_order", "upload_id", "row_index"),
        Index("ix_intake_product_rows_review_status", "review_status"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("intake_workspaces.id", ondelete="CASCADE"), nullable=False
    )
    upload_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("intake_uploads.id", ondelete="CASCADE"), nullable=False
    )
    source_row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_values: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    normalized_values: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    mapping_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    sku_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    unit_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    barcode: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    image_asset_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    review_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="UNREVIEWED", server_default=text("'UNREVIEWED'")
    )
    dedupe_key: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)


class IntakeValidationIssue(BaseModel):
    """Row-level and file-level validation issue placeholder."""

    __tablename__ = "intake_validation_issues"
    __table_args__ = (
        Index("ix_intake_validation_issues_workspace_id", "workspace_id"),
        Index("ix_intake_validation_issues_row_id", "row_id"),
        Index("ix_intake_validation_issues_severity", "severity"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("intake_workspaces.id", ondelete="CASCADE"), nullable=False
    )
    upload_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("intake_uploads.id", ondelete="CASCADE"), nullable=True
    )
    row_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("intake_product_rows.id", ondelete="CASCADE"), nullable=True
    )
    source_row_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    field: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    source_header: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_blocking: Mapped[bool] = mapped_column(nullable=False, default=False, server_default=text("false"))
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
