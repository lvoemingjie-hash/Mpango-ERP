from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class StockViewRead(BaseModel):
    sku_id: str
    sku_code: str
    sku_name: str
    quantity_on_hand: Decimal
    quantity_reserved: Decimal
    quantity_available: Decimal
    updated_at: datetime

    model_config = {"from_attributes": True}
