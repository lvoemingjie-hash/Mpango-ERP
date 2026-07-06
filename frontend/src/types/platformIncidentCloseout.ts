/**
 * P24 Incident + Runbook Closeout types (frontend console, P24-C).
 *
 * Field-for-field aligned to
 * docs/ai/PLATFORM_PRODUCT_P24_INCIDENT_RUNBOOK_CLOSEOUT_CONTRACT.md
 * (P24-A) and the backend P24 schemas
 * (backend/api/v1/platform/p24/schemas.py, P24-B skeleton).
 *
 * A CLOSEOUT IS A VIEW, NOT AN EXECUTOR. A RUNBOOK STEP IS A POINTER, NOT AN
 * EXECUTION. A FOLLOW-UP TASK IS A RECORD, NOT A REPAIR. These types describe
 * the read / triage / record surface only. There is no execute shape, no
 * approval-decision shape, no flag-write shape, and no tenant-business / payment
 * / product payload shape here. Recording a closeout or step transition records
 * operator judgment only; it never runs a P22 action, never decides a
 * P19/P20/P21 approval, never sets or clears the P17 incident_active flag, never
 * mutates a registry field, and never delivers a notification on any channel.
 *
 * The flag is mirrored, never owned. flag_observed / flag_ever_set are
 * observations of P17 incident_active; no field here ever represents a P24 flag
 * write (because P24 performs none).
 *
 * Redaction is total: every free-text field on the wire is the redacted form
 * (summary_redacted / reason_redacted / evidence_redacted). No raw secret / DSN
 * / host / port / token / cookie / auth header / shell / SQL / script /
 * tenant-business payload is ever present.
 *
 * The honest display_status (computed by the backend) is mirrored verbatim.
 * source_unknown is NEVER healthy (display_status === 'unknown' in every state,
 * including closed). A degraded source or a completed_with_warning linked
 * execution is NEVER success (display_status === 'warning' in every state,
 * including closed/done). A blocked runbook step is NEVER healthy. The frontend
 * defends these rules itself (see resolveCloseoutDisplayTone /
 * resolveStepDisplayTone) and never renders green for a source_unknown /
 * degraded / blocked item, regardless of the label the backend supplied. A
 * 'closed' closeout or 'done' step is rendered blue (not green) so a
 * backup_check_warning closeout/step is never visually read as success.
 *
 * 'closed' is never produced by frontend optimism: the page only ever reads
 * state / display_status back from the backend response after a transition. The
 * client never flips a local closeout to closed on its own.
 */

// -- Closed vocabularies (P24-A section 3.1 / 4.1 / 5 / 6 / 7) ----------------

/** The closed incident closeout lifecycle state set (P24-A 3.1). Exactly eight. */
export type CloseoutState =
  | 'detected'
  | 'triaged'
  | 'flagged_active'
  | 'in_remediation'
  | 'awaiting_closeout'
  | 'closed'
  | 'withdrawn'
  | 'expired';

/** The closed runbook step kind set (P24-A 4.1). Exactly three. */
export type StepKind = 'observation' | 'action_pointer' | 'approval_pointer';

/** The closed runbook step state set (P24-A 4.2). Exactly five. */
export type StepState =
  | 'owed'
  | 'in_progress'
  | 'done'
  | 'not_applicable'
  | 'blocked';

/** P15 incident classification vocabulary, reused unchanged (P24-A 2 / 3.2). */
export type Classification =
  | 'database'
  | 'system'
  | 'api'
  | 'tenant_health'
  | 'support_issue';

/** Three severity levels. Mirrors P23; correlation may raise, never lower. */
export type Severity = 'low' | 'medium' | 'high';

/** Visibility scope at which a closeout / step is shown (P24-A 6.1 / 8). */
export type ActorScope = 'platform' | 'tenant_contextual';

/** Suggested owner role (PRESENTATION ONLY; not authorization) (P24-A 6.1 / 8). */
export type OwnerRole =
  | 'super_admin'
  | 'engineering_operator'
  | 'support_operator';

