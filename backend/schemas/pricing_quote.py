"""S1 quote requests never accept an authoritative client amount."""
from typing import Optional

from pydantic import BaseModel, Field
from schemas.order import WholesalerOrderItemCreate


class QuoteRequest(BaseModel):
    items: list[WholesalerOrderItemCreate] = Field(..., min_length=1, max_length=100)
    retailer_id: Optional[str] = None
    model_config = {'extra': 'forbid'}
