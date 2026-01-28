from __future__ import annotations

from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field


class RetailerRegisterRequest(BaseModel):
    invitation_code: str = Field(..., description="Invitation code")
    phone: str = Field(..., min_length=1, max_length=32, description="Retailer phone")
    name: Optional[str] = Field(None, description="Retailer name")
    email: Optional[str] = Field(None, description="Retailer email")
    address: Optional[str] = Field(None, description="Retailer address")

    model_config = {"from_attributes": True}


class RetailerData(BaseModel):
    id: str = Field(..., description="Retailer id")
    phone: str = Field(..., description="Retailer phone")
    name: Optional[str] = Field(None, description="Retailer name")
    email: Optional[str] = Field(None, description="Retailer email")
    address: Optional[str] = Field(None, description="Retailer address")

    model_config = {"from_attributes": True}


class BindingData(BaseModel):
    id: str = Field(..., description="Binding id")
    wholesaler_id: str = Field(..., description="Wholesaler id")
    retailer_id: str = Field(..., description="Retailer id")
    status: str = Field(..., description="Binding status")
    created_at: datetime = Field(..., description="Created timestamp")

    model_config = {"from_attributes": True}


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