/** Audit actor role. The operator is identity-only; `system` covers intake/TTL. */
export type AuditActorRole =
  | 'super_admin'
  | 'engineering_operator'
  | 'support_operator'
  | 'system';

/** The mirrored P17 incident_active observation (P24-A 6.1). P24 NEVER writes the flag. */
export type FlagObserved =
  | 'observed_true'
  | 'observed_false'
  | 'observed_unknown';

/** Source-status mirror of the linked P17 / P22 source. Never fabricated healthy. */
export type SourceStatus = 'known' | 'unknown' | 'degraded';

/** The closed set of recorded PUSH intake events (P24-A 5.1). Operator console
 *  never sends intake (system-only); typed here for completeness. */
export type IntakeEventType =
  | 'incident_detected'
  | 'incident_classified'
  | 'incident_flag_observed'
  | 'runbook_step_owed'
  | 'runbook_step_progress'
  | 'runbook_step_terminal'
  | 'closeout_transition';

/** The honest display label (P24-A 3.2 / 6 / acceptance 7 / 8). */
export type DisplayStatus =
  | 'healthy'
  | 'warning'
  | 'unknown'
  | 'completed'
  | 'dismissed'
  | 'closed'
  | 'withdrawn'
  | 'none';

/** Closed denial-code set for rejected transitions (P24-A 3.4 / 7.3). */
export type CloseoutDenialCode =
  | 'TRANSITION_DENIED_INVALID'
  | 'TRANSITION_DENIED_TERMINAL'
  | 'CLOSE_DENIED_FLAG_STILL_SET'
  | 'CLOSE_DENIED_OWED_TASKS_NONTERMINAL'
  | 'CLOSE_DENIED_SOURCE_UNKNOWN'
  | 'CLOSE_DENIED_EXECUTION_WARNING'
  | 'STEP_DONE_DENIED_GATE_OPEN'
  | 'STEP_DONE_DENIED_NO_EVIDENCE'
  | 'CLOSEOUT_NOT_FOUND'
  | 'STEP_NOT_FOUND';

// -- Vocab arrays (drive the filter <select> options in the console) ----------

export const CLOSEOUT_STATES: CloseoutState[] = [
  'detected',
  'triaged',
  'flagged_active',
  'in_remediation',
  'awaiting_closeout',
  'closed',
  'withdrawn',
  'expired',
];

export const STEP_KINDS: StepKind[] = [
  'observation',
  'action_pointer',
  'approval_pointer',
];

export const STEP_STATES: StepState[] = [
  'owed',
  'in_progress',
  'done',
  'not_applicable',
  'blocked',
];

export const CLASSIFICATIONS: Classification[] = [
  'database',
  'system',
  'api',
  'tenant_health',
  'support_issue',
];

export const SEVERITIES: Severity[] = ['low', 'medium', 'high'];

export const ACTOR_SCOPES: ActorScope[] = ['platform', 'tenant_contextual'];

export const OWNER_ROLES: OwnerRole[] = [
  'super_admin',
  'engineering_operator',
  'support_operator',
];

export const FLAG_OBSERVED_VALUES: FlagObserved[] = [
  'observed_true',
  'observed_false',
  'observed_unknown',
];

export const SOURCE_STATUSES: SourceStatus[] = ['known', 'unknown', 'degraded'];

export const CLOSEOUT_DENIAL_CODES: CloseoutDenialCode[] = [
  'TRANSITION_DENIED_INVALID',
  'TRANSITION_DENIED_TERMINAL',
  'CLOSE_DENIED_FLAG_STILL_SET',
  'CLOSE_DENIED_OWED_TASKS_NONTERMINAL',
  'CLOSE_DENIED_SOURCE_UNKNOWN',
  'CLOSE_DENIED_EXECUTION_WARNING',
  'STEP_DONE_DENIED_GATE_OPEN',
  'STEP_DONE_DENIED_NO_EVIDENCE',
  'CLOSEOUT_NOT_FOUND',
  'STEP_NOT_FOUND',
];

