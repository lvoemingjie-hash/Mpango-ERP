/**
 * Neutrality capture for F3/F4/F5 (task directive #10; B1-R3 canonicalization).
 *
 * The forgot-password response is intercepted in the browser context. The raw
 * body text exists ONLY inside the route handler's local scope: it is parsed
 * and canonicalized by src/neutrality-core.ts (the real contract module) and
 * released immediately — the in-memory store keeps nothing but the canonical
 * fingerprint (HTTP status, SHA-256 and byte length of the SENTINEL-stable
 * canonical serialization). The raw body, the timestamp value and the full
 * envelope are never stored, logged or written to any artifact; failure
 * messages carry fixed category or field names only.
 *
 * See R4-NEUTRALITY-PROTOCOL-CORRECTION.md: the superseding contract ignores
 * only the top-level timestamp VALUE; raw-byte equality is superseded.
 */

import type { Page } from '@playwright/test';
import { a1State } from './token-store.js';
import {
  canonicalizeNeutralEnvelope,
  sameCanonicalFingerprint,
  firstCanonicalDifference,
  pinnedMessageMatches,
  NEUTRAL_ENVELOPE_KEYS,
  NEUTRAL_MESSAGE_CONSTANT,
  TIMESTAMP_SENTINEL,
  NeutralEnvelopeError,
  type CanonicalFingerprint,
} from './neutrality-core.js';

export {
  canonicalizeNeutralEnvelope,
  sameCanonicalFingerprint,
  firstCanonicalDifference,
  pinnedMessageMatches,
  NEUTRAL_ENVELOPE_KEYS,
  NEUTRAL_MESSAGE_CONSTANT,
  TIMESTAMP_SENTINEL,
  NeutralEnvelopeError,
};
export type { CanonicalFingerprint };

/** Backwards-compatible alias for the journey state's stored fingerprint. */
export type ResponseFingerprint = CanonicalFingerprint;

/** Legacy-free comparison surface used by the spec (F3/F4/F5). */
export const sameFingerprint = sameCanonicalFingerprint;
export const firstFingerprintDifference = firstCanonicalDifference;

/**
 * Install a one-shot interceptor on the forgot-password endpoint. The route
 * passes the real response through unchanged while recording only the
 * CANONICAL fingerprint of the first matching response into the in-memory
 * store. The raw body text never leaves this handler's local scope.
 */
export async function captureForgotFingerprint(
  page: Page,
  label: 'F3' | 'F4' | 'F5',
): Promise<void> {
  await page.route('**/api/v1/auth/forgot-password', async (route) => {
    const response = await route.fetch();
    // Local scope only: raw text is canonicalized and released here.
    const body = await response.text();
    a1State().fingerprints[label] = canonicalizeNeutralEnvelope(response.status(), body);
    await route.fulfill({ response });
  });
}
