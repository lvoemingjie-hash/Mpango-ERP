"""
RetailerPrice model — tenant-scoped retailer-specific sell prices.

Phase 3 MVP pricing: explicit retailer-to-SKU price records.
Lives in tenant schema alongside orders, skus, inventory.

Design rules (CTO Phase 3 directive):
- No promotions engine, no discount DSL
- Simple retailer_id + sku_id → price lookup
- Price is server-authoritative, never from client input
- Unique constraint on (retailer_id, sku_id) per tenant
"""
import uuid
from decimal import Decimal

from sqlalchemy import CheckConstraint, Index, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from models.base import BaseModel


class RetailerPrice(BaseModel):
    """
    Retailer-specific sell price for a SKU within a tenant.

    This table stores the price a specific retailer pays for a specific
    product. It is the single source of truth for pricing in client-facing
    APIs. Prices are NEVER accepted from the client request body.
    """
    __tablename__ = "retailer_prices"
    __table_args__ = (
        UniqueConstraint(
            "retailer_id", "sku_id",
            name="uq_retailer_prices_retailer_sku",
        ),
        CheckConstraint(
            "price > 0",
            name="ck_retailer_prices_positive_price",
        ),
        Index("ix_retailer_prices_retailer_id", "retailer_id"),
        Index("ix_retailer_prices_sku_id", "sku_id"),
    )

    retailer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        comment="FK to public.retailers.id (not enforced cross-schema)",
    )
    sku_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        comment="FK to skus.id within the same tenant schema",
    )
    price: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=2),
        nullable=False,
        comment="Sell price for this retailer+SKU combination",
    )
