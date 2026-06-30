"""P20 Durable Approval Governance -- service layer.

This service opens durable approval requests, lists and reads them, and records
per-checker approve / reject DECISIONS under a maker-checker, quorum-based
dual-control policy. It NEVER executes any controlled action and NEVER mutates
the P17 registry, tenant lifecycle, operational flags, provisioning, backup, or
any tenant business data. Approval is NOT execution and durability is NOT
execution: a quorum-met approval resolves to ``approved_execution_blocked`` and
``execution_allowed`` is always false.

P21-D-D runtime storage cutover gate: the DEFAULT backend is the durable store
(the P21-D-C concrete adapter, restart-safe). An explicit memory backend is
retained for test/dev only (``storage == "memory"``); production never silently
falls back to it. When the durable store is not ready the gate fails CLOSED
(``DurableStoreNotReady`` -> 503), never fabricating a record as success. The
dual-control / P18 / redaction / state-machine policy below is mirrored by both
backends (the in-memory logic is retained verbatim as the ``_memory_*`` path).

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
import os
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.platform.p18 import services as _p18
# P21-D-D runtime storage cutover: the durable backend is the P21-D-C concrete
# adapter. This is a one-way dependency (p20 services -> p21 adapter); the
# adapter mirrors the P20-B service logic and preserves the P20 response shapes.
from api.v1.platform.p21.adapter import DurableApprovalStoreAdapter, StoreResult

from .schemas import (
    CheckerDecisionSummary,
    DurableApprovalAuditEvent,
    DurableApprovalQueue,
    DurableApprovalRecord,
)


# -- P21-D-D runtime storage cutover gate ------------------------------------
#
# P21-D-D wires the P20 durable approval runtime to the P21-D-C durable store
# adapter behind an EXPLICIT, auditable readiness gate. The default runtime
# storage mode is DURABLE (production): every create / list / read / decision
# persists through the durable adapter against the P21-C1 public tables. The
# in-memory store below is RETAINED only as an explicit test / dev backend
# (storage == "memory"); production never silently falls back to it. When the
# durable store is not ready (DB unreachable, P21-C1 schema / tables missing, or
# adapter initialization / operation failure), the gate fails CLOSED: it raises
# DurableStoreNotReady and the route returns a clear 503 (storage_not_ready /
# unavailable / degraded). It never fabricates an in-memory record as success.
#
# Approval is not execution and durability is not execution: the durable path
# preserves execution_allowed == False, executed == False, execution_gate ==
# "blocked" on every record (re-asserted by the mapper below, fail-closed).

#: Environment flag selecting the explicit memory test / dev backend. The
#: default (unset / any other value) is the production DURABLE mode.
ENV_P20_STORAGE_MODE: str = "MPANGO_P20_DURABLE_APPROVAL_STORAGE"

STORAGE_MODE_DURABLE: str = "durable"
STORAGE_MODE_MEMORY: str = "memory"

#: Closed vocabulary of DurableStoreNotReady failure codes (the directive's
#: storage_not_ready / unavailable / degraded response shapes).
STORAGE_NOT_READY_CODES: frozenset[str] = frozenset(
    ("storage_not_ready", "unavailable", "degraded")
)

#: Test / dev override seam (takes precedence over the env flag). None resolves
#: from the environment (durable default).
_STORAGE_MODE_OVERRIDE: Optional[str] = None


def set_storage_mode(mode: Optional[str]) -> None:
    """TEST / DEV SEAM: force the runtime storage mode.

    Accepts STORAGE_MODE_MEMORY, STORAGE_MODE_DURABLE, or None (clear the
    override and fall back to the env flag / durable default). The platform test
    harness uses this to select the in-memory backend deterministically.
    """
    global _STORAGE_MODE_OVERRIDE
    if mode is not None and mode not in (STORAGE_MODE_DURABLE, STORAGE_MODE_MEMORY):
        raise ValueError(f"unknown storage mode: {mode!r}")
    _STORAGE_MODE_OVERRIDE = mode


def get_storage_mode() -> str:
    """Resolve the active runtime storage mode (override > env flag > durable)."""
    if _STORAGE_MODE_OVERRIDE is not None:
        return _STORAGE_MODE_OVERRIDE
    flag = (os.environ.get(ENV_P20_STORAGE_MODE) or "").strip().lower()
    if flag == STORAGE_MODE_MEMORY:
        return STORAGE_MODE_MEMORY
    return STORAGE_MODE_DURABLE


class DurableStoreNotReady(Exception):
    """Raised when the durable store gate fails CLOSED.

    Carries a closed-vocabulary ``code`` (storage_not_ready | unavailable |
    degraded) and a redaction-safe ``reason``. The P20 routes translate this into
    a 503 response. The service NEVER silently falls back to the in-memory store
    or fabricates a durable record as success when the store is not ready.
    """

    def __init__(self, code: str, reason: str = "") -> None:
        if code not in STORAGE_NOT_READY_CODES:
            raise ValueError(f"unknown DurableStoreNotReady code: {code!r}")
        self.code = code
        self.reason = reason
        super().__init__(f"{code}: {reason}" if reason else code)


#: The five P21-C1 public durable approval tables. The readiness gate requires
#: every one to exist in the public schema (migration 020 applied).
_DURABLE_REQUIRED_TABLES: tuple[str, ...] = (
    "durable_approval_requests",
    "durable_approval_decisions",
    "durable_approval_audit_events",
    "durable_approval_idempotency_keys",
    "durable_approval_retention_jobs",
)


async def _check_durable_readiness(db: AsyncSession) -> tuple[bool, str]:
    """Runtime storage readiness gate for the durable backend.

    Returns ``(True, "ready")`` only when the database is reachable AND every
    P21-C1 durable table exists in the public schema (migration 020 applied) AND
    the adapter constructs. Any failure (DB unreachable, schema / tables missing,
    adapter / tenant-filter init error) yields ``(False, <code>)`` where ``<code>``
    is a member of STORAGE_NOT_READY_CODES. Never raises.
    """
    # Adapter construction marks the session system-scope for the tenant
    # guardrail bypass; a construction failure is a not-ready signal.
    try:
        DurableApprovalStoreAdapter(db)
    except Exception:
        return False, "storage_not_ready"
    try:
        named = {f"t{i}": name for i, name in enumerate(_DURABLE_REQUIRED_TABLES)}
        clauses = ", ".join(f":{key}" for key in named)
        stmt = text(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema = 'public' "
            f"AND table_name IN ({clauses})"
        )
        present = int((await db.execute(stmt, named)).scalar_one())
    except Exception:
        # DB unreachable / connection refused / query error -> unavailable.
        return False, "unavailable"
    if present != len(_DURABLE_REQUIRED_TABLES):
        # Reachable but the P21-C1 schema is not fully applied -> not ready.
        return False, "storage_not_ready"
    return True, "ready"


def _from_durable_record(rec: DurableApprovalRecord) -> DurableApprovalRecord:
    """EXPLICIT, validating mapper from a durable adapter record to the P20
    response shape.

    The durable adapter already returns a ``DurableApprovalRecord`` (design lock
    4.5: identical P20 shape with ``storage == "durable"``). This mapper does NOT
    loosely merge dicts or pass a foreign shape through: it re-asserts the
    no-execution / redaction / storage invariants and fails CLOSED (raises
    DurableStoreNotReady) if a durable record ever violated them, so a dangerous
    record can never reach the API. It then returns the record unchanged.
    """
    if rec.execution_allowed is not False:
        raise DurableStoreNotReady("degraded", "durable record violated execution_allowed invariant")
    if rec.executed is not False:
        raise DurableStoreNotReady("degraded", "durable record violated executed invariant")
    if rec.execution_gate != "blocked":
        raise DurableStoreNotReady("degraded", "durable record violated execution_gate invariant")
    if rec.redaction_applied is not True:
        raise DurableStoreNotReady("degraded", "durable record violated redaction invariant")
    if rec.storage != STORAGE_MODE_DURABLE:
        raise DurableStoreNotReady("degraded", "durable record storage invariant")
    return rec


def _durable_denial_record(
    *, result: str, message: str, now: Optional[datetime] = None
) -> DurableApprovalRecord:
    """Build a ``storage="durable"`` shaped denial / not-found / conflict record.

    Used when the durable adapter returns a StoreResult error that maps to a
    contract-shaped P20 denial (the durable store is healthy; the request was
    denied / not found / a conflict). ``execution_allowed`` / ``executed`` stay
    False. This is NOT a memory fallback: it carries ``storage == "durable"`` and
    the in-memory ``_STORE`` is never touched on this path.
    """
    return DurableApprovalRecord(
        reason="",
        source_status="unknown",
        storage=STORAGE_MODE_DURABLE,
        result=result,  # type: ignore[arg-type]
        message=message,
        executed=False,
        execution_allowed=False,
        execution_gate="blocked",
        redaction_applied=True,
        updated_at=now or _now(),
    )


#: adapter StoreResult error code -> P20 result string for a CREATE denial.
_CREATE_ERR_RESULT: dict[str, str] = {
    "not_authorized": "denied",
    "not_found": "not_found",
    "decision_conflict": "conflict",
}

#: adapter StoreResult error code -> P20 result string for a DECISION denial.
_DECISION_ERR_RESULT: dict[str, str] = {
    "not_found": "not_found",
    "not_authorized": "denied",
    "self_decision_denied": "denied",
    "terminal": "denied",
    "unknown_source": "denied",
    "decision_conflict": "conflict",
}

#: adapter StoreResult codes that signal a STORE-HEALTH problem (not a contract
#: denial): the durable store could not guarantee the write/read. These fail
#: CLOSED to a degraded DurableStoreNotReady rather than a shaped success.
_STORE_HEALTH_CODES: frozenset[str] = frozenset(
    ("stale_write", "store_unknown", "idempotent_replay")
)


def _durable_store_health_error(res: StoreResult) -> DurableStoreNotReady:
    """Map a store-health StoreResult error to a fail-closed degraded exception."""
    code = res.error.code if res.error else "store_unknown"
    return DurableStoreNotReady("degraded", f"durable store health: {code}")


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


async def _memory_create_durable_approval(
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

    P20-B-R1 identity binding: the maker is the AUTHENTICATED identity-only
    super_admin actor. An absent authenticated actor, or a client-supplied maker
    that does not equal the authenticated actor, is denied (no identity spoof,
    no system / operator fallback).

    Order of checks: authenticated actor -> maker matches actor -> reason ->
    idempotency_key -> confirm -> expires_at (future) -> P18 reference
    resolvable -> create idempotency store. An unresolvable P18 reference, a
    missing required field, a missing confirmation, or a past expires_at yields a
    denied record (not recorded). An unknown source status does NOT block
    creation -- it is stored verbatim (validation_status = source_unknown) and
    blocks the later approve decision.
    """
    now = _now()
    raw_reason = (reason or "").strip()
    raw_key = (idempotency_key or "").strip()
    raw_maker = (maker or "").strip()
    safe_reason = _p18._redact_reason(raw_reason)
    safe_correlation_id = _p18._sanitize_text(correlation_id)
    # metadata is redacted for audit use; not echoed on the record (no leak).
    _p18.redact_metadata(metadata)
    # P20-B-R1: the maker is the AUTHENTICATED identity-only super_admin actor.
    # A client-supplied maker is accepted only as an explicit assertion that MUST
    # equal the authenticated actor; otherwise the request is an identity spoof
    # and is denied. There is no system / operator-secret fallback for the maker.
    bound_maker = _p18._sanitize_text(actor) if actor else None

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

    # 1) authenticated actor required -- the maker binds to the authenticated
    #    identity (no system / operator-secret fallback may be a maker)
    if not bound_maker:
        return denied("Denied: an authenticated identity-only super_admin actor is required to open a durable approval (maker binds to the authenticated actor; no system / operator fallback).")

    # 2) a client-supplied maker must match the authenticated actor (spoof denied)
    if raw_maker and raw_maker != actor:
        return denied("Denied: the payload maker must match the authenticated actor; identity spoofing is denied.")

    # 3) reason required
    if not raw_reason:
        return denied("Denied: a non-empty reason is required to open a durable approval.")

    # 4) idempotency_key required
    if not raw_key:
        return denied("Denied: an idempotency_key is required to open a durable approval.")

    # 5) explicit confirmation required to open the request
    if not confirm:
        return denied("Denied: explicit confirmation (confirm=true) is required to open a durable approval.")

    # 6) expires_at required and in the future (an approval must expire)
    exp = _utc(expires_at)
    if exp is None:
        return denied("Denied: expires_at is required (a durable approval must expire).")
    if exp <= now:
        return denied("Denied: expires_at must be in the future.")

    # durable_retain_until defaults to expires_at (retention TTL)
    retain = _utc(durable_retain_until) or exp

    # 7) P18 reference must be resolvable (never fabricate an available source)
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

    # 8) create idempotency: duplicate / conflict (keyed by the key DIGEST,
    #    never the raw idempotency_key)
    fp = _create_fingerprint(resolved_action_type, tenant_id, bound_maker, raw_reason)
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

    # 9) record the durable approval at pending_review; execution_allowed stays False
    approval_id = str(uuid4())
    req_digest = _request_digest(action_id, resolved_action_type, tenant_id, bound_maker)
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
        maker=bound_maker,
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


