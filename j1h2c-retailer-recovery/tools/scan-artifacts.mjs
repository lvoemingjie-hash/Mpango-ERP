#!/usr/bin/env node
/**
 * Post-run evidence zero-leak scanner.
 *
 * Executed AFTER the single authoritative run over the produced evidence
 * directory (machine JSON, JUnit XML, any logs). Frozen with the harness
 * but NOT a Playwright node; it can never surface as a browser PASS and
 * its verdict enters the reconciliation ledger separately.
 *
 * Findings are sanitized: they name the FILE and the FIELD/PATTERN only —
 * never a matched value, never a secret. With --secrets-from-env the
 * scanner additionally matches the run secrets (J1H2C_* password/token
 * env vars) against artifact bytes; values are loaded, used and discarded
 * in memory, never printed.
 *
 * Also asserts the screenshot/video/trace ban: the frozen config disables
 * them, so no image/video/zip artifact may exist.
 */

import { readFileSync, readdirSync, statSync } from 'node:fs';
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
];

const files = listFiles(args.artifactsDir);
for (const file of files) {
  const name = file.split(/[\\/]/).pop();
  const ext = name.slice(name.lastIndexOf('.')).toLowerCase();
  if (bannedArtifactExtensions.has(ext)) {
    findings.push(`banned-artifact-kind:${name}`);
    continue;
  }
  if (bannedNamePatterns.some((pattern) => pattern.test(name))) {
    findings.push(`banned-artifact-name:${name}`);
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
      findings.push(`secret-pattern:${name}:${pattern.source.slice(0, 24)}`);
    }
  }
}

if (args.secretsFromEnv) {
  const secretValues = Object.entries(process.env)
    .filter(([key]) => key.startsWith('J1H2C_'))
    .filter(([key]) => /PASSWORD|TOKEN|SECRET/.test(key))
    .map(([, value]) => value)
    .filter((value) => value && value.length >= 8);
  for (const file of files) {
    let text;
    try {
      text = readFileSync(file, 'utf8');
    } catch {
      continue;
    }
    for (const value of secretValues) {
      if (text.includes(value)) {
        findings.push(`env-secret-match:${file.split(/[\\/]/).pop()}`);
        break;
      }
    }
  }
}

if (findings.length > 0) {
  for (const finding of findings) console.error(`ARTIFACT SCAN FINDING: ${finding}`);
  console.error(`ARTIFACT SCAN FAILED (${findings.length} finding(s))`);
  process.exit(1);
}
console.log(`ARTIFACT SCAN PASSED (${files.length} file(s) scanned, zero findings).`);
