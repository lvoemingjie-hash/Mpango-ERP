/**
 * P12 Support Console types -- matches backend p12/schemas.py exactly.
 *
 * Every field, nullable behavior, and enum value mirrors the P12 backend
 * data contracts (P12-A-R1, P12-B, P12-B-R3).
 *
 * IMPORTANT CONTRACT NOTE:
 *   CreateSessionRequest.reason is Optional[str] in the backend Pydantic
 *   schema ONLY to allow the route layer to return 400 with a
 *   support_access_denied audit event instead of a bare 422 from Pydantic.
 *   The frontend MUST require reason (minimum 10 characters) before making
 *   the API call. The backend schema relaxation is an implementation detail,
 *   NOT a contract change. P12-C frontend must enforce reason as required.
 */

// -- Enums matching P12-A-R1 contract exactly --

export type SupportCategory =
  | 'login_issue'
  | 'activity_anomaly'
  | 'performance'
  | 'data_integrity'
  | 'integration'
  | 'general'
  | 'incident'
  | 'other';

export type SupportSessionStatus = 'active' | 'closed' | 'expired';

export type BundleType = 'full' | 'technical' | 'summary';

export type DiagnosticSourceStatus = 'available' | 'degraded' | 'unavailable' | 'unknown';

// -- Error shapes for P12-B-R3 reason contract --

export type SupportErrorCode =
  | 'MISSING_REASON'
  | 'REASON_TOO_SHORT'
  | 'SESSION_NOT_FOUND'
  | 'SESSION_NOT_ACTIVE'
  | 'SESSION_ALREADY_CLOSED'
  | 'SESSION_CREATE_FAILED'
  | 'DIAGNOSTICS_ERROR'
  | 'BUNDLE_ERROR'
  | 'CLOSE_ERROR';

export interface SupportErrorDetail {
  code: SupportErrorCode;
  message: string;
}

// -- Request models --

/**
 * Frontend request body for creating a support session.
 *
 * Unlike the backend schema, reason is required here (string, not Optional).
 * The frontend enforces min 10 chars client-side BEFORE the API call.
 * The backend accepts Optional only as an implementation detail for
 * route-layer 400 + audit coverage (P12-B-R3).
 */
export interface CreateSessionRequest {
  reason: string;
  category: SupportCategory;
  tenant_id?: string | null;
}

export interface CreateBundleRequest {
  bundle_type: BundleType;
}

// -- Response models --

export interface SupportSession {
  session_id: string;
  actor_id: string | null;
  actor_role: string | null;
  tenant_id: string | null;
  reason: string;
  category: SupportCategory;
  correlation_id: string | null;
  status: SupportSessionStatus;
  started_at: string;
  closed_at: string | null;
  expires_at: string | null;
  bundle_count: number;
}

export interface SupportDiagnosticItem {
  item_id: string;
  bundle_id: string | null;
  category: string;
  label: string;
  value: unknown;
  source_status: DiagnosticSourceStatus;
  collected_at: string;
}

export interface SupportBundle {
  bundle_id: string;
  session_id: string;
  actor_id: string | null;
  tenant_id: string | null;
  correlation_id: string | null;
  generated_at: string;
  diagnostics: SupportDiagnosticItem[];
  redaction_applied: boolean;
  bundle_type: BundleType;
}

// -- Helpers --

/** Minimum reason length enforced client-side (matches backend contract). */
export const REASON_MIN_LENGTH = 10;

/**
 * Validate support reason client-side.
 * Returns true only if reason is non-null, non-empty, and >= 10 chars.
 * Frontend MUST call this before createSession API call.
 */
export function isReasonValid(reason: string | null | undefined): boolean {
  if (!reason) return false;
  return reason.trim().length >= REASON_MIN_LENGTH;
}

/**
 * Get validation message for invalid reason.
 * Returns null if reason is valid.
 */
export function getReasonValidationError(reason: string | null | undefined): string | null {
  if (!reason || reason.trim().length === 0) {
    return 'Support reason is required.';
  }
  if (reason.trim().length < REASON_MIN_LENGTH) {
    return `Support reason must be at least ${REASON_MIN_LENGTH} characters (currently ${reason.trim().length}).`;
  }
  return null;
}
