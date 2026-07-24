"""Wholesaler-Retailer binding model - stored in public schema."""

import uuid
from decimal import Decimal
from typing import Optional

from sqlalchemy import CheckConstraint, String, Index, ForeignKey, Numeric, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from models.base import PublicBaseModel


class WholesalerRetailerBinding(PublicBaseModel):
    """Binding relationship between a wholesaler and a retailer."""

    __tablename__ = "wholesaler_retailer_bindings"
    __table_args__ = (
        UniqueConstraint("wholesaler_id", "retailer_id", name="uq_wholesaler_retailer"),
        CheckConstraint(
            "outstanding_balance >= 0",
            name="ck_wrb_outstanding_balance_non_negative",
        ),
        Index("ix_bindings_wholesaler_id", "wholesaler_id"),
        Index("ix_bindings_retailer_id", "retailer_id"),
        # DC-12R1-S1: authoritative retailer↔tenant-user mapping. A tenant-local
        # user maps to at most one retailer binding within a wholesaler. NULL
        # (pre-R1 bindings) and soft-deleted rows are excluded so legacy rows
        # do not collide. Plain UUID, no cross-schema FK (matches the existing
        # invitation convention; the referenced users row lives in t_<ws>).
        Index(
            "ux_bindings_wholesaler_tenant_user",
            "wholesaler_id",
            "tenant_user_id",
            unique=True,
            postgresql_where=text(
                "tenant_user_id IS NOT NULL AND is_deleted IS FALSE"
            ),
        ),
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

    tenant_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment=(
            "DC-12R1-S1: authoritative mapping to the tenant-local users.id for "
            "this binding. Client identity resolves token.user_id -> this column "
            "-> retailer_id. NULL for pre-R1 bindings (no login identity)."
        ),
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
