/**
 * Per-node neutrality application (HC07-HC10).
 *
 * Wraps neutrality-core over the page's real network responses: the four
 * outcome states each keep ONLY the canonical fingerprint; the raw body is
 * released immediately after fingerprinting and never stored, logged or
 * written to artifacts.
 */

import type { Response as PlaywrightResponse } from '@playwright/test';
import {
  CanonicalFingerprint,
  NeutralEnvelopeError,
  assertFingerprintsEqual,
  canonicalFingerprint,
} from './neutrality-core.js';
import { fieldOnly } from './assertions.js';

export async function fingerprintNeutralResponse(
  response: PlaywrightResponse,
): Promise<CanonicalFingerprint> {
  if (response.status() !== 200) {
    throw fieldOnly('http', 'status', 'expected_200');
  }
  let raw: unknown;
  try {
    raw = await response.json();
  } catch {
    throw fieldOnly('http', 'body', 'not_json');
  }
  const fingerprint = canonicalFingerprint(raw);
  // Raw body goes out of scope here; only the fingerprint survives.
  return fingerprint;
}

export function assertFourStateCanonicalEquality(
  fingerprints: Record<'HC07' | 'HC08' | 'HC09' | 'HC10', CanonicalFingerprint>,
): void {
  const entries = Object.values(fingerprints);
  for (let i = 1; i < entries.length; i += 1) {
    try {
      assertFingerprintsEqual(entries[0], entries[i]);
    } catch (error) {
      if (error instanceof NeutralEnvelopeError) {
        throw fieldOnly('http', 'canonical', 'four_state_mismatch');
      }
      throw error;
    }
  }
}

export { NeutralEnvelopeError };
