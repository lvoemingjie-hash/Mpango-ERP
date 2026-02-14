from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field
from schemas.base import CamelModel


class InvitationCreateRequest(BaseModel):
    retailer_phone: Optional[str] = Field(None, description="Optional target retailer phone")
    expires_at: Optional[datetime] = Field(None, description="Optional expiration timestamp")

    model_config = {"from_attributes": True}


class InvitationData(CamelModel):
    """v0.1.9: CamelModel adapter (accepts camelCase input)"""
    code: str = Field(..., description="Invitation code")
    status: str = Field(..., description="Invitation status")
    wholesaler_id: str = Field(..., description="Inviting wholesaler id")
    retailer_phone: Optional[str] = Field(None, description="Target retailer phone")
    expires_at: Optional[datetime] = Field(None, description="Expiration timestamp")
    created_at: datetime = Field(..., description="Created timestamp")


class InvitationLookupData(CamelModel):
    """v0.1.9: CamelModel adapter (accepts camelCase input)"""
    code: str = Field(..., description="Invitation code")
    usable: bool = Field(..., description="Whether invitation can be used")
    reason: Optional[str] = Field(None, description="Reason if not usable")
    status: Optional[str] = Field(None, description="Invitation status")
    wholesaler_id: Optional[str] = Field(None, description="Inviting wholesaler id")
    wholesaler_name: Optional[str] = Field(None, description="Inviting wholesaler name")
    expires_at: Optional[datetime] = Field(None, description="Expiration timestamp")
