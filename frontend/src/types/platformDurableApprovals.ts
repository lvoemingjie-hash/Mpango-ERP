/**
 * P20 Durable Approval Governance types (frontend console, P20-C).
 *
 * Field-for-field aligned to
 * docs/ai/PLATFORM_PRODUCT_P20_DURABLE_APPROVAL_GOVERNANCE_CONTRACT.md (P20-A)
 * and the backend P20 schemas
 * (backend/api/v1/platform/p20/schemas.py, P20-B skeleton).
 *
 * DURABILITY IS NOT EXECUTION. A quorum-met durable approval resolves to
 * approved_execution_blocked; it never runs the wrapped P18 action and never
 * mutates any tenant state. Every record and queue item carries
 * execution_allowed === false, execution_gate === 'blocked', and
 * executed === false. These types describe the durable approval read / write /
 * decide surface only -- there is no execution shape here.
 *
 * Maker-checker + quorum: the maker (the authenticated identity-only
 * super_admin who opened the request) can never be a checker; each checker is a
 * distinct identity-only super_admin; a write / write_request needs two distinct
 * approve checkers (excluding the maker) and a read needs one.
 *
 * RegistrySourceStatus is reused verbatim from the P18 controlled-actions types
 * so the P18 source-status vocabulary stays the single source of truth.
 */
export type { RegistrySourceStatus } from './platformControlledActions';
import type { RegistrySourceStatus } from './platformControlledActions';

/**
 * P20-A section 6 -- the durable approval lifecycle states. P20-B implements
 * only the first three (pending_review, approved_execution_blocked, rejected);
 * the remaining four are schema-only in P20 and any transition toward them is
 * rejected by the service layer.
 */
export type DurableApprovalState =
  | 'pending_review'
  | 'approved_execution_blocked'
  | 'rejected'
  | 'expired'
  | 'cancelled'
  | 'superseded'
  | 'failed_validation';

/** An approve / reject decision recorded by one checker. */
export type DurableApprovalDecisionType = 'approve' | 'reject';

/** P18 action classification; drives the quorum floor. */
export type DurableActionClass = 'read' | 'write' | 'write_request';

/**
 * Operational outcome of a create / decision call (analogous to the P18 / P19
 * result enum). Carried on the response record so denials / duplicates /
 * conflicts / quorum-pending states are observable without a persisted change.
 */
export type DurableApprovalResult =
  | 'recorded'
  | 'approved'
  | 'rejected'
  | 'denied'
  | 'duplicate'
  | 'conflict'
  | 'not_found'
  | 'quorum_pending';

/** Execution readiness gate (P20-A 5.2). Always 'blocked' in P20. */
export type DurableExecutionGate = 'blocked' | 'not_authorized';

/** Durable re-validation result (P20-A 3.1 / 3.6). */
export type DurableValidationStatus = 'valid' | 'source_unknown' | 'superseded_scope' | 'stale';

/** Retention class (P20-A 3.1 / 3.5). */
export type DurableRetentionClass = 'standard' | 'long' | 'legal_hold';

/**
 * Echo-safe summary of one checker's recorded decision. The checker's reason is
 * redacted. The raw decision idempotency_key is never stored; only its SHA-256
 * digest is held internally by the backend (never echoed here).
 */
export interface CheckerDecisionSummary {
  checker_id: string;
  decided_at: string;
  decision: DurableApprovalDecisionType;
  reason_redacted: string;
  audit_event_id: string | null;
}

/**
 * Inbound body to open a durable approval request
 * (POST /durable-approvals). Mirrors the backend
 * DurableApprovalCreateRequest. Fields are optional on the wire so a missing
 * required value yields a contract-shaped denied record (mirroring P18 / P19)
 * rather than a 422 transport error.
 *
 * The maker binds to the authenticated identity-only super_admin actor on the
 * server (P20-B-R1); the client sends it as an explicit assertion that MUST
 * equal the authenticated actor. Raw client values are never echoed raw by the
 * backend (reason / idempotency_key / correlation_id are redacted; only the
 * idempotency_key DIGEST is ever returned).
 */
export interface DurableApprovalCreateRequest {
  action_id?: string | null;
  tenant_id?: string | null;
  action_type?: string | null;
  maker?: string | null;
  reason?: string | null;
  idempotency_key?: string | null;
  expires_at?: string | null;
  durable_retain_until?: string | null;
  confirm: boolean;
  correlation_id?: string | null;
  metadata?: Record<string, unknown> | null;
}

/**
 * Inbound body for one checker to approve or reject a pending durable approval
 * (POST /durable-approvals/{approval_id}/decisions). The approver binds to the
 * authenticated identity-only super_admin actor on the server and MUST differ
 * from the approval's maker (maker-checker separation).
 */
export interface DurableApprovalDecisionRequest {
  decision: DurableApprovalDecisionType;
  approver_id?: string | null;
  reason?: string | null;
  idempotency_key?: string | null;
  confirm: boolean;
  correlation_id?: string | null;
  metadata?: Record<string, unknown> | null;
}

/**
 * Stored durable approval record and uniform response for create / read /
 * decision. Carries the P20-A required fields plus operational fields. The
 * execution invariants are always: execution_allowed === false,
 * execution_gate === 'blocked', executed === false, redaction_applied === true,
 * storage === 'memory'. idempotency_key_digest is the one-way SHA-256 digest of
 * the create idempotency key (the raw key is never stored / echoed).
 */
export interface DurableApprovalRecord {
  approval_id: string | null;
  action_id: string | null;
  tenant_id: string | null;
  action_type: string | null;
  action_class: DurableActionClass | null;
  state: DurableApprovalState | null;
  maker: string | null;
  maker_at: string | null;
  checkers: CheckerDecisionSummary[];
  quorum_required: number;
  quorum_met: boolean;
  decision: DurableApprovalDecisionType | null;
  reason: string;
  request_digest: string | null;
  /** One-way SHA-256 digest of the create idempotency key; raw key never echoed. */
  idempotency_key_digest: string | null;
  expires_at: string | null;
  durable_retain_until: string | null;
  /** Always false in P20 -- a durable approval never permits execution. */
  execution_allowed: boolean;
  /** Always 'blocked' in P20. */
  execution_gate: DurableExecutionGate;
  /** Always true -- reason / metadata are redacted via the P18 allowlist. */
  redaction_applied: boolean;
  /** In-memory only; no database persistence in P20. */
  storage: string;
  retention_class: DurableRetentionClass;
  validation_status: DurableValidationStatus;
  superseded_by: string | null;
  previous_state: DurableApprovalState | null;
  audit_event_id: string | null;
  correlation_id: string | null;
  /** Inherited P18 source status; unknown is never fabricated as available. */
  source_status: RegistrySourceStatus;
  result: DurableApprovalResult;
  message: string;
  /** Always false -- a durable approval never executes. */
  executed: boolean;
  created_at: string | null;
  updated_at: string | null;
}

/** Ephemeral operator queue of durable approval records. Read-only; never executes. */
export interface DurableApprovalQueue {
  items: DurableApprovalRecord[];
  total: number;
  limit: number;
  offset: number;
  /** In-process storage; no database persistence. */
  storage: string;
  /** Always false -- listing the queue never executes. */
  executed: boolean;
}
