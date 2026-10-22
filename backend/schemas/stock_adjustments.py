from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt


class AdjustmentPolicyEdit(BaseModel):
    model_config = ConfigDict(extra='forbid')
    approver_ids: list[UUID] = Field(min_length=1, max_length=100)
    owner_direct_enabled: StrictBool
    expected_policy_version: StrictInt = Field(gt=0)


class AdjustmentCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    sellable_unit_id: UUID
    quantity_delta: str = Field(min_length=1, max_length=64)
    reason_kind: Literal['loss', 'shrink', 'gain', 'correction']
    reason: str = Field(min_length=1, max_length=1000)
    expected_stock_revision: StrictInt = Field(gt=0)
    expected_policy_version: StrictInt = Field(gt=0)


class AdjustmentDecision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_version: StrictInt = Field(gt=0)
    reason: str = Field(default='', max_length=1000)
