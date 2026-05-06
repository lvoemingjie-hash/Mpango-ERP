"""
Order Pydantic schemas.
Implements openapi.yaml /orders/* endpoints.

S2.5: Enhanced input validation to prevent XSS and injection attacks.
Phase 5: Added PayOrderRequest for structured payment recording on order pay.
"""
from typing import List, Optional
from datetime import datetime
from decimal import Decimal
from enum import Enum
from pydantic import BaseModel, Field, field_validator
import re
from schemas.base import CamelModel


# S2.5: Regex patterns for input validation
SAFE_TEXT_PATTERN = re.compile(r'^[a-zA-Z0-9\s\-_.,!?@()]+$')
SAFE_CODE_PATTERN = re.compile(r'^[a-zA-Z0-9\-_]+$')


def validate_no_html_tags(v: str) -> str:
    """S2.5: Prevent HTML/script tags in text fields."""
    if v and ('<' in v or '>' in v or 'script' in v.lower()):
        raise ValueError("HTML tags and script content are not allowed")
    return v


class OrderStatus(str, Enum):
    """
    Order status enum.
    Implements openapi.yaml OrderStatus schema.

    Extended for S5-A Order State Machine with additional states.
    Must stay in sync with models.order.OrderStatus.
    """
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    FULFILLED = "fulfilled"
    CANCELLED = "cancelled"
    VOIDED = "voided"
    RETURNED = "returned"


# ============================================================================
# Order Item Schemas
# ============================================================================

class OrderItemCreate(BaseModel):
    """
    Order item creation request.
    Implements openapi.yaml OrderItemCreate schema.

    S2.5: Enhanced validation to prevent injection attacks.
    """
    product_name: str = Field(..., min_length=1, max_length=255, description="Product name snapshot")
    sku_code: str = Field(..., min_length=1, max_length=64, description="SKU code snapshot")
    quantity: int = Field(..., ge=1, le=10000, description="Item quantity")
    unit_price: Decimal = Field(..., ge=0, le=Decimal('999999.99'), description="Unit price")

    @field_validator("product_name")
    @classmethod
    def validate_product_name(cls, v: str) -> str:
        """S2.5: Validate product_name for XSS/injection."""
        v = validate_no_html_tags(v)
        if not SAFE_TEXT_PATTERN.match(v):
            raise ValueError("Product name contains invalid characters")
        return v

    @field_validator("sku_code")
    @classmethod
    def validate_sku_code(cls, v: str) -> str:
        """S2.5: Validate sku_code format."""
        if not SAFE_CODE_PATTERN.match(v):
            raise ValueError("SKU code contains invalid characters")
        return v

    model_config = {"from_attributes": True}


class OrderItem(CamelModel):
    """
    Order item read schema.
    Implements openapi.yaml OrderItem schema.
    v0.1.9: CamelModel adapter (accepts camelCase input)
    """
    id: str = Field(..., description="Order item UUID")
    product_name: str = Field(..., description="Product name snapshot")
    sku_code: str = Field(..., description="SKU code snapshot")
    quantity: int = Field(..., description="Item quantity")
    unit_price: Decimal = Field(..., description="Unit price")
    subtotal: Decimal = Field(..., description="Line item subtotal")


# ============================================================================
# Order Schemas
# ============================================================================

class OrderCreateRequest(BaseModel):
    """
    Order creation request.
    Implements openapi.yaml OrderCreateRequest schema.

    S2.5: Enhanced validation to prevent injection attacks.

    DEPRECATED for wholesaler use -- use WholesalerOrderCreateRequest instead.
    Retained for backward compatibility with any internal callers.
    """
    retailer_id: str = Field(..., min_length=36, max_length=36, description="Retailer UUID")
    items: List[OrderItemCreate] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Order items"
    )
    notes: str | None = Field(None, max_length=1000, description="Order notes")

    @field_validator("notes")
    @classmethod
    def validate_notes(cls, v: str | None) -> str | None:
        """S2.5: Validate notes for XSS/injection."""
        if v:
            v = validate_no_html_tags(v)
        return v

    model_config = {"from_attributes": True}


# ============================================================================
# Phase 4: Pricing-Safe Wholesaler Order Schemas
# ============================================================================

