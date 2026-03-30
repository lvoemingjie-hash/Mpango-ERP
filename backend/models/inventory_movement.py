"""Inventory movement journal model - Tenant schema.

Records every stock change (adjustment, deduction, restock) for audit trail.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from enum import Enum as PyEnum

from sqlalchemy import Numeric, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from models.base import BaseModel


class MovementType(str, PyEnum):
    """Type of inventory movement."""
    ADJUSTMENT = "adjustment"
    DEDUCTION = "deduction"
    RESTOCK = "restock"


class InventoryMovement(BaseModel):
    __tablename__ = "inventory_movements"
    __table_args__ = (
        Index("ix_inventory_movements_sku_id", "sku_id"),
        Index("ix_inventory_movements_created_at", "created_at"),
    )

    sku_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skus.id", ondelete="CASCADE"),
        nullable=False,
    )

    movement_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="adjustment | deduction | restock",
    )

    quantity: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=2),
        nullable=False,
        comment="Signed quantity change (+/-)",
    )

    quantity_before: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=2),
        nullable=False,
        comment="quantity_on_hand before this movement",
    )

    quantity_after: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=2),
        nullable=False,
        comment="quantity_on_hand after this movement",
    )

    reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Human-readable reason for this movement",
    )

    reference_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="e.g. order, manual, return",
    )

    reference_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="e.g. order_id for deduction/restock",
    )
