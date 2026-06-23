"""Pydantic schemas for P18 Controlled Platform Actions (request skeleton).

Field-for-field aligned to
docs/ai/PLATFORM_PRODUCT_P18_CONTROLLED_ACTIONS_CONTRACT.md (P18-A).

This is a REQUEST SKELETON only (P18-B). No controlled action is executed.
Every response carries executed == False and states that the action was not
executed. The skeleton never mutates the P17 registry, tenant lifecycle,
operational flags, provisioning, backup, or any tenant business data.

Contract rules carried from P10/P17:
  - source_status on every derived value (never a bare 0 / false for unknown).
  - unknown != healthy / active / success; null != 0.
  - reason required on every request; idempotency_key required on every request.
  - metadata_redacted is redacted via an allowlist-style filter -- never a raw
    secret / credential / DSN / host / port / connection string / log line.
  - extra="forbid" on every model (no undeclared fields / leaks).
  - No tenant business records (orders, payments, invoices, customers).
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# -- Catalog / action vocabulary (mirrors the P18-A action_type enum) --

ActionType = Literal[
    "support_mode.on",
    "support_mode.off",
    "tenant.pause",
    "tenant.resume",
    "incident.flag_set",
    "incident.flag_clear",
    "provisioning.recheck",
    "backup.check",
    "backup.restore_test_request",
    "lifecycle.transition",
]

ActionClassification = Literal["read", "write", "write_request"]

AllowedActor = Literal["super_admin", "support_operator", "engineering_operator"]

RegistrySourceStatus = Literal["available", "unavailable", "unknown"]


# Skeleton result vocabulary. Maps to the P18-A result enum:
#   accepted  -> a recorded (NOT executed) request. P18-A "completed" is never
#                used because nothing executes in the skeleton.
#   denied    -> rejected (unsupported type / missing reason / missing
#                idempotency key / missing confirmation / unknown source).
#                Equivalent to P18-A "denied".
#   degraded  -> a degraded read path (provisioning.recheck / backup.check only).
#                Equivalent to P18-A "degraded".
#   duplicate -> repeat idempotency key, identical payload. P18-A "duplicate".
#   conflict  -> repeat idempotency key, different payload (a denied variant).
RequestResult = Literal["accepted", "denied", "degraded", "duplicate", "conflict"]


class ActionCatalogItem(BaseModel):
    """One entry in the closed controlled-action catalog."""

    model_config = ConfigDict(extra="forbid")

    action_type: ActionType = Field(..., description="Controlled action identifier")
    classification: ActionClassification = Field(
        ..., description="read (no state change), write (mutate registry/lifecycle), or write_request (non-destructive trigger)"
    )
    allowed_actors: list[AllowedActor] = Field(
        ..., description="Roles permitted by the P18-A contract to request this action"
    )
    confirmation_required: bool = Field(
        ..., description="True for every write / write_request action"
    )
    degraded_allowed: bool = Field(
        ..., description="True only for provisioning.recheck and backup.check"
    )
    description: str = Field(..., description="Short human-readable description (states: not executed)")


class ActionCatalogResponse(BaseModel):
    """Response for GET /actions/catalog."""

    model_config = ConfigDict(extra="forbid")

    items: list[ActionCatalogItem]
    total: int
    contract: str = Field("P18-A", description="Source contract reference")
    executed: bool = Field(
        False, description="Always False -- the catalog is read-only and nothing is executed"
    )


class ActionRequest(BaseModel):
    """Inbound controlled-action request body (used by validate and request).

    action_type is a plain string (not the Literal) so an unsupported type can be
    echoed back in a uniform denied response instead of a 422 validation error.
    reason and idempotency_key are optional here so a missing one yields a
    contract-shaped denied response (and is audited) rather than a 422.
    """

    model_config = ConfigDict(extra="forbid")

    action_type: str = Field(..., description="Controlled action identifier from the P18-A catalog")
    tenant_id: Optional[str] = Field(
        None, description="Target tenant; null for platform-wide actions (for example incident.flag_set)"
    )
    reason: Optional[str] = Field(
        None, description="Required on every request; redacted before audit"
    )
    idempotency_key: Optional[str] = Field(
        None, description="Required on every request; client-supplied dedup key"
    )
    requested_state: Optional[str] = Field(
        None, description="Target state for transition-style actions"
    )
    confirm: bool = Field(
        False, description="Explicit confirmation token required for write / write_request actions"
    )
    correlation_id: Optional[str] = Field(None, description="Optional correlation id")
    metadata: Optional[dict] = Field(
        None, description="Optional metadata; redacted before audit -- never raw secrets"
    )


class ActionRequestResponse(BaseModel):
    """Uniform response for validate (dry_run=True) and request (dry_run=False)."""

    model_config = ConfigDict(extra="forbid")

    action_id: Optional[str] = Field(
        None, description="Assigned when a request is recorded; null for dry_run / denied"
    )
    action_type: str = Field(..., description="Echoed action type (may be unsupported)")
    result: RequestResult = Field(..., description="accepted / denied / degraded / duplicate / conflict")
    executed: bool = Field(
        False, description="Always False -- the skeleton never executes any action"
    )
    dry_run: bool = Field(False, description="True for /validate (no persistence)")
    message: str = Field(
        ..., description="Human-readable outcome; states not-executed where relevant"
    )
    reason: str = Field(..., description="Echoed reason (redacted of secret-like substrings)")
    idempotency_key: str = Field(..., description="Echoed idempotency key")
    requested_state: Optional[str] = Field(None, description="Echoed requested state")
    previous_state: Optional[str] = Field(
        None, description="Always null -- the skeleton reads no previous state and mutates nothing"
    )
    source_status: RegistrySourceStatus = Field(
        "unknown", description="Resolved registry source status for the target"
    )
    degraded_reason: Optional[str] = Field(
        None, description="Set when result is degraded"
    )
    metadata_redacted: Optional[dict] = Field(
        None, description="Redacted metadata; never a raw sensitive payload"
    )
    correlation_id: Optional[str] = Field(None, description="Echoed correlation id")
    created_at: datetime = Field(..., description="UTC ISO-8601 timestamp")


class ActionRequestQueueResponse(BaseModel):
    """Ephemeral operator queue of recorded P18 action requests."""

    model_config = ConfigDict(extra="forbid")

    items: list[ActionRequestResponse]
    total: int
    limit: int
    offset: int
    storage: str = Field(
        "memory", description="Ephemeral in-process storage; no database persistence"
    )
    executed: bool = Field(
        False, description="Always False -- listing the queue never executes actions"
    )
