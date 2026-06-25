"""P20 Durable Approval Governance -- service layer (P20-B skeleton).

SAFE skeleton: opens durable approval requests, lists and reads them, and
records per-checker approve / reject DECISIONS under a maker-checker,
quorum-based dual-control policy -- all in process-local memory. It NEVER
executes any controlled action and NEVER mutates the P17 registry, tenant
lifecycle, operational flags, provisioning, backup, or any tenant business
data. Approval is NOT execution and durability is NOT execution: a quorum-met
approval resolves to ``approved_execution_blocked`` and ``execution_allowed``
is always false. Recorded approvals are ephemeral (in-process memory) -- there
is intentionally no database table and no migration.

Dual-control policy (P20-A section 4):
  - maker-checker: the maker (the actor who opened the request) can never be a
    checker on the same approval. A decision whose approver_id == maker is
    denied (self-approval forbidden).
  - distinct checkers: each checker records at most one decision per approval;
    a repeat with the same decision is idempotent, a flip to a different
    decision is a conflict.
  - quorum: write / write_request floor of two distinct approve checkers
    (excluding the maker); read floor of one. quorum_met becomes true only when
    the distinct approve count reaches the floor and no reject is recorded.
  - reject is final: any single reject vetoes the approval (state -> rejected,
    terminal).

P18 validation boundary: a durable approval wraps a P18 controlled-action
request. ``_resolve_p18_context`` resolves the action_type, the P18 source
status, and the action class either from a recorded P18 action_id or, when only
an action_type is supplied, via the P18 catalog + registry source-status
resolver. It is conservative on every failure path: a missing action_id, an
unknown action_type, or any resolver error yields no context, and an unknown
source status is stored verbatim (never fabricated as available). An approve
against an unknown / unavailable source is denied.

Redaction reuses P18 verbatim (redact_metadata / _redact_reason / _sanitize_text
/ _reason_is_sensitive): a reason or value carrying any secret keyword, scheme,
or host:port pattern is replaced wholesale with "[redacted]". The RAW reason is
used only for the one-way request digest / idempotency digest (hashes that are
never echoed or audited).

State machine (P20-A section 6): P20-B implements only pending_review ->
approved_execution_blocked | rejected. Transitions to expired / cancelled /
superseded / failed_validation are NOT implemented and are explicitly rejected
(see submit_decision). The full seven-state enum lives in schemas.py.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.platform.p18 import services as _p18

from .schemas import (
    CheckerDecisionSummary,
    DurableApprovalAuditEvent,
    DurableApprovalQueue,
    DurableApprovalRecord,
)


# -- In-memory durable store (ephemeral, process-local) ---------------------


class _CheckerDecision:
    """One checker's recorded decision on a durable approval. Ephemeral, in memory."""

    __slots__ = (
        "checker_id",
        "decided_at",
        "decision",
        "reason_redacted",
        "audit_event_id",
        "decision_digest",
    )

    def __init__(self, **kwargs: Any) -> None:
        for key in self.__slots__:
            setattr(self, key, kwargs.get(key))


class _StoredDurableApproval:
    """A recorded durable approval and its checker state. Ephemeral, in memory."""

    __slots__ = (
        "approval_id",
        "action_id",
        "tenant_id",
        "action_type",
        "action_class",
        "state",
        "maker",
        "maker_at",
        "checkers",
        "quorum_required",
        "quorum_met",
        "decision",
        "reason",
        "request_digest",
        "idempotency_key_digest",
        "expires_at",
        "durable_retain_until",
        "validation_status",
        "source_status",
        "superseded_by",
        "previous_state",
        "correlation_id",
        "audit_event_id",
        "retention_class",
        "created_at",
        "updated_at",
        "create_key",
        "create_fingerprint",
    )

    def __init__(self, **kwargs: Any) -> None:
        for key in self.__slots__:
            setattr(self, key, kwargs.get(key))


