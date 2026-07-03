/**
 * P22 Controlled Execution v0 types (P22-C operator console).
 *
 * Field-for-field aligned to the P22-B backend schemas
 * (backend/api/v1/platform/p22/schemas.py) and
 * docs/ai/PLATFORM_PRODUCT_P22_CONTROLLED_EXECUTION_V0_CONTRACT.md (P22-A).
 *
 * This is a NON-EXECUTING operator console: every response carries
 * executed === false, execution_allowed === false, and
 * execution_started === false. A passed dry-run and a recorded request are
 * PRECONDITIONS, never an execution. result_state is only ever
 * 'dry_run_passed' | 'blocked' in P22-B; the full nine-state enum is typed
 * here for contract fidelity but only the two non-executing entry states are
 * ever realized.
 *
 * The raw idempotency_key is never stored / logged / echoed / audited by the
 * backend; only its one-way SHA-256 digest (idempotency_key_digest) and a
 * canonical payload_digest are returned. These types therefore never model a
 * raw key on a RESPONSE shape -- only the digest.
 */

// -- Vocabularies (mirror P22-A / backend schemas) ---------------------------

/**
 * The closed v0 execution allowlist: exactly seven action_types. Anything not
 * in this set has no v0 execution path. Used to drive the action_type select
 * in the console (excluded actions are never selectable).
 */
export type P22ActionType =
  | 'support_mode.on'
  | 'support_mode.off'
  | 'incident.flag_set'
  | 'incident.flag_clear'
  | 'provisioning.recheck'
  | 'backup.check'
  | 'backup.restore_test_request';

/** The seven allowlisted v0 action_types as a runtime tuple (catalog guard). */
export const P22_ALLOWED_ACTION_TYPES: readonly P22ActionType[] = [
  'support_mode.on',
  'support_mode.off',
  'incident.flag_set',
  'incident.flag_clear',
  'provisioning.recheck',
  'backup.check',
  'backup.restore_test_request',
];

/** P18 action classification, inherited verbatim. */
export type P22ActionClass = 'read' | 'write' | 'write_request';

/** The dry-run verdict (P22-A 5.2). */
export type ExecutionVerdict = 'passed' | 'blocked';

/**
 * The execution-record state machine (P22-A 7.1). P22-B realizes ONLY the two
 * non-executing entry states (dry_run_passed | blocked); the remaining states
 * belong to a separately approved execution phase and are never assigned here.
 */
export type ExecutionResultState =
  | 'dry_run_passed'
  | 'blocked'
  | 'execution_queued'
  | 'executing'
  | 'executed'
  | 'execution_failed'
  | 'compensation_required'
  | 'compensation_completed'
  | 'cancelled';

/** The two result_state values P22-B ever realizes. */
export type P22RealizedResultState = 'dry_run_passed' | 'blocked';

/** The P22 execution source-status vocabulary (known | unknown | degraded). */
export type ExecutionSourceStatus = 'known' | 'unknown' | 'degraded';

/** The execution mode. P22-B accepts both and executes neither. */
export type ExecutionMode = 'sync' | 'queued';

/** The wider actor_role vocabulary used in audit events and denied responses. */
export type ExecutionActorRole =
  | 'super_admin'
  | 'support_operator'
  | 'engineering_operator'
  | 'system'
  | 'unknown';

/** The wider identity_context vocabulary used in audit / denied responses. */
export type ExecutionIdentityContext =
  | 'identity_only'
  | 'tenant_contextual'
  | 'tenant_scoped_token'
  | 'tenant_admin'
  | 'system'
  | 'unknown';

/**
 * The closed block_reason / denial code vocabulary (P22-A section 4 / 8.2). A
 * blocked dry-run or a denied execution carries one or more of these codes.
 */
export type BlockReasonCode =
  | 'executor_not_identity_super_admin'
  | 'action_not_allowlisted'
  | 'action_excluded'
  | 'approval_not_found'
  | 'approval_state_not_approved_execution_blocked'
  | 'quorum_not_met'
  | 'source_unknown_for_write'
  | 'self_execution_forbidden'
  | 'checker_execution_forbidden'
  | 'idempotency_key_required'
  | 'action_mismatch_approval'
  | 'target_mismatch_approval'
  | 'reason_required'
  | 'execution_mode_required'
  | 'dry_run_required'
  | 'dry_run_invalid'
  | 'execution_ack_required'
  | 'idempotency_conflict';

/** Operational outcome of a recorded request (P22-A section 6). */
export type ExecutionRequestResult = 'recorded' | 'blocked' | 'denied' | 'conflict' | 'duplicate';

// -- Catalog -----------------------------------------------------------------

export interface CatalogItem {
  action_type: P22ActionType;
  action_class: P22ActionClass;
  /** The only v0 executor. Always 'super_admin (identity-only)'. */
  executor: string;
  reversible: boolean;
  /** The paired reversal action_type, if any (null for reads / restore-test). */
  reversibility_via: P22ActionType | null;
  /** Always 'none' for every v0 action -- no tenant business mutation. */
  tenant_business_mutation: string;
}

