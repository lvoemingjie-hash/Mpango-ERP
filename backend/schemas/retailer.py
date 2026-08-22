from __future__ import annotations

from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, EmailStr, model_validator, Field
from schemas.base import CamelModel


class RetailerRegisterRequest(BaseModel):
    """Dual-entry retailer registration (DC-12R1-MVP-L1-J1-H2-A-R1).

    Exactly ONE of ``invitation_code`` (entry A: wholesaler-shared invite)
    or ``join_intent`` (entry B: verified supplier-code self-join) must be
    present — submitting both, or neither, is rejected. There is NO
    ``wholesaler_id`` field: the bound wholesaler is resolved exclusively
    server-side from the verified credential. Email is REQUIRED — the
    credential lifecycle delivers the setup-password email to it.
    """

    invitation_code: Optional[str] = Field(None, description="Invitation code (entry A)")
    join_intent: Optional[str] = Field(None, description="Signed join intent (entry B)")
    phone: str = Field(..., min_length=1, max_length=32, description="Retailer phone")
    name: Optional[str] = Field(None, description="Retailer name")
    email: EmailStr = Field(..., description="Retailer email (required)")
    address: Optional[str] = Field(None, description="Retailer address")

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def _exactly_one_entry_credential(self) -> "RetailerRegisterRequest":
        has_invite = self.invitation_code is not None
        has_intent = self.join_intent is not None
        if has_invite == has_intent:  # both present, or neither
            raise ValueError("Provide exactly one of invitation_code or join_intent")
        return self


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
    # R1: server-verified supplier portal code for the login handoff
    # (/retail/login?w=<code>). Derived exclusively from the server-side
    # resolution context — never from client input.
    wholesaler_code: str

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
    # R1 dual-entry: how this relationship started. Derived server-side from
    # the used-invitation linkage ("invite") vs its absence ("code") — no
    # client input involved.
    join_source: str = Field("code", description="Join source: invite | code")

    model_config = {"from_attributes": True}


class RetailerListData(BaseModel):
    """Paginated list of retailers bound to the current wholesaler."""
    items: List[RetailerWithBinding] = Field(default_factory=list)
    pagination: dict = Field(default_factory=dict)

    model_config = {"from_attributes": True}
