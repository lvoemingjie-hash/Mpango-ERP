#!/usr/bin/env node
/**
 * Post-run evidence zero-leak scanner — B1-R2 (Kilo I closure).
 *
 * Executed AFTER the single authoritative run over the produced evidence
 * directory (machine JSON, JUnit XML, reconciliation + maildir-snapshot
 * artifacts, any logs). Frozen with the harness but NOT a Playwright node;
 * it can never surface as a browser PASS.
 *
 * AUTHORITATIVE MODE (Kilo I #1/#2/#3, B1-R2): the scanner derives its
 * dynamic secret inputs EXECUTABLY — no cross-process env handoff from the
 * Playwright child is relied upon:
 *   1. It reads THIS run's reset emails from the task-private maildir for
 *      the exact retailer email, scoped by the run-start snapshot persisted
 *      by runPreconditions (artifacts/maildir-snapshot.json) — only NEW
 *      files are parsed, so historical-task tokens never enter the secret
 *      set.
 *   2. Every mail token of THIS run is scanned against every artifact.
 *   3. The forged token comes from J1H2C_FORGED_RESET_TOKEN (the same
 *      launcher-injected value HC15 used); missing/short/equal-to-any-mail
 *      token fails closed.
 *   4. Runtime passwords (current/new) and the canonical w code come from
 *      J1H2C_* env; Authorization header shapes are pattern-scanned.
 *
 * Secrets live ONLY in this process's memory (Kilo I #6): no secret files,
 * no CLI arguments carrying values, no logging of values. Output carries
 * file/surface/category ONLY (Kilo I #7).
 *
 * Fail-closed conditions (Kilo I #8): missing --secrets-from-env,
 * unreadable maildir, zero new-mail tokens for THIS run, missing artifacts
 * directory, missing/short/reused forged token.
 */

import { readFileSync, readdirSync, existsSync, statSync } from 'node:fs';
import { join } from 'node:path';

function parseArgs(argv) {
  const args = { artifactsDir: 'artifacts', secretsFromEnv: false, maildirRoot: '' };
  for (let i = 0; i < argv.length; i += 1) {
    if (argv[i] === '--artifacts-dir') args.artifactsDir = argv[i + 1] ?? args.artifactsDir;
    if (argv[i] === '--secrets-from-env') args.secretsFromEnv = true;
    if (argv[i] === '--maildir-root') args.maildirRoot = argv[i + 1] ?? '';
  }
  return args;
}

const args = parseArgs(process.argv.slice(2));
const findings = [];

function failClosed(reason) {
  console.error(`SCANNER FAIL-CLOSED: ${reason}`);
  process.exit(1);
}

if (!args.secretsFromEnv) {
  failClosed('authoritative scan requires --secrets-from-env (this mode is never optional)');
}

const requiredEnv = [
  'J1H2C_RETAILER_CURRENT_PASSWORD',
  'J1H2C_RETAILER_NEW_PASSWORD',
  'J1H2C_FORGED_RESET_TOKEN',
  'J1H2C_W1_CANONICAL_CODE',
];
const missingEnv = requiredEnv.filter((name) => !process.env[name] || process.env[name].length < 4);
if (missingEnv.length > 0) {
  failClosed(`dynamic secret inputs missing: ${missingEnv.join(', ')} (names only)`);
}

if (!existsSync(args.artifactsDir) || !statSync(args.artifactsDir).isDirectory()) {
  failClosed('artifacts directory missing');
}

