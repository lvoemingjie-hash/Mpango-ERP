"""Service layer for P23 Operator Task / Notification Queue (P23-B skeleton).

NON-EXECUTING, NON-SENDING, IN-MEMORY read model + task-state skeleton.

    A task is a view, not an executor. A notification is a record, not a delivery.

What this module does:
  - materialize prior-phase events into a deduplicated, severity-ranked queue of
    operator tasks (an ephemeral, process-local in-memory read model);
  - run a presentation-only state machine over those tasks (acknowledge /
    self-assign / in-progress / complete / dismiss), recording one append-only
    OperatorTaskAuditEvent per transition (and one per denied attempt);
  - record notification EVENTS (delivery_state == recorded | suppressed) -- it
    resolves no recipient address and sends nothing on any channel;
  - redact every free-text field through a content redactor so no secret / DSN /
    host / port / token / cookie / auth header / raw body / shell / SQL / script /
    tenant business payload is ever stored, returned, or audited.

What this module NEVER does:
  - execute a P22 action, approve a P19/P20/P21 approval, mutate a P17 registry
    field, or flip any P18 `executed` flag;
  - deliver a notification (no socket / SMTP / HTTP webhook / push); notification
    events stay at delivery_state == recorded | suppressed;
  - dispatch a worker, scheduler, drain loop, or on-call engine;
  - run shell / SQL / script / subprocess / pg_dump / restore;
  - read or write any tenant business / payment / billing / product record;
  - delete or truncate audit history on dismiss / expire (the queue is a view, not
    the system of record).

There is no migration, no ORM model, no table, no persistent store here -- the
read model is in-memory and resets per process (and per test via reset_store()).

Aligned to docs/ai/PLATFORM_PRODUCT_P23_OPERATOR_TASK_NOTIFICATION_QUEUE_CONTRACT.md
(P23-A), sections 4 (state machine), 5 (data model plan), 6 (notification boundary),
10 (audit), 11 (severity / dedup / correlation).
"""
from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from .schemas import (
    ACTIVE_STATES,
    ALLOWED_TRANSITIONS,
    DEFAULT_SEVERITY,
    DENIAL_CODES,
    NEVER_HEALTHY_TYPES,
    NEVER_SUCCESS_TYPES,
    TERMINAL_STATES,
    OperatorNotificationEvent,
    OperatorTask,
    OperatorTaskAuditEvent,
    OperatorTaskDetail,
    OperatorTaskIntakeEvent,
    OperatorTaskIntakeResponse,
    OperatorTaskQueue,
    OperatorTaskTransitionRequest,
    OperatorTaskTransitionResponse,
    TaskState,
    TransitionDenialCode,
)


# -- Content redaction (P23-A 6.3 never-leaked list; total, fail-closed) -------
#
# Free-text fields (summary / reason / evidence / notification summary) pass
# through here before they are stored, returned, or audited. The redactor is
# deliberately aggressive: when in doubt it redacts. It never inserts a secret /
# DSN / host / port / token / cookie / auth header / raw body / shell / SQL /
# script. Over-redaction of a benign hostname is acceptable and documented; an
# un-redacted secret is not.

_RE_DSN = re.compile(
    r"\b(?:postgres(?:ql)?|mysql|redis|mongodb(?:\+srv)?|amqp|mssql|clickhouse|"
    r"cassandra|elasticsearch|smtp|smtps|ftp|ldap|ldaps|s3|gs|azure|"
    r"cockroachdb|influxdb)(?:\+\w+)?://\S+",
    re.IGNORECASE,
)
_RE_HTTP_URL = re.compile(r"\bhttps?://\S+", re.IGNORECASE)
_RE_USERINFO = re.compile(r"[A-Za-z0-9._%+-]+:[^\s@/]+@[A-Za-z0-9.-]+(?::\d{2,5})?")
_RE_HOSTPORT = re.compile(
    r"\b(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}(?::\d{2,5})?\b"
    r"|\blocalhost(?::\d{2,5})?\b"
    r"|\b\d{1,3}(?:\.\d{1,3}){3}(?::\d{2,5})?\b"
)
_RE_SECRET_KV = re.compile(
    r"\b(password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|"
    r"secret[_-]?key|auth|authorization|cookie|set[_-]?cookie|credential|"
    r"apikey|dsn|connection[_-]?string|database[_-]?url|bearer)\b"
    r"\s*[:=]\s*[^\s;,)\}\]]+",
    re.IGNORECASE,
)
_RE_UNSAFE_TOKEN = re.compile(
    r"\b(pg_dump|pg_restore|mysqldump|rm\s+-rf|DROP\s+TABLE|TRUNCATE\s+TABLE|"
    r"DELETE\s+FROM|INSERT\s+INTO|UPDATE\s+\w+\s+SET|subprocess|os\.system|"
    r"os\.popen|shell\s*=\s*True|eval\s*\(|exec\s*\(|<script|javascript:)\b",
    re.IGNORECASE,
)

