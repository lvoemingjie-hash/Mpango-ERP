"""Inventory stock view model - Tenant schema.

Phase B4: Inventory MVP

A minimal per-SKU stock view with on_hand/reserved numbers.
No stock movement journal or reservation workflows are implemented in Phase B4.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import Numeric, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import BaseModel


class InventoryStock(BaseModel):
    __tablename__ = "inventory_stocks"
    __table_args__ = (
        Index("ux_inventory_stocks_sku_id", "sku_id", unique=True),
    )

    sku_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skus.id", ondelete="CASCADE"),
        nullable=False,
    )

    quantity_on_hand: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=2),
        nullable=False,
        default=Decimal("0.00"),
    )
    quantity_reserved: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=2),
        nullable=False,
        default=Decimal("0.00"),
    )

    sku = relationship("SKU", lazy="selectin")