// --- derive THIS run's mail tokens (Kilo I #1/#2) ---------------------------
const snapshotPath = join(args.artifactsDir, 'maildir-snapshot.json');
if (!existsSync(snapshotPath)) {
  failClosed('run-start maildir snapshot artifact missing (precondition gate did not run)');
}
let snapshot;
try {
  snapshot = JSON.parse(readFileSync(snapshotPath, 'utf8'));
} catch {
  failClosed('maildir snapshot artifact unreadable');
}
if (!snapshot.mailboxes || !snapshot.mailboxes.established || !snapshot.mailboxes.unverified) {
  failClosed('snapshot missing an expected mailbox (established/unverified)');
}
const maildirRoot = args.maildirRoot || process.env.J1H2C_MAILDIR_ROOT || '';
if (!maildirRoot) {
  failClosed('maildir root missing (--maildir-root or J1H2C_MAILDIR_ROOT)');
}
// Identity labels -> env emails (values stay in memory only).
const mailboxEnv = {
  established: process.env.J1H2C_RETAILER_EMAIL,
  unverified: process.env.J1H2C_UNVERIFIED_EMAIL,
};
for (const [label, email] of Object.entries(mailboxEnv)) {
  if (!email || email.length < 3) {
    failClosed(`mailbox env missing: ${label} (label only)`);
  }
}
const setupTokens = { established: [], unverified: [] };
const resetTokens = [];
function collectFromMailbox(label, priorFiles) {
  const box = join(maildirRoot, mailboxEnv[label].trim().toLowerCase());
  let currentNames;
  try {
    currentNames = readdirSync(box).filter((name) => name.endsWith('.json'));
  } catch {
    failClosed(`mailbox unreadable: ${label} (label only)`);
  }
  const prior = new Set(priorFiles ?? []);
  const freshNames = currentNames.filter((name) => !prior.has(name));
  for (const name of freshNames) {
    let payload;
    try {
      payload = JSON.parse(readFileSync(join(box, name), 'utf8'));
    } catch {
      failClosed('fresh delivery file unreadable');
    }
    if (typeof payload.link !== 'string') failClosed('delivery link wrong type');
    const hashIndex = payload.link.indexOf('#');
    if (hashIndex < 0) failClosed('delivery link missing fragment');
    const fragment = new URLSearchParams(payload.link.slice(hashIndex + 1));
    const setupToken = fragment.get('setupToken');
    if (setupToken && setupToken.length >= 4) setupTokens[label].push(setupToken);
    const resetToken = fragment.get('resetToken');
    if (resetToken && resetToken.length >= 4) resetTokens.push(resetToken);
  }
}
collectFromMailbox('established', snapshot.mailboxes.established);
collectFromMailbox('unverified', snapshot.mailboxes.unverified);
// B1-R3-R1: setup token cardinality is STRICTLY ONE per mailbox. Zero OR
// more-than-one both fail closed (label + category only). Reset tokens are
// NEVER count-limited — every one is collected and scanned.
for (const label of ['established', 'unverified']) {
  if (setupTokens[label].length !== 1) {
    failClosed(`setup_token_cardinality:${label}:${setupTokens[label].length}`);
  }
}
const mailTokens = [...setupTokens.established, ...setupTokens.unverified, ...resetTokens];
if (mailTokens.length === 0) {
  failClosed('zero new-mail tokens for THIS run (snapshot scoping found nothing)');
}
const seen = new Set();
for (const token of mailTokens) {
  if (seen.has(token)) {
    failClosed('duplicate token across mailboxes (token collision)');
  }
  seen.add(token);
}
const forgedToken = process.env.J1H2C_FORGED_RESET_TOKEN;
if (forgedToken.trim().length < 8) {
  failClosed('forged token missing or too short');
}
if (mailTokens.includes(forgedToken)) {
  failClosed('forged token equals a real mail token (reuse forbidden)');
}

const canonicalCode = process.env.J1H2C_W1_CANONICAL_CODE;
const passwordSecrets = [
  process.env.J1H2C_RETAILER_CURRENT_PASSWORD,
  process.env.J1H2C_RETAILER_NEW_PASSWORD,
];
const allTokens = [...mailTokens, forgedToken];

// --- scan artifacts ----------------------------------------------------------
function listFiles(dir) {
  const out = [];
  const entries = readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) out.push(...listFiles(full));
    else out.push(full);
  }
  return out;
}

const bannedArtifactExtensions = new Set(['.png', '.jpg', '.jpeg', '.webp', '.mp4', '.webm', '.zip']);
const bannedNamePatterns = [/trace\.zip$/i, /screenshot/i, /video/i];
const structuralSecretPatterns = [
  /resetToken=[A-Za-z0-9._~%-]{8,}/,
  /#resetToken=/,
  /#setupToken=/,
  /"reset_token"\s*:\s*"[^"]{8,}"/,
  /"setup_token"\s*:\s*"[^"]{8,}"/,
  /Authorization['"]?\s*[:=]\s*['"]?(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]{8,}/i,
];

const files = listFiles(args.artifactsDir);
for (const file of files) {
  const name = file.split(/[\\/]/).pop();
  const ext = name.slice(name.lastIndexOf('.')).toLowerCase();
  const category = `file:${name}`;
  if (bannedArtifactExtensions.has(ext)) {
    findings.push(`banned-artifact-kind:${category}`);
    continue;
  }
  if (bannedNamePatterns.some((pattern) => pattern.test(name))) {
    findings.push(`banned-artifact-name:${category}`);
    continue;
  }
  let text;
  try {
    text = readFileSync(file, 'utf8');
  } catch {
    continue;
  }
  for (const pattern of structuralSecretPatterns) {
    if (pattern.test(text)) {
      findings.push(`secret-pattern:${category}:${pattern.source.slice(0, 24)}`);
    }
  }
  for (const secret of passwordSecrets) {
    if (secret && text.includes(secret)) {
      findings.push(`env-secret-match:${category}:password`);
    }
  }
  for (const token of allTokens) {
    if (text.includes(token)) {
      findings.push(`env-secret-match:${category}:run_token`);
    }
  }
  if (canonicalCode && text.includes(canonicalCode)) {
    findings.push(`canonical-code-forbidden-surface:${category}`);
  }
}

if (findings.length > 0) {
  for (const finding of findings) console.error(`ARTIFACT SCAN FINDING: ${finding}`);
  console.error(`ARTIFACT SCAN FAILED (${findings.length} finding(s))`);
  process.exit(1);
}
console.log(
  `ARTIFACT SCAN PASSED (${files.length} file(s), ${allTokens.length} run secret(s) in memory only; zero findings).`,
);
