"""
S7-4-T3 / S7-5: Report API Schemas — Pydantic validation for report CRUD.

🔒 Security: owner_id is NEVER accepted from the client.
    It is forced server-side from the authenticated user context.

🔒 S7-4-C3′: ACL entries are validated at schema level.
    Only user:<id>, role:<name>, tenant:* are accepted.

🔒 S7-5-C1: Config uses strong-typed ReportConfig from core.bi.
    All widget types, chart types, data sources, and metrics are Enums.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from core.bi.report_config import ReportConfig  # S7-5: Strong-typed contract


# ============================================================================
# Request schemas
# ============================================================================

class CreateReportRequest(BaseModel):
    """Request body for POST /api/bi/assets/reports."""
    title: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="Human-readable report name",
    )
    description: str = Field(
        default="",
        max_length=2048,
        description="Business-level description",
    )
    domain: str = Field(
        default="custom",
        min_length=1,
        max_length=50,
        description="BI domain (e.g., 'sales', 'finance', 'custom')",
    )
    config: ReportConfig = Field(
        ...,
        description="Report configuration (layout + widgets)",
    )
    acl: list[str] = Field(
        default_factory=list,
        description="Optional ACL entries for sharing",
    )

    @field_validator("acl", mode="before")
    @classmethod
    def validate_acl_entries(cls, v: list[str]) -> list[str]:
        """Validate ACL entry format."""
        if v is None:
            return []
        valid_prefixes = ("user:", "role:", "tenant:")
        for entry in v:
            if not isinstance(entry, str):
                raise ValueError(f"ACL entry must be a string, got {type(entry)}")
            if not any(entry.startswith(p) for p in valid_prefixes):
                raise ValueError(
                    f"Invalid ACL entry '{entry}'. "
                    f"Must start with one of: {valid_prefixes}"
                )
            prefix, _, value = entry.partition(":")
            if not value.strip():
                raise ValueError(f"ACL entry '{entry}' has empty value after prefix")
        return v


class UpdateReportRequest(BaseModel):
    """Request body for PATCH /api/bi/assets/reports/{report_id}."""
    title: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=256,
    )
    description: Optional[str] = Field(
        default=None,
        max_length=2048,
    )
    config: Optional[ReportConfig] = None
    acl: Optional[list[str]] = None

    @field_validator("acl", mode="before")
    @classmethod
    def validate_acl_entries(cls, v):
        """Validate ACL entry format (same as create)."""
        if v is None:
            return None
        valid_prefixes = ("user:", "role:", "tenant:")
        for entry in v:
            if not isinstance(entry, str):
                raise ValueError(f"ACL entry must be a string, got {type(entry)}")
            if not any(entry.startswith(p) for p in valid_prefixes):
                raise ValueError(
                    f"Invalid ACL entry '{entry}'. "
                    f"Must start with one of: {valid_prefixes}"
                )
            prefix, _, value = entry.partition(":")
            if not value.strip():
                raise ValueError(f"ACL entry '{entry}' has empty value after prefix")
        return v


# ============================================================================
# Response schemas
# ============================================================================

class ReportResponse(BaseModel):
    """Response body for report endpoints."""
    id: UUID
    urn: str
    title: str
    description: str
    domain: str
    config: dict
    owner_id: UUID
    acl: list[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CreateReportResponse(BaseModel):
    """Response body for POST /api/bi/assets/reports."""
    id: UUID
    urn: str
    title: str
    message: str = "Report created successfully"
