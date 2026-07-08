"""Pydantic schemas for P19 Controlled Action Approval Workflow (P19-B skeleton).

Field-for-field aligned to
docs/ai/PLATFORM_PRODUCT_P19_APPROVAL_WORKFLOW_CONTRACT.md (P19-A).

This is an APPROVAL READ / WRITE skeleton only. Approval changes approval state
only; it never executes any controlled action. Every record and queue item
carries ``executed == False`` and ``execution_allowed == False``. The skeleton
never mutates the P17 registry, tenant lifecycle, operational flags,
provisioning, backup, or any tenant business data.

Contract rules carried from P10 / P17 / P18:
  - approval != execution; approved resolves to execution_blocked.
  - execution_allowed is always false; executed is always false.
  - reason required on every request and decision; idempotency_key required on
    every request and decision; both redacted before storage / response / audit.
  - redaction reuses the P18 allowlist-style filter (never a raw secret /
    credential / DSN / host / port / connection string / log line).
  - extra="forbid" on every model (no undeclared fields / leaks).
  - No tenant business records (orders, payments, invoices, customers).

Request fields are lenient (Optional / plain str) so a missing or invalid
value yields a contract-shaped denied record (mirroring P18) rather than a 422
validation error. RAW client values are still used internally for the store key
and the one-way idempotency fingerprint; nothing raw is echoed or audited.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# -- Vocabularies (mirror P19-A) --

# The approval lifecycle states (P19-A section 3).
ApprovalState = Literal[
    "requested",
    "pending_review",
    "approved",
    "rejected",
    "expired",
    "cancelled",
    "execution_blocked",
]

# An approve / reject decision.
DecisionType = Literal["approve", "reject"]

# Operational outcome of a create / decision call (analogous to the P18 result
# enum). Carried on the response record so denials / duplicates / conflicts are
# observable without a persisted state change.
ApprovalResult = Literal[
    "recorded",
    "approved",
    "rejected",
    "denied",
    "duplicate",
    "conflict",
    "expired",
    "cancelled",
    "not_found",
]

# How the actor's identity was established (P19-A section 5.5).
IdentityContext = Literal[
    "identity_only",
    "tenant_contextual",
    "tenant_scoped_token",
    "tenant_admin",
    "system",
    "unknown",
]

# P18 registry source status, inherited verbatim.
RegistrySourceStatus = Literal["available", "unavailable", "unknown"]

# Approval audit event types (P19-A section 8).
ApprovalEventType = Literal[
    "approval_requested",
    "approval_approved",
    "approval_rejected",
    "approval_expired",
    "approval_cancelled",
    "approval_read",
    "approval_denied",
]


class ControlledActionApprovalRequest(BaseModel):
    """Inbound body to open an approval request (POST /approvals).

    Wraps a recorded P18 action request. ``action_id`` is preferred (a recorded
    P18 request whose result == accepted and executed == False); ``action_type``
    is the fallback when no recorded action_id is supplied. Either resolves the
    P18 source status honestly -- an unknown source is never fabricated as
    available.
    """

    model_config = ConfigDict(extra="forbid")

    action_id: Optional[str] = Field(
        None, description="Recorded P18 action request id (preferred reference)."
    )
    tenant_id: Optional[str] = Field(
        None, description="Target tenant; null for platform-wide actions."
    )
    action_type: Optional[str] = Field(
        None, description="P18 action_type; used to resolve source when no action_id is given."
    )
    requested_by: Optional[str] = Field(
        None, description="Identity-only actor opening the request; required."
    )
    reason: Optional[str] = Field(
        None, description="Required; redacted via the P18 allowlist before storage / audit."
    )
    idempotency_key: Optional[str] = Field(
        None, description="Required; client-supplied dedup key."
    )
    expires_at: Optional[datetime] = Field(
        None, description="Required; UTC ISO-8601; must be in the future at creation."
    )
    confirm: bool = Field(
        False, description="Explicit confirmation token required to open the request."
    )
    correlation_id: Optional[str] = Field(None, description="Optional correlation id.")
    metadata: Optional[dict] = Field(
        None, description="Optional metadata; redacted before audit -- never raw secrets."
    )


class ControlledActionApprovalDecision(BaseModel):
    """Inbound body to approve or reject a pending approval (POST /{id}/decision).

    Only an identity-only super_admin may supply a valid decision (the reused P10
    guard enforces platform-operator access; runtime role granularity is
    deferred, mirroring P18).
    """

    model_config = ConfigDict(extra="forbid")

    decision: str = Field(
        ..., description="approve | reject (plain str so an invalid value yields a shaped denial)."
    )
    reviewed_by: Optional[str] = Field(
        None, description="Identity-only super_admin deciding; required."
    )
    reason: Optional[str] = Field(
        None, description="Required; redacted via the P18 allowlist before storage / audit."
    )
    idempotency_key: Optional[str] = Field(
        None, description="Required; client-supplied dedup key for the decision."
    )
    confirm: bool = Field(
        False, description="Explicit confirmation token required for the decision to land."
    )
    correlation_id: Optional[str] = Field(None, description="Optional correlation id.")
    metadata: Optional[dict] = Field(
        None, description="Optional metadata; redacted before audit -- never raw secrets."
    )


class ControlledActionApprovalRecord(BaseModel):
    """Stored approval record and uniform response for create / read / decision.

    Carries every P19-A required field (action_id, approval_id, tenant_id,
    action_type, requested_by, requested_at, reviewed_by, reviewed_at, decision,
    reason, expires_at, execution_allowed=false, redaction_applied=true,
    audit_event_id) plus operational fields (state, result, message, executed,
    source_status, storage). execution_allowed and executed are always false.
    """

    model_config = ConfigDict(extra="forbid")

    action_id: Optional[str] = Field(None, description="Wrapped P18 action request id.")
    approval_id: Optional[str] = Field(None, description="Unique per approval; null until recorded.")
    tenant_id: Optional[str] = Field(None, description="Null for platform-wide actions.")
    action_type: Optional[str] = Field(None, description="The P18 action_type (echo-safe).")
    state: Optional[ApprovalState] = Field(None, description="Lifecycle state; null until recorded.")
    requested_by: Optional[str] = Field(None, description="Identity-only actor id (echo-safe).")
    requested_at: Optional[datetime] = Field(None, description="UTC ISO-8601; null until recorded.")
    reviewed_by: Optional[str] = Field(None, description="Deciding super_admin; null pre-decision.")
    reviewed_at: Optional[datetime] = Field(None, description="UTC ISO-8601; null pre-decision.")
    decision: Optional[DecisionType] = Field(None, description="approve | reject; null pre-decision.")
    reason: str = Field("", description="Echo-safe (redacted) reason.")
    expires_at: Optional[datetime] = Field(None, description="UTC ISO-8601 request expiry.")
    execution_allowed: bool = Field(
        False, description="Always False -- approval never permits execution."
    )
    redaction_applied: bool = Field(True, description="Always True.")
    idempotency_key: Optional[str] = Field(
        None, description="Echo-safe idempotency key (raw used only internally)."
    )
    source_status: RegistrySourceStatus = Field(
        "unknown", description="Inherited P18 source status; unknown is never fabricated available."
    )
    previous_state: Optional[ApprovalState] = Field(
        None, description="Lifecycle state before the last transition."
    )
    storage: str = Field("memory", description="In-memory only; no database persistence in P19.")
    audit_event_id: Optional[str] = Field(
        None, description="Id of the last ControlledActionApprovalAuditEvent for this approval."
    )
    correlation_id: Optional[str] = Field(None, description="Echo-safe correlation id.")
    result: ApprovalResult = Field("recorded", description="Operational outcome of the call.")
    message: str = Field("", description="Human-readable outcome; states not-executed where relevant.")
    executed: bool = Field(False, description="Always False -- approval never executes.")
    created_at: Optional[datetime] = Field(None, description="UTC ISO-8601.")
    updated_at: Optional[datetime] = Field(None, description="UTC ISO-8601.")


class ControlledActionApprovalQueue(BaseModel):
    """Ephemeral operator queue of approval records. Read-only; never executes."""

    model_config = ConfigDict(extra="forbid")

    items: list[ControlledActionApprovalRecord]
    total: int
    limit: int
    offset: int
    storage: str = Field("memory", description="In-process storage; no database persistence.")
    executed: bool = Field(False, description="Always False -- listing never executes.")


class ControlledActionApprovalAuditEvent(BaseModel):
    """Audit payload for an approval transition (P19-A section 8).

    Built by services._build_approval_audit_event and written best-effort to the
    platform audit log. Reason is always redacted. Every event -- including
    denials and reads -- carries all required fields.
    """

    model_config = ConfigDict(extra="forbid")

    audit_event_id: str
    event_type: ApprovalEventType
    actor: Optional[str] = Field(None, description="Identity-only actor id (or system actor).")
    identity_context: IdentityContext
    tenant_id: Optional[str] = None
    action_id: Optional[str] = None
    approval_id: Optional[str] = None
    decision: Optional[DecisionType] = None
    redaction_applied: bool = True
    reason: str = ""
    timestamp: datetime