/** Terminal closeout states accept no outgoing transition (P24-A 3.1 / 3.3).
 *  withdrawn / expired remove the closeout from the active view but never
 *  delete the audit history; closed is the honest end. */
export const TERMINAL_CLOSEOUT_STATES: ReadonlySet<CloseoutState> = new Set([
  'closed',
  'withdrawn',
  'expired',
]);

/** Terminal step states accept no outgoing transition (P24-A 4.2 / 4.4 / C14). */
export const TERMINAL_STEP_STATES: ReadonlySet<StepState> = new Set([
  'done',
  'not_applicable',
]);

/**
 * Allowed closeout transitions (P24-A 3.1). A transition not listed here is
 * rejected by the backend. Terminal states have no outgoing edges. This is a
 * PRESENTATION / CLOSEOUT lifecycle only; no transition executes a controlled
 * action, approves an approval, sets / clears the flag, or mutates a registry
 * field (P24-A 3.3). The console uses this map to enable/disable transition
 * controls per current state; the backend remains the authority and may still
 * return a 409 denial (the honest close gate: flag still set, owed tasks
 * non-terminal, source still unknown, or linked execution at warning).
 */
export const ALLOWED_CLOSEOUT_TRANSITIONS: Readonly<
  Record<CloseoutState, readonly CloseoutState[]>
> = {
  detected: ['triaged', 'withdrawn', 'expired'],
  triaged: [
    'flagged_active',
    'in_remediation',
    'closed',
    'withdrawn',
    'expired',
  ],
  flagged_active: [
    'in_remediation',
    'awaiting_closeout',
    'withdrawn',
    'expired',
  ],
  in_remediation: [
    'flagged_active',
    'awaiting_closeout',
    'withdrawn',
    'expired',
  ],
  awaiting_closeout: ['closed', 'in_remediation', 'expired'],
  closed: [],
  withdrawn: [],
  expired: [],
};

/**
 * Allowed runbook step transitions (P24-A 4.2). Terminal step states accept no
 * exit. A `done` is further conditioned on the per-kind gate (observed terminal
 * execution / resolved approval / evidence note) in the backend; the backend
 * rejects with 409 (STEP_DONE_DENIED_GATE_OPEN / STEP_DONE_DENIED_NO_EVIDENCE).
 */
export const ALLOWED_STEP_TRANSITIONS: Readonly<
  Record<StepState, readonly StepState[]>
> = {
  owed: ['in_progress', 'done', 'not_applicable', 'blocked'],
  in_progress: ['done', 'not_applicable', 'blocked'],
  blocked: ['owed', 'not_applicable'],
  done: [],
  not_applicable: [],
};

export function isTerminalCloseoutState(state: CloseoutState): boolean {
  return TERMINAL_CLOSEOUT_STATES.has(state);
}

export function isTerminalStepState(state: StepState): boolean {
  return TERMINAL_STEP_STATES.has(state);
}

// -- Models (mirrors backend extra="forbid" schemas) -------------------------

/** One closeout state-change audit event (P24-A 7.1). Append-only; never deleted.
 *  A denied transition is recorded with transition === 'denied:<action>',
 *  next_state === previous_state (no change), and a denial_code. flag_observed
 *  is always an observation mirror; no audit field records a P24 flag write. */
