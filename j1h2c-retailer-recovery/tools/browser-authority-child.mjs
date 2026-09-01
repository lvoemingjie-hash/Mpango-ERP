#!/usr/bin/env node
/**
 * Fixed browser-authority child process (B1-R6-R4) — the REAL Playwright
 * child of the direct authority chain.
 *
 * Invocation discipline:
 *   - launched ONLY through the fixed argv [process.execPath, THIS FILE] by
 *     the entrypoint-driven runner (canonicalAuthorityChildArgv); any extra
 *     argv element, injected flag or caller path is refused before spawn;
 *   - the Playwright CLI is resolved ONLY from the frozen install directory
 *     anchored at THIS module's own location
 *     (../node_modules/@playwright/test/cli.js, package version pinned to
 *     the frozen lockfile) — never from PATH, a shell, `pnpm exec`, or a
 *     caller-provided path;
 *   - Playwright and the artifact scanner run as argv-array subprocesses
 *     with shell:false;
 *   - stdin carries the exact input schema; additional or missing fields
 *     are refused;
 *   - the 15 materialized values are mapped to the EXACT J1H2C_* variables
 *     of the canonical profile (re-read from this module's own location);
 *     every other J1H2C_* spelling and every NODE_x and GIT_x variable (all
 *     letter cases) is stripped from the subprocess environment;
 *   - sensitive values never enter stdout, stderr, or any exception text —
 *     every refusal and failure is a fixed category label;
 *   - before the real Playwright process starts, an atomic create-exclusive
 *     marker records playwright_invocation_count = 1; a second start is
 *     refused BEFORE spawn;
 *   - the real Playwright PID and exit are awaited, never pre-classified:
 *     rc != 0 yields a RED result; rc == 0 still must pass the REAL
 *     reconciliation, run-genuineness and artifact-scanner gates before
 *     complete=true (15 BROWSER PASS + 2 STATIC PASS + gap=0 +
 *     PRECONDITION_PASS + scanner clean, all fresh under the bound
 *     candidate); anything missing, stale, mismatched or FAIL/NOT_RUN/
 *     PENDING yields complete=false;
 *   - the wrapper pid, the Playwright pid, the awaited exit and the
 *     candidate SHA are cross-bound in the result payload;
 *   - this child NEVER writes a PASS reconciliation itself — it only reads
 *     the artifacts the run produced.
 */

import { execFileSync, spawn, spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import {
  closeSync,
  existsSync,
  mkdirSync,
  openSync,
  readFileSync,
  readSync,
  realpathSync,
  statSync,
  writeSync,
} from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const INPUT_SCHEMA = 'j1h2c/browser-authority-child-input/1';
const RESULT_SCHEMA = 'j1h2c/browser-authority-child-result/1';
const INVOCATION_SCHEMA = 'j1h2c/browser-authority-invocation/1';
const RECONCILIATION_SCHEMA = 'j1h2c-reconciliation/1';
const MAX_STDIN_BYTES = 1048576;
const FROZEN_PLAYWRIGHT_VERSION = '1.49.1';
const BROWSER_NODE_IDS = [
  'HC01', 'HC02', 'HC03', 'HC04', 'HC05',
  'HC06', 'HC07', 'HC08', 'HC09', 'HC10',
  'HC12', 'HC13', 'HC14', 'HC15', 'HC16',
];
const STATIC_NODE_IDS = ['HC11', 'HC17'];
// A real 17-node serial journey at up to 120s per node, plus the scanner.
const PLAYWRIGHT_BUDGET_MS = 1_500_000;
const SCANNER_BUDGET_MS = 300_000;
const NULL_CANDIDATE = '0'.repeat(40);

const TOOL_DIR = dirname(fileURLToPath(import.meta.url));
const SELF_PATH = realpathSync(fileURLToPath(import.meta.url));

function sha256Hex(data) {
  return createHash('sha256').update(data, 'utf8').digest('hex');
}

function exactKeys(value, keys) {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) return false;
  const actual = Object.keys(value).sort();
  const expected = [...keys].sort();
  return actual.length === expected.length && actual.every((key, index) => key === expected[index]);
}

