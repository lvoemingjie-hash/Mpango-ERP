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
# Product View Models
# ---------------------------------------------------------------------------

class ClientProductSummary(BaseModel):
    """Product card — used in list view."""
    id: str
    product_id: str
    catalog_product_id: str
    sellable_unit_id: str
    name: str
    sku_code: str
    category: Optional[str] = None
    unit: str
    package_quantity: Decimal
    price: Optional[Decimal] = Field(None, description="Selling price visible to retailer (null if not priced)")
    in_stock: bool
    stock_level: StockLevel
    can_order: bool = Field(..., description="True if active AND in stock AND has price")

    model_config = {"from_attributes": True}


class ClientProductDetail(BaseModel):
    """Product detail — full info for single product view."""
    id: str
    product_id: str
    catalog_product_id: str
    sellable_unit_id: str
    name: str
    sku_code: str
    description: Optional[str] = None
    category: Optional[str] = None
    unit: str
    package_quantity: Decimal
    price: Optional[Decimal] = Field(None, description="Selling price (null if not priced for this retailer)")
    in_stock: bool
    stock_level: StockLevel
    can_order: bool

    model_config = {"from_attributes": True}


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
