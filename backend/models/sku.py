"""SKU master data model - Tenant schema.

Phase B4: Inventory MVP

The physical SKU table is the tenant-local SellableUnit identity. Orders use
its stable UUID plus immutable transaction snapshots; sku_code is descriptive.
"""

from __future__ import annotations

from typing import Optional

import uuid
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import BaseModel


class SKU(BaseModel):
    __tablename__ = "skus"
    __table_args__ = (
        Index("ux_skus_sku_code", "sku_code", unique=True),
        Index("ix_skus_catalog_product_id", "catalog_product_id"),
        Index("ix_skus_is_active", "is_active"),
        Index("ix_skus_created_at", "created_at"),
        CheckConstraint("package_quantity > 0", name="ck_skus_package_quantity_positive"),
    )

    catalog_product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("catalog_products.id", ondelete="RESTRICT"),
        nullable=False,
    )
    sku_code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    unit: Mapped[str] = mapped_column(String(32), nullable=False, default="unit")
    package_quantity: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=3), nullable=False, default=Decimal("1.000")
    )
    category: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    catalog_product = relationship("CatalogProduct", back_populates="sellable_units", lazy="selectin")
