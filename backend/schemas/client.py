"""Client-facing View Model schemas for Retailer App.

Design principles (CTO P0 mandates):
- Never expose cost_price, internal IDs, or wholesaler-internal fields
- Stock shown as level enum (LOW/MEDIUM/HIGH), not raw numbers
- retailer_id never accepted from request body
- All responses are UI-ready aggregated data
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Stock Level Enum (hides raw inventory numbers)
# ---------------------------------------------------------------------------

class StockLevel(str, Enum):
    OUT_OF_STOCK = "OUT_OF_STOCK"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


def compute_stock_level(quantity_on_hand: Decimal) -> StockLevel:
    """Convert raw quantity to a business-safe stock level."""
    qty = float(quantity_on_hand)
    if qty <= 0:
        return StockLevel.OUT_OF_STOCK
    if qty <= 10:
        return StockLevel.LOW
    if qty <= 50:
        return StockLevel.MEDIUM
    return StockLevel.HIGH


# ---------------------------------------------------------------------------
# Product View Models (DC-12R1-MVP-L1-SKU-R0-M1-R1-R1 product-level contract)
# ---------------------------------------------------------------------------
#
# OLD (per-SKU) semantics — REMOVED:
#   GET /client/products returned ONE item PER SELLABLE UNIT (per SKU row);
#   `id`/`sellable_unit_id` were the SKU.id and `product_id` was ambiguous
#   (GET /client/products/{id} actually queried skus.id).
#
# NEW (product-level) semantics:
#   GET /client/products returns ONE item PER CATALOG PRODUCT; `id` is the
#   CatalogProduct.id; the product carries its ACTIVE sellable units (packaging
#   choices) nested under `units`. GET /client/products/{id} queries
#   CatalogProduct.id ONLY (a sellable-unit UUID is a 404, never a product).

class ClientSellableUnitOption(BaseModel):
    """One packaging choice inside its parent product container."""
    sellable_unit_id: str = Field(..., description="Stable sellable-unit UUID used for ordering")
    sku_code: str
    unit: str
    package_quantity: Decimal
    price: Optional[Decimal] = Field(None, description="Retailer-specific selling price (null if not priced)")
    in_stock: bool
    stock_level: StockLevel
    can_order: bool = Field(..., description="True if in stock AND priced for this retailer")

    model_config = {"from_attributes": True}


_UNIT_STOCK_RANK = {
    StockLevel.HIGH: 3,
    StockLevel.MEDIUM: 2,
    StockLevel.LOW: 1,
    StockLevel.OUT_OF_STOCK: 0,
}


def product_stock_level(unit_levels: List[StockLevel]) -> StockLevel:
    """Aggregate a product's stock level as its BEST unit level."""
    if not unit_levels:
        return StockLevel.OUT_OF_STOCK
    return max(unit_levels, key=lambda level: _UNIT_STOCK_RANK[level])


class ClientProductSummary(BaseModel):
    """Product container — one per CatalogProduct in list view."""
    id: str = Field(..., description="CatalogProduct.id — the customer product identity")
    name: str
    category: Optional[str] = None
    in_stock: bool = Field(..., description="True if ANY active unit is in stock")
    stock_level: StockLevel = Field(..., description="Best (highest) unit stock level")
    can_order: bool = Field(..., description="True if ANY active unit can be ordered")
    unit_count: int
    units: List[ClientSellableUnitOption] = Field(..., description="Active packaging choices (deterministic order)")

    model_config = {"from_attributes": True}


class ClientProductDetail(ClientProductSummary):
    """Product detail — the full product container with its packaging choices."""
    description: Optional[str] = None


# ---------------------------------------------------------------------------
# Order View Models
# ---------------------------------------------------------------------------

class ClientOrderItemRequest(BaseModel):
    """Single line item in an order creation request."""
    sellable_unit_id: Optional[str] = Field(None, description="Stable sellable-unit UUID")
    sku_code: Optional[str] = Field(None, description="Compatibility SKU selector")
    quantity: int = Field(..., gt=0, description="Quantity to order")

    @field_validator("sellable_unit_id")
    @classmethod
    def validate_sellable_unit_id(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        try:
            return str(UUID(value))
        except (TypeError, ValueError) as exc:
            raise ValueError("sellable_unit_id must be a UUID") from exc

    @model_validator(mode="after")
    def require_selector(self):
        if not self.sellable_unit_id and not self.sku_code:
            raise ValueError("sellable_unit_id or sku_code is required")
        return self


class ClientCreateOrderRequest(BaseModel):
    """Order creation request — retailer_id is NOT here (derived from JWT)."""
    items: List[ClientOrderItemRequest] = Field(..., min_length=1)
    notes: Optional[str] = None


class ClientOrderItemView(BaseModel):
    """Single line item in an order response."""
    product_name: str
    sellable_unit_id: Optional[str] = None
    identity_status: str = "legacy"
    sku_code: str
    unit_snapshot: Optional[str] = None
    quantity: int
    unit_price: Decimal
    subtotal: Decimal

    model_config = {"from_attributes": True}


class ClientOrderView(BaseModel):
    """Aggregated order response — UI-ready."""
    id: str
    status: str
    total_amount: Decimal
    item_count: int
    notes: Optional[str] = None
    items: List[ClientOrderItemView] = []
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Payment and finance read models
# ---------------------------------------------------------------------------

class ClientPaymentView(BaseModel):
    """Retailer-safe payment history row."""
    id: str
    order_id: str
    amount: Decimal
    method: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ClientFinanceBalanceView(BaseModel):
    """Retailer-safe authoritative outstanding balance view."""
    outstanding_balance: Decimal
    has_outstanding_balance: bool
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Client Order Status (subset visible to retailer)
# ---------------------------------------------------------------------------

CLIENT_VISIBLE_STATUSES = {
    "draft": "CREATED",
    "confirmed": "CONFIRMED",
    "partially_paid": "CONFIRMED",
    "paid": "CONFIRMED",
    "fulfilled": "DELIVERED",
    "cancelled": "CANCELLED",
    "voided": "CANCELLED",
    "returned": "RETURNED",
}


def map_order_status_for_client(internal_status: str) -> str:
    """Map internal order status to client-visible status."""
    return CLIENT_VISIBLE_STATUSES.get(internal_status, internal_status.upper())
