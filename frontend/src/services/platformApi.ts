/**
 * Platform Admin Cockpit API client service.
 *
 * Uses the existing Axios singleton (api.ts) with Bearer token injection.
 * All calls go to P10/P12/P13 contract-backed endpoints.
 *
 * Auth transport (P11-B0-R1 resolved): The backend P10 guard accepts
 * identity-only (global) super_admin Bearer tokens only. The frontend
 * uses the standard Axios Bearer token from an identity/global super_admin
 * session (before tenant selection).
 *
 * No X-Platform-Operator secret is ever sent to or stored in the browser.
 */
import { api } from './api';
import type {
  PlatformTenantSummaryList,
  PlatformTenantSummary,
  PlatformTenantHealth,
  PlatformSystemHealth,
  PlatformAuditEventList,
  PlatformAuditEvent,
} from '@/types/platform';
import type {
  ErrorRateSummary,
  SlowRouteSummary,
  ResourceHealthSummary,
  NoisyNeighborSummary,
} from '@/types/platformOps';
import type { IncidentTriageSnapshot } from '@/types/platformIncident';
import type {
  PlatformTenantRegistry,
  PlatformTenantRegistryList,
} from '@/types/platformRegistry';
import type {
  ControlledActionCatalog,
  ControlledActionRequestPayload,
  ControlledActionRequestQueue,
  ControlledActionRequestResponse,
} from '@/types/platformControlledActions';
import type {
  ControlledActionApprovalDecision,
  ControlledActionApprovalQueue,
  ControlledActionApprovalRecord,
  ControlledActionApprovalRequest,
} from '@/types/platformApprovals';
import type {
  DurableApprovalCreateRequest,
  DurableApprovalDecisionRequest,
  DurableApprovalQueue,
  DurableApprovalRecord,
} from '@/types/platformDurableApprovals';
import type {
  BackupCheckSourceRead,
  ExecutionCatalogResponse,
  ExecutionDryRunRequest,
  ExecutionDryRunResponse,
  ExecutionRequestCreate,
  ExecutionRequestQueue,
  ExecutionRequestResponse,
} from '@/types/platformControlledExecution';
import type {
  OperatorMaterializeSummary,
  OperatorTaskDetail,
  OperatorTaskListFilters,
  OperatorTaskQueue,
  OperatorTaskTransitionRequest,
  OperatorTaskTransitionResponse,
} from '@/types/platformOperatorTasks';
import type {
  CloseoutTransitionRequest,
  IncidentCloseoutDetail,
  IncidentCloseoutIntakeResponse,
  IncidentCloseoutList,
  IncidentCloseoutListFilters,
  RunbookView,
  StepTransitionRequest,
} from '@/types/platformIncidentCloseout';

const P10_BASE = '/platform/p10';
const P13_BASE = '/platform/p13';
const P15_BASE = '/platform/p15';
const P17_BASE = '/platform/p17';
const P18_BASE = '/platform/p18';
const P19_BASE = '/platform/p19';
const P20_BASE = '/platform/p20';
const P22_BASE = '/platform/p22';
const P23_BASE = '/platform/p23';
const P24_BASE = '/platform/p24';

