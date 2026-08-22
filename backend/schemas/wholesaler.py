from typing import Optional
from datetime import datetime
from pydantic import AliasGenerator, BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class WholesalerBase(BaseModel):
    """批发商基础字段"""
    code: str
    name: str
    address: Optional[str] = None
    contact: Optional[str] = None
    plan_type: Optional[str] = None


class WholesalerCreate(WholesalerBase):
    """创建批发商"""
    code: str = Field(
        ...,
        min_length=3,
        max_length=32,
        pattern=r"^[A-Z0-9]+$",
        description="Tenant code (uppercase alphanumeric)",
    )


class WholesalerUpdate(BaseModel):
    """更新批发商"""
    name: Optional[str] = None
    address: Optional[str] = None
    contact: Optional[str] = None
    plan_type: Optional[str] = None


class WholesalerRead(WholesalerBase):
    """批发商响应 — v0.1.9: CamelModel adapter (accepts camelCase input)"""
    id: str
    schema_name: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=AliasGenerator(validation_alias=to_camel),
    )


class WholesalerResponse(BaseModel):
    """Single wholesaler response wrapper."""
    success: bool = Field(True, description="Always true for successful response")
    data: WholesalerRead = Field(..., description="Wholesaler data")
    message: Optional[str] = Field(None, description="Optional message")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Response timestamp"
    )

    model_config = {"from_attributes": True}


class WholesalerListResponse(BaseModel):
    """Paginated wholesaler list response."""
    success: bool = Field(True, description="Always true for successful response")
    data: dict = Field(
        ...,
        description="Data object with items and pagination"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Response timestamp"
    )

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# DC-12R1-MVP-L1-J1-H2-A-R1: public supplier-code lookup (dual-entry entry B)
# ---------------------------------------------------------------------------

class WholesalerCodeLookupRequest(BaseModel):
    """Public lookup by supplier portal code. Code regex mirrors the DB."""

    code: str = Field(..., min_length=1, max_length=32)

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)


class WholesalerJoinPreviewData(BaseModel):
    """SAFE preview only: identity display fields plus a short-lived signed
    join intent. No internal ids, no raw contact data, no plan metadata."""

    found: bool = Field(..., description="Whether the code resolved to a supplier")
    name: Optional[str] = Field(None, description="Supplier display name")
    region: Optional[str] = Field(None, description="Supplier region/address summary")
    contact_masked: Optional[str] = Field(None, description="Masked contact")
    join_intent: Optional[str] = Field(None, description="Signed short-lived join intent")
    expires_at: Optional[datetime] = Field(None, description="Join intent expiry")

    model_config = ConfigDict(populate_by_name=True)