_STORE: dict[str, _StoredDurableApproval] = {}  # approval_id -> record
# SHA-256 digest of the create idempotency_key -> approval_id. The RAW
# idempotency_key is never stored; only its one-way digest is.
_STORE_BY_CREATE_KEY: dict[str, str] = {}
_AUDIT_LOG: list[DurableApprovalAuditEvent] = []


def reset_store() -> None:
    """Clear the in-memory durable approval store and audit log. Used by tests."""
    _STORE.clear()
    _STORE_BY_CREATE_KEY.clear()
    _AUDIT_LOG.clear()


def audit_log() -> list[DurableApprovalAuditEvent]:
    """Return a copy of the emitted durable audit events (for tests / inspection)."""
    return list(_AUDIT_LOG)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(value: Optional[datetime]) -> Optional[datetime]:
    """Normalize a datetime to aware UTC; None stays None."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _digest(value: Optional[str]) -> str:
    """One-way SHA-256 hex digest of an idempotency key.

    The RAW idempotency_key is never stored in the store, in a record slot, or
    in an audit event. Dedup / duplicate / conflict checks compare these
    digests; the digest is echoed back as ``idempotency_key_digest`` (a one-way
    hash, never the raw key).
    """
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


# -- Quorum / action class ---------------------------------------------------


def _action_class_for(action_type: Optional[str]) -> Optional[str]:
    """Resolve the P18 action classification (read / write / write_request)."""
    if not action_type:
        return None
    item = _p18._item_for(action_type)
    if item is None:
        return None
    return item.classification


def _quorum_required_for(action_class: Optional[str]) -> int:
    """Quorum floor by action_class (P20-A 4.5). Maker is always excluded.

    write / write_request -> 2 distinct checkers; read -> 1. Unknown defaults to
    the strict write floor (2) -- it never weakens dual-control.
    """
    if action_class == "read":
        return 1
    return 2  # write, write_request, unknown-default


# -- Audit payload builder ---------------------------------------------------


def _emit(
    *,
    event_type: str,
    actor_id: Optional[str],
    actor_role: str,
    identity_context: str,
    tenant_id: Optional[str],
    action_id: Optional[str],
    approval_id: Optional[str],
    decision: Optional[str],
    previous_status: Optional[str],
    next_status: Optional[str],
    reason: str,
    request_digest: Optional[str],
    quorum_required: int,
    quorum_met: bool,
    checker_id: Optional[str],
    correlation_id: Optional[str],
    now: datetime,
) -> DurableApprovalAuditEvent:
    """Build, record, and return a durable audit event.

    Applies P18 reason redaction internally so a raw reason value can never
    reach the audit log, even if a caller forgets to pre-redact. The redaction
    is idempotent on an already-redacted value.
    """
    safe_reason = _p18._redact_reason(reason)
    event = DurableApprovalAuditEvent(
        event_id=str(uuid4()),
        event_type=event_type,  # type: ignore[arg-type]
        approval_id=approval_id,
        action_id=action_id,
        actor_id=actor_id,
        actor_role=actor_role,  # type: ignore[arg-type]
        identity_context=identity_context,  # type: ignore[arg-type]
        tenant_id=tenant_id,
        decision=decision,  # type: ignore[arg-type]
        previous_status=previous_status,  # type: ignore[arg-type]
        next_status=next_status,  # type: ignore[arg-type]
        reason_redacted=safe_reason,
        created_at=now,
        request_digest=request_digest,
        redaction_applied=True,
        quorum_required=quorum_required,
        quorum_met=quorum_met,
        checker_id=checker_id,
        correlation_id=correlation_id,
    )
    _AUDIT_LOG.append(event)
    return event


def _build_audit_event(
    *,
    event_type: str,
    actor_id: Optional[str],
    actor_role: str,
    identity_context: str,
    tenant_id: Optional[str],
    action_id: Optional[str],
    approval_id: Optional[str],
    decision: Optional[str],
    previous_status: Optional[str],
    next_status: Optional[str],
    reason: str,
    request_digest: Optional[str] = None,
    quorum_required: int = 0,
    quorum_met: bool = False,
    checker_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    timestamp: Optional[datetime] = None,
) -> DurableApprovalAuditEvent:
    """Public test seam: build a redacted durable audit event without persisting.

    Applies P18 reason redaction internally: a caller passing a raw reason such
    as "password=hunter2" receives an event whose reason_redacted is "[redacted]"
    -- the raw value never leaks. Mirrors _emit but does not append to the log.
    """
    safe_reason = _p18._redact_reason(reason)
    return DurableApprovalAuditEvent(
        event_id=str(uuid4()),
        event_type=event_type,  # type: ignore[arg-type]
        approval_id=approval_id,
        action_id=action_id,
        actor_id=actor_id,
        actor_role=actor_role,  # type: ignore[arg-type]
        identity_context=identity_context,  # type: ignore[arg-type]
        tenant_id=tenant_id,
        decision=decision,  # type: ignore[arg-type]
        previous_status=previous_status,  # type: ignore[arg-type]
        next_status=next_status,  # type: ignore[arg-type]
        reason_redacted=safe_reason,
        created_at=timestamp or _now(),
        request_digest=request_digest,
        redaction_applied=True,
        quorum_required=quorum_required,
        quorum_met=quorum_met,
        checker_id=checker_id,
        correlation_id=correlation_id,
    )


# -- P18 validation boundary -------------------------------------------------


async def _resolve_p18_context(
    action_id: Optional[str],
    action_type: Optional[str],
    tenant_id: Optional[str],
    db: AsyncSession,
) -> Optional[tuple[str, str, str]]:
    """Resolve (action_type, source_status, action_class) from P18.

    Returns None when the reference cannot be resolved at all (action_id given
    but no recorded P18 request, or no resolvable action_type). An unknown /
    unavailable source status is returned verbatim -- it is never upgraded.
    """
    if action_id:
        rec = _p18.get_stored_request(action_id)
        if rec is None:
            return None  # referenced P18 request does not exist
        cls = _action_class_for(rec.action_type)
        return (rec.action_type, rec.source_status, cls or "write")
    if action_type and _p18.known_action_type(action_type):
        status = await _p18._resolve_action_source_status(action_type, tenant_id, db)
        cls = _action_class_for(action_type) or "write"
        return (action_type, status, cls)
    return None


# -- Response builder --------------------------------------------------------


def _record_from(
    rec: Optional[_StoredDurableApproval],
    *,
    result: str,
    message: str,
    now: Optional[datetime] = None,
) -> DurableApprovalRecord:
    """Build the uniform response record. execution_allowed / executed are False."""
    if rec is None:
        return DurableApprovalRecord(
            reason="",
            source_status="unknown",
            storage="memory",
            result=result,  # type: ignore[arg-type]
            message=message,
            executed=False,
            execution_allowed=False,
            updated_at=now,
        )
    checkers = [
        CheckerDecisionSummary(
            checker_id=c.checker_id,
            decided_at=c.decided_at,
            decision=c.decision,  # type: ignore[arg-type]
            reason_redacted=c.reason_redacted,
            audit_event_id=c.audit_event_id,
        )
        for c in rec.checkers
    ]
    return DurableApprovalRecord(
        approval_id=rec.approval_id,
        action_id=rec.action_id,
        tenant_id=rec.tenant_id,
        action_type=rec.action_type,
        action_class=rec.action_class,  # type: ignore[arg-type]
        state=rec.state,  # type: ignore[arg-type]
        maker=rec.maker,
        maker_at=rec.maker_at,
        checkers=checkers,
        quorum_required=rec.quorum_required,
        quorum_met=rec.quorum_met,
        decision=rec.decision,  # type: ignore[arg-type]
        reason=rec.reason,
        request_digest=rec.request_digest,
        idempotency_key_digest=rec.idempotency_key_digest,
        expires_at=rec.expires_at,
        durable_retain_until=rec.durable_retain_until,
        execution_allowed=False,
        execution_gate="blocked",
        redaction_applied=True,
        storage="memory",
        retention_class=rec.retention_class,  # type: ignore[arg-type]
        validation_status=rec.validation_status,  # type: ignore[arg-type]
        superseded_by=rec.superseded_by,
        previous_state=rec.previous_state,  # type: ignore[arg-type]
        audit_event_id=rec.audit_event_id,
        correlation_id=rec.correlation_id,
        source_status=rec.source_status,  # type: ignore[arg-type]
        result=result,  # type: ignore[arg-type]
        message=message,
        executed=False,
        created_at=rec.created_at,
        updated_at=now or rec.updated_at,
    )


def _request_digest(
    action_id: Optional[str],
    action_type: Optional[str],
    tenant_id: Optional[str],
    maker: str,
) -> str:
    """SHA-256 of the canonical request envelope (P20-A 3.1)."""
    raw = "|".join([action_id or "", action_type or "", tenant_id or "", maker or ""])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _create_fingerprint(action_type: Optional[str], tenant_id: Optional[str], maker: str, reason_raw: str) -> str:
    raw = "|".join([action_type or "", tenant_id or "", maker or "", reason_raw or ""])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# -- Open a durable approval request -----------------------------------------


async def create_durable_approval(
    *,
    action_id: Optional[str],
    tenant_id: Optional[str],
    action_type: Optional[str],
    maker: Optional[str],
    reason: Optional[str],
    idempotency_key: Optional[str],
    expires_at: Optional[datetime],
    durable_retain_until: Optional[datetime],
    confirm: bool,
    correlation_id: Optional[str],
    metadata: Optional[dict],
    db: AsyncSession,
    actor: Optional[str],
    actor_role: str,
    identity_context: str,
) -> DurableApprovalRecord:
    """Validate and record a durable approval request. Never executes anything.

    Order of checks: reason -> idempotency_key -> maker -> confirm -> expires_at
    (future) -> P18 reference resolvable -> create idempotency store. An
    unresolvable P18 reference, a missing required field, a missing
    confirmation, or a past expires_at yields a denied record (not recorded).
    An unknown source status does NOT block creation -- it is stored verbatim
    (validation_status = source_unknown) and blocks the later approve decision.
    """
    now = _now()
    raw_reason = (reason or "").strip()
    raw_key = (idempotency_key or "").strip()
    raw_maker = (maker or "").strip()
    safe_reason = _p18._redact_reason(raw_reason)
    safe_maker = _p18._sanitize_text(raw_maker)
    safe_correlation_id = _p18._sanitize_text(correlation_id)
    # metadata is redacted for audit use; not echoed on the record (no leak).
    _p18.redact_metadata(metadata)

    def denied(message: str, result: str = "denied") -> DurableApprovalRecord:
        _emit(
            event_type="approval_denied",
            actor_id=actor,
            actor_role=actor_role,
            identity_context=identity_context,
            tenant_id=tenant_id,
            action_id=action_id,
            approval_id=None,
            decision=None,
            previous_status=None,
            next_status=None,
            reason=safe_reason,
            request_digest=None,
            quorum_required=0,
            quorum_met=False,
            checker_id=None,
            correlation_id=safe_correlation_id,
            now=now,
        )
        return _record_from(None, result=result, message=message, now=now)

    # 1) reason required
    if not raw_reason:
        return denied("Denied: a non-empty reason is required to open a durable approval.")

    # 2) idempotency_key required
    if not raw_key:
        return denied("Denied: an idempotency_key is required to open a durable approval.")

    # 3) maker required
    if not raw_maker:
        return denied("Denied: a maker is required to open a durable approval.")

    # 4) explicit confirmation required to open the request
    if not confirm:
        return denied("Denied: explicit confirmation (confirm=true) is required to open a durable approval.")

    # 5) expires_at required and in the future (an approval must expire)
    exp = _utc(expires_at)
    if exp is None:
        return denied("Denied: expires_at is required (a durable approval must expire).")
    if exp <= now:
        return denied("Denied: expires_at must be in the future.")

    # durable_retain_until defaults to expires_at (retention TTL)
    retain = _utc(durable_retain_until) or exp

    # 6) P18 reference must be resolvable (never fabricate an available source)
    ctx = await _resolve_p18_context(action_id, action_type, tenant_id, db)
    if ctx is None:
        return denied(
            "Denied: the P18 action reference could not be resolved "
            "(unknown action_id / action_type); durable approval not recorded.",
            result="not_found",
        )
    resolved_action_type, source_status, action_class = ctx
    safe_action_type = _p18._sanitize_text(resolved_action_type) or resolved_action_type
    quorum_required = _quorum_required_for(action_class)
    validation_status = "valid" if source_status == "available" else "source_unknown"

    # 7) create idempotency: duplicate / conflict (keyed by the key DIGEST,
    #    never the raw idempotency_key)
    fp = _create_fingerprint(resolved_action_type, tenant_id, raw_maker, raw_reason)
    create_digest = _digest(raw_key)
    existing_id = _STORE_BY_CREATE_KEY.get(create_digest)
    if existing_id is not None:
        existing = _STORE[existing_id]
        if existing.create_fingerprint == fp:
            _emit(
                event_type="approval_opened",
                actor_id=actor,
                actor_role=actor_role,
                identity_context=identity_context,
                tenant_id=tenant_id,
                action_id=existing.action_id,
                approval_id=existing.approval_id,
                decision=None,
                previous_status=None,
                next_status=existing.state,
                reason=existing.reason,
                request_digest=existing.request_digest,
                quorum_required=existing.quorum_required,
                quorum_met=existing.quorum_met,
                checker_id=None,
                correlation_id=existing.correlation_id,
                now=now,
            )
            return _record_from(
                existing,
                result="duplicate",
                message="Duplicate: idempotency_key already recorded with an identical durable approval request; the original record is returned and nothing was executed.",
                now=now,
            )
        return denied(
            "Conflict: idempotency_key already recorded with a different durable approval request; rejected and not recorded.",
            result="conflict",
        )

    # 8) record the durable approval at pending_review; execution_allowed stays False
    approval_id = str(uuid4())
    req_digest = _request_digest(action_id, resolved_action_type, tenant_id, raw_maker)
    audit = _emit(
        event_type="approval_opened",
        actor_id=actor,
        actor_role=actor_role,
        identity_context=identity_context,
        tenant_id=tenant_id,
        action_id=action_id,
        approval_id=approval_id,
        decision=None,
        previous_status=None,
        next_status="pending_review",
        reason=safe_reason,
        request_digest=req_digest,
        quorum_required=quorum_required,
        quorum_met=False,
        checker_id=None,
        correlation_id=safe_correlation_id,
        now=now,
    )
    rec = _StoredDurableApproval(
        approval_id=approval_id,
        action_id=action_id,
        tenant_id=tenant_id,
        action_type=safe_action_type,
        action_class=action_class,
        state="pending_review",
        maker=safe_maker,
        maker_at=now,
        checkers=[],
        quorum_required=quorum_required,
        quorum_met=False,
        decision=None,
        reason=safe_reason,
        request_digest=req_digest,
        idempotency_key_digest=create_digest,
        expires_at=exp,
        durable_retain_until=retain,
        validation_status=validation_status,
        source_status=source_status,
        superseded_by=None,
        previous_state=None,
        correlation_id=safe_correlation_id,
        audit_event_id=audit.event_id,
        retention_class="standard",
        created_at=now,
        updated_at=now,
        create_key=create_digest,
        create_fingerprint=fp,
    )
    _STORE[approval_id] = rec
    _STORE_BY_CREATE_KEY[create_digest] = approval_id
    return _record_from(
        rec,
        result="recorded",
        message="Recorded: the durable approval request was recorded at pending_review and audited. No action was executed and no tenant state was changed.",
        now=now,
    )


# -- Record a checker decision -----------------------------------------------


def submit_decision(
    approval_id: str,
    *,
    decision: Optional[str],
    approver_id: Optional[str],
    reason: Optional[str],
    idempotency_key: Optional[str],
    confirm: bool,
    correlation_id: Optional[str],
    metadata: Optional[dict],
    actor: Optional[str],
    actor_role: str,
    identity_context: str,
) -> DurableApprovalRecord:
    """Record one checker's approve / reject decision. Never executes anything.

    Maker-checker: approver_id must differ from maker (self-approval forbidden).
    Distinct checkers: each checker records at most one decision. reject is
    final (any single reject vetoes). approve accumulates until the quorum floor
    of distinct approve checkers is met, then resolves to
    approved_execution_blocked. An approve against an unknown / unavailable P18
    source is denied. Transitions to expired / cancelled / superseded /
    failed_validation are not implemented in P20-B and are explicitly rejected.
    """
    now = _now()
    rec = _STORE.get(approval_id)

    raw_reason = (reason or "").strip()
    raw_key = (idempotency_key or "").strip()
    raw_approver = (approver_id or "").strip()
    safe_reason = _p18._redact_reason(raw_reason)
    safe_approver = _p18._sanitize_text(raw_approver)
    safe_correlation_id = _p18._sanitize_text(correlation_id)
    _p18.redact_metadata(metadata)
    decision_digest = _digest(raw_key)

    def denied(message: str, result: str = "denied") -> DurableApprovalRecord:
        _emit(
            event_type="approval_denied",
            actor_id=actor,
            actor_role=actor_role,
            identity_context=identity_context,
            tenant_id=rec.tenant_id if rec else None,
            action_id=rec.action_id if rec else None,
            approval_id=approval_id,
            decision=None,
            previous_status=rec.state if rec else None,
            next_status=rec.state if rec else None,
            reason=safe_reason,
            request_digest=rec.request_digest if rec else None,
            quorum_required=rec.quorum_required if rec else 0,
            quorum_met=rec.quorum_met if rec else False,
            checker_id=safe_approver,
            correlation_id=safe_correlation_id,
            now=now,
        )
        return _record_from(rec, result=result, message=message, now=now)

    if rec is None:
        return denied("Denied: approval_id not found.", result="not_found")

    # 1) decision must be approve | reject
    if decision not in ("approve", "reject"):
        return denied("Denied: decision must be 'approve' or 'reject'.")

    # 2) approver_id / reason / idempotency_key / confirmation required
    if not raw_approver:
        return denied("Denied: an approver_id (checker) is required for a decision.")
    if not raw_reason:
        return denied("Denied: a non-empty reason is required for a decision.")
    if not raw_key:
        return denied("Denied: an idempotency_key is required for a decision.")
    if not confirm:
        return denied("Denied: explicit confirmation (confirm=true) is required for a decision.")

    # 3) unimplemented terminal transitions are explicitly rejected (P20-B
    #    implements only pending_review / approved_execution_blocked / rejected)
    if rec.state in ("expired", "cancelled", "superseded", "failed_validation"):
        return denied(
            "Denied: the '%s' state transition is not implemented in P20-B; the approval is terminal and cannot be decided." % rec.state,
        )

    # 4) maker-checker separation: the maker can never be a checker
    if safe_approver == rec.maker:
        return denied("Denied: maker-checker separation forbids the maker from approving / rejecting their own durable approval (self-approval denied).")

    # 5) already-rejected approval: reject is final
    if rec.state == "rejected":
        existing = next((c for c in rec.checkers if c.checker_id == safe_approver), None)
        if existing is not None and existing.decision == decision:
            _emit(
                event_type="approval_rejected",
                actor_id=actor,
                actor_role=actor_role,
                identity_context=identity_context,
                tenant_id=rec.tenant_id,
                action_id=rec.action_id,
                approval_id=approval_id,
                decision="reject",
                previous_status="rejected",
                next_status="rejected",
                reason=safe_reason,
                request_digest=rec.request_digest,
                quorum_required=rec.quorum_required,
                quorum_met=False,
                checker_id=safe_approver,
                correlation_id=safe_correlation_id,
                now=now,
            )
            return _record_from(rec, result="duplicate", message="Duplicate: this checker already recorded this decision; reject is final. Nothing was executed.", now=now)
        return denied("Conflict: the durable approval is already rejected; reject is final and no further decision is accepted.", result="conflict")

    # 6) quorum-met approval (approved_execution_blocked): no further state change
    if rec.state == "approved_execution_blocked":
        existing = next((c for c in rec.checkers if c.checker_id == safe_approver), None)
        if decision == "approve" and (existing is None or existing.decision == "approve"):
            return _record_from(rec, result="duplicate", message="Duplicate: the durable approval already reached quorum (approved_execution_blocked); the approve is idempotent. Nothing was executed.", now=now)
        return denied("Conflict: the durable approval already reached quorum (approved_execution_blocked); a reject after quorum is rejected.", result="conflict")

    # 7) state is pending_review -> apply the decision
    existing = next((c for c in rec.checkers if c.checker_id == safe_approver), None)
    if existing is not None:
        # distinct checker: one decision per checker
        if existing.decision == decision:
            return _record_from(rec, result="duplicate", message="Duplicate: this checker already recorded this decision; nothing changed and nothing was executed.", now=now)
        return denied("Conflict: this checker already recorded a different decision on this durable approval; a checker cannot flip.", result="conflict")

    if decision == "reject":
        # reject is final -> rejected (terminal)
        dec_audit = _emit(
            event_type="approval_decision_recorded",
            actor_id=actor,
            actor_role=actor_role,
            identity_context=identity_context,
            tenant_id=rec.tenant_id,
            action_id=rec.action_id,
            approval_id=approval_id,
            decision="reject",
            previous_status=rec.state,
            next_status="rejected",
            reason=safe_reason,
            request_digest=rec.request_digest,
            quorum_required=rec.quorum_required,
            quorum_met=False,
            checker_id=safe_approver,
            correlation_id=safe_correlation_id,
            now=now,
        )
        rec.checkers.append(
            _CheckerDecision(
                checker_id=safe_approver,
                decided_at=now,
                decision="reject",
                reason_redacted=safe_reason,
                audit_event_id=dec_audit.event_id,
                decision_digest=decision_digest,
            )
        )
        rec.previous_state = rec.state
        rec.state = "rejected"
        rec.decision = "reject"
        rec.updated_at = now
        audit = _emit(
            event_type="approval_rejected",
            actor_id=actor,
            actor_role=actor_role,
            identity_context=identity_context,
            tenant_id=rec.tenant_id,
            action_id=rec.action_id,
            approval_id=approval_id,
            decision="reject",
            previous_status=rec.previous_state,
            next_status="rejected",
            reason=safe_reason,
            request_digest=rec.request_digest,
            quorum_required=rec.quorum_required,
            quorum_met=False,
            checker_id=safe_approver,
            correlation_id=safe_correlation_id,
            now=now,
        )
        rec.audit_event_id = audit.event_id
        return _record_from(rec, result="rejected", message="Rejected: a checker rejected the durable approval; reject is final for this approval_id. Nothing was executed.", now=now)

    # decision == "approve"
    # approve requires a verified-available P18 source (unknown / unavailable cannot approve)
    if rec.validation_status != "valid":
        return denied(
            "Denied: the underlying P18 source status is '%s'; an approve requires an available source. Nothing was executed." % rec.source_status,
        )
    dec_audit = _emit(
        event_type="approval_decision_recorded",
        actor_id=actor,
        actor_role=actor_role,
        identity_context=identity_context,
        tenant_id=rec.tenant_id,
        action_id=rec.action_id,
        approval_id=approval_id,
        decision="approve",
        previous_status=rec.state,
        next_status="pending_review",  # provisional; updated below if quorum met
        reason=safe_reason,
        request_digest=rec.request_digest,
        quorum_required=rec.quorum_required,
        quorum_met=False,
        checker_id=safe_approver,
        correlation_id=safe_correlation_id,
        now=now,
    )
    rec.checkers.append(
        _CheckerDecision(
            checker_id=safe_approver,
            decided_at=now,
            decision="approve",
            reason_redacted=safe_reason,
            audit_event_id=dec_audit.event_id,
            decision_digest=decision_digest,
        )
    )
    approve_count = sum(1 for c in rec.checkers if c.decision == "approve")
    if approve_count >= rec.quorum_required:
        rec.previous_state = rec.state
        rec.state = "approved_execution_blocked"
        rec.decision = "approve"
        rec.quorum_met = True
        rec.updated_at = now
        audit = _emit(
            event_type="approval_quorum_met",
            actor_id=actor,
            actor_role=actor_role,
            identity_context=identity_context,
            tenant_id=rec.tenant_id,
            action_id=rec.action_id,
            approval_id=approval_id,
            decision="approve",
            previous_status=rec.previous_state,
            next_status="approved_execution_blocked",
            reason=safe_reason,
            request_digest=rec.request_digest,
            quorum_required=rec.quorum_required,
            quorum_met=True,
            checker_id=safe_approver,
            correlation_id=safe_correlation_id,
            now=now,
        )
        rec.audit_event_id = audit.event_id
        return _record_from(rec, result="approved", message="Approved: durable approval quorum was met and the approval resolved to approved_execution_blocked. The action was NOT executed; execution_allowed is false and no tenant state changed.", now=now)

    # quorum not yet met -> stays pending_review
    rec.updated_at = now
    return _record_from(rec, result="quorum_pending", message="Quorum pending: the checker approve was recorded; the durable approval stays pending_review until the quorum of distinct checkers is met. Nothing was executed.", now=now)


# -- Read / list -------------------------------------------------------------


def read_durable_approval(approval_id: str) -> Optional[DurableApprovalRecord]:
    """Return the record for an approval_id, or None when not found."""
    rec = _STORE.get(approval_id)
    if rec is None:
        return None
    return _record_from(rec, result="recorded", message="Read: durable approval record (ephemeral in-memory store). Nothing was executed.", now=rec.updated_at)


def list_durable_approvals(
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None,
    action_type: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> DurableApprovalQueue:
    """Return the current process-local queue of durable approval records.

    Optional filters: status (lifecycle state), action_type, tenant_id.
    """
    safe_limit = max(1, min(limit, 100))
    safe_offset = max(0, offset)
    records = sorted(
        _STORE.values(),
        key=lambda r: r.created_at or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    if status:
        records = [r for r in records if r.state == status]
    if action_type:
        records = [r for r in records if r.action_type == action_type]
    if tenant_id:
        records = [r for r in records if r.tenant_id == tenant_id]
    items = [
        _record_from(rec, result="recorded", message="Queued: durable approval record (ephemeral in-memory queue). Nothing was executed.", now=rec.updated_at)
        for rec in records[safe_offset : safe_offset + safe_limit]
    ]
    return DurableApprovalQueue(
        items=items,
        total=len(records),
        limit=safe_limit,
        offset=safe_offset,
        storage="memory",
        executed=False,
    )
