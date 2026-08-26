/**
 * B1-R3 semantic neutrality canonicalizer — the REAL contract implementation.
 *
 * CTO ruling (2026-08-25, V3 evidence 888fd207): the V2/V3-era raw-body byte
 * equality contract was over-constrained because the platform's neutral
 * envelope carries a generic per-request top-level `timestamp`. This module
 * canonicalizes the forgot-password neutral envelope for F3/F4/F5 comparison
 * under the SUPERSEDING contract:
 *
 *  1. HTTP status compared exactly (F3/F4/F5 must all be 200).
 *  2. The top-level JSON key set must be EXACTLY {success, data, message,
 *     timestamp} — no missing key, no extra key (any added key, including
 *     accountExists / eligible / userId / tenant / request_id, is a
 *     contract violation).
 *  3. success must be the boolean true.
 *  4. data must be exactly the empty object (no keys).
 *  5. message must be identical across F3/F4/F5 (it is part of the canonical
 *     payload) and equal the existing product neutral constant (asserted per
 *     node through pinnedMessageMatches).
 *  6. timestamp must be present in every envelope, be a string, and parse as
 *     a valid time.
 *  7. ONLY the timestamp VALUE is ignored. This is implemented by replacing
 *     the top-level timestamp with a fixed sentinel and serializing the four
 *     fields in a fixed order — NOT by a generic key deleter, a regex
 *     blacklist, or recursive field ignoring (all banned).
 *  8. Canonical SHA-256 and canonical byte length must be pairwise equal
 *     across F3/F4/F5.
 *
 * Failure messages carry fixed category strings ONLY — never the raw body,
 * never a timestamp value, never an email (see NeutralEnvelopeError).
 *
 * This module is deliberately dependency-free apart from node:crypto so the
 * executable neutrality contract check (tools/check-neutrality.mjs) can
 * transpile and exercise it directly.
 */

import { createHash } from 'node:crypto';

/** The exact top-level key set of the neutral envelope (contract #2). */
export const NEUTRAL_ENVELOPE_KEYS = ['success', 'data', 'message', 'timestamp'] as const;

/**
 * The existing product neutral constant (backend
 * services/password_reset_service.py NEUTRAL_PASSWORD_RESET_MESSAGE). The
 * harness pins it so any product-side drift in the neutral message fails the
 * contract instead of silently passing (contract #5).
 */
export const NEUTRAL_MESSAGE_CONSTANT =
  'Password reset result is not disclosed through this endpoint.';

/**
 * Fixed sentinel substituted for the top-level timestamp VALUE before stable
 * serialization (contract #7). It is a non-date string on purpose: it never
 * parses as a time, so a sentinel leaking back into validation would fail
 * closed rather than accidentally satisfy the timestamp format check.
 */
export const TIMESTAMP_SENTINEL = 'CANONICAL_TIMESTAMP_SENTINEL_B1_R3';

/** Fixed failure categories — the only strings allowed in failure output. */
export type NeutralEnvelopeCategory =
  | 'top_level_key_set'
  | 'success_value'
  | 'data_nonempty'
  | 'message_type'
  | 'timestamp_missing'
  | 'timestamp_not_string'
  | 'timestamp_unparseable'
  | 'status_non_200';

/**
 * Error whose message is ALWAYS a fixed category — by construction it can
 * never carry envelope content, a timestamp value, or an email.
 */
export class NeutralEnvelopeError extends Error {
  public readonly category: NeutralEnvelopeCategory;
  constructor(category: NeutralEnvelopeCategory) {
    super(`neutral envelope contract violation: ${category}`);
    this.name = 'NeutralEnvelopeError';
    this.category = category;
  }
}

/**
 * Canonical fingerprint — the ONLY retained form of a neutral response.
 * `message` is retained because it is PUBLIC product copy (the neutral
 * constant): it lets the journey assert the pinned-constant contract (#5)
 * per node while the canonical sha (which includes the message) enforces
 * cross-node message equality (#5/#8).
 */
export interface CanonicalFingerprint {
  status: number;
  message: string;
  canonicalSha256: string;
  canonicalLengthBytes: number;
}

/**
 * Contract #5 (equal to the EXISTING product neutral constant) is a separate
 * predicate so it is enforced per node by the spec (F3/F4/F5) and stays
 * independently executable/mutable-testable.
 */
export function pinnedMessageMatches(fingerprint: CanonicalFingerprint): boolean {
  return fingerprint.message === NEUTRAL_MESSAGE_CONSTANT;
}

