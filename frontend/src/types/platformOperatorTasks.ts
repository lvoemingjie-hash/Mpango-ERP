/**
 * P23 Operator Task / Notification Queue types (frontend console, P23-D).
 *
 * Field-for-field aligned to
 * docs/ai/PLATFORM_PRODUCT_P23_OPERATOR_TASK_NOTIFICATION_QUEUE_CONTRACT.md
 * (P23-A) and the backend P23 schemas (backend/api/v1/platform/p23/schemas.py
 * P23-B skeleton, plus sources.py P23-C materialize summary).
 *
 * A TASK IS A VIEW, NOT AN EXECUTOR. A NOTIFICATION IS A RECORD, NOT A
 * DELIVERY. These types describe the read / triage / record surface only.
 * There is no execute shape, no approval-decision shape, no delivery shape,
 * and no tenant-business / payment / product payload shape here. Completing a
 * task records operator attention only; it never runs a P22 action, never
 * decides a P19/P20/P21 approval, never mutates a P17 registry field, and never
 * delivers a notification on any channel.
 *
 * Redaction is total: every free-text field on the wire is the redacted form
 * (summary_redacted / reason_redacted / summary on a notification event). No
 * raw secret / DSN / host / port / token / cookie / auth header / shell / SQL /
 * script / tenant-business payload is ever present.
 *
 * The honest display_status (computed by the backend) is mirrored verbatim.
 * source_unknown is NEVER healthy (display_status === 'unknown' in every state,
 * including completed). backup_check_warning is NEVER success (display_status
 * === 'warning' in every state, including completed). The frontend defends this
 * rule itself (see resolveOperatorDisplayTone) and never renders green for
 * either task type, regardless of the label the backend supplied.
 */

// -- Closed vocabularies (P23-A section 3.1 / 4.1 / 5 / 6 / 10) --------------

/** The closed task-type catalog (P23-A 3.1). Exactly ten types. */
export type OperatorTaskType =
  | 'action_request_created'
  | 'approval_pending'
  | 'approval_decision_required'
  | 'execution_ready'
  | 'execution_completed'
  | 'execution_failed'
  | 'source_unknown'
  | 'backup_check_warning'
  | 'incident_followup_required'
  | 'runbook_step_required';

/** The closed task-state set (P23-A 4.1). Exactly nine states. */
export type OperatorTaskState =
  | 'open'
  | 'acknowledged'
  | 'in_progress'
  | 'waiting_on_approval'
  | 'waiting_on_source'
  | 'completed'
  | 'dismissed'
  | 'expired'
  | 'failed';

/** Three severity levels. No `critical` auto-execute tier (P23-A 11.1). */
export type OperatorTaskSeverity = 'low' | 'medium' | 'high';

/** Visibility scope at which a task is shown (P23-A 5.1). */
export type OperatorActorScope = 'platform' | 'tenant_contextual';

/** Source-status mirror of the linked P17 / P18 source. Never fabricated healthy. */
export type OperatorSourceStatus = 'known' | 'unknown' | 'degraded';

/** Suggested owner role (presentation only; not authorization). */
export type OperatorOwnerRole =
  | 'super_admin'
  | 'engineering_operator'
  | 'support_operator';

/** Audit actor role. The operator is identity-only; `system` covers sweep/TTL. */
export type OperatorAuditActorRole =
  | 'super_admin'
  | 'engineering_operator'
  | 'support_operator'
  | 'system';

/** Planned notification channels. P23 wires NO channel; record label only. */
export type OperatorNotificationChannel = 'in_app' | 'email' | 'webhook';

/** Notification delivery state. P23 only ever produces recorded | suppressed. */
export type OperatorNotificationDeliveryState =
  | 'recorded'
  | 'queued_for_delivery'
  | 'delivered'
  | 'failed_delivery'
  | 'suppressed';

/** The honest display label (P23-A 4.2 / 6.3 / 12.7 / 12.8). */
export type OperatorDisplayStatus =
  | 'healthy'
  | 'warning'
  | 'unknown'
  | 'failed'
  | 'completed'
  | 'dismissed'
  | 'none';

