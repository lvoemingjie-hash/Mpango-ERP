from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel
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
