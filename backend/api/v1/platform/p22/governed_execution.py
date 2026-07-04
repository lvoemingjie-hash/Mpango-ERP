"""P22-G governed backup.check execution -- the first REALIZED, SAFE governed action.

P22-G realizes the ``backup.check`` adapter body BEHIND the runtime governed
action adapter seam (P22-E1): the first action in the P22 v0 program that
actually COMPLETES something after approval. It proves "after approval the system
completed one safe thing" -- and that one thing is a READ.

This module is ADDITIVE and changes no existing invariant:
  - the static ``backup.check`` adapter descriptor in ``adapters.py`` STAYS
    ``not_implemented`` / ``source_unknown`` (the G15 invariant,
    ``test_p22_backup_check_still_not_implemented``, is unchanged) -- that
    descriptor is the closed GENERIC adapter name-table; this module is the
    separately-gated REALIZED adapter body anticipated by P22-E0 section 9.6;
  - the seam (``seam.py``) STAYS a NON-EXECUTING preflight boundary
    (``SEAM_REALIZES_EXECUTION`` is still False; ``evaluate_preflight_gate`` is
    reused UNCHANGED as the precondition gate);
  - the P22-B dry-run / request shapes STAY ``executed=False`` (a NEW
    governed-execution result shape carries the completed read).

What this module IS:
  - The realized adapter body for ``backup.check`` ONLY -- the single allowlisted
    action in this slice. It runs ONLY after the seam preflight passes (executor
    is identity-only super_admin; the durable approval is at
    approved_execution_blocked with quorum; a bound passed dry-run; the typed
    acknowledgement; the allowlist; the digest-only idempotency not a conflict).
  - The action CONTENT is a READ of the PROVEN P17-D-C backup / status source via
    the P22-E3 probe (``read_backup_check_source``). It performs NO backup, NO
    restore, NO dump, NO shell / child process / SQL script, NO queue drain, NO
    worker, and NO tenant mutation. Approval is not execution; this layer runs
    only after approval AND preflight, and what it runs is a read.

Result mapping (honest, source-derived; unknown is never healthy):
  - fresh success                     -> 'succeeded',              executed=True
  - stale / failed / partial / in_progress (degraded source)
                                       -> 'completed_with_warning', executed=True, warning
  - no outcome (unknown source)       -> 'completed_with_warning', executed=True, warning
  - read failure (unavailable source) -> 'failed',                 executed=False (fail-closed)
  - preflight blocked                 -> 'blocked',                executed=False

`executed=True` means the governed READ completed (a verdict was produced); it is
never a tenant mutation. `no_tenant_mutated` is ALWAYS True. `execution_allowed`
is ALWAYS False (approval is not execution; this flag is never a trigger).

Every completion records a redacted ``ExecutionAuditEvent`` (event_type
``execution_succeeded`` | ``execution_failed`` | ``execution_denied``) carrying
action_type, approval / dry-run refs, actor identity, tenant scope,
source_status, result_state, executed, the redacted reason, correlation_id, and
the one-way idempotency digest. The audit reason explicitly states no tenant
mutation occurred.

This module performs NO execution beyond the governed read: no backup, restore,
dump, shell, child process, SQL script, queue drain, or worker; it mutates no
tenant / payment / product / order / invoice / customer / inventory record.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .schemas import BlockReasonCode, ExecutionSourceStatus
from .seam import SeamAdapterRequest, evaluate_preflight_gate
from .services import _emit_audit, _now, read_execution_request
from .source_probe import BackupCheckSourceRead, read_backup_check_source


# -- Markers / vocabularies ---------------------------------------------------

#: The single allowlisted action realized in this slice (backup.check ONLY).
GOVERNED_ACTION_TYPE: str = "backup.check"

#: The P22-G phase implemented by this module.
GOVERNED_PHASE: str = "P22-G-first-safe-backup-check-action"

#: The closed governed result_state vocabulary this module realizes. These are
#: the honest outcomes of a governed READ completion (not the P22-A nine-state
#: execution-record enum; the audit layer maps to that enum).
GovernedResultState = Literal[
    "succeeded",
    "completed_with_warning",
    "failed",
    "blocked",
]

#: Audit reason recorded for every completion (the governed action never mutates).
_NO_TENANT_MUTATION = "Governed backup.check read completed; no tenant mutation occurred."


# -- Typed request / result ---------------------------------------------------


class GovernedBackupCheckRequest(BaseModel):
    """Typed, echo-safe request to complete the governed backup.check action.

    Carries one-way DIGESTS, never a raw idempotency key / secret / DSN / host.
    ``action_type`` is pinned to ``backup.check`` -- the only realized action in
    this slice. The executor identity is supplied by the caller (from the
    authenticated token in a live wiring), never trusted from an untrusted field.
    """

    model_config = ConfigDict(extra="forbid")

    action_type: Literal["backup.check"] = GOVERNED_ACTION_TYPE
    execution_request_id: Optional[str] = Field(
        None,
        description="Required: must resolve to a recorded P22 execution request that matches.",
    )
    durable_approval_id: Optional[str] = None
    tenant_id: Optional[str] = Field(None, description="Scoped id only; null for platform-wide.")
    requested_state: Optional[str] = None
    dry_run_ref: Optional[str] = None
    execution_ack: bool = False
    idempotency_key_digest: Optional[str] = Field(
        None, description="SHA-256 of the client key; the raw key is never accepted or stored."
    )
    payload_digest: Optional[str] = None
    actor_id: Optional[str] = None
    actor_role: str = "unknown"
    identity_context: str = "unknown"
    correlation_id: Optional[str] = None


class GovernedBackupCheckResult(BaseModel):
    """The honest result of the governed backup.check read-completion.

    ``executed`` is True ONLY when the governed read COMPLETED (a source verdict
    was produced); it is False when the preflight blocked or the read failed
    (fail-closed). ``no_tenant_mutated`` is ALWAYS True -- this action only reads.
    ``execution_allowed`` is ALWAYS False -- approval is not execution and this
    flag is never a trigger.
    """

    model_config = ConfigDict(extra="forbid")

    action_type: Literal["backup.check"] = GOVERNED_ACTION_TYPE
    governed_phase: Literal["P22-G-first-safe-backup-check-action"] = GOVERNED_PHASE

    execution_request_id: Optional[str] = None
    durable_approval_id: Optional[str] = None
    dry_run_ref: Optional[str] = None
    tenant_id: Optional[str] = None
    actor_id: Optional[str] = None
    actor_role: Optional[str] = None
    identity_context: Optional[str] = None

    verdict: Literal["passed", "blocked"] = Field("blocked", description="The seam preflight verdict.")
    block_reasons: list[BlockReasonCode] = Field(default_factory=list)
    source_status: ExecutionSourceStatus = Field(
        "unknown", description="known | unknown | degraded. Unknown is never healthy."
    )
    source_summary: Optional[str] = None
    result_state: GovernedResultState = Field(
        "blocked",
        description="succeeded | completed_with_warning | failed | blocked.",
    )
    warning: Optional[str] = None
    failure_reason_redacted: Optional[str] = None

    executed: bool = Field(False, description="True only when the governed read completed.")
    execution_allowed: bool = Field(
        False, description="Always False -- approval is not execution; never a trigger."
    )
    no_tenant_mutated: bool = Field(True, description="Always True -- this action only reads.")
    redaction_applied: bool = Field(True)

    correlation_id: Optional[str] = None
    idempotency_key_digest: Optional[str] = None
    payload_digest: Optional[str] = None
    audit_recorded: bool = Field(False, description="True when a redacted audit event was appended.")
    execution_started_at: Optional[datetime] = None
    execution_finished_at: Optional[datetime] = None


# -- Read -> governed result mapping ------------------------------------------


def _map_read_to_result(
    read: BackupCheckSourceRead,
) -> tuple[GovernedResultState, str, Optional[str], Optional[str], bool, str]:
    """Map a P22-E3 source read to a governed result.

    Returns ``(governed_state, audit_reason, warning, failure_reason_redacted,
    executed, audit_event_type)``. Never returns a healthy state for an unhealthy
    source; never raises. The audit reason always notes no tenant mutation.
    """
    summary = read.source_summary
    if summary == "fresh_success":
        return ("succeeded", _NO_TENANT_MUTATION, None, None, True, "execution_succeeded")
    if summary == "unavailable":
        # Read failed -> fail-closed; never a fabricated healthy status.
        reason = read.reason or "Backup source read failed; status is unavailable."
        return (
            "failed",
            f"Governed backup.check read failed (source unavailable); no tenant mutation occurred. {reason}",
            None,
            None,
            False,
            "execution_failed",
        )
    if summary == "unknown":
        # Read completed but no outcome -> completed with a warning; never healthy.
        note = read.reason or "No backup outcome has been recorded; source is unknown."
        return (
            "completed_with_warning",
            f"Governed backup.check read completed (source unknown); no tenant mutation occurred. {note}",
            note,
            None,
            True,
            "execution_succeeded",
        )
    # Degraded verdicts: stale / failed / partial / in_progress.
    warning = read.reason or f"Backup source is {read.source_status} (summary={summary})."
    failure_reason = read.failure_reason_redacted if summary in ("failed", "partial") else None
    return (
        "completed_with_warning",
        f"Governed backup.check read completed (source {read.source_status}); no tenant mutation occurred. {warning}",
        warning,
        failure_reason,
        True,
        "execution_succeeded",
    )


def _audit_state(governed_state: GovernedResultState) -> str:
    """Map the governed result_state to the P22-A execution-record audit state."""
    if governed_state == "failed":
        return "execution_failed"
    if governed_state == "blocked":
        return "blocked"
    # succeeded | completed_with_warning -> the governed read completed.
    return "executed"


# -- Recorded-request binding (P22-G-R1) --------------------------------------


def _norm(value: Optional[str]) -> Optional[str]:
    """Normalize an optional string: None for missing/empty, else the stripped value."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _request_mismatch(request: "GovernedBackupCheckRequest", stored: Any) -> Optional[str]:
    """Return a mismatch reason if the governed request does not bind to the stored
    recorded execution request, else None.

    The recorded request is the source of truth (validated at recording time). The
    governed request must bind to the SAME approval / action / tenant / dry-run /
    actor / identity / idempotency digest / payload digest, and the stored record
    must be at result_state dry_run_passed.
    """
    checks: list[tuple[bool, str]] = [
        (stored.result_state == "dry_run_passed", "result_state is not dry_run_passed"),
        (stored.action_type == GOVERNED_ACTION_TYPE, "action_type is not backup.check"),
        (_norm(stored.durable_approval_id) == _norm(request.durable_approval_id),
         "durable_approval_id mismatch"),
        (_norm(stored.tenant_id) == _norm(request.tenant_id), "tenant_id mismatch"),
        (_norm(stored.dry_run_ref) == _norm(request.dry_run_ref), "dry_run_ref mismatch"),
        (_norm(stored.actor_id) == _norm(request.actor_id), "actor_id mismatch"),
        ((stored.identity_context or "identity_only")
         == (request.identity_context or "identity_only"),
         "identity_context mismatch"),
        (_norm(stored.idempotency_key_digest) == _norm(request.idempotency_key_digest),
         "idempotency_key_digest mismatch"),
        (_norm(stored.payload_digest) == _norm(request.payload_digest),
         "payload_digest mismatch"),
    ]
    for ok, reason in checks:
        if not ok:
            return f"execution_request {request.execution_request_id} {reason}."
    return None