/** Closed denial-code set for rejected transitions (P23-A 4.4 / 10.2). */
export type OperatorTransitionDenialCode =
  | 'TRANSITION_DENIED_INVALID'
  | 'TRANSITION_DENIED_TERMINAL'
  | 'COMPLETE_DENIED_NO_EVIDENCE'
  | 'COMPLETE_DENIED_GATE_OPEN'
  | 'TASK_NOT_FOUND';

// -- Vocab arrays (drive the filter <select> options in the console) ---------

export const OPERATOR_TASK_TYPES: OperatorTaskType[] = [
  'action_request_created',
  'approval_pending',
  'approval_decision_required',
  'execution_ready',
  'execution_completed',
  'execution_failed',
  'source_unknown',
  'backup_check_warning',
  'incident_followup_required',
  'runbook_step_required',
];

export const OPERATOR_TASK_STATES: OperatorTaskState[] = [
  'open',
  'acknowledged',
  'in_progress',
  'waiting_on_approval',
  'waiting_on_source',
  'completed',
  'dismissed',
  'expired',
  'failed',
];

export const OPERATOR_SEVERITIES: OperatorTaskSeverity[] = ['low', 'medium', 'high'];

export const OPERATOR_SOURCE_STATUSES: OperatorSourceStatus[] = [
  'known',
  'unknown',
  'degraded',
];

export const OPERATOR_DISPLAY_STATUSES: OperatorDisplayStatus[] = [
  'healthy',
  'warning',
  'unknown',
  'failed',
  'completed',
  'dismissed',
  'none',
];

/** Terminal states accept no outgoing transition (P23-A 4.1 / 4.3 / 4.4). */
export const TERMINAL_OPERATOR_TASK_STATES: ReadonlySet<OperatorTaskState> = new Set([
  'completed',
  'dismissed',
  'expired',
  'failed',
]);

/** Task types that force display_status away from healthy (P23-A 12.7, C4). */
export const NEVER_HEALTHY_OPERATOR_TYPES: ReadonlySet<OperatorTaskType> = new Set([
  'source_unknown',
]);

/** Task types that force display_status away from success (P23-A 12.8, C5). */
export const NEVER_SUCCESS_OPERATOR_TYPES: ReadonlySet<OperatorTaskType> = new Set([
  'backup_check_warning',
]);

/**
 * Allowed presentation transitions (P23-A 4.1). A transition not listed is
 * rejected by the backend. Terminal states have no outgoing edges. The console
 * uses this map to enable/disable transition controls per current state; the
 * backend remains the authority and may still return a 409 denial.
 */
export const ALLOWED_OPERATOR_TRANSITIONS: Readonly<
  Record<OperatorTaskState, readonly OperatorTaskState[]>
> = {
  open: [
    'acknowledged',
    'in_progress',
    'waiting_on_approval',
    'waiting_on_source',
    'dismissed',
    'expired',
    'failed',
    'completed',
  ],
  acknowledged: [
    'in_progress',
    'waiting_on_approval',
    'waiting_on_source',
    'completed',
    'dismissed',
    'expired',
  ],
  in_progress: [
    'waiting_on_approval',
    'waiting_on_source',
    'completed',
    'failed',
    'dismissed',
  ],
  waiting_on_approval: ['acknowledged', 'in_progress', 'expired', 'failed'],
  waiting_on_source: ['acknowledged', 'in_progress', 'expired', 'failed'],
  completed: [],
  dismissed: [],
  expired: [],
  failed: [],
};

export function isTerminalOperatorTaskState(state: OperatorTaskState): boolean {
  return TERMINAL_OPERATOR_TASK_STATES.has(state);
}

// -- Models (mirrors backend extra="forbid" schemas) -------------------------

