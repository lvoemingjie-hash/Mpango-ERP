"""Service layer for P24 Incident + Runbook Closeout (P24-B skeleton).

NON-EXECUTING, NON-SENDING, IN-MEMORY closeout read model + runbook step model.

    An incident closeout is a view, not an executor. A runbook step is a pointer,
    not an execution. A follow-up task is a record, not a repair.

What this module does:
  - materialize recorded PUSH intake events into an incident closeout read model
    and an ordered runbook step model (an ephemeral, process-local in-memory
    store);
  - run a presentation-only closeout lifecycle (detect / triage / flag-observe /
    remediate / await / close / withdraw) and step state machine over them,
    recording one append-only audit event per transition (and one per denied
    attempt) -- closeout and step each get their own audit event;
  - materialize the two P23 task types P23-C left as PUSH intake
    (``incident_followup_required`` for an owed follow-up on an active-flagged
    closeout; ``runbook_step_required`` per owed / in-progress / blocked step)
    through the EXISTING P23 upsert seam, and resolve them when the follow-up /
    step goes terminal -- completing those tasks executes nothing;
  - mirror -- never write -- the P17 ``incident_active`` flag, the P22 execution
    outcome, and the P21 approval state, all supplied as observed-state mirrors
    on intake events;
  - redact every free-text field through the P23 content redactor so no secret /
    DSN / host / port / token / cookie / auth header / raw body / shell / SQL /
    script / tenant business payload is ever stored, returned, or audited.

What this module NEVER does:
  - execute a P22 action, approve a P19/P20/P21 approval, set or clear the P17
    ``incident_active`` flag, flip any P18 ``executed`` flag, or mutate a
    registry field;
  - deliver a notification (no socket / SMTP / HTTP webhook / push);
  - dispatch a worker, scheduler, drain loop, or on-call engine;
  - run shell / SQL / script / subprocess / pg_dump / restore;
  - read or write any tenant business / payment / billing / product record;
  - delete or truncate audit history on withdraw / expire (the closeout is a
    view, not the system of record).

There is no migration, no ORM model, no table, no persistent store here -- the
read model is in-memory and resets per process (and per test via reset_store()).

This module imports ONLY the P23 service seam (upsert / complete / dismiss +
redact_text) -- it imports no P15 / P17 / P18 / P19 / P20 / P21 / P22 module; a
static AST guard in the test suite asserts that. All prior-phase state arrives
as redacted, echo-safe OBSERVED mirrors on intake events (PUSH intake only, the
counterpart to P23-C's read-only PULL bridge).

Aligned to docs/ai/PLATFORM_PRODUCT_P24_INCIDENT_RUNBOOK_CLOSEOUT_CONTRACT.md
(P24-A), sections 3 (closeout lifecycle), 4 (runbook step model), 5 (source
boundaries / materialization), 6 (data model plan), 7 (audit), 11 (severity /
dedup / correlation).
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

# The P23 service seam is the ONLY prior-phase import. P23.services itself
# imports no P22 execution / P17 registry module, so this stays non-executing.
from api.v1.platform.p23.schemas import (
    TERMINAL_STATES as TERMINAL_P23_STATES,
    OperatorTaskIntakeEvent,
    OperatorTaskTransitionRequest,
)
from api.v1.platform.p23.services import (
    complete_task as _p23_complete_task,
    dismiss_task as _p23_dismiss_task,
    read_task as _p23_read_task,
    redact_text,
    upsert_task_from_event as _p23_upsert_task,
)

from .schemas import (
    ACTIVE_CLOSEOUT_STATES,
    ACTIVE_STEP_STATES,
    ALLOWED_CLOSEOUT_TRANSITIONS,
    ALLOWED_STEP_TRANSITIONS,
    CloseoutDenialCode,
    DENIAL_CODES,
    IncidentCloseout,
    IncidentCloseoutAuditEvent,
    IncidentCloseoutDetail,
    IncidentCloseoutIntakeEvent,
    IncidentCloseoutIntakeResponse,
    IncidentCloseoutList,
    RunbookStep,
    RunbookStepAuditEvent,
    RunbookView,
    TERMINAL_CLOSEOUT_STATES,
    TERMINAL_STEP_STATES,
)


# -- In-memory store (ephemeral, process-local) -------------------------------


class _StoredCloseout:
    """A materialized incident closeout. Ephemeral, in memory. Never persisted."""

    __slots__ = (
        "closeout_id",
        "state",
        "display_status",
        "classification",
        "severity",
        "tenant_id",
        "actor_scope",
        "owner_role",
        "owner_actor_id",
        "correlation_id",
        "flag_observed",
        "flag_ever_set",
        "linked_incident_id",
        "linked_triage_snapshot_ref",
        "linked_handoff_ref",
        "summary_redacted",
        "reason_redacted",
        "source_status",
        "linked_execution_warning",
        "dedup_key_digest",
        "ttl_expires_at",
        "linked_followup_task_id",
        "followup_owed",
        "created_at",
        "updated_at",
        "redaction_applied",
    )

    def __init__(self, **kwargs: Any) -> None:
        for key in self.__slots__:
            setattr(self, key, kwargs.get(key))


class _StoredStep:
    """A runbook step. Ephemeral, in memory. Never persisted."""

    __slots__ = (
        "step_id",
        "closeout_id",
        "sequence_no",
        "step_kind",
        "step_state",
        "display_status",
        "tenant_id",
        "correlation_id",
        "linked_action_id",
        "linked_approval_id",
        "linked_execution_id",
        "linked_source_ref",
        "evidence_ref",
        "summary_redacted",
        "reason_redacted",
        "source_status",
        "linked_execution_terminal",
        "linked_approval_resolved",
        "linked_execution_warning",
        "dedup_key_digest",
        "linked_task_id",
        "created_at",
        "updated_at",
        "redaction_applied",
    )

    def __init__(self, **kwargs: Any) -> None:
        for key in self.__slots__:
            setattr(self, key, kwargs.get(key))


_CLOSEOUTS: dict[str, _StoredCloseout] = {}  # closeout_id -> stored closeout
_STEPS: dict[str, _StoredStep] = {}  # step_id -> stored step
_CLOSEOUT_STEP_ORDER: dict[str, list[str]] = {}  # closeout_id -> [step_id, ...]
_CLOSEOUT_AUDIT: list[IncidentCloseoutAuditEvent] = []  # global append-only
_STEP_AUDIT: list[RunbookStepAuditEvent] = []  # global append-only
_ACTIVE_CLOSEOUT_DEDUP: dict[str, str] = {}  # digest -> closeout_id (ACTIVE only)
_ACTIVE_STEP_DEDUP: dict[str, str] = {}  # digest -> step_id (ACTIVE only)
_CLOSEOUT_AUDIT_SEQ: dict[str, int] = {}
_STEP_AUDIT_SEQ: dict[str, int] = {}


def reset_store() -> None:
    """Clear all in-memory P24 state. Used by tests; also a clean process start."""
    _CLOSEOUTS.clear()
    _STEPS.clear()
    _CLOSEOUT_STEP_ORDER.clear()
    _CLOSEOUT_AUDIT.clear()
    _STEP_AUDIT.clear()
    _ACTIVE_CLOSEOUT_DEDUP.clear()
    _ACTIVE_STEP_DEDUP.clear()
    _CLOSEOUT_AUDIT_SEQ.clear()
    _STEP_AUDIT_SEQ.clear()


def closeout_audit_log() -> list[IncidentCloseoutAuditEvent]:
    """Return a copy of the global append-only closeout audit log."""
    return list(_CLOSEOUT_AUDIT)


def closeout_audit_log_for(closeout_id: str) -> list[IncidentCloseoutAuditEvent]:
    """This closeout's audit events in sequence order (append-only; never deleted)."""
    return [e for e in _CLOSEOUT_AUDIT if e.closeout_id == closeout_id]


