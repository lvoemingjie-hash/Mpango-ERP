"""
SQLAlchemy base models and mixins for Mpango ERP.
Implements database_contract.md requirements for audit columns and soft delete.
"""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, Boolean, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    """SQLAlchemy 2.0 declarative base."""
    pass


class AuditMixin:
    """
    Mixin for audit columns required by database_contract.md.
    All tables MUST include these columns.
    """
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("false"),
        nullable=False
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    
    def soft_delete(self) -> None:
        """Mark record as deleted without removing from database."""
        self.is_deleted = True
        self.deleted_at = datetime.utcnow()
    
    def restore(self) -> None:
        """Restore a soft-deleted record."""
        self.is_deleted = False
        self.deleted_at = None


class UserTrackingMixin:
    """
    Mixin for user tracking columns.
    Tracks who created and last updated the record.
    """
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True  # NULL for system-created records
    )
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True
    )


class BaseModel(Base, AuditMixin, UserTrackingMixin):
    """
    Abstract base model with UUID primary key, audit columns, and user tracking.
    All tenant-scoped models should inherit from this.
    
    Implements database_contract.md requirements:
    - UUID primary key with gen_random_uuid() default
    - Audit columns (created_at, updated_at, is_deleted, deleted_at)
    - User tracking columns (created_by, updated_by)
    """
    __abstract__ = True
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()")
    )


class PublicBaseModel(Base, AuditMixin):
    """
    Base model for public schema tables (e.g., wholesalers).
    Does not include user tracking since users are tenant-scoped.
    """
    __abstract__ = True
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()")
    )
