/**
 * Task-private maildir reader (HC11/HC17 evidence source).
 *
 * Reads the latest retailer credential delivery for one exact email from
 * the task-private maildir the launcher dumps emails into. The reset link
 * and token exist ONLY in the single harness process memory (see
 * token-store); they are never written to logs, JSON, JUnit, CSV, trace or
 * screenshots, and never echoed into failure messages.
 */

import { readFile, readdir } from 'node:fs/promises';
import { join } from 'node:path';
import { fieldOnly } from './assertions.js';

export interface MaildirDelivery {
  /** The reset link exactly as delivered (fragment form). */
  resetLink: string;
  /** The reset token extracted from the link fragment (memory only). */
  resetToken: string;
  /** The public `w` code carried by the link fragment, when present. */
  portalCode: string | null;
}

function parseResetLink(link: string): MaildirDelivery {
  const hashIndex = link.indexOf('#');
  if (hashIndex < 0) {
    throw fieldOnly('mail', 'reset_link', 'missing_fragment');
  }
  const fragment = new URLSearchParams(link.slice(hashIndex + 1));
  const resetToken = fragment.get('resetToken');
  if (!resetToken) {
    throw fieldOnly('mail', 'reset_link.fragment', 'missing_resetToken');
  }
  return {
    resetLink: link,
    resetToken,
    portalCode: fragment.get('w'),
  };
}

export async function readLatestDelivery(
  maildirRoot: string,
  exactEmail: string,
): Promise<MaildirDelivery> {
  const dir = join(maildirRoot, exactEmail.toLowerCase());
  let names: string[];
  try {
    names = await readdir(dir);
  } catch {
    throw fieldOnly('mail', 'maildir', 'unreadable_or_missing');
  }
  const sorted = names.filter((n) => n.endsWith('.json')).sort();
  const latest = sorted[sorted.length - 1];
  if (!latest) {
    throw fieldOnly('mail', 'maildir', 'no_delivery');
  }
  let payload: { link?: unknown };
  try {
    payload = JSON.parse(await readFile(join(dir, latest), 'utf8'));
  } catch {
    throw fieldOnly('mail', 'delivery_file', 'not_json');
  }
  if (typeof payload.link !== 'string') {
    throw fieldOnly('mail', 'delivery_file.link', 'wrong_type');
  }
  return parseResetLink(payload.link);
}

/** Read-only count of deliveries for one exact email (HC06 post-proof). */
export async function countDeliveries(
  maildirRoot: string,
  exactEmail: string,
): Promise<number> {
  const dir = join(maildirRoot, exactEmail.toLowerCase());
  try {
    const names = await readdir(dir);
    return names.filter((n) => n.endsWith('.json')).length;
  } catch {
    return 0;
  }
}
