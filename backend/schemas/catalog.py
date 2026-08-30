"""Catalog-product and sellable-unit API contracts."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from schemas.base import CamelModel


class SellableUnitCreate(BaseModel):
    sku_code: str = Field(..., min_length=1, max_length=64)
    unit: str = Field(default="unit", min_length=1, max_length=32)
    package_quantity: Decimal = Field(default=Decimal("1.000"), gt=0, max_digits=12, decimal_places=3)
    is_active: bool = True


class CatalogProductCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    category: Optional[str] = Field(default=None, max_length=64)
    is_active: bool = True
    sellable_units: list[SellableUnitCreate] = Field(..., min_length=1, max_length=50)

    @model_validator(mode="after")
    def unique_codes(self):
        codes = [unit.sku_code for unit in self.sellable_units]
        if len(codes) != len(set(codes)):
            raise ValueError("sellable unit SKU codes must be unique")
        return self


class CatalogProductUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    category: Optional[str] = Field(default=None, max_length=64)
    is_active: Optional[bool] = None


class SellableUnitUpdate(BaseModel):
    unit: Optional[str] = Field(default=None, min_length=1, max_length=32)
    package_quantity: Optional[Decimal] = Field(default=None, gt=0, max_digits=12, decimal_places=3)
    is_active: Optional[bool] = None


class SellableUnitRead(CamelModel):
    id: str
    catalog_product_id: str
    sku_code: str
    unit: str
    package_quantity: Decimal
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CatalogProductRead(CamelModel):
    id: str
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    is_active: bool
    sellable_units: list[SellableUnitRead]
    created_at: datetime
    updated_at: datetime
