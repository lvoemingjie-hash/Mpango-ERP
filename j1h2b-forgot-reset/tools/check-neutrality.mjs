#!/usr/bin/env node
/**
 * B1-R3 executable neutrality contract check (static-gate member).
 *
 * Transpiles the REAL canonicalizer (src/neutrality-core.ts) with the
 * already-installed typescript dev dependency and exercises it against a
 * fixture matrix that pins the CTO-ruled contract:
 *
 *   G1  three envelopes whose ONLY difference is the timestamp VALUE must be
 *       pairwise canonically equal (the V3 finding is thereby tolerated).
 *   G2  a message difference must break canonical equality.
 *   G3  any added top-level key (accountExists / eligible / userId / tenant /
 *       request_id probes) must be REJECTED (fixed category).
 *   G4  a missing, non-string, or unparseable timestamp must be REJECTED.
 *   G5  a non-200 status must be REJECTED.
 *   G6  failure output may contain fixed category/field names ONLY — the raw
 *       body, the timestamp value and any fixture secret marker must never
 *       appear in an error message (leak probe).
 *
 * Mutation truth gates M1–M4 and M6 (task B1-R3) map onto G1–G6: mutating the
 * canonicalizer back to raw-byte hashing, dropping message from the canonical
 * payload, allowing arbitrary volatile keys, skipping timestamp validation,
 * or leaking raw content into errors each make THIS check exit non-zero.
 *
 * No browser, no product runtime, no network: fixtures are local strings.
 */

