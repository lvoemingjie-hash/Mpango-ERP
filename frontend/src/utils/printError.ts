/**
 * DC-12R1-S3-S2B-I2C-I2 — Status-only error sanitizer for print views.
 *
 * Maps an HTTP status to a fixed, neutral, user-facing string. It deliberately
 * NEVER inspects or echoes the response body, headers, or any server-provided
 * code/message/detail. This guarantees that print/receipt views never leak:
 *   - internal identifiers (payment row UUID, tenant_user_id, schema names),
 *   - eligibility/payment/binding state,
 *   - another supplier's data, or
 *   - raw server error text.
 *
 * The existing normalizeApiError() is reused elsewhere and left unedited
 * (HIGH-impact, 15 dependants). Print views use this stricter sanitizer because
 * their failure modes (especially /receipt 404) must be uniformly neutral.
 */
import type { AxiosError } from 'axios';

export type PrintViewKind = 'order' | 'declaration' | 'receipt';

const NEUTRAL_MESSAGES = {
  /** 401 — session expired / not authenticated. */
  auth: 'Please sign in to view this document.',
  /** 403 — authenticated but not allowed to see this record. */
  forbidden: 'You do not have access to this document.',
  /** 404 — record missing, belongs to another party, or (for receipts) not eligible. */
  notFound: 'This document is not available.',
  /** 5xx / network / unknown. */
  unavailable: 'We couldn’t load this document. Please try again later.',
} as const;

/**
 * Returns a neutral, status-derived message. Only the HTTP status (and a coarse
 * network/no-response signal) is consulted — never the body. `kind` is accepted
 * for future copy tuning but the default wording stays uniform so that, e.g., a
 * /receipt 404 is indistinguishable from any other not-available case.
 */
export function sanitizePrintError(error: unknown, _kind?: PrintViewKind): string {
  const axErr = error as AxiosError;
  const status = axErr?.response?.status;

  if (status === 401) return NEUTRAL_MESSAGES.auth;
  if (status === 403) return NEUTRAL_MESSAGES.forbidden;
  if (status === 404) return NEUTRAL_MESSAGES.notFound;
  if (status !== undefined && status >= 500) return NEUTRAL_MESSAGES.unavailable;

  // No response object at all → network/timeout/unknown. Neutral fallback.
  if (axErr && typeof axErr === 'object' && 'request' in axErr) {
    return NEUTRAL_MESSAGES.unavailable;
  }
  return NEUTRAL_MESSAGES.unavailable;
}