def _memory_submit_decision(
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

    P20-B-R1 identity binding: the checker is the AUTHENTICATED identity-only
    super_admin actor. An absent authenticated actor, or a client-supplied
    approver_id that does not equal the authenticated actor, is denied (no
    identity spoof, no system / operator fallback).

    Maker-checker: the checker (authenticated actor) must differ from the maker
    (self-approval forbidden). Distinct checkers: each checker records at most
    one decision. reject is final (any single reject vetoes). approve accumulates
    until the quorum floor of distinct approve checkers is met, then resolves to
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
    safe_correlation_id = _p18._sanitize_text(correlation_id)
    _p18.redact_metadata(metadata)
    decision_digest = _digest(raw_key)
    # P20-B-R1: the checker binds to the AUTHENTICATED identity-only super_admin
    # actor. A client-supplied approver_id is accepted only as an explicit
    # assertion that MUST equal the authenticated actor; otherwise it is an
    # identity spoof and is denied. No system / operator fallback may count as a
    # checker or toward quorum.
    bound_approver = _p18._sanitize_text(actor) if actor else None

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
            checker_id=bound_approver,
            correlation_id=safe_correlation_id,
            now=now,
        )
        return _record_from(rec, result=result, message=message, now=now)

    if rec is None:
        return denied("Denied: approval_id not found.", result="not_found")

    # 1) authenticated actor required -- the checker binds to the authenticated
    #    identity (no system / operator-secret fallback may be a checker)
    if not bound_approver:
        return denied("Denied: an authenticated identity-only super_admin actor is required to record a decision (checker binds to the authenticated actor; no system / operator fallback).")

    # 2) a client-supplied approver_id must match the authenticated actor (spoof)
    if raw_approver and raw_approver != actor:
        return denied("Denied: the payload approver_id must match the authenticated actor; identity spoofing is denied.")

    # 3) decision must be approve | reject
    if decision not in ("approve", "reject"):
        return denied("Denied: decision must be 'approve' or 'reject'.")

    # 4) reason / idempotency_key / confirmation required
    if not raw_reason:
        return denied("Denied: a non-empty reason is required for a decision.")
    if not raw_key:
        return denied("Denied: an idempotency_key is required for a decision.")
    if not confirm:
        return denied("Denied: explicit confirmation (confirm=true) is required for a decision.")

    # 5) unimplemented terminal transitions are explicitly rejected (P20-B
    #    implements only pending_review / approved_execution_blocked / rejected)
    if rec.state in ("expired", "cancelled", "superseded", "failed_validation"):
        return denied(
            "Denied: the '%s' state transition is not implemented in P20-B; the approval is terminal and cannot be decided." % rec.state,
        )

    # 6) maker-checker separation: the checker (authenticated actor) must differ
    #    from the maker (the authenticated actor who opened the request)
    if bound_approver == rec.maker:
        return denied("Denied: maker-checker separation forbids the maker from approving / rejecting their own durable approval (self-approval denied).")

    # 7) already-rejected approval: reject is final
    if rec.state == "rejected":
        existing = next((c for c in rec.checkers if c.checker_id == bound_approver), None)
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
                checker_id=bound_approver,
                correlation_id=safe_correlation_id,
                now=now,
            )
            return _record_from(rec, result="duplicate", message="Duplicate: this checker already recorded this decision; reject is final. Nothing was executed.", now=now)
        return denied("Conflict: the durable approval is already rejected; reject is final and no further decision is accepted.", result="conflict")

    # 8) quorum-met approval (approved_execution_blocked): no further state change
    if rec.state == "approved_execution_blocked":
        existing = next((c for c in rec.checkers if c.checker_id == bound_approver), None)
        if decision == "approve" and (existing is None or existing.decision == "approve"):
            return _record_from(rec, result="duplicate", message="Duplicate: the durable approval already reached quorum (approved_execution_blocked); the approve is idempotent. Nothing was executed.", now=now)
        return denied("Conflict: the durable approval already reached quorum (approved_execution_blocked); a reject after quorum is rejected.", result="conflict")

    # 9) state is pending_review -> apply the decision
    existing = next((c for c in rec.checkers if c.checker_id == bound_approver), None)
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
            checker_id=bound_approver,
            correlation_id=safe_correlation_id,
            now=now,
        )
        rec.checkers.append(
            _CheckerDecision(
                checker_id=bound_approver,
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
            checker_id=bound_approver,
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
        checker_id=bound_approver,
        correlation_id=safe_correlation_id,
        now=now,
    )
    rec.checkers.append(
        _CheckerDecision(
            checker_id=bound_approver,
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
            checker_id=bound_approver,
            correlation_id=safe_correlation_id,
            now=now,
        )
        rec.audit_event_id = audit.event_id
        return _record_from(rec, result="approved", message="Approved: durable approval quorum was met and the approval resolved to approved_execution_blocked. The action was NOT executed; execution_allowed is false and no tenant state changed.", now=now)

    # quorum not yet met -> stays pending_review
    rec.updated_at = now
    return _record_from(rec, result="quorum_pending", message="Quorum pending: the checker approve was recorded; the durable approval stays pending_review until the quorum of distinct checkers is met. Nothing was executed.", now=now)


# -- Read / list -------------------------------------------------------------


def _memory_read_durable_approval(approval_id: str) -> Optional[DurableApprovalRecord]:
    """Return the record for an approval_id, or None when not found."""
    rec = _STORE.get(approval_id)
    if rec is None:
        return None
    return _record_from(rec, result="recorded", message="Read: durable approval record (ephemeral in-memory store). Nothing was executed.", now=rec.updated_at)


def _memory_list_durable_approvals(
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


# -- P21-D-D public handlers (runtime storage gate) --------------------------
#
# Each public operation resolves the runtime storage mode and delegates to the
# in-memory backend (explicit test / dev MEMORY mode) or the durable adapter
# (default / production DURABLE mode) behind the readiness gate. The durable
# path NEVER silently falls back to memory: on a not-ready store it raises
# DurableStoreNotReady (the route returns 503), and on a healthy store it
# persists through the adapter. Approval is not execution; durability is not
# execution: every durable record is re-validated by _from_durable_record.


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
    """Validate and record a durable approval request behind the storage gate.

    DURABLE mode (default): readiness-gated durable adapter write. MEMORY mode
    (explicit test / dev): the in-memory backend (``storage == "memory"``). Never
    executes anything; never silently falls back to memory in durable mode.
    """
    if get_storage_mode() == STORAGE_MODE_MEMORY:
        return await _memory_create_durable_approval(
            action_id=action_id, tenant_id=tenant_id, action_type=action_type,
            maker=maker, reason=reason, idempotency_key=idempotency_key,
            expires_at=expires_at, durable_retain_until=durable_retain_until,
            confirm=confirm, correlation_id=correlation_id, metadata=metadata,
            db=db, actor=actor, actor_role=actor_role, identity_context=identity_context,
        )
    # DURABLE mode: fail CLOSED at the readiness gate before any write.
    ready, code = await _check_durable_readiness(db)
    if not ready:
        raise DurableStoreNotReady(code, "durable approval store not ready for create")
    # Resolve the P18 reference honestly (never fabricate an available source).
    ctx = await _resolve_p18_context(action_id, action_type, tenant_id, db)
    if ctx is None:
        return _durable_denial_record(
            result="not_found",
            message="Denied: the P18 action reference could not be resolved (unknown action_id / action_type); durable approval not recorded.",
        )
    resolved_action_type, source_status, action_class = ctx
    adapter = DurableApprovalStoreAdapter(db)
    try:
        res = await adapter.create_request(
            action_id=action_id, tenant_id=tenant_id, action_type=resolved_action_type,
            source_status=source_status, action_class=action_class, maker=maker,
            reason=reason, idempotency_key=idempotency_key, expires_at=expires_at,
            durable_retain_until=durable_retain_until, confirm=confirm,
            correlation_id=correlation_id, metadata=metadata, actor=actor,
            actor_role=actor_role, identity_context=identity_context,
        )
    except DurableStoreNotReady:
        raise
    except Exception:
        # Pre-check passed but the write failed -> degraded (fail closed).
        raise DurableStoreNotReady("degraded", "durable create failed after readiness check")
    if res.ok:
        return _from_durable_record(res.value)
    if res.error and res.error.code in _STORE_HEALTH_CODES:
        raise _durable_store_health_error(res)
    result = _CREATE_ERR_RESULT.get(
        res.error.code if res.error else "store_unknown", "denied"
    )
    return _durable_denial_record(result=result, message=res.error.message if res.error else "")


async def submit_decision(
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
    db: AsyncSession,
) -> DurableApprovalRecord:
    """Record one checker decision behind the storage gate. Never executes.

    DURABLE mode: readiness-gated durable adapter write (maker-checker / quorum /
    reject-final / source-honesty enforced by the adapter). MEMORY mode: the
    in-memory backend. Never silently falls back to memory in durable mode.
    """
    if get_storage_mode() == STORAGE_MODE_MEMORY:
        return _memory_submit_decision(
            approval_id, decision=decision, approver_id=approver_id, reason=reason,
            idempotency_key=idempotency_key, confirm=confirm, correlation_id=correlation_id,
            metadata=metadata, actor=actor, actor_role=actor_role, identity_context=identity_context,
        )
    ready, code = await _check_durable_readiness(db)
    if not ready:
        raise DurableStoreNotReady(code, "durable approval store not ready for decision")
    adapter = DurableApprovalStoreAdapter(db)
    try:
        res = await adapter.submit_decision(
            approval_id, decision=decision, approver_id=approver_id, reason=reason,
            idempotency_key=idempotency_key, confirm=confirm, correlation_id=correlation_id,
            metadata=metadata, actor=actor, actor_role=actor_role, identity_context=identity_context,
        )
    except DurableStoreNotReady:
        raise
    except (ValueError, TypeError):
        # A malformed approval_id (not a UUID) -> not-found denial (matching the
        # in-memory contract), not a store-health failure.
        return _durable_denial_record(result="not_found", message="Denied: approval_id not found.")
    except Exception:
        raise DurableStoreNotReady("degraded", "durable decision failed after readiness check")
    if res.ok:
        return _from_durable_record(res.value)
    if res.error and res.error.code in _STORE_HEALTH_CODES:
        raise _durable_store_health_error(res)
    result = _DECISION_ERR_RESULT.get(
        res.error.code if res.error else "store_unknown", "denied"
    )
    return _durable_denial_record(result=result, message=res.error.message if res.error else "")


async def read_durable_approval(
    approval_id: str, *, db: AsyncSession
) -> Optional[DurableApprovalRecord]:
    """Return the record for an approval_id behind the storage gate, or None.

    DURABLE mode: readiness-gated durable adapter read; not-found returns None
    (the route maps that to 404, matching the in-memory contract). MEMORY mode:
    the in-memory backend.
    """
    if get_storage_mode() == STORAGE_MODE_MEMORY:
        return _memory_read_durable_approval(approval_id)
    ready, code = await _check_durable_readiness(db)
    if not ready:
        raise DurableStoreNotReady(code, "durable approval store not ready for read")
    adapter = DurableApprovalStoreAdapter(db)
    try:
        res = await adapter.get_request(approval_id)
    except DurableStoreNotReady:
        raise
    except (ValueError, TypeError):
        # A malformed approval_id (not a UUID) is a not-found, not a store
        # health issue -> None (the route returns 404), matching in-memory.
        return None
    except Exception:
        raise DurableStoreNotReady("degraded", "durable read failed after readiness check")
    if res.ok:
        return _from_durable_record(res.value)
    if res.error and res.error.code in _STORE_HEALTH_CODES:
        raise _durable_store_health_error(res)
    # not_found is the only expected non-health error from get_request -> None
    # so the route returns 404 (matching the in-memory read contract).
    return None


async def list_durable_approvals(
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None,
    action_type: Optional[str] = None,
    tenant_id: Optional[str] = None,
    *,
    db: AsyncSession,
) -> DurableApprovalQueue:
    """Return the queue of durable approval records behind the storage gate.

    DURABLE mode: readiness-gated durable adapter read (no audit write; list is
    read-only). MEMORY mode: the in-memory backend.
    """
    if get_storage_mode() == STORAGE_MODE_MEMORY:
        return _memory_list_durable_approvals(
            limit=limit, offset=offset, status=status, action_type=action_type, tenant_id=tenant_id
        )
    ready, code = await _check_durable_readiness(db)
    if not ready:
        raise DurableStoreNotReady(code, "durable approval store not ready for list")
    adapter = DurableApprovalStoreAdapter(db)
    filters: dict = {}
    if status:
        filters["status"] = status
    if action_type:
        filters["action_type"] = action_type
    if tenant_id:
        filters["tenant_id"] = tenant_id
    try:
        res = await adapter.list_requests(filters, limit=limit, offset=offset)
    except DurableStoreNotReady:
        raise
    except Exception:
        raise DurableStoreNotReady("degraded", "durable list failed after readiness check")
    if res.ok:
        queue = res.value
        # Re-assert the no-execution invariant on every queued record (fail-closed).
        for item in queue.items:
            _from_durable_record(item)
        return queue
    raise _durable_store_health_error(res)