export interface IncidentCloseoutAuditEvent {
  event_id: string;
  closeout_id: string;
  state: CloseoutState;
  /** The operator (or None for SYSTEM intake / TTL). */
  actor_id: string | null;
  actor_role: AuditActorRole;
  /** Scoped id only; never a business payload. */
  tenant_id: string | null;
  /** e.g. detected->triaged, flagged_active->awaiting_closeout, denied:close. */
  transition: string;
  previous_state: CloseoutState;
  next_state: CloseoutState;
  /** Mirrors P17 incident_active; never a P24 write. */
  flag_observed: FlagObserved;
  /** Redacted reason / judgment note. */
  reason_redacted: string | null;
  /** Set iff this is a denied (no-op) transition record. */
  denial_code: CloseoutDenialCode | null;
  correlation_id: string;
  linked_incident_id: string | null;
  linked_action_id: string | null;
  linked_approval_id: string | null;
  linked_execution_id: string | null;
  /** Always true; redaction is total. */
  redaction_applied: boolean;
  /** Monotonic per-closeout sequence. */
  sequence_no: number;
  /** UTC ISO-8601. */
  created_at: string;
}

/** One runbook step state-change audit event (P24-A 7.2). Append-only. */
export interface RunbookStepAuditEvent {
  event_id: string;
  step_id: string;
  closeout_id: string;
  step_kind: StepKind;
  /** e.g. owed->in_progress, in_progress->done, denied:done. */
  step_transition: string;
  previous_state: StepState;
  next_state: StepState;
  /** Operator or SYSTEM. */
  actor_id: string | null;
  actor_role: AuditActorRole;
  /** Scoped id only. */
  tenant_id: string | null;
  /** Redacted observation / evidence note. */
  evidence_redacted: string | null;
  correlation_id: string;
  linked_action_id: string | null;
  linked_approval_id: string | null;
  linked_execution_id: string | null;
  linked_source_ref: string | null;
  /** Always true; redaction is total. */
  redaction_applied: boolean;
  /** Monotonic per-step sequence. */
  sequence_no: number;
  /** UTC ISO-8601. */
  created_at: string;
}

/** A runbook step view (P24-A 4 / 6.2). A pointer and a record, never an
 *  execution. All free-text fields redacted. */
export interface RunbookStep {
  step_id: string;
  closeout_id: string;
  /** Presentation order; not execution order. */
  sequence_no: number;
  step_kind: StepKind;
  step_state: StepState;
  /** Computed honest label; never healthy for source_unknown / blocked. */
  display_status: DisplayStatus;
  /** Scoped id only. */
  tenant_id: string | null;
  correlation_id: string;
  /** -> P18 action_id (action_pointer). */
  linked_action_id: string | null;
  /** -> P21 durable_approval_id (approval_pointer). */
  linked_approval_id: string | null;
  /** -> P22 execution_request_id (action_pointer). */
  linked_execution_id: string | null;
  /** -> P17 backup / status source handle. */
  linked_source_ref: string | null;
  /** Pointer to evidence; never raw payload. */
  evidence_ref: string | null;
  /** One-line redacted summary. */
  summary_redacted: string;
  /** Redacted step reason / observation note. */
  reason_redacted: string | null;
  /** Mirrors the linked source; never fabricated healthy. */
  source_status: SourceStatus | null;
  /** Mirror; True iff linked execution observed terminal (action_pointer). */
  linked_execution_terminal: boolean;
  /** Mirror; True iff linked approval observed resolved (approval_pointer). */
  linked_approval_resolved: boolean;
  /** Mirror; True iff linked execution completed_with_warning. */
  linked_execution_warning: boolean;
  /** SHA-256 of the canonical step dedup key. */
  dedup_key_digest: string;
  /** -> P23 runbook_step_required task materialized for this step. */
  linked_task_id: string | null;
  /** UTC ISO-8601. */
  created_at: string;
  /** UTC ISO-8601. */
  updated_at: string;
  /** Always true; redaction is total. */
  redaction_applied: boolean;
}

