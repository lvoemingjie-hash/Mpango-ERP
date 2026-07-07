/**
 * P19 Controlled Action Approval Workflow types (frontend console, P19-C).
 *
 * Field-for-field aligned to
 * docs/ai/PLATFORM_PRODUCT_P19_APPROVAL_WORKFLOW_CONTRACT.md (P19-A) and the
 * backend P19 schemas (backend/api/v1/platform/p19/schemas.py, P19-B skeleton).
 *
 * APPROVAL IS NOT EXECUTION. An approved approval resolves to
 * execution_blocked; it never runs the wrapped P18 action and never mutates any
 * tenant state. Every record and queue item carries execution_allowed === false
 * and executed === false. These types describe the approval read / write /
 * decide surface only -- there is no execution shape here.
 *
 * RegistrySourceStatus is reused verbatim from the P18 controlled-actions
 * types so the P18 source-status vocabulary stays the single source of truth.
 */
import type { RegistrySourceStatus } from './platformControlledActions';
export type { RegistrySourceStatus };

/** P19-A section 3 -- the seven approval lifecycle states. */
export type ApprovalState =
  | 'requested'
  | 'pending_review'
  | 'approved'
  | 'rejected'
  | 'expired'
  | 'cancelled'
  | 'execution_blocked';

/** An approve / reject decision. */
export type ApprovalDecisionType = 'approve' | 'reject';

/**
 * Operational outcome of a create / decision call (analogous to the P18 result
 * enum). Carried on the response record so denials / duplicates / conflicts are
 * observable without a persisted state change.
 */
export type ApprovalResult =
  | 'recorded'
  | 'approved'
  | 'rejected'
  | 'denied'
  | 'duplicate'
  | 'conflict'
  | 'expired'
  | 'cancelled'
  | 'not_found';

/**
 * Inbound body to open an approval request (POST /approvals). Mirrors the
 * backend ControlledActionApprovalRequest. Fields are optional on the wire so a
 * missing required value yields a contract-shaped denied record (mirroring P18)
 * rather than a 422 transport error. Raw client values are never echoed raw by
 * the backend (reason / idempotency_key / correlation_id are redacted).
 */
export interface ControlledActionApprovalRequest {
  action_id?: string | null;
  tenant_id?: string | null;
  action_type?: string | null;
  requested_by?: string | null;
  reason?: string | null;
  idempotency_key?: string | null;
  expires_at?: string | null;
  confirm: boolean;
  correlation_id?: string | null;
  metadata?: Record<string, unknown> | null;
}

/**
 * Inbound body to approve or reject a pending approval
 * (POST /{approval_id}/decision). Only an identity-only super_admin may supply
 * a valid decision; the reused P10 guard enforces that at runtime.
 */
export interface ControlledActionApprovalDecision {
  decision: ApprovalDecisionType;
  reviewed_by?: string | null;
  reason?: string | null;
  idempotency_key?: string | null;
  confirm: boolean;
  correlation_id?: string | null;
  metadata?: Record<string, unknown> | null;
}

/**
 * Stored approval record and uniform response for create / read / decision.
 *
 * Carries every P19-A required field (action_id, approval_id, tenant_id,
 * action_type, state, requested_by, requested_at, reviewed_by, reviewed_at,
 * decision, reason, expires_at, execution_allowed, redaction_applied,
 * idempotency_key, source_status, previous_state, storage, audit_event_id,
 * correlation_id, created_at, updated_at) plus the operational fields the UI
 * surfaces (result, message, executed). execution_allowed and executed are
 * always false.
 */
export interface ControlledActionApprovalRecord {
  action_id: string | null;
  approval_id: string | null;
  tenant_id: string | null;
  action_type: string | null;
  state: ApprovalState | null;
  requested_by: string | null;
  requested_at: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  decision: ApprovalDecisionType | null;
  reason: string;
  expires_at: string | null;
  /** Always false in P19 -- approval never permits execution. */
  execution_allowed: boolean;
  /** Always true -- reason / metadata are redacted via the P18 allowlist. */
  redaction_applied: boolean;
  /** Echo-safe (sanitized) idempotency key; the raw key is never returned. */
  idempotency_key: string | null;
  /** Inherited P18 source status; unknown is never fabricated as available. */
  source_status: RegistrySourceStatus;
  previous_state: ApprovalState | null;
  /** In-memory only; no database persistence in P19. */
  storage: string;
  audit_event_id: string | null;
  correlation_id: string | null;
  result: ApprovalResult;
  message: string;
  /** Always false -- approval never executes. */
  executed: boolean;
  created_at: string | null;
  updated_at: string | null;
}

/** Ephemeral operator queue of approval records. Read-only; never executes. */
export interface ControlledActionApprovalQueue {
  items: ControlledActionApprovalRecord[];
  total: number;
  limit: number;
  offset: number;
  /** In-process storage; no database persistence. */
  storage: string;
  /** Always false -- listing the queue never executes. */
  executed: boolean;
}