function sha256(text: string): string {
  return createHash('sha256').update(text, 'utf8').digest('hex');
}

/**
 * Canonicalize one neutral envelope (contract #2–#7).
 *
 * The raw body text exists ONLY inside this function; the caller receives
 * the canonical fingerprint and nothing that could reconstruct the body.
 * Throws NeutralEnvelopeError with a fixed category on any violation.
 */
export function canonicalizeNeutralEnvelope(status: number, bodyText: string): CanonicalFingerprint {
  if (status !== 200) {
    throw new NeutralEnvelopeError('status_non_200');
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(bodyText);
  } catch {
    // A non-JSON body cannot even carry the required key set.
    throw new NeutralEnvelopeError('top_level_key_set');
  }
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
    throw new NeutralEnvelopeError('top_level_key_set');
  }
  const envelope = parsed as Record<string, unknown>;

  // Contract #2: exact key set — no more, no fewer. Checked by explicit
  // membership against the frozen key list; there is deliberately NO code
  // path that deletes, filters, or generally ignores unexpected keys. A
  // MISSING timestamp gets its precise category (contract #6 presence
  // requirement) instead of the generic set category; every other key-set
  // deviation (extra key or other missing key) is 'top_level_key_set'.
  const present = Object.keys(envelope);
  const expected = [...NEUTRAL_ENVELOPE_KEYS];
  if (!expected.every((key) => key in envelope)) {
    if (!('timestamp' in envelope)) {
      throw new NeutralEnvelopeError('timestamp_missing');
    }
    throw new NeutralEnvelopeError('top_level_key_set');
  }
  if (present.length !== expected.length) {
    throw new NeutralEnvelopeError('top_level_key_set');
  }

  // Contract #3: success === true.
  if (envelope.success !== true) {
    throw new NeutralEnvelopeError('success_value');
  }

  // Contract #4: data is exactly the empty object.
  const data = envelope.data;
  if (
    typeof data !== 'object' ||
    data === null ||
    Array.isArray(data) ||
    Object.keys(data).length !== 0
  ) {
    throw new NeutralEnvelopeError('data_nonempty');
  }

  // Contract #5 (type half): message must be a string. Its VALUE travels
  // into the canonical payload below, so cross-node canonical equality
  // enforces message equality; the pinned-constant half of contract #5 is
  // the separate pinnedMessageMatches predicate asserted by every node.
  if (typeof envelope.message !== 'string') {
    throw new NeutralEnvelopeError('message_type');
  }

  // Contract #6: timestamp present, string, parseable valid time.
  const timestamp = envelope.timestamp;
  if (timestamp === undefined) {
    throw new NeutralEnvelopeError('timestamp_missing');
  }
  if (typeof timestamp !== 'string') {
    throw new NeutralEnvelopeError('timestamp_not_string');
  }
  if (timestamp.length === 0 || Number.isNaN(Date.parse(timestamp))) {
    throw new NeutralEnvelopeError('timestamp_unparseable');
  }

  // Contract #7: replace ONLY the top-level timestamp value with the fixed
  // sentinel, then serialize the four fields in a fixed order.
  const canonicalText = JSON.stringify({
    success: envelope.success,
    data: {},
    message: envelope.message,
    timestamp: TIMESTAMP_SENTINEL,
  });

  // Contract #8: equality is over the stable canonical serialization.
  return {
    status,
    message: envelope.message,
    canonicalSha256: sha256(canonicalText),
    canonicalLengthBytes: Buffer.byteLength(canonicalText, 'utf8'),
  };
}

/** Pairwise canonical equality (status + canonical sha + canonical length). */
export function sameCanonicalFingerprint(
  left: CanonicalFingerprint,
  right: CanonicalFingerprint,
): boolean {
  return (
    left.status === right.status &&
    left.canonicalSha256 === right.canonicalSha256 &&
    left.canonicalLengthBytes === right.canonicalLengthBytes
  );
}

/** First differing canonical field — fixed field names only. */
export function firstCanonicalDifference(
  left: CanonicalFingerprint,
  right: CanonicalFingerprint,
): 'status' | 'canonicalLengthBytes' | 'canonicalSha256' | 'none' {
  if (left.status !== right.status) return 'status';
  if (left.canonicalLengthBytes !== right.canonicalLengthBytes) return 'canonicalLengthBytes';
  if (left.canonicalSha256 !== right.canonicalSha256) return 'canonicalSha256';
  return 'none';
}