export const platformService = {
  /** List tenants with optional pagination */
  listTenants: (limit = 50, offset = 0) =>
    api.get<PlatformTenantSummaryList>(`${P10_BASE}/tenants`, {
      params: { limit, offset },
    }),

  /** Get a single tenant summary */
  getTenant: (tenantId: string) =>
    api.get<PlatformTenantSummary>(`${P10_BASE}/tenants/${tenantId}`),

  /** Get tenant health detail */
  getTenantHealth: (tenantId: string) =>
    api.get<PlatformTenantHealth>(`${P10_BASE}/tenants/${tenantId}/health`),

  /** Get system health */
  getSystemHealth: () =>
    api.get<PlatformSystemHealth>(`${P10_BASE}/system/health`),

  /** List audit events with optional pagination */
  listAuditEvents: (limit = 50, offset = 0) =>
    api.get<PlatformAuditEventList>(`${P10_BASE}/audit/events`, {
      params: { limit, offset },
    }),

  /** Get a single audit event */
  getAuditEvent: (eventId: string) =>
    api.get<PlatformAuditEvent>(`${P10_BASE}/audit/events/${eventId}`),

  // -- P13 Operations Cockpit (read-only) --

  /** P13: Get ops system health */
  getOpsHealth: () =>
    api.get<PlatformSystemHealth>(`${P13_BASE}/ops/health`),

  /** P13: Get error rate analysis */
  getOpsErrors: (window = 15) =>
    api.get<ErrorRateSummary>(`${P13_BASE}/ops/errors`, {
      params: { window },
    }),

  /** P13: Get slow route analysis */
  getOpsSlowRoutes: (window = 15, threshold = 1000) =>
    api.get<SlowRouteSummary>(`${P13_BASE}/ops/slow-routes`, {
      params: { window, threshold },
    }),

  /** P13: Get resource health summary */
  getOpsResources: () =>
    api.get<ResourceHealthSummary>(`${P13_BASE}/ops/resources`),

  /** P13: Get noisy-neighbor analysis */
  getOpsNoisyNeighbors: (window = 15) =>
    api.get<NoisyNeighborSummary>(`${P13_BASE}/ops/noisy-neighbors`, {
      params: { window },
    }),

  // -- P15 Incident Triage (read-only snapshot) --

  /** P15: Get incident triage snapshot (read-only) */
  getIncidentTriageSnapshot: () =>
    api.get<IncidentTriageSnapshot>(`${P15_BASE}/incidents/triage/snapshot`),

  // -- P17 Platform Registry (read-only tenant registry) --

  /** P17: List tenant registry (read-only) */
  listTenantRegistry: (limit = 50, offset = 0) =>
    api.get<PlatformTenantRegistryList>(`${P17_BASE}/registry`, {
      params: { limit, offset },
    }),

  /** P17: Get a single tenant registry (read-only) */
  getTenantRegistry: (tenantId: string) =>
    api.get<PlatformTenantRegistry>(`${P17_BASE}/registry/${tenantId}`),

  // -- P18 Controlled Actions (request skeleton; not executed) --

  /** P18: Get the controlled-action catalog (read-only) */
  getControlledActionCatalog: () =>
    api.get<ControlledActionCatalog>(`${P18_BASE}/actions/catalog`),

  /** P18: Dry-run validate a controlled-action request (not executed) */
  validateControlledAction: (payload: ControlledActionRequestPayload) =>
    api.post<ControlledActionRequestResponse>(`${P18_BASE}/actions/validate`, payload),

  /** P18: Record a controlled-action request (not executed) */
  submitControlledAction: (payload: ControlledActionRequestPayload) =>
    api.post<ControlledActionRequestResponse>(`${P18_BASE}/actions/request`, payload),

  /** P18: List recorded controlled-action requests (ephemeral; not executed) */
  listControlledActionRequests: (limit = 20, offset = 0) =>
    api.get<ControlledActionRequestQueue>(`${P18_BASE}/actions/requests`, {
      params: { limit, offset },
    }),

  /** P18: Read a recorded controlled-action request by id (not executed) */
  getControlledActionRequest: (actionId: string) =>
    api.get<ControlledActionRequestResponse>(`${P18_BASE}/actions/requests/${actionId}`),

  // -- P19 Approval Workflow (approval read / write / decide; not executed) --
  //
  // Approval is not execution: an approved approval resolves to
  // execution_blocked, never runs the wrapped P18 action, and every record and
  // queue item carries execution_allowed === false and executed === false. No
  // X-Platform-Operator secret is sent; these reuse the standard Axios Bearer
  // token transport, identical to the P10..P18 platform calls above.

  /** P19: Create (record) an approval request (not executed) */
  createApprovalRequest: (payload: ControlledActionApprovalRequest) =>
    api.post<ControlledActionApprovalRecord>(`${P19_BASE}/approvals`, payload),

  /** P19: List the approval queue (ephemeral in-memory; not executed) */
  listApprovals: (limit = 50, offset = 0) =>
    api.get<ControlledActionApprovalQueue>(`${P19_BASE}/approvals`, {
      params: { limit, offset },
    }),

  /** P19: Read a recorded approval by id (not executed) */
  getApproval: (approvalId: string) =>
    api.get<ControlledActionApprovalRecord>(`${P19_BASE}/approvals/${approvalId}`),

  /** P19: Submit an approve / reject decision (approved resolves to
   *  execution_blocked; reject is final; never executes) */
  submitApprovalDecision: (
    approvalId: string,
    payload: ControlledActionApprovalDecision,
  ) =>
    api.post<ControlledActionApprovalRecord>(
      `${P19_BASE}/approvals/${approvalId}/decision`,
      payload,
    ),

  // -- P20 Durable Approval Governance (maker-checker + quorum; not executed) --
  //
  // Durability is not execution: a quorum-met durable approval resolves to
  // approved_execution_blocked, never runs the wrapped P18 action, and every
  // record and queue item carries execution_allowed === false,
  // execution_gate === 'blocked', and executed === false. The maker and the
  // checker bind to the authenticated identity-only super_admin actor on the
  // server. No X-Platform-Operator secret is sent; these reuse the standard
  // Axios Bearer token transport, identical to the P10..P19 platform calls.

  /** P20: Open (record) a durable approval request (not executed) */
  createDurableApproval: (payload: DurableApprovalCreateRequest) =>
    api.post<DurableApprovalRecord>(`${P20_BASE}/durable-approvals`, payload),

  /** P20: List the durable approval queue (ephemeral in-memory; not executed) */
  listDurableApprovals: (
    limit = 50,
    offset = 0,
    filters?: { status?: string; action_type?: string; tenant_id?: string },
  ) =>
    api.get<DurableApprovalQueue>(`${P20_BASE}/durable-approvals`, {
      params: { limit, offset, ...filters },
    }),

  /** P20: Read a recorded durable approval by id (not executed) */
  getDurableApproval: (approvalId: string) =>
    api.get<DurableApprovalRecord>(`${P20_BASE}/durable-approvals/${approvalId}`),

  /** P20: Record one checker's approve / reject decision (approved resolves to
   *  approved_execution_blocked; reject is final; never executes) */
  submitDurableApprovalDecision: (
    approvalId: string,
    payload: DurableApprovalDecisionRequest,
  ) =>
    api.post<DurableApprovalRecord>(
      `${P20_BASE}/durable-approvals/${approvalId}/decisions`,
      payload,
    ),

  // -- P22 Controlled Execution (non-executing operator console; never executed) --
  //
  // Approval is not execution and durability is not execution. A passed dry-run
  // is a PRECONDITION, not an execution; a recorded request is RECORDED only.
  // Every response carries execution_allowed === false, executed === false, and
  // execution_started === false, and a result_state that is only ever
  // dry_run_passed | blocked. No worker is dispatched, no queue is drained, no
  // P16 harness is invoked, and no tenant / payment / product state is changed.
  // The raw idempotency_key is hashed at the boundary; only its one-way digest
  // is ever returned. No X-Platform-Operator secret is sent; these reuse the
  // standard Axios Bearer token transport, identical to the P10..P20 calls.

  /** P22: Get the v0 execution catalog (allowlist + exclusions; read-only) */
  getExecutionCatalog: () =>
    api.get<ExecutionCatalogResponse>(`${P22_BASE}/execution/catalog`),

  /** P22: Dry-run validate an execution (no mutation; never executes) */
  dryRunExecution: (payload: ExecutionDryRunRequest) =>
    api.post<ExecutionDryRunResponse>(`${P22_BASE}/execution/dry-run`, payload),

  /** P22: Record an execution request after a passed dry-run + ack (never executes) */
  recordExecutionRequest: (payload: ExecutionRequestCreate) =>
    api.post<ExecutionRequestResponse>(`${P22_BASE}/execution/requests`, payload),

  /** P22: List recorded execution requests with optional filters (read-only) */
  listExecutionRequests: (
    limit = 50,
    offset = 0,
    filters?: {
      result_state?: string;
      action_type?: string;
      durable_approval_id?: string;
    },
  ) =>
    api.get<ExecutionRequestQueue>(`${P22_BASE}/execution/requests`, {
      params: { limit, offset, ...filters },
    }),

  /** P22: Read one recorded execution request by id (read-only; never executes) */
  getExecutionRequest: (executionRequestId: string) =>
    api.get<ExecutionRequestResponse>(
      `${P22_BASE}/execution/requests/${executionRequestId}`,
    ),

  /** P22-E3/E4: read-only backup.check source status probe (never executes).
   *  Surfaces the proven P17-D-C backup / status source. tenantId omitted =
   *  platform-wide. A read failure degrades to an honest unavailable / unknown
   *  body (HTTP 200, fail-closed), never an execution. */
  getBackupCheckSource: (tenantId?: string) =>
    api.get<BackupCheckSourceRead>(`${P22_BASE}/backup-check/source`, {
      params: tenantId && tenantId.trim() ? { tenant_id: tenantId.trim() } : undefined,
    }),

  // -- P23 Operator Task / Notification Queue (view, not executor; record, not
  //    delivery) --
  //
  // A task is a view, not an executor; a notification is a record, not a
  // delivery. Every call below is read / triage / record only. None runs a P22
  // action, decides a P19/P20/P21 approval, mutates a P17 registry field,
  // delivers a notification on any channel, dispatches a worker, drains a queue,
  // runs shell / SQL / script, or reads / writes any tenant business / payment /
  // billing / product record. The actor for every transition is the
  // authenticated identity-only super_admin token (read in the route); it is
  // never sent from the request body (no identity spoof), mirroring P20-B-R1 /
  // P22. Owner is presentation only and grants no new privilege. Materialize is
  // a manual read/materialize operation; it is NOT a scheduler and NOT a worker.
  // No X-Platform-Operator secret is sent; these reuse the standard Axios Bearer
  // token transport, identical to the P10..P22 platform calls above.

  /** P23: list the operator task queue with optional filters (read-only). */
  listOperatorTasks: (
    limit = 50,
    offset = 0,
    filters?: OperatorTaskListFilters,
  ) =>
    api.get<OperatorTaskQueue>(`${P23_BASE}/operator-tasks`, {
      params: { limit, offset, ...filters },
    }),

  /** P23: read one task's redacted record, audit history, and notification
   *  events (read-only; 404 when not found). */
  getOperatorTask: (taskId: string) =>
    api.get<OperatorTaskDetail>(`${P23_BASE}/operator-tasks/${taskId}`),

  /** P23-C: manually read the safe source surfaces and materialize tasks through
   *  the service layer (read-only; NOT a scheduler / worker; executes nothing). */
  materializeOperatorTasks: () =>
    api.post<OperatorMaterializeSummary>(
      `${P23_BASE}/operator-tasks/internal/materialize`,
    ),

  /** P23: open|waiting_on_* -> acknowledged (state management only). */
  acknowledgeOperatorTask: (
    taskId: string,
    payload: OperatorTaskTransitionRequest = {},
  ) =>
    api.post<OperatorTaskTransitionResponse>(
      `${P23_BASE}/operator-tasks/${taskId}/acknowledge`,
      payload,
    ),

  /** P23: set the owner to the authenticated operator (presentation only; grants
   *  no new privilege; does not change state). */
  selfAssignOperatorTask: (
    taskId: string,
    payload: OperatorTaskTransitionRequest = {},
  ) =>
    api.post<OperatorTaskTransitionResponse>(
      `${P23_BASE}/operator-tasks/${taskId}/self-assign`,
      payload,
    ),

  /** P23: -> in_progress (records operator attention only; the action still runs
   *  through P22). */
  markOperatorTaskInProgress: (
    taskId: string,
    payload: OperatorTaskTransitionRequest = {},
  ) =>
    api.post<OperatorTaskTransitionResponse>(
      `${P23_BASE}/operator-tasks/${taskId}/in-progress`,
      payload,
    ),

  /** P23: -> completed. Requires a redacted evidence note OR a linked completed
   *  id (evidence_ref) AND a closed linked gate; the backend rejects with 409
   *  (COMPLETE_DENIED_NO_EVIDENCE / COMPLETE_DENIED_GATE_OPEN) otherwise.
   *  Completing a task records attention only; it executes nothing and does not
   *  make the completer the P22 executor. */
  completeOperatorTask: (
    taskId: string,
    payload: OperatorTaskTransitionRequest,
  ) =>
    api.post<OperatorTaskTransitionResponse>(
      `${P23_BASE}/operator-tasks/${taskId}/complete`,
      payload,
    ),

  /** P23: -> dismissed (removes from the active queue; audit history retained). */
  dismissOperatorTask: (
    taskId: string,
    payload: OperatorTaskTransitionRequest = {},
  ) =>
    api.post<OperatorTaskTransitionResponse>(
      `${P23_BASE}/operator-tasks/${taskId}/dismiss`,
      payload,
    ),

  // -- P24 Incident + Runbook Closeout (view, not executor; pointer, not
  //    execution; record, not repair) --
  //
  // A closeout is a view, not an executor; a runbook step is a pointer, not an
  // execution; a follow-up task is a record, not a repair. Every call below is
  // read / triage / record only. None runs a P22 action, decides a P19/P20/P21
  // approval, sets or clears the P17 incident_active flag, mutates a registry
  // field, delivers a notification, dispatches a worker, drains a queue, runs
  // shell / SQL / script, or reads / writes any tenant business / payment /
  // billing / product record. The actor for every transition is the
  // authenticated identity-only super_admin token (read in the route); it is
  // never sent from the request body (no identity spoof), mirroring P20-B-R1 /
  // P22 / P23. The flag is mirrored, never owned. Owner is presentation only and
  // grants no new privilege. Intake is system-only and is NOT exposed here (the
  // operator console never pushes intake). No X-Platform-Operator secret is
  // sent; these reuse the standard Axios Bearer token transport, identical to
  // the P10..P23 platform calls above.

  /** P24: list incident closeouts with optional filters (read-only). */
  listIncidentCloseouts: (
    limit = 50,
    offset = 0,
    filters?: IncidentCloseoutListFilters,
  ) =>
    api.get<IncidentCloseoutList>(`${P24_BASE}/incident-closeouts`, {
      params: { limit, offset, ...filters },
    }),

  /** P24: read one closeout's redacted record, full audit history, and runbook
   *  steps (read-only; 404 when not found). withdrawn / expired retain history. */
  getIncidentCloseout: (closeoutId: string) =>
    api.get<IncidentCloseoutDetail>(
      `${P24_BASE}/incident-closeouts/${closeoutId}`,
    ),

  /** P24: read the ordered runbook steps for one closeout (read-only). */
  getRunbook: (closeoutId: string) =>
    api.get<RunbookView>(`${P24_BASE}/incident-closeouts/${closeoutId}/runbook`),

  /** P24: set the closeout owner to the authenticated operator (presentation
   *  only; grants no new privilege; does not change state). */
  selfAssignCloseout: (closeoutId: string) =>
    api.post<IncidentCloseoutIntakeResponse>(
      `${P24_BASE}/incident-closeouts/${closeoutId}/self-assign`,
    ),

  /** P24: record an operator closeout judgment (advance to awaiting_closeout /
   *  closed / withdrawn / ...). Rejects with 409 when the honest close gate is
   *  still open (flag still set, owed tasks non-terminal, source still unknown,
   *  or linked execution at backup_check_warning). Executes nothing; flips no
   *  flag. The backend verdict (accepted / denial_code) is authoritative; the
   *  page never fabricates closed locally. */
  transitionCloseout: (
    closeoutId: string,
    payload: CloseoutTransitionRequest,
  ) =>
    api.post<IncidentCloseoutIntakeResponse>(
      `${P24_BASE}/incident-closeouts/${closeoutId}/transition`,
      payload,
    ),

  /** P24: record a runbook step state change with a redacted evidence /
   *  observation note. Rejects with 409 (STEP_DONE_DENIED_GATE_OPEN /
   *  STEP_DONE_DENIED_NO_EVIDENCE) on a `done` whose per-kind gate is still open
   *  (action_pointer execution not observed terminal / approval_pointer approval
   *  not observed resolved / observation step without an evidence note). A step
   *  is a pointer, not an execution; marking it done executes nothing. */
  transitionRunbookStep: (
    closeoutId: string,
    stepId: string,
    payload: StepTransitionRequest,
  ) =>
    api.post<IncidentCloseoutIntakeResponse>(
      `${P24_BASE}/incident-closeouts/${closeoutId}/runbook/${stepId}/transition`,
      payload,
    ),
};
