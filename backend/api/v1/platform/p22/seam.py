"""P22-E1 runtime governed action adapter seam -- NON-EXECUTING skeleton.

This module is the runtime governed action adapter seam defined by P22-E0
(docs/ai/PLATFORM_PRODUCT_P22_RUNTIME_GOVERNED_ADAPTER_CONTRACT.md, section 4):
the ONLY boundary a future real execution of a v0 action may run through. This
P22-E1 skeleton realizes the SEAM SHAPE only and performs NO execution.

What the seam skeleton IS (shape only):
  - Per-action adapter resolution (P22-E0 4.2.1): an allowlisted action_type
    resolves to its ONE NON-EXECUTING adapter; every other value is refused.
    There is no generic dispatcher.
  - The preflight gate (P22-E0 4.2.4): re-validates the full precondition set at
    execution time by REUSING the P22-B precondition evaluator (executor
    identity, durable approval at approved_execution_blocked with quorum, the
    bound dry-run still matches and is not expired, the explicit acknowledgement,
    the allowlist, the target / tenant binding, operator separation, the source
    status, and the digest-only idempotency). Any failed precondition blocks
    (fail closed).
  - The audit shape (P22-E0 4.2.5): the before / after / failure / denial event
    templates (FIELD NAMES ONLY) a future real-execution phase would emit. The
    skeleton writes NO real audit event and never carries executed == True.
  - The idempotency guard (P22-E0 4.2.6): a digest-only replay / conflict
    classification against the recorded request store. The raw key is never
    stored; only the one-way digest is.

What the seam skeleton is NOT:
  - It performs NO execution. It dispatches NO worker, drains NO queue, invokes
    NO development-time worktree harness, runs no shell / SQL / script / external
    process, reads / writes NO tenant business data, and writes NO real
    execution_succeeded audit event. Every adapter is not_implemented and
    realized_execution / executed are always False.

Approval is not execution. A passed dry-run is not execution. A recorded request
is not execution. A passed preflight is not execution. The seam is a PRECONDITION
boundary, not an executor. This module is import-tested in P22-E1; it is not
wired into any HTTP route and adds no public execution entry point.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from . import services as _p22b
from .adapters import (
    ADAPTER_REALIZES_EXECUTION,
    resolve_adapter_descriptor,
    non_executing_adapter_result,
)
from .schemas import BlockReasonCode, ExecutionSourceStatus


# -- Phase / non-execution markers --------------------------------------------

#: The P22-E1 phase implemented by this module.
SEAM_PHASE: str = "P22-E1-runtime-governed-adapter-seam-skeleton"

#: Explicit non-execution marker. The seam skeleton realizes NO execution.
SEAM_REALIZES_EXECUTION: bool = False

#: Storage is in-memory, process-local (mirrors P22-B).
SEAM_STORAGE_MODE: str = "memory"

#: The echo-safe field names a seam audit event carries (P22-E0 4.2.5 / P22-A 8.1).
#: FIELD NAMES ONLY -- never values, secrets, digests-as-values, or executed=True.
SEAM_AUDIT_FIELD_NAMES: tuple[str, ...] = (
    "event_id",
    "event_type",
    "execution_request_id",
    "durable_approval_id",
    "actor_id",
    "actor_role",
    "identity_context",
    "action_type",
    "tenant_id",
    "result_state",
    "previous_state",
    "reason_redacted",
    "payload_digest",
    "idempotency_key_digest",
    "source_status",
    "dry_run_ref",
    "redaction_applied",
    "correlation_id",
    "block_reasons",
    "sequence_no",
    "created_at",
)

#: The before / after / failure event templates a passed preflight describes. The
#: skeleton emits NONE of them; it only names the shape a future real-execution
#: phase would emit (P22-E0 4.2.5). Field names only -- no values, no executed=True.
_PASSED_EVENT_TYPES: tuple[str, ...] = (
    "execution_started",
    "execution_succeeded",
    "execution_failed",
    "execution_compensation_recorded",
)

#: The denial event template a blocked preflight describes (P22-E0 4.2.4 / 4.2.9).
_BLOCKED_EVENT_TYPES: tuple[str, ...] = ("execution_denied",)


# -- Typed request / verdict --------------------------------------------------


class SeamAdapterRequest(BaseModel):
    """Typed, echo-safe governed adapter request (P22-E0 4.3).

    Carries one-way DIGESTS, never a raw idempotency key, secret, DSN, host:port,
    auth header, raw body, or shell / SQL / script. The executor identity is
    supplied by the caller (in a live wiring it would come from the authenticated
    token via the P10 identity-only guard), never trusted from an untrusted field.
    """

    model_config = ConfigDict(extra="forbid")

    durable_approval_id: Optional[str] = None
    action_type: Optional[str] = None
    tenant_id: Optional[str] = None
    requested_state: Optional[str] = None
    dry_run_ref: Optional[str] = None
    execution_ack: bool = False
    idempotency_key_digest: Optional[str] = Field(
        None, description="SHA-256 of the client key; the raw key is never accepted or stored."
    )
    payload_digest: Optional[str] = Field(
        None, description="SHA-256 of the canonical execution payload."
    )
    actor_id: Optional[str] = None
    actor_role: str = Field("unknown", description="The authenticated executor role.")
    identity_context: str = Field("unknown", description="The authenticated identity context.")
    correlation_id: Optional[str] = None


class PreflightVerdict(BaseModel):
    """The NON-EXECUTING preflight verdict the seam returns.

    verdict is 'passed' only when every precondition holds at execution time; it
    is 'blocked' otherwise (fail closed). A 'passed' verdict means the gate would
    permit a future real execution IF the adapter were realized -- it is NOT
    execution. realized_execution and executed are ALWAYS False: the skeleton runs
    no adapter and writes no success. expected_audit_shape carries before / after /
    failure / denial event templates (FIELD NAMES ONLY); it never carries a value
    or executed=True.
    """

    model_config = ConfigDict(extra="forbid")

    action_type: Optional[str] = None
    registered: bool = Field(False, description="True only for an allowlisted action with a descriptor.")
    verdict: str = Field("blocked", description="passed | blocked.")
    block_reasons: list[BlockReasonCode] = Field(default_factory=list)
    source_status: ExecutionSourceStatus = Field(
        "unknown", description="The adapter's honest source; unknown is never healthy."
    )
    realizes_execution: bool = Field(False, description="Always False in P22-E1.")
    realized_execution: bool = Field(False, description="Always False -- the seam never executes.")
    executed: bool = Field(False, description="Always False -- the seam never executes.")
    adapter_result: str = Field(
        "not_evaluated", description="not_implemented | not_registered (always non-executing)."
    )
    expected_audit_shape: dict = Field(
        default_factory=dict,
        description="Before / after / failure / denial event templates, FIELD NAMES ONLY.",
    )
    idempotency_class: str = Field(
        "new", description="new | replay | conflict (digest-only; never the raw key)."
    )
    redaction_applied: bool = Field(True, description="Always True.")
    storage: str = Field("memory", description="Always 'memory' in P22-E1.")


# -- Audit shape (templates, field names only) --------------------------------


def expected_seam_audit_shape(verdict: str) -> dict:
    """The before / after / failure / denial audit templates for a verdict.

    Returns event_type -> field-name-list (P22-E0 4.2.5). Field NAMES ONLY: never
    a value, secret, digest-as-value, or executed=True. A passed verdict names the
    before (execution_started), after (execution_succeeded), failure
    (execution_failed), and compensation templates a future real-execution phase
    would emit; a blocked verdict names the denial (execution_denied) template.
    The skeleton writes none of them.
    """
    if verdict == "passed":
        return {et: list(SEAM_AUDIT_FIELD_NAMES) for et in _PASSED_EVENT_TYPES}
    return {et: list(SEAM_AUDIT_FIELD_NAMES) for et in _BLOCKED_EVENT_TYPES}


# -- Idempotency guard (digest-only, read-only classify) ----------------------


def classify_idempotency(
    idempotency_key_digest: Optional[str], payload_digest: Optional[str]
) -> str:
    """Digest-only replay / conflict classification (P22-E0 4.2.6).

    Read-only against the recorded request store. The raw idempotency key is
    never stored or accepted; only its one-way digest is. Returns:
      - 'new': no recorded request carries this key digest.
      - 'replay': the same key digest is recorded with a MATCHING payload digest
        (the original result stands; no second state change).
      - 'conflict': the same key digest is recorded with a DIFFERENT payload
        digest (rejected, audited as execution_denied, never a second change).
    """
    if not idempotency_key_digest:
        return "new"
    existing_id = _p22b._EXEC_BY_KEY_DIGEST.get(idempotency_key_digest)
    if not existing_id:
        return "new"
    existing = _p22b._EXEC_REQUESTS.get(existing_id)
    if existing is None:
        return "new"
    if payload_digest and existing.payload_digest == payload_digest:
        return "replay"
    return "conflict"


# -- Preflight gate (reuses the P22-B precondition evaluator) -----------------


def _dry_run_binding_block(request: SeamAdapterRequest, now: datetime) -> Optional[BlockReasonCode]:
    """Re-validate the bound dry-run at execution time (P22-E0 4.2.4).

    Reads the in-memory dry-run store only. The dry_run_ref must resolve to a
    passed dry-run that binds the SAME approval / action / tenant / requested
    state / executor and has not expired. None when the binding is valid; else a
    block code (dry_run_required | dry_run_invalid).
    """
    if not request.dry_run_ref:
        return "dry_run_required"
    dry = _p22b._DRY_RUNS.get(request.dry_run_ref)
    if dry is None:
        return "dry_run_invalid"
    if (
        dry.durable_approval_id != request.durable_approval_id
        or dry.action_type != request.action_type
        or dry.tenant_id != request.tenant_id
        or dry.requested_state != request.requested_state
        or dry.executor != request.actor_id
        or dry.expires_at is None
        or dry.expires_at <= now
    ):
        return "dry_run_invalid"
    return None


async def evaluate_preflight_gate(
    request: SeamAdapterRequest, *, db=None
) -> PreflightVerdict:
    """Re-validate the full precondition set at execution time (P22-E0 4.2.4).

    NON-EXECUTING. Reuses the P22-B precondition evaluator and returns a verdict
    that describes whether the gate would permit a future real execution through
    the seam. It never runs an adapter, never writes state, and never writes a
    success audit event. Any failed precondition blocks (fail closed).

    Re-validates: executor is identity-only super_admin; the idempotency digest is
    present; the explicit acknowledgement is present; the action is allowlisted
    (registry resolution); the bound dry-run is still valid (same binding, not
    expired); the durable approval is at approved_execution_blocked with quorum,
    matching action / target, honest source, and operator separation; and the
    digest-only idempotency is not a conflict.
    """
    now = _p22b._now()
    block_reasons: list[BlockReasonCode] = []

    # 1) executor is identity-only super_admin
    ex = _p22b._executor_block_reason(request.actor_role, request.identity_context)
    if ex is not None:
        block_reasons.append(ex)
    # 2) idempotency digest present (digest-only; raw key never accepted)
    if not request.idempotency_key_digest:
        block_reasons.append("idempotency_key_required")
    # 3) explicit execution acknowledgement present
    if not request.execution_ack:
        block_reasons.append("execution_ack_required")
    # 4) action is in the closed v0 allowlist (per-action registry resolution)
    descriptor = resolve_adapter_descriptor(request.action_type)
    if descriptor is None:
        _allowlisted, excluded_reason = _p22b._classify_action(request.action_type)
        block_reasons.append(excluded_reason or "action_not_allowlisted")  # type: ignore[arg-type]
    # 5) the bound dry-run is still valid (same binding, not expired)
    dry_block = _dry_run_binding_block(request, now)
    if dry_block is not None:
        block_reasons.append(dry_block)
    # 6) durable approval preconditions: state / quorum / source / action match /
    #    target (tenant) binding / operator separation (P22-B evaluator).
    approval = await _p22b._resolve_approval(request.durable_approval_id, db=db)
    approval_reasons, _approval_source, _reversible = _p22b._check_approval_preconditions(
        approval, request.action_type, request.actor_id, request.tenant_id
    )
    block_reasons.extend(approval_reasons)
    # 7) digest-only idempotency: a conflict blocks (replay does not, but the
    #    skeleton never applies a second state change regardless).
    idempotency_class = classify_idempotency(
        request.idempotency_key_digest, request.payload_digest
    )
    if idempotency_class == "conflict":
        block_reasons.append("idempotency_conflict")

    passed = not block_reasons
    verdict = "passed" if passed else "blocked"
    # The adapter's honest source (unknown for every adapter in P22-E1). Unknown
    # is never healthy; the approval-source precondition is enforced above.
    adapter_source = descriptor.source_status if descriptor is not None else "unknown"
    descriptor_result = non_executing_adapter_result(request.action_type)

    return PreflightVerdict(
        action_type=request.action_type,
        registered=descriptor is not None,
        verdict=verdict,
        block_reasons=block_reasons,
        source_status=adapter_source,  # type: ignore[arg-type]
        realizes_execution=ADAPTER_REALIZES_EXECUTION,
        realized_execution=SEAM_REALIZES_EXECUTION,
        executed=False,
        adapter_result=descriptor_result["adapter_result"],
        expected_audit_shape=expected_seam_audit_shape(verdict),
        idempotency_class=idempotency_class,
        redaction_applied=True,
        storage=SEAM_STORAGE_MODE,
    )


__all__ = [
    "SEAM_PHASE",
    "SEAM_REALIZES_EXECUTION",
    "SEAM_STORAGE_MODE",
    "SEAM_AUDIT_FIELD_NAMES",
    "SeamAdapterRequest",
    "PreflightVerdict",
    "expected_seam_audit_shape",
    "classify_idempotency",
    "evaluate_preflight_gate",
]
