"""U4 intake workspace and staging API schemas."""
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

IntakeIssueSeverity = Literal["ERROR", "WARNING"]


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


class IntakeUploadRead(BaseModel):
    """Upload parser response payload."""

    upload_id: str
    workspace_id: str
    filename: str
    file_ext: str
    status: str
    row_count: int
    column_count: int
    headers_raw: list[str] = Field(default_factory=list)
    headers_normalized: dict[str, str] = Field(default_factory=dict)
    parse_summary: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    model_config = {"from_attributes": True}


class IntakeMappingRequest(BaseModel):
    """Request body for applying source-column to staging-field mapping."""

    mapping: dict[str, str] = Field(..., min_length=1)


class IntakeMappingRead(BaseModel):
    """Mapping update response payload."""

    workspace_id: str
    mapped_rows: int
    mapping: dict[str, str]
    status: IntakeWorkspaceStatus
    unit_default_note: str


class IntakeValidationRead(BaseModel):
    """Validation response payload."""

    workspace_id: str
    status: IntakeWorkspaceStatus
    row_count: int
    error_count: int
    warning_count: int


class IntakeApplyRead(BaseModel):
    """Response payload for applying staged intake rows to official SKUs."""

    workspace_id: str
    apply_status: str
    created_count: int
    row_count: int
    created_sku_ids: list[str] = Field(default_factory=list)


class IntakeProductRowRead(BaseModel):
    """Staged product row response payload."""

    row_id: str
    upload_id: str
    source_row_number: int
    row_index: int
    raw_values: dict[str, Any] = Field(default_factory=dict)
    normalized_values: dict[str, Any] = Field(default_factory=dict)
    mapping_version: int
    sku_code: Optional[str] = None
    name: Optional[str] = None
    unit: Optional[str] = None
    category: Optional[str] = None
    unit_price: Optional[str] = None
    barcode: Optional[str] = None
    review_status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class IntakeValidationIssueRead(BaseModel):
    """Validation issue response payload."""

    issue_id: str
    upload_id: Optional[str] = None
    row_id: Optional[str] = None
    source_row_number: Optional[int] = None
    severity: IntakeIssueSeverity
    code: str
    field: Optional[str] = None
    source_header: Optional[str] = None
    message: str
    is_blocking: bool
    created_at: datetime

    model_config = {"from_attributes": True}
