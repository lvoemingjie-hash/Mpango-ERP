"""S3 accepts only price strings and an explicit timezone-aware deadline."""
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictInt, StrictStr


class NegotiationLine(BaseModel):
    model_config = ConfigDict(extra='forbid')
    sku_id: UUID
    unit_price: StrictStr = Field(min_length=1, max_length=40)


class ProposalCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    lines: list[NegotiationLine] = Field(min_length=1, max_length=100)
    expires_at: AwareDatetime


class ProposalDecision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: StrictInt = Field(ge=1)
    digest: StrictStr = Field(pattern=r'^[0-9a-f]{64}$')