/** Shared closeout fields (P24-A 6.1). All free-text fields are redacted. */
export interface IncidentCloseoutBase {
  closeout_id: string;
  state: CloseoutState;
  /** Computed honest label; never healthy for source_unknown. */
  display_status: DisplayStatus;
  /** P15 vocabulary; nullable until triage. */
  classification: Classification | null;
  severity: Severity;
  /** Scoped id only; null for platform-wide. Never a business payload. */
  tenant_id: string | null;
  actor_scope: ActorScope;
  /** Presentation only; not authorization. */
  owner_role: OwnerRole | null;
  /** The operator who self-assigned, if any. */
  owner_actor_id: string | null;
  correlation_id: string;
  /** Mirrors P17 incident_active; P24 NEVER writes the flag. */
  flag_observed: FlagObserved;
  /** Mirror; True iff flag was ever observed_true. Drives the closed rule. */
  flag_ever_set: boolean;
  /** -> P15 / P17 incident id. */
  linked_incident_id: string | null;
  /** -> P15 snapshot handle. */
  linked_triage_snapshot_ref: string | null;
  /** -> P15 handoff handle. */
  linked_handoff_ref: string | null;
  /** One-line redacted summary. */
  summary_redacted: string;
  /** Redacted closeout / triage reason. */
  reason_redacted: string | null;
  /** Mirrors the linked source; never fabricated healthy. */
  source_status: SourceStatus | null;
  /** Mirror; True iff a linked execution completed_with_warning. */
  linked_execution_warning: boolean;
  /** SHA-256 of the canonical closeout dedup key. */
  dedup_key_digest: string;
  /** When the closeout auto-expires. */
  ttl_expires_at: string | null;
  /** -> P23 incident_followup_required task, while owed. */
  linked_followup_task_id: string | null;
  /** Mirror; True while follow-up is owed. */
  followup_owed: boolean;
  /** UTC ISO-8601. */
  created_at: string;
  /** UTC ISO-8601. */
  updated_at: string;
  /** Always true; redaction is total. */
  redaction_applied: boolean;
}

/** A list-item view of one incident closeout. */
export interface IncidentCloseout extends IncidentCloseoutBase {}

/** A single-closeout read: the redacted record, full append-only audit history,
 *  ordered runbook steps, and linked P23 task ids (P24-A 9). withdrawn / expired
 *  closeouts retain their full audit history and steps here. */
export interface IncidentCloseoutDetail extends IncidentCloseoutBase {
  /** Append-only per-closeout audit history. */
  audit_events: IncidentCloseoutAuditEvent[];
  /** Ordered runbook steps. */
  steps: RunbookStep[];
}

/** The closeout list response (P24-A 9). Read-only; ranked by severity then recency. */
export interface IncidentCloseoutList {
  closeouts: IncidentCloseout[];
  /** Total matches before pagination. */
  total: number;
  /** Matches in a non-terminal state. */
  active_count: number;
  limit: number;
  offset: number;
}

/** The ordered runbook for one closeout (P24-A 9). Read-only. */
export interface RunbookView {
  closeout_id: string;
  steps: RunbookStep[];
}

/** Filters accepted by GET /incident-closeouts. All optional. */
export interface IncidentCloseoutListFilters {
  state?: CloseoutState;
  classification?: Classification;
  severity?: Severity;
  /** Scoped tenant id only. */
  tenant_id?: string;
  flag_observed?: FlagObserved;
  owner_actor_id?: string;
  correlation_id?: string;
}

/** Body for POST .../{closeout_id}/transition (P24-A 9). Carries only a closed
 *  target-state set and a redacted reason. The ACTOR is the authenticated token
 *  (read in the route); it is never sent from the body (no identity spoof). */
export interface CloseoutTransitionRequest {
  /** Operator judgment target (awaiting_closeout / closed / withdrawn / ...). */
  target_state: CloseoutState;
  /** Redacted closeout / triage reason / judgment note. */
  reason?: string | null;
}

/** Body for POST .../runbook/{step_id}/transition (P24-A 9). Carries a closed
 *  target step-state set, a redacted evidence note (required for an observation
 *  done), and an optional redacted reason. The ACTOR is the authenticated token. */
