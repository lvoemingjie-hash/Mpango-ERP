"""
Order and OrderItem models - Tenant schema sales tables.
Implements openapi.yaml Order schemas.
"""
from typing import Optional, List
from enum import Enum as PyEnum
from decimal import Decimal

from sqlalchemy import CheckConstraint, String, Text, Enum, Numeric, Integer, ForeignKey, Index, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
import uuid

from models.base import BaseModel


class OrderStatus(str, PyEnum):
    """
    Order status enum per openapi.yaml OrderStatus schema.

    Extended for S5-A Order State Machine with additional states:
    - PARTIALLY_PAID: Order has received partial payment
    - PAID: Order is fully paid
    - FULFILLED: Order has been delivered/completed
    - VOIDED: Order was voided before any payment (clean cancellation)
    - RETURNED: Order was returned after fulfillment (full return)
    """
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    FULFILLED = "fulfilled"
    CANCELLED = "cancelled"
    VOIDED = "voided"
    RETURNED = "returned"


class Order(BaseModel):
    """
    Order model - stored in tenant schema.

    Implements openapi.yaml Order schema:
    - retailer_id: UUID, NOT NULL
    - status: enum (draft, confirmed, cancelled)
    - total_amount: numeric
    - notes: text, NULL
    """
    __tablename__ = "orders"
    __table_args__ = (
        Index('ix_orders_wholesaler_id', 'wholesaler_id'),
        Index('ix_orders_retailer_id', 'retailer_id'),
        Index('ix_orders_status', 'status'),
        Index('ix_orders_created_at', 'created_at'),
        Index('ux_orders_creation_intent', 'wholesaler_id', 'retailer_id', 'created_by',
              'creation_operation', 'creation_key_digest', unique=True,
              postgresql_where=text('creation_key_digest IS NOT NULL')),
        Index('ux_orders_replacement', 'replaces_order_id', unique=True,
              postgresql_where=text('replaces_order_id IS NOT NULL')),
        CheckConstraint("currency_snapshot IS NULL OR currency_snapshot IN ('KES', 'UGX')",
                        name="ck_orders_s1_currency"),
        CheckConstraint("(creation_key_digest IS NULL AND creation_fingerprint IS NULL "
                        "AND creation_operation IS NULL) OR "
                        "(creation_key_digest IS NOT NULL AND creation_fingerprint IS NOT NULL "
                        "AND creation_operation IS NOT NULL AND created_by IS NOT NULL "
                        "AND currency_snapshot IS NOT NULL)", name="ck_orders_creation_intent"),
    )

    wholesaler_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="FK to public.wholesalers.id (not enforced in skeleton)"
    )
    retailer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="FK to retailers.id (not enforced in skeleton)"
    )
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, name="order_status", values_callable=lambda x: [e.value for e in x]),
        default=OrderStatus.DRAFT,
        nullable=False,
        index=True
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=2),
        default=Decimal("0.00"),
        nullable=False
    )
    notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    country_snapshot: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    currency_snapshot: Mapped[Optional[str]] = mapped_column(String(3), nullable=True)
    registration_snapshot_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    creation_operation: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    creation_key_digest: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    creation_fingerprint: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    quote_seen: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    quote_resolved: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    replaces_order_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey('orders.id', ondelete='RESTRICT'), nullable=True)

    # Relationships
    items: Mapped[List["OrderItem"]] = relationship(
        "OrderItem",
        back_populates="order",
        cascade="all, delete-orphan",
        lazy="selectin"
    )


class OrderItem(BaseModel):
    """
    OrderItem model - stored in tenant schema.

    Implements openapi.yaml OrderItem schema:
    - order_id: UUID, NOT NULL, FK to orders.id
    - product_id: UUID, NOT NULL
    - quantity: integer, NOT NULL
    - unit_price: numeric, NOT NULL
    - subtotal: numeric, NOT NULL
    """
    __tablename__ = "order_items"
    __table_args__ = (
        Index('ix_order_items_order_id', 'order_id'),
        Index('ix_order_items_sku_code', 'sku_code'),
        Index('ix_order_items_sellable_unit_id', 'sellable_unit_id'),
        CheckConstraint(
            "identity_status IN ('legacy', 'linked_legacy', 'stable')",
            name="ck_order_items_identity_status",
        ),
        CheckConstraint(
            "(identity_status = 'legacy' AND sellable_unit_id IS NULL) OR "
            "(identity_status = 'linked_legacy' AND sellable_unit_id IS NOT NULL) OR "
            "(identity_status = 'stable' AND sellable_unit_id IS NOT NULL AND unit_snapshot IS NOT NULL)",
            name="ck_order_items_identity_shape",
        ),
    )

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    sellable_unit_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skus.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    identity_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="legacy"
    )

    product_name: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )
    sku_code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True
    )
    unit_snapshot: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    package_quantity_snapshot: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 3), nullable=True)
    display_label_snapshot: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )
    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=2),
        nullable=False
    )
    subtotal: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=2),
        nullable=False
    )

    # Relationships
    order: Mapped["Order"] = relationship(
        "Order",
        back_populates="items"
    )
    sellable_unit = relationship("SKU", lazy="selectin")
