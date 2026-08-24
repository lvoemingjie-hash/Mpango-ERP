#!/usr/bin/env node
/**
 * R13 — post-run evidence zero-leak scan (NON-BROWSER POSTCOND node).
 *
 * Executed AFTER the single authoritative run over the produced evidence
 * directory (machine JSON, JUnit XML, node-outcome CSV, any logs). This tool
 * is frozen with the harness but is NOT a Playwright node and can never
 * surface as a browser PASS; its verdict enters the reconciliation ledger.
 *
 * Findings are sanitized: they name the FILE and the FIELD/PATTERN only —
 * never a matched value, never a secret. With --secrets-from-env the scanner
 * additionally matches the in-memory run secrets (passwords/token env vars)
 * against artifact bytes; those values are loaded, used and discarded in
 * memory, never printed.
 *
 * Also asserts the screenshot/video/trace ban: the frozen config disables
 * them, so no image/video/zip artifact may exist.
 */

import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';

function parseArgs(argv) {
  const args = { artifactsDir: 'artifacts', secretsFromEnv: false };
  for (let i = 0; i < argv.length; i += 1) {
    if (argv[i] === '--artifacts-dir') args.artifactsDir = argv[i + 1] ?? args.artifactsDir;
    if (argv[i] === '--secrets-from-env') args.secretsFromEnv = true;
  }
  return args;
}

const args = parseArgs(process.argv.slice(2));
const findings = [];

function listFiles(dir) {
  const out = [];
  let entries;
  try {
    entries = readdirSync(dir, { withFileTypes: true });
  } catch {
    findings.push({ file: relative(process.cwd(), dir), field: 'artifacts dir unreadable' });
    return out;
  }
  for (const entry of entries) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      out.push(...listFiles(full));
    } else {
      out.push(full);
    }
  }
  return out;
}

const TEXT_PATTERN_FINDINGS = [
  { pattern: /resetToken=/i, field: 'literal resetToken parameter' },
  { pattern: /reset_token=/i, field: 'literal reset_token parameter' },
  { pattern: /Authorization"\s*:/i, field: 'Authorization header object' },
  { pattern: /Bearer\s+[A-Za-z0-9._-]{8,}/i, field: 'Bearer credential literal' },
  { pattern: /"password"\s*:\s*"[^"]{8,}"/i, field: 'password field with value' },
  { pattern: /\b[a-f0-9]{64}\b/i, field: '64-hex digest-like literal' },
];

const BANNED_SUFFIXES = ['.png', '.jpg', '.jpeg', '.webp', '.zip', '.webm', '.mp4', '.trace'];

let scanned = 0;
for (const file of listFiles(args.artifactsDir)) {
  const rel = relative(process.cwd(), file);
  scanned += 1;
  if (BANNED_SUFFIXES.some((suffix) => file.toLowerCase().endsWith(suffix))) {
    findings.push({ file: rel, field: 'banned artifact type (screenshot/video/trace)' });
    continue;
  }
  let text;
  try {
    text = readFileSync(file, 'utf8');
  } catch {
    findings.push({ file: rel, field: 'unreadable file' });
    continue;
  }
  for (const { pattern, field } of TEXT_PATTERN_FINDINGS) {
    if (pattern.test(text)) findings.push({ file: rel, field });
  }
  if (args.secretsFromEnv) {
    const SECRET_VARS = [
      'J1H2B_A1_INITIAL_PASSWORD',
      'J1H2B_A1_NEW_PASSWORD',
      'J1H2B_A1_REPLAY_PASSWORD',
      'J1H2B_INELIGIBLE_TEMP_PASSWORD',
      'J1H2B_W1_OWNER_PASSWORD',
      'J1H2B_W2_OWNER_PASSWORD',
      'J1H2B_M_INITIAL_PASSWORD',
      'J1H2B_M_NEW_PASSWORD',
    ];
    for (const name of SECRET_VARS) {
      const value = (process.env[name] ?? '').trim();
      if (value.length >= 8 && text.includes(value)) {
        findings.push({ file: rel, field: `run secret from ${name}` });
      }
    }
  }
}

console.log(`R13 artifact scan: ${scanned} file(s) under ${args.artifactsDir}`);
if (findings.length > 0) {
  console.error('R13 FAILED — findings (values withheld):');
  for (const finding of findings) {
    console.error(` - ${finding.file}: ${finding.field}`);
  }
  process.exit(1);
}
console.log('R13 PASSED — zero leak findings.');
