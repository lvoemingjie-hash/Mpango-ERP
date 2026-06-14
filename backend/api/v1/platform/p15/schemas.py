"""
Pydantic schemas for P15 Incident Triage (read-only snapshot API).

Aligned to docs/ai/PLATFORM_PRODUCT_P15_INCIDENT_TRIAGE_CONTRACT.md (P15-A).

Contract rules (carried from P13/P14):
  - source_status on every telemetry-derived value (not bare 0 for unknown).
  - Nullable totals when a source is unavailable (null != 0).
  - unknown != healthy. unavailable_reason / degraded_reason always visible.
  - No raw payloads, no credentials, no DSN, no host/port, no tenant business records.
  - extra="forbid" on input for all response models.

P15-A is contract-only; P15-B implements these as a read-only snapshot adapter.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from api.v1.platform.p13.schemas import DatabaseHealth, OpsSourceStatus
from api.v1.platform.p10.schemas import HealthStatus

# -- Enum literals matching the P15-A contract --

IncidentCategory = Literal[
    "database", "system", "api", "tenant_health", "support_issue"
]

IncidentSeverity = Literal[
    "info", "warning", "degraded", "unhealthy", "unknown"
]

IncidentOwner = Literal["support", "engineering", "dba", "platform"]

IncidentConfidence = Literal["low", "medium", "high"]


# -- 4.1 IncidentSignal --


class IncidentSignal(BaseModel):
    """A single observed anomaly signal from an existing read-only source."""

    model_config = ConfigDict(extra="forbid")

    signal_id: str = Field(..., description="Stable within one snapshot; not persisted")
    kind: IncidentCategory = Field(..., description="Suggested incident category")
    severity: IncidentSeverity = Field(..., description="unknown != healthy")
    source_ref: str = Field(..., description="Originating P10/P13/P14 endpoint or field")
    observed_value: Optional[str] = Field(
        None, description="Live value or null when source unavailable"
    )
    source_status: OpsSourceStatus = Field(..., description="available|unavailable|unknown")
    unavailable_reason: Optional[str] = Field(
        None, description="Visible reason when source unavailable/unknown"
    )
    degraded_reason: Optional[str] = Field(
        None, description="Visible reason when degraded/unhealthy"
    )
    observed_at: datetime = Field(..., description="UTC ISO-8601 freshness")


# -- 4.2 IncidentClassification --


class IncidentClassification(BaseModel):
    """Operator-assigned label. Suggestion only -- never an automated action."""

    model_config = ConfigDict(extra="forbid")

    category: IncidentCategory = Field(..., description="Required category")
    confidence: IncidentConfidence = Field(..., description="Operator confidence")
    suggested_owner: IncidentOwner = Field(..., description="Handoff target hint")
    notes: Optional[str] = Field(
        None, description="Free text; redacted before any handoff"
    )


# -- 4.3 IncidentRunbookHint --


class IncidentRunbookHint(BaseModel):
    """Static, doc-driven hint. Observation steps only -- no action steps."""

    model_config = ConfigDict(extra="forbid")

    category: IncidentCategory = Field(..., description="Key")
    checklist: List[str] = Field(
        default_factory=list, description="Read-only observation steps"
    )
    do_not: List[str] = Field(
        default_factory=list, description="Explicit prohibitions (no repair/impersonation/business query)"
    )
    handoff_to: IncidentOwner = Field(..., description="Suggested owner")


# -- 4.4 IncidentTriageSnapshot --


class IncidentTriageSnapshot(BaseModel):
    """Aggregated read-only triage view.

    On any source failure the snapshot still returns with graceful_degraded=true
    and the failing component marked unknown/unavailable with a reason -- never a
    fabricated healthy/0.
    """

    model_config = ConfigDict(extra="forbid")

    snapshot_id: str = Field(..., description="Ephemeral; not persisted")
    generated_at: datetime = Field(..., description="UTC ISO-8601")
    overall_status: HealthStatus = Field(
        ..., description="healthy|degraded|unhealthy|unknown (unknown != healthy)"
    )
    signals: List[IncidentSignal] = Field(
        default_factory=list, description="Aggregated P10/P13/P14 signals"
    )
    database_probe: Optional[DatabaseHealth] = Field(
        None, description="P14 live DB probe (latency/pool/status)"
    )
    system_health_overall: Optional[HealthStatus] = Field(
        None, description="P10 system health overall status (counts/status only)"
    )
    tenant_health_sample_count: Optional[int] = Field(
        None, ge=0, description="P10 tenant count, null if unavailable (no business records)"
    )
    tenant_health_unhealthy_count: Optional[int] = Field(
        None, ge=0, description="P10 tenants in non-healthy state, null if unavailable"
    )
    degraded_reason: Optional[str] = Field(
        None, description="Why overall is degraded, if so"
    )
    unavailable_reason: Optional[str] = Field(
        None, description="Why a primary source is missing"
    )
    graceful_degraded: bool = Field(
        ..., description="True when assembled despite a source failure"
    )


# -- 4.5 IncidentHandoffSummary --


class IncidentHandoffSummary(BaseModel):
    """Redacted package handed to support/engineering.

    No raw payloads, credentials, DSN, host/port, or tenant business records.
    """

    model_config = ConfigDict(extra="forbid")

    summary_id: str = Field(..., description="Ephemeral")
    created_at: datetime = Field(..., description="UTC ISO-8601")
    classification: IncidentClassification = Field(..., description="Operator label")
    signals: List[IncidentSignal] = Field(
        default_factory=list, description="Redacted (counts/paths/statuses)"
    )
    runbook_hint: Optional[IncidentRunbookHint] = Field(
        None, description="Doc-driven checklist"
    )
    redacted: bool = Field(..., description="Always true in P15; allowlist applied")
    sensitive_keys_dropped: int = Field(
        ..., ge=0, description="Count of redacted keys (diagnostic only)"
    )