import { readFileSync, mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { createRequire } from 'node:module';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
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

// --- transpile the real canonicalizer (src/neutrality-core.ts) --------------

const coreSource = readFileSync(join(ROOT, 'src', 'neutrality-core.ts'), 'utf8');
const transpiled = ts.transpileModule(coreSource, {
  compilerOptions: {
    module: ts.ModuleKind.ES2022,
    target: ts.ScriptTarget.ES2022,
  },
});
const tempDir = mkdtempSync(join(tmpdir(), 'j1h2b-neutrality-'));
const tempFile = join(tempDir, 'neutrality-core.mjs');
writeFileSync(tempFile, transpiled.outputText, 'utf8');

let core;
try {
  core = await import(`file:///${tempFile.replace(/\\/g, '/')}`);
} catch (error) {
  console.error('executable neutrality check: cannot load transpiled canonicalizer');
  rmSync(tempDir, { recursive: true, force: true });
  process.exit(1);
}

const {
  canonicalizeNeutralEnvelope,
  sameCanonicalFingerprint,
  firstCanonicalDifference,
  pinnedMessageMatches,
  NEUTRAL_MESSAGE_CONSTANT,
  NEUTRAL_ENVELOPE_KEYS,
  TIMESTAMP_SENTINEL,
  NeutralEnvelopeError,
} = core;

// --- fixtures ----------------------------------------------------------------

const MESSAGE = NEUTRAL_MESSAGE_CONSTANT;
const LEAK_MARKER = 'J1H2B-LEAK-PROBE-7f31';
const tsA = '2026-08-25T01:02:03.456789Z';
const tsB = '2026-08-25T09:08:07.654321Z';
const tsC = '2026-08-25T23:59:59.999999Z';

function envelope(overrides = {}, keyOrder = ['success', 'data', 'message', 'timestamp']) {
  const base = {
    success: true,
    data: {},
    message: MESSAGE,
    timestamp: tsA,
    ...overrides,
  };
  const ordered = {};
  for (const key of keyOrder) ordered[key] = base[key];
  for (const key of Object.keys(base)) {
    if (!(key in ordered)) ordered[key] = base[key];
  }
  return JSON.stringify(ordered);
}

const validA = envelope({ timestamp: tsA });
const validB = envelope({ timestamp: tsB }, ['timestamp', 'message', 'data', 'success']);
const validC = envelope({ timestamp: tsC }, ['data', 'timestamp', 'success', 'message']);

// --- G1: timestamp-value-only differences are canonically EQUAL --------------

let fpA;
let fpB;
let fpC;
try {
  fpA = canonicalizeNeutralEnvelope(200, validA);
  fpB = canonicalizeNeutralEnvelope(200, validB);
  fpC = canonicalizeNeutralEnvelope(200, validC);
} catch (error) {
  fail(`G1: a valid neutral envelope was rejected (${error?.message ?? 'unknown category'})`);
}
if (fpA && fpB && fpC) {
  expect(sameCanonicalFingerprint(fpA, fpB), 'G1: envelopes differing only in timestamp value (and key order) must be canonically equal (A vs B)');
  expect(sameCanonicalFingerprint(fpB, fpC), 'G1: envelopes differing only in timestamp value must be canonically equal (B vs C)');
  expect(firstCanonicalDifference(fpA, fpB) === 'none', 'G1: firstCanonicalDifference must report none for the timestamp-only pair');
  expect(fpA.status === 200, 'G1: canonical fingerprint keeps the 200 status');
}

// --- G2: message difference breaks equality (message IS canonical payload) ----

// Both envelopes carry well-TYPED string messages; canonicalization accepts
// them (the type check is the only in-envelope message validation), so the
// canonical payload must make the difference observable: equality must FAIL.
// (Mutation M2: deleting message from the canonical payload makes these two
// envelopes wrongly equal — this probe must go red.)
try {
  const fpM = canonicalizeNeutralEnvelope(200, envelope({ message: `${LEAK_MARKER}-differing-message` }));
  expect(fpM !== undefined, 'G2: well-typed differing-message envelope must canonicalize');
  if (fpM) {
    expect(!sameCanonicalFingerprint(fpA, fpM), 'G2: a differing message must break canonical equality (message must be part of the canonical payload)');
    expect(firstCanonicalDifference(fpA, fpM) !== 'none', 'G2: firstCanonicalDifference must be non-none for the differing message');
  }
} catch (error) {
  fail(`G2: well-typed differing-message envelope must not be rejected (${error?.message ?? 'unknown'})`);
}

// G2b: the pinned-constant predicate — true for the existing neutral
// constant, false for any drifted message (contract #5, spec-side per node).
{
  const fpConst = canonicalizeNeutralEnvelope(200, envelope({}));
  const fpDrift = canonicalizeNeutralEnvelope(200, envelope({ message: 'drifted neutral copy' }));
  expect(pinnedMessageMatches(fpConst) === true, 'G2b: pinnedMessageMatches must accept the existing neutral constant');
  expect(pinnedMessageMatches(fpDrift) === false, 'G2b: pinnedMessageMatches must reject a drifted message');
  expect(fpConst.message === NEUTRAL_MESSAGE_CONSTANT, 'G2b: the fingerprint carries the envelope message for the pinned predicate');
}

// --- G3: added top-level keys are rejected -------------------------------------

const ADDED_KEY_PROBES = ['accountExists', 'eligible', 'userId', 'tenant', 'request_id'];
for (const key of ADDED_KEY_PROBES) {
  let rejected = false;
  let category = '';
  try {
    canonicalizeNeutralEnvelope(200, envelope({ [key]: true }));
  } catch (error) {
    rejected = true;
    category = error?.message ?? '';
  }
  expect(rejected, `G3: added top-level key probe must be rejected (${key})`);
  expect(category.includes('top_level_key_set'), `G3: added key rejection must use the top_level_key_set category (${key})`);
}

// --- G4: timestamp presence / type / format ------------------------------------

const TIMESTAMP_FIXTURES = [
  [{ timestamp: undefined }, 'timestamp_missing', 'missing timestamp'],
  [{ timestamp: 1756071723456 }, 'timestamp_not_string', 'non-string timestamp'],
  [{ timestamp: 'not-a-time' }, 'timestamp_unparseable', 'unparseable timestamp'],
  [{ timestamp: '' }, 'timestamp_unparseable', 'empty timestamp'],
];
for (const [overrides, expectedCategory, label] of TIMESTAMP_FIXTURES) {
  let rejected = false;
  let category = '';
  try {
    const payload = overrides.timestamp === undefined
      ? JSON.stringify({ success: true, data: {}, message: MESSAGE })
      : envelope(overrides);
    canonicalizeNeutralEnvelope(200, payload);
  } catch (error) {
    rejected = true;
    category = error?.message ?? '';
  }
  expect(rejected, `G4: ${label} must be rejected`);
  expect(category.includes(expectedCategory), `G4: ${label} must use category ${expectedCategory}`);
}

// --- G5: non-200 status rejected ------------------------------------------------

try {
  canonicalizeNeutralEnvelope(202, validA);
  fail('G5: a non-200 status must be rejected');
} catch (error) {
  expect(String(error?.message).includes('status_non_200'), 'G5: non-200 rejection must use the status_non_200 category');
}

// --- G6: leak probe — fixed categories only, no content -------------------------

const leakBodies = [
  envelope({ message: `${LEAK_MARKER}-leaky-message` }),
  envelope({ timestamp: `${LEAK_MARKER}-leaky-timestamp` }),
  JSON.stringify({ success: true, data: {}, message: MESSAGE, timestamp: tsA, extra: LEAK_MARKER }),
];
const leakMessages = [];
for (const body of leakBodies) {
  try {
    canonicalizeNeutralEnvelope(200, body);
  } catch (error) {
    // The leak surface is ERROR OUTPUT ONLY: the fingerprint deliberately
    // retains the public message constant field, so fp fields are not part
    // of this probe — a leaky mutant interpolates raw body / timestamp
    // values into thrown messages or stacks.
    leakMessages.push(String(error?.message ?? ''));
    leakMessages.push(String(error?.stack ?? ''));
  }
}
const leakSurface = leakMessages.join('\n');
expect(!leakSurface.includes(LEAK_MARKER), 'G6: failure/error output must never contain envelope content (leak marker found)');
expect(!leakSurface.includes(tsA) && !leakSurface.includes(tsB), 'G6: failure/error output must never contain a timestamp value');
expect(!leakSurface.includes(validA), 'G6: failure/error output must never contain the raw body');

// Also: the pinned exports must exist (the static gate relies on them).
expect(Array.isArray(NEUTRAL_ENVELOPE_KEYS) && NEUTRAL_ENVELOPE_KEYS.length === 4, 'exports: NEUTRAL_ENVELOPE_KEYS must be the 4-key tuple');
expect(typeof TIMESTAMP_SENTINEL === 'string' && TIMESTAMP_SENTINEL.length > 0, 'exports: TIMESTAMP_SENTINEL must be a non-empty string');
expect(typeof NEUTRAL_MESSAGE_CONSTANT === 'string' && NEUTRAL_MESSAGE_CONSTANT.length > 0, 'exports: NEUTRAL_MESSAGE_CONSTANT must be pinned');

rmSync(tempDir, { recursive: true, force: true });

// --- verdict ---------------------------------------------------------------------

if (failures.length > 0) {
  console.error('EXECUTABLE NEUTRALITY CONTRACT CHECK FAILED:');
  for (const message of failures) console.error(` - ${message}`);
  process.exit(1);
}
console.log('Executable neutrality contract check PASSED (G1–G6).');
