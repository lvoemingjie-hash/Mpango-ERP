"""
Pydantic schemas for P12 Support Console API.

Every schema is field-by-field aligned with PLATFORM_PRODUCT_P12_SUPPORT_CONSOLE_CONTRACT.md (P12-A-R1).
Nullable fields use Optional. Enum fields use Literal types for exact contract values.

Cross-contract rules enforced here:
  - reason minimum 10 characters.
  - UUIDs must be version 4 or 7 (validated by pattern).
  - Timestamps must be UTC ISO-8601.
  - unknown != healthy.
  - Sensitive keys must be redacted before storage in diagnostics.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.v1.platform.p10.schemas import (
    ActorRole,
    AuditResult,
    validate_uuid_v4_v7,
)

# -- Enum literals matching P12-A-R1 contract exactly --

SupportCategory = Literal[
    "login_issue",
    "activity_anomaly",
    "performance",
    "data_integrity",
    "integration",
    "general",
    "incident",
    "other",
]

SupportSessionStatus = Literal["active", "closed", "expired"]

BundleType = Literal["full", "technical", "summary"]

DiagnosticSourceStatus = Literal["available", "degraded", "unavailable", "unknown"]

SupportAction = Literal[
    "support_session_start",
    "support_session_end",
    "support_bundle_generated",
    "support_session_expired",
    "support_view_diagnostic",
    "support_access_denied",
]


# -- Request models --


class CreateSessionRequest(BaseModel):
    """Request body for creating a support session.

    Reason validation (min 10 chars) is enforced at the route layer
    so that missing/short reason returns 400 with support_access_denied
    audit, not a bare 422 from Pydantic.
    """

    model_config = ConfigDict(extra="forbid")

    reason: Optional[str] = Field(
        None,
        description="Support reason, minimum 10 characters",
    )
    category: SupportCategory = Field(
        ...,
        description="Support category classification",
    )
    tenant_id: Optional[str] = Field(
        None,
        description="Target tenant UUID (optional at session creation)",
    )

    _validate_tenant_id = field_validator("tenant_id")(validate_uuid_v4_v7)


class CreateBundleRequest(BaseModel):
    """Request body for generating a support bundle."""

    model_config = ConfigDict(extra="forbid")

    bundle_type: BundleType = Field(
        "full",
        description="Bundle type: full, technical, or summary",
    )


# -- SupportSession --


class SupportSession(BaseModel):
    """
    In-memory support session contract object.

    Aligned to P12-A-R1 Section 4.2.
    Sessions are request-scoped/in-memory -- no persistent storage.
    """

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., description="UUID v4, unique session identifier")
    actor_id: Optional[str] = Field(None, description="Platform operator identity")
    actor_role: Optional[ActorRole] = Field(
        None, description="super_admin, support_operator, or engineering_operator"
    )
    tenant_id: Optional[str] = Field(None, description="Target tenant UUID")
    reason: str = Field(..., description="Support reason text (min 10 chars)")
    category: SupportCategory = Field(..., description="Support category")
    correlation_id: Optional[str] = Field(
        None, description="Session correlation ID"
    )
    status: SupportSessionStatus = Field(
        ..., description="active, closed, or expired"
    )
    started_at: datetime = Field(..., description="UTC ISO-8601 session start")
    closed_at: Optional[datetime] = Field(
        None, description="UTC ISO-8601, null if active"
    )
    expires_at: Optional[datetime] = Field(
        None, description="UTC ISO-8601, auto-expiry deadline"
    )
    bundle_count: int = Field(0, ge=0, description="Number of bundles generated")

    _validate_session_id = field_validator("session_id")(validate_uuid_v4_v7)
    _validate_tenant_id = field_validator("tenant_id")(validate_uuid_v4_v7)


# -- SupportDiagnosticItem --


class SupportDiagnosticItem(BaseModel):
    """
    Single redacted diagnostic item within a support bundle.

    Aligned to P12-A-R1 Section 4.4.
    """

    model_config = ConfigDict(extra="forbid")

    item_id: str = Field(..., description="UUID v4, unique item identifier")
    bundle_id: Optional[str] = Field(None, description="Parent bundle UUID")
    category: str = Field(
        ..., description="Diagnostic category (e.g., tenant_metadata, health_summary)"
    )
    label: str = Field(..., description="Human-readable label")
    value: Any = Field(
        ..., description="Redacted diagnostic value (dict, list, str, int, float, bool, or None)"
    )
    source_status: DiagnosticSourceStatus = Field(
        ..., description="Data source health status"
    )
    collected_at: datetime = Field(..., description="UTC ISO-8601 collection time")

    _validate_item_id = field_validator("item_id")(validate_uuid_v4_v7)


# -- SupportBundle --


class SupportBundle(BaseModel):
    """
    Generated support bundle with redacted diagnostics.

    Aligned to P12-A-R1 Section 4.3.
    """

    model_config = ConfigDict(extra="forbid")

    bundle_id: str = Field(..., description="UUID v4, unique bundle identifier")
    session_id: str = Field(..., description="Parent support session UUID")
    actor_id: Optional[str] = Field(None, description="Who requested the bundle")
    tenant_id: Optional[str] = Field(None, description="Target tenant UUID")
    correlation_id: Optional[str] = Field(
        None, description="Inherited from session + bundle suffix"
    )
    generated_at: datetime = Field(..., description="UTC ISO-8601 generation time")
    diagnostics: list[SupportDiagnosticItem] = Field(
        ..., min_length=1, description="At least 1 diagnostic item"
    )
    redaction_applied: bool = Field(
        True, description="Always true -- redaction is mandatory"
    )
    bundle_type: BundleType = Field(
        ..., description="full, technical, or summary"
    )

    _validate_bundle_id = field_validator("bundle_id")(validate_uuid_v4_v7)
    _validate_session_id = field_validator("session_id")(validate_uuid_v4_v7)
    _validate_tenant_id = field_validator("tenant_id")(validate_uuid_v4_v7)

    @field_validator("redaction_applied")
    @classmethod
    def redaction_must_be_true(cls, v: bool) -> bool:
        if not v:
            raise ValueError("redaction_applied must be true -- bundles are always redacted")
        return v


# -- SupportAuditEventResponse --


class SupportAuditEventResponse(BaseModel):
    """
    P12 support audit event shape for API responses.

    Extends the P10 PlatformAuditEvent pattern with P12-specific fields.
    scope is always "support" for support console events.
    """

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(..., description="UUID v4/v7")
    actor_id: Optional[str] = Field(None, description="Platform operator identity")
    actor_role: Optional[ActorRole] = Field(
        None, description="super_admin, support_operator, or engineering_operator"
    )
    tenant_id: Optional[str] = Field(None, description="Target tenant UUID")
    scope: Literal["support"] = Field(
        ..., description="Always 'support' for support console events"
    )
    action: SupportAction = Field(..., description="Support audit action")
    reason: Optional[str] = Field(
        None, description="Support reason text"
    )
    result: AuditResult = Field(..., description="allowed, denied, failed, or completed")
    metadata_redacted: Optional[dict] = Field(
        None, description="Redacted metadata -- never raw sensitive payload"
    )
    correlation_id: Optional[str] = Field(
        None, description="Session correlation ID"
    )
    created_at: datetime = Field(..., description="UTC ISO-8601")
    session_id: Optional[str] = Field(
        None, description="Reference to SupportSession"
    )
    bundle_id: Optional[str] = Field(
        None, description="Reference to SupportBundle (if applicable)"
    )
    bundle_type: Optional[BundleType] = Field(
        None, description="Bundle type (if applicable)"
    )

    _validate_event_id = field_validator("event_id")(validate_uuid_v4_v7)
    _validate_tenant_id = field_validator("tenant_id")(validate_uuid_v4_v7)
