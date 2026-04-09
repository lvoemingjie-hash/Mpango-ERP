"""
PlatformAuditLog model — Append-only audit log for platform admin actions.

Table: public.platform_audit_logs
Track: Platform P0

Append-only design: no AuditMixin, no updated_at, no is_deleted.
This table is an immutable event log — records are written once and never modified.
"""
from datetime import datetime
from typing import Optional
import uuid

from sqlalchemy import String, DateTime, ForeignKey, Index, func, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class PlatformAuditLog(Base):
    """
    Append-only platform audit log entry.

    Design decisions:
    - Inherits from Base directly (NOT PublicBaseModel/AuditMixin)
    - No updated_at — records are immutable once written
    - No is_deleted — audit logs are never soft-deleted
    - No user tracking — set by internal appender service

    Domain separation from sys_audit_logs:
    - sys_audit_logs = BI/business data access patterns (product track)
    - platform_audit_logs = platform admin actions (platform track)
    """
    __tablename__ = 'platform_audit_logs'
    __table_args__ = (
        Index('ix_platform_audit_logs_wholesaler_id', 'wholesaler_id'),
        Index('ix_platform_audit_logs_action', 'action'),
        Index('ix_platform_audit_logs_created_at', 'created_at'),
        {'schema': 'public'}
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text('gen_random_uuid()')
    )
    actor_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment='Who acted: system, admin, api'
    )
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment='UUID of the actor'
    )
    wholesaler_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('public.wholesalers.id'),
        nullable=True,
        comment='Affected tenant (NULL for global actions). FK enforced at DB level.'
    )
    action: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment='Action performed, e.g. tenant.suspend, tier.change'
    )
    resource: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment='Resource affected, e.g. wholesalers/<id>'
    )
    audit_metadata: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        server_default='{}',
        comment='Action details (before/after, context)'
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment='When the action occurred (set server-side)'
    )
