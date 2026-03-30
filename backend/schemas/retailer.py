from __future__ import annotations

from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field
from schemas.base import CamelModel


class RetailerRegisterRequest(BaseModel):
    invitation_code: str = Field(..., description="Invitation code")
    phone: str = Field(..., min_length=1, max_length=32, description="Retailer phone")
    name: Optional[str] = Field(None, description="Retailer name")
    email: Optional[str] = Field(None, description="Retailer email")
    address: Optional[str] = Field(None, description="Retailer address")

    model_config = {"from_attributes": True}


class RetailerData(CamelModel):
    """v0.1.9: CamelModel adapter (accepts camelCase input)"""
    id: str = Field(..., description="Retailer id")
    phone: str = Field(..., description="Retailer phone")
    name: Optional[str] = Field(None, description="Retailer name")
    email: Optional[str] = Field(None, description="Retailer email")
    address: Optional[str] = Field(None, description="Retailer address")


class BindingData(CamelModel):
    """v0.1.9: CamelModel adapter (accepts camelCase input)"""
    id: str = Field(..., description="Binding id")
    wholesaler_id: str = Field(..., description="Wholesaler id")
    retailer_id: str = Field(..., description="Retailer id")
    status: str = Field(..., description="Binding status")
    created_at: datetime = Field(..., description="Created timestamp")


class RetailerRegisterResponseData(BaseModel):
    retailer: RetailerData
    binding: BindingData

    model_config = {"from_attributes": True}


class BindingListItem(BaseModel):
    binding: BindingData
    retailer: Optional[RetailerData] = None

    model_config = {"from_attributes": True}


class BindingListData(BaseModel):
    items: List[BindingListItem] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class RetailerWithBinding(BaseModel):
    """Retailer data enriched with binding metadata for CRM list."""
    retailer: RetailerData
    binding_status: str = Field(..., description="Binding status (active / inactive)")
    bound_at: datetime = Field(..., description="When the retailer was bound")

    model_config = {"from_attributes": True}


class RetailerListData(BaseModel):
    """Paginated list of retailers bound to the current wholesaler."""
    items: List[RetailerWithBinding] = Field(default_factory=list)
    pagination: dict = Field(default_factory=dict)

    model_config = {"from_attributes": True}