export interface ExcludedAction {
  action_type: string;
  reason: string;
}

export interface ExecutionCatalogResponse {
  items: CatalogItem[];
  exclusions: ExcludedAction[];
  /** Number of allowlisted actions (always 7). */
  total: number;
  /** The contract revision. Always 'P22-A'. */
  contract: string;
  /** Always 'memory' in P22-B skeleton. */
  storage: string;
  /** Always false -- the catalog never executes. */
  executed: boolean;
}

// -- Dry-run -----------------------------------------------------------------

/**
 * Inbound body for a no-mutation dry-run. The executor identity is derived
 * from the authenticated token on the server; it is NOT read from this body.
 * Raw client values are used for catalog lookup and the one-way idempotency
 * digest only; nothing raw is echoed or audited.
 */
export interface ExecutionDryRunRequest {
  durable_approval_id?: string | null;
  action_type?: string | null;
  /** Scoped id only; null for platform-wide. Never a business payload. */
  tenant_id?: string | null;
  requested_state?: string | null;
  reason?: string | null;
  /** Required; hashed to a digest at the boundary; the raw key is never returned. */
  idempotency_key?: string | null;
  /** Required. sync | queued. P22-B accepts both and executes neither. */
  execution_mode?: string | null;
  correlation_id?: string | null;
  metadata?: Record<string, unknown> | null;
}

/**
 * Dry-run response (P22-A 5.2). No mutation; never executes. `executable` is
 * the dry-run verdict (true only if every precondition holds).
 * `execution_allowed` is ALWAYS false in P22-B: a passed dry-run is a
 * precondition, not an execution. The raw idempotency key is never returned;
 * only its one-way digest is.
 */
export interface ExecutionDryRunResponse {
  /** Present when verdict === 'passed'. */
  dry_run_id: string | null;
  durable_approval_id: string | null;
  action_type: string | null;
  tenant_id: string | null;
  requested_state: string | null;
  /** true only if every precondition holds. */
  executable: boolean;
  verdict: ExecutionVerdict;
  /** Empty when passed; the failed precondition codes when blocked. */
  block_reasons: BlockReasonCode[];
  /**
   * The event_type(s) execution would emit, with FIELD NAMES ONLY -- never
   * values, secrets, or raw payloads. Keyed by event_type.
   */
  expected_audit_shape: Record<string, string[]>;
  execution_mode: ExecutionMode | null;
  /** known | unknown | degraded. Unknown is never healthy. */
  source_status: ExecutionSourceStatus;
  /** Whether a paired reversal action exists. */
  reversible: boolean;
  /** Always true. */
  redaction_applied: boolean;
  /** SHA-256 of the client key; the raw key is never returned. */
  idempotency_key_digest: string | null;
  /** Always 'memory' in P22-B skeleton. */
  storage: string;
  /** Always false -- a dry-run never executes. */
  executed: boolean;
  /** Always false -- a dry-run never starts execution. */
  execution_started: boolean;
  /** Always false in P22-B -- a passed dry-run is a precondition, not execution. */
  execution_allowed: boolean;
  /** UTC ISO-8601. */
  created_at: string;
}

// -- Execution request -------------------------------------------------------

/**
 * Inbound body to record an execution request. Requires a passed dry-run
 * (dry_run_ref) and the typed execution acknowledgement (execution_ack). The
 * request is RECORDED only; it is never executed.
 */
export interface ExecutionRequestCreate {
  durable_approval_id?: string | null;
  action_type?: string | null;
  tenant_id?: string | null;
  requested_state?: string | null;
  reason?: string | null;
  /** Required. Only its SHA-256 digest is stored. */
  idempotency_key?: string | null;
  /** Required. The dry_run_id of a passed dry-run for the same approval / action / target / executor. */
  dry_run_ref?: string | null;
  /** Required typed execution acknowledgement; the request lands only when true. */
  execution_ack: boolean;
  /** Required. sync | queued. */
  execution_mode?: string | null;
  correlation_id?: string | null;
  metadata?: Record<string, unknown> | null;
}

/**
 * A recorded execution request and uniform response (P22-A section 6).
 * result_state is only ever 'dry_run_passed' (recorded) or 'blocked' (a
 * precondition failed at request time, or an idempotency conflict).
 * executed / execution_started / execution_allowed are always false. The raw
 * idempotency key is never stored or returned; only the digest and the
 * canonical payload_digest are.
 */
