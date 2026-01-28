"""SKU master data model - Tenant schema.

Phase B4: Inventory MVP

Defines a minimal SKU entity that can be referenced by orders via sku_code.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import String, Text, Boolean, Index
from sqlalchemy.orm import Mapped, mapped_column

from models.base import BaseModel


class SKU(BaseModel):
    __tablename__ = "skus"
    __table_args__ = (
        Index("ux_skus_sku_code", "sku_code", unique=True),
        Index("ix_skus_is_active", "is_active"),
        Index("ix_skus_created_at", "created_at"),
    )

    sku_code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    unit: Mapped[str] = mapped_column(String(32), nullable=False, default="unit")
    category: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
