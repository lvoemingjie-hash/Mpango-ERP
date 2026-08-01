"""DC-12R1-S3-S2B-I1: Payment Declaration and Receipt Sequence ORM models.

Tenant-scoped models for the retailer payment declaration workflow.
These models are NOT soft-deletable — declarations are immutable audit records.

R2: CHAR(8) for receipt_sequences.business_date (matches migration/bootstrap exactly).
    CHECK constraints and defaults added for metadata parity.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    CHAR,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from models.base import Base


class DeclarationStatus(enum.Enum):
    """Lifecycle states for a payment declaration."""
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class DeclarationMethod(enum.Enum):
    """Allowed declaration methods (credit is NOT a valid declaration method)."""
    CASH = "cash"
    TRANSFER = "transfer"


class PaymentDeclaration(Base):
    """A retailer-submitted payment declaration.

    This is NOT a canonical payment — it has zero accounting effect until
    a wholesaler cashier confirms it. Confirmed declarations link to a
    canonical payment via confirmation_payment_id.

    Immutable: no is_deleted column. Never soft-deleted or hard-deleted.
    """
    __tablename__ = "payment_declarations"
    __table_args__ = (
        CheckConstraint(
            "method IN ('cash', 'transfer')",
            name="ck_payment_declarations_method",
        ),
        CheckConstraint(
            "status IN ('pending', 'confirmed', 'rejected')",
            name="ck_payment_declarations_status",
        ),
        CheckConstraint(
            "declared_amount > 0",
            name="ck_payment_declarations_amount_positive",
        ),
        UniqueConstraint(
            "retailer_id", "idempotency_key",
            name="ux_payment_declarations_retailer_idem",
        ),
        Index(
            "ix_payment_declarations_retailer_status",
            "retailer_id", "status",
        ),
        Index(
            "ix_payment_declarations_wholesaler_status",
            "wholesaler_id", "status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="RESTRICT"),
        nullable=False,
    )
    retailer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    wholesaler_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    declared_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )
    method: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )
    transfer_reference: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=DeclarationStatus.PENDING.value,
        server_default=text(f"'{DeclarationStatus.PENDING.value}'"),
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    submitted_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    confirmed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    confirmation_payment_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payments.id", ondelete="RESTRICT"),
        nullable=True,
    )
    rejected_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    rejected_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    reason: Mapped[Optional[str]] = mapped_column(
        String(256),
        nullable=True,
    )


class ReceiptSequence(Base):
    """Per-tenant receipt number allocator.

    Uses business_date CHAR(8) as primary key (exact match with migration/bootstrap).
    Allocation via INSERT ... ON CONFLICT DO UPDATE ... RETURNING next_seq.
    Atomic within the same transaction as the payment confirmation.
    """
    __tablename__ = "receipt_sequences"

    business_date: Mapped[str] = mapped_column(
        CHAR(8),
        primary_key=True,
    )
    next_seq: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