export interface ExecutionRequestResponse {
  /** Unique per attempt; null until recorded (blocked requests are not recorded). */
  execution_request_id: string | null;
  durable_approval_id: string | null;
  action_type: string | null;
  tenant_id: string | null;
  requested_state: string | null;
  /** Redacted reason; never a raw body. */
  reason_redacted: string;
  /** SHA-256 of the client key; the raw key is never stored / returned. */
  idempotency_key_digest: string | null;
  /** SHA-256 of the canonical execution payload; drives replay dedup. */
  payload_digest: string | null;
  /** Identity-only super_admin executor (from the token). */
  actor_id: string | null;
  /** Always super_admin for a recorded request; denied responses reflect the denied actor. */
  actor_role: ExecutionActorRole;
  /** Always identity_only for a recorded request; denied responses reflect the denied actor. */
  identity_context: ExecutionIdentityContext;
  execution_mode: ExecutionMode | null;
  /** The bound passed dry-run id. */
  dry_run_ref: string | null;
  /** The typed acknowledgement carried by the request. */
  execution_ack: boolean;
  correlation_id: string | null;
  /** Redacted metadata; never raw secrets. */
  metadata_redacted: Record<string, unknown> | null;
  /** Always true. */
  redaction_applied: boolean;
  /** Only dry_run_passed | blocked in P22-B. */
  result_state: ExecutionResultState;
  /** Empty for a recorded request; the failed precondition codes when blocked. */
  block_reasons: BlockReasonCode[];
  /** Operational outcome (recorded | blocked | denied | conflict | duplicate). */
  result: ExecutionRequestResult;
  /** Human-readable outcome; states not-executed. */
  message: string;
  /** Always 'memory' in P22-B skeleton. */
  storage: string;
  /** Always false -- P22-B never executes. */
  executed: boolean;
  /** Always false -- P22-B never starts execution. */
  execution_started: boolean;
  /** Always false in P22-B. */
  execution_allowed: boolean;
  /** UTC ISO-8601. */
  created_at: string | null;
  /** UTC ISO-8601. */
  updated_at: string | null;
}

/** Ephemeral operator queue of recorded execution requests. Read-only. */
export interface ExecutionRequestQueue {
  items: ExecutionRequestResponse[];
  total: number;
  limit: number;
  offset: number;
  /** Always 'memory' in P22-B skeleton. */
  storage: string;
  /** Always false -- listing never executes. */
  executed: boolean;
}

// -- backup.check read-only source probe (P22-E3/E4) -------------------------

/**
 * The honest one-line backup verdict the P22-E3 source probe derives from the
 * P17-D-C source (P22-E4 surfaces this in the console). `unavailable` is the
 * fail-closed case for a source read failure; `unknown` is the no-outcome case.
 */
export type BackupCheckSummary =
  | 'fresh_success'
  | 'stale'
  | 'failed'
  | 'partial'
  | 'in_progress'
  | 'unknown'
  | 'unavailable';

/**
 * The READ-ONLY, NON-EXECUTING result of binding backup.check to the proven
 * P17-D-C backup / status source (P22-E3). Every execution flag is ALWAYS false
 * and result_state is ALWAYS 'blocked': this is a read, not an execution.
 *
 * Field-for-field aligned to backend/api/v1/platform/p22/source_probe.py
 * `BackupCheckSourceRead`. Only allowlisted, echo-safe fields are modelled --
 * never raw logs, DSNs, host/port/path, command lines, secrets, or raw failure
 * text; `failure_reason_redacted` is the closed allowlisted reason code only.
 */
export interface BackupCheckSourceRead {
  action_type: 'backup.check';
  action_class: 'read';
  /** Always 'read_only_source_probe'. */
  binding: 'read_only_source_probe';
  /** Always 'not_implemented' -- the adapter (execution) is not realized. */
  adapter_result: 'not_implemented';
  /** known | unknown | degraded. Unknown is never healthy. */
  source_status: ExecutionSourceStatus;
  /** The honest one-line P17-derived verdict (incl. 'unavailable'). */
  source_summary: BackupCheckSummary;
  /** Freshness-routed verdict: success | partial | failed | in_progress | stale. */
  last_backup_status: string | null;
  /** UTC ISO-8601, or null. */
  last_backup_at: string | null;
  /** passed | failed | stale | unknown, or null. */
  restore_test_status: string | null;
  /** UTC ISO-8601, or null. */
  last_restore_test_at: string | null;
  /** Allowlisted BACKUP_FAILURE_REASONS code only; never the raw reason. */
  failure_reason_redacted: string | null;
  /** A restorable dump exists, or null. */
  export_available: boolean | null;
  /** Policy label, or null. */
  retention_policy: string | null;
  /** The P17 vocabulary mirror: available | unavailable | unknown. */
  p17_backup_source_status: string | null;
  /** Always false -- a read is not execution. */
  realizes_execution: boolean;
  /** Always false. */
  executed: boolean;
  /** Always false. */
  execution_started: boolean;
  /** Always false. */
  execution_allowed: boolean;
  /** Always 'blocked' (never executed). */
  result_state: 'blocked';
  /** Always true. */
  read_only: boolean;
  /** Always true. */
  redaction_applied: boolean;
  /** The honest reason when source_status is unknown / unavailable. */
  reason: string | null;
  /** UTC ISO-8601. */
  checked_at: string;
}