#: The literal "[redacted:*]" markers are themselves echo-safe.
_REDACTED_DSN = "[redacted:dsn]"
_REDACTED_URL = "[redacted:url]"
_REDACTED_CRED = "[redacted:credentials]"
_REDACTED_HOSTPORT = "[redacted:hostport]"
_REDACTED_SECRET = "[redacted:secret]"
_REDACTED_UNSAFE = "[redacted:unsafe-token]"


def redact_text(value: Optional[str]) -> Optional[str]:
    """Redact secrets / DSNs / host:port / unsafe tokens from a free-text string.

    Returns None unchanged. Returns the scrubbed string otherwise. The output
    never contains a scheme-bearing DSN, a user:pass@host pair, a host:port pair,
    a key=value secret, or a shell / SQL / script / dump token. Idempotent: the
    ``[redacted:*]`` markers contain no dot+TLD and survive a second pass.
    """
    if value is None:
        return None
    text = value
    text = _RE_DSN.sub(_REDACTED_DSN, text)
    text = _RE_HTTP_URL.sub(_REDACTED_URL, text)
    text = _RE_USERINFO.sub(_REDACTED_CRED, text)
    text = _RE_SECRET_KV.sub(_REDACTED_SECRET, text)
    text = _RE_HOSTPORT.sub(_REDACTED_HOSTPORT, text)
    text = _RE_UNSAFE_TOKEN.sub(_REDACTED_UNSAFE, text)
    return text


def _redact_optional(value: Optional[str]) -> Optional[str]:
    """Redact a free-text field that may be absent."""
    if value is None:
        return None
    return redact_text(value)


# -- In-memory store (ephemeral, process-local) -------------------------------


class _StoredTask:
    """A materialized operator task. Ephemeral, in memory. Never persisted."""

    __slots__ = (
        "task_id",
        "task_type",
        "severity",
        "state",
        "display_status",
        "tenant_id",
        "actor_scope",
        "owner_role",
        "owner_actor_id",
        "correlation_id",
        "linked_action_id",
        "linked_approval_id",
        "linked_execution_id",
        "linked_dry_run_ref",
        "linked_source_ref",
        "linked_incident_id",
        "summary_redacted",
        "reason_redacted",
        "evidence_ref",
        "source_status",
        "linked_gate_open",
        "dedup_key_digest",
        "ttl_expires_at",
        "created_at",
        "updated_at",
        "redaction_applied",
    )

    def __init__(self, **kwargs: Any) -> None:
        for key in self.__slots__:
            setattr(self, key, kwargs.get(key))


_TASKS: dict[str, _StoredTask] = {}  # task_id -> stored task
_AUDIT: list[OperatorTaskAuditEvent] = []  # global append-only audit
_NOTIFICATIONS: list[OperatorNotificationEvent] = []  # global notification events
_ACTIVE_DEDUP: dict[str, str] = {}  # dedup_key_digest -> task_id (ACTIVE tasks only)
_TASK_AUDIT_SEQ: dict[str, int] = {}  # task_id -> last sequence_no
# Delivery dedup: (task_id, channel) -> event_id for an in-flight (recorded /
# queued / delivered) notification, so a replay writes no duplicate.
_NOTIFICATION_INFLIGHT: dict[tuple[str, str], str] = {}


def reset_store() -> None:
    """Clear all in-memory P23 state. Used by tests; also gives a clean process start."""
    _TASKS.clear()
    _AUDIT.clear()
    _NOTIFICATIONS.clear()
    _ACTIVE_DEDUP.clear()
    _TASK_AUDIT_SEQ.clear()
    _NOTIFICATION_INFLIGHT.clear()


def audit_log() -> list[OperatorTaskAuditEvent]:
    """Return a copy of the global append-only audit log (for tests / inspection)."""
    return list(_AUDIT)


def task_audit_log(task_id: str) -> list[OperatorTaskAuditEvent]:
    """Return this task's audit events in sequence order (append-only; never deleted)."""
    return [e for e in _AUDIT if e.task_id == task_id]


