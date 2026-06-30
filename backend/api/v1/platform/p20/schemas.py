"""Pydantic schemas for P20 Durable Approval Governance (P20-B skeleton).

Field-for-field aligned to
docs/ai/PLATFORM_PRODUCT_P20_DURABLE_APPROVAL_GOVERNANCE_CONTRACT.md (P20-A).

This is a DURABLE APPROVAL READ / WRITE package only. It records maker-checker
approval decisions. It NEVER executes any controlled action and NEVER mutates
the P17 registry, tenant lifecycle, operational flags, provisioning, backup, or
any tenant business data. Approval is not execution and durability is not
execution: a quorum-met approval resolves to ``approved_execution_blocked`` and
``execution_allowed`` / ``executed`` are always false. These schemas preserve
the P20 API shape across both runtime backends; the ``storage`` field
distinguishes the durable store (``"durable"``, the P21-D-D default) from the
explicit memory test/dev backend (``"memory"``).

Contract rules carried from P10 / P17 / P18 / P19 / P20-A:
  - approval != execution; durability != execution.
  - execution_allowed is always false; executed is always false;
    execution_gate is always "blocked".
  - maker-checker separation: the maker can never be a checker (self-approval
    forbidden). checkers must be distinct identities.
  - quorum: write / write_request floor of two distinct checkers (excluding the
    maker); read floor of one.
  - reject is final (any single reject vetoes the approval).
  - idempotency_key is stored ONLY as a one-way SHA-256 digest
    (``idempotency_key_digest``); the raw key is never stored / logged / echoed.
  - reason / comment / metadata reuse the P18 allowlist-style redaction (never a
    raw secret / credential / DSN / host / port / connection string / log line).
  - extra="forbid" on every model (no undeclared fields / leaks).
  - No tenant business records (orders, payments, invoices, customers).

State machine (P20-A section 6): the full seven-state enum is defined below.
P20-B IMPLEMENTS only pending_review / approved_execution_blocked / rejected;
transitions to expired / cancelled / superseded / failed_validation are NOT
implemented and are explicitly rejected by the service layer.

Request fields are lenient (Optional / plain str) so a missing or invalid value
yields a contract-shaped denied record (mirroring P18 / P19) rather than a 422
validation error. RAW client values are still used internally for the store key
and the one-way idempotency digest; nothing raw is echoed or audited.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# -- Vocabularies (mirror P20-A) --

# The durable approval lifecycle states (P20-A section 6). The full enum is
# defined here; P20-B implements only the first three (pending_review,
# approved_execution_blocked, rejected). The remaining four are schema-only in
# P20-B and any transition toward them is explicitly rejected.
DurableApprovalState = Literal[
    "pending_review",
    "approved_execution_blocked",
    "rejected",
    "expired",
    "cancelled",
    "superseded",
    "failed_validation",
]

# An approve / reject decision recorded by one checker.
DecisionType = Literal["approve", "reject"]

# P18 action classification, inherited verbatim. Drives quorum (P20-A 4.5).
ActionClass = Literal["read", "write", "write_request"]

# Operational outcome of a create / decision call (analogous to the P18 / P19
# result enum). Carried on the response record so denials / duplicates /
# conflicts / quorum-pending states are observable without a persisted change.
DurableApprovalResult = Literal[
    "recorded",
    "approved",
    "rejected",
    "denied",
    "duplicate",
    "conflict",
    "not_found",
    "quorum_pending",
]

# How the actor's identity was established (P20-A audit contract).
IdentityContext = Literal[
    "identity_only",
    "tenant_contextual",
    "tenant_scoped_token",
    "tenant_admin",
    "system",
    "unknown",
]

# The actor's operational role (P20-A audit contract).
ActorRole = Literal[
    "super_admin",
    "support_operator",
    "engineering_operator",
    "system",
    "unknown",
]

# P18 registry source status, inherited verbatim.
RegistrySourceStatus = Literal["available", "unavailable", "unknown"]

# Durable re-validation result (P20-A 3.1 / 3.6).
ValidationStatus = Literal["valid", "source_unknown", "superseded_scope", "stale"]

# Execution readiness gate (P20-A 5.2). Always "blocked" in P20.
ExecutionGate = Literal["blocked", "not_authorized"]

# Retention class (P20-A 3.1 / 3.5).
RetentionClass = Literal["standard", "long", "legal_hold"]

# Durable audit event types (P20-A section 7).
DurableApprovalEventType = Literal[
    "approval_opened",
    "approval_decision_recorded",
    "approval_quorum_met",
    "approval_rejected",
    "approval_expired",
    "approval_cancelled",
    "approval_superseded",
    "approval_failed_validation",
    "approval_read",
    "approval_exported",
    "approval_denied",
    "approval_purged",
]


class CheckerDecisionSummary(BaseModel):
    """Echo-safe summary of one checker's recorded decision (within a record).

    The checker's reason is redacted. The raw decision idempotency_key is never
    stored; only its SHA-256 digest is held internally (not echoed here).
    """

    model_config = ConfigDict(extra="forbid")

    checker_id: str = Field(..., description="Identity-only super_admin checker id.")
    decided_at: datetime = Field(..., description="UTC ISO-8601.")
    decision: DecisionType = Field(..., description="approve | reject.")
    reason_redacted: str = Field("", description="Redacted checker reason.")
    audit_event_id: Optional[str] = Field(None, description="Id of the decision audit event.")


class DurableApprovalCreateRequest(BaseModel):
    """Inbound body to open a durable approval request (POST /durable-approvals).

    Wraps a recorded P18 action request. ``action_id`` is preferred (a recorded
    P18 request whose result == accepted and executed == False); ``action_type``
    is the fallback when no recorded action_id is supplied. Either resolves the
    P18 source status and the action class honestly -- an unknown source is never
    fabricated as available, and an unknown action_type is rejected.
    """

    model_config = ConfigDict(extra="forbid")

    action_id: Optional[str] = Field(None, description="Recorded P18 action request id (preferred).")
    tenant_id: Optional[str] = Field(None, description="Target tenant; null for platform-wide actions.")
    action_type: Optional[str] = Field(None, description="P18 action_type; resolves class + source when no action_id is given.")
    maker: Optional[str] = Field(None, description="Identity-only actor opening the request; required. Can never be a checker on this approval.")
    reason: Optional[str] = Field(None, description="Required; redacted via the P18 allowlist before storage / audit.")
    idempotency_key: Optional[str] = Field(None, description="Required; client-supplied dedup key. Only its SHA-256 digest is stored.")
    expires_at: Optional[datetime] = Field(None, description="Required; UTC ISO-8601; must be in the future at creation.")
    durable_retain_until: Optional[datetime] = Field(None, description="Retention TTL; defaults to expires_at when omitted.")
    confirm: bool = Field(False, description="Explicit confirmation token required to open the request.")
    correlation_id: Optional[str] = Field(None, description="Optional correlation id.")
    metadata: Optional[dict] = Field(None, description="Optional metadata; redacted before audit -- never raw secrets.")


class DurableApprovalDecisionRequest(BaseModel):
    """Inbound body for one checker to approve or reject a pending durable
    approval (POST /durable-approvals/{approval_id}/decisions).

    ``approver_id`` is the checker and MUST differ from the approval's maker
    (maker-checker separation). Only an identity-only super_admin may supply a
    valid decision (the reused P10 guard enforces platform-operator access;
    narrower runtime role granularity is deferred, mirroring P18 / P19).
    """

    model_config = ConfigDict(extra="forbid")

    decision: str = Field(..., description="approve | reject (plain str so an invalid value yields a shaped denial).")
    approver_id: Optional[str] = Field(None, description="Identity-only super_admin checker; required; must differ from maker.")
    reason: Optional[str] = Field(None, description="Required; redacted via the P18 allowlist before storage / audit.")
    idempotency_key: Optional[str] = Field(None, description="Required; client-supplied dedup key for this checker decision. Only its SHA-256 digest is stored.")
    confirm: bool = Field(False, description="Explicit confirmation token required for the decision to land.")
    correlation_id: Optional[str] = Field(None, description="Optional correlation id.")
    metadata: Optional[dict] = Field(None, description="Optional metadata; redacted before audit -- never raw secrets.")


class DurableApprovalRecord(BaseModel):
    """Stored durable approval record and uniform response for create / read /
    decision.

    Carries the P20-A required fields plus operational fields (result, message,
    executed, source_status). execution_allowed, executed are always false;
    execution_gate is always "blocked"; redaction_applied is always true;
    storage is always "memory". ``idempotency_key_digest`` is the one-way SHA-256
    digest of the create idempotency key (the raw key is never stored / echoed).
    """

    model_config = ConfigDict(extra="forbid")

    approval_id: Optional[str] = Field(None, description="Unique per durable approval; null until recorded.")
    action_id: Optional[str] = Field(None, description="Wrapped P18 action request id.")
    tenant_id: Optional[str] = Field(None, description="Null for platform-wide actions.")
    action_type: Optional[str] = Field(None, description="The P18 action_type (echo-safe).")
    action_class: Optional[ActionClass] = Field(None, description="read | write | write_request; drives quorum.")
    state: Optional[DurableApprovalState] = Field(None, description="Lifecycle state; null until recorded.")
    maker: Optional[str] = Field(None, description="Identity-only actor that opened the request (echo-safe).")
    maker_at: Optional[datetime] = Field(None, description="UTC ISO-8601; null until recorded.")
    checkers: list[CheckerDecisionSummary] = Field(default_factory=list, description="Append-only log of checker decisions.")
    quorum_required: int = Field(0, description="Floor per action_class; maker excluded.")
    quorum_met: bool = Field(False, description="True only when distinct approve checkers >= quorum_required and no reject.")
    decision: Optional[DecisionType] = Field(None, description="approve | reject; null until a terminal decision.")
    reason: str = Field("", description="Echo-safe (redacted) maker reason.")
    request_digest: Optional[str] = Field(None, description="SHA-256 of the canonical request envelope.")
    idempotency_key_digest: Optional[str] = Field(None, description="SHA-256 digest of the create idempotency key; raw key never stored / echoed.")
    expires_at: Optional[datetime] = Field(None, description="UTC ISO-8601 decision-window expiry.")
    durable_retain_until: Optional[datetime] = Field(None, description="UTC ISO-8601 retention TTL.")
    execution_allowed: bool = Field(False, description="Always False -- a durable approval never permits execution.")
    execution_gate: ExecutionGate = Field("blocked", description="Always 'blocked' in P20.")
    redaction_applied: bool = Field(True, description="Always True.")
    storage: str = Field("memory", description="durable | memory; the active backend (durable store via the P21-D-D gate, or explicit memory test/dev).")
    retention_class: RetentionClass = Field("standard", description="Retention class; legal_hold suspends purge (future).")
    validation_status: ValidationStatus = Field("valid", description="Durable re-validation result.")
    superseded_by: Optional[str] = Field(None, description="Approval that superseded this one (future).")
    previous_state: Optional[DurableApprovalState] = Field(None, description="Lifecycle state before the last transition.")
    audit_event_id: Optional[str] = Field(None, description="Id of the last durable audit event for this approval.")
    correlation_id: Optional[str] = Field(None, description="Echo-safe correlation id.")
    source_status: RegistrySourceStatus = Field("unknown", description="Inherited P18 source status; unknown is never fabricated available.")
    result: DurableApprovalResult = Field("recorded", description="Operational outcome of the call.")
    message: str = Field("", description="Human-readable outcome; states not-executed where relevant.")
    executed: bool = Field(False, description="Always False -- a durable approval never executes.")
    created_at: Optional[datetime] = Field(None, description="UTC ISO-8601.")
    updated_at: Optional[datetime] = Field(None, description="UTC ISO-8601.")


class DurableApprovalQueue(BaseModel):
    """Ephemeral operator queue of durable approval records. Read-only; never executes."""

    model_config = ConfigDict(extra="forbid")

    items: list[DurableApprovalRecord]
    total: int
    limit: int
    offset: int
    storage: str = Field("memory", description="durable | memory; the queue backend (durable store via the P21-D-D gate, or explicit memory test/dev).")
    executed: bool = Field(False, description="Always False -- listing never executes.")


class DurableApprovalAuditEvent(BaseModel):
    """Audit payload for a durable approval transition (P20-A section 7).

    Built by services._emit / _build_audit_event and recorded in the in-memory
    audit log. ``reason_redacted`` is always redacted via the P18 allowlist. Every
    event -- including denials and reads -- carries all P20-A required audit
    fields: event_id, approval_id, action_id, actor_id, actor_role,
    identity_context, decision, previous_status, next_status, reason_redacted,
    created_at, request_digest, redaction_applied.
    """

    model_config = ConfigDict(extra="forbid")

    event_id: str
    event_type: DurableApprovalEventType
    approval_id: Optional[str] = None
    action_id: Optional[str] = None
    actor_id: Optional[str] = Field(None, description="Identity-only actor id (or system actor).")
    actor_role: ActorRole = "system"
    identity_context: IdentityContext
    tenant_id: Optional[str] = None
    decision: Optional[DecisionType] = None
    previous_status: Optional[DurableApprovalState] = None
    next_status: Optional[DurableApprovalState] = None
    reason_redacted: str = ""
    created_at: datetime
    request_digest: Optional[str] = None
    redaction_applied: bool = True
    quorum_required: int = 0
    quorum_met: bool = False
    checker_id: Optional[str] = None
    correlation_id: Optional[str] = None