def _finish_blocked(
    request: "GovernedBackupCheckRequest",
    source_status: ExecutionSourceStatus,
    block_reasons: list[BlockReasonCode],
    reason: str,
    started_at: datetime,
) -> GovernedBackupCheckResult:
    """Record an execution_denied audit and return a fail-closed blocked result."""
    _emit_audit(
        event_type="execution_denied",
        actor_id=request.actor_id,
        actor_role=request.actor_role,
        identity_context=request.identity_context,
        execution_request_id=request.execution_request_id,
        durable_approval_id=request.durable_approval_id,
        action_type=request.action_type,
        tenant_id=request.tenant_id,
        result_state="blocked",
        previous_state=None,
        reason=f"{reason}; no tenant mutation occurred.",
        payload_digest=request.payload_digest,
        idempotency_key_digest=request.idempotency_key_digest,
        source_status=source_status,
        dry_run_ref=request.dry_run_ref,
        correlation_id=request.correlation_id,
        block_reasons=list(block_reasons),
        sequence_no=1,
        now=started_at,
    )
    return GovernedBackupCheckResult(
        execution_request_id=request.execution_request_id,
        durable_approval_id=request.durable_approval_id,
        dry_run_ref=request.dry_run_ref,
        tenant_id=request.tenant_id,
        actor_id=request.actor_id,
        actor_role=request.actor_role,
        identity_context=request.identity_context,
        verdict="blocked",
        block_reasons=list(block_reasons),
        source_status=source_status,
        result_state="blocked",
        executed=False,
        correlation_id=request.correlation_id,
        idempotency_key_digest=request.idempotency_key_digest,
        payload_digest=request.payload_digest,
        audit_recorded=True,
        execution_started_at=started_at,
        execution_finished_at=started_at,
    )


