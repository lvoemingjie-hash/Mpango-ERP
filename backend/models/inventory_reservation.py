"""Per-order inventory reservation ownership model."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from models.base import BaseModel


class InventoryReservation(BaseModel):
    """Owned reservation row for one order item and SKU."""

    __tablename__ = "inventory_reservations"
    __table_args__ = (
        Index("ix_inventory_reservations_order_id", "order_id"),
        Index("ix_inventory_reservations_sku_id", "sku_id"),
        Index("ix_inventory_reservations_status", "status"),
        Index(
            "ux_inventory_reservations_active_order_item",
            "order_item_id",
            unique=True,
            postgresql_where=text("status = 'reserved'"),
        ),
        CheckConstraint("quantity > 0", name="ck_inventory_reservations_quantity_positive"),
        CheckConstraint(
            "status IN ('reserved', 'consumed', 'released')",
            name="ck_inventory_reservations_status",
        ),
    )

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    order_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("order_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    sku_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skus.id", ondelete="CASCADE"),
        nullable=False,
    )
    sku_code: Mapped[str] = mapped_column(String(64), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=2),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="reserved")
    reserved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reference_type: Mapped[str] = mapped_column(String(50), nullable=False, default="order")
    reference_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    order = relationship("Order", lazy="selectin")
    order_item = relationship("OrderItem", lazy="selectin")
    sku = relationship("SKU", lazy="selectin")