function readStdinText() {
  const chunks = [];
  let total = 0;
  const buffer = Buffer.alloc(65536);
  for (;;) {
    const read = readSync(0, buffer, 0, buffer.length, null);
    if (read <= 0) break;
    chunks.push(buffer.subarray(0, read));
    total += read;
    if (total > MAX_STDIN_BYTES) break;
  }
  return Buffer.concat(chunks, total).toString('utf8');
}

const RESULT_PLAYWRIGHT_NEVER = { launched: false, pid: null, exit_code: null, invocation_count: 0 };

function emit(exitCode, category, complete, reconciliationCategory, playwright, candidateSha) {
  writeSync(
    1,
    Buffer.from(
      JSON.stringify({
        schema: RESULT_SCHEMA,
        pid: process.pid,
        exit: exitCode,
        category,
        playwright: playwright ?? RESULT_PLAYWRIGHT_NEVER,
        candidate_sha: candidateSha ?? NULL_CANDIDATE,
        reconciliation: { complete, category: reconciliationCategory ?? category },
      }) + '\n',
      'utf8',
    ),
  );
  process.exit(exitCode);
}

/** git rev-parse HEAD with every GIT_* variable stripped (all cases). */
function resolveHead(cwd) {
  const env = {};
  for (const [key, value] of Object.entries(process.env)) {
    if (!key.toUpperCase().startsWith('GIT_')) env[key] = value;
  }
  const out = execFileSync('git', ['-C', cwd, 'rev-parse', 'HEAD'], {
    stdio: ['ignore', 'pipe', 'ignore'],
    env,
  })
    .toString('utf8')
    .trim();
  if (!/^[0-9a-f]{40}$/.test(out)) throw new Error('head_unresolvable');
  return out;
}

/** Canonical profile re-read from THIS module's own location. */
function readCanonicalProfileFields() {
  const profilePath = join(TOOL_DIR, '..', 'inventory', 'browser-authority-profile.json');
  const doc = JSON.parse(readFileSync(profilePath, 'utf8'));
  if (
    doc === null ||
    typeof doc !== 'object' ||
    doc.schema !== 'j1h2c/browser-authority-profile/1' ||
    doc.fields === null ||
    typeof doc.fields !== 'object' ||
    Array.isArray(doc.fields)
  ) {
    throw new Error('profile_shape');
  }
  for (const field of Object.values(doc.fields)) {
    if (
      field === null ||
      typeof field !== 'object' ||
      typeof field.env !== 'string' ||
      !/^J1H2C_[A-Z0-9_]+$/.test(field.env) ||
      field.required !== true
    ) {
      throw new Error('profile_shape');
    }
  }
  return doc.fields;
}

/**
 * The Playwright subprocess environment: every NODE_* and GIT_* variable is
 * stripped in ALL letter cases, every J1H2C_* variable that is NOT one of
 * the canonical profile's authorized names is stripped, and the 15
 * authorized names are set to the materialized values.
 */
function buildPlaywrightEnv(authorizedEnvByName, valuesByEnvName) {
  const authorized = new Set(Object.keys(authorizedEnvByName));
  const env = {};
  for (const [key, value] of Object.entries(process.env)) {
    const upper = key.toUpperCase();
    if (upper.startsWith('NODE_') || upper.startsWith('GIT_')) continue;
    if (upper.startsWith('J1H2C_') && !authorized.has(upper)) continue;
    env[key] = value;
  }
  for (const [envName, value] of Object.entries(valuesByEnvName)) {
    env[envName] = value;
  }
  return env;
}

