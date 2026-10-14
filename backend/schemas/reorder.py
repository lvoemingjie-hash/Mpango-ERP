"""S2 requests express a decision for every historical line, never a price."""
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from services.pricing_quote_service import QUOTE_TOKEN_MAX_LENGTH


class ReorderSelection(BaseModel):
    source_item_id: str
    action: Literal['keep', 'remove', 'replace']
    sellable_unit_id: Optional[str] = None
    quantity: Optional[int] = Field(None, ge=1, le=10000, strict=True)
    model_config = {'extra': 'forbid'}

    @field_validator('source_item_id', 'sellable_unit_id')
    @classmethod
    def normalize_uuid(cls, value):
        return str(UUID(value)) if value is not None else None

    @model_validator(mode='after')
    def require_explicit_replacement(self):
        if self.action == 'replace':
            if self.sellable_unit_id is None or self.quantity is None:
                raise ValueError('Replacement requires an explicit sellable unit and quantity')
        elif self.sellable_unit_id is not None or self.quantity is not None:
            raise ValueError('Keep/remove use the historical line, without replacement fields')
        return self


class ReorderQuoteRequest(BaseModel):
    selections: Optional[list[ReorderSelection]] = Field(None, max_length=100)
    model_config = {'extra': 'forbid'}


class ReorderCreateRequest(BaseModel):
    selections: list[ReorderSelection] = Field(..., min_length=1, max_length=100)
    quote_token: str = Field(..., min_length=1, max_length=QUOTE_TOKEN_MAX_LENGTH)
    notes: Optional[str] = Field(None, max_length=1000)
    model_config = {'extra': 'forbid'}


class ClientReorderCreateRequest(ReorderCreateRequest):
    source_order_id: UUID


class ReorderOriginalLine(BaseModel):
    product_name: str
    sku_code: str
    sellable_unit_id: Optional[str]
    identity_status: str
    unit: Optional[str]
    package_quantity: Optional[str]
    display_label: Optional[str]
    quantity: int
    unit_price: str
    subtotal: str


class ReorderRow(BaseModel):
    source_item_id: str
    original: ReorderOriginalLine
    selection: ReorderSelection
    status: Literal['READY', 'UNAVAILABLE', 'REMOVED']
    reason: Optional[str] = None
    current: Optional[dict] = None
    stock_warning: Optional[Literal['INSUFFICIENT_STOCK']] = None


class ReorderPreview(BaseModel):
    source_order_id: str
    order_basis: Literal['HISTORICAL_ITEM_ID'] = 'HISTORICAL_ITEM_ID'
    historical_total: str
    historical_currency: Optional[str]
    historical_currency_status: str
    rows: list[ReorderRow]
    ready: bool
    quote: Optional[dict]
    current_total: Optional[str]
    current_currency: str
    delta: Optional[str]
