/**
 * Retailer canonical-neutrality canonicalizer — the REAL contract
 * implementation for HC07-HC10 (POST /api/v1/client/auth/forgot-password).
 *
 * Frozen contract (H2-C-R0-R1 canonical neutrality):
 *  1. HTTP status compared exactly (all four states must be 200).
 *  2. The top-level JSON key set must be EXACTLY {success, data, message,
 *     timestamp} — no missing key, no extra key.
 *  3. success must be the boolean true.
 *  4. data must be exactly the empty object.
 *  5. message must equal the pinned product constant
 *     NEUTRAL_RETAILER_CREDENTIAL_MESSAGE.
 *  6. timestamp must be present, be a string, and parse as a valid time.
 *  7. ONLY the timestamp VALUE is replaced by a fixed sentinel before a
 *     stable serialization — NOT a generic key deleter, regex blacklist or
 *     recursive field ignoring (all banned).
 *  8. Canonical SHA-256 and canonical byte length must be pairwise equal
 *     across the four states; raw bodies are released immediately and only
 *     the canonical fingerprint is retained.
 *
 * Failure messages carry fixed category strings ONLY — never the raw body,
 * a timestamp value, or an email.
 *
 * Dependency-free apart from node:crypto so tools/check-neutrality.mjs can
 * transpile and exercise this module directly.
 */

import { createHash } from 'node:crypto';

export const NEUTRAL_ENVELOPE_KEYS = ['success', 'data', 'message', 'timestamp'] as const;

/**
 * The product neutral constant (backend api/v1/client/auth.py
 * NEUTRAL_RETAILER_CREDENTIAL_MESSAGE). Pinned so product-side drift fails
 * the contract instead of silently passing.
 */
export const NEUTRAL_MESSAGE_CONSTANT =
  'Retailer credential result is not disclosed through this endpoint.';

/** Non-date sentinel: never parses as a time, so leakage fails closed. */
export const TIMESTAMP_SENTINEL = 'CANONICAL_TIMESTAMP_SENTINEL_H2C_B1';

export type NeutralEnvelopeCategory =
  | 'STATUS'
  | 'KEY_SET'
  | 'SUCCESS_VALUE'
  | 'DATA_VALUE'
  | 'MESSAGE_VALUE'
  | 'TIMESTAMP_MISSING'
  | 'TIMESTAMP_UNPARSABLE'
  | 'TIMESTAMP_TYPE'
  | 'FINGERPRINT_MISMATCH';

export class NeutralEnvelopeError extends Error {
  readonly category: NeutralEnvelopeCategory;
  constructor(category: NeutralEnvelopeCategory, detailField: string) {
    // detailField names a FIELD, never a value.
    super(`neutral-envelope:${category}:${detailField}`);
    this.category = category;
    this.name = 'NeutralEnvelopeError';
  }
}

export interface CanonicalFingerprint {
  /** SHA-256 of the stable canonical serialization. */
  sha256: string;
  /** Byte length of the canonical serialization. */
  byteLength: number;
}

/** Validate one raw envelope and return ONLY its canonical fingerprint. */
export function canonicalFingerprint(raw: unknown): CanonicalFingerprint {
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) {
    throw new NeutralEnvelopeError('KEY_SET', 'body');
  }
  const body = raw as Record<string, unknown>;
  const keySet = Object.keys(body).sort().join(',');
  const expectedKeySet = [...NEUTRAL_ENVELOPE_KEYS].sort().join(',');
  if (keySet !== expectedKeySet) {
    throw new NeutralEnvelopeError('KEY_SET', 'body.keys');
  }
  if (body.success !== true) {
    throw new NeutralEnvelopeError('SUCCESS_VALUE', 'success');
  }
  const data = body.data;
  if (
    typeof data !== 'object' ||
    data === null ||
    Array.isArray(data) ||
    Object.keys(data).length !== 0
  ) {
    throw new NeutralEnvelopeError('DATA_VALUE', 'data');
  }
  if (body.message !== NEUTRAL_MESSAGE_CONSTANT) {
    throw new NeutralEnvelopeError('MESSAGE_VALUE', 'message');
  }
  const ts = body.timestamp;
  if (ts === undefined || ts === null) {
    throw new NeutralEnvelopeError('TIMESTAMP_MISSING', 'timestamp');
  }
  if (typeof ts !== 'string') {
    throw new NeutralEnvelopeError('TIMESTAMP_TYPE', 'timestamp');
  }
  if (Number.isNaN(Date.parse(ts))) {
    throw new NeutralEnvelopeError('TIMESTAMP_UNPARSABLE', 'timestamp');
  }
  const canonical: Record<string, unknown> = {
    data: body.data,
    message: body.message,
    success: body.success,
    timestamp: TIMESTAMP_SENTINEL, // ONLY the timestamp value is replaced
  };
  const serialized = JSON.stringify(canonical);
  return {
    sha256: createHash('sha256').update(serialized, 'utf8').digest('hex'),
    byteLength: Buffer.byteLength(serialized, 'utf8'),
  };
}

/** Pairwise equality of fingerprints with a single fixed category. */
export function assertFingerprintsEqual(
  a: CanonicalFingerprint,
  b: CanonicalFingerprint,
): void {
  if (a.sha256 !== b.sha256 || a.byteLength !== b.byteLength) {
    throw new NeutralEnvelopeError('FINGERPRINT_MISMATCH', 'canonical.sha256');
  }
}
