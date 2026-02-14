from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field
from schemas.base import CamelModel


class PaymentMethod(str, Enum):
    cash = "cash"
    transfer = "transfer"
    credit = "credit"


class PaymentStatus(str, Enum):
    pending = "pending"
    completed = "completed"


class PaymentCreateRequest(BaseModel):
    order_id: str = Field(..., description="Order UUID")
    amount: Decimal = Field(..., gt=0, description="Payment amount")
    method: PaymentMethod = Field(..., description="Payment method")
    transaction_id: str | None = Field(None, description="External transaction reference (required for transfer)")

    model_config = {"from_attributes": True}


class PaymentData(CamelModel):
    """v0.1.9: CamelModel adapter (accepts camelCase input)"""
    id: str
    order_id: str
    retailer_id: str
    transaction_id: str | None
    amount: Decimal
    method: PaymentMethod
    status: PaymentStatus
    created_at: datetime
    updated_at: datetime


class PaymentResponse(BaseModel):
    success: bool = Field(True, description="Always true for successful response")
    data: PaymentData
    message: str | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"from_attributes": True}