/** One task state-change audit event (P23-A 10.1). Append-only; never deleted. */
export interface OperatorTaskAuditEvent {
  event_id: string;
  task_id: string;
  task_type: OperatorTaskType;
  actor_id: string | null;
  actor_role: OperatorAuditActorRole;
  /** Scoped id only; never a business payload. */
  tenant_id: string | null;
  /** e.g. open->acknowledged, in_progress->completed, denied:complete. */
  transition: string;
  previous_state: OperatorTaskState;
  next_state: OperatorTaskState;
  /** Redacted reason / evidence note. */
  reason_redacted: string | null;
  /** Set iff this is a denied (no-op) transition record. */
  denial_code: OperatorTransitionDenialCode | null;
  correlation_id: string;
  linked_action_id: string | null;
  linked_approval_id: string | null;
  linked_execution_id: string | null;
  linked_source_ref: string | null;
  linked_incident_id: string | null;
  /** Always true; redaction is total. */
  redaction_applied: boolean;
  /** Monotonic per-task sequence. */
  sequence_no: number;
  /** UTC ISO-8601. */
  created_at: string;
}

/** A record of attention (P23-A 5.2 / 6). NOT a delivery. */
export interface OperatorNotificationEvent {
  event_id: string;
  task_id: string;
  /** Planned channel. P23 wires none; the field is a record label. */
  channel: OperatorNotificationChannel;
  /** recorded | suppressed in P23. Never delivered. */
  delivery_state: OperatorNotificationDeliveryState;
  severity: OperatorTaskSeverity;
  /** Scoped id only. */
  tenant_id: string | null;
  actor_scope: OperatorActorScope;
  /** Role hint; P23 resolves no address. */
  recipient_role: OperatorOwnerRole | null;
  /** Redacted one-line summary. Never a secret / DSN / host / port. */
  summary_redacted: string;
  correlation_id: string;
  /** Always true; redaction is total. */
  redaction_applied: boolean;
  /** UTC ISO-8601. */
  created_at: string;
}

/** Shared task fields (P23-A 5.1). All free-text fields are redacted. */
export interface OperatorTaskBase {
  task_id: string;
  task_type: OperatorTaskType;
  severity: OperatorTaskSeverity;
  state: OperatorTaskState;
  /** Computed honest label; never healthy for source_unknown, never success for backup_check_warning. */
  display_status: OperatorDisplayStatus;
  /** Scoped id only; never joinable to business tables. */
  tenant_id: string | null;
  actor_scope: OperatorActorScope;
  /** Presentation only; not authorization. */
  owner_role: OperatorOwnerRole | null;
  /** The operator who self-assigned, if any. */
  owner_actor_id: string | null;
  correlation_id: string;
  /** -> P18 action_id (evidence pointer). */
  linked_action_id: string | null;
  /** -> P21 durable_approval_id. */
  linked_approval_id: string | null;
  /** -> P22 execution_request_id. */
  linked_execution_id: string | null;
  /** -> P22 dry_run_id. */
  linked_dry_run_ref: string | null;
  /** -> P17 backup / status source handle. */
  linked_source_ref: string | null;
  /** -> P15 / P17 incident id. */
  linked_incident_id: string | null;
  /** One-line redacted summary. */
  summary_redacted: string;
  /** Redacted triage reason. */
  reason_redacted: string | null;
  /** Pointer to evidence; never raw payload. */
  evidence_ref: string | null;
  /** Mirrors the linked source; never fabricated healthy. */
  source_status: OperatorSourceStatus | null;
  /** Mirror of the linked gate. True == still open; completing then is rejected. */
  linked_gate_open: boolean;
  /** SHA-256 of the canonical dedup key. */
  dedup_key_digest: string;
  /** When the task auto-expires. */
  ttl_expires_at: string | null;
  /** UTC ISO-8601. */
  created_at: string;
  /** UTC ISO-8601. */
  updated_at: string;
  /** Always true; redaction is total. */
  redaction_applied: boolean;
}

/** A queue list-item view of one operator task. */
export interface OperatorTask extends OperatorTaskBase {}

/** A single-task read: the redacted record plus its full append-only audit
 *  history and its notification-event records (P23-A 7). */
export interface OperatorTaskDetail extends OperatorTaskBase {
  /** Append-only per-task audit history. */
  audit_events: OperatorTaskAuditEvent[];
  /** Record-of-attention events for this task. */
  notification_events: OperatorNotificationEvent[];
}

/** The queue list response (P23-A 7). Read-only; ranked by severity then recency. */
export interface OperatorTaskQueue {
  tasks: OperatorTask[];
  /** Total active+terminal matches before pagination. */
  total: number;
  /** Matches in a non-terminal state. */
  active_count: number;
  limit: number;
  offset: number;
}

