"""Pydantic schemas for P24 Incident + Runbook Closeout (P24-B skeleton).

Field-for-field aligned to
docs/ai/PLATFORM_PRODUCT_P24_INCIDENT_RUNBOOK_CLOSEOUT_CONTRACT.md (P24-A).

This is a NON-EXECUTING, NON-SENDING, IN-MEMORY backend skeleton. It materializes
recorded PUSH intake events into an incident closeout read model and a runbook
step model, runs a presentation-only closeout lifecycle and step state machine
over them, and materializes the two P23 task types P23-C left as PUSH intake
(``incident_followup_required`` and ``runbook_step_required``) through the
existing P23 upsert seam. It NEVER executes a P22 action, NEVER approves a
P19/P20/P21 approval, NEVER sets or clears the P17 ``incident_active`` flag, NEVER
mutates a registry field, NEVER delivers a notification, NEVER dispatches a
worker / scheduler / drain loop, NEVER runs shell / SQL / script, and NEVER
mutates tenant business / payment / billing / product data.

Contract rules carried from P10 / P15 / P17 / P18 / P19 / P20 / P21 / P22 / P23 /
P24-A:
  - An incident closeout is a view, not an executor. A runbook step is a pointer,
    not an execution. A follow-up task is a record, not a repair.
  - The closeout lifecycle has EXACTLY the eight defined states (section 3.1) and
    enforces the allowed / forbidden transitions; terminal states accept no exit;
    ``closed`` requires honest completion (terminal owed tasks + observed flag
    clear when the flag was set).
  - The runbook step model has EXACTLY the three defined kinds and five defined
    states (section 4.1 / 4.2); an ``action_pointer`` ``done`` requires an
    observed terminal execution; an ``approval_pointer`` ``done`` requires an
    observed resolved approval; an ``observation`` ``done`` requires a redacted
    evidence note. Approvals are not execution.
  - The flag is mirrored, never owned. ``flag_observed`` is an observation enum;
    no field ever records a P17 flag write performed by P24 (because P24 performs
    none).
  - source_unknown is never displayed or closed healthy; backup_check_warning /
    a degraded linked execution is never displayed or closed as success (the
    computed display_status and the close gate enforce this).
  - Redaction is total: every free-text field passes through the P23 content
    redactor; no secret / DSN / host / port / token / cookie / auth header / raw
    body / shell / SQL / script / tenant business payload is ever stored,
    returned, or audited.
  - extra="forbid" on every model (no undeclared fields / leaks).
  - No tenant business records; tenant_id is a scoped identifier only.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# -- Closed vocabularies (P24-A section 3.1 / 4.1 / 5 / 6 / 7) -----------------

#: The closed incident closeout lifecycle state set (P24-A 3.1). Exactly eight.
CLOSEOUT_STATES: tuple[str, ...] = (
    "detected",
    "triaged",
    "flagged_active",
    "in_remediation",
    "awaiting_closeout",
    "closed",
    "withdrawn",
    "expired",
)

#: Terminal closeout states accept no outgoing transition (P24-A 3.1 / 3.3).
#: ``withdrawn`` and ``expired`` remove the closeout from the active view but
#: never delete the underlying audit history; ``closed`` is the honest end.
TERMINAL_CLOSEOUT_STATES: frozenset[str] = frozenset(
    {"closed", "withdrawn", "expired"}
)

#: Active (non-terminal) closeout states. Dedup collapses repeat intake events
#: into one ACTIVE closeout; terminal closeouts are exempt so a recurring
#: incident re-opens as a NEW closeout (P24-A 5.5 / 6.1).
ACTIVE_CLOSEOUT_STATES: frozenset[str] = frozenset(
    {"detected", "triaged", "flagged_active", "in_remediation", "awaiting_closeout"}
)

#: The closed runbook step kind set (P24-A 4.1). Exactly three. Every kind is a
#: pointer and a record, never an execution.
STEP_KINDS: tuple[str, ...] = (
    "observation",
    "action_pointer",
    "approval_pointer",
)

#: The closed runbook step state set (P24-A 4.2). Exactly five.
STEP_STATES: tuple[str, ...] = (
    "owed",
    "in_progress",
    "done",
    "not_applicable",
    "blocked",
)

#: Terminal step states accept no outgoing transition (P24-A 4.2 / 4.4 / C14).
TERMINAL_STEP_STATES: frozenset[str] = frozenset({"done", "not_applicable"})

#: Active (non-terminal) step states. A ``runbook_step_required`` P23 task is
#: materialized for a step in any of these (P24-A 5.3).
ACTIVE_STEP_STATES: frozenset[str] = frozenset({"owed", "in_progress", "blocked"})

#: P15 incident classification vocabulary, reused unchanged (P24-A 2 / 3.2).
CLASSIFICATIONS: tuple[str, ...] = (
    "database",
    "system",
    "api",
    "tenant_health",
    "support_issue",
)

#: Three severity levels. Mirrors P23; correlation may raise, never lower.
SEVERITIES: tuple[str, ...] = ("low", "medium", "high")

#: Visibility scope at which a closeout / step is shown (P24-A 6.1 / 8).
ACTOR_SCOPES: tuple[str, ...] = ("platform", "tenant_contextual")

#: Suggested owner roles (PRESENTATION ONLY; not authorization) (P24-A 6.1 / 8).
OWNER_ROLES: tuple[str, ...] = ("super_admin", "engineering_operator", "support_operator")

#: Audit actor roles (P24-A 7.1). The operator is identity-only platform-operator;
#: ``system`` covers intake / TTL.
AUDIT_ACTOR_ROLES: tuple[str, ...] = (
    "super_admin",
    "engineering_operator",
    "support_operator",
    "system",
)

#: The mirrored P17 ``incident_active`` observation (P24-A 6.1). P24 NEVER writes
#: the flag; this enum records what P24 observed about it. ``observed_unknown``
#: means the flag state is not (yet) known.
FLAG_OBSERVED_VALUES: tuple[str, ...] = (
    "observed_true",
    "observed_false",
    "observed_unknown",
)

#: Source-status mirror of the linked P17 / P22 source (P24-A 6.1). Never
#: fabricated healthy: ``unknown`` is never healthy; ``degraded`` is never
#: success (P10 / P17 / P22 / P23 rule, carried into P24).
SOURCE_STATUSES: tuple[str, ...] = ("known", "unknown", "degraded")

#: The closed set of recorded PUSH intake events (P24-A 5.1). P24-B accepts only
#: these; every other event shape is rejected at the schema layer (extra=forbid).
INTAKE_EVENT_TYPES: tuple[str, ...] = (
    "incident_detected",
    "incident_classified",
    "incident_flag_observed",
    "runbook_step_owed",
    "runbook_step_progress",
    "runbook_step_terminal",
    "closeout_transition",
)

#: The honest display label (P24-A 3.2 / 6 / acceptance 7 / 8). Computed by the
#: service from source_status + linked execution warning + state; NEVER
#: overridable to healthy / success for source_unknown / backup_check_warning.
#: ``unknown`` covers source_unknown and the unresolved / blocked / expired
#: cases; ``warning`` covers a degraded source or a completed_with_warning
#: linked execution (never a success); ``completed`` / ``dismissed`` label
#: terminal steps; ``closed`` / ``withdrawn`` label terminal closeouts.
DISPLAY_STATUSES: tuple[str, ...] = (
    "healthy",
    "warning",
    "unknown",
    "completed",
    "dismissed",
    "closed",
    "withdrawn",
    "none",
)


# -- State machines (P24-A section 3.1 / 4.2) ----------------------------------

#: Allowed closeout transitions (P24-A 3.1). A transition not listed here is
#: rejected. Terminal states have no outgoing edges. This is a PRESENTATION /
#: CLOSEOUT lifecycle only; no transition executes a controlled action, approves
#: an approval, sets / clears the flag, or mutates a registry field (P24-A 3.3).
ALLOWED_CLOSEOUT_TRANSITIONS: dict[str, frozenset[str]] = {
    "detected": frozenset({"triaged", "withdrawn", "expired"}),
    "triaged": frozenset(
        {"flagged_active", "in_remediation", "closed", "withdrawn", "expired"}
    ),
    "flagged_active": frozenset(
        {"in_remediation", "awaiting_closeout", "withdrawn", "expired"}
    ),
    "in_remediation": frozenset(
        {"flagged_active", "awaiting_closeout", "withdrawn", "expired"}
    ),
    "awaiting_closeout": frozenset({"closed", "in_remediation", "expired"}),
    "closed": frozenset(),
    "withdrawn": frozenset(),
    "expired": frozenset(),
}

#: Allowed runbook step transitions (P24-A 4.2). Terminal step states accept no
#: exit. A ``done`` is further conditioned on the per-kind gate (observed
#: terminal execution / resolved approval / evidence note) in the service.
ALLOWED_STEP_TRANSITIONS: dict[str, frozenset[str]] = {
    "owed": frozenset({"in_progress", "done", "not_applicable", "blocked"}),
    "in_progress": frozenset({"done", "not_applicable", "blocked"}),
    "blocked": frozenset({"owed", "not_applicable"}),
    "done": frozenset(),
    "not_applicable": frozenset(),
}


#: Closed denial-code set for rejected closeout transitions (P24-A 3.4 / 7.3).
#: Denials are recorded as denied audit events; they change no state.
DENIAL_CODES: tuple[str, ...] = (
    "TRANSITION_DENIED_INVALID",
    "TRANSITION_DENIED_TERMINAL",
    "CLOSE_DENIED_FLAG_STILL_SET",
    "CLOSE_DENIED_OWED_TASKS_NONTERMINAL",
    "CLOSE_DENIED_SOURCE_UNKNOWN",
    "CLOSE_DENIED_EXECUTION_WARNING",
    "STEP_DONE_DENIED_GATE_OPEN",
    "STEP_DONE_DENIED_NO_EVIDENCE",
    "CLOSEOUT_NOT_FOUND",
    "STEP_NOT_FOUND",
)

CloseoutDenialCode = Literal[
    "TRANSITION_DENIED_INVALID",
    "TRANSITION_DENIED_TERMINAL",
    "CLOSE_DENIED_FLAG_STILL_SET",
    "CLOSE_DENIED_OWED_TASKS_NONTERMINAL",
    "CLOSE_DENIED_SOURCE_UNKNOWN",
    "CLOSE_DENIED_EXECUTION_WARNING",
    "STEP_DONE_DENIED_GATE_OPEN",
    "STEP_DONE_DENIED_NO_EVIDENCE",
    "CLOSEOUT_NOT_FOUND",
    "STEP_NOT_FOUND",
]


# -- Pydantic Literal mirrors (closed sets enforced at the schema layer) -------

CloseoutState = Literal[
    "detected",
    "triaged",
    "flagged_active",
    "in_remediation",
    "awaiting_closeout",
    "closed",
    "withdrawn",
    "expired",
]
StepKind = Literal["observation", "action_pointer", "approval_pointer"]
StepState = Literal["owed", "in_progress", "done", "not_applicable", "blocked"]
Classification = Literal[
    "database", "system", "api", "tenant_health", "support_issue"
]
Severity = Literal["low", "medium", "high"]
ActorScope = Literal["platform", "tenant_contextual"]
OwnerRole = Literal["super_admin", "engineering_operator", "support_operator"]
AuditActorRole = Literal[
    "super_admin", "engineering_operator", "support_operator", "system"
]
FlagObserved = Literal["observed_true", "observed_false", "observed_unknown"]
SourceStatus = Literal["known", "unknown", "degraded"]
IntakeEventType = Literal[
    "incident_detected",
    "incident_classified",
    "incident_flag_observed",
    "runbook_step_owed",
    "runbook_step_progress",
    "runbook_step_terminal",
    "closeout_transition",
]
DisplayStatus = Literal[
    "healthy", "warning", "unknown", "completed", "dismissed", "closed", "withdrawn", "none"
]


# -- Models (all extra="forbid") ----------------------------------------------


class IncidentCloseoutAuditEvent(BaseModel):
    """One closeout state-change audit event (P24-A 7.1). Append-only; never deleted.

    A denied transition is recorded with ``transition == "denied:<action>"``,
    ``next_state == previous_state`` (no change), and a ``denial_code``.
    ``flag_observed`` is always an observation mirror; no audit field ever records
    a P17 flag write performed by P24 (because P24 performs none).
    """

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(..., description="PK. Unique per audit event.")
    closeout_id: str = Field(..., description="The closeout whose state changed.")
    state: CloseoutState
    actor_id: Optional[str] = Field(
        None, description="The operator (or None for SYSTEM intake / TTL)."
    )
    actor_role: AuditActorRole
    tenant_id: Optional[str] = Field(None, description="Scoped id only; never a business payload.")
    transition: str = Field(
        ...,
        description="e.g. detected->triaged, flagged_active->awaiting_closeout, denied:close.",
    )
    previous_state: CloseoutState
    next_state: CloseoutState
    flag_observed: FlagObserved = Field(
        ..., description="Mirrors P17 incident_active; never a P24 write."
    )
    reason_redacted: Optional[str] = Field(
        None, description="Redacted reason / judgment note. P10 allowlist applied."
    )
    denial_code: Optional[CloseoutDenialCode] = Field(
        None, description="Set iff this is a denied (no-op) transition record."
    )
    correlation_id: str
    linked_incident_id: Optional[str] = None
    linked_action_id: Optional[str] = None
    linked_approval_id: Optional[str] = None
    linked_execution_id: Optional[str] = None
    redaction_applied: bool = Field(True, description="Always true; redaction is total.")
    sequence_no: int = Field(..., description="Monotonic per-closeout sequence.")
    created_at: datetime = Field(..., description="UTC ISO-8601.")


class RunbookStepAuditEvent(BaseModel):
    """One runbook step state-change audit event (P24-A 7.2). Append-only.

    A denied step transition is recorded with ``step_transition ==
    "denied:<action>"``, ``next_state == previous_state``, and a ``denial_code``.
    """

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(..., description="PK. Unique per audit event.")
    step_id: str = Field(..., description="The step whose state changed.")
    closeout_id: str = Field(..., description="Echoed.")
    step_kind: StepKind
    step_transition: str = Field(
        ..., description="e.g. owed->in_progress, in_progress->done, denied:done."
    )
    previous_state: StepState
    next_state: StepState
    actor_id: Optional[str] = Field(None, description="Operator or SYSTEM.")
    actor_role: AuditActorRole
    tenant_id: Optional[str] = Field(None, description="Scoped id only.")
    evidence_redacted: Optional[str] = Field(
        None, description="Redacted observation / evidence note. P10 allowlist applied."
    )
    correlation_id: str
    linked_action_id: Optional[str] = None
    linked_approval_id: Optional[str] = None
    linked_execution_id: Optional[str] = None
    linked_source_ref: Optional[str] = None
    redaction_applied: bool = Field(True, description="Always true; redaction is total.")
    sequence_no: int = Field(..., description="Monotonic per-step sequence.")
    created_at: datetime = Field(..., description="UTC ISO-8601.")


class RunbookStep(BaseModel):
    """A runbook step list-item view (P24-A 4 / 6.2). All free-text fields redacted.

    A step is a pointer and a record, never an execution. ``display_status`` is
    computed: ``unknown`` for a source_unknown / blocked-on-unknown step (never
    healthy), ``warning`` for a degraded source (never success), else follows the
    step state.
    """

    model_config = ConfigDict(extra="forbid")

    step_id: str
    closeout_id: str
    sequence_no: int = Field(..., description="Presentation order; not execution order.")
    step_kind: StepKind
    step_state: StepState
    display_status: DisplayStatus = Field(
        ..., description="Computed honest label; never healthy for source_unknown."
    )
    tenant_id: Optional[str] = Field(None, description="Scoped id only.")
    correlation_id: str
    linked_action_id: Optional[str] = Field(None, description="-> P18 action_id (action_pointer).")
    linked_approval_id: Optional[str] = Field(None, description="-> P21 durable_approval_id (approval_pointer).")
    linked_execution_id: Optional[str] = Field(None, description="-> P22 execution_request_id (action_pointer).")
    linked_source_ref: Optional[str] = Field(None, description="-> P17 backup / status source handle.")
    evidence_ref: Optional[str] = Field(None, description="Pointer to evidence; never raw payload.")
    summary_redacted: str = Field(..., description="One-line redacted summary.")
    reason_redacted: Optional[str] = Field(None, description="Redacted step reason / observation note.")
    source_status: Optional[SourceStatus] = Field(
        None, description="Mirrors the linked source; never fabricated healthy."
    )
    #: Mirror of the linked P22 execution terminal state (action_pointer). True
    #: iff the linked execution was observed at executed / execution_failed /
    #: compensation_completed. Marking the step done is rejected while False.
    linked_execution_terminal: bool = Field(
        False, description="Mirror; True iff linked execution observed terminal."
    )
    #: Mirror of the linked P19/P20/P21 approval resolved state (approval_pointer).
    linked_approval_resolved: bool = Field(
        False, description="Mirror; True iff linked approval observed resolved."
    )
    #: Mirror of a P22-G ``completed_with_warning`` (backup_check_warning) linked
    #: execution. A closeout carrying such a step cannot close as success.
    linked_execution_warning: bool = Field(
        False, description="Mirror; True iff linked execution completed_with_warning."
    )
    dedup_key_digest: str = Field(..., description="SHA-256 of the canonical step dedup key.")
    linked_task_id: Optional[str] = Field(
        None, description="-> P23 runbook_step_required task materialized for this step."
    )
    created_at: datetime = Field(..., description="UTC ISO-8601.")
    updated_at: datetime = Field(..., description="UTC ISO-8601.")
    redaction_applied: bool = Field(True, description="Always true; redaction is total.")


class _CloseoutRecord(BaseModel):
    """Shared closeout fields (P24-A 6.1). All free-text fields are redacted."""

    model_config = ConfigDict(extra="forbid")

    closeout_id: str
    state: CloseoutState
    display_status: DisplayStatus = Field(
        ..., description="Computed honest label; never healthy for source_unknown."
    )
    classification: Optional[Classification] = Field(
        None, description="P15 vocabulary; nullable until triage."
    )
    severity: Severity
    tenant_id: Optional[str] = Field(
        None, description="Scoped id only; null for platform-wide. Never a business payload."
    )
    actor_scope: ActorScope
    owner_role: Optional[OwnerRole] = Field(None, description="Presentation only; not authorization.")
    owner_actor_id: Optional[str] = Field(None, description="The operator who self-assigned, if any.")
    correlation_id: str
    flag_observed: FlagObserved = Field(
        ..., description="Mirrors P17 incident_active; P24 NEVER writes the flag."
    )
    #: Internal mirror: True iff the flag was ever observed_true. Drives the
    #: ``closed`` rule that requires an observed clear when the flag was set.
    flag_ever_set: bool = Field(
        False, description="Mirror; True iff flag was ever observed_true."
    )
    linked_incident_id: Optional[str] = Field(None, description="-> P15 / P17 incident id.")
    linked_triage_snapshot_ref: Optional[str] = Field(None, description="-> P15 snapshot handle.")
    linked_handoff_ref: Optional[str] = Field(None, description="-> P15 handoff handle.")
    summary_redacted: str = Field(..., description="One-line redacted summary.")
    reason_redacted: Optional[str] = Field(None, description="Redacted closeout / triage reason.")
    source_status: Optional[SourceStatus] = Field(
        None, description="Mirrors the linked source; never fabricated healthy."
    )
    #: Mirror of a P22-G ``completed_with_warning`` (backup_check_warning) linked
    #: execution. A closeout carrying such a warning cannot close as success.
    linked_execution_warning: bool = Field(
        False, description="Mirror; True iff a linked execution completed_with_warning."
    )
    dedup_key_digest: str = Field(..., description="SHA-256 of the canonical closeout dedup key.")
    ttl_expires_at: Optional[datetime] = Field(None, description="When the closeout auto-expires.")
    #: -> P23 incident_followup_required task materialized while follow-up is owed.
    linked_followup_task_id: Optional[str] = Field(
        None, description="-> P23 incident_followup_required task, while owed."
    )
    #: Mirror: True while an incident follow-up is owed on this closeout.
    followup_owed: bool = Field(False, description="Mirror; True while follow-up is owed.")
    created_at: datetime = Field(..., description="UTC ISO-8601.")
    updated_at: datetime = Field(..., description="UTC ISO-8601.")
    redaction_applied: bool = Field(True, description="Always true; redaction is total.")


class IncidentCloseout(_CloseoutRecord):
    """A list-item view of one incident closeout."""


class IncidentCloseoutDetail(_CloseoutRecord):
    """A single-closeout read: the redacted record, full append-only audit
    history, ordered runbook steps, and the linked P23 task ids.

    ``withdrawn`` and ``expired`` closeouts retain their full audit history and
    steps here; the closeout is a view, not the system of record (P24-A 1.3.2 /
    acceptance 11 / C11).
    """

    audit_events: list[IncidentCloseoutAuditEvent] = Field(
        default_factory=list, description="Append-only per-closeout audit history."
    )
    steps: list[RunbookStep] = Field(
        default_factory=list, description="Ordered runbook steps."
    )


class IncidentCloseoutList(BaseModel):
    """The closeout list response (P24-A 9). Read-only; ranked by severity then recency."""

    model_config = ConfigDict(extra="forbid")

    closeouts: list[IncidentCloseout]
    total: int = Field(..., description="Total matches before pagination.")
    active_count: int = Field(..., description="Matches in a non-terminal state.")
    limit: int
    offset: int


class RunbookView(BaseModel):
    """The ordered runbook for one closeout (P24-A 9). Read-only."""

    model_config = ConfigDict(extra="forbid")

    closeout_id: str
    steps: list[RunbookStep]


class CloseoutTransitionRequest(BaseModel):
    """Body for POST .../{closeout_id}/transition (P24-A 9).

    Carries only a closed target-state set and a redacted reason. The ACTOR is
    the authenticated token (read in the route); it is never read from the body
    (no identity spoof). extra="forbid" rejects any other field.
    """

    model_config = ConfigDict(extra="forbid")

    target_state: CloseoutState = Field(
        ..., description="Operator judgment target (awaiting_closeout / closed / withdrawn / ...)."
    )
    reason: Optional[str] = Field(
        None, description="Redacted closeout / triage reason / judgment note."
    )


class CloseoutTransitionResponse(BaseModel):
    """Result of a closeout transition (P24-A 9)."""

    model_config = ConfigDict(extra="forbid")

    accepted: bool = Field(..., description="True iff the transition changed state.")
    closeout: IncidentCloseout
    transition: str = Field(..., description="e.g. awaiting_closeout->closed or denied:close.")
    previous_state: CloseoutState
    next_state: CloseoutState
    denial_code: Optional[CloseoutDenialCode] = Field(None, description="Set iff accepted is False.")


class StepTransitionRequest(BaseModel):
    """Body for POST .../runbook/{step_id}/transition (P24-A 9).

    Carries a closed target step-state set, a redacted evidence note (required for
    an observation ``done``), and an optional redacted reason. The ACTOR is the
    authenticated token. extra="forbid" rejects any other field.
    """

    model_config = ConfigDict(extra="forbid")

    target_state: StepState = Field(
        ..., description="Step target (in_progress / done / not_applicable / blocked / owed)."
    )
    evidence: Optional[str] = Field(
        None, description="Redacted observation / evidence note. Required for an observation done."
    )
    reason: Optional[str] = Field(None, description="Redacted step reason.")


class StepTransitionResponse(BaseModel):
    """Result of a runbook step transition (P24-A 9)."""

    model_config = ConfigDict(extra="forbid")

    accepted: bool = Field(..., description="True iff the step transition changed state.")
    step: RunbookStep
    step_transition: str = Field(..., description="e.g. owed->done or denied:done.")
    previous_state: StepState
    next_state: StepState
    denial_code: Optional[CloseoutDenialCode] = Field(None, description="Set iff accepted is False.")


class IncidentCloseoutIntakeEvent(BaseModel):
    """A typed, redacted PUSH intake event accepted only by the intake endpoint
    (P24-A 5.1).

    This is NOT an arbitrary raw payload: it carries only the closed
    ``event_type`` enum and redacted, echo-safe identifiers / summaries /
    observed-state mirrors. extra="forbid" rejects any other field. There is no
    order / payment / invoice / customer / inventory / ledger field (P24-A 1.3.2
    / C13 / C17). Processing this event executes nothing, approves nothing, flips
    no flag, and delivers nothing; it only advances the in-memory closeout /
    step view and upserts P23 tasks through the existing seam.

    The ACTOR is the authenticated token (read in the route); it is never read
    from the body. ``closeout_id`` may be supplied to address an existing
    closeout; for ``incident_detected`` it may be omitted (a new id is generated).

    The ``flag_observed`` / ``source_status`` / ``linked_execution_terminal`` /
    ``linked_approval_resolved`` / ``linked_execution_warning`` fields are
    OBSERVED-state mirrors of prior-phase outcomes (P17 flag, P22 execution, P21
    approval); P24 writes none of them.
    """

    model_config = ConfigDict(extra="forbid")

    event_type: IntakeEventType
    closeout_id: Optional[str] = Field(
        None, description="Existing closeout id; required except for incident_detected."
    )
    classification: Optional[Classification] = None
    severity: Optional[Severity] = Field(
        None, description="Override; None -> default, then correlation rule."
    )
    tenant_id: Optional[str] = Field(None, description="Scoped id only; null for platform-wide.")
    actor_scope: ActorScope = Field("platform", description="Visibility scope.")
    owner_role: Optional[OwnerRole] = None
    correlation_id: str = Field(..., description="Threads P15/P17/P18/P19/P20/P21/P22/P23 events.")
    linked_incident_id: Optional[str] = None
    linked_triage_snapshot_ref: Optional[str] = None
    linked_handoff_ref: Optional[str] = None
    summary: str = Field(..., description="Pre-redaction summary; redacted before storage.")
    reason: Optional[str] = Field(None, description="Pre-redaction triage / judgment reason.")
    flag_observed: Optional[FlagObserved] = Field(
        None, description="Observed P17 incident_active mirror; never a P24 write."
    )
    source_status: Optional[SourceStatus] = None
    linked_action_id: Optional[str] = None
    linked_approval_id: Optional[str] = None
    linked_execution_id: Optional[str] = None
    linked_source_ref: Optional[str] = None
    #: Step fields (runbook_step_* events).
    step_id: Optional[str] = Field(
        None, description="Existing step id; for runbook_step_owed may be omitted (new id)."
    )
    step_kind: Optional[StepKind] = None
    sequence_no: Optional[int] = Field(
        None, description="Presentation order; not execution order."
    )
    linked_execution_terminal: Optional[bool] = Field(
        None, description="Mirror; True iff linked execution observed terminal (action_pointer)."
    )
    linked_approval_resolved: Optional[bool] = Field(
        None, description="Mirror; True iff linked approval observed resolved (approval_pointer)."
    )
    linked_execution_warning: Optional[bool] = Field(
        None, description="Mirror; True iff linked execution completed_with_warning."
    )
    evidence: Optional[str] = Field(
        None, description="Pre-redaction evidence / observation note (runbook_step_terminal)."
    )
    #: closeout_transition only: operator judgment target state.
    target_state: Optional[CloseoutState] = Field(
        None, description="Operator judgment target (closeout_transition)."
    )
    ttl_expires_at: Optional[datetime] = None


class IncidentCloseoutIntakeResponse(BaseModel):
    """Result of intake: the affected closeout + step (if any) + dedup flags."""

    model_config = ConfigDict(extra="forbid")

    closeout: IncidentCloseout
    step: Optional[RunbookStep] = Field(
        None, description="The step affected by a runbook_step_* event, if any."
    )
    created: bool = Field(..., description="True iff a brand-new closeout was created.")
    deduped: bool = Field(..., description="True iff an existing ACTIVE closeout absorbed the event.")
    accepted: bool = Field(..., description="True iff the event advanced state (else denied/recorded).")
    denial_code: Optional[CloseoutDenialCode] = Field(
        None, description="Set iff the event was a denied transition (audited, no state change)."
    )


__all__ = [
    # vocab tuples
    "CLOSEOUT_STATES",
    "TERMINAL_CLOSEOUT_STATES",
    "ACTIVE_CLOSEOUT_STATES",
    "STEP_KINDS",
    "STEP_STATES",
    "TERMINAL_STEP_STATES",
    "ACTIVE_STEP_STATES",
    "CLASSIFICATIONS",
    "SEVERITIES",
    "ACTOR_SCOPES",
    "OWNER_ROLES",
    "AUDIT_ACTOR_ROLES",
    "FLAG_OBSERVED_VALUES",
    "SOURCE_STATUSES",
    "INTAKE_EVENT_TYPES",
    "DISPLAY_STATUSES",
    "ALLOWED_CLOSEOUT_TRANSITIONS",
    "ALLOWED_STEP_TRANSITIONS",
    "DENIAL_CODES",
    # literal types
    "CloseoutState",
    "StepKind",
    "StepState",
    "Classification",
    "Severity",
    "ActorScope",
    "OwnerRole",
    "AuditActorRole",
    "FlagObserved",
    "SourceStatus",
    "IntakeEventType",
    "DisplayStatus",
    "CloseoutDenialCode",
    # models
    "IncidentCloseoutAuditEvent",
    "RunbookStepAuditEvent",
    "RunbookStep",
    "IncidentCloseout",
    "IncidentCloseoutDetail",
    "IncidentCloseoutList",
    "RunbookView",
    "CloseoutTransitionRequest",
    "CloseoutTransitionResponse",
    "StepTransitionRequest",
    "StepTransitionResponse",
    "IncidentCloseoutIntakeEvent",
    "IncidentCloseoutIntakeResponse",
]