/** Await a spawned process; resolve {pid, exit_code} — never pre-classified. */
function awaitExit(child) {
  return new Promise((resolve) => {
    let settled = false;
    const budget = setTimeout(() => {
      try {
        child.kill();
      } catch {
        // already gone
      }
    }, PLAYWRIGHT_BUDGET_MS);
    const hardKill = setTimeout(() => {
      try {
        child.kill('SIGKILL');
      } catch {
        // already gone
      }
    }, PLAYWRIGHT_BUDGET_MS + 5000);
    child.on('error', () => {
      if (settled) return;
      settled = true;
      clearTimeout(budget);
      clearTimeout(hardKill);
      resolve({ pid: child.pid ?? null, exit_code: null });
    });
    child.on('close', (code) => {
      if (settled) return;
      settled = true;
      clearTimeout(budget);
      clearTimeout(hardKill);
      resolve({ pid: child.pid ?? null, exit_code: Number.isInteger(code) ? code : null });
    });
  });
}

// ---------------------------------------------------------------------------
// 1. Fixed argv discipline — exactly [node, THIS FILE], nothing else.
// ---------------------------------------------------------------------------

let argvOk = false;
try {
  argvOk =
    process.argv.length === 2 && realpathSync(process.argv[1]).toLowerCase() === SELF_PATH.toLowerCase();
} catch {
  argvOk = false;
}
if (!argvOk) {
  emit(5, 'child_argv_shape_refused', false, 'child_argv_shape_refused', RESULT_PLAYWRIGHT_NEVER, NULL_CANDIDATE);
}

// ---------------------------------------------------------------------------
// 2. Exact stdin schema + canonical bindings.
// ---------------------------------------------------------------------------

let input = null;
try {
  const candidate = JSON.parse(readStdinText());
  if (
    exactKeys(candidate, [
      'schema',
      'input_sha',
      'cwd_sha',
      'candidate_sha',
      'owner_email_label',
      'values',
    ]) &&
    candidate.schema === INPUT_SCHEMA &&
    typeof candidate.input_sha === 'string' &&
    /^[0-9a-f]{64}$/.test(candidate.input_sha) &&
    typeof candidate.cwd_sha === 'string' &&
    /^[0-9a-f]{64}$/.test(candidate.cwd_sha) &&
    typeof candidate.candidate_sha === 'string' &&
    /^[0-9a-f]{40}$/.test(candidate.candidate_sha) &&
    typeof candidate.owner_email_label === 'string' &&
    candidate.owner_email_label.length > 0 &&
    candidate.values !== null &&
    typeof candidate.values === 'object' &&
    !Array.isArray(candidate.values) &&
    Object.values(candidate.values).every((value) => typeof value === 'string')
  ) {
    input = candidate;
  }
} catch {
  input = null;
}
if (input === null) {
  emit(3, 'child_input_schema_refused', false, 'child_input_schema_refused', RESULT_PLAYWRIGHT_NEVER, NULL_CANDIDATE);
}

let profileFields;
try {
  profileFields = readCanonicalProfileFields();
} catch {
  emit(3, 'child_profile_unreadable', false, 'child_profile_unreadable', RESULT_PLAYWRIGHT_NEVER, NULL_CANDIDATE);
}

// The 15 materialized values must map 1:1 onto the canonical profile keys.
const valuesByKey = input.values;
if (!exactKeys(valuesByKey, Object.keys(profileFields))) {
  emit(3, 'child_values_not_canonical', false, 'child_values_not_canonical', RESULT_PLAYWRIGHT_NEVER, NULL_CANDIDATE);
}

// Input binding: the runner-bound input SHA must cover EXACTLY the values
// this child is about to map into the Playwright environment.
const recomputedInputSha = sha256Hex(
  JSON.stringify({ owner_email_label: input.owner_email_label, values: valuesByKey }),
);
if (recomputedInputSha !== input.input_sha) {
  emit(3, 'child_input_sha_mismatch', false, 'child_input_sha_mismatch', RESULT_PLAYWRIGHT_NEVER, NULL_CANDIDATE);
}

const CWD = process.cwd();
let cwdReal;
try {
  cwdReal = realpathSync(CWD);
} catch {
  emit(3, 'child_cwd_unresolvable', false, 'child_cwd_unresolvable', RESULT_PLAYWRIGHT_NEVER, NULL_CANDIDATE);
}
if (sha256Hex(cwdReal) !== input.cwd_sha) {
  emit(3, 'child_cwd_sha_mismatch', false, 'child_cwd_sha_mismatch', RESULT_PLAYWRIGHT_NEVER, NULL_CANDIDATE);
}

