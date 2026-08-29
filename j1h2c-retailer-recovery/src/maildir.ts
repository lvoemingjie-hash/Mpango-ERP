/**
 * Task-private maildir reader (HC11/HC17 evidence source) — B1-R1 (Kilo E).
 *
 * FRESHNESS CONTRACT (Kilo E):
 *  - The caller snapshots the delivery file set for one exact email BEFORE
 *    triggering the journey step (snapshotDeliveries).
 *  - After the step, pollForExactlyOneNewDelivery polls until EXACTLY ONE
 *    new file exists that was not in the snapshot; stale files (HC06 or
 *    historical deliveries) can never be selected.
 *  - Only the NEW file(s) are parsed — never "sort filenames, take latest".
 *
 * LINK CONTRACT (Kilo E #5/#6):
 *  - The reset link may be a relative path (/retailer/reset-password#...)
 *    or an absolute URL using PUBLIC_FRONTEND_URL.
 *  - After parsing, the link is validated EXACTLY: pathname
 *    /retailer/reset-password, EMPTY query string, fragment key set
 *    exactly {resetToken, w} (for fresh links) with a non-empty token and
 *    the canonical w.
 *
 * Errors name the step/category only — never a filename, email, URL,
 * token, or code value.
 */

import { readFile, readdir } from 'node:fs/promises';
import { join } from 'node:path';
import { fieldOnly } from './assertions.js';

export interface MaildirDelivery {
  /** The reset link exactly as delivered (relative or absolute). */
  resetLink: string;
  /** The reset token extracted from the link fragment (memory only). */
  resetToken: string;
  /** The public `w` code carried by the link fragment, when present. */
  portalCode: string | null;
}

/** Snapshot the exact set of delivery filenames for one email (Kilo E #1). */
export async function snapshotDeliveries(
  maildirRoot: string,
  exactEmail: string,
): Promise<Set<string>> {
  const dir = join(maildirRoot, exactEmail.toLowerCase());
  try {
    const names = await readdir(dir);
    return new Set(names.filter((name) => name.endsWith('.json')));
  } catch {
    return new Set();
  }
}

/** Read-only count of deliveries for one exact email. */
export async function countDeliveries(
  maildirRoot: string,
  exactEmail: string,
): Promise<number> {
  return (await snapshotDeliveries(maildirRoot, exactEmail)).size;
}

/**
 * Poll (event-based deadline, no fixed sleep loops of unbounded length)
 * until exactly ONE new delivery file exists beyond the snapshot.
 * Zero or multiple new files are a failure — never "pick latest".
 */
export async function pollForExactlyOneNewDelivery(
  maildirRoot: string,
  exactEmail: string,
  snapshot: Set<string>,
  options: { timeoutMs?: number; intervalMs?: number } = {},
): Promise<{ fileName: string; link: string }> {
  const timeoutMs = options.timeoutMs ?? 30_000;
  const intervalMs = options.intervalMs ?? 250;
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const current = await snapshotDeliveries(maildirRoot, exactEmail);
    const fresh = [...current].filter((name) => !snapshot.has(name));
    if (fresh.length === 1) {
      const link = await readDeliveryLink(maildirRoot, exactEmail, fresh[0]);
      return { fileName: fresh[0], link };
    }
    if (fresh.length > 1) {
      throw fieldOnly('mail', 'fresh_delivery_count', 'multiple_new_files');
    }
    if (Date.now() >= deadline) {
      throw fieldOnly('mail', 'fresh_delivery_count', 'timeout_no_new_file');
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
}

async function readDeliveryLink(
  maildirRoot: string,
  exactEmail: string,
  fileName: string,
): Promise<string> {
  const dir = join(maildirRoot, exactEmail.toLowerCase());
  let payload: { link?: unknown };
  try {
    payload = JSON.parse(await readFile(join(dir, fileName), 'utf8'));
  } catch {
    throw fieldOnly('mail', 'delivery_file', 'not_json');
  }
  if (typeof payload.link !== 'string') {
    throw fieldOnly('mail', 'delivery_file.link', 'wrong_type');
  }
  return payload.link;
}

/**
 * Parse + EXACTLY validate a reset link (Kilo E #6): relative path or
 * absolute PUBLIC_FRONTEND_URL form; pathname, empty query, fragment key
 * set, token presence, and (optionally) the canonical w.
 */
export function parseAndValidateResetLink(
  link: string,
  options: { requireCanonicalW?: string } = {},
): MaildirDelivery {
  let url: URL;
  try {
    url = new URL(link, 'http://link.local.invalid/');
  } catch {
    throw fieldOnly('mail', 'reset_link', 'unparsable');
  }
  if (url.pathname !== '/retailer/reset-password') {
    throw fieldOnly('mail', 'reset_link.pathname', 'wrong_path');
  }
  if (url.search !== '') {
    throw fieldOnly('mail', 'reset_link.query', 'query_string_forbidden');
  }
  const fragment = new URLSearchParams(url.hash.startsWith('#') ? url.hash.slice(1) : url.hash);
  const fragmentKeys = [...fragment.keys()].sort().join(',');
  const resetToken = fragment.get('resetToken') ?? '';
  if (!resetToken) {
    throw fieldOnly('mail', 'reset_link.fragment', 'missing_resetToken');
  }
  const portalCode = fragment.get('w');
  if (portalCode === null) {
    throw fieldOnly('mail', 'reset_link.fragment', 'missing_w');
  }
  if (fragmentKeys !== 'resetToken,w') {
    throw fieldOnly('mail', 'reset_link.fragment', 'unexpected_fragment_keys');
  }
  if (options.requireCanonicalW !== undefined && portalCode !== options.requireCanonicalW) {
    throw fieldOnly('mail', 'reset_link.fragment.w', 'not_canonical_code');
  }
  return { resetLink: link, resetToken, portalCode };
}
