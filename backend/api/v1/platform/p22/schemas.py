"""Pydantic schemas for P22 Controlled Execution v0 (P22-B non-executing skeleton).

Field-for-field aligned to
docs/ai/PLATFORM_PRODUCT_P22_CONTROLLED_EXECUTION_V0_CONTRACT.md (P22-A).

This is a NON-EXECUTING backend skeleton: it reads the catalog, runs a no-
mutation dry-run validator, records (digest-only, redacted) execution REQUESTS,
and reads execution results. It NEVER executes any action, NEVER dispatches a
worker, NEVER drains a queue, NEVER invokes the P16 governed harness, NEVER runs
shell / SQL / script, and NEVER mutates tenant business data, the P17 registry,
operational flags, provisioning, backup, or any payment / billing / product
record. Approval is not execution and durability is not execution.

Contract rules carried from P10 / P17 / P18 / P19 / P20 / P21 / P22-A:
  - The v0 execution allowlist is EXACTLY the seven actions below; every other
    action (including the explicitly excluded tenant.pause / tenant.resume /
    lifecycle.transition / real restore / schema migration / data deletion /
    payment-billing / tenant-business-records / arbitrary shell-SQL-script) has
    no v0 execution path.
  - approval != execution; durability != execution. A durable, quorum-met
    approval at approved_execution_blocked is a PRECONDITION, not an execution.
  - The v0 executor is ALWAYS an identity-only super_admin. support_operator,
    engineering_operator, tenant admin, tenant-contextual super_admin, and
    tenant-scoped tokens are denied as executors (and audited).
  - Operator separation: the executor is a distinct identity from the maker and
    from every checker; self-execution and checker-execution are denied.
  - execution_allowed / executed / execution_started are ALWAYS false in P22-B;
    result_state is only ever dry_run_passed | blocked (never executing /
    executed). The full nine-state execution-record enum is defined here for
    contract fidelity; P22-B realizes only the two non-executing entry states.
  - The raw idempotency_key is NEVER stored / logged / echoed / audited; only its
    one-way SHA-256 digest (idempotency_key_digest) and a canonical payload_digest
    are recorded.
  - reason / metadata / correlation reuse the P18 allowlist-style redaction
    (never a raw secret / credential / DSN / host / port / connection string /
    auth header / raw body / shell / SQL / script).
  - extra="forbid" on every model (no undeclared fields / leaks).
  - No tenant business records; tenant_id is a scoped identifier only.

Request fields are lenient (Optional / plain str) so a missing or invalid value
yields a contract-shaped blocked / denied response (mirroring P18 / P20) rather
than a 422 validation error. The executor identity (actor_id / actor_role /
identity_context) is derived from the authenticated token via the reused P10
identity-only guard -- it is NEVER read from the request body (no identity
spoof), mirroring the P20-B-R1 binding.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# -- v0 execution allowlist (P22-A section 3.1) -- EXACTLY seven actions -------

#: The closed v0 execution allowlist. An action_type not in this set has no v0
#: execution path, regardless of how many approvals it carries.
ALLOWED_ACTION_TYPES: tuple[str, ...] = (
    "support_mode.on",
    "support_mode.off",
    "incident.flag_set",
    "incident.flag_clear",
    "provisioning.recheck",
    "backup.check",
    "backup.restore_test_request",
)

#: The explicitly excluded, never-executable-in-v0 named actions (P22-A 3.2).
#: These reach at most approved_execution_blocked and never execute in any P22
#: phase. Anything not in ALLOWED_ACTION_TYPES is excluded by definition; these
#: are named for the catalog / audit / tests.
EXCLUDED_ACTION_TYPES: tuple[str, ...] = (
    "tenant.pause",
    "tenant.resume",
    "lifecycle.transition",
)

#: The paired reversal action for each reversible v0 write (P22-A 3.1 / 7.3).
#: Reads and the restore-test request have no paired reversal.
REVERSAL_MAP: dict[str, Optional[str]] = {
    "support_mode.on": "support_mode.off",
    "support_mode.off": "support_mode.on",
    "incident.flag_set": "incident.flag_clear",
    "incident.flag_clear": "incident.flag_set",
    "provisioning.recheck": None,
    "backup.check": None,
    "backup.restore_test_request": None,
}

#: The v0 read actions (P22-A 3.1). These may execute against a degraded source
#: and return a degraded result; writes / write-requests require a known source.
READ_ACTION_TYPES: frozenset[str] = frozenset({"provisioning.recheck", "backup.check"})

#: The action_class per allowlisted action (mirrors P18-A section 3 / P22-A 3.1).
ACTION_CLASS_MAP: dict[str, str] = {
    "support_mode.on": "write",
    "support_mode.off": "write",
    "incident.flag_set": "write",
    "incident.flag_clear": "write",
    "provisioning.recheck": "read",
    "backup.check": "read",
    "backup.restore_test_request": "write_request",
}


# -- Vocabularies (mirror P22-A) ----------------------------------------------

#: A v0 allowlisted action_type (closed seven-member set).
P22ActionType = Literal[
    "support_mode.on",
    "support_mode.off",
    "incident.flag_set",
    "incident.flag_clear",
    "provisioning.recheck",
    "backup.check",
    "backup.restore_test_request",
]

#: P18 action classification, inherited verbatim.
P22ActionClass = Literal["read", "write", "write_request"]

#: The dry-run verdict (P22-A 5.2).
ExecutionVerdict = Literal["passed", "blocked"]

#: The execution-record state machine (P22-A 7.1). The full nine-state enum is
#: defined here for contract fidelity; P22-B realizes ONLY the two non-executing
#: entry states (dry_run_passed | blocked). The executing / executed / failed /
#: compensation / cancelled states are NEVER assigned in P22-B -- they belong to
#: a separately approved execution phase behind the P16 harness.
ExecutionResultState = Literal[
    "dry_run_passed",
    "blocked",
    "execution_queued",
    "executing",
    "executed",
    "execution_failed",
    "compensation_required",
    "compensation_completed",
    "cancelled",
]

#: The closed execution audit event_type set (P22-A 8.2).
ExecutionEventType = Literal[
    "execution_dry_run_requested",
    "execution_dry_run_passed",
    "execution_dry_run_blocked",
    "execution_requested",
    "execution_started",
    "execution_succeeded",
    "execution_failed",
    "execution_compensation_recorded",
    "execution_denied",
]

#: The P22 execution source-status vocabulary (known | unknown | degraded). This
#: generalizes the P18/P20 available/unavailable/unknown vocabulary: a known
#: source is healthy; an unknown source is never healthy (blocks writes); a
#: degraded source is the only allowance, for reads only (P22-A 4.5 / 10.10).
ExecutionSourceStatus = Literal["known", "unknown", "degraded"]

#: The execution mode (P22-A 5.1 / 7.2). P22-B accepts both but executes neither.
ExecutionMode = Literal["sync", "queued"]

#: The only permitted identity_context for a v0 EXECUTOR (P22-A 4.1 / 6). A
#: recorded execution request always carries identity_only; `system` appears
#: only for automated compensation / sweep in a future phase.
P22IdentityContext = Literal["identity_only", "system"]

#: The v0 EXECUTOR role (P22-A 4.1 / 11.3). A recorded execution request always
#: carries super_admin.
P22ActorRole = Literal["super_admin", "system"]

#: The wider actor_role vocabulary used in AUDIT events and DENIED responses.
#: The v0 executor is always identity-only super_admin, but a DENIAL must record
#: the real denied actor (support_operator / engineering_operator / tenant admin /
#: tenant-contextual / unknown), exactly as P20 audits denials (P22-A 8.2). A
#: recorded (non-denied) request always carries super_admin.
ExecutionActorRole = Literal[
    "super_admin", "support_operator", "engineering_operator", "system", "unknown"
]

#: The wider identity_context vocabulary used in AUDIT events and DENIED
#: responses, mirroring P20. A recorded execution request always carries
#: identity_only; denied responses reflect the denied actor's real context.
ExecutionIdentityContext = Literal[
    "identity_only", "tenant_contextual", "tenant_scoped_token", "tenant_admin", "system", "unknown"
]

#: The closed block_reason / denial code vocabulary (P22-A section 4 / 8.2).
#: A blocked dry-run or a denied execution carries one or more of these codes.
BlockReasonCode = Literal[
    "executor_not_identity_super_admin",
    "action_not_allowlisted",
    "action_excluded",
    "approval_not_found",
    "approval_state_not_approved_execution_blocked",
    "quorum_not_met",
    "source_unknown_for_write",
    "self_execution_forbidden",
    "checker_execution_forbidden",
    "idempotency_key_required",
    "action_mismatch_approval",
    "dry_run_required",
    "dry_run_invalid",
    "execution_ack_required",
    "idempotency_conflict",
]


# -- Catalog ------------------------------------------------------------------


class CatalogItem(BaseModel):
    """One v0 allowlisted action in the execution catalog (P22-A 3.1)."""

    model_config = ConfigDict(extra="forbid")

    action_type: P22ActionType
    action_class: P22ActionClass
    executor: str = Field("super_admin (identity-only)", description="The only v0 executor.")
    reversible: bool
    reversibility_via: Optional[P22ActionType] = Field(
        None, description="The paired reversal action, if any."
    )
    tenant_business_mutation: str = Field(
        "none", description="Always 'none' for every v0 action."
    )


class ExcludedAction(BaseModel):
    """One explicitly excluded, never-executable-in-v0 action (P22-A 3.2)."""

    model_config = ConfigDict(extra="forbid")

    action_type: str
    reason: str


class ExecutionCatalogResponse(BaseModel):
    """The v0 execution allowlist and the explicit exclusion list.

    Read-only; never executes. ``storage`` is always "memory" in P22-B.
    """

    model_config = ConfigDict(extra="forbid")

    items: list[CatalogItem]
    exclusions: list[ExcludedAction]
    total: int = Field(..., description="Number of allowlisted actions (always 7).")
    contract: str = Field("P22-A", description="The contract revision.")
    storage: str = Field("memory", description="Always 'memory' in P22-B skeleton.")
    executed: bool = Field(False, description="Always False -- the catalog never executes.")


# -- Dry-run ------------------------------------------------------------------


class ExecutionDryRunRequest(BaseModel):
    """Inbound body for a no-mutation dry-run (POST /execution/dry-run).

    The executor identity is derived from the authenticated token (P10
    identity-only guard) -- it is NOT read from this body. Raw client values are
    used internally for catalog lookup and the one-way idempotency digest only;
    nothing raw is echoed or audited.
    """

    model_config = ConfigDict(extra="forbid")

    durable_approval_id: Optional[str] = Field(
        None, description="Required. Must resolve to a real durable approval."
    )
    action_type: Optional[str] = Field(
        None, description="Required. A v0 allowlisted action_type; must match the approval."
    )
    tenant_id: Optional[str] = Field(
        None, description="Scoped id only; null for platform-wide. Never a business payload."
    )
    requested_state: Optional[str] = Field(
        None, description="Null for reads / no-target actions."
    )
    reason: Optional[str] = Field(
        None, description="Required; redacted via the P18 allowlist before any record / response."
    )
    idempotency_key: Optional[str] = Field(
        None,
        description="Required. Hashed to a digest at the boundary; the raw key is never "
        "stored / logged / returned.",
    )
    execution_mode: Optional[str] = Field(
        None, description="Required. sync | queued. P22-B accepts both and executes neither."
    )
    correlation_id: Optional[str] = Field(None, description="Optional correlation id.")
    metadata: Optional[dict] = Field(
        None, description="Optional metadata; redacted before audit -- never raw secrets."
    )


class ExecutionDryRunResponse(BaseModel):
    """Dry-run response (P22-A 5.2). No mutation; never executes.

    ``executable`` is the dry-run verdict (true only if every precondition
    holds). ``execution_allowed`` is ALWAYS False in P22-B: a passed dry-run is a
    precondition, not an execution. The raw idempotency key is never returned;
    only its one-way digest is.
    """

    model_config = ConfigDict(extra="forbid")

    dry_run_id: Optional[str] = Field(None, description="Present when verdict == passed.")
    durable_approval_id: Optional[str] = None
    action_type: Optional[str] = None
    tenant_id: Optional[str] = None
    requested_state: Optional[str] = None
    executable: bool = Field(False, description="true only if every precondition holds.")
    verdict: ExecutionVerdict = Field("blocked", description="passed | blocked.")
    block_reasons: list[BlockReasonCode] = Field(
        default_factory=list, description="Empty when passed; the failed precondition codes when blocked."
    )
    expected_audit_shape: dict = Field(
        default_factory=dict,
        description="The event_type(s) execution would emit, with FIELD NAMES ONLY -- "
        "never values, secrets, or raw payloads.",
    )
    execution_mode: Optional[ExecutionMode] = None
    source_status: ExecutionSourceStatus = Field(
        "unknown", description="known | unknown | degraded. Unknown is never healthy."
    )
    reversible: bool = Field(False, description="Whether a paired reversal action exists.")
    redaction_applied: bool = Field(True, description="Always True.")
    idempotency_key_digest: Optional[str] = Field(
        None, description="SHA-256 of the client key; the raw key is never returned."
    )
    storage: str = Field("memory", description="Always 'memory' in P22-B skeleton.")
    executed: bool = Field(False, description="Always False -- a dry-run never executes.")
    execution_started: bool = Field(False, description="Always False -- a dry-run never starts execution.")
    execution_allowed: bool = Field(
        False, description="Always False in P22-B -- a passed dry-run is a precondition, not execution."
    )
    created_at: datetime = Field(..., description="UTC ISO-8601.")


# -- Execution request --------------------------------------------------------


class ExecutionRequestCreate(BaseModel):
    """Inbound body to record an execution request (POST /execution/requests).

    Requires a passed dry-run (``dry_run_ref``) and the typed execution
    acknowledgement (``execution_ack``). The request is RECORDED only; it is
    never executed. The executor identity is derived from the authenticated
    token, never from this body.
    """

    model_config = ConfigDict(extra="forbid")

    durable_approval_id: Optional[str] = Field(None, description="Required.")
    action_type: Optional[str] = Field(None, description="Required. A v0 allowlisted action_type.")
    tenant_id: Optional[str] = Field(None, description="Scoped id only; null for platform-wide.")
    requested_state: Optional[str] = Field(None, description="Null for reads / no-target actions.")
    reason: Optional[str] = Field(None, description="Required; redacted before any record / response.")
    idempotency_key: Optional[str] = Field(
        None, description="Required. Only its SHA-256 digest is stored."
    )
    dry_run_ref: Optional[str] = Field(
        None, description="Required. The dry_run_id of a passed dry-run for the same approval / "
        "action / target / executor."
    )
    execution_ack: bool = Field(
        False, description="Required typed execution acknowledgement; the request lands only when true."
    )
    execution_mode: Optional[str] = Field(None, description="Required. sync | queued.")
    correlation_id: Optional[str] = Field(None, description="Optional correlation id.")
    metadata: Optional[dict] = Field(None, description="Optional metadata; redacted before audit.")


class ExecutionRequestResponse(BaseModel):
    """A recorded execution request and uniform response (P22-A section 6).

    result_state is only ever ``dry_run_passed`` (preconditions held, request
    recorded) or ``blocked`` (a precondition failed at request time, or an
    idempotency conflict). It is NEVER executing / executed / failed /
    compensation / cancelled in P22-B. ``execution_allowed`` / ``executed`` /
    ``execution_started`` are always False. The raw idempotency key is never
    stored or returned; only the digest and the canonical payload_digest are.
    """

    model_config = ConfigDict(extra="forbid")

    execution_request_id: Optional[str] = Field(None, description="Unique per attempt; null until recorded.")
    durable_approval_id: Optional[str] = None
    action_type: Optional[str] = None
    tenant_id: Optional[str] = None
    requested_state: Optional[str] = None
    reason_redacted: str = Field("", description="Redacted reason; never a raw body.")
    idempotency_key_digest: Optional[str] = Field(
        None, description="SHA-256 of the client key; the raw key is never stored / returned."
    )
    payload_digest: Optional[str] = Field(
        None, description="SHA-256 of the canonical execution payload; drives replay dedup."
    )
    actor_id: Optional[str] = Field(None, description="Identity-only super_admin executor (from the token).")
    actor_role: ExecutionActorRole = Field(
        "super_admin",
        description="Always super_admin for a recorded request; denied responses reflect the denied actor.",
    )
    identity_context: ExecutionIdentityContext = Field(
        "identity_only",
        description="Always identity_only for a recorded request; denied responses reflect the denied actor.",
    )
    execution_mode: Optional[ExecutionMode] = None
    dry_run_ref: Optional[str] = Field(None, description="The bound passed dry-run id.")
    execution_ack: bool = Field(False, description="The typed acknowledgement carried by the request.")
    correlation_id: Optional[str] = None
    metadata_redacted: Optional[dict] = Field(None, description="Redacted metadata; never raw secrets.")
    redaction_applied: bool = Field(True, description="Always True.")
    result_state: ExecutionResultState = Field(
        "dry_run_passed", description="Only dry_run_passed | blocked in P22-B."
    )
    block_reasons: list[BlockReasonCode] = Field(
        default_factory=list,
        description="Empty for a recorded request; the failed precondition codes when blocked.",
    )
    result: str = Field(
        "recorded",
        description="Operational outcome (recorded | blocked | duplicate | conflict).",
    )
    message: str = Field("", description="Human-readable outcome; states not-executed.")
    storage: str = Field("memory", description="Always 'memory' in P22-B skeleton.")
    executed: bool = Field(False, description="Always False -- P22-B never executes.")
    execution_started: bool = Field(False, description="Always False -- P22-B never starts execution.")
    execution_allowed: bool = Field(False, description="Always False in P22-B.")
    created_at: Optional[datetime] = Field(None, description="UTC ISO-8601.")
    updated_at: Optional[datetime] = Field(None, description="UTC ISO-8601.")


class ExecutionRequestQueue(BaseModel):
    """Ephemeral operator queue of recorded execution requests. Read-only."""

    model_config = ConfigDict(extra="forbid")

    items: list[ExecutionRequestResponse]
    total: int
    limit: int
    offset: int
    storage: str = Field("memory", description="Always 'memory' in P22-B skeleton.")
    executed: bool = Field(False, description="Always False -- listing never executes.")


# -- Execution audit event (P22-A 8.1) ----------------------------------------


class ExecutionAuditEvent(BaseModel):
    """One redacted execution audit event (P22-A 8.1).

    Recorded in the in-memory execution audit log. Every field is redacted /
    echo-safe; the raw idempotency key, raw secrets, DSNs, host:port, auth
    headers, raw request / response bodies, and shell / SQL / script NEVER appear
    (only the one-way digests and the redacted reason). Denials are audited with
    the same shape as successes.
    """

    model_config = ConfigDict(extra="forbid")

    event_id: str
    event_type: ExecutionEventType
    execution_request_id: Optional[str] = None
    durable_approval_id: Optional[str] = None
    action_id: Optional[str] = Field(None, description="The P18 action_id, where applicable.")
    actor_id: Optional[str] = Field(None, description="Identity-only super_admin; SYSTEM for sweeps.")
    actor_role: ExecutionActorRole = Field("super_admin")
    identity_context: ExecutionIdentityContext = Field("identity_only")
    action_type: Optional[str] = None
    tenant_id: Optional[str] = None
    result_state: Optional[ExecutionResultState] = None
    previous_state: Optional[ExecutionResultState] = None
    reason_redacted: str = Field("", description="Redacted via P10/P18 allowlist; never a raw body.")
    payload_digest: Optional[str] = None
    idempotency_key_digest: Optional[str] = None
    source_status: Optional[ExecutionSourceStatus] = None
    dry_run_ref: Optional[str] = None
    redaction_applied: bool = Field(True, description="Always True.")
    correlation_id: Optional[str] = None
    block_reasons: list[BlockReasonCode] = Field(default_factory=list)
    sequence_no: int = Field(0, description="Monotonic per-execution-request audit sequence.")
    created_at: datetime


__all__ = [
    # allowlist / mappings
    "ALLOWED_ACTION_TYPES",
    "EXCLUDED_ACTION_TYPES",
    "REVERSAL_MAP",
    "READ_ACTION_TYPES",
    "ACTION_CLASS_MAP",
    # vocabularies
    "P22ActionType",
    "P22ActionClass",
    "ExecutionVerdict",
    "ExecutionResultState",
    "ExecutionEventType",
    "ExecutionSourceStatus",
    "ExecutionMode",
    "P22IdentityContext",
    "P22ActorRole",
    "ExecutionActorRole",
    "ExecutionIdentityContext",
    "BlockReasonCode",
    # models
    "CatalogItem",
    "ExcludedAction",
    "ExecutionCatalogResponse",
    "ExecutionDryRunRequest",
    "ExecutionDryRunResponse",
    "ExecutionRequestCreate",
    "ExecutionRequestResponse",
    "ExecutionRequestQueue",
    "ExecutionAuditEvent",
]
