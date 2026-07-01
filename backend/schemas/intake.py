"""U4-C intake workspace API schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


IntakeSourceType = Literal[
    "CUSTOMER_ONBOARDING",
    "CATALOG_REFRESH",
    "STOCK_INTAKE",
    "MOBILE_SCAN",
]

IntakeWorkspaceStatus = Literal[
    "DRAFT",
    "OPEN",
    "UPLOADED",
    "MAPPED",
    "VALIDATING",
    "NEEDS_REVIEW",
    "READY_FOR_EXPORT",
    "EXPORTED",
    "PUSHED_TO_ERP_PREVIEW",
    "CLOSED",
    "CANCELLED",
]


class IntakeWorkspaceCreateRequest(BaseModel):
    """Request body for POST /api/v1/intake/workspaces."""

    name: str = Field(..., min_length=1, max_length=160)
    description: Optional[str] = Field(None, max_length=5000)
    source_type: IntakeSourceType = "CUSTOMER_ONBOARDING"
    metadata: dict[str, Any] = Field(default_factory=dict)


class IntakeWorkspaceRead(BaseModel):
    """Workspace response payload."""

    workspace_id: str
    tenant_id: str
    name: str
    description: Optional[str] = None
    source_type: IntakeSourceType
    status: IntakeWorkspaceStatus
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
