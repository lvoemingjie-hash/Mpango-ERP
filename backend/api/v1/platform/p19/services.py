"""P19 Controlled Action Approval Workflow -- service layer (P19-B skeleton).

SAFE skeleton: records approval requests, lists the approval queue, reads a
single approval, and records approve / reject DECISIONS in process-local
memory. It NEVER executes any controlled action and NEVER mutates the P17
registry, tenant lifecycle, operational flags, provisioning, backup, or any
tenant business data. Approval is NOT execution: an approved approval resolves
to ``execution_blocked`` and ``execution_allowed`` is always false. Recorded
approvals are ephemeral (in-process memory) -- there is intentionally no
database table and no migration.

P18 validation boundary: an approval wraps a P18 controlled-action request.
``_resolve_p18_context`` resolves the action_type and the P18 source status
either from a recorded P18 action_id (read from the P18 in-memory store, shared
within the process) or, when only an action_type is supplied, via the P18
registry source-status resolver. It is conservative on every failure path: a
missing action_id, an unknown action_type, or any resolver error yields no
context, and an unknown source status is stored verbatim (never fabricated as
available). An approve against an unknown / unavailable source is denied.

Redaction reuses P18 verbatim (redact_metadata / _redact_reason / _sanitize_text
/ _reason_is_sensitive): a reason or value carrying any secret keyword, scheme,
or host:port pattern is replaced wholesale with "[redacted]". The RAW reason is
used only for the one-way idempotency fingerprint (a hash that is never echoed
or audited).
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.platform.p18 import services as _p18

from .schemas import (
    ControlledActionApprovalAuditEvent,
    ControlledActionApprovalQueue,
    ControlledActionApprovalRecord,
)


# -- In-memory approval store (ephemeral, process-local) ---------------------


class _StoredApproval:
    """A recorded approval and its decision state. Ephemeral, in memory."""

    __slots__ = (
        "approval_id",
        "action_id",
        "tenant_id",
        "action_type",
        "state",
        "requested_by",
        "requested_at",
        "reviewed_by",
        "reviewed_at",
        "decision",
        "reason",
        "expires_at",
        "idempotency_key",
        "source_status",
        "previous_state",
        "correlation_id",
        "audit_event_id",
        "created_at",
        "updated_at",
        "create_key",
        "create_fingerprint",
        "decision_key",
    )

    def __init__(self, **kwargs: Any) -> None:
        for key in self.__slots__:
            setattr(self, key, kwargs.get(key))


_STORE: dict[str, _StoredApproval] = {}  # approval_id -> record
_STORE_BY_CREATE_KEY: dict[str, str] = {}  # raw create idempotency_key -> approval_id
_AUDIT_LOG: list[ControlledActionApprovalAuditEvent] = []


def reset_store() -> None:
    """Clear the in-memory approval store and audit log. Used by tests."""
    _STORE.clear()
    _STORE_BY_CREATE_KEY.clear()
    _AUDIT_LOG.clear()


def audit_log() -> list[ControlledActionApprovalAuditEvent]:
    """Return a copy of the emitted approval audit events (for tests / inspection)."""
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


# -- Audit payload builder ---------------------------------------------------


def _emit(
    *,
    event_type: str,
    actor: Optional[str],
    identity_context: str,
    tenant_id: Optional[str],
    action_id: Optional[str],
    approval_id: Optional[str],
    decision: Optional[str],
    reason: str,
    now: datetime,
) -> ControlledActionApprovalAuditEvent:
    """Build, record, and return an approval audit event. Reason must be redacted."""
    event = ControlledActionApprovalAuditEvent(
        audit_event_id=str(uuid4()),
        event_type=event_type,  # type: ignore[arg-type]
        actor=actor,
        identity_context=identity_context,  # type: ignore[arg-type]
        tenant_id=tenant_id,
        action_id=action_id,
        approval_id=approval_id,
        decision=decision,  # type: ignore[arg-type]
        redaction_applied=True,
        reason=reason,
        timestamp=now,
    )
    _AUDIT_LOG.append(event)
    return event


def _build_approval_audit_event(
    *,
    event_type: str,
    actor: Optional[str],
    identity_context: str,
    tenant_id: Optional[str],
    action_id: Optional[str],
    approval_id: Optional[str],
    decision: Optional[str],
    reason: str,
    timestamp: Optional[datetime] = None,
) -> ControlledActionApprovalAuditEvent:
    """Public test seam: build a redacted approval audit event without persisting.

    Mirrors _emit but does not append to the in-memory log. Provided so tests can
    assert the audit payload shape and redaction directly.
    """
    return ControlledActionApprovalAuditEvent(
        audit_event_id=str(uuid4()),
        event_type=event_type,  # type: ignore[arg-type]
        actor=actor,
        identity_context=identity_context,  # type: ignore[arg-type]
        tenant_id=tenant_id,
        action_id=action_id,
        approval_id=approval_id,
        decision=decision,  # type: ignore[arg-type]
        redaction_applied=True,
        reason=reason,
        timestamp=timestamp or _now(),
    )


# -- P18 validation boundary -------------------------------------------------


async def _resolve_p18_context(
    action_id: Optional[str],
    action_type: Optional[str],
    tenant_id: Optional[str],
    db: AsyncSession,
) -> Optional[tuple[str, str]]:
    """Resolve (action_type, source_status) from P18. Never fabricates available.

    Returns None when the reference cannot be resolved at all (action_id given
    but no recorded P18 request, or no resolvable action_type). An unknown /
    unavailable source status is returned verbatim -- it is never upgraded.
    """
    if action_id:
        rec = _p18.get_stored_request(action_id)
        if rec is None:
            return None  # referenced P18 request does not exist
        return (rec.action_type, rec.source_status)
    if action_type and _p18.known_action_type(action_type):
        status = await _p18._resolve_action_source_status(action_type, tenant_id, db)
        return (action_type, status)
    return None


# -- Response builder --------------------------------------------------------


def _record_from(
    rec: Optional[_StoredApproval],
    *,
    result: str,
    message: str,
    now: Optional[datetime] = None,
) -> ControlledActionApprovalRecord:
    """Build the uniform response record. execution_allowed / executed are False."""
    if rec is None:
        return ControlledActionApprovalRecord(
            reason="",
            source_status="unknown",
            storage="memory",
            result=result,  # type: ignore[arg-type]
            message=message,
            executed=False,
            execution_allowed=False,
            updated_at=now,
        )
    return ControlledActionApprovalRecord(
        action_id=rec.action_id,
        approval_id=rec.approval_id,
        tenant_id=rec.tenant_id,
        action_type=rec.action_type,
        state=rec.state,  # type: ignore[arg-type]
        requested_by=rec.requested_by,
        requested_at=rec.requested_at,
        reviewed_by=rec.reviewed_by,
        reviewed_at=rec.reviewed_at,
        decision=rec.decision,  # type: ignore[arg-type]
        reason=rec.reason,
        expires_at=rec.expires_at,
        execution_allowed=False,
        redaction_applied=True,
        idempotency_key=rec.idempotency_key,
        source_status=rec.source_status,  # type: ignore[arg-type]
        previous_state=rec.previous_state,  # type: ignore[arg-type]
        storage="memory",
        audit_event_id=rec.audit_event_id,
        correlation_id=rec.correlation_id,
        result=result,  # type: ignore[arg-type]
        message=message,
        executed=False,
        created_at=rec.created_at,
        updated_at=now or rec.updated_at,
    )


def _create_fingerprint(action_type: Optional[str], tenant_id: Optional[str], reason_raw: str) -> str:
    raw = "|".join([action_type or "", tenant_id or "", reason_raw or ""])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# -- Create an approval request ---------------------------------------------


async def create_approval(
    *,
    action_id: Optional[str],
    tenant_id: Optional[str],
    action_type: Optional[str],
    requested_by: Optional[str],
    reason: Optional[str],
    idempotency_key: Optional[str],
    expires_at: Optional[datetime],
    confirm: bool,
    correlation_id: Optional[str],
    metadata: Optional[dict],
    db: AsyncSession,
    actor: Optional[str],
    identity_context: str,
) -> ControlledActionApprovalRecord:
    """Validate and record an approval request. Never executes anything.

    Order of checks: reason -> idempotency_key -> requested_by -> confirm ->
    expires_at (future) -> P18 reference resolvable -> create idempotency store.
    An unresolvable P18 reference, a missing required field, a missing
    confirmation, or a past expires_at yields a denied record (not recorded).
    An unknown source status does NOT block creation -- it is stored verbatim
    and blocks the later approve decision.
    """
    now = _now()
    raw_reason = (reason or "").strip()
    raw_key = (idempotency_key or "").strip()
    raw_requested_by = (requested_by or "").strip()
    safe_reason = _p18._redact_reason(raw_reason)
    safe_key = _p18._sanitize_text(raw_key) or ""
    safe_requested_by = _p18._sanitize_text(raw_requested_by)
    safe_correlation_id = _p18._sanitize_text(correlation_id)
    redacted_md = _p18.redact_metadata(metadata)

    def denied(message: str, result: str = "denied") -> ControlledActionApprovalRecord:
        _emit(
            event_type="approval_denied",
            actor=actor,
            identity_context=identity_context,
            tenant_id=tenant_id,
            action_id=action_id,
            approval_id=None,
            decision=None,
            reason=safe_reason,
            now=now,
        )
        return _record_from(None, result=result, message=message, now=now)

    # 1) reason required
    if not raw_reason:
        return denied("Denied: a non-empty reason is required to open an approval.")

    # 2) idempotency_key required
    if not raw_key:
        return denied("Denied: an idempotency_key is required to open an approval.")

    # 3) requested_by required
    if not raw_requested_by:
        return denied("Denied: requested_by is required to open an approval.")

    # 4) explicit confirmation required to open the request
    if not confirm:
        return denied("Denied: explicit confirmation (confirm=true) is required to open an approval.")

    # 5) expires_at required and in the future (an approval must expire)
    exp = _utc(expires_at)
    if exp is None:
        return denied("Denied: expires_at is required (an approval must expire).")
    if exp <= now:
        return denied("Denied: expires_at must be in the future.")

    # 6) P18 reference must be resolvable (never fabricate an available source)
    ctx = await _resolve_p18_context(action_id, action_type, tenant_id, db)
    if ctx is None:
        return denied(
            "Denied: the P18 action reference could not be resolved "
            "(unknown action_id / action_type); approval not recorded.",
            result="not_found",
        )
    resolved_action_type, source_status = ctx
    safe_action_type = _p18._sanitize_text(resolved_action_type) or resolved_action_type

    # 7) create idempotency: duplicate / conflict
    fp = _create_fingerprint(resolved_action_type, tenant_id, raw_reason)
    existing_id = _STORE_BY_CREATE_KEY.get(raw_key)
    if existing_id is not None:
        existing = _STORE[existing_id]
        if existing.create_fingerprint == fp:
            _emit(
                event_type="approval_requested",
                actor=actor,
                identity_context=identity_context,
                tenant_id=tenant_id,
                action_id=existing.action_id,
                approval_id=existing.approval_id,
                decision=None,
                reason=existing.reason,
                now=now,
            )
            return _record_from(existing, result="duplicate", message="Duplicate: idempotency_key already recorded with an identical approval request; the original record is returned and nothing was executed.", now=now)
        return denied(
            "Conflict: idempotency_key already recorded with a different approval request; rejected and not recorded.",
            result="conflict",
        )

    # 8) record the approval at pending_review; execution_allowed stays False
    approval_id = str(uuid4())
    audit = _emit(
        event_type="approval_requested",
        actor=actor,
        identity_context=identity_context,
        tenant_id=tenant_id,
        action_id=action_id,
        approval_id=approval_id,
        decision=None,
        reason=safe_reason,
        now=now,
    )
    rec = _StoredApproval(
        approval_id=approval_id,
        action_id=action_id,
        tenant_id=tenant_id,
        action_type=safe_action_type,
        state="pending_review",
        requested_by=safe_requested_by,
        requested_at=now,
        reviewed_by=None,
        reviewed_at=None,
        decision=None,
        reason=safe_reason,
        expires_at=exp,
        idempotency_key=safe_key,
        source_status=source_status,
        previous_state=None,
        correlation_id=safe_correlation_id,
        audit_event_id=audit.audit_event_id,
        created_at=now,
        updated_at=now,
        create_key=raw_key,
        create_fingerprint=fp,
        decision_key=None,
    )
    _STORE[approval_id] = rec
    _STORE_BY_CREATE_KEY[raw_key] = approval_id
    return _record_from(
        rec,
        result="recorded",
        message="Recorded: the approval request was recorded at pending_review and audited. No action was executed and no tenant state was changed.",
        now=now,
    )


# -- Submit an approve / reject decision ------------------------------------


def submit_decision(
    approval_id: str,
    *,
    decision: Optional[str],
    reviewed_by: Optional[str],
    reason: Optional[str],
    idempotency_key: Optional[str],
    confirm: bool,
    correlation_id: Optional[str],
    metadata: Optional[dict],
    actor: Optional[str],
    identity_context: str,
) -> ControlledActionApprovalRecord:
    """Record an approve / reject decision. Never executes anything.

    reject is final. An expired / cancelled approval cannot be decided. A
    duplicate decision (same approval_id, same idempotency_key, same decision)
    is idempotent; a conflicting decision (different key or different decision
    on an already-decided approval) fails. An approve against an unknown /
    unavailable source is denied. approved resolves to execution_blocked.
    """
    now = _now()
    rec = _STORE.get(approval_id)

    raw_reason = (reason or "").strip()
    raw_key = (idempotency_key or "").strip()
    raw_reviewed_by = (reviewed_by or "").strip()
    safe_reason = _p18._redact_reason(raw_reason)
    safe_key = _p18._sanitize_text(raw_key) or ""

    def denied(message: str, result: str = "denied") -> ControlledActionApprovalRecord:
        _emit(
            event_type="approval_denied",
            actor=actor,
            identity_context=identity_context,
            tenant_id=rec.tenant_id if rec else None,
            action_id=rec.action_id if rec else None,
            approval_id=approval_id,
            decision=None,
            reason=safe_reason,
            now=now,
        )
        return _record_from(rec, result=result, message=message, now=now)

    if rec is None:
        return denied("Denied: approval_id not found.", result="not_found")

    # 1) decision must be approve | reject
    if decision not in ("approve", "reject"):
        return denied("Denied: decision must be 'approve' or 'reject'.")

    # 2) reason / idempotency_key / confirmation required
    if not raw_reason:
        return denied("Denied: a non-empty reason is required for a decision.")
    if not raw_key:
        return denied("Denied: an idempotency_key is required for a decision.")
    if not raw_reviewed_by:
        return denied("Denied: reviewed_by is required for a decision.")
    if not confirm:
        return denied("Denied: explicit confirmation (confirm=true) is required for a decision.")

    # 3) terminal, undecided-by-operator states cannot be decided
    if rec.state == "expired":
        _emit(
            event_type="approval_expired",
            actor=actor,
            identity_context=identity_context,
            tenant_id=rec.tenant_id,
            action_id=rec.action_id,
            approval_id=approval_id,
            decision=None,
            reason=safe_reason,
            now=now,
        )
        return _record_from(rec, result="expired", message="Expired: the approval has expired and can no longer be decided; nothing was executed.", now=now)
    if rec.state == "cancelled":
        return denied("Denied: a cancelled approval cannot be decided.")

    # 4) already-decided approvals: idempotent duplicate vs final conflict
    if rec.state in ("execution_blocked", "rejected"):
        if rec.decision_key == raw_key and rec.decision == decision:
            event_type = "approval_approved" if decision == "approve" else "approval_rejected"
            _emit(
                event_type=event_type,
                actor=actor,
                identity_context=identity_context,
                tenant_id=rec.tenant_id,
                action_id=rec.action_id,
                approval_id=approval_id,
                decision=rec.decision,
                reason=rec.reason,
                now=now,
            )
            return _record_from(rec, result="duplicate", message="Duplicate: this decision was already recorded with the same idempotency_key; the original record is returned and nothing was re-executed.", now=now)
        return denied(
            "Conflict: the approval is already decided (reject is final / approve resolves to execution_blocked); a different decision is rejected.",
            result="conflict",
        )

    # 5) state is pending_review -> apply the decision
    if decision == "approve":
        # approve requires a verified-available P18 source (unknown / unavailable cannot approve)
        if rec.source_status != "available":
            return denied(
                "Denied: the underlying P18 source status is '%s'; an approve requires an available source. Nothing was executed." % rec.source_status,
            )
        rec.previous_state = rec.state
        rec.state = "execution_blocked"  # approved resolves to execution_blocked
        rec.decision = "approve"
        rec.reviewed_by = _p18._sanitize_text(raw_reviewed_by)
        rec.reviewed_at = now
        rec.decision_key = raw_key
        rec.updated_at = now
        audit = _emit(
            event_type="approval_approved",
            actor=actor,
            identity_context=identity_context,
            tenant_id=rec.tenant_id,
            action_id=rec.action_id,
            approval_id=approval_id,
            decision="approve",
            reason=safe_reason,
            now=now,
        )
        rec.audit_event_id = audit.audit_event_id
        return _record_from(rec, result="approved", message="Approved: the approval was approved and resolved to execution_blocked. The action was NOT executed; execution_allowed is false and no tenant state changed.", now=now)

    # decision == "reject"
    rec.previous_state = rec.state
    rec.state = "rejected"  # reject is final
    rec.decision = "reject"
    rec.reviewed_by = _p18._sanitize_text(raw_reviewed_by)
    rec.reviewed_at = now
    rec.decision_key = raw_key
    rec.updated_at = now
    audit = _emit(
        event_type="approval_rejected",
        actor=actor,
        identity_context=identity_context,
        tenant_id=rec.tenant_id,
        action_id=rec.action_id,
        approval_id=approval_id,
        decision="reject",
        reason=safe_reason,
        now=now,
    )
    rec.audit_event_id = audit.audit_event_id
    return _record_from(rec, result="rejected", message="Rejected: the approval was rejected; reject is final for this approval_id. Nothing was executed.", now=now)


# -- Cancel (requester only, pre-decision) ----------------------------------
#
# Provided so a pending approval can be cancelled (terminal). Kept minimal and
# unused by the routes in P19-B beyond the lifecycle helper; included to make
# the state machine complete and testable.


def cancel_approval(
    approval_id: str,
    *,
    actor: Optional[str],
    identity_context: str,
    reason: str,
) -> ControlledActionApprovalRecord:
    now = _now()
    rec = _STORE.get(approval_id)
    safe_reason = _p18._redact_reason((reason or "").strip())
    if rec is None:
        return _record_from(None, result="not_found", message="Denied: approval_id not found.", now=now)
    if rec.state != "pending_review":
        _emit(event_type="approval_denied", actor=actor, identity_context=identity_context, tenant_id=rec.tenant_id, action_id=rec.action_id, approval_id=approval_id, decision=None, reason=safe_reason, now=now)
        return _record_from(rec, result="denied", message="Denied: only a pending approval can be cancelled.", now=now)
    rec.previous_state = rec.state
    rec.state = "cancelled"
    rec.updated_at = now
    audit = _emit(event_type="approval_cancelled", actor=actor, identity_context=identity_context, tenant_id=rec.tenant_id, action_id=rec.action_id, approval_id=approval_id, decision=None, reason=safe_reason, now=now)
    rec.audit_event_id = audit.audit_event_id
    return _record_from(rec, result="cancelled", message="Cancelled: the approval was cancelled before any decision. Nothing was executed.", now=now)


# -- Expire sweep (best-effort; tests can drive it) --------------------------


def sweep_expired(now: Optional[datetime] = None) -> int:
    """Mark pending approvals whose expires_at has passed as expired. Returns count."""
    now = now or _now()
    count = 0
    for rec in _STORE.values():
        if rec.state == "pending_review" and rec.expires_at is not None and rec.expires_at <= now:
            rec.previous_state = rec.state
            rec.state = "expired"
            rec.updated_at = now
            audit = _emit(event_type="approval_expired", actor=None, identity_context="system", tenant_id=rec.tenant_id, action_id=rec.action_id, approval_id=rec.approval_id, decision=None, reason=rec.reason, now=now)
            rec.audit_event_id = audit.audit_event_id
            count += 1
    return count


# -- Read / list -------------------------------------------------------------


def read_approval(approval_id: str) -> Optional[ControlledActionApprovalRecord]:
    """Return the record for an approval_id, or None when not found."""
    rec = _STORE.get(approval_id)
    if rec is None:
        return None
    return _record_from(rec, result="recorded", message="Read: approval record (ephemeral in-memory store). Nothing was executed.", now=rec.updated_at)


def list_approvals(limit: int = 50, offset: int = 0) -> ControlledActionApprovalQueue:
    """Return the current process-local operator queue of approval records."""
    safe_limit = max(1, min(limit, 100))
    safe_offset = max(0, offset)
    records = sorted(
        _STORE.values(),
        key=lambda r: r.created_at or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    items = [
        _record_from(rec, result="recorded", message="Queued: approval record (ephemeral in-memory queue). Nothing was executed.", now=rec.updated_at)
        for rec in records[safe_offset : safe_offset + safe_limit]
    ]
    return ControlledActionApprovalQueue(
        items=items,
        total=len(records),
        limit=safe_limit,
        offset=safe_offset,
        storage="memory",
        executed=False,
    )
