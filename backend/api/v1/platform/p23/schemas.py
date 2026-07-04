"""Pydantic schemas for P23 Operator Task / Notification Queue (P23-B skeleton).

Field-for-field aligned to
docs/ai/PLATFORM_PRODUCT_P23_OPERATOR_TASK_NOTIFICATION_QUEUE_CONTRACT.md (P23-A).

This is a NON-EXECUTING, NON-SENDING, IN-MEMORY backend skeleton. It materializes
prior-phase events into a deduplicated, severity-ranked queue of operator tasks,
runs a presentation-only state machine over them, and records notification EVENTS
(records of attention). It NEVER executes a P22 action, NEVER approves a P19/P20/P21
approval, NEVER mutates a P17 registry field, NEVER delivers a notification, NEVER
dispatches a worker / scheduler / drain loop, NEVER runs shell / SQL / script, and
NEVER mutates tenant business / payment / billing / product data.

Contract rules carried from P10 / P17 / P18 / P19 / P20 / P21 / P22 / P23-A:
  - The task type catalog is EXACTLY the ten defined types (section 3.1); every
    excluded item (product business, tenant payload, synthetic execution,
    auto-approval, cross-tenant broadcast, channel delivery) has no P23 path.
  - The task state machine has EXACTLY the nine defined states (section 4.1) and
    enforces the allowed / forbidden transitions; terminal states accept no exit;
    completion requires evidence and a closed linked gate.
  - A task is a view, not an executor. A notification is a record, not a delivery.
  - source_unknown is never displayed healthy; backup_check_warning is never
    displayed as success (the computed display_status enforces this in every state).
  - Redaction is total: every free-text field passes through the P23 content
    redactor; no secret / DSN / host / port / token / cookie / auth header / raw
    body / shell / SQL / script / tenant business payload is ever stored, returned,
    or audited.
  - extra="forbid" on every model (no undeclared fields / leaks).
  - No tenant business records; tenant_id is a scoped identifier only.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# -- Closed vocabularies (P23-A section 3.1 / 4.1 / 5 / 6 / 10) ----------------

#: The closed task type catalog (P23-A 3.1). A task_type not in this set has no
#: P23 path, regardless of what event triggered it. Exactly ten types.
TASK_TYPES: tuple[str, ...] = (
    "action_request_created",
    "approval_pending",
    "approval_decision_required",
    "execution_ready",
    "execution_completed",
    "execution_failed",
    "source_unknown",
    "backup_check_warning",
    "incident_followup_required",
    "runbook_step_required",
)

#: The closed task state set (P23-A 4.1). Exactly nine states.
TASK_STATES: tuple[str, ...] = (
    "open",
    "acknowledged",
    "in_progress",
    "waiting_on_approval",
    "waiting_on_source",
    "completed",
    "dismissed",
    "expired",
    "failed",
)

#: Terminal states accept no outgoing transition (P23-A 4.1 / 4.3 / 4.4).
TERMINAL_STATES: frozenset[str] = frozenset(
    {"completed", "dismissed", "expired", "failed"}
)

#: Active (non-terminal) states. Dedup collapses repeat events into one ACTIVE task;
#: terminal tasks are exempt from dedup so a recurring follow-up re-opens as a new
#: task (P23-A 5.4 / 11.2).
ACTIVE_STATES: frozenset[str] = frozenset(
    {"open", "acknowledged", "in_progress", "waiting_on_approval", "waiting_on_source"}
)

#: Three severity levels. No `critical` auto-execute tier (P23-A 11.1).
SEVERITIES: tuple[str, ...] = ("low", "medium", "high")

#: Visibility scope at which a task is shown (P23-A 5.1).
ACTOR_SCOPES: tuple[str, ...] = ("platform", "tenant_contextual")

#: Source-status mirror of the linked P17 / P18 source (P23-A 5.1). Never fabricated
#: healthy: `unknown` is never healthy (P10 / P17 / P22 rule, carried into P23).
SOURCE_STATUSES: tuple[str, ...] = ("known", "unknown", "degraded")

#: Suggested owner roles (PRESENTATION ONLY; not authorization) (P23-A 3.1 / 5.1).
OWNER_ROLES: tuple[str, ...] = ("super_admin", "engineering_operator", "support_operator")

#: Audit actor roles (P23-A 10.1). The operator is identity-only platform-operator;
#: `system` covers TTL / sweep (not implemented in P23-B, but reserved).
AUDIT_ACTOR_ROLES: tuple[str, ...] = (
    "super_admin",
    "engineering_operator",
    "support_operator",
    "system",
)

#: Planned notification channels (P23-A 5.2 / 6). P23-B wires NO channel; the enum
#: is defined for contract fidelity only.
NOTIFICATION_CHANNELS: tuple[str, ...] = ("in_app", "email", "webhook")

#: Notification delivery state (P23-A 5.2). P23-B only ever produces `recorded`
#: (a normal record of attention) or `suppressed` (a record whose redacted summary
#: could not be made safe to even record as a delivery candidate). It NEVER produces
#: queued_for_delivery / delivered / failed_delivery -- those require a channel that
#: P23-B does not implement.
NOTIFICATION_DELIVERY_STATES: tuple[str, ...] = (
    "recorded",
    "queued_for_delivery",
    "delivered",
    "failed_delivery",
    "suppressed",
)

#: The honest display label (P23-A 4.2 / 6.3 / 12.7 / 12.8). Computed by the service
#: from task_type + source_status + state; NEVER overridable to healthy / success for
#: source_unknown / backup_check_warning.
DISPLAY_STATUSES: tuple[str, ...] = (
    "healthy",
    "warning",
    "unknown",
    "failed",
    "completed",
    "dismissed",
    "none",
)


# -- State machine (P23-A section 4.1) ----------------------------------------

#: Allowed transitions. A transition not listed here is rejected. Terminal states
#: have no outgoing edges. This is a PRESENTATION / TRIAGE lifecycle only; no
#: transition executes a controlled action (P23-A 4.3).
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "open": frozenset(
        {
            "acknowledged",
            "in_progress",
            "waiting_on_approval",
            "waiting_on_source",
            "dismissed",
            "expired",
            "failed",
            "completed",
        }
    ),
    "acknowledged": frozenset(
        {
            "in_progress",
            "waiting_on_approval",
            "waiting_on_source",
            "completed",
            "dismissed",
            "expired",
        }
    ),
    "in_progress": frozenset(
        {
            "waiting_on_approval",
            "waiting_on_source",
            "completed",
            "failed",
            "dismissed",
        }
    ),
    "waiting_on_approval": frozenset(
        {"acknowledged", "in_progress", "expired", "failed"}
    ),
    "waiting_on_source": frozenset(
        {"acknowledged", "in_progress", "expired", "failed"}
    ),
    "completed": frozenset(),
    "dismissed": frozenset(),
    "expired": frozenset(),
    "failed": frozenset(),
}

#: Default severity per task type (P23-A 3.1). Correlation may raise, never lower.
DEFAULT_SEVERITY: dict[str, str] = {
    "action_request_created": "low",
    "approval_pending": "medium",
    "approval_decision_required": "high",
    "execution_ready": "high",
    "execution_completed": "low",
    "execution_failed": "high",
    "source_unknown": "high",
    "backup_check_warning": "high",
    "incident_followup_required": "medium",
    "runbook_step_required": "medium",
}

#: Task types that force `display_status` away from healthy regardless of state
#: (P23-A 12.7 / 12.8, C4 / C5).
NEVER_HEALTHY_TYPES: frozenset[str] = frozenset({"source_unknown"})
NEVER_SUCCESS_TYPES: frozenset[str] = frozenset({"backup_check_warning"})


#: Closed denial-code set for rejected transitions (P23-A 4.4 / 10.2). Denials are
#: recorded as denied audit events; they change no state.
DENIAL_CODES: tuple[str, ...] = (
    "TRANSITION_DENIED_INVALID",
    "TRANSITION_DENIED_TERMINAL",
    "COMPLETE_DENIED_NO_EVIDENCE",
    "COMPLETE_DENIED_GATE_OPEN",
    "TASK_NOT_FOUND",
)

TransitionDenialCode = Literal[
    "TRANSITION_DENIED_INVALID",
    "TRANSITION_DENIED_TERMINAL",
    "COMPLETE_DENIED_NO_EVIDENCE",
    "COMPLETE_DENIED_GATE_OPEN",
    "TASK_NOT_FOUND",
]


# -- Pydantic Literal mirrors (closed sets enforced at the schema layer) -------

TaskType = Literal[
    "action_request_created",
    "approval_pending",
    "approval_decision_required",
    "execution_ready",
    "execution_completed",
    "execution_failed",
    "source_unknown",
    "backup_check_warning",
    "incident_followup_required",
    "runbook_step_required",
]

TaskState = Literal[
    "open",
    "acknowledged",
    "in_progress",
    "waiting_on_approval",
    "waiting_on_source",
    "completed",
    "dismissed",
    "expired",
    "failed",
]

Severity = Literal["low", "medium", "high"]
ActorScope = Literal["platform", "tenant_contextual"]
SourceStatus = Literal["known", "unknown", "degraded"]
OwnerRole = Literal["super_admin", "engineering_operator", "support_operator"]
AuditActorRole = Literal[
    "super_admin", "engineering_operator", "support_operator", "system"
]
NotificationChannel = Literal["in_app", "email", "webhook"]
NotificationDeliveryState = Literal[
    "recorded",
    "queued_for_delivery",
    "delivered",
    "failed_delivery",
    "suppressed",
]
DisplayStatus = Literal[
    "healthy", "warning", "unknown", "failed", "completed", "dismissed", "none"
]


# -- Models (all extra="forbid") ----------------------------------------------


class OperatorTaskAuditEvent(BaseModel):
    """One task state-change audit event (P23-A 10.1). Append-only; never deleted.

    A denied transition is recorded with ``transition == "denied:<action>"``,
    ``next_state == previous_state`` (no change), and a ``denial_code``.
    """

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(..., description="PK. Unique per audit event.")
    task_id: str = Field(..., description="The task whose state changed.")
    task_type: TaskType
    actor_id: Optional[str] = Field(
        None, description="The operator (or None for the system / operator-secret path)."
    )
    actor_role: AuditActorRole
    tenant_id: Optional[str] = Field(None, description="Scoped id only; never a business payload.")
    transition: str = Field(
        ..., description="e.g. open->acknowledged, in_progress->completed, denied:complete."
    )
    previous_state: TaskState
    next_state: TaskState
    reason_redacted: Optional[str] = Field(
        None, description="Redacted reason / evidence note. P23 allowlist applied."
    )
    denial_code: Optional[TransitionDenialCode] = Field(
        None, description="Set iff this is a denied (no-op) transition record."
    )
    correlation_id: str
    linked_action_id: Optional[str] = None
    linked_approval_id: Optional[str] = None
    linked_execution_id: Optional[str] = None
    linked_source_ref: Optional[str] = None
    linked_incident_id: Optional[str] = None
    redaction_applied: bool = Field(True, description="Always true; redaction is total.")
    sequence_no: int = Field(..., description="Monotonic per-task sequence.")
    created_at: datetime = Field(..., description="UTC ISO-8601.")


class OperatorNotificationEvent(BaseModel):
    """A record of attention (P23-A 5.2 / 6). NOT a delivery.

    P23-B only ever produces ``delivery_state == recorded`` (or ``suppressed``).
    It resolves no recipient address and sends nothing on any channel.
    """

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(..., description="PK. Unique per notification event.")
    task_id: str = Field(..., description="-> platform_operator_task.task_id.")
    channel: NotificationChannel = Field(
        ..., description="Planned channel. P23-B wires none; the field is a record label."
    )
    delivery_state: NotificationDeliveryState = Field(
        ..., description="recorded | suppressed in P23-B. Never delivered."
    )
    severity: Severity
    tenant_id: Optional[str] = Field(None, description="Scoped id only.")
    actor_scope: ActorScope
    recipient_role: Optional[OwnerRole] = Field(
        None, description="Role hint; P23-B resolves no address."
    )
    summary_redacted: str = Field(
        ..., description="Redacted one-line summary. Never a secret / DSN / host / port."
    )
    correlation_id: str
    redaction_applied: bool = Field(True, description="Always true; redaction is total.")
    created_at: datetime = Field(..., description="UTC ISO-8601.")


class _TaskRecord(BaseModel):
    """Shared task fields (P23-A 5.1). All free-text fields are redacted."""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    task_type: TaskType
    severity: Severity
    state: TaskState
    display_status: DisplayStatus = Field(
        ..., description="Computed honest label; never healthy for source_unknown, "
        "never success for backup_check_warning."
    )
    tenant_id: Optional[str] = Field(None, description="Scoped id only; never joinable to business tables.")
    actor_scope: ActorScope
    owner_role: Optional[OwnerRole] = Field(None, description="Presentation only; not authorization.")
    owner_actor_id: Optional[str] = Field(None, description="The operator who self-assigned, if any.")
    correlation_id: str
    linked_action_id: Optional[str] = Field(None, description="-> P18 action_id (evidence pointer).")
    linked_approval_id: Optional[str] = Field(None, description="-> P21 durable_approval_id.")
    linked_execution_id: Optional[str] = Field(None, description="-> P22 execution_request_id.")
    linked_dry_run_ref: Optional[str] = Field(None, description="-> P22 dry_run_id.")
    linked_source_ref: Optional[str] = Field(None, description="-> P17 backup / status source handle.")
    linked_incident_id: Optional[str] = Field(None, description="-> P15 / P17 incident id.")
    summary_redacted: str = Field(..., description="One-line redacted summary.")
    reason_redacted: Optional[str] = Field(None, description="Redacted triage reason.")
    evidence_ref: Optional[str] = Field(None, description="Pointer to evidence; never raw payload.")
    source_status: Optional[SourceStatus] = Field(
        None, description="Mirrors the linked source; never fabricated healthy."
    )
    linked_gate_open: bool = Field(
        False,
        description="Mirror of the linked P19/P20/P21/P22 gate. True == still open "
        "(e.g. execution at dry_run_passed, approval at pending_review). Completing a "
        "task whose gate is still open is rejected.",
    )
    dedup_key_digest: str = Field(..., description="SHA-256 of the canonical dedup key.")
    ttl_expires_at: Optional[datetime] = Field(None, description="When the task auto-expires.")
    created_at: datetime = Field(..., description="UTC ISO-8601.")
    updated_at: datetime = Field(..., description="UTC ISO-8601.")
    redaction_applied: bool = Field(True, description="Always true; redaction is total.")


class OperatorTask(_TaskRecord):
    """A queue list-item view of one operator task."""


class OperatorTaskDetail(_TaskRecord):
    """A single-task read: the redacted record plus its full append-only audit
    history and its notification-event records.

    ``dismissed`` and ``expired`` tasks retain their full audit history here; the
    queue view is a view, not the system of record (P23-A 12.9 / C6).
    """

    audit_events: list[OperatorTaskAuditEvent] = Field(
        default_factory=list, description="Append-only per-task audit history."
    )
    notification_events: list[OperatorNotificationEvent] = Field(
        default_factory=list, description="Record-of-attention events for this task."
    )


class OperatorTaskQueue(BaseModel):
    """The queue list response (P23-A 7). Read-only; ranked by severity then recency."""

    model_config = ConfigDict(extra="forbid")

    tasks: list[OperatorTask]
    total: int = Field(..., description="Total active+terminal matches before pagination.")
    active_count: int = Field(..., description="Matches in a non-terminal state.")
    limit: int
    offset: int


class OperatorTaskTransitionRequest(BaseModel):
    """Body for acknowledge / self-assign / in-progress / complete / dismiss.

    Carries only redacted free-text triage fields. The ACTOR is the authenticated
    token (read in the route); it is never read from the body (no identity spoof),
    mirroring the P20-B-R1 / P22 binding. extra="forbid" rejects any other field.
    """

    model_config = ConfigDict(extra="forbid")

    reason: Optional[str] = Field(
        None, description="Redacted triage reason / dismissal reason."
    )
    evidence: Optional[str] = Field(
        None, description="Redacted evidence note. Required for complete (or evidence_ref)."
    )
    evidence_ref: Optional[str] = Field(
        None, description="Linked completed object id; alternative evidence for complete."
    )


class OperatorTaskTransitionResponse(BaseModel):
    """Result of a state-management transition (P23-A 7)."""

    model_config = ConfigDict(extra="forbid")

    accepted: bool = Field(..., description="True iff the transition changed state.")
    task: OperatorTask
    transition: str = Field(..., description="e.g. open->acknowledged or denied:complete.")
    previous_state: TaskState
    next_state: TaskState
    denial_code: Optional[TransitionDenialCode] = Field(
        None, description="Set iff accepted is False."
    )


class OperatorTaskIntakeEvent(BaseModel):
    """A typed, redacted source event accepted only by the internal/intake endpoint.

    This is NOT an arbitrary raw payload: it carries only the closed task-type enum
    and redacted, echo-safe identifiers / summaries. extra="forbid" rejects any other
    field. There is no order / payment / invoice / customer / inventory / ledger
    field (P23-A 3.2 / C8 / C15). Materializing a task from this event executes
    nothing and approves nothing.
    """

    model_config = ConfigDict(extra="forbid")

    task_type: TaskType
    severity: Optional[Severity] = Field(
        None, description="Override; None -> the catalog default, then correlation rule."
    )
    tenant_id: Optional[str] = Field(None, description="Scoped id only; null for platform-wide.")
    actor_scope: ActorScope = Field("platform", description="Visibility scope.")
    owner_role: Optional[OwnerRole] = None
    correlation_id: str = Field(..., description="Threads P18/P19/P20/P21/P22/P15/P17 events.")
    linked_action_id: Optional[str] = None
    linked_approval_id: Optional[str] = None
    linked_execution_id: Optional[str] = None
    linked_dry_run_ref: Optional[str] = None
    linked_source_ref: Optional[str] = None
    linked_incident_id: Optional[str] = None
    summary: str = Field(..., description="Pre-redaction summary; redacted before storage.")
    reason: Optional[str] = Field(None, description="Pre-redaction triage reason.")
    source_status: Optional[SourceStatus] = None
    linked_gate_open: bool = Field(
        False, description="Mirror of the linked gate; True == still open."
    )
    followup_variant: Optional[str] = Field(
        None, description="Dedup-key variant (e.g. runbook step id). Defaults to task_type."
    )
    ttl_expires_at: Optional[datetime] = None
    channel: Optional[NotificationChannel] = Field(
        None, description="If set, a notification EVENT (record-only) is also recorded."
    )


class OperatorTaskIntakeResponse(BaseModel):
    """Result of internal/intake: the materialized task plus dedup flags."""

    model_config = ConfigDict(extra="forbid")

    task: OperatorTask
    created: bool = Field(..., description="True iff a brand-new task was created.")
    deduped: bool = Field(..., description="True iff an existing ACTIVE task absorbed the event.")


__all__ = [
    # vocab tuples
    "TASK_TYPES",
    "TASK_STATES",
    "TERMINAL_STATES",
    "ACTIVE_STATES",
    "SEVERITIES",
    "ACTOR_SCOPES",
    "SOURCE_STATUSES",
    "OWNER_ROLES",
    "AUDIT_ACTOR_ROLES",
    "NOTIFICATION_CHANNELS",
    "NOTIFICATION_DELIVERY_STATES",
    "DISPLAY_STATUSES",
    "ALLOWED_TRANSITIONS",
    "DEFAULT_SEVERITY",
    "NEVER_HEALTHY_TYPES",
    "NEVER_SUCCESS_TYPES",
    "DENIAL_CODES",
    # literal types
    "TaskType",
    "TaskState",
    "Severity",
    "ActorScope",
    "SourceStatus",
    "OwnerRole",
    "AuditActorRole",
    "NotificationChannel",
    "NotificationDeliveryState",
    "DisplayStatus",
    "TransitionDenialCode",
    # models
    "OperatorTaskAuditEvent",
    "OperatorNotificationEvent",
    "OperatorTask",
    "OperatorTaskDetail",
    "OperatorTaskQueue",
    "OperatorTaskTransitionRequest",
    "OperatorTaskTransitionResponse",
    "OperatorTaskIntakeEvent",
    "OperatorTaskIntakeResponse",
]
