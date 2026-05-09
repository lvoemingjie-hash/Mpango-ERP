"""
PlatformAuditLog model — Append-only audit log for platform admin actions.

Table: public.platform_audit_logs
Track: Platform P0

Append-only service semantics: records are written once and never modified
through business logic. ORM contract columns (updated_at, is_deleted, deleted_at)
exist for schema uniformity but no business entry points write to them.
"""
from datetime import datetime
from typing import Optional
import uuid

from sqlalchemy import String, DateTime, Boolean, ForeignKey, Index, func, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class PlatformAuditLog(Base):
    """
    Append-only platform audit log entry.

    Design decisions:
    - Inherits from Base directly (NOT PublicBaseModel/AuditMixin)
    - ORM contract columns (updated_at, is_deleted, deleted_at) present for
      schema uniformity; defaults ensure they are inert for append-only writes
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
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment='ORM contract column — inert for append-only semantics'
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text('false'),
        nullable=False,
        comment='ORM contract column — always false for append-only'
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment='ORM contract column — always null for append-only'
    )
