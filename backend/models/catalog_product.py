"""Tenant-local catalog product identity."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import Boolean, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import BaseModel


class CatalogProduct(BaseModel):
    """Stable product identity shared by one or more sellable units."""

    __tablename__ = "catalog_products"
    __table_args__ = (
        Index("ix_catalog_products_name", "name"),
        Index("ix_catalog_products_is_active", "is_active"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    sellable_units = relationship("SKU", back_populates="catalog_product", lazy="selectin")
