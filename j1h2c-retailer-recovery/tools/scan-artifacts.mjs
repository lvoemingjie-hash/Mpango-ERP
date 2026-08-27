#!/usr/bin/env node
/**
 * Post-run evidence zero-leak scanner — B1-R1 (Kilo I closure).
 *
 * Executed AFTER the single authoritative run over the produced evidence
 * directory (machine JSON, JUnit XML, reconciliation artifacts, any
 * logs). Frozen with the harness but NOT a Playwright node; it can never
 * surface as a browser PASS.
 *
 * AUTHORITATIVE MODE (Kilo I #1/#5): the package script `scan:artifacts`
 * ALWAYS runs with --secrets-from-env. Without the dynamic secret inputs
 * (J1H2C_* password/token variables) the scanner FAILS CLOSED — it never
 * degrades to a structure-only scan.
 *
 * Scanned secret surfaces (Kilo I #2):
 *   - runtime passwords (J1H2C_RETAILER_CURRENT_PASSWORD / NEW_PASSWORD)
 *   - the dynamic reset token (J1H2C_LAST_RESET_TOKEN, exported by the
 *     launcher after the run) across every artifact byte
 *   - Authorization header shapes (Bearer / Basic value patterns)
 *   - the canonical w code on FORBIDDEN artifact surfaces (any file other
 *     than the reconciliation artifacts, which contain no URLs)
 *   - structural patterns: resetToken= fragments, reset_token JSON values
 *
 * Findings are sanitized: file + surface + category ONLY (Kilo I #3) —
 * never a matched value, never a secret.
 */

import { readFileSync, readdirSync, statSync, existsSync } from 'node:fs';
import { join } from 'node:path';

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

// Kilo I #5: fail closed when secret inputs are missing.
if (args.secretsFromEnv) {
  const requiredEnv = [
    'J1H2C_RETAILER_CURRENT_PASSWORD',
    'J1H2C_RETAILER_NEW_PASSWORD',
    'J1H2C_LAST_RESET_TOKEN',
  ];
  const missing = requiredEnv.filter(
    (name) => !process.env[name] || process.env[name].length < 4,
  );
  if (missing.length > 0) {
    console.error(
      `SCANNER FAIL-CLOSED: dynamic secret inputs missing: ${missing.join(', ')} (names only)`,
    );
    process.exit(1);
  }
} else {
  console.error(
    'SCANNER FAIL-CLOSED: authoritative scan requires --secrets-from-env (this mode is never optional)',
  );
  process.exit(1);
}

function listFiles(dir) {
  const out = [];
  let entries;
  try {
    entries = readdirSync(dir, { withFileTypes: true });
  } catch {
    return out;
  }
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
  /"reset_token"\s*:\s*"[^"]{8,}"/,
  /Authorization['"]?\s*[:=]\s*['"]?(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]{8,}/i,
];
const canonicalCode = process.env.J1H2C_W1_CANONICAL_CODE ?? '';

const files = listFiles(args.artifactsDir);
const passwordSecrets = [
  process.env.J1H2C_RETAILER_CURRENT_PASSWORD,
  process.env.J1H2C_RETAILER_NEW_PASSWORD,
];
const runtimeToken = process.env.J1H2C_LAST_RESET_TOKEN ?? '';

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
  if (runtimeToken && text.includes(runtimeToken)) {
    findings.push(`env-secret-match:${category}:reset_token`);
  }
  // Canonical w is public in URLs but artifacts carry NO URLs; any
  // occurrence in an artifact is a leak (exception: none expected).
  if (canonicalCode && text.includes(canonicalCode)) {
    findings.push(`canonical-code-forbidden-surface:${category}`);
  }
}

if (findings.length > 0) {
  for (const finding of findings) console.error(`ARTIFACT SCAN FINDING: ${finding}`);
  console.error(`ARTIFACT SCAN FAILED (${findings.length} finding(s))`);
  process.exit(1);
}
console.log(`ARTIFACT SCAN PASSED (${files.length} file(s), zero findings).`);
