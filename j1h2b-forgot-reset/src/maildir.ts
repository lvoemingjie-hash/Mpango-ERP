/**
 * Task-private maildir reader — the F6 execution surface (task directive #9).
 *
 * The authoritative run's launcher dumps the backend's non-production email
 * sink into J1H2B_MAILDIR_ROOT. Contract for the dump (documented in README):
 * each email is a UTF-8 text file anywhere under the root (flat files or a
 * classic new/cur/tmp maildir layout are both supported) whose content
 * contains the recipient address and the fragment-only link
 * (/reset-password#resetToken=…, /verify-email#token=…,
 * /setup-credential#setupToken=…).
 *
 * This helper reads files with fs only, keeps the extracted link and token in
 * memory, and never writes, logs, screenshots or otherwise persists them.
 * All errors are sanitized: they name the operation and counts, never
 * content.
 */

import { readdir, readFile, stat } from 'node:fs/promises';
import { join } from 'node:path';

export type LinkKind = 'reset' | 'verify' | 'setup';

const FRAGMENT_KEYS: Record<LinkKind, { path: string; param: string }> = {
  reset: { path: '/reset-password', param: 'resetToken' },
  verify: { path: '/verify-email', param: 'token' },
  setup: { path: '/setup-credential', param: 'setupToken' },
};

/** Match an absolute URL or a bare absolute path carrying the fragment param. */
function linkPattern(kind: LinkKind): RegExp {
  const { path, param } = FRAGMENT_KEYS[kind];
  const charClass = '[A-Za-z0-9~_.%\\-]+';
  return new RegExp(`(?:https?://[^\\s"'<>]+)?${path}#${param}=${charClass}`);
}

export interface MaildirHit {
  link: string;
  /** Decoded fragment token value — in-memory only. */
  token: string;
  mtimeMs: number;
}

interface ScannedFile {
  path: string;
  mtimeMs: number;
}

async function collectFiles(
  root: string,
  depth: number,
  out: ScannedFile[],
): Promise<void> {
  let entries;
  try {
    entries = await readdir(root, { withFileTypes: true });
  } catch {
    throw new Error(
      `maildir: cannot read directory (root is configured; path withheld)`,
    );
  }
  for (const entry of entries) {
    if (entry.name.startsWith('.')) continue;
    const full = join(root, entry.name);
    if (entry.isDirectory()) {
      if (depth > 0) await collectFiles(full, depth - 1, out);
      continue;
    }
    if (!entry.isFile()) continue;
    try {
      const info = await stat(full);
      out.push({ path: full, mtimeMs: info.mtimeMs });
    } catch {
      // Transient launcher write; the next poll re-reads.
    }
  }
}

function extractToken(link: string, kind: LinkKind): string | undefined {
  const { param } = FRAGMENT_KEYS[kind];
  const fragment = link.split('#')[1] ?? '';
  const raw = new URLSearchParams(fragment).get(param);
  if (!raw) return undefined;
  try {
    return decodeURIComponent(raw);
  } catch {
    return raw;
  }
}

async function scanOnce(options: {
  root: string;
  kind: LinkKind;
  recipient: string;
  sinceMs: number;
}): Promise<MaildirHit | undefined> {
  const files: ScannedFile[] = [];
  await collectFiles(options.root, 4, files);
  const skewMs = 3_000;
  let newest: MaildirHit | undefined;
  let candidateCount = 0;
  const recipientLower = options.recipient.toLowerCase();
  const pattern = linkPattern(options.kind);
  for (const file of files) {
    if (file.mtimeMs + skewMs < options.sinceMs) continue;
    let content: string;
    try {
      content = await readFile(file.path, 'utf8');
    } catch {
      continue;
    }
    if (!content.toLowerCase().includes(recipientLower)) continue;
    const match = content.match(pattern);
    if (!match) continue;
    candidateCount += 1;
    const link = match[0];
    const token = extractToken(link, options.kind);
    if (!token) continue;
    if (!newest || file.mtimeMs > newest.mtimeMs) {
      newest = { link, token, mtimeMs: file.mtimeMs };
    }
  }
  // Deliberately do not expose candidateCount in errors that could correlate
  // with content; the count is only used internally.
  void candidateCount;
  return newest;
}

/**
 * Poll the task-private maildir for the newest <kind> link for the recipient
 * written at/after sinceMs. The returned link/token exist in memory only.
 */
export async function waitForLink(options: {
  root: string;
  kind: LinkKind;
  recipient: string;
  sinceMs: number;
  timeoutMs?: number;
  pollMs?: number;
}): Promise<MaildirHit> {
  const timeoutMs = options.timeoutMs ?? 120_000;
  const pollMs = options.pollMs ?? 1_000;
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const hit = await scanOnce(options);
    if (hit) return hit;
    if (Date.now() >= deadline) {
      throw new Error(
        `maildir: no ${options.kind} link found for the requested recipient within ${timeoutMs}ms (contents withheld)`,
      );
    }
    await new Promise((resolve) => setTimeout(resolve, pollMs));
  }
}

/**
 * One-shot probe used by negative postconditions (F5): returns whether any
 * <kind> link for the recipient exists at/after sinceMs. Never throws on
 * absence — the caller turns a `true` result into a sanitized failure.
 */
export async function probeForLink(options: {
  root: string;
  kind: LinkKind;
  recipient: string;
  sinceMs: number;
}): Promise<boolean> {
  const hit = await scanOnce(options);
  return hit !== undefined;
}

/**
 * Wait out a negative-evidence window (F5 zero-mail postcondition): poll for
 * the whole window and report whether any matching link appeared.
 */
export async function negativeWindowHasLink(options: {
  root: string;
  kind: LinkKind;
  recipient: string;
  sinceMs: number;
  windowMs: number;
}): Promise<boolean> {
  const deadline = Date.now() + options.windowMs;
  for (;;) {
    if (await probeForLink(options)) return true;
    if (Date.now() >= deadline) return false;
    await new Promise((resolve) => setTimeout(resolve, 1_000));
  }
}
