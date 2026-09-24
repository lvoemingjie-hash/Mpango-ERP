"""OrderCreditHold model — the R2 per-order credit-hold lifecycle.

Tenant-schema table ``order_credit_holds``: exactly one lifecycle row per
order (``order_id`` is UNIQUE), no soft-delete columns — a financial record
that can never be resurrected, deleted-and-recreated, or re-expanded after
reaching a terminal state. ``order_id`` is the single attribution anchor:
the owning retailer/wholesaler is always derived from the (live, locked)
order row, never denormalised here.

Lifecycle (service-enforced transitions; CHECK enforces row shape only):
    active    remaining_amount > 0, decremented by cash/transfer settlement
    settled   full cash/transfer settlement, remaining_amount = 0
    released  cancelled order, remaining_amount = 0
    converted full credit sale, remaining_amount = 0

Rows created by migration 039 carry ``created_by IS NULL`` (synthetic
backfill snapshot); runtime-created rows always carry the acting user.
"""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime
from sqlalchemy.sql import func

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class OrderCreditHold(Base):
    __tablename__ = "order_credit_holds"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active','released','settled','converted')",
            name="ck_order_credit_holds_status",
        ),
        CheckConstraint(
            "amount > 0",
            name="ck_order_credit_holds_amount_positive",
        ),
        CheckConstraint(
            "remaining_amount <= amount",
            name="ck_order_credit_holds_remaining_cap",
        ),
        CheckConstraint(
            "(status = 'active' AND remaining_amount > 0) "
            "OR (status IN ('released','settled','converted') "
            "AND remaining_amount = 0)",
            name="ck_order_credit_holds_lifecycle_shape",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
        index=True,
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )
    remaining_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="active",
        server_default="active",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
