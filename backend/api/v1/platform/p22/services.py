"""P22 Controlled Execution v0 -- non-executing backend skeleton service layer.

This service implements the P22-B execution skeleton: it reads the v0 catalog,
runs a no-mutation dry-run validator, records (digest-only, redacted) execution
REQUESTS, and reads execution results. It NEVER executes any action.

What this service IS:
  - The closed v0 execution allowlist and exclusion list (P22-A section 3).
  - The execution precondition evaluator (P22-A section 4): identity-only
    super_admin executor, matching durable approval at approved_execution_blocked
    with quorum met, source status valid (known for writes; known or degraded for
    reads), action in the allowlist, operator separation, idempotency.
  - The dry-run validator (P22-A section 5): returns executable / verdict /
    block_reasons / expected_audit_shape; mutates nothing; records dry-run audit
    events in memory.
  - Execution-request recording (P22-A section 6 / 9): digest-only idempotency,
    redacted reason / metadata, replay vs conflict, result_state only ever
    dry_run_passed | blocked.
  - Execution-result read / list (P22-A section 12).

What this service is NOT:
  - It performs NO execution. There is no function that runs an action. There is
    no worker, no queue drain, no scheduler, no call to the P16 governed harness,
    no subprocess / shell / SQL / script, and no mutation of tenant business data,
    the P17 registry, operational flags, provisioning, backup, or any payment /
    billing / product record.
  - It adds NO migration, NO alembic change, NO table, NO auth / RBAC / session /
    tenancy rewrite, and NO frontend.
  - result_state is ONLY ever dry_run_passed | blocked. The executing / executed /
    failed / compensation / cancelled states are never assigned (they belong to a
    separately approved execution phase behind the P16 harness).

Approval is not execution and durability is not execution. A durable, quorum-met
approval at approved_execution_blocked is a PRECONDITION for a passed dry-run and
a recorded request; it is not execution itself. ``execution_allowed`` /
``executed`` / ``execution_started`` are always false.

Durable approval resolution: the service resolves a ``durable_approval_id``
through the P20/P21 durable approval READ path via an injectable resolver seam
(:func:`set_approval_resolver`). The default resolver reads the P20 in-memory
durable approval store (the feasible, DB-free read path); tests inject crafted
snapshots for determinism. P22 holds NO durable approval state of its own and
performs NO durable approval mutation.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from api.v1.platform.p18 import services as _p18

from .schemas import (
    ACTION_CLASS_MAP,
    ALLOWED_ACTION_TYPES,
    BlockReasonCode,
    CatalogItem,
    EXCLUDED_ACTION_TYPES,
    ExecutionAuditEvent,
    ExecutionCatalogResponse,
    ExecutionDryRunRequest,
    ExecutionDryRunResponse,
    ExecutionRequestCreate,
    ExecutionRequestQueue,
    ExecutionRequestResponse,
    ExecutionSourceStatus,
    ExecutionVerdict,
    ExcludedAction,
    READ_ACTION_TYPES,
    REVERSAL_MAP,
)


# -- Phase / non-execution markers -------------------------------------------

#: The P22-B storage class. The skeleton is in-memory, process-local.
STORAGE_MODE: str = "memory"

#: A passed dry-run / recorded request never permits execution in P22-B.
EXECUTION_ALLOWED: bool = False
#: Nothing is ever executed in P22-B.
EXECUTED: bool = False
#: Execution never starts in P22-B.
EXECUTION_STARTED: bool = False

#: The only two result_state values P22-B ever assigns (P22-A 7.1). The remaining
#: seven states belong to a separately approved execution phase and are never
#: produced here.
REALIZED_RESULT_STATES: frozenset[str] = frozenset({"dry_run_passed", "blocked"})

#: A passed dry-run is reusable as an execution precondition for this long.
_DRY_RUN_TTL: timedelta = timedelta(minutes=15)


# -- Vocabularies mirrored for the resolver ----------------------------------

#: The P20/P18 durable approval states that are NOT an execution precondition
#: (P22-A 4.3 / 4.10). Any of these blocks execution.
_NON_EXECUTABLE_APPROVAL_STATES: frozenset[str] = frozenset(
    {"pending_review", "rejected", "expired", "cancelled", "superseded", "failed_validation"}
)

#: The ONLY approval state that is a v0 execution precondition (P22-A 4.3).
_APPROVED_EXECUTION_BLOCKED: str = "approved_execution_blocked"


# -- In-memory execution-request store (ephemeral, process-local) -------------


class _StoredDryRun:
    """A passed dry-run bound as an execution precondition. Ephemeral, in memory."""

    __slots__ = (
        "dry_run_id",
        "durable_approval_id",
        "action_type",
        "tenant_id",
        "requested_state",
        "executor",
        "source_status",
        "execution_mode",
        "created_at",
        "expires_at",
    )

    def __init__(self, **kwargs: Any) -> None:
        for key in self.__slots__:
            setattr(self, key, kwargs.get(key))


class _StoredExecutionRequest:
    """A recorded execution request. Ephemeral, in memory. Never executed."""

    __slots__ = (
        "execution_request_id",
        "durable_approval_id",
        "action_type",
        "tenant_id",
        "requested_state",
        "reason_redacted",
        "idempotency_key_digest",
        "payload_digest",
        "actor_id",
        "actor_role",
        "identity_context",
        "execution_mode",
        "dry_run_ref",
        "execution_ack",
        "correlation_id",
        "metadata_redacted",
        "result_state",
        "result",
        "message",
        "sequence_no",
        "created_at",
        "updated_at",
    )

    def __init__(self, **kwargs: Any) -> None:
        for key in self.__slots__:
            setattr(self, key, kwargs.get(key))


_DRY_RUNS: dict[str, _StoredDryRun] = {}  # dry_run_id -> passed dry-run binding
_EXEC_REQUESTS: dict[str, _StoredExecutionRequest] = {}  # execution_request_id -> request
# SHA-256 digest of the execution idempotency_key -> execution_request_id. The
# RAW idempotency_key is never stored; only its one-way digest is.
_EXEC_BY_KEY_DIGEST: dict[str, str] = {}
_EXEC_AUDIT: list[ExecutionAuditEvent] = []


def reset_store() -> None:
    """Clear the in-memory dry-run / execution-request / audit state. Used by tests."""
    _DRY_RUNS.clear()
    _EXEC_REQUESTS.clear()
    _EXEC_BY_KEY_DIGEST.clear()
    _EXEC_AUDIT.clear()


def audit_log() -> list[ExecutionAuditEvent]:
    """Return a copy of the in-memory execution audit events (for tests / inspection)."""
    return list(_EXEC_AUDIT)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _digest(value: Optional[str]) -> str:
    """One-way SHA-256 hex digest. Used for idempotency keys and payload fingerprints.

    The RAW idempotency_key is never stored in a record slot or an audit event;
    only this one-way digest is. The digest is safe to echo / audit.
    """
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def _payload_digest(
    durable_approval_id: Optional[str],
    action_type: Optional[str],
    tenant_id: Optional[str],
    requested_state: Optional[str],
    executor: Optional[str],
) -> str:
    """SHA-256 of the canonical execution payload (P22-A section 6).

    Built from echo-safe identifiers only (approval / action / tenant / state /
    executor). Drives replay dedup: same key + same payload_digest is an
    idempotent replay; same key + different payload_digest is a conflict.
    """
    raw = "|".join(
        [
            durable_approval_id or "",
            action_type or "",
            tenant_id or "",
            requested_state or "",
            executor or "",
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# -- Durable approval resolution (read-only seam) -----------------------------


class ApprovalSnapshot:
    """A read-only view of the durable approval fields P22 needs to evaluate
    preconditions.

    P22 holds no durable approval state of its own; it resolves a
    durable_approval_id to one of these through the P20/P21 read path (default:
    the P20 in-memory store) or an injected test resolver. source_status is in
    the P22 vocabulary (known | unknown | degraded).
    """

    __slots__ = (
        "approval_id",
        "state",
        "quorum_required",
        "quorum_met",
        "maker",
        "checker_ids",
        "source_status",
        "action_type",
        "action_class",
        "tenant_id",
        "validation_status",
        "expires_at",
    )

    def __init__(self, **kwargs: Any) -> None:
        for key in self.__slots__:
            setattr(self, key, kwargs.get(key))


#: P20/P18 source-status (available / unavailable / unknown) -> P22 vocabulary
#: (known / unknown / degraded). `available` -> `known` (healthy); `unavailable`
#: -> `degraded` (the only degraded allowance, reads only); `unknown` -> `unknown`
#: (never healthy). The map never upgrades an unknown / unavailable source to
#: known for writes (the evaluator enforces that separately).
_P20_TO_P22_SOURCE: dict[str, str] = {
    "available": "known",
    "unavailable": "degraded",
    "unknown": "unknown",
}


#: Test / dev override seam for the durable approval resolver. None resolves
#: through the default P20 in-memory read path.
_RESOLVER_OVERRIDE: Optional[Callable[[str], Optional[ApprovalSnapshot]]] = None


def set_approval_resolver(
    resolver: Optional[Callable[[str], Optional[ApprovalSnapshot]]],
) -> None:
    """TEST / DEV SEAM: inject a durable-approval resolver.

    The resolver maps a durable_approval_id to an :class:`ApprovalSnapshot` (or
    None when not found). Passing None restores the default resolver, which reads
    the P20 in-memory durable approval store (the feasible, DB-free read path).
    """
    global _RESOLVER_OVERRIDE
    _RESOLVER_OVERRIDE = resolver


def reset_approval_resolver() -> None:
    """Restore the default durable-approval resolver (P20 in-memory read path)."""
    set_approval_resolver(None)


def _snapshot_from_p20_record(rec: Any) -> ApprovalSnapshot:
    """Map a P20 ``DurableApprovalRecord`` to an :class:`ApprovalSnapshot`.

    The P20 record carries the P18/P20 source vocabulary and the maker / checker
    summary. P22 never mutates it. ``degraded`` has no P20 source counterpart; an
    unavailable source maps to degraded so a read may proceed against it (writes
    are blocked by the evaluator).
    """
    checker_ids = [c.checker_id for c in (getattr(rec, "checkers", None) or [])]
    return ApprovalSnapshot(
        approval_id=getattr(rec, "approval_id", None),
        state=getattr(rec, "state", None),
        quorum_required=int(getattr(rec, "quorum_required", 0) or 0),
        quorum_met=bool(getattr(rec, "quorum_met", False)),
        maker=getattr(rec, "maker", None),
        checker_ids=checker_ids,
        source_status=_P20_TO_P22_SOURCE.get(getattr(rec, "source_status", "unknown"), "unknown"),
        action_type=getattr(rec, "action_type", None),
        action_class=getattr(rec, "action_class", None),
        tenant_id=getattr(rec, "tenant_id", None),
        validation_status=getattr(rec, "validation_status", None),
        expires_at=getattr(rec, "expires_at", None),
    )


def _default_resolve_approval(approval_id: Optional[str]) -> Optional[ApprovalSnapshot]:
    """Default resolver: read the P20 in-memory durable approval store.

    This is the feasible, DB-free P20/P21 read path. It reads the process-local
    in-memory durable approval store directly (no DB session, no async engine).
    If the approval is absent the resolver returns None (treated as not-found ->
    blocked). It never mutates durable approval state.
    """
    if not approval_id:
        return None
    try:
        # Lazy import avoids any import-time coupling to the P20 service module
        # (which wires the P21 durable adapter). The in-memory read is sync and
        # touches only the process-local _STORE.
        from api.v1.platform.p20.services import _memory_read_durable_approval
    except Exception:
        return None
    try:
        rec = _memory_read_durable_approval(approval_id)
    except Exception:
        return None
    if rec is None:
        return None
    return _snapshot_from_p20_record(rec)


def _resolve_approval(approval_id: Optional[str]) -> Optional[ApprovalSnapshot]:
    """Resolve a durable_approval_id through the active resolver (override > default)."""
    resolver = _RESOLVER_OVERRIDE or _default_resolve_approval
    try:
        return resolver(approval_id)
    except Exception:
        # Conservative: any resolver error yields no snapshot (unknown -> blocked).
        return None


# -- Audit (in-memory, append-only, redacted) --------------------------------

#: The echo-safe field names execution audit events carry (P22-A 5.2 / 8.1). Used
#: for ``expected_audit_shape`` (field names ONLY, never values / secrets).
_AUDIT_FIELD_NAMES: tuple[str, ...] = (
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


def _emit_audit(
    *,
    event_type: str,
    actor_id: Optional[str],
    actor_role: str,
    identity_context: str,
    execution_request_id: Optional[str],
    durable_approval_id: Optional[str],
    action_type: Optional[str],
    tenant_id: Optional[str],
    result_state: Optional[str],
    previous_state: Optional[str],
    reason: str,
    payload_digest: Optional[str],
    idempotency_key_digest: Optional[str],
    source_status: Optional[str],
    dry_run_ref: Optional[str],
    correlation_id: Optional[str],
    block_reasons: list[BlockReasonCode],
    sequence_no: int,
    now: datetime,
) -> ExecutionAuditEvent:
    """Build, record, and return one redacted execution audit event.

    The reason is redacted via the P18 allowlist internally so a raw reason can
    never reach the audit log. Only the one-way digests and the redacted reason
    are recorded; the raw idempotency key, raw secrets, DSNs, host:port, auth
    headers, raw bodies, and shell / SQL / script NEVER appear.
    """
    from uuid import uuid4

    event = ExecutionAuditEvent(
        event_id=str(uuid4()),
        event_type=event_type,  # type: ignore[arg-type]
        execution_request_id=execution_request_id,
        durable_approval_id=durable_approval_id,
        action_id=None,
        actor_id=actor_id,
        actor_role=actor_role,  # type: ignore[arg-type]
        identity_context=identity_context,  # type: ignore[arg-type]
        action_type=action_type,
        tenant_id=tenant_id,
        result_state=result_state,  # type: ignore[arg-type]
        previous_state=previous_state,  # type: ignore[arg-type]
        reason_redacted=_p18._redact_reason(reason),
        payload_digest=payload_digest,
        idempotency_key_digest=idempotency_key_digest,
        source_status=source_status,  # type: ignore[arg-type]
        dry_run_ref=dry_run_ref,
        redaction_applied=True,
        correlation_id=_p18._sanitize_text(correlation_id),
        block_reasons=list(block_reasons),
        sequence_no=sequence_no,
        created_at=now,
    )
    _EXEC_AUDIT.append(event)
    return event


def _expected_audit_shape(executable: bool, execution_mode: Optional[str]) -> dict:
    """The event_type(s) execution would emit, with FIELD NAMES ONLY (P22-A 5.2).

    Never values, secrets, or raw payloads. A passed dry-run names the dry-run
    events plus the execution events a separately approved phase would emit; a
    blocked dry-run names the dry-run blocked / denial events.
    """
    if executable:
        events = ["execution_dry_run_requested", "execution_dry_run_passed"]
        # The events a FUTURE separately-approved execution phase would emit
        # (P22-B emits none of them; this is the expected shape only).
        if execution_mode == "queued":
            events += ["execution_requested", "execution_started", "execution_succeeded"]
        else:
            events += ["execution_requested", "execution_started", "execution_succeeded"]
        return {et: list(_AUDIT_FIELD_NAMES) for et in events}
    return {
        "execution_dry_run_requested": list(_AUDIT_FIELD_NAMES),
        "execution_dry_run_blocked": list(_AUDIT_FIELD_NAMES),
        "execution_denied": list(_AUDIT_FIELD_NAMES),
    }


# -- Precondition evaluation (shared by dry-run and request) ------------------


def _executor_block_reason(actor_role: str, identity_context: str) -> Optional[BlockReasonCode]:
    """None when the executor is an identity-only super_admin; else a block code."""
    if actor_role == "super_admin" and identity_context == "identity_only":
        return None
    return "executor_not_identity_super_admin"


def _classify_action(action_type: Optional[str]) -> tuple[bool, Optional[str]]:
    """Return (is_allowlisted, excluded_or_none) for an action_type.

    An allowlisted action is in ALLOWED_ACTION_TYPES. A named excluded action
    (tenant.pause / tenant.resume / lifecycle.transition) yields the excluded
    code; any other unknown action yields action_not_allowlisted.
    """
    if action_type in ALLOWED_ACTION_TYPES:
        return True, None
    if action_type in EXCLUDED_ACTION_TYPES:
        return False, "action_excluded"
    return False, "action_not_allowlisted"


def _check_approval_preconditions(
    approval: Optional[ApprovalSnapshot],
    action_type: Optional[str],
    executor: Optional[str],
) -> tuple[list[BlockReasonCode], Optional[ExecutionSourceStatus], bool]:
    """Evaluate the approval-dependent preconditions (P22-A 4.2-4.6 / 4.10-4.12).

    Returns (block_reasons, source_status, reversible). source_status is the P22
    vocabulary value to surface; reversible is whether a paired reversal exists.
    """
    reasons: list[BlockReasonCode] = []
    if approval is None:
        reasons.append("approval_not_found")
        return reasons, "unknown", False

    if approval.state != _APPROVED_EXECUTION_BLOCKED:
        reasons.append("approval_state_not_approved_execution_blocked")
    if not approval.quorum_met:
        reasons.append("quorum_not_met")
    # The approval must be for the SAME action the executor is trying to run.
    if approval.action_type and action_type and approval.action_type != action_type:
        reasons.append("action_mismatch_approval")

    # Source status: writes / write-requests require a known source; reads may
    # proceed against a degraded source (P22-A 4.5 / 10.10).
    action_class = ACTION_CLASS_MAP.get(action_type or "")
    source_status: ExecutionSourceStatus = approval.source_status or "unknown"
    is_write = action_class in ("write", "write_request")
    if is_write and source_status != "known":
        reasons.append("source_unknown_for_write")

    # Operator separation: executor distinct from maker and every checker.
    if executor and approval.maker and executor == approval.maker:
        reasons.append("self_execution_forbidden")
    if executor and approval.checker_ids and executor in approval.checker_ids:
        reasons.append("checker_execution_forbidden")

    reversible = bool(REVERSAL_MAP.get(action_type or ""))
    return reasons, source_status, reversible


# -- Catalog ------------------------------------------------------------------


def build_catalog() -> ExecutionCatalogResponse:
    """Return the closed v0 execution catalog (allowlist + exclusions). Read-only."""
    items = [
        CatalogItem(
            action_type=at,  # type: ignore[arg-type]
            action_class=ACTION_CLASS_MAP[at],  # type: ignore[arg-type]
            reversible=bool(REVERSAL_MAP.get(at)),
            reversibility_via=REVERSAL_MAP.get(at),  # type: ignore[arg-type]
        )
        for at in ALLOWED_ACTION_TYPES
    ]
    exclusions = [
        ExcludedAction(
            action_type="tenant.pause",
            reason="destructive lifecycle (blocks tenant logins / writes); excluded from v0.",
        ),
        ExcludedAction(
            action_type="tenant.resume",
            reason="destructive lifecycle (moves tenant out of paused / suspended); excluded from v0.",
        ),
        ExcludedAction(
            action_type="lifecycle.transition",
            reason="generic destructive lifecycle transition; excluded from v0.",
        ),
        ExcludedAction(
            action_type="real restore",
            reason="restoring real tenant data; only backup.restore_test_request (test-only) is allowlisted.",
        ),
        ExcludedAction(
            action_type="schema migration",
            reason="any DDL / alembic / schema change; excluded from v0 forever.",
        ),
        ExcludedAction(
            action_type="data deletion",
            reason="any deletion of tenant or platform records; excluded from v0 forever.",
        ),
        ExcludedAction(
            action_type="payment / billing",
            reason="any payment, billing, invoice, or financial-record action; excluded from v0.",
        ),
        ExcludedAction(
            action_type="tenant business records",
            reason="any read / write of orders, payments, invoices, customers, inventory, ledgers.",
        ),
        ExcludedAction(
            action_type="arbitrary shell / SQL / script",
            reason="no general code-execution surface exists or is introduced in any P22 phase.",
        ),
    ]
    return ExecutionCatalogResponse(
        items=items,
        exclusions=exclusions,
        total=len(items),
        contract="P22-A",
        storage=STORAGE_MODE,
        executed=EXECUTED,
    )


# -- Dry-run ------------------------------------------------------------------


def evaluate_dry_run(
    request: ExecutionDryRunRequest,
    *,
    actor: Optional[str],
    actor_role: str,
    identity_context: str,
) -> ExecutionDryRunResponse:
    """Validate an execution against the preconditions; return a no-mutation verdict.

    NEVER executes. Mutates nothing except recording dry-run audit events in
    memory (and, when the verdict is passed, binding the dry-run for a later
    execution request via dry_run_ref). Returns executable / verdict /
    block_reasons / expected_audit_shape / source_status / reversible.

    Order of checks: executor identity -> idempotency key present -> action
    allowlisted -> approval resolves -> approval preconditions (state / quorum /
    source / action match / operator separation). Every failed precondition is
    collected into block_reasons; a single failure blocks the dry-run.
    """
    now = _now()
    raw_reason = (request.reason or "").strip()
    raw_key = (request.idempotency_key or "").strip()
    safe_reason = _p18._redact_reason(raw_reason)
    safe_correlation_id = _p18._sanitize_text(request.correlation_id)
    _ = _p18.redact_metadata(request.metadata)  # redact (defense in depth); not echoed on dry-run
    key_digest = _digest(raw_key)
    safe_action_type = _p18._sanitize_text(request.action_type) or request.action_type
    # execution_mode is request-lenient (plain str); coerce to the strict vocab so a
    # bad value can never reach the strict response field (never a 500).
    safe_mode: Optional[str] = request.execution_mode if request.execution_mode in ("sync", "queued") else None

    block_reasons: list[BlockReasonCode] = []

    # 1) executor is identity-only super_admin
    ex = _executor_block_reason(actor_role, identity_context)
    if ex is not None:
        block_reasons.append(ex)
    # 2) idempotency key present (digest-only)
    if not raw_key:
        block_reasons.append("idempotency_key_required")
    # 3) action is in the closed v0 allowlist
    allowlisted, excluded_reason = _classify_action(request.action_type)
    if not allowlisted:
        block_reasons.append(excluded_reason or "action_not_allowlisted")  # type: ignore[arg-type]

    # 4) approval resolves + 5) approval preconditions
    approval = _resolve_approval(request.durable_approval_id)
    approval_reasons, source_status, reversible = _check_approval_preconditions(
        approval, request.action_type, actor
    )
    block_reasons.extend(approval_reasons)

    executable = not block_reasons
    verdict: ExecutionVerdict = "passed" if executable else "blocked"

    # expected audit shape (field names only) + dry-run audit events (in memory)
    expected = _expected_audit_shape(executable, safe_mode)
    # sequence_no is per execution_request; dry-run events use 0 (no request yet).
    _emit_audit(
        event_type="execution_dry_run_requested",
        actor_id=actor,
        actor_role=actor_role,
        identity_context=identity_context,
        execution_request_id=None,
        durable_approval_id=request.durable_approval_id,
        action_type=safe_action_type,
        tenant_id=request.tenant_id,
        result_state=None,
        previous_state=None,
        reason=safe_reason,
        payload_digest=None,
        idempotency_key_digest=key_digest if raw_key else None,
        source_status=source_status,
        dry_run_ref=None,
        correlation_id=safe_correlation_id,
        block_reasons=block_reasons,
        sequence_no=0,
        now=now,
    )
    _emit_audit(
        event_type="execution_dry_run_passed" if executable else "execution_dry_run_blocked",
        actor_id=actor,
        actor_role=actor_role,
        identity_context=identity_context,
        execution_request_id=None,
        durable_approval_id=request.durable_approval_id,
        action_type=safe_action_type,
        tenant_id=request.tenant_id,
        result_state=None,
        previous_state=None,
        reason=safe_reason,
        payload_digest=None,
        idempotency_key_digest=key_digest if raw_key else None,
        source_status=source_status,
        dry_run_ref=None,
        correlation_id=safe_correlation_id,
        block_reasons=[] if executable else block_reasons,
        sequence_no=0,
        now=now,
    )

    dry_run_id: Optional[str] = None
    if executable:
        # Bind the passed dry-run as an execution precondition (reusable via dry_run_ref).
        from uuid import uuid4

        dry_run_id = str(uuid4())
        _DRY_RUNS[dry_run_id] = _StoredDryRun(
            dry_run_id=dry_run_id,
            durable_approval_id=request.durable_approval_id,
            action_type=request.action_type,
            tenant_id=request.tenant_id,
            requested_state=request.requested_state,
            executor=actor,
            source_status=source_status,
            execution_mode=safe_mode,
            created_at=now,
            expires_at=now + _DRY_RUN_TTL,
        )

    return ExecutionDryRunResponse(
        dry_run_id=dry_run_id,
        durable_approval_id=request.durable_approval_id,
        action_type=safe_action_type,
        tenant_id=request.tenant_id,
        requested_state=request.requested_state,
        executable=executable,
        verdict=verdict,
        block_reasons=block_reasons,
        expected_audit_shape=expected,
        execution_mode=safe_mode,  # type: ignore[arg-type]
        source_status=source_status,
        reversible=reversible,
        redaction_applied=True,
        idempotency_key_digest=key_digest if raw_key else None,
        storage=STORAGE_MODE,
        executed=EXECUTED,
        execution_started=EXECUTION_STARTED,
        execution_allowed=EXECUTION_ALLOWED,
        created_at=now,
    )


# -- Execution request --------------------------------------------------------


def _response_from(
    rec: _StoredExecutionRequest, *, result: Optional[str] = None, message: Optional[str] = None
) -> ExecutionRequestResponse:
    """Build the uniform execution-request response. Never executes."""
    return ExecutionRequestResponse(
        execution_request_id=rec.execution_request_id,
        durable_approval_id=rec.durable_approval_id,
        action_type=rec.action_type,
        tenant_id=rec.tenant_id,
        requested_state=rec.requested_state,
        reason_redacted=rec.reason_redacted,
        idempotency_key_digest=rec.idempotency_key_digest,
        payload_digest=rec.payload_digest,
        actor_id=rec.actor_id,
        actor_role=rec.actor_role,
        identity_context=rec.identity_context,
        execution_mode=rec.execution_mode,
        dry_run_ref=rec.dry_run_ref,
        execution_ack=rec.execution_ack,
        correlation_id=rec.correlation_id,
        metadata_redacted=rec.metadata_redacted,
        redaction_applied=True,
        result_state=rec.result_state,  # type: ignore[arg-type]
        block_reasons=[],
        result=result or rec.result,
        message=message or rec.message,
        storage=STORAGE_MODE,
        executed=EXECUTED,
        execution_started=EXECUTION_STARTED,
        execution_allowed=EXECUTION_ALLOWED,
        created_at=rec.created_at,
        updated_at=rec.updated_at,
    )


def record_execution_request(
    request: ExecutionRequestCreate,
    *,
    actor: Optional[str],
    actor_role: str,
    identity_context: str,
) -> ExecutionRequestResponse:
    """Record an execution request after a passed dry-run and acknowledgement.

    NEVER executes, NEVER dispatches a worker, NEVER drains a queue, NEVER
    invokes the P16 harness. result_state is only ever dry_run_passed (request
    recorded after a passed dry-run + ack + re-validated preconditions) or blocked
    (a precondition failed, or an idempotency conflict). It is NEVER executing /
    executed / failed / compensation / cancelled.

    Idempotency is digest-only (P22-A section 9): the raw idempotency_key is
    hashed at the boundary and discarded. A repeat with the same
    idempotency_key_digest and a matching payload_digest is an idempotent replay
    (returns the original response, no new success audit). The same digest with a
    different payload_digest is a conflict (blocked, audited as execution_denied,
    never a second state change).
    """
    now = _now()
    raw_reason = (request.reason or "").strip()
    raw_key = (request.idempotency_key or "").strip()
    safe_reason = _p18._redact_reason(raw_reason)
    safe_correlation_id = _p18._sanitize_text(request.correlation_id)
    redacted_md = _p18.redact_metadata(request.metadata)
    key_digest = _digest(raw_key)
    safe_action_type = _p18._sanitize_text(request.action_type) or request.action_type
    # execution_mode is request-lenient (plain str); coerce to the strict vocab.
    safe_mode: Optional[str] = request.execution_mode if request.execution_mode in ("sync", "queued") else None
    payload_digest = _payload_digest(
        request.durable_approval_id,
        request.action_type,
        request.tenant_id,
        request.requested_state,
        actor,
    )

    block_reasons: list[BlockReasonCode] = []
    denied_message: Optional[str] = None

    # 1) executor is identity-only super_admin
    ex = _executor_block_reason(actor_role, identity_context)
    if ex is not None:
        block_reasons.append(ex)
    # 2) idempotency key present
    if not raw_key:
        block_reasons.append("idempotency_key_required")
    # 3) execution acknowledgement present
    if not request.execution_ack:
        block_reasons.append("execution_ack_required")
    # 4) action is in the closed v0 allowlist
    allowlisted, excluded_reason = _classify_action(request.action_type)
    if not allowlisted:
        block_reasons.append(excluded_reason or "action_not_allowlisted")  # type: ignore[arg-type]
    # 5) a passed dry-run is bound (dry_run_ref) and matches approval/action/target/executor
    dry_run = _DRY_RUNS.get(request.dry_run_ref or "")
    if not request.dry_run_ref:
        block_reasons.append("dry_run_required")
    elif dry_run is None:
        block_reasons.append("dry_run_invalid")
    elif (
        dry_run.durable_approval_id != request.durable_approval_id
        or dry_run.action_type != request.action_type
        or dry_run.tenant_id != request.tenant_id
        or dry_run.requested_state != request.requested_state
        or dry_run.executor != actor
        or dry_run.expires_at is None
        or dry_run.expires_at <= now
    ):
        block_reasons.append("dry_run_invalid")

    # 6) re-validate the approval preconditions at request time (P22-A 4 / 10.5)
    approval = _resolve_approval(request.durable_approval_id)
    approval_reasons, source_status, _reversible = _check_approval_preconditions(
        approval, request.action_type, actor
    )
    block_reasons.extend(approval_reasons)

    # 7) idempotency: replay vs conflict (BEFORE recording). Keyed by the digest,
    #    never the raw key. A matching payload_digest is a replay; a mismatch is a
    #    conflict that is rejected and audited (never a second state change).
    existing_id = _EXEC_BY_KEY_DIGEST.get(key_digest) if raw_key else None
    is_conflict = False
    replay_response: Optional[ExecutionRequestResponse] = None
    if existing_id is not None and raw_key:
        existing = _EXEC_REQUESTS.get(existing_id)
        if existing is not None and existing.payload_digest == payload_digest:
            # idempotent replay: return the original response, no new success audit
            replay_response = _response_from(existing)
        elif existing is not None:
            is_conflict = True
            block_reasons.append("idempotency_conflict")
            denied_message = (
                "Conflict: idempotency_key already recorded with a different execution "
                "payload; rejected, audited, and NOT executed."
            )

    # If a precondition failed OR an idempotency conflict occurred -> blocked.
    # The request is recorded only on a clean (non-replay, non-conflict) pass.
    blocked = bool(block_reasons)
    denied = blocked and replay_response is None

    # Allocate the execution_request_id + per-request sequence base up front so
    # audit events can reference it (matches the contract shape). Only persisted
    # when the request is recorded (clean pass).
    from uuid import uuid4

    execution_request_id = str(uuid4())

    if replay_response is not None:
        # Idempotent replay: NO new success audit event (P22-A 9 / C20). Denials
        # are always auditable, but a replay of a recorded request is not a
        # denial; emit nothing and return the original response.
        return replay_response

    if denied:
        result_state = "blocked"
        result = "denied" if not is_conflict else "conflict"
        message = denied_message or (
            "Blocked: an execution precondition failed; the request was not recorded "
            "and nothing was executed."
        )
        # Audited as execution_denied (a denial is always auditable; P22-A 8.2).
        _emit_audit(
            event_type="execution_denied",
            actor_id=actor,
            actor_role=actor_role,
            identity_context=identity_context,
            execution_request_id=None,
            durable_approval_id=request.durable_approval_id,
            action_type=safe_action_type,
            tenant_id=request.tenant_id,
            result_state=result_state,
            previous_state=None,
            reason=safe_reason,
            payload_digest=payload_digest,
            idempotency_key_digest=key_digest if raw_key else None,
            source_status=source_status,
            dry_run_ref=request.dry_run_ref,
            correlation_id=safe_correlation_id,
            block_reasons=block_reasons,
            sequence_no=1,
            now=now,
        )
        # A blocked / denied / conflict request is NOT recorded (no state change,
        # no second application). Return a non-recorded response shape.
        return ExecutionRequestResponse(
            execution_request_id=None,
            durable_approval_id=request.durable_approval_id,
            action_type=safe_action_type,
            tenant_id=request.tenant_id,
            requested_state=request.requested_state,
            reason_redacted=safe_reason,
            idempotency_key_digest=key_digest if raw_key else None,
            payload_digest=payload_digest,
            actor_id=actor,
            actor_role=actor_role,  # type: ignore[arg-type]
            identity_context=identity_context,  # type: ignore[arg-type]
            execution_mode=safe_mode,  # type: ignore[arg-type]
            dry_run_ref=request.dry_run_ref,
            execution_ack=request.execution_ack,
            correlation_id=safe_correlation_id,
            metadata_redacted=redacted_md,
            redaction_applied=True,
            result_state=result_state,  # type: ignore[arg-type]
            block_reasons=block_reasons,
            result=result,
            message=message,
            storage=STORAGE_MODE,
            executed=EXECUTED,
            execution_started=EXECUTION_STARTED,
            execution_allowed=EXECUTION_ALLOWED,
            created_at=now,
            updated_at=now,
        )

    # Clean pass: record the execution request at dry_run_passed. NEVER transition
    # to executing / executed (no worker, no harness, no execution).
    rec = _StoredExecutionRequest(
        execution_request_id=execution_request_id,
        durable_approval_id=request.durable_approval_id,
        action_type=safe_action_type,
        tenant_id=request.tenant_id,
        requested_state=request.requested_state,
        reason_redacted=safe_reason,
        idempotency_key_digest=key_digest,
        payload_digest=payload_digest,
        actor_id=actor,
        actor_role=actor_role,
        identity_context=identity_context,
        execution_mode=safe_mode,
        dry_run_ref=request.dry_run_ref,
        execution_ack=request.execution_ack,
        correlation_id=safe_correlation_id,
        metadata_redacted=redacted_md,
        result_state="dry_run_passed",
        result="recorded",
        message=(
            "Recorded: the execution request was recorded at dry_run_passed after a passed "
            "dry-run and acknowledgement. P22-B does NOT execute; no worker was dispatched, "
            "no queue was drained, no P16 harness was invoked, and no tenant / payment / "
            "product state changed."
        ),
        sequence_no=1,
        created_at=now,
        updated_at=now,
    )
    _EXEC_REQUESTS[execution_request_id] = rec
    _EXEC_BY_KEY_DIGEST[key_digest] = execution_request_id
    _emit_audit(
        event_type="execution_requested",
        actor_id=actor,
        actor_role=actor_role,
        identity_context=identity_context,
        execution_request_id=execution_request_id,
        durable_approval_id=request.durable_approval_id,
        action_type=safe_action_type,
        tenant_id=request.tenant_id,
        result_state="dry_run_passed",
        previous_state=None,
        reason=safe_reason,
        payload_digest=payload_digest,
        idempotency_key_digest=key_digest,
        source_status=source_status,
        dry_run_ref=request.dry_run_ref,
        correlation_id=safe_correlation_id,
        block_reasons=[],
        sequence_no=1,
        now=now,
    )
    return _response_from(rec)


# -- Read / list --------------------------------------------------------------


def list_execution_requests(
    limit: int = 50,
    offset: int = 0,
    result_state: Optional[str] = None,
    action_type: Optional[str] = None,
    durable_approval_id: Optional[str] = None,
) -> ExecutionRequestQueue:
    """Return the current process-local queue of recorded execution requests.

    Optional filters: result_state, action_type, durable_approval_id. Read-only;
    never executes.
    """
    safe_limit = max(1, min(limit, 100))
    safe_offset = max(0, offset)
    records = sorted(
        _EXEC_REQUESTS.values(),
        key=lambda r: r.created_at or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    if result_state:
        records = [r for r in records if r.result_state == result_state]
    if action_type:
        records = [r for r in records if r.action_type == action_type]
    if durable_approval_id:
        records = [r for r in records if r.durable_approval_id == durable_approval_id]
    items = [_response_from(r) for r in records[safe_offset : safe_offset + safe_limit]]
    return ExecutionRequestQueue(
        items=items,
        total=len(records),
        limit=safe_limit,
        offset=safe_offset,
        storage=STORAGE_MODE,
        executed=EXECUTED,
    )


def read_execution_request(execution_request_id: str) -> Optional[ExecutionRequestResponse]:
    """Return the recorded execution request by id, or None when not found."""
    rec = _EXEC_REQUESTS.get(execution_request_id)
    if rec is None:
        return None
    return _response_from(rec)


__all__ = [
    # markers
    "STORAGE_MODE",
    "EXECUTION_ALLOWED",
    "EXECUTED",
    "EXECUTION_STARTED",
    "REALIZED_RESULT_STATES",
    # store
    "reset_store",
    "audit_log",
    "ApprovalSnapshot",
    "set_approval_resolver",
    "reset_approval_resolver",
    # operations
    "build_catalog",
    "evaluate_dry_run",
    "record_execution_request",
    "list_execution_requests",
    "read_execution_request",
]
