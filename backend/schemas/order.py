"""
Order Pydantic schemas.
Implements openapi.yaml order component schemas.
"""
from typing import List
from datetime import datetime
from decimal import Decimal
from enum import Enum
from pydantic import BaseModel, Field


class OrderStatus(str, Enum):
    """
    Order status enum.
    Implements openapi.yaml OrderStatus schema.
    """
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    CANCELLED = "cancelled"


# ============================================================================
# Order Item Schemas
# ============================================================================

class OrderItemCreate(BaseModel):
    """
    Order item creation request.
    Implements openapi.yaml OrderItemCreate schema.
    """
    product_id: str = Field(..., description="Product UUID")
    quantity: int = Field(..., ge=1, description="Item quantity")
    
    model_config = {"from_attributes": True}


class OrderItem(BaseModel):
    """
    Order item read schema.
    Implements openapi.yaml OrderItem schema.
    """
    id: str = Field(..., description="Order item UUID")
    product_id: str = Field(..., description="Product UUID")
    product_name: str | None = Field(None, description="Product name")
    quantity: int = Field(..., description="Item quantity")
    unit_price: Decimal = Field(..., description="Unit price")
    subtotal: Decimal = Field(..., description="Line item subtotal")
    
    model_config = {"from_attributes": True}


# ============================================================================
# Order Schemas
# ============================================================================

class OrderCreateRequest(BaseModel):
    """
    Order creation request.
    Implements openapi.yaml OrderCreateRequest schema.
    """
    retailer_id: str = Field(..., description="Retailer UUID")
    items: List[OrderItemCreate] = Field(
        ...,
        min_length=1,
        description="Order items"
    )
    notes: str | None = Field(None, description="Order notes")
    
    model_config = {"from_attributes": True}


class Order(BaseModel):
    """
    Order read schema.
    Implements openapi.yaml Order schema.
    """
    id: str = Field(..., description="Order UUID")
    retailer_id: str = Field(..., description="Retailer UUID")
    retailer_name: str | None = Field(None, description="Retailer name")
    status: OrderStatus = Field(..., description="Order status")
    total_amount: Decimal = Field(..., description="Order total amount")
    items: List[OrderItem] = Field(default_factory=list, description="Order items")
    notes: str | None = Field(None, description="Order notes")
    created_by: str | None = Field(None, description="Creator user UUID")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    
    model_config = {"from_attributes": True}


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
