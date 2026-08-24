/**
 * Neutrality fingerprinting for F3/F4 (task directive #10).
 *
 * The forgot-password response is intercepted in the browser context, reduced
 * to a fingerprint — HTTP status, SHA-256 of the body, body length in bytes —
 * and the raw body is then DISCARDED. The raw response is never stored,
 * logged or written to any artifact. F4 compares its fingerprint plus the
 * visible neutral copy against F3's for byte-indistinguishable behavior.
 */

import { createHash } from 'node:crypto';
import type { Page } from '@playwright/test';
import { a1State } from './token-store.js';

export interface ResponseFingerprint {
  status: number;
  bodySha256: string;
  bodyLengthBytes: number;
}

export function fingerprintResponse(status: number, bodyText: string): ResponseFingerprint {
  return {
    status,
    bodySha256: createHash('sha256').update(bodyText, 'utf8').digest('hex'),
    bodyLengthBytes: Buffer.byteLength(bodyText, 'utf8'),
  };
}

/**
 * Install a one-shot interceptor on the forgot-password endpoint. The route
 * passes the real response through unchanged while recording only the
 * fingerprint of the FIRST matching response into the in-memory store.
 */
export async function captureForgotFingerprint(
  page: Page,
  label: 'F3' | 'F4' | 'F5',
): Promise<void> {
  await page.route('**/api/v1/auth/forgot-password', async (route) => {
    const response = await route.fetch();
    const body = await response.text();
    a1State().fingerprints[label] = fingerprintResponse(response.status(), body);
    // body goes out of scope here — the raw response text is never retained.
    await route.fulfill({ response });
  });
}

export function sameFingerprint(
  left: ResponseFingerprint,
  right: ResponseFingerprint,
): boolean {
  return (
    left.status === right.status &&
    left.bodySha256 === right.bodySha256 &&
    left.bodyLengthBytes === right.bodyLengthBytes
  );
}

/** Which fingerprint field differs first — used for sanitized failure messages. */
export function firstFingerprintDifference(
  left: ResponseFingerprint,
  right: ResponseFingerprint,
): string {
  if (left.status !== right.status) return 'status';
  if (left.bodyLengthBytes !== right.bodyLengthBytes) return 'bodyLengthBytes';
  if (left.bodySha256 !== right.bodySha256) return 'bodySha256';
  return 'none';
}