# -- The governed completion --------------------------------------------------


async def complete_governed_backup_check(
    request: GovernedBackupCheckRequest,
    db: Any,
) -> GovernedBackupCheckResult:
    """Complete the governed backup.check action: bind -> preflight -> read -> record.

    Requires a recorded P22 execution request (``execution_request_id``) that
    matches the governed request on approval / action / tenant / dry-run / actor /
    identity / idempotency digest / payload digest and is at result_state
    ``dry_run_passed``. Missing / unknown / mismatched -> blocked, fail-closed,
    ``executed=False``. The ONLY action content is a read of the P17-D-C source via
    the P22-E3 probe. Never mutates, never runs shell / child process / SQL script,
    never performs a backup / restore / dump, never drains a queue. Fail-closed
    throughout.
    """
    started_at = _now()

    # 1) Bind to a recorded P22 execution request (P22-G-R1). The recorded request
    #    is the source of truth; the governed request must match it exactly.
    if not _norm(request.execution_request_id):
        return _finish_blocked(
            request, "unknown", ["execution_request_required"],
            "Governed backup.check requires a recorded execution_request_id; none provided.",
            started_at,
        )
    stored = read_execution_request(request.execution_request_id)
    if stored is None:
        return _finish_blocked(
            request, "unknown", ["execution_request_not_found"],
            f"Governed backup.check execution_request {request.execution_request_id} not found.",
            started_at,
        )
    mismatch = _request_mismatch(request, stored)
    if mismatch is not None:
        return _finish_blocked(
            request, "unknown", ["execution_request_mismatch"], mismatch, started_at
        )

    # 2) Seam preflight: revalidate EVERY precondition at completion time (executor
    #    identity, approval state/quorum, dry-run binding, ack, allowlist,
    #    idempotency, source status). Reused UNCHANGED from P22-E1.
    seam_request = SeamAdapterRequest(
        durable_approval_id=request.durable_approval_id,
        action_type=request.action_type,
        tenant_id=request.tenant_id,
        requested_state=request.requested_state,
        dry_run_ref=request.dry_run_ref,
        execution_ack=request.execution_ack,
        idempotency_key_digest=request.idempotency_key_digest,
        payload_digest=request.payload_digest,
        actor_id=request.actor_id,
        actor_role=request.actor_role,
        identity_context=request.identity_context,
        correlation_id=request.correlation_id,
    )
    verdict = evaluate_preflight_gate(seam_request)
    if verdict.verdict != "passed":
        # Fail closed: a blocked preflight never reaches the read.
        return _finish_blocked(
            request, verdict.source_status, verdict.block_reasons,
            "Governed backup.check preflight blocked; action not completed.",
            started_at,
        )

    # 3) Preflight passed: complete the governed READ of the P17-D-C source.
    read = await read_backup_check_source(db, tenant_id=request.tenant_id)
    finished_at = _now()
    (
        governed_state,
        audit_reason,
        warning,
        failure_reason,
        executed,
        audit_event_type,
    ) = _map_read_to_result(read)

    _emit_audit(
        event_type=audit_event_type,
        actor_id=request.actor_id,
        actor_role=request.actor_role,
        identity_context=request.identity_context,
        execution_request_id=request.execution_request_id,
        durable_approval_id=request.durable_approval_id,
        action_type=request.action_type,
        tenant_id=request.tenant_id,
        result_state=_audit_state(governed_state),
        previous_state=None,
        reason=audit_reason,
        payload_digest=request.payload_digest,
        idempotency_key_digest=request.idempotency_key_digest,
        source_status=read.source_status,
        dry_run_ref=request.dry_run_ref,
        correlation_id=request.correlation_id,
        block_reasons=[],
        sequence_no=1,
        now=finished_at,
    )
    return GovernedBackupCheckResult(
        execution_request_id=request.execution_request_id,
        durable_approval_id=request.durable_approval_id,
        dry_run_ref=request.dry_run_ref,
        tenant_id=request.tenant_id,
        actor_id=request.actor_id,
        actor_role=request.actor_role,
        identity_context=request.identity_context,
        verdict="passed",
        source_status=read.source_status,
        source_summary=read.source_summary,
        result_state=governed_state,
        warning=warning,
        failure_reason_redacted=failure_reason,
        executed=executed,
        correlation_id=request.correlation_id,
        idempotency_key_digest=request.idempotency_key_digest,
        payload_digest=request.payload_digest,
        audit_recorded=True,
        execution_started_at=started_at,
        execution_finished_at=finished_at,
    )


__all__ = [
    "GOVERNED_ACTION_TYPE",
    "GOVERNED_PHASE",
    "GovernedResultState",
    "GovernedBackupCheckRequest",
    "GovernedBackupCheckResult",
    "complete_governed_backup_check",
]
