from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional, List

from pydantic import BaseModel, Field
from schemas.base import CamelModel


class StockViewRead(CamelModel):
    """v0.1.9: CamelModel adapter (accepts camelCase input)"""
    sku_id: str
    sku_code: str
    sku_name: str
    quantity_on_hand: Decimal
    quantity_reserved: Decimal
    quantity_available: Decimal
    updated_at: datetime


class InventoryAdjustRequest(BaseModel):
    """Request body for POST /inventory/adjust."""
    sku_code: str = Field(..., min_length=1, max_length=64, description="SKU code to adjust")
    quantity: Decimal = Field(..., description="Signed adjustment amount (+/- allowed)")
    reason: str = Field(..., min_length=1, max_length=500, description="Reason: stocktake / damage / correction")

    model_config = {"from_attributes": True}


class InventoryAdjustResponse(CamelModel):
    """Response for a successful inventory adjustment."""
    sku_code: str
    quantity_before: Decimal
    quantity_after: Decimal
    adjustment: Decimal
    reason: str


class MovementLogEntry(CamelModel):
    """A single inventory movement log entry."""
    id: str
    sku_id: str
    sku_code: Optional[str] = None
    movement_type: str
    quantity: Decimal
    quantity_before: Decimal
    quantity_after: Decimal
    reason: Optional[str] = None
    reference_type: Optional[str] = None
    reference_id: Optional[str] = None
    created_at: datetime
    created_by: Optional[str] = None


class MovementLogListData(BaseModel):
    """Paginated movement log."""
    items: List[MovementLogEntry] = Field(default_factory=list)
    pagination: dict = Field(default_factory=dict)

    model_config = {"from_attributes": True}
