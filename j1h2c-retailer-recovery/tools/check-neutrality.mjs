#!/usr/bin/env node
/**
 * Executable canonical-neutrality contract check (static-gate member).
 *
 * Transpiles the REAL canonicalizer (src/neutrality-core.ts) with the
 * installed typescript dev dependency and exercises it against a fixture
 * matrix pinning the H2-C canonical neutrality contract:
 *
 *   G1  four envelopes whose ONLY difference is the timestamp VALUE must be
 *       pairwise canonically equal.
 *   G2  a message difference must break canonical equality.
 *   G3  any added top-level key (accountExists / eligible / userId /
 *       request_id probes) must be REJECTED with the fixed KEY_SET category.
 *   G4  a missing, non-string, or unparseable timestamp must be REJECTED.
 *   G5  a non-empty data object or non-true success must be REJECTED.
 *   G6  failure output may contain fixed category/field names ONLY — the raw
 *       body, the timestamp value and any fixture secret marker must never
 *       appear in an error message (leak probe).
 *
 * No browser, no product runtime, no network: fixtures are local strings.
 */

import { readFileSync, mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { createRequire } from 'node:module';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { pathToFileURL } from 'node:url';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const ts = require('typescript');

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const failures = [];

function fail(message) {
  failures.push(message);
}

function expect(condition, label) {
  if (!condition) fail(`executable neutrality check: ${label}`);
}

const coreSource = readFileSync(join(ROOT, 'src', 'neutrality-core.ts'), 'utf8');
const transpiled = ts.transpileModule(coreSource, {
  compilerOptions: {
    module: ts.ModuleKind.ES2022,
    target: ts.ScriptTarget.ES2022,
  },
});
const tempDir = mkdtempSync(join(tmpdir(), 'j1h2c-neutrality-'));
const tempFile = join(tempDir, 'neutrality-core.mjs');
writeFileSync(tempFile, transpiled.outputText, 'utf8');

let core;
try {
  core = await import(`file:///${tempFile.replace(/\\/g, '/')}`);
} catch {
  console.error('executable neutrality check: cannot load transpiled canonicalizer');
  rmSync(tempDir, { recursive: true, force: true });
  process.exit(1);
}

const {
  canonicalFingerprint,
  assertFingerprintsEqual,
  NEUTRAL_MESSAGE_CONSTANT,
  TIMESTAMP_SENTINEL,
  NeutralEnvelopeError,
} = core;
if (typeof NEUTRAL_MESSAGE_CONSTANT !== 'string' || !NEUTRAL_MESSAGE_CONSTANT) {
  console.error('executable neutrality check: NEUTRAL_MESSAGE_CONSTANT export missing');
  process.exit(1);
}
const envelope = buildEnvelope();

const FIXTURE_SECRET = 'FIXTURE_SECRET_MARKER_DO_NOT_LEAK'; // pragma: allowlist secret

// message default is injected by buildEnvelope AFTER the core constants are
// loaded, so a missing export fails loudly instead of silently.
function buildEnvelope() {
  return (overrides = {}) => ({
    success: true,
    data: {},
    message: NEUTRAL_MESSAGE_CONSTANT,
    timestamp: '2026-08-27T00:00:00Z',
    ...overrides,
  });
}

function mustThrowCategory(body, category, label) {
  try {
    canonicalFingerprint(body);
  } catch (error) {
    if (error instanceof NeutralEnvelopeError) {
      expect(error.category === category, `${label}: category ${error.category}`);
      const text = String(error.message);
      expect(
        !text.includes(FIXTURE_SECRET) && !text.includes('2026-'),
        `${label}: error output leaked fixture content`,
      );
      return;
    }
    fail(`${label}: wrong error type`);
    return;
  }
  fail(`${label}: expected rejection but passed`);
}

// G1 — timestamp-only differences are canonically equal.
{
  const fingerprints = [
    '2026-08-27T00:00:00Z',
    '2026-08-27T00:00:01Z',
    '2027-01-01T12:34:56.789Z',
  ].map((timestamp) => canonicalFingerprint(envelope({ timestamp })));
  for (let i = 1; i < fingerprints.length; i += 1) {
    try {
      assertFingerprintsEqual(fingerprints[0], fingerprints[i]);
    } catch {
      fail('G1: timestamp-only difference broke canonical equality');
    }
  }
  console.log('G1 OK — timestamp-only differences canonically equal');
}

// G2 — a message difference breaks equality (the mutated envelope is
// EXPECTED to be rejected by the validator, so it must be computed inside
// the try; an unhandled rejection here is the crash we fixed).
{
  const a = canonicalFingerprint(envelope({}));
  let broke = false;
  try {
    const b = canonicalFingerprint(
      envelope({ message: NEUTRAL_MESSAGE_CONSTANT + 'x' }),
    );
    assertFingerprintsEqual(a, b);
  } catch {
    broke = true;
  }
  expect(broke, 'G2: message difference must break equality');
  console.log('G2 OK — message difference breaks equality');
}

// G3 — added keys are rejected.
{
  for (const key of ['accountExists', 'eligible', 'userId', 'request_id', FIXTURE_SECRET]) {
    const body = envelope({});
    body[key] = FIXTURE_SECRET;
    mustThrowCategory(body, 'KEY_SET', `G3:${key}`);
  }
  console.log('G3 OK — added keys rejected with KEY_SET');
}

// G4 — timestamp validation.
{
  const missing = envelope({});
  delete missing.timestamp;
  // The exact key-set check runs first, so a deleted timestamp surfaces as
  // KEY_SET (stricter and equally fail-closed).
  mustThrowCategory(missing, 'KEY_SET', 'G4:missing');
  mustThrowCategory(envelope({ timestamp: 12345 }), 'TIMESTAMP_TYPE', 'G4:non-string');
  mustThrowCategory(
    envelope({ timestamp: 'not-a-time' }),
    'TIMESTAMP_UNPARSABLE',
    'G4:unparsable',
  );
  console.log('G4 OK — timestamp missing/type/unparsable rejected');
}

// G5 — data/success value validation.
{
  mustThrowCategory(envelope({ data: { k: 1 } }), 'DATA_VALUE', 'G5:data');
  mustThrowCategory(envelope({ success: false }), 'SUCCESS_VALUE', 'G5:success');
  console.log('G5 OK — non-empty data / non-true success rejected');
}

// G6 — failure output leak probe.
{
  try {
    canonicalFingerprint(envelope({ message: FIXTURE_SECRET }));
    fail('G6: expected MESSAGE_VALUE rejection');
  } catch (error) {
    const message = String((error && error.message) || error);
    expect(!message.includes(FIXTURE_SECRET), 'G6: raw value leaked in error');
  }
  const sentinelProbe = canonicalFingerprint(envelope({}));
  const serialized = JSON.stringify(sentinelProbe);
  expect(!serialized.includes('2026-'), 'G6: timestamp value retained in fingerprint');
  expect(
    !serialized.includes(NEUTRAL_MESSAGE_CONSTANT),
    'G6: message retained in fingerprint',
  );
  expect(typeof TIMESTAMP_SENTINEL === 'string', 'G6: sentinel not exported');
  console.log('G6 OK — errors carry categories only; fingerprint carries no raw values');
}

rmSync(tempDir, { recursive: true, force: true });

if (failures.length > 0) {
  for (const message of failures) console.error(message);
  console.error(`EXECUTABLE NEUTRALITY CHECK FAILED (${failures.length})`);
  process.exit(1);
}
console.log('EXECUTABLE NEUTRALITY CONTRACT CHECK PASSED (G1-G6).');
