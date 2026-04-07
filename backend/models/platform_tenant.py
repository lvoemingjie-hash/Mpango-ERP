"""
PlatformTenant model - Platform-level tenant lifecycle journal.

Table: public.platform_tenants
Track: Platform P0

This table tracks platform-level provisioning operations.
It is NOT a replacement for wholesalers — it is an operational journal
for platform admin actions related to tenant lifecycle.
"""
from datetime import datetime
from typing import Optional
import uuid

from sqlalchemy import String, Text, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from models.base import PublicBaseModel


class PlatformTenant(PublicBaseModel):
    """
    Platform tenant record — tracks provisioning lifecycle.

    One-to-one relationship with wholesalers via wholesaler_id.
    References tenant identity, does NOT duplicate it.

    Key semantic distinction:
    - wholesalers.status = current platform-facing tenant state snapshot
    - platform_tenants.provisioning_status = operational provisioning lifecycle state
    These are NOT the same concept.
    """
    __tablename__ = "platform_tenants"
    __table_args__ = (
        Index('ix_platform_tenants_wholesaler_id', 'wholesaler_id', unique=True),
        {"schema": "public"}
    )

    wholesaler_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('public.wholesalers.id'),
        nullable=False,
        comment="Reference to tenant registry (wholesalers.id)"
    )
    provisioning_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending",
        comment="Provisioning state: pending, schema_created, seed_complete, failed"
    )
    provisioning_log: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        server_default="{}",
        comment="Structured provisioning event log"
    )
    activated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When platform activation completed"
    )
    deactivated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When platform deactivation occurred"
    )
    deactivation_reason: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Reason for deactivation"
    )