def notifications_log() -> list[OperatorNotificationEvent]:
    """Return a copy of the recorded notification events (for tests / inspection)."""
    return list(_NOTIFICATIONS)


def task_notifications(task_id: str) -> list[OperatorNotificationEvent]:
    """Return this task's notification-event records in creation order."""
    return [n for n in _NOTIFICATIONS if n.task_id == task_id]


# -- Helpers -------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


def _digest(value: str) -> str:
    """One-way SHA-256 hex digest. Used for the dedup key and evidence-note pointers."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


_SEVERITY_RANK: dict[str, int] = {"low": 0, "medium": 1, "high": 2}
_RANK_SEVERITY: tuple[str, str, str] = ("low", "medium", "high")

#: Task types that force severity to high within their correlation (P23-A 11.1).
_FORCE_HIGH_TYPES: frozenset[str] = frozenset(
    {"source_unknown", "backup_check_warning", "execution_failed"}
)


def _first_linked_id(event: OperatorTaskIntakeEvent) -> Optional[str]:
    """The most-specific linked object id for the dedup key (P23-A 11.2)."""
    for value in (
        event.linked_execution_id,
        event.linked_approval_id,
        event.linked_action_id,
        event.linked_incident_id,
        event.linked_source_ref,
    ):
        if value:
            return value
    return None


def _dedup_key_digest(event: OperatorTaskIntakeEvent) -> str:
    """SHA-256 over the canonical dedup key (P23-A 5.4 / 11.2).

    Key = (task_type, linked object id, tenant_id, source_status, follow-up
    variant). The raw key is canonicalized before hashing; only the digest is
    stored. tenant_id is part of the key, so tenant-A and tenant-B events never
    collapse into one task (no cross-tenant dedup, P23-A 11.2 / C16).
    """
    linked_id = _first_linked_id(event) or ""
    raw = "|".join(
        [
            event.task_type,
            linked_id,
            event.tenant_id or "",
            event.source_status or "",
            (event.followup_variant or event.task_type),
        ]
    )
    return _digest(raw)


def _compute_display_status(
    task_type: str, source_status: Optional[str], state: str
) -> str:
    """The honest display label (P23-A 4.2 / 12.7 / 12.8, C4 / C5).

    source_unknown is NEVER healthy (rule 1 wins in every state, including
    completed). backup_check_warning is NEVER success (rule 2 wins in every
    state). A degraded source reads warning. Otherwise the label follows the
    lifecycle state.
    """
    if task_type in NEVER_HEALTHY_TYPES or source_status == "unknown":
        return "unknown"
    if task_type in NEVER_SUCCESS_TYPES or source_status == "degraded":
        return "warning"
    if state == "failed":
        return "failed"
    if state == "completed":
        return "completed"
    if state == "dismissed":
        return "dismissed"
    return "healthy"


def _severity_for(
    task_type: str,
    requested: Optional[str],
    correlation_id: str,
    tenant_id: Optional[str],
) -> str:
    """Default severity raised by the monotonic-within-correlation rule (P23-A 11.1).

    Severity is only ever raised, never lowered. If any ACTIVE peer sharing the
    correlation (and tenant) is high, this task is at least medium. If any ACTIVE
    peer (or this task itself) is a force-high type, this task is high.
    """
    base = requested if requested in _SEVERITY_RANK else DEFAULT_SEVERITY.get(task_type, "medium")
    level = _SEVERITY_RANK[base]
    peer_high = False
    peer_force_high = task_type in _FORCE_HIGH_TYPES
    tenant_norm = tenant_id or ""
    for peer in _TASKS.values():
        if peer.state in TERMINAL_STATES:
            continue
        if peer.correlation_id != correlation_id:
            continue
        if (peer.tenant_id or "") != tenant_norm:
            continue  # no cross-tenant severity bleed
        if _SEVERITY_RANK[peer.severity] >= 2:
            peer_high = True
        if peer.task_type in _FORCE_HIGH_TYPES:
            peer_force_high = True
    if peer_high:
        level = max(level, 1)
    if peer_force_high:
        level = max(level, 2)
    return _RANK_SEVERITY[level]


def _rerank_correlation(correlation_id: str, tenant_id: Optional[str]) -> None:
    """Lift ACTIVE peers in a correlation per the monotonic rule (P23-A 11.1).

    Never lowers. Called after each upsert so a late-arriving high / force-high
    task raises its already-materialized peers.
    """
    tenant_norm = tenant_id or ""
    peers = [
        t
        for t in _TASKS.values()
        if t.state not in TERMINAL_STATES
        and t.correlation_id == correlation_id
        and (t.tenant_id or "") == tenant_norm
    ]
    if not peers:
        return
    any_high = any(_SEVERITY_RANK[t.severity] >= 2 for t in peers)
    any_force = any(t.task_type in _FORCE_HIGH_TYPES for t in peers)
    if not (any_high or any_force):
        return
    for t in peers:
        level = _SEVERITY_RANK[t.severity]
        if any_force:
            level = max(level, 2)
        elif any_high:
            level = max(level, 1)
        new_sev = _RANK_SEVERITY[level]
        if new_sev != t.severity:
            t.severity = new_sev
            t.updated_at = _now()


def _view(stored: _StoredTask) -> OperatorTask:
    """Build an echo-safe OperatorTask view from the stored record."""
    return OperatorTask(
        task_id=stored.task_id,
        task_type=stored.task_type,
        severity=stored.severity,
        state=stored.state,
        display_status=stored.display_status,
        tenant_id=stored.tenant_id,
        actor_scope=stored.actor_scope,
        owner_role=stored.owner_role,
        owner_actor_id=stored.owner_actor_id,
        correlation_id=stored.correlation_id,
        linked_action_id=stored.linked_action_id,
        linked_approval_id=stored.linked_approval_id,
        linked_execution_id=stored.linked_execution_id,
        linked_dry_run_ref=stored.linked_dry_run_ref,
        linked_source_ref=stored.linked_source_ref,
        linked_incident_id=stored.linked_incident_id,
        summary_redacted=stored.summary_redacted,
        reason_redacted=stored.reason_redacted,
        evidence_ref=stored.evidence_ref,
        source_status=stored.source_status,
        linked_gate_open=stored.linked_gate_open,
        dedup_key_digest=stored.dedup_key_digest,
        ttl_expires_at=stored.ttl_expires_at,
        created_at=stored.created_at,
        updated_at=stored.updated_at,
        redaction_applied=True,
    )


def _emit_audit(
    stored: _StoredTask,
    *,
    transition: str,
    previous_state: TaskState,
    next_state: TaskState,
    actor_id: Optional[str],
    actor_role: str,
    reason_redacted: Optional[str] = None,
    denial_code: Optional[TransitionDenialCode] = None,
) -> OperatorTaskAuditEvent:
    """Append exactly one OperatorTaskAuditEvent. Append-only; never deleted."""
    seq = _TASK_AUDIT_SEQ.get(stored.task_id, 0) + 1
    _TASK_AUDIT_SEQ[stored.task_id] = seq
    event = OperatorTaskAuditEvent(
        event_id=_uuid(),
        task_id=stored.task_id,
        task_type=stored.task_type,
        actor_id=actor_id,
        actor_role=actor_role,  # type: ignore[arg-type]
        tenant_id=stored.tenant_id,
        transition=transition,
        previous_state=previous_state,
        next_state=next_state,
        reason_redacted=_redact_optional(reason_redacted),
        denial_code=denial_code,
        correlation_id=stored.correlation_id,
        linked_action_id=stored.linked_action_id,
        linked_approval_id=stored.linked_approval_id,
        linked_execution_id=stored.linked_execution_id,
        linked_source_ref=stored.linked_source_ref,
        linked_incident_id=stored.linked_incident_id,
        redaction_applied=True,
        sequence_no=seq,
        created_at=_now(),
    )
    _AUDIT.append(event)
    return event


def _record_notification(
    stored: _StoredTask,
    channel: str,
    summary: Optional[str],
    recipient_role: Optional[str],
) -> Optional[OperatorNotificationEvent]:
    """Record one notification EVENT (P23-A 6). delivery_state == recorded | suppressed.

    Delivery dedup: at most one in-flight (recorded) notification per
    (task_id, channel); a replay returns the existing event and writes no
    duplicate (P23-A 5.2 / 11.2 / C17). Nothing is sent on any channel.
    """
    key = (stored.task_id, channel)
    inflight = _NOTIFICATION_INFLIGHT.get(key)
    if inflight is not None:
        for n in _NOTIFICATIONS:
            if n.event_id == inflight:
                return n

    redacted_summary = redact_text(summary) if summary else ""
    delivery_state = "recorded" if redacted_summary else "suppressed"
    event = OperatorNotificationEvent(
        event_id=_uuid(),
        task_id=stored.task_id,
        channel=channel,  # type: ignore[arg-type]
        delivery_state=delivery_state,  # type: ignore[arg-type]
        severity=stored.severity,
        tenant_id=stored.tenant_id,
        actor_scope=stored.actor_scope,
        recipient_role=recipient_role,  # type: ignore[arg-type]
        summary_redacted=redacted_summary or "[suppressed:non-safe-summary]",
        correlation_id=stored.correlation_id,
        redaction_applied=True,
        created_at=_now(),
    )
    _NOTIFICATIONS.append(event)
    if delivery_state == "recorded":
        _NOTIFICATION_INFLIGHT[key] = event.event_id
    return event


# -- Intake / materialization (executes nothing, approves nothing) -------------


def upsert_task_from_event(
    event: OperatorTaskIntakeEvent,
) -> OperatorTaskIntakeResponse:
    """Materialize (or dedup-bump) a task from a typed, redacted source event.

    Executes nothing and approves nothing. Collapses repeat events for the same
    logical follow-up into one ACTIVE task via dedup_key_digest; terminal tasks
    are exempt so a recurring follow-up re-opens as a NEW task (P23-A 5.4).
    """
    digest = _dedup_key_digest(event)
    now = _now()

    existing_id = _ACTIVE_DEDUP.get(digest)
    if existing_id is not None and existing_id in _TASKS:
        stored = _TASKS[existing_id]
        # Idempotent replay: bump updated_at, re-rank severity, refresh the
        # linked-gate mirror. Writes no new task and no duplicate success audit.
        stored.updated_at = now
        stored.severity = _severity_for(
            stored.task_type, event.severity, stored.correlation_id, stored.tenant_id
        )
        stored.linked_gate_open = bool(event.linked_gate_open)
        if event.reason:
            stored.reason_redacted = _redact_optional(event.reason)
        _rerank_correlation(stored.correlation_id, stored.tenant_id)
        if event.channel:
            _record_notification(stored, event.channel, event.summary, event.owner_role)
        return OperatorTaskIntakeResponse(
            task=_view(stored), created=False, deduped=True
        )

    severity = _severity_for(event.task_type, event.severity, event.correlation_id, event.tenant_id)
    summary_redacted = redact_text(event.summary) if event.summary else ""
    stored = _StoredTask(
        task_id=_uuid(),
        task_type=event.task_type,
        severity=severity,
        state="open",
        display_status=_compute_display_status(event.task_type, event.source_status, "open"),
        tenant_id=event.tenant_id,
        actor_scope=event.actor_scope,
        owner_role=event.owner_role,
        owner_actor_id=None,
        correlation_id=event.correlation_id,
        linked_action_id=event.linked_action_id,
        linked_approval_id=event.linked_approval_id,
        linked_execution_id=event.linked_execution_id,
        linked_dry_run_ref=event.linked_dry_run_ref,
        linked_source_ref=event.linked_source_ref,
        linked_incident_id=event.linked_incident_id,
        summary_redacted=summary_redacted or "[suppressed:non-safe-summary]",
        reason_redacted=_redact_optional(event.reason),
        evidence_ref=None,
        source_status=event.source_status,
        linked_gate_open=bool(event.linked_gate_open),
        dedup_key_digest=digest,
        ttl_expires_at=event.ttl_expires_at,
        created_at=now,
        updated_at=now,
        redaction_applied=True,
    )
    _TASKS[stored.task_id] = stored
    _ACTIVE_DEDUP[digest] = stored.task_id
    _TASK_AUDIT_SEQ[stored.task_id] = 0
    _emit_audit(
        stored,
        transition="materialized",
        previous_state="open",
        next_state="open",
        actor_id=None,
        actor_role="system",
        reason_redacted=event.summary,
    )
    _rerank_correlation(stored.correlation_id, stored.tenant_id)
    if event.channel:
        _record_notification(stored, event.channel, event.summary, event.owner_role)
    return OperatorTaskIntakeResponse(task=_view(stored), created=True, deduped=False)


# -- Read / list ---------------------------------------------------------------


def list_tasks(
    *,
    limit: int = 50,
    offset: int = 0,
    severity: Optional[str] = None,
    task_type: Optional[str] = None,
    state: Optional[str] = None,
    tenant_id: Optional[str] = None,
    source_status: Optional[str] = None,
    owner_actor_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> OperatorTaskQueue:
    """List tasks with filters, ranked by severity DESC then recency. Read-only."""
    items = list(_TASKS.values())
    if severity is not None:
        items = [t for t in items if t.severity == severity]
    if task_type is not None:
        items = [t for t in items if t.task_type == task_type]
    if state is not None:
        items = [t for t in items if t.state == state]
    if tenant_id is not None:
        items = [t for t in items if (t.tenant_id or "") == tenant_id]
    if source_status is not None:
        items = [t for t in items if (t.source_status or "") == source_status]
    if owner_actor_id is not None:
        items = [t for t in items if (t.owner_actor_id or "") == owner_actor_id]
    if correlation_id is not None:
        items = [t for t in items if t.correlation_id == correlation_id]

    total = len(items)
    active_count = sum(1 for t in items if t.state in ACTIVE_STATES)

    items.sort(
        key=lambda t: (-_SEVERITY_RANK[t.severity], t.created_at)
    )
    page = items[offset : offset + limit]
    return OperatorTaskQueue(
        tasks=[_view(t) for t in page],
        total=total,
        active_count=active_count,
        limit=limit,
        offset=offset,
    )


def read_task(task_id: str) -> Optional[OperatorTaskDetail]:
    """Read one task's redacted record, full audit history, and notification events.

    Returns None when missing. dismissed / expired tasks retain their full audit
    history here (the queue is a view, not the system of record; P23-A 12.9 / C6).
    """
    stored = _TASKS.get(task_id)
    if stored is None:
        return None
    detail = OperatorTaskDetail(
        **_view(stored).model_dump(),
        audit_events=task_audit_log(task_id),
        notification_events=task_notifications(task_id),
    )
    return detail


# -- Transitions (presentation-only; never execute / approve / mutate / send) --


def _transition_response(
    stored: _StoredTask,
    *,
    accepted: bool,
    transition: str,
    previous_state: TaskState,
    next_state: TaskState,
    denial_code: Optional[TransitionDenialCode],
) -> OperatorTaskTransitionResponse:
    return OperatorTaskTransitionResponse(
        accepted=accepted,
        task=_view(stored),
        transition=transition,
        previous_state=previous_state,
        next_state=next_state,
        denial_code=denial_code,
    )


def _apply_transition(
    task_id: str,
    target_state: TaskState,
    *,
    action: str,
    actor_id: Optional[str],
    actor_role: str,
    payload: Optional[OperatorTaskTransitionRequest],
) -> OperatorTaskTransitionResponse:
    """Core state-machine step. Records exactly one audit event (success or denial).

    Rejects: missing task, terminal source state, transition not in the allowed
    graph, completion without evidence, completion while the linked gate is open.
    A rejection changes no state; it is audited as a denied transition.
    """
    stored = _TASKS.get(task_id)
    if stored is None:
        # No task row to echo; surface a not-found denial with no state change.
        return OperatorTaskTransitionResponse(
            accepted=False,
            task=OperatorTask(  # type: ignore[call-arg]
                task_id=task_id,
                task_type="action_request_created",
                severity="low",
                state="open",
                display_status="none",
                tenant_id=None,
                actor_scope="platform",
                owner_role=None,
                owner_actor_id=None,
                correlation_id="",
                linked_action_id=None,
                linked_approval_id=None,
                linked_execution_id=None,
                linked_dry_run_ref=None,
                linked_source_ref=None,
                linked_incident_id=None,
                summary_redacted="[not-found]",
                reason_redacted=None,
                evidence_ref=None,
                source_status=None,
                linked_gate_open=False,
                dedup_key_digest="",
                ttl_expires_at=None,
                created_at=_now(),
                updated_at=_now(),
                redaction_applied=True,
            ),
            transition=f"denied:{action}",
            previous_state="open",
            next_state="open",
            denial_code="TASK_NOT_FOUND",
        )

    previous_state = stored.state
    reason = payload.reason if payload else None
    evidence = payload.evidence if payload else None
    evidence_ref = payload.evidence_ref if payload else None

    # Terminal states accept no outgoing transition (P23-A 4.4 / C11).
    if previous_state in TERMINAL_STATES:
        _emit_audit(
            stored,
            transition=f"denied:{action}",
            previous_state=previous_state,
            next_state=previous_state,
            actor_id=actor_id,
            actor_role=actor_role,
            reason_redacted=reason,
            denial_code="TRANSITION_DENIED_TERMINAL",
        )
        return _transition_response(
            stored,
            accepted=False,
            transition=f"denied:{action}",
            previous_state=previous_state,
            next_state=previous_state,
            denial_code="TRANSITION_DENIED_TERMINAL",
        )

    allowed = ALLOWED_TRANSITIONS.get(previous_state, frozenset())
    if target_state not in allowed:
        _emit_audit(
            stored,
            transition=f"denied:{action}",
            previous_state=previous_state,
            next_state=previous_state,
            actor_id=actor_id,
            actor_role=actor_role,
            reason_redacted=reason,
            denial_code="TRANSITION_DENIED_INVALID",
        )
        return _transition_response(
            stored,
            accepted=False,
            transition=f"denied:{action}",
            previous_state=previous_state,
            next_state=previous_state,
            denial_code="TRANSITION_DENIED_INVALID",
        )

    # Completion rules (P23-A 4.4 / C9): evidence required AND linked gate closed.
    if target_state == "completed":
        has_note = bool(evidence and evidence.strip())
        has_ref = bool(evidence_ref and evidence_ref.strip())
        if not (has_note or has_ref):
            _emit_audit(
                stored,
                transition="denied:complete",
                previous_state=previous_state,
                next_state=previous_state,
                actor_id=actor_id,
                actor_role=actor_role,
                reason_redacted=reason,
                denial_code="COMPLETE_DENIED_NO_EVIDENCE",
            )
            return _transition_response(
                stored,
                accepted=False,
                transition="denied:complete",
                previous_state=previous_state,
                next_state=previous_state,
                denial_code="COMPLETE_DENIED_NO_EVIDENCE",
            )
        if stored.linked_gate_open:
            _emit_audit(
                stored,
                transition="denied:complete",
                previous_state=previous_state,
                next_state=previous_state,
                actor_id=actor_id,
                actor_role=actor_role,
                reason_redacted=reason,
                denial_code="COMPLETE_DENIED_GATE_OPEN",
            )
            return _transition_response(
                stored,
                accepted=False,
                transition="denied:complete",
                previous_state=previous_state,
                next_state=previous_state,
                denial_code="COMPLETE_DENIED_GATE_OPEN",
            )

    # Apply the transition.
    stored.state = target_state
    stored.display_status = _compute_display_status(
        stored.task_type, stored.source_status, target_state
    )
    stored.updated_at = _now()
    if reason:
        stored.reason_redacted = _redact_optional(reason)
    if target_state == "completed":
        if evidence and evidence.strip():
            # Store a one-way digest pointer, never the raw note, on the task row;
            # the redacted evidence note itself lives in the completion audit event.
            stored.evidence_ref = "note:" + _digest(redact_text(evidence) or "")[:16]
        elif evidence_ref and evidence_ref.strip():
            stored.evidence_ref = _redact_optional(evidence_ref)
    if target_state in TERMINAL_STATES:
        # Terminal tasks leave the active dedup window so a recurrence re-opens
        # as a NEW task (P23-A 5.4 / 11.2).
        _ACTIVE_DEDUP.pop(stored.dedup_key_digest, None)

    audit_reason = reason
    if target_state == "completed":
        audit_reason = evidence if (evidence and evidence.strip()) else (evidence_ref or reason)
    _emit_audit(
        stored,
        transition=f"{previous_state}->{target_state}",
        previous_state=previous_state,
        next_state=target_state,
        actor_id=actor_id,
        actor_role=actor_role,
        reason_redacted=audit_reason,
    )
    return _transition_response(
        stored,
        accepted=True,
        transition=f"{previous_state}->{target_state}",
        previous_state=previous_state,
        next_state=target_state,
        denial_code=None,
    )


def acknowledge_task(
    task_id: str,
    *,
    actor_id: Optional[str],
    actor_role: str,
    payload: Optional[OperatorTaskTransitionRequest] = None,
) -> OperatorTaskTransitionResponse:
    """open|waiting_on_* -> acknowledged (an operator has seen the task)."""
    return _apply_transition(
        task_id, "acknowledged", action="acknowledge",
        actor_id=actor_id, actor_role=actor_role, payload=payload,
    )


def mark_in_progress_task(
    task_id: str,
    *,
    actor_id: Optional[str],
    actor_role: str,
    payload: Optional[OperatorTaskTransitionRequest] = None,
) -> OperatorTaskTransitionResponse:
    """-> in_progress (operator is working the follow-up; the task runs nothing)."""
    return _apply_transition(
        task_id, "in_progress", action="in_progress",
        actor_id=actor_id, actor_role=actor_role, payload=payload,
    )


def complete_task(
    task_id: str,
    *,
    actor_id: Optional[str],
    actor_role: str,
    payload: Optional[OperatorTaskTransitionRequest] = None,
) -> OperatorTaskTransitionResponse:
    """-> completed. Requires evidence AND a closed linked gate. Executes nothing."""
    return _apply_transition(
        task_id, "completed", action="complete",
        actor_id=actor_id, actor_role=actor_role, payload=payload,
    )


def dismiss_task(
    task_id: str,
    *,
    actor_id: Optional[str],
    actor_role: str,
    payload: Optional[OperatorTaskTransitionRequest] = None,
) -> OperatorTaskTransitionResponse:
    """-> dismissed. Removes from the active queue; audit history is RETAINED."""
    return _apply_transition(
        task_id, "dismissed", action="dismiss",
        actor_id=actor_id, actor_role=actor_role, payload=payload,
    )


def self_assign_task(
    task_id: str,
    *,
    actor_id: Optional[str],
    actor_role: str,
    payload: Optional[OperatorTaskTransitionRequest] = None,
) -> OperatorTaskTransitionResponse:
    """Set owner_actor_id / owner_role to the authenticated operator.

    Owner is PRESENTATION only (not authorization). This does NOT change the
    task state and runs nothing; it records a self_assigned audit event. An
    operator may self-assign only tasks already visible to them (the route guard
    enforces visibility); owner grants no new privilege (P23-A 9.2 / C24).
    """
    stored = _TASKS.get(task_id)
    if stored is None:
        return _apply_transition(
            task_id, "open", action="self_assign",
            actor_id=actor_id, actor_role=actor_role, payload=payload,
        )
    previous_state = stored.state
    reason = payload.reason if payload else None
    # Self-assignment is allowed on any non-terminal task; on a terminal task it
    # is a no-op denial (the task has left the active queue).
    if previous_state in TERMINAL_STATES:
        _emit_audit(
            stored,
            transition="denied:self_assign",
            previous_state=previous_state,
            next_state=previous_state,
            actor_id=actor_id,
            actor_role=actor_role,
            reason_redacted=reason,
            denial_code="TRANSITION_DENIED_TERMINAL",
        )
        return _transition_response(
            stored,
            accepted=False,
            transition="denied:self_assign",
            previous_state=previous_state,
            next_state=previous_state,
            denial_code="TRANSITION_DENIED_TERMINAL",
        )
    stored.owner_actor_id = actor_id
    if actor_role in ("super_admin", "engineering_operator", "support_operator"):
        stored.owner_role = actor_role  # type: ignore[assignment]
    stored.updated_at = _now()
    if reason:
        stored.reason_redacted = _redact_optional(reason)
    _emit_audit(
        stored,
        transition="self_assigned",
        previous_state=previous_state,
        next_state=previous_state,
        actor_id=actor_id,
        actor_role=actor_role,
        reason_redacted=reason,
    )
    return _transition_response(
        stored,
        accepted=True,
        transition="self_assigned",
        previous_state=previous_state,
        next_state=previous_state,
        denial_code=None,
    )


def record_notification_event(
    task_id: str,
    *,
    channel: str,
    summary: Optional[str],
    recipient_role: Optional[str] = None,
    actor_id: Optional[str] = None,
    actor_role: str = "system",
) -> Optional[OperatorNotificationEvent]:
    """Record a notification event for an existing task. Record-only; sends nothing.

    delivery_state == recorded (or suppressed if the redacted summary is empty).
    Subject to the per-(task, channel) in-flight delivery dedup. Returns None if
    the task does not exist.
    """
    stored = _TASKS.get(task_id)
    if stored is None:
        return None
    return _record_notification(stored, channel, summary, recipient_role)


__all__ = [
    "reset_store",
    "audit_log",
    "task_audit_log",
    "notifications_log",
    "task_notifications",
    "redact_text",
    "upsert_task_from_event",
    "list_tasks",
    "read_task",
    "acknowledge_task",
    "self_assign_task",
    "mark_in_progress_task",
    "complete_task",
    "dismiss_task",
    "record_notification_event",
]


# Static import-time guards: keep the denial vocabulary closed and discoverable.
assert all(code in DENIAL_CODES for code in TransitionDenialCode.__args__)  # type: ignore[attr-defined]