export interface StepTransitionRequest {
  /** Step target (in_progress / done / not_applicable / blocked / owed). */
  target_state: StepState;
  /** Redacted observation / evidence note. Required for an observation done. */
  evidence?: string | null;
  /** Redacted step reason. */
  reason?: string | null;
}

/**
 * Result of intake / self-assign / closeout-transition / step-transition
 * (P24-A 9). The transition routes return this shape on success; a denied
 * transition raises an HTTPException (409 / 404) with {detail:{code, message}},
 * which the page surfaces inline. `accepted` is the backend verdict (true iff
 * state changed); the page never fabricates accepted=true or closed locally.
 */
export interface IncidentCloseoutIntakeResponse {
  closeout: IncidentCloseout;
  /** The step affected by a runbook_step_* event / step transition, if any. */
  step: RunbookStep | null;
  /** True iff a brand-new closeout was created (intake only). */
  created: boolean;
  /** True iff an existing ACTIVE closeout absorbed the event. */
  deduped: boolean;
  /** True iff the event advanced state (else denied/recorded). */
  accepted: boolean;
  /** Set iff the event was a denied transition (audited, no state change). */
  denial_code: CloseoutDenialCode | null;
}

// -- Frontend display helpers (the honest-label rule, defended client-side) ---

export type IncidentDisplayTone = 'green' | 'yellow' | 'gray' | 'red' | 'blue';

/**
 * Resolve the badge tone for a closeout from its source mirrors + the
 * backend-supplied display_status. Defends the P24-A honesty rules on the
 * client:
 *   - source_unknown is NEVER healthy -> never green (rule 1).
 *   - a degraded source OR a completed_with_warning linked execution is NEVER
 *     success -> never green (rule 2).
 * The backend already computes the honest label; this guard is defensive
 * against a malformed / drifted response. Mirrors the backend
 * _compute_closeout_display mapping, then maps to a tone. 'closed' is rendered
 * blue (not green) so a closed-but-warning closeout is never visually read as
 * success.
 */
export function resolveCloseoutDisplayTone(
  displayStatus: DisplayStatus,
  sourceStatus: SourceStatus | null,
  linkedExecutionWarning: boolean,
): IncidentDisplayTone {
  if (sourceStatus === 'unknown') return 'gray';
  if (linkedExecutionWarning || sourceStatus === 'degraded') return 'yellow';
  switch (displayStatus) {
    case 'healthy':
      return 'green';
    case 'warning':
      return 'yellow';
    case 'closed':
      return 'blue';
    case 'withdrawn':
      return 'gray';
    case 'unknown':
    case 'none':
      return 'gray';
    default:
      return 'gray';
  }
}

/**
 * Resolve the badge tone for a runbook step. Defends the P24-A honesty rules on
 * the client:
 *   - a source_unknown step OR any blocked step is NEVER healthy -> never green.
 *   - a degraded source OR a completed_with_warning linked execution is NEVER
 *     success -> never green.
 * 'done' is rendered blue (not green) so a done-but-warning step is never
 * visually read as success. Mirrors the backend _compute_step_display mapping.
 */
export function resolveStepDisplayTone(
  displayStatus: DisplayStatus,
  sourceStatus: SourceStatus | null,
  linkedExecutionWarning: boolean,
  stepState: StepState,
): IncidentDisplayTone {
  if (sourceStatus === 'unknown' || stepState === 'blocked') return 'gray';
  if (linkedExecutionWarning || sourceStatus === 'degraded') return 'yellow';
  switch (displayStatus) {
    case 'healthy':
      return 'green';
    case 'warning':
      return 'yellow';
    case 'completed':
      return 'blue';
    case 'dismissed':
      return 'gray';
    case 'unknown':
    case 'none':
      return 'gray';
    default:
      return 'gray';
  }
}

/** True iff the tone is a healthy/success color (green). Used by tests + a11y. */
export function isHealthyIncidentTone(tone: IncidentDisplayTone): boolean {
  return tone === 'green';
}
