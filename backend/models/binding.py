"""Wholesaler-Retailer binding model - stored in public schema."""

import uuid
from decimal import Decimal

from sqlalchemy import String, Index, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from models.base import PublicBaseModel


class WholesalerRetailerBinding(PublicBaseModel):
    """Binding relationship between a wholesaler and a retailer."""

    __tablename__ = "wholesaler_retailer_bindings"
    __table_args__ = (
        UniqueConstraint("wholesaler_id", "retailer_id", name="uq_wholesaler_retailer"),
        Index("ix_bindings_wholesaler_id", "wholesaler_id"),
        Index("ix_bindings_retailer_id", "retailer_id"),
        {"schema": "public"},
    )

    wholesaler_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.wholesalers.id"),
        nullable=False,
        comment="Wholesaler (tenant) id",
    )

    retailer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.retailers.id"),
        nullable=False,
        comment="Retailer id",
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="active",
        server_default="active",
        comment="active|inactive",
    )

    outstanding_balance: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
        comment="Outstanding balance / credit exposure cache (MVP)",
    )