let liveHead;
try {
  liveHead = resolveHead(CWD);
} catch {
  emit(5, 'child_candidate_unresolvable', false, 'child_candidate_unresolvable', RESULT_PLAYWRIGHT_NEVER, NULL_CANDIDATE);
}
if (liveHead !== input.candidate_sha) {
  emit(5, 'child_candidate_mismatch', false, 'child_candidate_mismatch', RESULT_PLAYWRIGHT_NEVER, liveHead);
}

// ---------------------------------------------------------------------------
// 3. Frozen Playwright CLI resolution + subprocess environment.
// ---------------------------------------------------------------------------

let cliPath;
try {
  const installDir = join(TOOL_DIR, '..', 'node_modules', '@playwright', 'test');
  const resolvedInstall = realpathSync(installDir);
  const installPackage = JSON.parse(readFileSync(join(resolvedInstall, 'package.json'), 'utf8'));
  if (installPackage.name !== '@playwright/test' || installPackage.version !== FROZEN_PLAYWRIGHT_VERSION) {
    throw new Error('version');
  }
  cliPath = realpathSync(join(resolvedInstall, 'cli.js'));
  if (!existsSync(cliPath)) throw new Error('missing');
} catch {
  emit(5, 'playwright_cli_unresolvable', false, 'playwright_cli_unresolvable', RESULT_PLAYWRIGHT_NEVER, liveHead);
}

const valuesByEnvName = {};
for (const [key, field] of Object.entries(profileFields)) {
  valuesByEnvName[field.env] = valuesByKey[key];
}
const playwrightEnv = buildPlaywrightEnv(valuesByEnvName, valuesByEnvName);

// ---------------------------------------------------------------------------
// 4. Atomic once-only invocation marker — BEFORE the real process starts.
// ---------------------------------------------------------------------------

const ARTIFACTS_DIR = join(cwdReal, 'artifacts');
const MARKER_PATH = join(ARTIFACTS_DIR, 'authority-invocation.json');
const runId = sha256Hex(`${process.pid}:${Date.now()}:${Math.random()}`).slice(0, 32);
const startedAtMs = Date.now();
try {
  mkdirSync(ARTIFACTS_DIR, { recursive: true });
} catch {
  emit(5, 'child_artifacts_unwritable', false, 'child_artifacts_unwritable', RESULT_PLAYWRIGHT_NEVER, liveHead);
}
let markerFd;
try {
  // Create-exclusive: any existing marker proves a prior invocation and
  // refuses THIS one before any process is spawned.
  markerFd = openSync(MARKER_PATH, 'wx');
} catch {
  emit(5, 'playwright_invocation_exceeded', false, 'playwright_invocation_exceeded', RESULT_PLAYWRIGHT_NEVER, liveHead);
}
try {
  writeSync(
    markerFd,
    Buffer.from(
      JSON.stringify({
        schema: INVOCATION_SCHEMA,
        playwright_invocation_count: 1,
        run_id: runId,
        candidate_sha: liveHead,
        wrapper_pid: process.pid,
        started_at_ms: startedAtMs,
      }) + '\n',
      'utf8',
    ),
  );
  // fsync via a fresh fsyncSync on the same fd is unavailable portably;
  // close + the create-exclusive guarantee above are the atomic record.
  closeSync(markerFd);
} catch {
  emit(5, 'child_marker_unwritable', false, 'child_marker_unwritable', RESULT_PLAYWRIGHT_NEVER, liveHead);
}

// ---------------------------------------------------------------------------
// 5. REAL Playwright process — argv array, shell:false, awaited exit.
// ---------------------------------------------------------------------------

const playwrightChild = spawn(process.execPath, [cliPath, 'test'], {
  cwd: cwdReal,
  env: playwrightEnv,
  stdio: ['ignore', 'ignore', 'ignore'],
  shell: false,
  windowsHide: true,
});
const playwrightOutcome = await awaitExit(playwrightChild);

