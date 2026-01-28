from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class SKUCreateRequest(BaseModel):
    sku_code: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    unit: str = Field(default="unit", min_length=1, max_length=32)
    category: Optional[str] = Field(default=None, max_length=64)
    is_active: bool = True


class SKUUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    unit: Optional[str] = Field(default=None, min_length=1, max_length=32)
    category: Optional[str] = Field(default=None, max_length=64)
    is_active: Optional[bool] = None


class SKURead(BaseModel):
    id: str
    sku_code: str
    name: str
    description: Optional[str] = None
    unit: str
    category: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