/** Filters accepted by GET /operator-tasks. All optional. */
export interface OperatorTaskListFilters {
  severity?: OperatorTaskSeverity;
  task_type?: OperatorTaskType;
  state?: OperatorTaskState;
  source_status?: OperatorSourceStatus;
  /** Scoped tenant id only. */
  tenant_id?: string;
  owner_actor_id?: string;
  correlation_id?: string;
}

/**
 * Body for acknowledge / self-assign / in-progress / complete / dismiss. Carries
 * only redacted free-text triage fields. The ACTOR is the authenticated token
 * (read in the route); it is never sent from the body (no identity spoof).
 */
export interface OperatorTaskTransitionRequest {
  /** Redacted triage reason / dismissal reason. */
  reason?: string | null;
  /** Redacted evidence note. Required for complete (or evidence_ref). */
  evidence?: string | null;
  /** Linked completed object id; alternative evidence for complete. */
  evidence_ref?: string | null;
}

/** Result of a state-management transition (P23-A 7). */
export interface OperatorTaskTransitionResponse {
  /** True iff the transition changed state. */
  accepted: boolean;
  task: OperatorTask;
  /** e.g. open->acknowledged or denied:complete. */
  transition: string;
  previous_state: OperatorTaskState;
  next_state: OperatorTaskState;
  /** Set iff accepted is false. */
  denial_code: OperatorTransitionDenialCode | null;
}

// -- P23-C source materialization (manual read/materialize; NOT a scheduler) --

/** Per-source counts for one materialization pass. Read-only summary. */
export interface OperatorMaterializeSourceCounts {
  /** Source label, e.g. p19_approvals. */
  source: string;
  /** Source items read this pass. */
  read: number;
  /** Brand-new tasks materialized. */
  created: number;
  /** Events absorbed into an existing ACTIVE task (idempotent replay). */
  deduped: number;
  /** Source items that needed no follow-up (healthy / non-pending). */
  skipped: number;
  /** Source reads that were unavailable / failed (still surfaced as source_unknown). */
  unavailable: number;
  /** Tasks touched (created or deduped) this pass. */
  task_ids: string[];
}

/** Aggregate result of one manual materialize pass. Read-only summary. */
export interface OperatorMaterializeSummary {
  sources: OperatorMaterializeSourceCounts[];
  total_created: number;
  total_deduped: number;
  total_skipped: number;
  total_unavailable: number;
  /** UTC ISO-8601. */
  materialized_at: string;
}

// -- Frontend display helpers (the honest-label rule, defended client-side) ---

export type OperatorDisplayTone = 'green' | 'yellow' | 'gray' | 'red' | 'blue';

/**
 * Resolve the badge tone for a task from its task_type + the backend-supplied
 * display_status. Defends the two P23-A honesty rules on the client:
 *   - source_unknown is NEVER healthy -> never green (rule 1).
 *   - backup_check_warning is NEVER success -> never green (rule 2).
 * 'completed' is rendered blue (not green) so a completed backup_check_warning
 * is never visually read as success. The backend already computes the honest
 * label; this guard is defensive against a malformed / drifted response.
 */
export function resolveOperatorDisplayTone(
  taskType: OperatorTaskType,
  displayStatus: OperatorDisplayStatus,
): OperatorDisplayTone {
  if (NEVER_HEALTHY_OPERATOR_TYPES.has(taskType)) return 'gray';
  if (NEVER_SUCCESS_OPERATOR_TYPES.has(taskType)) return 'yellow';
  switch (displayStatus) {
    case 'healthy':
      return 'green';
    case 'warning':
      return 'yellow';
    case 'unknown':
    case 'none':
    case 'dismissed':
      return 'gray';
    case 'failed':
      return 'red';
    case 'completed':
      return 'blue';
    default:
      return 'gray';
  }
}

/** True iff the tone is a healthy/success color (green). Used by tests + a11y. */
export function isHealthyOperatorTone(tone: OperatorDisplayTone): boolean {
  return tone === 'green';
}