const pw = {
  launched: true,
  pid: playwrightOutcome.pid,
  exit_code: playwrightOutcome.exit_code,
  invocation_count: 1,
};

function red(category) {
  emit(4, category, false, category, pw, liveHead);
}

if (pw.exit_code === null) red('playwright_exit_unobserved');
if (pw.exit_code !== 0) red('playwright_nonzero_exit');

// Post-run cross-binding: the marker must be intact and the candidate must
// not have moved during the run.
let marker;
try {
  marker = JSON.parse(readFileSync(MARKER_PATH, 'utf8'));
} catch {
  red('invocation_marker_unreadable');
}
if (
  !exactKeys(marker, [
    'schema',
    'playwright_invocation_count',
    'run_id',
    'candidate_sha',
    'wrapper_pid',
    'started_at_ms',
  ]) ||
  marker.schema !== INVOCATION_SCHEMA ||
  marker.playwright_invocation_count !== 1 ||
  marker.run_id !== runId ||
  marker.candidate_sha !== liveHead ||
  marker.wrapper_pid !== process.pid
) {
  red('invocation_marker_drift');
}
try {
  const postHead = resolveHead(CWD);
  if (postHead !== liveHead) red('candidate_drift_during_run');
} catch {
  red('candidate_unresolvable_post_run');
}

// ---------------------------------------------------------------------------
// 6. rc == 0 still must pass the REAL reconciliation + scanner gates.
// ---------------------------------------------------------------------------

function redEvidence(category) {
  red(category);
}

const reconciliationJsonPath = join(ARTIFACTS_DIR, 'reconciliation.json');
const reconciliationCsvPath = join(ARTIFACTS_DIR, 'reconciliation.csv');
const resultsJsonPath = join(ARTIFACTS_DIR, 'results.json');
const junitPath = join(ARTIFACTS_DIR, 'results-junit.xml');

for (const [path, category] of [
  [reconciliationJsonPath, 'reconciliation_json_missing'],
  [reconciliationCsvPath, 'reconciliation_csv_missing'],
  [resultsJsonPath, 'results_json_missing'],
  [junitPath, 'junit_missing'],
]) {
  if (!existsSync(path)) redEvidence(category);
}

// Freshness: every artifact must be produced during THIS invocation (after
// the pre-spawn marker), never a leftover of an older run.
for (const [path, category] of [
  [reconciliationJsonPath, 'reconciliation_stale'],
  [reconciliationCsvPath, 'reconciliation_stale'],
  [resultsJsonPath, 'results_stale'],
  [junitPath, 'junit_stale'],
]) {
  try {
    if (statSync(path).mtimeMs < startedAtMs) redEvidence(category);
  } catch {
    redEvidence(category);
  }
}

let reconciliation;
try {
  reconciliation = JSON.parse(readFileSync(reconciliationJsonPath, 'utf8'));
} catch {
  redEvidence('reconciliation_json_unparsable');
}
const expectedNodes = [
  ...BROWSER_NODE_IDS.map((nodeId) => ({ nodeId, surface: 'browser', outcome: 'PASS' })),
  ...STATIC_NODE_IDS.map((nodeId) => ({ nodeId, surface: 'static', outcome: 'PASS' })),
];
if (
  !exactKeys(reconciliation, ['schema', 'preconditionOutcome', 'note', 'summary', 'nodes']) ||
  reconciliation.schema !== RECONCILIATION_SCHEMA ||
  reconciliation.preconditionOutcome !== 'PRECONDITION_PASS' ||
  !exactKeys(reconciliation.summary, [
    'browser',
    'static',
    'total',
    'gap',
    'incomplete',
    'outcomes',
    'preconditionOutcome',
  ]) ||
  !exactKeys(reconciliation.summary.browser, ['total', 'pass']) ||
  !exactKeys(reconciliation.summary.static, ['total', 'pass']) ||
  reconciliation.summary.browser.total !== 15 ||
  reconciliation.summary.browser.pass !== 15 ||
  reconciliation.summary.static.total !== 2 ||
  reconciliation.summary.static.pass !== 2 ||
  reconciliation.summary.total !== 17 ||
  reconciliation.summary.gap !== 0 ||
  JSON.stringify(reconciliation.summary.incomplete) !== '[]' ||
  !exactKeys(reconciliation.summary.outcomes, ['pass', 'fail', 'notRun', 'pending']) ||
  reconciliation.summary.outcomes.pass !== 17 ||
  reconciliation.summary.outcomes.fail !== 0 ||
  reconciliation.summary.outcomes.notRun !== 0 ||
  reconciliation.summary.outcomes.pending !== 0 ||
  !Array.isArray(reconciliation.nodes) ||
  JSON.stringify(reconciliation.nodes) !== JSON.stringify(expectedNodes)
) {
  redEvidence('reconciliation_incomplete');
}