class WholesalerOrderItemCreate(BaseModel):
    """
    Wholesaler order item -- pricing-safe.

    Phase 4: The frontend sends ONLY sku_code + quantity.
    product_name and unit_price are resolved server-side from
    the SKU catalog and retailer_prices table respectively.
    Any client-supplied price is structurally impossible.
    """
    sku_code: str = Field(..., min_length=1, max_length=64, description="SKU code")
    quantity: int = Field(..., ge=1, le=10000, description="Item quantity")

    @field_validator("sku_code")
    @classmethod
    def validate_sku_code(cls, v: str) -> str:
        if not SAFE_CODE_PATTERN.match(v):
            raise ValueError("SKU code contains invalid characters")
        return v

    model_config = {"from_attributes": True}


class WholesalerOrderCreateRequest(BaseModel):
    """
    Wholesaler order creation request -- pricing-safe.

    Phase 4: Price authority lives in the backend.
    The request contains retailer_id, items (sku_code + quantity), and notes.
    No unit_price or product_name accepted from the client.
    """
    retailer_id: str = Field(..., min_length=36, max_length=36, description="Retailer UUID")
    items: List[WholesalerOrderItemCreate] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Order line items (sku_code + quantity only)"
    )
    notes: str | None = Field(None, max_length=1000, description="Order notes")

    @field_validator("notes")
    @classmethod
    def validate_notes(cls, v: str | None) -> str | None:
        if v:
            v = validate_no_html_tags(v)
        return v

    model_config = {"from_attributes": True}


# ============================================================================
# Phase 5: Structured Payment Recording on Order Pay
# ============================================================================

class PayOrderRequest(BaseModel):
    """
    Optional structured payment input for POST /orders/{order_id}/pay.

    Phase 5: All fields are optional. When provided, a Payment record is
    created alongside the order state transition. When omitted, the endpoint
    behaves exactly as before (state-only transition, backward compatible).

    Validation rules:
    - If `amount` is provided, it must be > 0
    - If `amount` is provided, `method` must also be provided
    - `transaction_id` is only meaningful for transfer method
    """
    method: Optional[str] = Field(
        None,
        description="Payment method: cash, transfer, credit",
    )
    amount: Optional[Decimal] = Field(
        None,
        gt=0,
        description="Payment amount (must be > 0)",
    )
    transaction_id: Optional[str] = Field(
        None,
        max_length=255,
        description="External transaction reference (for transfer/mobile_money)",
    )
    notes: Optional[str] = Field(
        None,
        max_length=1000,
        description="Payment notes",
    )

    @field_validator("notes")
    @classmethod
    def validate_notes(cls, v: str | None) -> str | None:
        if v:
            v = validate_no_html_tags(v)
        return v

    model_config = {"from_attributes": True}


class Order(CamelModel):
    """
    Order read schema.
    Implements openapi.yaml Order schema.
    v0.1.9: CamelModel adapter (accepts camelCase input)
    """
    id: str = Field(..., description="Order UUID")
    wholesaler_id: str = Field(..., description="Wholesaler/Tenant UUID")
    retailer_id: str = Field(..., description="Retailer UUID")
    retailer_name: str | None = Field(None, description="Retailer name")
    status: OrderStatus = Field(..., description="Order status")
    total_amount: Decimal = Field(..., description="Order total amount")
    items: List[OrderItem] = Field(default_factory=list, description="Order items")
    notes: str | None = Field(None, description="Order notes")
    created_by: str | None = Field(None, description="Creator user UUID")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


class OrderResponse(BaseModel):
    """
    Single order response.
    Implements openapi.yaml OrderResponse schema.
    """
    success: bool = Field(True, description="Always true for successful response")
    data: Order = Field(..., description="Order data")
    message: str | None = Field(None, description="Optional message")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Response timestamp"
    )

    model_config = {"from_attributes": True}


class OrderListResponse(BaseModel):
    """
    Paginated order list response.
    Implements openapi.yaml OrderListResponse schema.
    """
    success: bool = Field(True, description="Always true for successful response")
    data: dict = Field(
        ...,
        description="Data object with items and pagination"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Response timestamp"
    )

    model_config = {"from_attributes": True}


class OrderActionResponse(BaseModel):
    """
    Order action response (confirm/ship/cancel).
    Implements openapi.yaml OrderActionResponse schema.
    """
    success: bool = Field(True, description="Always true for successful response")
    data: dict = Field(
        ...,
        description="Data object with order_id and status"
    )
    message: str | None = Field(None, description="Action message")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Response timestamp"
    )

    model_config = {"from_attributes": True}