def step_audit_log() -> list[RunbookStepAuditEvent]:
    """Return a copy of the global append-only step audit log."""
    return list(_STEP_AUDIT)


def step_audit_log_for(step_id: str) -> list[RunbookStepAuditEvent]:
    """This step's audit events in sequence order (append-only; never deleted)."""
    return [e for e in _STEP_AUDIT if e.step_id == step_id]


# -- Helpers -------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


def _digest(value: str) -> str:
    """One-way SHA-256 hex digest. Used for dedup keys and evidence-note pointers."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _redact_optional(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return redact_text(value)


_SEVERITY_RANK: dict[str, int] = {"low": 0, "medium": 1, "high": 2}
_RANK_SEVERITY: tuple[str, str, str] = ("low", "medium", "high")

#: Closeout is forced to severity high when it mirrors an unknown source or a
#: completed_with_warning execution (P24-A 5.2 / 5.3 severity rule, mirroring
#: P23's force-high types).
_FORCE_HIGH: bool = True  # marker for the import-time guard below


def _actor_scope_for_tenant(tenant_id: Optional[str]) -> str:
    return "tenant_contextual" if tenant_id else "platform"


def _compute_closeout_display(
    state: str,
    source_status: Optional[str],
    linked_execution_warning: bool,
) -> str:
    """The honest closeout label (P24-A acceptance 7 / 8, C9 / C10).

    source_unknown is NEVER healthy (rule wins in every state, incl closed). A
    degraded source or a completed_with_warning linked execution is NEVER a
    success. Otherwise the label follows the lifecycle state.
    """
    if source_status == "unknown":
        return "unknown"
    if linked_execution_warning or source_status == "degraded":
        return "warning"
    if state == "closed":
        return "closed"
    if state == "withdrawn":
        return "withdrawn"
    if state == "expired":
        return "unknown"
    return "healthy"


def _compute_step_display(
    state: str,
    source_status: Optional[str],
    linked_execution_warning: bool,
) -> str:
    """The honest step label (P24-A 4.2 / acceptance 7 / 8).

    A source_unknown step, or any blocked step, reads ``unknown`` (never healthy,
    never auto-completed). A degraded source or a completed_with_warning linked
    execution reads ``warning`` (never a success). Otherwise the label follows
    the step state.
    """
    if source_status == "unknown" or state == "blocked":
        return "unknown"
    if linked_execution_warning or source_status == "degraded":
        return "warning"
    if state == "done":
        return "completed"
    if state == "not_applicable":
        return "dismissed"
    return "healthy"


def _closeout_dedup_digest(
    correlation_id: str,
    tenant_id: Optional[str],
    linked_incident_id: Optional[str],
) -> str:
    """SHA-256 over the canonical closeout dedup key (P24-A 5.5 / 6.1).

    Key = (incident_closeout, correlation_id, tenant_id, linked_incident_id),
    scoped to non-terminal states. tenant_id is part of the key so tenant-A and
    tenant-B closeouts never collapse into one (no cross-tenant dedup, C18).
    """
    raw = "|".join(
        [
            "incident_closeout",
            correlation_id or "",
            tenant_id or "",
            linked_incident_id or "",
        ]
    )
    return _digest(raw)


def _step_dedup_digest(
    closeout_id: str,
    sequence_no: int,
    step_kind: str,
    tenant_id: Optional[str],
) -> str:
    """SHA-256 over the canonical step dedup key (P24-A 5.5 / 6.2).

    Key = (runbook_step, closeout_id, sequence_no, step_kind, tenant_id),
    scoped to non-terminal step states so a recurring step re-opens as a NEW
    step (P24-A 5.5 / C14). tenant_id is part of the key (no cross-tenant dedup).
    """
    raw = "|".join(
        [
            "runbook_step",
            closeout_id or "",
            str(sequence_no),
            step_kind or "",
            tenant_id or "",
        ]
    )
    return _digest(raw)


def _severity_for(
    requested: Optional[str],
    source_status: Optional[str],
    linked_execution_warning: bool,
    correlation_id: str,
    tenant_id: Optional[str],
) -> str:
    """Default severity raised by the monotonic-within-correlation rule (P24-A 5.2).

    Severity is only ever raised, never lowered. An unknown source or a
    completed_with_warning linked execution forces high. If any ACTIVE peer
    closeout sharing the correlation (and tenant) is high, this closeout is at
    least medium.
    """
    force_high = source_status == "unknown" or bool(linked_execution_warning)
    base = requested if requested in _SEVERITY_RANK else ("high" if force_high else "medium")
    level = _SEVERITY_RANK[base]
    tenant_norm = tenant_id or ""
    peer_high = force_high
    if not peer_high:
        for peer in _CLOSEOUTS.values():
            if peer.state in TERMINAL_CLOSEOUT_STATES:
                continue
            if peer.correlation_id != correlation_id:
                continue
            if (peer.tenant_id or "") != tenant_norm:
                continue
            if _SEVERITY_RANK[peer.severity] >= 2:
                peer_high = True
                break
    if peer_high:
        level = max(level, 1)
        if force_high:
            level = max(level, 2)
    return _RANK_SEVERITY[level]


# -- Views (echo-safe Pydantic builds from the stored records) -----------------


def _step_view(stored: _StoredStep) -> RunbookStep:
    return RunbookStep(
        step_id=stored.step_id,
        closeout_id=stored.closeout_id,
        sequence_no=stored.sequence_no,
        step_kind=stored.step_kind,
        step_state=stored.step_state,
        display_status=stored.display_status,
        tenant_id=stored.tenant_id,
        correlation_id=stored.correlation_id,
        linked_action_id=stored.linked_action_id,
        linked_approval_id=stored.linked_approval_id,
        linked_execution_id=stored.linked_execution_id,
        linked_source_ref=stored.linked_source_ref,
        evidence_ref=stored.evidence_ref,
        summary_redacted=stored.summary_redacted,
        reason_redacted=stored.reason_redacted,
        source_status=stored.source_status,
        linked_execution_terminal=stored.linked_execution_terminal,
        linked_approval_resolved=stored.linked_approval_resolved,
        linked_execution_warning=stored.linked_execution_warning,
        dedup_key_digest=stored.dedup_key_digest,
        linked_task_id=stored.linked_task_id,
        created_at=stored.created_at,
        updated_at=stored.updated_at,
        redaction_applied=True,
    )


def _closeout_view(stored: _StoredCloseout) -> IncidentCloseout:
    return IncidentCloseout(
        closeout_id=stored.closeout_id,
        state=stored.state,
        display_status=stored.display_status,
        classification=stored.classification,
        severity=stored.severity,
        tenant_id=stored.tenant_id,
        actor_scope=stored.actor_scope,
        owner_role=stored.owner_role,
        owner_actor_id=stored.owner_actor_id,
        correlation_id=stored.correlation_id,
        flag_observed=stored.flag_observed,
        flag_ever_set=stored.flag_ever_set,
        linked_incident_id=stored.linked_incident_id,
        linked_triage_snapshot_ref=stored.linked_triage_snapshot_ref,
        linked_handoff_ref=stored.linked_handoff_ref,
        summary_redacted=stored.summary_redacted,
        reason_redacted=stored.reason_redacted,
        source_status=stored.source_status,
        linked_execution_warning=stored.linked_execution_warning,
        dedup_key_digest=stored.dedup_key_digest,
        ttl_expires_at=stored.ttl_expires_at,
        linked_followup_task_id=stored.linked_followup_task_id,
        followup_owed=stored.followup_owed,
        created_at=stored.created_at,
        updated_at=stored.updated_at,
        redaction_applied=True,
    )


# -- Audit emitters (one event per transition / step change; append-only) ------


def _emit_closeout_audit(
    stored: _StoredCloseout,
    *,
    transition: str,
    previous_state: str,
    next_state: str,
    actor_id: Optional[str],
    actor_role: str,
    reason_redacted: Optional[str] = None,
    denial_code: Optional[CloseoutDenialCode] = None,
) -> IncidentCloseoutAuditEvent:
    seq = _CLOSEOUT_AUDIT_SEQ.get(stored.closeout_id, 0) + 1
    _CLOSEOUT_AUDIT_SEQ[stored.closeout_id] = seq
    event = IncidentCloseoutAuditEvent(
        event_id=_uuid(),
        closeout_id=stored.closeout_id,
        state=next_state,  # the recorded state for this audit row
        actor_id=actor_id,
        actor_role=actor_role,  # type: ignore[arg-type]
        tenant_id=stored.tenant_id,
        transition=transition,
        previous_state=previous_state,  # type: ignore[arg-type]
        next_state=next_state,  # type: ignore[arg-type]
        flag_observed=stored.flag_observed,
        reason_redacted=_redact_optional(reason_redacted),
        denial_code=denial_code,
        correlation_id=stored.correlation_id,
        linked_incident_id=stored.linked_incident_id,
        linked_action_id=None,
        linked_approval_id=None,
        linked_execution_id=None,
        redaction_applied=True,
        sequence_no=seq,
        created_at=_now(),
    )
    _CLOSEOUT_AUDIT.append(event)
    return event


def _emit_step_audit(
    stored: _StoredStep,
    *,
    step_transition: str,
    previous_state: str,
    next_state: str,
    actor_id: Optional[str],
    actor_role: str,
    evidence_redacted: Optional[str] = None,
    denial_code: Optional[CloseoutDenialCode] = None,
) -> RunbookStepAuditEvent:
    seq = _STEP_AUDIT_SEQ.get(stored.step_id, 0) + 1
    _STEP_AUDIT_SEQ[stored.step_id] = seq
    event = RunbookStepAuditEvent(
        event_id=_uuid(),
        step_id=stored.step_id,
        closeout_id=stored.closeout_id,
        step_kind=stored.step_kind,
        step_transition=step_transition,
        previous_state=previous_state,  # type: ignore[arg-type]
        next_state=next_state,  # type: ignore[arg-type]
        actor_id=actor_id,
        actor_role=actor_role,  # type: ignore[arg-type]
        tenant_id=stored.tenant_id,
        evidence_redacted=_redact_optional(evidence_redacted),
        correlation_id=stored.correlation_id,
        linked_action_id=stored.linked_action_id,
        linked_approval_id=stored.linked_approval_id,
        linked_execution_id=stored.linked_execution_id,
        linked_source_ref=stored.linked_source_ref,
        redaction_applied=True,
        sequence_no=seq,
        created_at=_now(),
    )
    _STEP_AUDIT.append(event)
    return event


# -- P23 task materialization seam (executes nothing; P24 owns when owed) ------


def _materialize_followup_task(stored: _StoredCloseout) -> None:
    """Upsert an ``incident_followup_required`` P23 task while follow-up is owed
    (P24-A 5.2). Idempotent via the P23 dedup seam. Executes / approves / sends
    nothing. Stores the resulting task id on the closeout as a mirror.
    """
    event = OperatorTaskIntakeEvent(
        task_type="incident_followup_required",
        severity=stored.severity,
        tenant_id=stored.tenant_id,
        actor_scope=stored.actor_scope,
        owner_role=stored.owner_role,
        correlation_id=stored.correlation_id,
        linked_incident_id=stored.linked_incident_id,
        summary="Incident follow-up owed for closeout " + stored.closeout_id + ".",
        reason="Materialized by P24 closeout state=" + stored.state + ".",
        source_status=stored.source_status,
        linked_gate_open=False,
        followup_variant=stored.closeout_id,
        ttl_expires_at=stored.ttl_expires_at,
        channel=None,
    )
    result = _p23_upsert_task(event)
    stored.linked_followup_task_id = result.task.task_id
    stored.followup_owed = True
    stored.updated_at = _now()


def _resolve_followup_task(
    stored: _StoredCloseout,
    *,
    actor_id: Optional[str],
    actor_role: str,
    evidence: str,
) -> None:
    """Resolve the ``incident_followup_required`` P23 task when the follow-up is
    no longer owed (closeout left ``flagged_active`` / closed / withdrawn /
    expired) (P24-A 5.2). Completes the P23 task with redacted evidence; the task
    runs nothing. Idempotent: a no-op when no task is linked or it is terminal.
    """
    task_id = stored.linked_followup_task_id
    if not task_id:
        stored.followup_owed = False
        return
    if _p23_task_is_terminal(task_id):
        stored.followup_owed = False
        return
    payload = OperatorTaskTransitionRequest(reason="follow-up resolved via P24 closeout", evidence=evidence)
    _p23_complete_task(task_id, actor_id=actor_id, actor_role=actor_role, payload=payload)
    stored.followup_owed = False
    stored.updated_at = _now()


def _materialize_step_task(stored: _StoredStep, closeout_severity: str) -> None:
    """Upsert a ``runbook_step_required`` P23 task for an owed / in-progress /
    blocked step (P24-A 5.3). Idempotent via the P23 dedup seam. Executes nothing.
    """
    severity = "high" if (
        stored.step_kind == "action_pointer"
        and (stored.source_status == "unknown" or stored.linked_execution_warning)
    ) else closeout_severity
    event = OperatorTaskIntakeEvent(
        task_type="runbook_step_required",
        severity=severity,
        tenant_id=stored.tenant_id,
        actor_scope="tenant_contextual" if stored.tenant_id else "platform",
        owner_role=None,
        correlation_id=stored.correlation_id,
        linked_action_id=stored.linked_action_id,
        linked_approval_id=stored.linked_approval_id,
        linked_execution_id=stored.linked_execution_id,
        linked_source_ref=stored.linked_source_ref,
        linked_incident_id=None,
        summary="Runbook step " + stored.step_id + " (" + stored.step_kind + ") owed.",
        reason="Materialized by P24 step_state=" + stored.step_state + ".",
        source_status=stored.source_status,
        linked_gate_open=False,
        followup_variant=stored.step_id,
        channel=None,
    )
    result = _p23_upsert_task(event)
    stored.linked_task_id = result.task.task_id
    stored.updated_at = _now()


def _resolve_step_task(
    stored: _StoredStep,
    *,
    actor_id: Optional[str],
    actor_role: str,
    evidence: Optional[str],
    dismiss: bool = False,
) -> None:
    """Resolve the ``runbook_step_required`` P23 task when the step goes terminal
    (P24-A 5.3). Completes (or dismisses for not_applicable) the P23 task with
    redacted evidence; the task runs nothing. Idempotent.
    """
    task_id = stored.linked_task_id
    if not task_id or _p23_task_is_terminal(task_id):
        return
    note = evidence or ("step " + stored.step_state + " via P24")
    payload = OperatorTaskTransitionRequest(reason="runbook step resolved via P24", evidence=note)
    if dismiss:
        _p23_dismiss_task(task_id, actor_id=actor_id, actor_role=actor_role, payload=payload)
    else:
        _p23_complete_task(task_id, actor_id=actor_id, actor_role=actor_role, payload=payload)
    stored.updated_at = _now()


def _p23_task_is_terminal(task_id: str) -> bool:
    """True iff the linked P23 task is missing or in a terminal state.

    P24 tracks its own mirrors too, but consulting the real P23 store at the
    close gate proves the materialization seam stays intact and that closing
    requires an honestly terminal linked task (P24-A acceptance 6 / 21).
    """
    detail = _p23_read_task(task_id)
    if detail is None:
        return True
    return detail.state in TERMINAL_P23_STATES


# -- Closeout transitions (presentation-only; never execute / approve / flag) ---


def _set_closeout_state(stored: _StoredCloseout, target_state: str) -> None:
    stored.state = target_state
    stored.display_status = _compute_closeout_display(
        stored.state, stored.source_status, stored.linked_execution_warning
    )
    stored.updated_at = _now()


def _steps_for(closeout_id: str) -> list[_StoredStep]:
    order = _CLOSEOUT_STEP_ORDER.get(closeout_id, [])
    return [_STEPS[sid] for sid in order if sid in _STEPS]


def _transition_closeout(
    stored: _StoredCloseout,
    target_state: str,
    *,
    action: str,
    actor_id: Optional[str],
    actor_role: str,
    reason: Optional[str] = None,
) -> tuple[bool, Optional[CloseoutDenialCode], str, str]:
    """Core closeout state-machine step. Returns (accepted, denial_code, prev, next).

    Rejects: terminal source state, transition not in the allowed graph,
    ``flagged_active`` fabricated without an observed-true flag, ``closed`` with
    the flag still set / owed tasks non-terminal / source unknown / execution
    warning, ``awaiting_closeout`` with owed steps. A rejection changes no state;
    it is audited as a denied transition. Executes / approves / flags nothing.
    """
    previous_state = stored.state

    if previous_state in TERMINAL_CLOSEOUT_STATES:
        return False, "TRANSITION_DENIED_TERMINAL", previous_state, previous_state

    allowed = ALLOWED_CLOSEOUT_TRANSITIONS.get(previous_state, frozenset())
    if target_state not in allowed:
        return False, "TRANSITION_DENIED_INVALID", previous_state, previous_state

    # `flagged_active` may not be fabricated: it requires an observed-true flag
    # (P24-A 3.4 / C5). P24 set nothing; it only honors the mirror.
    if target_state == "flagged_active" and stored.flag_observed != "observed_true":
        return False, "TRANSITION_DENIED_INVALID", previous_state, previous_state

    steps = _steps_for(stored.closeout_id)
    owed_steps_open = any(s.step_state in ACTIVE_STEP_STATES for s in steps)

    # `awaiting_closeout` from in_remediation requires all owed steps terminal.
    if target_state == "awaiting_closeout" and owed_steps_open:
        return False, "CLOSE_DENIED_OWED_TASKS_NONTERMINAL", previous_state, previous_state

    if target_state == "closed":
        # All owed runbook steps must be terminal (P24-A 3.3 rule 4 / C4).
        if owed_steps_open:
            return False, "CLOSE_DENIED_OWED_TASKS_NONTERMINAL", previous_state, previous_state
        # If the flag was ever set, it must be observed cleared via P22 (C3).
        if stored.flag_ever_set and stored.flag_observed != "observed_false":
            return False, "CLOSE_DENIED_FLAG_STILL_SET", previous_state, previous_state
        # The owed incident follow-up task must be terminal (C4). Consult the
        # real P23 store to prove the seam.
        if stored.followup_owed and not _followup_task_terminal(stored):
            return False, "CLOSE_DENIED_OWED_TASKS_NONTERMINAL", previous_state, previous_state
        # source_unknown is never closed healthy (C9).
        if stored.source_status == "unknown":
            return False, "CLOSE_DENIED_SOURCE_UNKNOWN", previous_state, previous_state
        # backup_check_warning / completed_with_warning is never closed as success (C10).
        if stored.linked_execution_warning:
            return False, "CLOSE_DENIED_EXECUTION_WARNING", previous_state, previous_state

    # Apply the transition (no execution, no flag write, no approval).
    _set_closeout_state(stored, target_state)
    if reason:
        stored.reason_redacted = _redact_optional(reason)
    if target_state == "flagged_active" and stored.followup_owed is False and stored.flag_observed == "observed_true":
        # Follow-up is owed while the flag is observed set (P24-A 5.2).
        _materialize_followup_task(stored)
    if target_state in ("awaiting_closeout",) and stored.followup_owed:
        # Follow-up considered done once we are awaiting closeout after remediation.
        _resolve_followup_task(stored, actor_id=actor_id, actor_role=actor_role,
                               evidence="closeout advanced to awaiting_closeout")
    if target_state == "closed" and stored.followup_owed:
        _resolve_followup_task(stored, actor_id=actor_id, actor_role=actor_role,
                               evidence="closeout closed")
    if target_state in TERMINAL_CLOSEOUT_STATES:
        # A terminal closeout leaves the active dedup window so a recurrence
        # re-opens as a NEW closeout (P24-A 5.5).
        _ACTIVE_CLOSEOUT_DEDUP.pop(stored.dedup_key_digest, None)
        if stored.followup_owed:
            _resolve_followup_task(stored, actor_id=actor_id, actor_role=actor_role,
                                   evidence="closeout terminal")

    return True, None, previous_state, target_state


def _followup_task_terminal(stored: _StoredCloseout) -> bool:
    if not stored.linked_followup_task_id:
        return True
    return _p23_task_is_terminal(stored.linked_followup_task_id)


def apply_closeout_transition(
    closeout_id: str,
    *,
    target_state: str,
    actor_id: Optional[str],
    actor_role: str,
    reason: Optional[str] = None,
) -> tuple[Optional[IncidentCloseout], bool, Optional[CloseoutDenialCode], str, str]:
    """Apply an operator closeout judgment (P24-A 9 transition endpoint).

    Returns (closeout_view_or_None, accepted, denial_code, prev, next). Emits
    exactly one audit event (success or denial). Executes / approves / flags
    nothing.
    """
    stored = _CLOSEOUTS.get(closeout_id)
    if stored is None:
        return None, False, "CLOSEOUT_NOT_FOUND", "", ""

    previous_state = stored.state
    action = "closeout:" + target_state
    accepted, denial, _prev, _next = _transition_closeout(
        stored, target_state, action=action, actor_id=actor_id,
        actor_role=actor_role, reason=reason,
    )
    transition_label = (
        f"{previous_state}->{_next}" if accepted else f"denied:{action}"
    )
    _emit_closeout_audit(
        stored,
        transition=transition_label,
        previous_state=previous_state,
        next_state=stored.state,
        actor_id=actor_id,
        actor_role=actor_role,
        reason_redacted=reason,
        denial_code=denial,
    )
    return _closeout_view(stored), accepted, denial, previous_state, stored.state


# -- Step transitions (pointer-only; never execute / approve) ------------------


def _set_step_state(stored: _StoredStep, target_state: str) -> None:
    stored.step_state = target_state
    stored.display_status = _compute_step_display(
        stored.step_state, stored.source_status, stored.linked_execution_warning
    )
    stored.updated_at = _now()


def _transition_step(
    stored: _StoredStep,
    target_state: str,
    *,
    action: str,
    actor_id: Optional[str],
    actor_role: str,
    evidence: Optional[str] = None,
    reason: Optional[str] = None,
    closeout_severity: str = "medium",
) -> tuple[bool, Optional[CloseoutDenialCode], str, str]:
    """Core step state-machine step. Returns (accepted, denial_code, prev, next).

    Per-kind ``done`` gate (P24-A 4.1 / acceptance 9):
      - action_pointer: requires an observed terminal linked execution (C6 / C7);
        an approval alone is NOT execution.
      - approval_pointer: requires an observed resolved linked approval (C8).
      - observation: requires a redacted evidence note.
    A rejection changes no state; it is audited as a denied step transition.
    """
    previous_state = stored.step_state

    if previous_state in TERMINAL_STEP_STATES:
        return False, "TRANSITION_DENIED_TERMINAL", previous_state, previous_state

    allowed = ALLOWED_STEP_TRANSITIONS.get(previous_state, frozenset())
    if target_state not in allowed:
        return False, "TRANSITION_DENIED_INVALID", previous_state, previous_state

    if target_state == "done":
        if stored.step_kind == "action_pointer":
            if not stored.linked_execution_terminal:
                return False, "STEP_DONE_DENIED_GATE_OPEN", previous_state, previous_state
        elif stored.step_kind == "approval_pointer":
            if not stored.linked_approval_resolved:
                return False, "STEP_DONE_DENIED_GATE_OPEN", previous_state, previous_state
        else:  # observation
            if not (evidence and evidence.strip()):
                return False, "STEP_DONE_DENIED_NO_EVIDENCE", previous_state, previous_state

    _set_step_state(stored, target_state)
    if reason:
        stored.reason_redacted = _redact_optional(reason)
    if evidence and evidence.strip():
        # Store a one-way digest pointer; the redacted note itself lives in the
        # step audit event. Never the raw note on the row.
        stored.evidence_ref = "note:" + _digest(redact_text(evidence) or "")[:16]
    if target_state in ACTIVE_STEP_STATES:
        # (Re)materialize the runbook_step_required task while the step is still
        # owed / in-progress / blocked.
        _materialize_step_task(stored, closeout_severity)
    if target_state in TERMINAL_STEP_STATES:
        # Resolve the P23 task: completed for done, dismissed for not_applicable.
        _ACTIVE_STEP_DEDUP.pop(stored.dedup_key_digest, None)
        _resolve_step_task(
            stored, actor_id=actor_id, actor_role=actor_role,
            evidence=evidence, dismiss=(target_state == "not_applicable"),
        )

    return True, None, previous_state, target_state


def apply_step_transition(
    closeout_id: str,
    step_id: str,
    *,
    target_state: str,
    actor_id: Optional[str],
    actor_role: str,
    evidence: Optional[str] = None,
    reason: Optional[str] = None,
) -> tuple[Optional[RunbookStep], bool, Optional[CloseoutDenialCode], str, str]:
    """Apply a runbook step state change (P24-A 9 step-transition endpoint).

    Returns (step_view_or_None, accepted, denial_code, prev, next). Emits exactly
    one step audit event (success or denial). The step points; it runs nothing.
    """
    stored = _STEPS.get(step_id)
    if stored is None or stored.closeout_id != closeout_id:
        return None, False, "STEP_NOT_FOUND", "", ""

    closeout = _CLOSEOUTS.get(closeout_id)
    closeout_severity = closeout.severity if closeout else "medium"

    previous_state = stored.step_state
    action = "step:" + target_state
    accepted, denial, _prev, _next = _transition_step(
        stored, target_state, action=action, actor_id=actor_id,
        actor_role=actor_role, evidence=evidence, reason=reason,
        closeout_severity=closeout_severity,
    )
    step_transition_label = (
        f"{previous_state}->{stored.step_state}" if accepted else f"denied:{action}"
    )
    _emit_step_audit(
        stored,
        step_transition=step_transition_label,
        previous_state=previous_state,
        next_state=stored.step_state,
        actor_id=actor_id,
        actor_role=actor_role,
        evidence_redacted=evidence if accepted and target_state == "done" else reason,
        denial_code=denial,
    )
    return _step_view(stored), accepted, denial, previous_state, stored.step_state


# -- PUSH intake dispatcher (executes / approves / flags / sends nothing) ------


def _denied_intake(
    stored: _StoredCloseout,
    *,
    action: str,
    actor_id: Optional[str],
    actor_role: str,
    denial_code: CloseoutDenialCode,
    reason: Optional[str] = None,
) -> IncidentCloseoutIntakeResponse:
    """Record a denied intake-driven transition and return an audit-bearing response."""
    previous_state = stored.state
    _emit_closeout_audit(
        stored,
        transition=f"denied:{action}",
        previous_state=previous_state,
        next_state=previous_state,
        actor_id=actor_id,
        actor_role=actor_role,
        reason_redacted=reason,
        denial_code=denial_code,
    )
    return IncidentCloseoutIntakeResponse(
        closeout=_closeout_view(stored), step=None, created=False,
        deduped=False, accepted=False, denial_code=denial_code,
    )


def ingest_event(
    event: IncidentCloseoutIntakeEvent,
    *,
    actor_id: Optional[str],
    actor_role: str,
) -> IncidentCloseoutIntakeResponse:
    """Process one typed PUSH intake event (P24-A 5.1).

    Dispatches on ``event_type``. Accepts / dedups / advances the in-memory
    closeout / step view and upserts P23 tasks through the seam. Executes,
    approves, flags, and sends nothing. The actor is the authenticated token
    (passed in by the route); it is never read from the event body (C22).
    """
    et = event.event_type

    if et == "incident_detected":
        return _ingest_incident_detected(event, actor_id=actor_id, actor_role=actor_role)

    # All other event types address an existing closeout.
    closeout_id = event.closeout_id
    if not closeout_id:
        # Nothing to address; surface a not-found denial without a row.
        return IncidentCloseoutIntakeResponse(
            closeout=_phantom_closeout(event), step=None, created=False,
            deduped=False, accepted=False, denial_code="CLOSEOUT_NOT_FOUND",
        )
    stored = _CLOSEOUTS.get(closeout_id)
    if stored is None:
        return IncidentCloseoutIntakeResponse(
            closeout=_phantom_closeout(event), step=None, created=False,
            deduped=False, accepted=False, denial_code="CLOSEOUT_NOT_FOUND",
        )

    if et == "incident_classified":
        return _ingest_incident_classified(stored, event, actor_id=actor_id, actor_role=actor_role)
    if et == "incident_flag_observed":
        return _ingest_incident_flag_observed(stored, event, actor_id=actor_id, actor_role=actor_role)
    if et == "closeout_transition":
        return _ingest_closeout_transition(stored, event, actor_id=actor_id, actor_role=actor_role)
    if et in ("runbook_step_owed", "runbook_step_progress", "runbook_step_terminal"):
        return _ingest_runbook_step(stored, event, actor_id=actor_id, actor_role=actor_role)

    # Unreachable (schema closes the event_type set), but kept honest / explicit.
    return _denied_intake(
        stored, action="intake:" + str(et), actor_id=actor_id,
        actor_role=actor_role, denial_code="TRANSITION_DENIED_INVALID",
        reason=event.summary,
    )


def _phantom_closeout(event: IncidentCloseoutIntakeEvent) -> IncidentCloseout:
    """A not-found placeholder view (no stored row to echo)."""
    now = _now()
    return IncidentCloseout(
        closeout_id=event.closeout_id or "[not-found]",
        state="detected",
        display_status="none",
        classification=event.classification,
        severity=event.severity or "medium",
        tenant_id=event.tenant_id,
        actor_scope=event.actor_scope,
        owner_role=event.owner_role,
        owner_actor_id=None,
        correlation_id=event.correlation_id,
        flag_observed=event.flag_observed or "observed_unknown",
        flag_ever_set=False,
        linked_incident_id=event.linked_incident_id,
        linked_triage_snapshot_ref=event.linked_triage_snapshot_ref,
        linked_handoff_ref=event.linked_handoff_ref,
        summary_redacted="[not-found]",
        reason_redacted=_redact_optional(event.reason),
        source_status=event.source_status,
        linked_execution_warning=bool(event.linked_execution_warning),
        dedup_key_digest="",
        ttl_expires_at=event.ttl_expires_at,
        linked_followup_task_id=None,
        followup_owed=False,
        created_at=now,
        updated_at=now,
        redaction_applied=True,
    )


def _ingest_incident_detected(
    event: IncidentCloseoutIntakeEvent,
    *,
    actor_id: Optional[str],
    actor_role: str,
) -> IncidentCloseoutIntakeResponse:
    """incident_detected -- open a closeout at ``detected`` (P24-A 5.1).

    Dedups on (correlation_id, tenant_id, linked_incident_id) over ACTIVE
    closeouts: a repeat event for the same active incident bumps updated_at and
    is an idempotent replay (P24-A 5.5 / C19).
    """
    digest = _closeout_dedup_digest(
        event.correlation_id, event.tenant_id, event.linked_incident_id
    )
    existing_id = _ACTIVE_CLOSEOUT_DEDUP.get(digest)
    if existing_id and existing_id in _CLOSEOUTS:
        stored = _CLOSEOUTS[existing_id]
        stored.updated_at = _now()
        if event.reason:
            stored.reason_redacted = _redact_optional(event.reason)
        _emit_closeout_audit(
            stored,
            transition="replayed:incident_detected",
            previous_state=stored.state,
            next_state=stored.state,
            actor_id=actor_id,
            actor_role=actor_role,
            reason_redacted=event.summary,
        )
        return IncidentCloseoutIntakeResponse(
            closeout=_closeout_view(stored), step=None, created=False,
            deduped=True, accepted=True, denial_code=None,
        )

    flag_observed = event.flag_observed or "observed_unknown"
    source_status = event.source_status
    linked_warning = bool(event.linked_execution_warning)
    severity = _severity_for(
        event.severity, source_status, linked_warning,
        event.correlation_id, event.tenant_id,
    )
    now = _now()
    stored = _StoredCloseout(
        closeout_id=event.closeout_id or _uuid(),
        state="detected",
        display_status=_compute_closeout_display("detected", source_status, linked_warning),
        classification=event.classification,
        severity=severity,
        tenant_id=event.tenant_id,
        actor_scope=event.actor_scope,
        owner_role=event.owner_role,
        owner_actor_id=None,
        correlation_id=event.correlation_id,
        flag_observed=flag_observed,
        flag_ever_set=(flag_observed == "observed_true"),
        linked_incident_id=event.linked_incident_id,
        linked_triage_snapshot_ref=event.linked_triage_snapshot_ref,
        linked_handoff_ref=event.linked_handoff_ref,
        summary_redacted=redact_text(event.summary) or "[suppressed:non-safe-summary]",
        reason_redacted=_redact_optional(event.reason),
        source_status=source_status,
        linked_execution_warning=linked_warning,
        dedup_key_digest=digest,
        ttl_expires_at=event.ttl_expires_at,
        linked_followup_task_id=None,
        followup_owed=False,
        created_at=now,
        updated_at=now,
        redaction_applied=True,
    )
    _CLOSEOUTS[stored.closeout_id] = stored
    _CLOSEOUT_STEP_ORDER[stored.closeout_id] = []
    _ACTIVE_CLOSEOUT_DEDUP[digest] = stored.closeout_id
    _CLOSEOUT_AUDIT_SEQ[stored.closeout_id] = 0
    _emit_closeout_audit(
        stored,
        transition="materialized:detected",
        previous_state="detected",
        next_state="detected",
        actor_id=actor_id,
        actor_role=actor_role,
        reason_redacted=event.summary,
    )
    return IncidentCloseoutIntakeResponse(
        closeout=_closeout_view(stored), step=None, created=True,
        deduped=False, accepted=True, denial_code=None,
    )


def _ingest_incident_classified(
    stored: _StoredCloseout,
    event: IncidentCloseoutIntakeEvent,
    *,
    actor_id: Optional[str],
    actor_role: str,
) -> IncidentCloseoutIntakeResponse:
    """incident_classified -- advance detected -> triaged (P24-A 5.1)."""
    if event.classification:
        stored.classification = event.classification
    accepted, denial, prev, nxt = _transition_closeout(
        stored, "triaged", action="intake:classify",
        actor_id=actor_id, actor_role=actor_role, reason=event.reason,
    )
    _emit_closeout_audit(
        stored,
        transition=(f"{prev}->{nxt}" if accepted else "denied:intake:classify"),
        previous_state=prev,
        next_state=stored.state,
        actor_id=actor_id,
        actor_role=actor_role,
        reason_redacted=event.reason,
        denial_code=denial,
    )
    return IncidentCloseoutIntakeResponse(
        closeout=_closeout_view(stored), step=None, created=False,
        deduped=False, accepted=accepted, denial_code=denial,
    )


def _ingest_incident_flag_observed(
    stored: _StoredCloseout,
    event: IncidentCloseoutIntakeEvent,
    *,
    actor_id: Optional[str],
    actor_role: str,
) -> IncidentCloseoutIntakeResponse:
    """incident_flag_observed -- MIRROR the P17 flag (P24-A 5.1 / 3.3 rule 2).

    P24 writes nothing to P17. It records the observed flag value and, if the
    graph + gate permit, advances the lifecycle:
      - observed_true  -> flagged_active (from triaged / in_remediation);
        the follow-up task is materialized.
      - observed_false on a flagged_active closeout -> awaiting_closeout (the
        follow-up is resolved; close still needs operator judgment).
    Other observations update the mirror only.
    """
    if event.flag_observed:
        stored.flag_observed = event.flag_observed
        if event.flag_observed == "observed_true":
            stored.flag_ever_set = True
    prev = stored.state
    accepted = True
    denial: Optional[CloseoutDenialCode] = None
    action = "intake:flag_observed"

    target: Optional[str] = None
    if stored.flag_observed == "observed_true" and prev in ("triaged", "in_remediation"):
        target = "flagged_active"
    elif stored.flag_observed == "observed_false" and prev == "flagged_active":
        target = "awaiting_closeout"

    if target is not None:
        accepted, denial, _p, _n = _transition_closeout(
            stored, target, action=action, actor_id=actor_id,
            actor_role=actor_role, reason=event.reason,
        )
        label = f"{prev}->{stored.state}" if accepted else f"denied:{action}"
    else:
        stored.updated_at = _now()
        label = "mirrored:flag_observed"

    if event.reason:
        stored.reason_redacted = _redact_optional(event.reason)
    _emit_closeout_audit(
        stored,
        transition=label,
        previous_state=prev,
        next_state=stored.state,
        actor_id=actor_id,
        actor_role=actor_role,
        reason_redacted=event.reason,
        denial_code=denial,
    )
    return IncidentCloseoutIntakeResponse(
        closeout=_closeout_view(stored), step=None, created=False,
        deduped=False, accepted=accepted, denial_code=denial,
    )


def _ingest_closeout_transition(
    stored: _StoredCloseout,
    event: IncidentCloseoutIntakeEvent,
    *,
    actor_id: Optional[str],
    actor_role: str,
) -> IncidentCloseoutIntakeResponse:
    """closeout_transition -- operator judgment via intake (P24-A 5.1).

    The operator target_state is honored subject to the transition rules. This
    is the PUSH twin of the ``.../transition`` endpoint.
    """
    target = event.target_state
    if target is None:
        return _denied_intake(
            stored, action="intake:closeout_transition", actor_id=actor_id,
            actor_role=actor_role, denial_code="TRANSITION_DENIED_INVALID",
            reason=event.reason,
        )
    view, accepted, denial, prev, nxt = apply_closeout_transition(
        stored.closeout_id, target_state=target,
        actor_id=actor_id, actor_role=actor_role, reason=event.reason,
    )
    return IncidentCloseoutIntakeResponse(
        closeout=view or _closeout_view(stored), step=None, created=False,
        deduped=False, accepted=accepted, denial_code=denial,
    )


def _ingest_runbook_step(
    stored: _StoredCloseout,
    event: IncidentCloseoutIntakeEvent,
    *,
    actor_id: Optional[str],
    actor_role: str,
) -> IncidentCloseoutIntakeResponse:
    """runbook_step_owed / _progress / _terminal -- runbook step changes (P24-A 5.1)."""
    et = event.event_type
    step_kind = event.step_kind or "observation"

    if et == "runbook_step_owed":
        seq = event.sequence_no if event.sequence_no is not None else _next_sequence(stored.closeout_id)
        digest = _step_dedup_digest(stored.closeout_id, seq, step_kind, event.tenant_id)
        existing_id = _ACTIVE_STEP_DEDUP.get(digest)
        if existing_id and existing_id in _STEPS:
            step = _STEPS[existing_id]
            step.updated_at = _now()
            _emit_step_audit(
                step,
                step_transition="replayed:runbook_step_owed",
                previous_state=step.step_state,
                next_state=step.step_state,
                actor_id=actor_id,
                actor_role=actor_role,
                evidence_redacted=event.summary,
            )
            return IncidentCloseoutIntakeResponse(
                closeout=_closeout_view(stored), step=_step_view(step),
                created=False, deduped=True, accepted=True, denial_code=None,
            )
        step = _new_step(stored, event, step_kind=step_kind, sequence_no=seq, digest=digest)
        # A newly-owed step on a triaged / flagged_active / in_remediation
        # closeout derives the closeout into in_remediation when appropriate.
        _maybe_enter_remediation(stored, actor_id=actor_id, actor_role=actor_role)
        _materialize_step_task(step, stored.severity)
        _emit_step_audit(
            step,
            step_transition="materialized:owed",
            previous_state="owed",
            next_state="owed",
            actor_id=actor_id,
            actor_role=actor_role,
            evidence_redacted=event.summary,
        )
        return IncidentCloseoutIntakeResponse(
            closeout=_closeout_view(stored), step=_step_view(step),
            created=False, deduped=False, accepted=True, denial_code=None,
        )

    # runbook_step_progress / _terminal address an existing step.
    step_id = event.step_id
    if not step_id:
        return _denied_intake(
            stored, action="intake:" + str(et), actor_id=actor_id,
            actor_role=actor_role, denial_code="STEP_NOT_FOUND", reason=event.summary,
        )
    step = _STEPS.get(step_id)
    if step is None or step.closeout_id != stored.closeout_id:
        return _denied_intake(
            stored, action="intake:" + str(et), actor_id=actor_id,
            actor_role=actor_role, denial_code="STEP_NOT_FOUND", reason=event.summary,
        )

    # Refresh observed-state mirrors carried on this event (P24 writes nothing
    # upstream; these are observations only).
    if event.source_status is not None:
        step.source_status = event.source_status
    if event.linked_execution_terminal is not None:
        step.linked_execution_terminal = bool(event.linked_execution_terminal)
    if event.linked_approval_resolved is not None:
        step.linked_approval_resolved = bool(event.linked_approval_resolved)
    if event.linked_execution_warning is not None:
        step.linked_execution_warning = bool(event.linked_execution_warning)
    step.display_status = _compute_step_display(
        step.step_state, step.source_status, step.linked_execution_warning
    )

    if et == "runbook_step_progress":
        target = "in_progress"
        evidence = None
    else:  # runbook_step_terminal
        target = "done"  # default honest terminal; operator may re-target via the step endpoint
        evidence = event.evidence

    view, accepted, denial, prev, nxt = apply_step_transition(
        stored.closeout_id, step_id, target_state=target,
        actor_id=actor_id, actor_role=actor_role,
        evidence=evidence, reason=event.reason,
    )
    # If a terminal-via-intake could not honor `done` (e.g. gate open), keep the
    # step where it is; the denial is audited inside apply_step_transition.
    return IncidentCloseoutIntakeResponse(
        closeout=_closeout_view(stored), step=view,
        created=False, deduped=False, accepted=accepted, denial_code=denial,
    )


def _next_sequence(closeout_id: str) -> int:
    order = _CLOSEOUT_STEP_ORDER.get(closeout_id, [])
    return len(order) + 1


def _new_step(
    stored: _StoredCloseout,
    event: IncidentCloseoutIntakeEvent,
    *,
    step_kind: str,
    sequence_no: int,
    digest: str,
) -> _StoredStep:
    now = _now()
    source_status = event.source_status
    linked_warning = bool(event.linked_execution_warning)
    step = _StoredStep(
        step_id=event.step_id or _uuid(),
        closeout_id=stored.closeout_id,
        sequence_no=sequence_no,
        step_kind=step_kind,
        step_state="owed",
        display_status=_compute_step_display("owed", source_status, linked_warning),
        tenant_id=stored.tenant_id,
        correlation_id=stored.correlation_id,
        linked_action_id=event.linked_action_id,
        linked_approval_id=event.linked_approval_id,
        linked_execution_id=event.linked_execution_id,
        linked_source_ref=event.linked_source_ref,
        evidence_ref=None,
        summary_redacted=redact_text(event.summary) or "[suppressed:non-safe-summary]",
        reason_redacted=_redact_optional(event.reason),
        source_status=source_status,
        linked_execution_terminal=bool(event.linked_execution_terminal),
        linked_approval_resolved=bool(event.linked_approval_resolved),
        linked_execution_warning=linked_warning,
        dedup_key_digest=digest,
        linked_task_id=None,
        created_at=now,
        updated_at=now,
        redaction_applied=True,
    )
    _STEPS[step.step_id] = step
    order = _CLOSEOUT_STEP_ORDER.setdefault(stored.closeout_id, [])
    order.append(step.step_id)
    _ACTIVE_STEP_DEDUP[digest] = step.step_id
    _STEP_AUDIT_SEQ[step.step_id] = 0
    return step


def _maybe_enter_remediation(
    stored: _StoredCloseout,
    *,
    actor_id: Optional[str],
    actor_role: str,
) -> None:
    """Derive a triaged / flagged_active closeout into in_remediation when a step
    is owed (P24-A 3.1). Records a transition audit if it moves. Executes nothing.
    """
    if stored.state not in ("triaged", "flagged_active"):
        return
    prev = stored.state
    accepted, denial, _p, _n = _transition_closeout(
        stored, "in_remediation", action="intake:runbook_step_owed",
        actor_id=actor_id, actor_role=actor_role,
    )
    if accepted:
        _emit_closeout_audit(
            stored,
            transition=f"{prev}->in_remediation",
            previous_state=prev,
            next_state=stored.state,
            actor_id=actor_id,
            actor_role=actor_role,
        )


# -- Read / list ---------------------------------------------------------------


def list_closeouts(
    *,
    limit: int = 50,
    offset: int = 0,
    state: Optional[str] = None,
    classification: Optional[str] = None,
    severity: Optional[str] = None,
    tenant_id: Optional[str] = None,
    flag_observed: Optional[str] = None,
    owner_actor_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> IncidentCloseoutList:
    """List closeouts with filters, ranked by severity DESC then recency. Read-only."""
    items = list(_CLOSEOUTS.values())
    if state is not None:
        items = [c for c in items if c.state == state]
    if classification is not None:
        items = [c for c in items if c.classification == classification]
    if severity is not None:
        items = [c for c in items if c.severity == severity]
    if tenant_id is not None:
        items = [c for c in items if (c.tenant_id or "") == tenant_id]
    if flag_observed is not None:
        items = [c for c in items if c.flag_observed == flag_observed]
    if owner_actor_id is not None:
        items = [c for c in items if (c.owner_actor_id or "") == owner_actor_id]
    if correlation_id is not None:
        items = [c for c in items if c.correlation_id == correlation_id]

    total = len(items)
    active_count = sum(1 for c in items if c.state in ACTIVE_CLOSEOUT_STATES)
    items.sort(key=lambda c: (-_SEVERITY_RANK[c.severity], c.created_at))
    page = items[offset : offset + limit]
    return IncidentCloseoutList(
        closeouts=[_closeout_view(c) for c in page],
        total=total,
        active_count=active_count,
        limit=limit,
        offset=offset,
    )


def read_closeout(closeout_id: str) -> Optional[IncidentCloseoutDetail]:
    """Read one closeout's redacted record, full audit history, and runbook steps.

    Returns None when missing. withdrawn / expired closeouts retain their full
    audit history and steps here (the closeout is a view, not the system of
    record; P24-A acceptance 11 / C11).
    """
    stored = _CLOSEOUTS.get(closeout_id)
    if stored is None:
        return None
    steps = [_step_view(_STEPS[sid]) for sid in _CLOSEOUT_STEP_ORDER.get(closeout_id, []) if sid in _STEPS]
    detail = IncidentCloseoutDetail(
        **_closeout_view(stored).model_dump(),
        audit_events=closeout_audit_log_for(closeout_id),
        steps=steps,
    )
    return detail


def read_runbook(closeout_id: str) -> Optional[RunbookView]:
    """Read the ordered runbook steps for one closeout. Read-only."""
    if closeout_id not in _CLOSEOUTS:
        return None
    steps = [_step_view(_STEPS[sid]) for sid in _CLOSEOUT_STEP_ORDER.get(closeout_id, []) if sid in _STEPS]
    return RunbookView(closeout_id=closeout_id, steps=steps)


def self_assign_closeout(
    closeout_id: str,
    *,
    actor_id: Optional[str],
    actor_role: str,
) -> tuple[Optional[IncidentCloseout], bool, Optional[CloseoutDenialCode]]:
    """Set owner_actor_id / owner_role to the authenticated operator (P24-A 8.2).

    Owner is PRESENTATION only (not authorization). Does not change the closeout
    state and runs nothing; records a self_assigned audit event. An operator may
    self-assign only closeouts already visible to them (the route guard enforces
    visibility); owner grants no new privilege (P24-A acceptance 16 / C26).
    """
    stored = _CLOSEOUTS.get(closeout_id)
    if stored is None:
        return None, False, "CLOSEOUT_NOT_FOUND"
    prev = stored.state
    if prev in TERMINAL_CLOSEOUT_STATES:
        _emit_closeout_audit(
            stored,
            transition="denied:self_assign",
            previous_state=prev,
            next_state=prev,
            actor_id=actor_id,
            actor_role=actor_role,
            denial_code="TRANSITION_DENIED_TERMINAL",
        )
        return _closeout_view(stored), False, "TRANSITION_DENIED_TERMINAL"
    stored.owner_actor_id = actor_id
    if actor_role in ("super_admin", "engineering_operator", "support_operator"):
        stored.owner_role = actor_role  # type: ignore[assignment]
    stored.updated_at = _now()
    _emit_closeout_audit(
        stored,
        transition="self_assigned",
        previous_state=prev,
        next_state=prev,
        actor_id=actor_id,
        actor_role=actor_role,
    )
    return _closeout_view(stored), True, None


__all__ = [
    "reset_store",
    "closeout_audit_log",
    "closeout_audit_log_for",
    "step_audit_log",
    "step_audit_log_for",
    "ingest_event",
    "apply_closeout_transition",
    "apply_step_transition",
    "self_assign_closeout",
    "list_closeouts",
    "read_closeout",
    "read_runbook",
]


# Static import-time guards: keep the denial vocabulary closed and the
# non-execution marker discoverable.
assert all(code in DENIAL_CODES for code in CloseoutDenialCode.__args__)  # type: ignore[attr-defined]
assert _FORCE_HIGH is True