let csvText;
try {
  csvText = readFileSync(reconciliationCsvPath, 'utf8');
} catch {
  redEvidence('reconciliation_csv_unreadable');
}
const csvLines = csvText.split('\n').filter((line) => line.length > 0);
const expectedCsv = [
  'node_id,surface,outcome',
  ...expectedNodes.map((node) => `${node.nodeId},${node.surface},${node.outcome}`),
];
if (JSON.stringify(csvLines) !== JSON.stringify(expectedCsv)) {
  redEvidence('reconciliation_csv_mismatch');
}

let resultsJson;
try {
  resultsJson = JSON.parse(readFileSync(resultsJsonPath, 'utf8'));
} catch {
  redEvidence('results_json_unparsable');
}
// Playwright 1.49.1 JSON reporter stats: expected (passed), unexpected
// (failed/timed out), skipped, flaky (+ interrupted only when present).
if (
  resultsJson === null ||
  typeof resultsJson !== 'object' ||
  typeof resultsJson.stats !== 'object' ||
  resultsJson.stats === null ||
  resultsJson.stats.expected !== 15 ||
  resultsJson.stats.unexpected !== 0 ||
  resultsJson.stats.skipped !== 0 ||
  resultsJson.stats.flaky !== 0 ||
  (resultsJson.stats.interrupted ?? 0) !== 0
) {
  redEvidence('run_stats_not_all_green');
}

let junitText;
try {
  junitText = readFileSync(junitPath, 'utf8');
} catch {
  redEvidence('junit_unreadable');
}
if (
  !junitText.includes('tests="15"') ||
  !junitText.includes('failures="0"') ||
  !junitText.includes('skipped="0"') ||
  !junitText.includes('errors="0"') ||
  junitText.includes('<failure') ||
  junitText.includes('<error')
) {
  redEvidence('junit_not_all_green');
}

// ---------------------------------------------------------------------------
// 7. Artifact scanner over THIS run's evidence — from the frozen tools dir.
// ---------------------------------------------------------------------------

let scannerPath;
try {
  scannerPath = realpathSync(join(TOOL_DIR, 'scan-artifacts.mjs'));
} catch {
  redEvidence('scanner_missing');
}
const scanner = spawnSync(
  process.execPath,
  [
    scannerPath,
    '--artifacts-dir',
    'artifacts',
    '--maildir-root',
    valuesByKey.maildir_root,
    '--secrets-from-env',
  ],
  {
    cwd: cwdReal,
    env: playwrightEnv,
    stdio: ['ignore', 'pipe', 'pipe'],
    timeout: SCANNER_BUDGET_MS,
    encoding: 'utf8',
    windowsHide: true,
  },
);
const scannerOut = `${scanner.stdout ?? ''}`;
if (scanner.error || scanner.status !== 0 || !scannerOut.includes('ARTIFACT SCAN PASSED')) {
  redEvidence('scanner_not_clean');
}

// ---------------------------------------------------------------------------
// 8. Only now: complete=true, exit 0.
// ---------------------------------------------------------------------------

emit(0, 'child_complete', true, 'child_complete', pw, liveHead);
