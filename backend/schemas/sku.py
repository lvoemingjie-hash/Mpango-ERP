from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field
from schemas.base import CamelModel


class SKUCreateRequest(BaseModel):
    catalog_product_id: Optional[str] = Field(default=None, min_length=36, max_length=36)
    sku_code: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    unit: str = Field(default="unit", min_length=1, max_length=32)
    package_quantity: Decimal = Field(default=Decimal("1.000"), gt=0, max_digits=12, decimal_places=3)
    category: Optional[str] = Field(default=None, max_length=64)
    is_active: bool = True


class SKUUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    unit: Optional[str] = Field(default=None, min_length=1, max_length=32)
    package_quantity: Optional[Decimal] = Field(default=None, gt=0, max_digits=12, decimal_places=3)
    category: Optional[str] = Field(default=None, max_length=64)
    is_active: Optional[bool] = None


class SKURead(CamelModel):
    """v0.1.9: CamelModel adapter (accepts camelCase input)"""
    id: str
    catalog_product_id: Optional[str] = None
    sku_code: str
    name: str
    description: Optional[str] = None
    unit: str
    package_quantity: Decimal = Decimal("1.000")
    category: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
