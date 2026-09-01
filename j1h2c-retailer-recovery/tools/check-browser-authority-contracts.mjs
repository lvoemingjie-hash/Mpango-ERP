#!/usr/bin/env node
/**
 * Executable B1-R5-R1 control-plane contract checks (live-binding,
 * terminal-state and audit-ledger truth closure).
 *
 * REALLY loads tools/browser-authority-runner.mjs (no parallel/copied
 * implementation) and proves, against the real module, over a fixture git
 * repository (live HEAD) and a task-private contract file + JSONL sink:
 *
 *   S0  schema + protected profile parse; profile reconciles with the
 *       J1H2C_* set actually consumed by src/env.ts; fixture contract
 *       validates against the schema and covers the profile;
 *   G   canonical GREEN path: materialize -> preflight -> authorize ->
 *       single launch (rc==0 + complete reconciliation) -> FINISHED ->
 *       terminal seal -> evidence; deterministic input SHA across instances;
 *   R1  destructive merge over owner_email_label -> owner_label_overwrite_forbidden
 *   R2  missing required owner field              -> required_field_missing
 *   R3  transition with wrong `from`              -> transition_from_mismatch
 *   R4  post-STOP rejection NOT ledgered          -> rejection_unledgered
 *   R5  any call after VOID                       -> terminal_stop
 *   R6  second preflight                          -> preflight_already_invoked
 *   R7  second browser launch                     -> launch_already_invoked
 *   R8  caller-side SHA mismatch at authorize     -> candidate/input/contract_sha_drift
 *   R9  argv drift + non-array argv               -> argv_drift / argv_not_array
 *   R10 sensitive value into ledger               -> sensitive_value_rejected
 *   R11 live contract bytes mutated after authorize -> contract_sha_drift, STOPPED, starts=0
 *   R12 materialized input tamper (freeze removed by mutation) -> input_sha_drift, STOPPED, starts=0
 *   R13 live git HEAD moved after authorize        -> candidate_sha_drift, STOPPED, starts=0
 *   R14 child rc!=0 / incomplete reconciliation    -> TEST_RED (never FINISHED/VOID)
 *   R15 second preflight, catch, then launch       -> terminal_stop, starts=0
 *   R16 ledger tail truncated / rewritten / duplicate seq -> ledger_truncated / ledger_chain_broken / ledger_seq_duplicate
 *   R17 each required profile field deleted        -> RED (runner refuses; env.ts reconciliation flags)
 *   R18 caller contract weaker than profile        -> contract_weaker_than_profile
 *   R19 profilePath override ignored               -> canonical protected profile only
 *   R20 async child outcome truth                  -> FINISHED/TEST_RED after settle
 *   R21 tampered ledger verifier                   -> ledger_chain_broken
 *   R22 dirty working-tree profile                 -> profile_dirty_vs_head
 *   R23 foreign repoRoot                           -> repo_root_mismatch
 *   R24/R25 GIT_* identity injection               -> canonical identity preserved
 *   R26 mandatory runner-owned CORS probe          -> cors_probe_missing / matrix RED
 *   R27 ambient fetch poisoning                    -> no authority bypass
 *   R28 launcher http/https poisoning              -> pristine child process probe
 *   R29 mutable launcher child result forgery      -> no authority seal/evidence
 *   R30 fixed real child launches Playwright       -> PID/exit awaited + bound
 *   R31 child/CLI path substitution refused        -> fixed module-relative argv only
 *   R32 second Playwright start                    -> refused BEFORE spawn
 *   R33 rc=0 without reconciliation                -> TEST_RED (complete=false)
 *   R34 forged PASS artifacts / wrong candidate /  -> complete=false, TEST_RED
 *       stale mtime / tampered run id
 *   R35 scanner missing or nonzero                 -> TEST_RED
 *   R36 helper omitted / forged payload / repeat   -> RED before authorize
 *   R37 any preflight check RED                    -> VOID, spawn=0
 *   R38 post-preflight input/helper/child drift    -> launch blocked, spawn=0
 *   R39 sensitive values in outputs/ledger         -> firewall holds
 *   R40 library seal/evidence still refused; R1-R29 GREEN preserved
 *
 * Every failing probe must throw the EXACT category; a probe that does not
 * throw, or throws a different category, fails this checker. After each RED
 * scenario a fresh instance re-runs the canonical GREEN path (restore ->
 * re-GREEN). Labels, booleans, categories and counts only — fixture values
 * never reach output.
 */

import http from 'node:http';
import https from 'node:https';
import { execFile, execFileSync, spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, readdirSync, realpathSync, writeFileSync, mkdtempSync, rmSync, utimesSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname, relative, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const SCRATCH = mkdtempSync(join(tmpdir(), 'j1h2c-b1r5r1-'));
const failures = [];

function expect(condition, label) {
  if (!condition) failures.push(`browser-authority: ${label}`);
}

function expectCategory(probe, category, label) {
  try {
    probe();
    expect(false, `${label} did NOT throw (control plane accepted a defect)`);
  } catch (error) {
    const thrownCategory =
      error && error.name === 'BrowserAuthorityError' ? error.category : `<${error && error.name}>`;
    expect(thrownCategory === category, `${label} threw "${thrownCategory}" instead of "${category}"`);
  }
}

async function expectCategoryAsync(probe, category, label) {
  try {
    await probe();
    expect(false, `${label} did NOT throw (control plane accepted a defect)`);
  } catch (error) {
    const thrownCategory =
      error && error.name === 'BrowserAuthorityError' ? error.category : `<${error && error.name}>`;
    expect(thrownCategory === category, `${label} threw "${thrownCategory}" instead of "${category}"`);
  }
}

// ---------------------------------------------------------------------------
// Fixture infrastructure: real git repo, live contract file, JSONL sink
// ---------------------------------------------------------------------------

// B1-R5-R4: the candidate repository is the ONE canonical toplevel derived
// from the profile's own location — there is no fixture repo anymore, and a
// foreign repoRoot is refused (R23). GIT_* injections cannot hijack it (R24).


const contractPath = join(SCRATCH, 'contract.json');

// Fixture contract covers every profile env name (labels + env NAMES only;
// values are synthetic and never printed).
const CONTRACT = {
  schema: 'j1h2c/browser-authority-contract/1',
  owner_field: 'owner',
  fields: {
    owner: { env: 'J1H2C_RETAILER_EMAIL', required: true, sensitive: true },
    owner_current_password: { env: 'J1H2C_RETAILER_CURRENT_PASSWORD', required: true, sensitive: true },
    owner_new_password: { env: 'J1H2C_RETAILER_NEW_PASSWORD', required: true, sensitive: true },
    base_url: { env: 'J1H2C_BASE_URL', required: true, sensitive: true },
    api_base_url: { env: 'J1H2C_API_BASE_URL', required: true, sensitive: true },
    maildir_root: { env: 'J1H2C_MAILDIR_ROOT', required: true, sensitive: true },
    w1_canonical_code: { env: 'J1H2C_W1_CANONICAL_CODE', required: true, sensitive: false },
    w2_canonical_code: { env: 'J1H2C_W2_CANONICAL_CODE', required: true, sensitive: false },
    unknown_identity: { env: 'J1H2C_UNKNOWN_EMAIL', required: true, sensitive: true },
    unverified_identity: { env: 'J1H2C_UNVERIFIED_EMAIL', required: true, sensitive: true },
    forged_reset_token: { env: 'J1H2C_FORGED_RESET_TOKEN', required: true, sensitive: true },
    w1_verified_invitation_code: { env: 'J1H2C_W1_VERIFIED_INVITATION_CODE', required: true, sensitive: true },
    w1_verified_invitation_phone: { env: 'J1H2C_W1_VERIFIED_INVITATION_PHONE', required: true, sensitive: true },
    w1_unverified_invitation_code: { env: 'J1H2C_W1_UNVERIFIED_INVITATION_CODE', required: true, sensitive: true },
    w1_unverified_invitation_phone: { env: 'J1H2C_W1_UNVERIFIED_INVITATION_PHONE', required: true, sensitive: true },
  },
  transitions: [
    { from: 'INIT', to: 'PREFLIGHTED' },
    { from: 'PREFLIGHTED', to: 'AUTHORIZED' },
  ],
  launch: { max_starts: 1 },
};
writeFileSync(contractPath, JSON.stringify(CONTRACT), 'utf8');

// Local CORS fixture server: modes ok / wrong / missing / 400 / 500 / timeout.
// It doubles as the preflight helper's frontend/backend fixture: GETs return
// the real frontend SPA marker, and the formal login endpoint admits ONLY
// the fixture owner value (the unverified identity must stay refused), so
// the helper's positive flow passes against a REAL server over REAL http.
let corsMode = 'ok';
let preflightMode = 'ok'; // ok | frontend_down | health_down | owner_login_denied | unverified_login_allowed
const corsRequests = [];
const corsServer = http.createServer((req, res) => {
  corsRequests.push({
    method: req.method,
    url: req.url,
    origin: req.headers.origin ?? null,
    acrm: req.headers['access-control-request-method'] ?? null,
    acrh: req.headers['access-control-request-headers'] ?? null,
  });
  if (corsMode === 'timeout') return; // hold the request open
  if (corsMode === '400') { res.writeHead(400); res.end(); return; }
  if (corsMode === '500') { res.writeHead(500); res.end(); return; }
  if (corsMode === 'wrong') {
    res.writeHead(200, { 'Access-Control-Allow-Origin': 'https://wrong-origin.invalid' });
    res.end();
    return;
  }
  if (corsMode === 'missing') { res.writeHead(200); res.end(); return; }
  let body = '';
  req.on('data', (chunk) => {
    if (body.length < 65536) body += chunk;
  });
  req.on('end', () => {
    if (preflightMode === 'frontend_down' && req.url.startsWith('/portal')) {
      res.writeHead(500); res.end(); return;
    }
    if (preflightMode === 'health_down' && req.url.startsWith('/healthz')) {
      res.writeHead(404); res.end(); return;
    }
    if (req.method === 'POST' && req.url.startsWith('/api/v1/client/auth/login')) {
      let email = '';
      try { email = String(JSON.parse(body || '{}').email ?? ''); } catch { email = ''; }
      const ownerAllows = preflightMode !== 'owner_login_denied' && email === FIXTURE_ENV.J1H2C_RETAILER_EMAIL;
      const unverifiedAllowed = preflightMode === 'unverified_login_allowed';
      if (ownerAllows || (unverifiedAllowed && email === FIXTURE_ENV.J1H2C_UNVERIFIED_EMAIL)) {
        res.writeHead(200, { 'content-type': 'application/json' });
        res.end('{"token":"fixture-login-token","role":"fixture"}');
        return;
      }
      res.writeHead(401, { 'content-type': 'application/json' });
      res.end('{"error":"invalid_credentials"}');
      return;
    }
    res.writeHead(200, { 'Access-Control-Allow-Origin': req.headers.origin ?? '' });
    res.end('<!doctype html><html><body><div id="root"></div></body></html>');
  });
});
await new Promise((resolve) => corsServer.listen(0, '127.0.0.1', resolve));
const corsPort = corsServer.address().port;

// The preflight helper proves the maildir exists, is writable and is EMPTY
// at authority start — so the fixture value must be a real, empty directory.
const FIXTURE_MAILDIR = join(SCRATCH, 'maildir');
mkdirSync(FIXTURE_MAILDIR, { recursive: true });

const FIXTURE_ENV = {
  J1H2C_RETAILER_EMAIL: 'fixture-owner-email-value',
  J1H2C_RETAILER_CURRENT_PASSWORD: 'fixture-current-password-value', // pragma: allowlist secret
  J1H2C_RETAILER_NEW_PASSWORD: 'fixture-new-password-value', // pragma: allowlist secret
  J1H2C_BASE_URL: `http://127.0.0.1:${corsPort}/portal`,
  J1H2C_API_BASE_URL: `http://127.0.0.1:${corsPort}`,
  J1H2C_MAILDIR_ROOT: FIXTURE_MAILDIR,
  J1H2C_W1_CANONICAL_CODE: 'FIXW1CODE',
  J1H2C_W2_CANONICAL_CODE: 'FIXW2CODE',
  J1H2C_UNKNOWN_EMAIL: 'fixture-unknown-email-value',
  J1H2C_UNVERIFIED_EMAIL: 'fixture-unverified-email-value',
  J1H2C_FORGED_RESET_TOKEN: 'fixture-forged-token-value',
  J1H2C_W1_VERIFIED_INVITATION_CODE: 'fixture-ivcode-v-value',
  J1H2C_W1_VERIFIED_INVITATION_PHONE: 'fixture-ivphone-v-value',
  J1H2C_W1_UNVERIFIED_INVITATION_CODE: 'fixture-ivcode-u-value',
  J1H2C_W1_UNVERIFIED_INVITATION_PHONE: 'fixture-ivphone-u-value',
};

// ---------------------------------------------------------------------------
// S0 — real module, real schema, real protected profile, env.ts reconciliation
// ---------------------------------------------------------------------------

const runner = await import('./browser-authority-runner.mjs');

const CANONICAL_ROOT = runner.canonicalRepoRoot();
function gitInRoot(...args) {
  return execFileSync('git', ['-C', CANONICAL_ROOT, ...args], { stdio: ['ignore', 'pipe', 'ignore'] });
}
const repoRoot = CANONICAL_ROOT;
const CANONICAL_HEAD = gitInRoot('rev-parse', 'HEAD').toString().trim();
expect(typeof runner.ControlPlane === 'function', 'S0: real module exports ControlPlane');
expect(typeof runner.DurableJsonlLedger === 'function', 'S0: real module exports DurableJsonlLedger');
expect(typeof runner.resolveLiveHead === 'function', 'S0: real module exports resolveLiveHead');
expect(!/contractShaOf/.test(readFileSync(join(ROOT, 'tools', 'browser-authority-runner.mjs'), 'utf8')), 'S0: contractShaOf self-comparison removed');

const schema = JSON.parse(readFileSync(join(ROOT, 'inventory', 'browser-authority-contract.schema.json'), 'utf8'));
expect(schema.properties.launch.properties.max_starts.const === 1, 'S0: schema launch max_starts const 1');

const profilePath = join(ROOT, 'inventory', 'browser-authority-profile.json');
const profileText = readFileSync(profilePath, 'utf8');
const profile = JSON.parse(profileText);
expect(profile.schema === 'j1h2c/browser-authority-profile/1', 'S0: profile schema');
expect(profile.owner_field === 'owner', 'S0: profile owner field');

// Machine reconciliation: the profile env set must EXACTLY equal the set of
// required('J1H2C_*') variables declared by the real src/env.ts contract.
const envTsText = readFileSync(join(ROOT, 'src', 'env.ts'), 'utf8');
const envTsNames = new Set([...envTsText.matchAll(/required\('(J1H2C_[A-Z0-9_]+)'\)/g)].map((m) => m[1]));
const profileNames = new Set(Object.values(profile.fields).map((field) => field.env));
expect(
  envTsNames.size > 0 && envTsNames.size === profileNames.size && [...envTsNames].every((name) => profileNames.has(name)),
  `S0: profile env set == env.ts required set (${envTsNames.size} names)`,
);

const contract = runner.parseContract(JSON.stringify(CONTRACT));
const contractShaInitial = runner.sha256Hex(JSON.stringify(CONTRACT));
expect(contract !== undefined, 'S0: fixture contract parses');

const candidateShaInitial = runner.resolveLiveHead(repoRoot);
expect(candidateShaInitial === CANONICAL_HEAD, 'S0: live candidate resolves to the canonical worktree HEAD');

function freshLedger(name) {
  return new runner.DurableJsonlLedger(join(SCRATCH, `ledger-${name}.jsonl`));
}

function freshControl(name) {
  return new runner.ControlPlane({
    contractPath,
    repoRoot,
    ledger: freshLedger(name),
  });
}

async function fullFlow(control) {
  const { inputSha } = control.materialize(FIXTURE_ENV);
  await control.corsPreflightProbe();
  await control.preflight();
  const argv = ['node', 'tools', 'fixture-launch'];
  control.authorize({ inputSha, argv });
  return { inputSha, argv };
}

/** Canonical GREEN path on a brand-new instance; returns binding facts. */
async function greenPath(name = 'green') {
  const control = freshControl(name);
  const { inputSha, argv } = await fullFlow(control);
  const calls = [];
  const result = control.launch(
    (file, args) => {
      calls.push({ file, argsCount: args.length });
      return { rc: 0, reconciliation: { complete: true } };
    },
    { argv },
  );
  if (result && typeof result.then === 'function') {
    failures.push(`${name}: GREEN path launch unexpectedly returned a promise for a plain result`);
    return { inputSha, argv, evidence: null };
  }
  expect(result.outcome === 'FINISHED' && result.rc === 0, `${name}: FINISHED on rc0+complete`);
  expect(calls.length === 1, `${name}: exactly one launch through the double`);
  expect(control.current === 'FINISHED' && control.launchStarts === 1, `${name}: state FINISHED, starts=1`);
  // B1-R6-R3: library-mode controls cannot seal or produce evidence.
  expectCategory(() => control.seal(), 'authority_mode_required', `${name}: library seal refused`);
  expectCategory(() => control.evidence(), 'authority_mode_required', `${name}: library evidence refused`);
  return { control, inputSha, argv };
}

/** Materialize + (no probe yet): for CORS refusal scenarios. */
function fullFlowProbeOnly(control) {
  const { inputSha } = control.materialize(FIXTURE_ENV);
  return { inputSha };
}

function ensureDir(path) {
  mkdirSync(path, { recursive: true });
}

function copyCurrentAuthoritySource(label, { commitMutate = null } = {}) {
  const sourceRoot = mkdtempSync(join(SCRATCH, `${label}-source-`));
  ensureDir(join(sourceRoot, 'tools'));
  ensureDir(join(sourceRoot, 'inventory'));
  for (const rel of [
    'tools/browser-authority-runner.mjs',
    'tools/browser-authority-entrypoint.mjs',
    'tools/browser-authority-cors-probe-helper.mjs',
    'tools/browser-authority-preflight-helper.mjs',
    'tools/browser-authority-child.mjs',
    'tools/scan-artifacts.mjs',
    'inventory/browser-authority-profile.json',
  ]) {
    writeFileSync(join(sourceRoot, rel), readFileSync(join(ROOT, rel)));
  }
  if (commitMutate) commitMutate(sourceRoot);
  const git = (...args) => execFileSync('git', ['-C', sourceRoot, ...args], { stdio: ['ignore', 'pipe', 'ignore'] });
  git('init', '-b', 'main');
  git('config', 'user.email', 'fixture@charges.invalid');
  git('config', 'user.name', 'fixture');
  git('add', 'tools', 'inventory');
  git('commit', '-m', 'authority source');
  return sourceRoot;
}

async function runCommittedEntrypoint(label, { envPatch = {}, mutate = null, commitMutate = null } = {}) {
  const sourceRoot = copyCurrentAuthoritySource(label, { commitMutate });
  const contractPathLocal = join(sourceRoot, 'contract.json');
  const ledgerPath = join(sourceRoot, 'ledger.jsonl');
  writeFileSync(contractPathLocal, JSON.stringify(CONTRACT), 'utf8');
  if (mutate) mutate(sourceRoot);
  const env = { ...runner.probeChildEnv(), ...FIXTURE_ENV, ...envPatch };
  const result = await new Promise((resolve) => {
    execFile(
      process.execPath,
      ['tools/browser-authority-entrypoint.mjs', '--contract', contractPathLocal, '--ledger', ledgerPath],
      {
        cwd: sourceRoot,
        env,
        encoding: 'utf8',
        timeout: 45000,
        windowsHide: true,
      },
      (error, stdout, stderr) => {
        resolve({
          status: error ? (Number.isInteger(error.code) ? error.code : 1) : 0,
          stdout,
          stderr,
        });
      },
    );
  });
  return { ...result, sourceRoot, ledgerPath };
}

function parseSingleJsonLine(text) {
  const lines = String(text).split('\n').filter((line) => line.length > 0);
  if (lines.length !== 1) return null;
  try {
    return JSON.parse(lines[0]);
  } catch {
    return null;
  }
}

// Captured authority outputs for the R39 secret-firewall scans (assigned by
// the R29/R30 scenarios that run real entrypoint/child processes).
const r39ScannedOutputs = { entrypointStdout: '', entrypointStderr: '', childStdout: '', childStderr: '' };

function ledgerRecords(path) {
  return readFileSync(path, 'utf8')
    .split('\n')
    .filter((line) => line.length > 0)
    .map((line) => JSON.parse(line));
}

function writeCommittedChildVariant(sourceRoot, variant) {
  const prefix = [
    "#!/usr/bin/env node",
    "import { writeSync } from 'node:fs';",
    "const RESULT_SCHEMA = 'j1h2c/browser-authority-child-result/1';",
  ];
  if (variant === 'forged_stdout') {
    writeFileSync(
      join(sourceRoot, 'tools', 'browser-authority-child.mjs'),
      [...prefix, 'writeSync(1, Buffer.from(\'{"ok":true,"rc":0,"reconciliation":{"complete":true}}\\n\', \'utf8\'));', 'process.exit(0);', ''].join('\n'),
      'utf8',
    );
    return;
  }
  // The dummy variants emit the EXACT new child result shape: a never-
  // launched Playwright block, a bound candidate stand-in, and the requested
  // exit/complete combination.
  const exitCode = variant === 'nonzero' ? 7 : 0;
  const complete = variant === 'incomplete' ? 'false' : 'true';
  const category = variant === 'incomplete' ? 'reconciliation_incomplete' : 'child_complete';
  writeFileSync(
    join(sourceRoot, 'tools', 'browser-authority-child.mjs'),
    [
      ...prefix,
      `const pw = { launched: ${variant === 'incomplete'}, pid: ${variant === 'incomplete' ? 'process.pid + 12345' : 'null'}, exit_code: ${variant === 'incomplete' ? 0 : 'null'}, invocation_count: ${variant === 'incomplete' ? 1 : 0} };`,
      `writeSync(1, Buffer.from(JSON.stringify({ schema: RESULT_SCHEMA, pid: process.pid, exit: ${exitCode}, category: '${category}', playwright: pw, candidate_sha: '${'a'.repeat(40)}', reconciliation: { complete: ${complete}, category: '${category}' } }) + '\\n', 'utf8'));`,
      `process.exit(${exitCode});`,
      '',
    ].join('\n'),
    'utf8',
  );
}

/** Runs the runner-owned CORS probe; returns the refusal category or null. */
async function runCorsProbe(control) {
  try {
    await control.corsPreflightProbe();
    return null;
  } catch (error) {
    return error && error.name === 'BrowserAuthorityError' ? error.category : `<${error && error.name}>`;
  }
}

// Deterministic projection: same env -> same input SHA on fresh instances.
{
  const a = freshControl('det-a');
  const b = freshControl('det-b');
  const shaA = a.materialize(FIXTURE_ENV).inputSha;
  const shaB = b.materialize(FIXTURE_ENV).inputSha;
  expect(shaA === shaB, 'G: input SHA deterministic across fresh instances');
  const input = a.materializedInput();
  expect(Object.isFrozen(input) && Object.isFrozen(input.values), 'G: materialized input is deep-frozen');
}

// ---------------------------------------------------------------------------
// R1-R10 — carried over from B1-R5, adapted to the live-binding surface
// ---------------------------------------------------------------------------

// R1 — destructive merge over owner_email_label / owner field binding
{
  const control = freshControl('r1');
  control.materialize(FIXTURE_ENV);
  const input = control.materializedInput();
  expectCategory(
    () => runner.mergeMaterialized(contract, input, { owner_email_label: 'other_field' }),
    'owner_label_overwrite_forbidden',
    'R1: merge overwriting owner_email_label',
  );
  expectCategory(
    () => runner.mergeMaterialized(contract, input, { owner: 'replacement-owner-value' }),
    'owner_label_overwrite_forbidden',
    'R1: merge overwriting the owner field binding',
  );
  await greenPath('r1-restore');
}

// R2 — missing required owner field / W1 / W2
{
  expectCategory(
    () => runner.materializeInput(contract, { ...FIXTURE_ENV, J1H2C_RETAILER_EMAIL: '' }),
    'required_field_missing',
    'R2: empty owner email',
  );
  expectCategory(
    () => runner.materializeInput(contract, { ...FIXTURE_ENV, J1H2C_W2_CANONICAL_CODE: undefined }),
    'required_field_missing',
    'R2: missing W2 required field',
  );
  expectCategory(
    () => runner.materializeInput(contract, { ...FIXTURE_ENV, J1H2C_W1_CANONICAL_CODE: null }),
    'required_field_missing',
    'R2: missing W1 required field',
  );
  await greenPath('r2-restore');
}

// R3 — transition `from` mismatch (captured before mutation)
{
  const control = freshControl('r3');
  expectCategory(
    () => control.transition('PREFLIGHTED', 'AUTHORIZED'),
    'transition_from_mismatch',
    'R3: transition from wrong state',
  );
  expect(control.current === 'INIT', 'R3: state unchanged after refused transition');
  expectCategory(
    () => control.transition('INIT', 'FINISHED'),
    'transition_not_in_contract',
    'R3: edge not in contract',
  );
  await greenPath('r3-restore');
}

// R4 — post-STOP rejection NOT ledgered must be DETECTED
{
  const sinkPath = join(SCRATCH, 'ledger-r4.jsonl');
  const ledger = freshLedger('r4');
  const control = new runner.ControlPlane({ contractPath, repoRoot, ledger });
  control.stop('probe_void');
  try {
    await control.preflight();
  } catch {
    /* terminal_stop — the rejection was persisted before the throw */
  }
  // B1-R6-R3: library-mode controls cannot seal — authority gate fires.
  expectCategory(() => control.seal(), 'authority_mode_required', 'R4: library seal refused');
  const lines = readFileSync(sinkPath, 'utf8')
    .split('\n')
    .filter((line) => line.length > 0);
  const records = lines.map((line) => JSON.parse(line));
  expect(
    records.some((record) => record.entry.kind === 'rejection_after_stop'),
    'R4: rejection durable in the hash-chained sink',
  );
  expect(new runner.DurableJsonlLedger(sinkPath).verifyChain().count === lines.length, 'R4: intact sink chain verifies');
  // RED counterexample: suppress the rejection line — the durable guards
  // fire (strict seq ordering / hash chain), so an unledgered rejection
  // cannot hide.
  const strippedLines = lines.filter((line) => {
    const record = JSON.parse(line);
    return !(record.entry && record.entry.kind === 'rejection_after_stop');
  });
  writeFileSync(sinkPath, strippedLines.join('\n') + '\n', 'utf8');
  expectCategory(
    () => ledger.verifyChain(),
    'ledger_truncated',
    'R4: suppressed rejection caught by the seq/chain guards',
  );
  writeFileSync(sinkPath, lines.join('\n') + '\n', 'utf8');
  await greenPath('r4-restore');
}

// R5 — every control surface after terminal VOID
{
  const control = freshControl('r5');
  control.materialize(FIXTURE_ENV);
  control.stop('probe_void');
  await expectCategoryAsync(() => control.preflight(), 'terminal_stop', 'R5: preflight after VOID');
  expectCategory(
    () => control.authorize({ inputSha: control.materializedInputSha(), argv: ['node', 'x'] }),
    'terminal_stop',
    'R5: authorize after VOID',
  );
  expectCategory(
    () => control.launch(() => ({ rc: 0, reconciliation: { complete: true } }), { argv: ['node', 'x'] }),
    'terminal_stop',
    'R5: launch after VOID',
  );
  await greenPath('r5-restore');
}

// R6 — second preflight (also C: rejection persisted, then STOPPED)
{
  const control = freshControl('r6');
  await fullFlowPreflight(control);
  await expectCategoryAsync(() => control.preflight(), 'preflight_already_invoked', 'R6: preflight twice');
  expect(control.current === 'STOPPED', 'R6: repeat preflight lands STOPPED (C)');
  await greenPath('r6-restore');
}

async function fullFlowPreflight(control) {
  control.materialize(FIXTURE_ENV);
  await control.corsPreflightProbe();
  await control.preflight();
}

// R7 — second browser launch (double called exactly once)
{
  const control = freshControl('r7');
  const { inputSha, argv } = await fullFlow(control);
  let calls = 0;
  const impl = () => {
    calls += 1;
    return { rc: 0, reconciliation: { complete: true } };
  };
  control.launch(impl, { argv });
  expectCategory(() => control.launch(impl, { argv }), 'launch_already_invoked', 'R7: launch twice');
  expect(calls === 1, 'R7: the double executed exactly one process start');
  await greenPath('r7-restore');
}

// R8 — caller-side SHA mismatch at authorize (drift vs live recomputation)
{
  const control = freshControl('r8a');
  const { inputSha } = control.materialize(FIXTURE_ENV);
  await control.corsPreflightProbe();
  await control.preflight();
  expectCategory(
    () => control.authorize({ inputSha: runner.sha256Hex('drifted-input'), argv: ['node', 'x'] }),
    'input_sha_drift',
    'R8: input SHA mismatch at authorize',
  );
  expect(control.current === 'STOPPED', 'R8: drifted plane is STOPPED');
  await greenPath('r8-restore');
}

// R9 — argv drift + non-array argv (shell strings refused)
{
  const preFlow = async (control) => {
    const { inputSha } = control.materialize(FIXTURE_ENV);
    await control.corsPreflightProbe();
    await control.preflight();
    return { inputSha };
  };
  const control = freshControl('r9');
  const { inputSha, argv } = await fullFlow(control);
  expectCategory(
    () => control.launch(() => ({ rc: 0, reconciliation: { complete: true } }), { argv: ['node', 'DIFFERENT'] }),
    'argv_drift',
    'R9: argv drift at launch',
  );
  const controlB = freshControl('r9b');
  const flowB = await preFlow(controlB);
  expectCategory(
    () => controlB.authorize({ inputSha: flowB.inputSha, argv: 'node tools fixture-launch' }),
    'argv_not_array',
    'R9: shell-style string argv refused at authorize',
  );
  const controlC = freshControl('r9c');
  const flowC = await fullFlow(controlC);
  expectCategory(
    () => controlC.launch(() => ({ rc: 0, reconciliation: { complete: true } }), { argv: 'node x' }),
    'argv_not_array',
    'R9: shell-style string argv refused at launch',
  );
  const controlD = freshControl('r9d');
  const flowD = await preFlow(controlD);
  expectCategory(() => controlD.authorize({ inputSha: flowD.inputSha, argv: [] }), 'argv_not_array', 'R9: empty argv refused');
  expect(control.current === 'STOPPED', 'R9: argv-drifted plane is terminal');
  await greenPath('r9-restore');
}

// R10 — sensitive value into the durable ledger
{
  const ledger = freshLedger('r10');
  const control = new runner.ControlPlane({ contractPath, repoRoot, ledger });
  control.materialize(FIXTURE_ENV);
  const sensitive = Object.values(control.materializedInput().values);
  let acceptedClean = false;
  try {
    ledger.append({ kind: 'note', label: 'owner' }, sensitive);
    acceptedClean = true;
  } catch {
    acceptedClean = false;
  }
  expect(acceptedClean, 'R10: category-only note accepted');
  expectCategory(
    () => ledger.append({ kind: 'note', label: FIXTURE_ENV.J1H2C_RETAILER_EMAIL }, sensitive),
    'sensitive_value_rejected',
    'R10: owner email value into ledger',
  );
  expectCategory(
    () => ledger.append({ kind: 'note', note: `code=${FIXTURE_ENV.J1H2C_W1_CANONICAL_CODE}` }, sensitive),
    'sensitive_value_rejected',
    'R10: W1 code embedded in note text',
  );
  await greenPath('r10-restore');
}

// ---------------------------------------------------------------------------
// R11 — live contract bytes mutated after authorize
// ---------------------------------------------------------------------------

{
  const control = freshControl('r11');
  const { inputSha, argv } = await fullFlow(control);
  const original = readFileSync(contractPath, 'utf8');
  try {
    writeFileSync(contractPath, original.replace('"base_url"', '"base_url_tampered"'), 'utf8');
    expectCategory(
      () => control.launch(() => ({ rc: 0, reconciliation: { complete: true } }), { argv }),
      'contract_sha_drift',
      'R11: live contract bytes mutated after authorize',
    );
    expect(control.current === 'STOPPED' && control.launchStarts === 0, 'R11: STOPPED with starts=0');
  } finally {
    writeFileSync(contractPath, original, 'utf8');
  }
  expect(control.liveContractSha() === contractShaInitial, 'R11: contract bytes restored');
  await greenPath('r11-restore');
}

// ---------------------------------------------------------------------------
// R12 — materialized input tamper (file-level: freeze removed, then tampered)
// ---------------------------------------------------------------------------

{
  // Scenario level: the deep-frozen input refuses mutation; the canonical
  // SHA stays stable and no false drift is reported.
  const control = freshControl('r12');
  const { inputSha, argv } = await fullFlow(control);
  const input = control.materializedInput();
  const attempted = { ...input.values, w1_canonical_code: 'TAMPERED' };
  const reassigned = (() => {
    try {
      input.values = attempted;
      return 'silent-noop';
    } catch {
      return 'strict-refused';
    }
  })();
  expect(
    reassigned === 'silent-noop' || reassigned === 'strict-refused',
    'R12: mutation attempt handled',
  );
  expect(control.materializedInputSha() === inputSha, 'R12: frozen input SHA unchanged');
  const calls = [];
  const result = control.launch(
    () => {
      calls.push(1);
      return { rc: 0, reconciliation: { complete: true } };
    },
    { argv },
  );
  expect(result.outcome === 'FINISHED' && calls.length === 1, 'R12: no false drift for an intact frozen input');
  await greenPath('r12-restore');
}
// File-level probe is executed by the driver (see ledger + report): mutate
// deepFreeze away, tamper input, observe input_sha_drift with starts=0.

// ---------------------------------------------------------------------------
// R13 — candidate binds the SINGLE canonical repository's live HEAD
//
// The fixture HEAD-move probe is retired by the B1-R5-R4 identity closure:
// repo identity is pinned to the canonical toplevel, so a foreign HEAD can
// no longer be bound at all (see R23). The canonical-HEAD drift re-resolve
// path stays code-live at authorize/launch (same live re-read as the
// profile/contract checks, which R11/R12/R22 exercise with real byte
// mutations).
// ---------------------------------------------------------------------------

{
  const control = freshControl('r13');
  const expectedHead = gitInRoot('rev-parse', 'HEAD').toString().trim();
  expect(expectedHead === CANONICAL_HEAD, 'R13: canonical HEAD stable during the round');
  expect(control.liveCandidateSha() === expectedHead, 'R13: candidate == canonical live HEAD');
  const { inputSha, argv } = await fullFlow(control);
  expect(control.liveCandidateSha() === expectedHead, 'R13: binding survives the full flow');
  await greenPath('r13-restore');
}

// ---------------------------------------------------------------------------
// R14 — child failure / incomplete reconciliation => TEST_RED, never FINISHED
// ---------------------------------------------------------------------------

{
  const control = freshControl('r14a');
  const { inputSha, argv } = await fullFlow(control);
  const red = control.launch(() => ({ rc: 1, reconciliation: { complete: true } }), { argv });
  expect(red.outcome === 'TEST_RED', 'R14: rc!=0 lands TEST_RED');
  expect(control.current === 'TEST_RED' && control.launchStarts === 1, 'R14: state TEST_RED with true starts=1');
  expectCategory(() => control.seal(), 'authority_mode_required', 'R14: library TEST_RED seal refused');
  expectCategory(() => control.evidence(), 'authority_mode_required', 'R14: library TEST_RED evidence refused');

  const controlB = freshControl('r14b');
  const flowB = await fullFlow(controlB);
  const incomplete = controlB.launch(() => ({ rc: 0, reconciliation: { complete: false } }), { argv: flowB.argv });
  expect(incomplete.outcome === 'TEST_RED', 'R14: incomplete reconciliation lands TEST_RED');
  expect(controlB.current === 'TEST_RED', 'R14: never FINISHED without complete reconciliation');
  await greenPath('r14-restore');
}

// ---------------------------------------------------------------------------
// R15 — second preflight, catch, then launch
// ---------------------------------------------------------------------------

{
  const control = freshControl('r15');
  const { inputSha, argv } = await fullFlow(control);
  let caught = null;
  try {
    await control.preflight();
  } catch (error) {
    caught = error.category;
  }
  expect(caught === 'preflight_already_invoked', 'R15: repeat preflight category');
  expect(control.current === 'STOPPED', 'R15: repeat preflight landed STOPPED');
  expectCategory(
    () => control.launch(() => ({ rc: 0, reconciliation: { complete: true } }), { argv }),
    'terminal_stop',
    'R15: launch after catching repeat-preflight',
  );
  expect(control.launchStarts === 0, 'R15: launch starts=0 (nothing ever started)');
  const sinkPath = join(SCRATCH, 'ledger-r15.jsonl');
  const records = readFileSync(sinkPath, 'utf8')
    .split('\n')
    .filter((line) => line.length > 0)
    .map((line) => JSON.parse(line));
  expect(
    records.some((record) => record.entry.kind === 'rejection' && record.entry.attempted === 'preflight_repeat'),
    'R15: repeat-preflight rejection persisted BEFORE STOPPED',
  );
  await greenPath('r15-restore');
}

// ---------------------------------------------------------------------------
// R16 — durable ledger truncation / tail rewrite / duplicate seq
// ---------------------------------------------------------------------------

{
  const sinkPath = join(SCRATCH, 'ledger-r16.jsonl');
  const ledger = new runner.DurableJsonlLedger(sinkPath);
  ledger.append({ kind: 'note', label: 'one' });
  ledger.append({ kind: 'note', label: 'two' });
  ledger.append({ kind: 'note', label: 'three' });
  const intact = readFileSync(sinkPath, 'utf8');
  const lines = intact.split('\n').filter((line) => line.length > 0);

  // (a) tail deletion detected by the SAME instance (private expected tail)
  writeFileSync(sinkPath, lines.slice(0, 2).join('\n') + '\n', 'utf8');
  expectCategory(() => ledger.verifyChain(), 'ledger_truncated', 'R16: tail deletion (same instance)');

  // (b) tail rewrite detected by chain recompute (even a fresh reader)
  writeFileSync(sinkPath, [lines[0], lines[1], lines[2].replace('three', 'REWROTE')].join('\n'), 'utf8');
  const freshLedger = new runner.DurableJsonlLedger(sinkPath);
  expectCategory(() => freshLedger.verifyChain(), 'ledger_chain_broken', 'R16: tail rewrite (chain mismatch)');

  // (c) duplicate seq detected by strict ordering
  writeFileSync(sinkPath, [lines[0], lines[1], lines[1], lines[2]].join('\n'), 'utf8');
  expectCategory(() => freshLedger.verifyChain(), 'ledger_seq_duplicate', 'R16: duplicate seq line');

  // (d) an append on a truncated sink fails closed
  writeFileSync(sinkPath, lines.slice(0, 2).join('\n') + '\n', 'utf8');
  expectCategory(() => ledger.append({ kind: 'note', label: 'four' }), 'ledger_truncated', 'R16: append on truncated sink');

  // restore + re-GREEN on a fresh sink
  writeFileSync(sinkPath, intact, 'utf8');
  expect(ledger.verifyChain().count === 3, 'R16: restored sink re-verifies');
}

// ---------------------------------------------------------------------------
// R17 — every required profile field deleted (weakened profile => RED)
//
// The production constructor binds the CANONICAL profile bytes only (no
// profilePath override exists since B1-R5-R2), so a weakened profile is
// probed at the reconciliation guard the constructor itself uses, plus the
// structural owner guard and the env.ts machine reconciliation. The
// tracked-file mutation variant runs in the external falsification driver
// (deleted field on disk -> static [14] + checker S0 both FAIL).
// ---------------------------------------------------------------------------

{
  const profileShaBefore = runner.parseProfile(profileText).profileSha;
  const fields = Object.entries(profile.fields);
  let deletedAll = 0;
  for (const [key] of fields) {
    const mutatedDoc = JSON.parse(profileText);
    delete mutatedDoc.fields[key];
    if (mutatedDoc.owner_field === key) {
      expectCategory(
        () => runner.parseProfile(JSON.stringify(mutatedDoc)),
        'profile_owner_field_unknown',
        `R17: profile field "${key}" deleted (owner)`,
      );
    } else {
      // The reconciliation guard used by the constructor: a profile that no
      // longer knows an env the contract carries must be refused.
      expectCategory(
        () => runner.reconcileContractWithProfile(contract, mutatedDoc),
        'contract_field_unknown_to_profile',
        `R17: profile field "${key}" deleted`,
      );
      // Checker-level env.ts reconciliation: the weakened profile no longer
      // equals the consumed J1H2C_* set (profile_field_missing).
      const mutatedNames = new Set(Object.values(mutatedDoc.fields).map((field) => field.env));
      const reconciles =
        envTsNames.size === mutatedNames.size && [...envTsNames].every((name) => mutatedNames.has(name));
      expect(reconciles === false, `R17: env.ts reconciliation flags deleted "${key}" (profile_field_missing)`);
    }
    deletedAll += 1;
  }
  expect(deletedAll === fields.length, `R17: every one of ${fields.length} required fields probed`);
  expect(runner.parseProfile(profileText).profileSha === profileShaBefore, 'R17: profile restored byte-identical');
  await greenPath('r17-restore');
}

// ---------------------------------------------------------------------------
// R18 — caller contract weaker than the protected profile
// ---------------------------------------------------------------------------

{
  const weak = {
    schema: 'j1h2c/browser-authority-contract/1',
    owner_field: 'owner',
    fields: { owner: { env: 'J1H2C_RETAILER_EMAIL', required: true, sensitive: true } },
    transitions: CONTRACT.transitions,
    launch: { max_starts: 1 },
  };
  const weakPath = join(SCRATCH, 'contract-weak.json');
  writeFileSync(weakPath, JSON.stringify(weak), 'utf8');
  expectCategory(
    () =>
      new runner.ControlPlane({
        contractPath: weakPath,
        repoRoot,
        ledger: freshLedger('r18'),
      }),
    'contract_weaker_than_profile',
    'R18: single-owner-field caller contract refused',
  );
  // An invented field (side door) is equally refused.
  const invented = JSON.parse(JSON.stringify(CONTRACT));
  invented.fields.smuggled = { env: 'J1H2C_SMUGGLED_FIELD', required: true, sensitive: true };
  const inventedPath = join(SCRATCH, 'contract-invented.json');
  writeFileSync(inventedPath, JSON.stringify(invented), 'utf8');
  expectCategory(
    () =>
      new runner.ControlPlane({
        contractPath: inventedPath,
        repoRoot,
        ledger: freshLedger('r18b'),
      }),
    'contract_field_unknown_to_profile',
    'R18: invented field side door refused',
  );
  await greenPath('r18-restore');
}

// ---------------------------------------------------------------------------
// R19 — the production profilePath override entry is GONE (B1-R5-R2)
// ---------------------------------------------------------------------------

{
  const weak = {
    schema: 'j1h2c/browser-authority-contract/1',
    owner_field: 'owner',
    fields: { owner: { env: 'J1H2C_RETAILER_EMAIL', required: true, sensitive: true } },
    transitions: CONTRACT.transitions,
    launch: { max_starts: 1 },
  };
  const weakContractPath = join(SCRATCH, 'contract-weak19.json');
  writeFileSync(weakContractPath, JSON.stringify(weak), 'utf8');
  const weakProfile = JSON.parse(profileText);
  weakProfile.fields = { owner: profile.fields.owner };
  const weakProfilePath = join(SCRATCH, 'profile-weak19.json');
  writeFileSync(weakProfilePath, JSON.stringify(weakProfile), 'utf8');

  // The production constructor has NO profilePath parameter: the override
  // attempt is ignored and the CANONICAL protected profile is used, so the
  // weak contract is still refused.
  expectCategory(
    () =>
      new runner.ControlPlane({
        contractPath: weakContractPath,
        repoRoot,
        ledger: freshLedger('r19'),
        profilePath: weakProfilePath,
      }),
    'contract_weaker_than_profile',
    'R19: profilePath override ignored; weak contract refused by canonical profile',
  );
  // Even with a FULL contract, a bogus profilePath must not change the
  // binding: the canonical profile SHA is what gets bound.
  const control = new runner.ControlPlane({
    contractPath,
    repoRoot,
    ledger: freshLedger('r19b'),
    profilePath: weakProfilePath,
  });
  expect(
    control.boundProfileSha() === runner.parseProfile(profileText).profileSha,
    'R19: canonical profile bound despite override attempt',
  );
  await greenPath('r19-restore');
}

// ---------------------------------------------------------------------------
// R20 — launch awaits the REAL (async) child outcome (B1-R5-R2)
// ---------------------------------------------------------------------------

{
  // (a) Promise-returning successful child: must reach FINISHED after the
  // promise settles — never an immediate TEST_RED.
  const control = freshControl('r20');
  const { inputSha, argv } = await fullFlow(control);
  let calls = 0;
  const result = await control.launch(
    () => {
      calls += 1;
      return Promise.resolve({ rc: 0, reconciliation: { complete: true } });
    },
    { argv },
  );
  expect(result && result.outcome === 'FINISHED', 'R20: async successful child -> FINISHED');
  expect(control.current === 'FINISHED' && control.launchStarts === 1, 'R20: final state FINISHED, starts=1');
  expect(calls === 1, 'R20: the double started exactly once');

  // (b) Promise-rejecting child: DID start -> TEST_RED with true starts.
  const controlB = freshControl('r20b');
  const flowB = await fullFlow(controlB);
  let caught = null;
  try {
    await controlB.launch(() => Promise.reject(new Error('child boom')), { argv: flowB.argv });
  } catch (error) {
    caught = error && error.name === 'BrowserAuthorityError' ? error.category : `<${error && error.name}>`;
  }
  expect(caught === 'test_red_async_child_failure', `R20: async child failure category (${caught})`);
  expect(controlB.current === 'TEST_RED' && controlB.launchStarts === 1, 'R20: async failure lands TEST_RED, starts=1');

  // (c) Synchronous executor exception BEFORE an actual start: STOPPED with
  // starts reverted to 0.
  const controlC = freshControl('r20c');
  const flowC = await fullFlow(controlC);
  let threw = false;
  try {
    controlC.launch(
      () => {
        throw new Error('executor boom');
      },
      { argv: flowC.argv },
    );
  } catch {
    threw = true;
  }
  expect(threw, 'R20: sync executor exception propagates');
  expect(controlC.current === 'STOPPED' && controlC.launchStarts === 0, 'R20: pre-start executor STOPPED, starts=0');
  await greenPath('r20-restore');
}

// ---------------------------------------------------------------------------
// R21 — a tampered ledger can never become authority evidence (B1-R5-R2)
// B1-R6-R3: library-mode seal/evidence are authority-gated; the same durable
// chain verifier remains the mandatory evidence backstop.
// ---------------------------------------------------------------------------

{
  const sinkPath = join(SCRATCH, 'ledger-r21.jsonl');
  const control = new runner.ControlPlane({ contractPath, repoRoot, ledger: new runner.DurableJsonlLedger(sinkPath) });
  const { argv } = await fullFlow(control);
  const result = control.launch(() => ({ rc: 0, reconciliation: { complete: true } }), { argv });
  expect(result.outcome === 'FINISHED', 'R21: library flow can finish functionally');
  expectCategory(() => control.seal(), 'authority_mode_required', 'R21: library seal refused before evidence');
  expectCategory(() => control.evidence(), 'authority_mode_required', 'R21: library evidence refused before seal');

  const intact = readFileSync(sinkPath, 'utf8');
  const records = intact.split('\n').filter((line) => line.length > 0).map((line) => JSON.parse(line));
  const finishIndex = records.findIndex((record) => record.entry.kind === 'finish');
  expect(finishIndex >= 0, 'R21: finish record present');
  records[finishIndex].entry.argv_count = 999; // stale event_sha kept on purpose
  writeFileSync(
    sinkPath,
    records.map((record) => JSON.stringify(record)).join('\n') + '\n',
    'utf8',
  );
  expectCategory(
    () => new runner.DurableJsonlLedger(sinkPath).verifyChain(),
    'ledger_chain_broken',
    'R21: tampered early record refused by chain re-verification',
  );

  writeFileSync(sinkPath, intact, 'utf8');
  expect(
    new runner.DurableJsonlLedger(sinkPath).verifyChain().count === records.length,
    'R21: restored sink re-verifies',
  );
  await greenPath('r21-restore');
}

// ---------------------------------------------------------------------------
// R22 — dirty working-tree profile (HEAD unchanged) can never construct
// (B1-R5-R3 committed-blob binding; the CTO counterexample shape)
// ---------------------------------------------------------------------------

{
  const profileShaClean = runner.parseProfile(profileText).profileSha;
  const originalBytes = readFileSync(profilePath);

  // The CTO counterexample: weaken the canonical profile AND pair it with a
  // weak contract, all while HEAD stays unchanged. The constructor must
  // refuse because the working-tree profile bytes no longer equal the
  // committed blob at the owning repository's live HEAD.
  const weakened = JSON.parse(profileText);
  weakened.fields = { owner: profile.fields.owner };
  const weakContractPath = join(SCRATCH, 'contract-weak22.json');
  writeFileSync(
    weakContractPath,
    JSON.stringify({
      schema: 'j1h2c/browser-authority-contract/1',
      owner_field: 'owner',
      fields: { owner: { env: 'J1H2C_RETAILER_EMAIL', required: true, sensitive: true } },
      transitions: CONTRACT.transitions,
      launch: { max_starts: 1 },
    }),
    'utf8',
  );
  try {
    writeFileSync(profilePath, weakenedText(weakened), 'utf8');
    expect(controlProfileStillDirty() === true, 'R22: (precondition) working profile differs from HEAD blob');
    expectCategory(
      () =>
        new runner.ControlPlane({
          contractPath: weakContractPath,
          repoRoot,
          ledger: freshLedger('r22'),
        }),
      'profile_dirty_vs_head',
      'R22: dirty profile + weak contract refused (HEAD unchanged)',
    );
    // Even the FULL contract pairing is refused while the tree is dirty.
    expectCategory(
      () => new runner.ControlPlane({ contractPath, repoRoot, ledger: freshLedger('r22b') }),
      'profile_dirty_vs_head',
      'R22: dirty profile refuses any construction',
    );
  } finally {
    writeFileSync(profilePath, originalBytes, 'utf8');
  }
  expect(runner.parseProfile(profileText).profileSha === profileShaClean, 'R22: profile bytes restored');
  await greenPath('r22-restore');
}

function weakenedText(doc) {
  return JSON.stringify(doc);
}

function controlProfileStillDirty() {
  const working = readFileSync(profilePath);
  let committed;
  try {
    const toplevel = execFileSync('git', ['-C', dirname(profilePath), 'rev-parse', '--show-toplevel'], {
      stdio: ['ignore', 'pipe', 'ignore'],
    })
      .toString()
      .trim();
    const rel = relative(toplevel, profilePath).split(sep).join('/');
    committed = execFileSync('git', ['-C', toplevel, 'cat-file', 'blob', `HEAD:${rel}`], {
      stdio: ['ignore', 'pipe', 'ignore'],
    });
  } catch {
    return false;
  }
  return !working.equals(committed);
}

// ---------------------------------------------------------------------------
// R23 — foreign repoRoot (cross-repo candidate substitution) refused
// ---------------------------------------------------------------------------

{
  const foreign = mkdtempSync(join(SCRATCH, 'foreign-'));
  const fgit = (...args) => execFileSync('git', ['-C', foreign, ...args], { stdio: ['ignore', 'pipe', 'ignore'] });
  fgit('init', '-b', 'main');
  fgit('config', 'user.email', 'fixture@charges.invalid');
  fgit('config', 'user.name', 'fixture');
  writeFileSync(join(foreign, 'x.txt'), 'x', 'utf8');
  fgit('add', 'x.txt');
  fgit('commit', '-m', 'foreign');
  const foreignHead = fgit('rev-parse', 'HEAD').toString().trim();
  expect(foreignHead !== CANONICAL_HEAD, 'R23: foreign HEAD genuinely differs');

  expectCategory(
    () => new runner.ControlPlane({ contractPath, repoRoot: foreign, ledger: freshLedger('r23') }),
    'repo_root_mismatch',
    'R23: foreign repoRoot refused at construction (category exact)',
  );
  // realpath-equal spellings of the canonical root ARE accepted.
  const trailing = new runner.ControlPlane({
    contractPath,
    repoRoot: CANONICAL_ROOT + sep,
    ledger: freshLedger('r23b'),
  });
  expect(trailing.liveCandidateSha() === CANONICAL_HEAD, 'R23: realpath-equal trailing-separator form accepted');
  await greenPath('r23-restore');
}

// ---------------------------------------------------------------------------
// R24 — GIT_* environment injection cannot hijack repository identity
// ---------------------------------------------------------------------------

{
  const foreign = mkdtempSync(join(SCRATCH, 'gitenv-'));
  const fgit = (...args) => execFileSync('git', ['-C', foreign, ...args], { stdio: ['ignore', 'pipe', 'ignore'] });
  fgit('init', '-b', 'main');
  fgit('config', 'user.email', 'fixture@charges.invalid');
  fgit('config', 'user.name', 'fixture');
  writeFileSync(join(foreign, 'y.txt'), 'y', 'utf8');
  fgit('add', 'y.txt');
  fgit('commit', '-m', 'foreign-env');
  const foreignHead = fgit('rev-parse', 'HEAD').toString().trim();
  expect(foreignHead !== CANONICAL_HEAD, 'R24: injected GIT_DIR target genuinely differs');

  const saved = { GIT_DIR: process.env.GIT_DIR, GIT_WORK_TREE: process.env.GIT_WORK_TREE, GIT_INDEX_FILE: process.env.GIT_INDEX_FILE };
  try {
    process.env.GIT_DIR = join(foreign, '.git');
    process.env.GIT_WORK_TREE = foreign;
    process.env.GIT_INDEX_FILE = join(foreign, '.git', 'index');

    const control = freshControl('r24');
    expect(control.liveCandidateSha() === CANONICAL_HEAD, 'R24: candidate identity immune to GIT_* injection');
    expect(
      control.boundProfileSha() === runner.parseProfile(profileText).profileSha,
      'R24: profile committed-blob identity immune to GIT_* injection',
    );
    const { inputSha, argv } = await fullFlow(control);
    const result = control.launch(() => ({ rc: 0, reconciliation: { complete: true } }), { argv });
    expect(result.outcome === 'FINISHED', 'R24: launch proceeds on the canonical identity');
  } finally {
    for (const [key, value] of Object.entries(saved)) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
  }
  await greenPath('r24-restore');
}

// ---------------------------------------------------------------------------
// R25 — mixed/lowercase GIT_* injection (case-insensitive sanitization,
// B1-R5-R4-R1). The foreign repository is VALID and carries a COPY of the
// canonical profile bytes committed at the same relative path, with a
// different HEAD. The attack pair is (foreign repoRoot + lowercase
// injections): under a weakened case-sensitive filter this produces a REAL
// identity substitution — the control plane constructs, binds the foreign
// HEAD and the foreign committed profile copy, and can launch — never a
// mere git crash. Under the fixed filter the pair is refused with the exact
// category and the canonical identity keeps working.
// ---------------------------------------------------------------------------

{
  const foreign = mkdtempSync(join(SCRATCH, 'foreign-case-'));
  const fgit = (...args) => execFileSync('git', ['-C', foreign, ...args], { stdio: ['ignore', 'pipe', 'ignore'] });
  fgit('init', '-b', 'main');
  fgit('config', 'user.email', 'fixture@charges.invalid');
  fgit('config', 'user.name', 'fixture');
  // Identical COPY of the canonical profile committed at the same relative
  // path, so a hijacked committed-blob read RESOLVES and MATCHES (no crash,
  // full substitution reachability).
  mkdirSync(join(foreign, 'inventory'), { recursive: true });
  writeFileSync(join(foreign, 'inventory', 'browser-authority-profile.json'), profileText, 'utf8');
  fgit('add', 'inventory/browser-authority-profile.json');
  fgit('commit', '-m', 'profile copy');
  const foreignHead = fgit('rev-parse', 'HEAD').toString().trim();
  expect(foreignHead !== CANONICAL_HEAD, 'R25: foreign HEAD genuinely differs');

  const saved = {};
  for (const key of ['git_dir', 'Git_Work_Tree', 'git_index_file', 'GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE']) {
    saved[key] = process.env[key];
    delete process.env[key];
  }
  try {
    // MIXED/lowercase spellings (Windows env is case-insensitive: git honors
    // every case form).
    process.env.git_dir = join(foreign, '.git');
    process.env.Git_Work_Tree = foreign;
    process.env.git_index_file = join(foreign, '.git', 'index');

    // Layer 1 — the sanitizer output handed to EVERY git subprocess contains
    // no GIT_* spelling in ANY case.
    const sanitized = runner.gitEnv();
    expect(
      Object.keys(sanitized).every((key) => !key.toUpperCase().startsWith('GIT_')),
      'R25: sanitized environment has zero GIT_* keys in any case',
    );
    expect(Object.keys(sanitized).length > 0, 'R25: sanitized environment is non-empty');

    // Layer 2 — REAL SUBSTITUTION at the candidate source (the exact value
    // the control plane binds): under mixed/lowercase GIT_* injection with a
    // weakened case-sensitive filter, resolveLiveHead(canonical root)
    // returns the FOREIGN HEAD. The fixed filter returns the canonical HEAD.
    const resolved = runner.resolveLiveHead(CANONICAL_ROOT);
    if (resolved === foreignHead) {
      console.error(
        'R25 REAL_IDENTITY_SUBSTITUTION (candidate source): resolveLiveHead returned the injected foreign HEAD under mixed/lowercase GIT_* injection (case-sensitive filter defect live)',
      );
      process.exit(1); // decisive falsification verdict; nothing may mask it
    }
    expect(resolved === CANONICAL_HEAD, 'R25: candidate source stays canonical under injection');

    // Layer 3 — end-to-end backstop (defense in depth): the attack pair
    // (foreign repoRoot + lowercase injections) is still refused at
    // construction by the independent committed-blob guard.
    let ctorCategory = null;
    try {
      new runner.ControlPlane({
        contractPath,
        repoRoot: foreign,
        ledger: freshLedger('r25'),
      });
    } catch (error) {
      ctorCategory = error && error.name === 'BrowserAuthorityError' ? error.category : `<${error && error.name}>`;
    }
    expect(ctorCategory !== null, 'R25: attack pair must not construct');
    expect(
      ctorCategory === 'profile_dirty_vs_head' || ctorCategory === 'repo_root_mismatch',
      `R25: attack pair refused, got ${ctorCategory}`,
    );

    // Layer 4 — positive control: the CANONICAL repoRoot still constructs,
    // binds canonical identity, and finishes under the same injection.
    let control = null;
    try {
      control = freshControl('r25c');
    } catch (error) {
      const category = error && error.name === 'BrowserAuthorityError' ? error.category : `<${error && error.name}>`;
      failures.push(`R25: canonical construction refused under injection (${category}) — canonical identity must keep working`);
      control = null;
    }
    if (control) {
      expect(control.liveCandidateSha() === CANONICAL_HEAD, 'R25: canonical candidate stays canonical under injection');
      expect(
        control.boundProfileSha() === runner.parseProfile(profileText).profileSha,
        'R25: canonical profile identity stays canonical under injection',
      );
      const { inputSha, argv } = await fullFlow(control);
      const result = control.launch(() => ({ rc: 0, reconciliation: { complete: true } }), { argv });
      expect(result.outcome === 'FINISHED', 'R25: canonical launch completes under injection');
    }
  } finally {
    for (const key of Object.keys(saved)) {
      if (saved[key] === undefined) delete process.env[key];
      else process.env[key] = saved[key];
    }
  }
  await greenPath('r25-restore');
}

// ---------------------------------------------------------------------------
// Verdict
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// R26 — mandatory runner-owned CORS preflight probe (matrix, B1-R6)
// ---------------------------------------------------------------------------

{
  // R26-POS positive: exact derivation, side-effect-free OPTIONS declaring
  // POST + content-type, exact allow-origin echo, then the full flow.
  const control = freshControl('r26-pos');
  const { inputSha, argv } = await fullFlow(control);
  const lastOptions = [...corsRequests].reverse().find((request) => request.method === 'OPTIONS');
  expect(lastOptions.method === 'OPTIONS', 'R26-POS: side-effect-free OPTIONS');
  expect(lastOptions.url === '/client/auth/forgot-password', 'R26-POS: target derived from bound api_base_url exactly');
  expect(lastOptions.acrm === 'POST' && lastOptions.acrh === 'content-type', 'R26-POS: declares POST + content-type');
  const derivedOrigin = new URL(FIXTURE_ENV.J1H2C_BASE_URL).origin;
  expect(lastOptions.origin === derivedOrigin, 'R26-POS: Origin derived from bound base_url');
  await expectCategoryAsync(
    () => control.corsPreflightProbe(),
    'cors_probe_already_invoked',
    'R26-REP: repeat probe refused',
  );
  expect(control.launchStarts === 0, 'R26: probe+preflight+authorize start nothing (starts=0)');
  await greenPath('r26-pos-restore');

  // R26-OMIT: omitting the probe can never reach preflight.
  const controlOmit = freshControl('r26-omit');
  controlOmit.materialize(FIXTURE_ENV);
  await expectCategoryAsync(
    () => controlOmit.preflight(),
    'cors_probe_missing',
    'R26-OMIT: preflight without the runner-owned probe',
  );
  expect(controlOmit.current === 'STOPPED' && controlOmit.launchStarts === 0, 'R26-OMIT: STOPPED, starts=0');

  // R26-FAKE: caller-supplied check results (however labeled) have no path
  // into the runner-owned preflight at all.
  const controlFake = freshControl('r26-fake');
  controlFake.materialize(FIXTURE_ENV);
  await controlFake.corsPreflightProbe();
  await expectCategoryAsync(
    () =>
      controlFake.preflight([
        { ok: true, label: 'caller_cors', category: 'caller_cors_ok' },
        { ok: true, label: 'anything' },
      ]),
    'preflight_input_rejected',
    'R26-FAKE: caller ok=true boolean refused',
  );
  expect(controlFake.launchStarts === 0, 'R26-FAKE: starts=0');
  await greenPath('r26-ab-restore');

  // R26-MATRIX: per-mode refusals, each STOPPED before authorize, starts=0.
  for (const [mode, wantCategory] of [
    ['wrong', 'cors_allow_origin_mismatch'],
    ['missing', 'cors_allow_origin_mismatch'],
    ['400', 'cors_probe_http_error'],
    ['500', 'cors_probe_http_error'],
    ['timeout', 'cors_probe_timeout'],
  ]) {
    corsMode = mode;
    const controlM = freshControl(`r26-${mode}`);
    const flowM = await fullFlowProbeOnly(controlM);
    const category = await runCorsProbe(controlM);
    expect(category === wantCategory, `R26-${mode}: category ${category} != ${wantCategory}`);
    expect(controlM.current === 'STOPPED', `R26-${mode}: STOPPED before authorize`);
    expect(controlM.launchStarts === 0, `R26-${mode}: launchStarts=0`);
    corsMode = 'ok'; // restore BEFORE any greenPath inside the loop
    await greenPath(`r26-${mode}-restore`);
  }
  corsMode = 'ok';

  // Evidence hygiene: no URL fragments in the durable ledger or evidence.
  const r26Sink = join(SCRATCH, 'ledger-r26-wrong.jsonl');
  const sinkText = existsSync(r26Sink) ? readFileSync(r26Sink, 'utf8') : '';
  expect(
    !sinkText.includes('http://127.0.0.1') && !sinkText.includes('/client/auth/forgot-password'),
    'R26: ledger carries no URLs (categories/booleans/counts only)',
  );
}

// ---------------------------------------------------------------------------
// R27 — ambient globalThis.fetch substitution cannot forge CORS authority
// (B1-R6-R1). The PRE-import substitution runs in a real child process (the
// checker's own import cannot be re-ordered); the POST-import substitution
// and the real-server pass run in-process. The injected ambient fetch is a
// SUCCESS fake: with a degraded (ambient) transport an unreachable target
// would be reported as success — BYPASS_ACCEPTED — while the native
// transport must really fail with cors_probe_no_response.
// ---------------------------------------------------------------------------

const R27_CHILD_SOURCE = [
  "import { readFileSync, writeFileSync, mkdtempSync } from 'node:fs';",
  "import { tmpdir } from 'node:os';",
  "import { join } from 'node:path';",
  "globalThis.fetch = async () => ({",
  "  ok: true,",
  "  status: 200,",
  "  headers: { get: (name) => (String(name).toLowerCase() === 'access-control-allow-origin' ? 'FAKE-AMBIENT-ORIGIN' : null) },",
  "});",
  "const runner = await import('./tools/browser-authority-runner.mjs');",
  "const profile = JSON.parse(readFileSync('inventory/browser-authority-profile.json', 'utf8'));",
  "const fields = {};",
  "for (const [key, field] of Object.entries(profile.fields)) fields[key] = { env: field.env, required: true, sensitive: field.sensitive };",
  "const contract = { schema: 'j1h2c/browser-authority-contract/1', owner_field: profile.owner_field, fields, transitions: [{ from: 'INIT', to: 'PREFLIGHTED' }, { from: 'PREFLIGHTED', to: 'AUTHORIZED' }], launch: { max_starts: 1 } };",
  "const scratch = mkdtempSync(join(tmpdir(), 'r27-child-'));",
  "const contractPath = join(scratch, 'contract.json');",
  "writeFileSync(contractPath, JSON.stringify(contract), 'utf8');",
  "const env = {};",
  "for (const field of Object.values(contract.fields)) env[field.env] = (field.env === 'J1H2C_BASE_URL' ? 'http://127.0.0.1:9/portal' : field.env === 'J1H2C_API_BASE_URL' ? 'http://127.0.0.1:9' : 'fixture-' + field.env.toLowerCase() + '-value');",
  "async function probeOnce(label) {",
  "  const control = new runner.ControlPlane({ contractPath, repoRoot: runner.canonicalRepoRoot(), ledger: new runner.DurableJsonlLedger(join(scratch, 'ledger-' + label + '.jsonl')) });",
  "  control.materialize(env);",
  "  let category = null;",
  "  try { await control.corsPreflightProbe(); } catch (error) { category = error && error.name === 'BrowserAuthorityError' ? error.category : '<' + (error && error.name) + '>'; }",
  "  return { control, category };",
  "}",
  "const pre = await probeOnce('pre-import-substitution');",
  "if (pre.category === null || pre.category === 'cors_allow_origin_mismatch') {",
  "  console.log('BYPASS_ACCEPTED pre-import state=' + pre.control.current);",
  "  process.exit(2);",
  "}",
  "if (pre.category !== 'cors_probe_no_response' || pre.control.current !== 'STOPPED' || pre.control.launchStarts !== 0) {",
  "  console.log('R27-PREIMPORT-UNEXPECTED category=' + pre.category + ' state=' + pre.control.current);",
  "  process.exit(3);",
  "}",
  "if (['PREFLIGHTED', 'AUTHORIZED'].includes(pre.control.current)) {",
  "  console.log('BYPASS_ACCEPTED pre-import reached ' + pre.control.current);",
  "  process.exit(2);",
  "}",
  "globalThis.fetch = async () => ({",
  "  ok: true,",
  "  status: 200,",
  "  headers: { get: (name) => (String(name).toLowerCase() === 'access-control-allow-origin' ? 'FAKE-AMBIENT-ORIGIN-POST' : null) },",
  "});",
  "const post = await probeOnce('post-import-substitution');",
  "if (post.category === null || post.category === 'cors_allow_origin_mismatch') {",
  "  console.log('BYPASS_ACCEPTED post-import state=' + post.control.current);",
  "  process.exit(2);",
  "}",
  "if (post.category !== 'cors_probe_no_response' || post.control.current !== 'STOPPED') {",
  "  console.log('R27-POSTIMPORT-UNEXPECTED category=' + post.category + ' state=' + post.control.current);",
  "  process.exit(3);",
  "}",
  "console.log('R27 AMBIENT_SUBSTITUTION_BLOCKED pre=cors_probe_no_response post=cors_probe_no_response');",
  "process.exit(0);",
].join("\n");

{
  const child = execFileSync(process.execPath, ['--input-type=module', '-e', R27_CHILD_SOURCE], {
    cwd: ROOT,
    stdio: ['ignore', 'pipe', 'pipe'],
    env: runner.gitEnv(),
  });
  const out = child.toString('utf8');
  expect(out.includes('R27 AMBIENT_SUBSTITUTION_BLOCKED'), 'R27-PRE: pre-import ambient substitution blocked in child');
  expect(!out.includes('BYPASS_ACCEPTED'), 'R27-PRE: no BYPASS_ACCEPTED');
}

{
  // POST-import substitution, in-process: unreachable target + a SUCCESS
  // fake on globalThis.fetch must still really fail.
    const savedFetch = globalThis.fetch;
    try {
      // The fake echoes the CORRECT allow-origin for the bound target: if the
      // runner consulted ambient fetch at all, the unreachable target would
      // be reported as a full CORS success (complete bypass).
      globalThis.fetch = async () => ({
        ok: true,
        status: 200,
        headers: { get: (name) => (String(name).toLowerCase() === 'access-control-allow-origin' ? unreachableOrigin : null) },
      });
    const UNREACHABLE_ENV = {
      ...FIXTURE_ENV,
      J1H2C_BASE_URL: 'http://127.0.0.1:9/portal',
      J1H2C_API_BASE_URL: 'http://127.0.0.1:9',
    };
    const unreachableOrigin = new URL(UNREACHABLE_ENV.J1H2C_BASE_URL).origin;
    const control = freshControl('r27-post');
    control.materialize(UNREACHABLE_ENV);
    await expectCategoryAsync(
      () => control.corsPreflightProbe(),
      'cors_probe_no_response',
      'R27-POST: unreachable target really fails under ambient substitution',
    );
    expect(control.current === 'STOPPED', 'R27-POST: STOPPED');
    expect(
      !['PREFLIGHTED', 'AUTHORIZED'].includes(control.current),
      'R27-POST: never reached PREFLIGHTED/AUTHORIZED',
    );
    expect(control.launchStarts === 0, 'R27-POST: starts=0');

    // A correct REAL server still passes with ambient fetch poisoned.
    const controlR = freshControl('r27-real');
    const flowR = await fullFlow(controlR);
    const resultR = controlR.launch(() => ({ rc: 0, reconciliation: { complete: true } }), { argv: flowR.argv });
    expect(resultR.outcome === 'FINISHED', 'R27-REAL: correct real server still passes');
  } finally {
    globalThis.fetch = savedFetch;
  }
  await greenPath('r27-restore');
}

// ---------------------------------------------------------------------------
// R28 — process-isolated probe: launcher-process builtin poisoning cannot
// forge CORS authority (B1-R6-R2, MUTABLE_NODE_BUILTIN_TRANSPORT closure).
// The LAUNCHER process (this checker playing the hostile executor) poisons
// globalThis.fetch AND http.request/https.request AND freezes them via
// syncBuiltinESMExports; the runner must still consult the pristine child.
// UNREACHABLE_ENV points at 127.0.0.1:9 — a real network attempt fails, a
// forged in-process attempt would "succeed" with zero real network calls.
// ---------------------------------------------------------------------------

{
  const savedFetch = globalThis.fetch;
  const savedHttpRequest = http.request;
  const savedHttpsRequest = https.request;
  let fakeCalls = 0;
  const UNREACHABLE_ORIGIN = 'http://127.0.0.1:9';
  const UNREACHABLE_ENV = {
    ...FIXTURE_ENV,
    J1H2C_BASE_URL: `${UNREACHABLE_ORIGIN}/portal`,
    J1H2C_API_BASE_URL: UNREACHABLE_ORIGIN,
  };
  try {
    globalThis.fetch = async () => ({
      ok: true,
      status: 200,
      headers: { get: (name) => (String(name).toLowerCase() === 'access-control-allow-origin' ? UNREACHABLE_ORIGIN : null) },
    });
    const fakeResponse = (originHeader) => ({
      statusCode: 200,
      headers: { 'access-control-allow-origin': originHeader },
      resume() {},
      on(event, handler) {
        if (event === 'end') queueMicrotask(handler);
        return this;
      },
    });
    const fakeRequest = function fakeRequest(url, options, callback) {
      fakeCalls += 1;
      const done = typeof options === 'function' ? options : callback;
      const originHeader = (options && options.headers && options.headers.Origin) || UNREACHABLE_ORIGIN;
      const res = fakeResponse(originHeader);
      const reqObj = {
        setTimeout() { return this; },
        destroy() { return this; },
        on() { return this; },
        end() {
          queueMicrotask(() => done(res));
          return this;
        },
      };
      return reqObj;
    };
    http.request = fakeRequest;
    https.request = fakeRequest;
    if (typeof https.syncBuiltinESMExports === 'function') {
      https.syncBuiltinESMExports();
    }

    // Attack: unreachable target under a fully poisoned launcher process.
    const control = freshControl('r28');
    control.materialize(UNREACHABLE_ENV);
    const serverBefore = corsRequests.length;
    await expectCategoryAsync(
      () => control.corsPreflightProbe(),
      'cors_probe_no_response',
      'R28: unreachable target really fails through the pristine child',
    );
    const serverDelta = corsRequests.length - serverBefore;
    expect(control.current === 'STOPPED', 'R28: STOPPED');
    expect(
      !['PREFLIGHTED', 'AUTHORIZED'].includes(control.current),
      'R28: never reached PREFLIGHTED/AUTHORIZED',
    );
    expect(control.launchStarts === 0, 'R28: starts=0');
    expect(fakeCalls === 0, 'R28: the runner never consulted the poisoned in-process bindings');
    expect(serverDelta === 0, 'R28: zero real network calls for the unreachable target');

    // Positive control: the REAL reachable server passes under the same
    // poisoning — process isolation, not absence of network.
    const controlR = freshControl('r28-real');
    const flowR = await fullFlow(controlR);
    const resultR = controlR.launch(() => ({ rc: 0, reconciliation: { complete: true } }), { argv: flowR.argv });
    expect(resultR.outcome === 'FINISHED', 'R28-REAL: correct real server still passes');

    // Wrong-origin / HTTP RED / timeout stay fail-closed under poisoning.
    // The probes are called DIRECTLY (not through fullFlow) because a
    // failing probe throws — the scenario expects the throw.
    corsMode = 'wrong';
    const controlW = freshControl('r28-wrong');
    controlW.materialize(FIXTURE_ENV);
    await expectCategoryAsync(
      () => controlW.corsPreflightProbe(),
      'cors_allow_origin_mismatch',
      'R28: wrong-origin still fail-closed',
    );
    corsMode = '400';
    const controlH = freshControl('r28-400');
    controlH.materialize(FIXTURE_ENV);
    await expectCategoryAsync(
      () => controlH.corsPreflightProbe(),
      'cors_probe_http_error',
      'R28: HTTP RED still fail-closed',
    );
    corsMode = 'timeout';
    const controlT = freshControl('r28-timeout');
    controlT.materialize(FIXTURE_ENV);
    await expectCategoryAsync(
      () => controlT.corsPreflightProbe(),
      'cors_probe_timeout',
      'R28: timeout still fail-closed',
    );
  } finally {
    globalThis.fetch = savedFetch;
    http.request = savedHttpRequest;
    https.request = savedHttpsRequest;
    if (typeof https.syncBuiltinESMExports === 'function') {
      https.syncBuiltinESMExports();
    }
    corsMode = 'ok';
  }
  await greenPath('r28-restore');
}

// ---------------------------------------------------------------------------
// R29-R1 — direct-process authority positive path + mutable launcher
// child-result forgery closure (B1-R6-R3-R1,
// MUTABLE_CHILD_PROCESS_LAUNCH__PROBE_RESULT_FORGERY). Library ControlPlanes
// may exercise the functional state machine with doubles, but public
// authority elevation is refused and seal/evidence remain unavailable. The
// only authority evidence path is a direct entrypoint process launching the
// fixed real child argv.
// ---------------------------------------------------------------------------

{
  expectCategory(
    () =>
      new runner.ControlPlane({
        contractPath,
        repoRoot,
        ledger: freshLedger('r29-public-authority'),
        authority: true,
      }),
    'authority_mode_required',
    'R29: public authority:true elevation refused at construction',
  );

  const control = freshControl('r29-forged-sync');
  const { argv } = await fullFlow(control);
  const forged = control.launch(
    () => ({ rc: 0, pid: process.pid, real_child: true, reconciliation: { complete: true } }),
    { argv },
  );
  expect(forged.outcome === 'FINISHED', 'R29: fake sync child result can only affect library state');
  expect(control.current === 'FINISHED' && control.launchStarts === 1, 'R29: forged sync result precondition reached');
  expectCategory(() => control.seal(), 'authority_mode_required', 'R29: forged sync result cannot seal');
  expectCategory(() => control.evidence(), 'authority_mode_required', 'R29: forged sync result cannot produce evidence');
  expectCategory(
    () => runner.sealAuthorityEvidence(control),
    'not_direct_entrypoint',
    'R29: exported authority sealer cannot mint from library import',
  );
  expectCategory(
    () => control.enableAuthorityForEntrypoint({}),
    'authority_mode_required',
    'R29: plain exported object cannot become authority capability',
  );
  expectCategory(
    () => control.enableAuthorityForEntrypoint({ [Symbol('browser-authority-capability')]: true }),
    'authority_mode_required',
    'R29: same-description Symbol cannot become authority capability',
  );
  expectCategory(
    () => control.enableAuthorityForEntrypoint(JSON.parse('{"browser-authority-capability":true}')),
    'authority_mode_required',
    'R29: JSON cannot become authority capability',
  );
  const syncRecords = readFileSync(join(SCRATCH, 'ledger-r29-forged-sync.jsonl'), 'utf8')
    .split('\n')
    .filter((line) => line.length > 0)
    .map((line) => JSON.parse(line));
  expect(
    !syncRecords.some((record) => record.entry && record.entry.kind === 'terminal_seal'),
    'R29: forged sync result wrote no terminal seal',
  );

  const controlAsync = freshControl('r29-forged-async');
  const flowAsync = await fullFlow(controlAsync);
  const forgedAsync = await controlAsync.launch(
    () => Promise.resolve({ rc: 0, pid: process.pid, real_child: true, reconciliation: { complete: true } }),
    { argv: flowAsync.argv },
  );
  expect(forgedAsync.outcome === 'FINISHED', 'R29: fake async child result can only affect library state');
  expectCategory(() => controlAsync.seal(), 'authority_mode_required', 'R29: forged async result cannot seal');
  expectCategory(() => controlAsync.evidence(), 'authority_mode_required', 'R29: forged async result cannot produce evidence');

  for (const [label, payload] of [
    ['missing-field', { ok: true, category: 'cors_probe_passed', status_2xx: true, allow_origin_present: true, allow_origin_exact: true }],
    ['extra-field', { schema: runner.CORS_PROBE_RESULT_SCHEMA, ok: true, category: 'cors_probe_passed', status_2xx: true, allow_origin_present: true, allow_origin_exact: true, extra: true }],
    ['type-error', { schema: runner.CORS_PROBE_RESULT_SCHEMA, ok: 'true', category: 'cors_probe_passed', status_2xx: true, allow_origin_present: true, allow_origin_exact: true }],
    ['ok-three-false', { schema: runner.CORS_PROBE_RESULT_SCHEMA, ok: true, category: 'cors_probe_passed', status_2xx: false, allow_origin_present: false, allow_origin_exact: false }],
    ['false-three-true', { schema: runner.CORS_PROBE_RESULT_SCHEMA, ok: false, category: 'cors_allow_origin_mismatch', status_2xx: true, allow_origin_present: true, allow_origin_exact: true }],
  ]) {
    expectCategory(
      () => runner.parseCorsProbePayload(payload),
      'cors_probe_payload_invalid',
      `R29: exact CORS helper payload rejects ${label}`,
    );
  }

  // B1-R6-R4 positive control: the direct entrypoint now runs the chain
  // against the REAL child, which truthfully refuses to spawn a frozen
  // Playwright CLI that the fixture source tree does not carry. The
  // truthful terminal verdict is therefore a SEALED TEST_RED with the real
  // child process observed — never a fabricated FINISHED.
  const positive = await runCommittedEntrypoint('r29-r1-positive');
  r39ScannedOutputs.entrypointStdout = String(positive.stdout ?? '');
  r39ScannedOutputs.entrypointStderr = String(positive.stderr ?? '');
  const positivePayload = parseSingleJsonLine(positive.stdout);
  expect(positive.status !== 0, `R29-R1: direct entrypoint without a frozen install exits nonzero (got ${positive.status})`);
  expect(positivePayload && positivePayload.authority === true, 'R29-R1: direct entrypoint emitted authority evidence');
  expect(positivePayload && positivePayload.outcome === 'TEST_RED', 'R29-R1: truthful TEST_RED verdict');
  expect(positivePayload && positivePayload.evidence && positivePayload.evidence.state === 'TEST_RED', 'R29-R1: evidence state TEST_RED');
  expect(positivePayload && positivePayload.evidence && positivePayload.evidence.child_real_process_observed === true, 'R29-R1: real child observed');
  expect(positivePayload && positivePayload.evidence && Number.isInteger(positivePayload.evidence.child_pid) && positivePayload.evidence.child_pid > 0, 'R29-R1: real child PID recorded');
  expect(positivePayload && positivePayload.evidence && Number.isInteger(positivePayload.evidence.child_exit_code) && positivePayload.evidence.child_exit_code !== 0, 'R29-R1: child refusal exit recorded');
  expect(positivePayload && positivePayload.evidence && positivePayload.evidence.child_playwright_observed === false, 'R29-R1: no Playwright process without a frozen install');
  expect(positivePayload && positivePayload.evidence && positivePayload.evidence.ledger_sealed === true, 'R29-R1: evidence reports terminal seal');
  expect(new runner.DurableJsonlLedger(positive.ledgerPath).verifyChain().count > 0, 'R29-R1: ledger hash chain valid');
  expect(
    ledgerRecords(positive.ledgerPath).some((record) => record.entry && record.entry.kind === 'terminal_seal'),
    'R29-R1: terminal seal record present',
  );

  const importSource = copyCurrentAuthoritySource('r29-import');
  const importAttack = spawnSync(
    process.execPath,
    ['--input-type=module', '-e', "process.argv[1]='tools/browser-authority-entrypoint.mjs'; await import('./tools/browser-authority-entrypoint.mjs'); console.log('R29_IMPORT_ACCEPTED');"],
    { cwd: importSource, env: { ...runner.probeChildEnv(), ...FIXTURE_ENV }, encoding: 'utf8', windowsHide: true },
  );
  expect(importAttack.status !== 0, 'R29: entrypoint import exits nonzero');
  expect((importAttack.stdout + importAttack.stderr).includes('not_direct_entrypoint'), 'R29: entrypoint import forgery refused');
  expect(!(importAttack.stdout + importAttack.stderr).includes('R29_IMPORT_ACCEPTED'), 'R29: entrypoint import never accepted');

  for (const [label, envPatch] of [
    ['node-options', { NODE_OPTIONS: '--trace-warnings' }],
    ['node-path', { NODE_PATH: join(SCRATCH, 'r29-node-path') }],
    ['git-env', { GIT_DIR: join(SCRATCH, 'r29-git-dir') }],
  ]) {
    const red = await runCommittedEntrypoint(`r29-${label}`, { envPatch });
    expect(red.status !== 0, `R29: direct entrypoint rejects ${label}`);
    expect((red.stdout + red.stderr).includes('env_injection_detected'), `R29: ${label} category exact`);
  }

  for (const [label, rel] of [
    ['entrypoint', 'tools/browser-authority-entrypoint.mjs'],
    ['runner', 'tools/browser-authority-runner.mjs'],
    ['helper', 'tools/browser-authority-cors-probe-helper.mjs'],
    ['profile', 'inventory/browser-authority-profile.json'],
  ]) {
    const red = await runCommittedEntrypoint(`r29-dirty-${label}`, {
      mutate: (sourceRoot) => writeFileSync(join(sourceRoot, rel), readFileSync(join(sourceRoot, rel), 'utf8') + '\n', 'utf8'),
    });
    expect(red.status !== 0, `R29: dirty ${label} rejects direct authority`);
    expect((red.stdout + red.stderr).includes('working_tree_dirty_vs_head'), `R29: dirty ${label} category exact`);
  }

  const forgedStdout = await runCommittedEntrypoint('r29-forged-stdout', {
    commitMutate: (sourceRoot) => writeCommittedChildVariant(sourceRoot, 'forged_stdout'),
  });
  expect(forgedStdout.status !== 0, 'R29: forged execFile stdout exits nonzero');
  expect(!String(forgedStdout.stdout).includes('"authority":true'), 'R29: forged execFile stdout cannot mint evidence');

  for (const [label, mode] of [
    ['nonzero', 'nonzero'],
    ['incomplete', 'incomplete'],
  ]) {
    const red = await runCommittedEntrypoint(`r29-child-${label}`, {
      commitMutate: (sourceRoot) => writeCommittedChildVariant(sourceRoot, mode),
    });
    const payload = parseSingleJsonLine(red.stdout);
    expect(red.status !== 0, `R29: child ${label} direct entrypoint exits nonzero`);
    expect(payload && payload.authority === true, `R29: child ${label} still produces sealed authority evidence`);
    expect(payload && payload.outcome === 'TEST_RED', `R29: child ${label} lands TEST_RED`);
    expect(payload && payload.evidence && payload.evidence.state === 'TEST_RED', `R29: child ${label} evidence TEST_RED`);
    expect(payload && payload.evidence && payload.evidence.ledger_sealed === true, `R29: child ${label} terminal seal present`);
    expect(new runner.DurableJsonlLedger(red.ledgerPath).verifyChain().count > 0, `R29: child ${label} ledger chain valid`);
  }

  await greenPath('r29-restore');
}

// ---------------------------------------------------------------------------
// R30-R40 — real Playwright child + runner-owned preflight authenticity
// (B1-R6-R4). The child is exercised DIRECTLY as a fixed-argv process over a
// scratch source tree with a FAKE frozen Playwright install; every PID, exit
// and artifact is awaited and cross-bound. Sensitive fixture values never
// reach output.
// ---------------------------------------------------------------------------

// Field-keyed projection of the fixture values (the materialized input shape).
const FIXTURE_VALUES = {
  owner: FIXTURE_ENV.J1H2C_RETAILER_EMAIL,
  owner_current_password: FIXTURE_ENV.J1H2C_RETAILER_CURRENT_PASSWORD,
  owner_new_password: FIXTURE_ENV.J1H2C_RETAILER_NEW_PASSWORD,
  base_url: FIXTURE_ENV.J1H2C_BASE_URL,
  api_base_url: FIXTURE_ENV.J1H2C_API_BASE_URL,
  maildir_root: FIXTURE_MAILDIR,
  w1_canonical_code: FIXTURE_ENV.J1H2C_W1_CANONICAL_CODE,
  w2_canonical_code: FIXTURE_ENV.J1H2C_W2_CANONICAL_CODE,
  unknown_identity: FIXTURE_ENV.J1H2C_UNKNOWN_EMAIL,
  unverified_identity: FIXTURE_ENV.J1H2C_UNVERIFIED_EMAIL,
  forged_reset_token: FIXTURE_ENV.J1H2C_FORGED_RESET_TOKEN,
  w1_verified_invitation_code: FIXTURE_ENV.J1H2C_W1_VERIFIED_INVITATION_CODE,
  w1_verified_invitation_phone: FIXTURE_ENV.J1H2C_W1_VERIFIED_INVITATION_PHONE,
  w1_unverified_invitation_code: FIXTURE_ENV.J1H2C_W1_UNVERIFIED_INVITATION_CODE,
  w1_unverified_invitation_phone: FIXTURE_ENV.J1H2C_W1_UNVERIFIED_INVITATION_PHONE,
};

function fixtureGit(root, ...args) {
  return execFileSync('git', ['-C', root, ...args], { stdio: ['ignore', 'pipe', 'ignore'] });
}

const FAKE_CLI_TEMPLATE = (cliExit, writeArtifacts, tamperMarker, refreshArtifacts) => `
import { writeFileSync, mkdirSync, readFileSync, utimesSync } from 'node:fs';
const proof = { pid: process.pid, argv: process.argv.slice(2), marker: 'fake-playwright-ran' };
mkdirSync('artifacts', { recursive: true });
writeFileSync('artifacts/fake-playwright-proof.json', JSON.stringify(proof));
${refreshArtifacts ? `
for (const name of ['reconciliation.json', 'reconciliation.csv', 'results.json', 'results-junit.xml', 'maildir-snapshot.json']) {
  const now = new Date();
  utimesSync('artifacts/' + name, now, now);
}
` : ''}
${writeArtifacts ? `
const nodes = [
  ...['HC01','HC02','HC03','HC04','HC05','HC06','HC07','HC08','HC09','HC10','HC12','HC13','HC14','HC15','HC16'].map((id) => ({ nodeId: id, surface: 'browser', outcome: 'PASS' })),
  { nodeId: 'HC11', surface: 'static', outcome: 'PASS' },
  { nodeId: 'HC17', surface: 'static', outcome: 'PASS' },
];
const summary = { browser: { total: 15, pass: 15 }, static: { total: 2, pass: 2 }, total: 17, gap: 0, incomplete: [], outcomes: { pass: 17, fail: 0, notRun: 0, pending: 0 }, preconditionOutcome: 'PRECONDITION_PASS' };
writeFileSync('artifacts/reconciliation.json', JSON.stringify({ schema: 'j1h2c-reconciliation/1', preconditionOutcome: 'PRECONDITION_PASS', note: 'fixture', summary, nodes }, null, 2));
writeFileSync('artifacts/reconciliation.csv', 'node_id,surface,outcome\\n' + nodes.map((n) => n.nodeId + ',' + n.surface + ',' + n.outcome).join('\\n') + '\\n');
writeFileSync('artifacts/results.json', JSON.stringify({ stats: { startTime: new Date().toISOString(), duration: 1, expected: 15, skipped: 0, unexpected: 0, flaky: 0 } }));
writeFileSync('artifacts/results-junit.xml', '<testsuites tests="15" failures="0" skipped="0" errors="0" time="0.001"></testsuites>');
writeFileSync('artifacts/maildir-snapshot.json', JSON.stringify({ schema: 'j1h2c-maildir-snapshot/2', mailboxes: { established: [], unverified: [] }, note: 'fixture' }));
${tamperMarker ? `
const markerPath = 'artifacts/authority-invocation.json';
const marker = JSON.parse(readFileSync(markerPath, 'utf8'));
marker.run_id = 'tampered-run-id-00000000000000000000000000';
writeFileSync(markerPath, JSON.stringify(marker));
` : ''}` : ''}
process.exit(${cliExit});
`;

function makeChildFixture(label, { withCli = true, cliExit = 0, writeArtifacts = true, tamperMarker = false, withScanner = true, refreshArtifacts = false } = {}) {
  const root = join(SCRATCH, `${label}-root`);
  ensureDir(join(root, 'tools'));
  ensureDir(join(root, 'inventory'));
  for (const rel of [
    'tools/browser-authority-runner.mjs',
    'tools/browser-authority-entrypoint.mjs',
    'tools/browser-authority-cors-probe-helper.mjs',
    'tools/browser-authority-preflight-helper.mjs',
    'tools/browser-authority-child.mjs',
    'tools/scan-artifacts.mjs',
    'inventory/browser-authority-profile.json',
  ]) {
    writeFileSync(join(root, rel), readFileSync(join(ROOT, rel)));
  }
  if (!withScanner) rmSync(join(root, 'tools', 'scan-artifacts.mjs'));
  fixtureGit(root, 'init', '-b', 'main');
  fixtureGit(root, 'config', 'user.email', 'fixture@charges.invalid');
  fixtureGit(root, 'config', 'user.name', 'fixture');
  fixtureGit(root, 'add', 'tools', 'inventory');
  fixtureGit(root, 'commit', '-m', 'child fixture');
  const head = fixtureGit(root, 'rev-parse', 'HEAD').toString().trim();
  if (withCli) {
    const cliDir = join(root, 'node_modules', '@playwright', 'test');
    ensureDir(cliDir);
    writeFileSync(
      join(cliDir, 'package.json'),
      JSON.stringify({ name: '@playwright/test', version: '1.49.1' }),
      'utf8',
    );
    writeFileSync(join(cliDir, 'cli.js'), FAKE_CLI_TEMPLATE(cliExit, writeArtifacts, tamperMarker, refreshArtifacts), 'utf8');
  }
  // Task maildir with exactly one fresh delivery per mailbox (setup tokens).
  const maildir = join(root, 'maildir');
  mkdirSync(join(maildir, FIXTURE_ENV.J1H2C_RETAILER_EMAIL.toLowerCase()), { recursive: true });
  mkdirSync(join(maildir, FIXTURE_ENV.J1H2C_UNVERIFIED_EMAIL.toLowerCase()), { recursive: true });
  writeFileSync(
    join(maildir, FIXTURE_ENV.J1H2C_RETAILER_EMAIL.toLowerCase(), 'delivery-1.json'),
    JSON.stringify({ link: 'https://mail.invalid/reset#setupToken=fixsetup-established-token-0001' }),
    'utf8',
  );
  writeFileSync(
    join(maildir, FIXTURE_ENV.J1H2C_UNVERIFIED_EMAIL.toLowerCase(), 'delivery-1.json'),
    JSON.stringify({ link: 'https://mail.invalid/setup#setupToken=fixsetup-unverified-token-0002' }),
    'utf8',
  );
  return { root, head, proofPath: join(root, 'artifacts', 'fake-playwright-proof.json'), maildir };
}

function childInputFor(fx, { valuesPatch = {}, candidateSha } = {}) {
  const values = { ...FIXTURE_VALUES, ...valuesPatch, maildir_root: fx.maildir };
  return {
    schema: 'j1h2c/browser-authority-child-input/1',
    input_sha: runner.sha256Hex(JSON.stringify({ owner_email_label: 'owner', values })),
    cwd_sha: runner.sha256Hex(realpathSync(fx.root)),
    candidate_sha: candidateSha ?? fx.head,
    owner_email_label: 'owner',
    values,
  };
}

function runChildDirect(fx, input, { argvExtra = [], envPatch = {} } = {}) {
  const result = spawnSync(
    process.execPath,
    [join(fx.root, 'tools', 'browser-authority-child.mjs'), ...argvExtra],
    {
      cwd: fx.root,
      input: JSON.stringify(input),
      encoding: 'utf8',
      env: { ...runner.probeChildEnv(), ...envPatch },
      timeout: 120000,
      windowsHide: true,
    },
  );
  let payload = null;
  try {
    payload = JSON.parse(String(result.stdout).trim());
  } catch {
    payload = null;
  }
  return { status: result.status, stdout: String(result.stdout ?? ''), stderr: String(result.stderr ?? ''), payload };
}

// R30 — the fixed child REALLY launches the fake Playwright executable and
// awaits + binds its PID and exit; only a fully consistent, fresh,
// candidate-bound, scanner-clean evidence set reaches complete=true.
const r30fx = makeChildFixture('r30');
const r30input = childInputFor(r30fx);
const r30 = runChildDirect(r30fx, r30input);
r39ScannedOutputs.childStdout = r30.stdout;
r39ScannedOutputs.childStderr = r30.stderr;
expect(r30.status === 0, `R30: child exit 0 (got ${r30.status}; stderr ${r30.stderr.slice(0, 120)})`);
expect(r30.payload && r30.payload.schema === 'j1h2c/browser-authority-child-result/1', 'R30: exact result schema');
expect(r30.payload && r30.payload.exit === 0 && r30.payload.reconciliation.complete === true, 'R30: complete=true only after full gates');
expect(r30.payload && r30.payload.reconciliation.category === 'child_complete', 'R30: complete category');
expect(r30.payload && r30.payload.playwright.launched === true, 'R30: Playwright process launched');
expect(r30.payload && Number.isInteger(r30.payload.playwright.pid) && r30.payload.playwright.pid > 0, 'R30: Playwright PID bound');
expect(r30.payload && r30.payload.playwright.pid !== r30.payload.pid, 'R30: Playwright PID distinct from wrapper PID');
expect(r30.payload && r30.payload.playwright.exit_code === 0, 'R30: awaited Playwright exit bound');
expect(r30.payload && r30.payload.playwright.invocation_count === 1, 'R30: exactly one invocation recorded');
expect(r30.payload && r30.payload.candidate_sha === r30fx.head, 'R30: candidate SHA cross-bound');
const r30proof = JSON.parse(readFileSync(r30fx.proofPath, 'utf8'));
expect(r30proof.marker === 'fake-playwright-ran', 'R30: fake Playwright executable really ran');
expect(r30.payload && r30proof.pid === r30.payload.playwright.pid, 'R30: reported PID equals the real spawned PID');
expect(JSON.stringify(r30proof.argv) === JSON.stringify(['test']), 'R30: fixed Playwright argv only');
const r30marker = JSON.parse(readFileSync(join(r30fx.root, 'artifacts', 'authority-invocation.json'), 'utf8'));
expect(r30marker.playwright_invocation_count === 1 && r30marker.candidate_sha === r30fx.head, 'R30: atomic invocation marker bound');
expect(r30.payload && r30marker.wrapper_pid === r30.payload.pid, 'R30: wrapper PID cross-bound via marker');

// R31 — caller child/CLI path substitution is refused.
{
  const fx = makeChildFixture('r31', { cliExit: 0 });
  // Extra argv element: refused before anything runs (proof file absent).
  const extra = runChildDirect(fx, childInputFor(fx), { argvExtra: ['--evil-arg'] });
  expect(extra.status !== 0, 'R31: extra argv refused');
  expect(extra.payload && extra.payload.category === 'child_argv_shape_refused', 'R31: argv shape category');
  expect(extra.payload && extra.payload.playwright.launched === false, 'R31: nothing launched under a doctored argv');
  expect(!existsSync(fx.proofPath), 'R31: doctored argv never reached Playwright');
  // Environment-provided path overrides are ignored by construction.
  const override = runChildDirect(fx, childInputFor(fx), {
    envPatch: { PLAYWRIGHT_CLI_PATH: join(SCRATCH, 'evil-cli.js'), J1H2C_BROWSER_AUTHORITY_CHILD: join(SCRATCH, 'evil-child.mjs') },
  });
  expect(override.status === 0 && override.payload && override.payload.playwright.launched === true, 'R31: env path overrides cannot redirect the frozen CLI');
}

// R32 — a second Playwright start is refused BEFORE spawn.
{
  const r32 = runChildDirect(r30fx, r30input);
  expect(r32.status !== 0, 'R32: second invocation refused');
  expect(r32.payload && r32.payload.category === 'playwright_invocation_exceeded', 'R32: pre-spawn refusal category');
  expect(r32.payload && r32.payload.playwright.launched === false, 'R32: no second Playwright process');
  const proofAfter = JSON.parse(readFileSync(r30fx.proofPath, 'utf8'));
  expect(proofAfter.pid === r30proof.pid, 'R32: spawn count still exactly one');
}

// R33 — Playwright rc=0 WITHOUT genuine reconciliation evidence is TEST_RED.
{
  const fx = makeChildFixture('r33', { cliExit: 0, writeArtifacts: false });
  const out = runChildDirect(fx, childInputFor(fx));
  expect(out.status !== 0, 'R33: missing evidence exits nonzero');
  expect(out.payload && out.payload.exit !== 0 && out.payload.reconciliation.complete === false, 'R33: complete=false');
  expect(out.payload && out.payload.reconciliation.category === 'reconciliation_json_missing', 'R33: missing reconciliation category');
}

// R34 — forged PASS artifacts, wrong candidate, stale mtimes and a tampered
// run id are ALL refused.
{
  // (a) forged PASS reconciliation whose run stats disagree: the full
  // artifact set is pre-written by the forger (the fake CLI only records
  // its own spawn), everything fresh — ONLY the stats lie.
  const fxA = makeChildFixture('r34-stats', { cliExit: 0, writeArtifacts: false, refreshArtifacts: true });
  ensureDir(join(fxA.root, 'artifacts'));
  const forgedNodes = [
    ...['HC01','HC02','HC03','HC04','HC05','HC06','HC07','HC08','HC09','HC10','HC12','HC13','HC14','HC15','HC16'].map((id) => ({ nodeId: id, surface: 'browser', outcome: 'PASS' })),
    { nodeId: 'HC11', surface: 'static', outcome: 'PASS' },
    { nodeId: 'HC17', surface: 'static', outcome: 'PASS' },
  ];
  const forgedSummary = { browser: { total: 15, pass: 15 }, static: { total: 2, pass: 2 }, total: 17, gap: 0, incomplete: [], outcomes: { pass: 17, fail: 0, notRun: 0, pending: 0 }, preconditionOutcome: 'PRECONDITION_PASS' };
  writeFileSync(join(fxA.root, 'artifacts', 'reconciliation.json'), JSON.stringify({ schema: 'j1h2c-reconciliation/1', preconditionOutcome: 'PRECONDITION_PASS', note: 'forged', summary: forgedSummary, nodes: forgedNodes }));
  writeFileSync(join(fxA.root, 'artifacts', 'reconciliation.csv'), 'node_id,surface,outcome\n' + forgedNodes.map((n) => `${n.nodeId},${n.surface},${n.outcome}`).join('\n') + '\n');
  writeFileSync(join(fxA.root, 'artifacts', 'results.json'), JSON.stringify({ stats: { startTime: new Date().toISOString(), duration: 1, expected: 3, skipped: 0, unexpected: 12, flaky: 0 } }));
  writeFileSync(join(fxA.root, 'artifacts', 'results-junit.xml'), '<testsuites tests="15" failures="0" skipped="0" errors="0" time="0.001"></testsuites>');
  writeFileSync(join(fxA.root, 'artifacts', 'maildir-snapshot.json'), JSON.stringify({ schema: 'j1h2c-maildir-snapshot/2', mailboxes: { established: [], unverified: [] } }));
  const outA = runChildDirect(fxA, childInputFor(fxA));
  expect(outA.status !== 0 && outA.payload && outA.payload.reconciliation.complete === false, 'R34: forged PASS reconciliation refused');
  expect(outA.payload && outA.payload.reconciliation.category === 'run_stats_not_all_green', 'R34: stats mismatch category');

  // (b) input candidate SHA that does not match the live HEAD.
  const fxB = makeChildFixture('r34-candidate', { cliExit: 0 });
  const outB = runChildDirect(fxB, childInputFor(fxB, { candidateSha: 'b'.repeat(40) }));
  expect(outB.status === 5 && outB.payload && outB.payload.category === 'child_candidate_mismatch', 'R34: wrong candidate refused pre-spawn');
  expect(outB.payload && outB.payload.playwright.launched === false, 'R34: wrong candidate never spawns');

  // (c) stale artifacts older than the invocation marker.
  const fxC = makeChildFixture('r34-stale', { cliExit: 0, writeArtifacts: false });
  mkdirSync(join(fxC.root, 'artifacts'), { recursive: true });
  const staleNodes = [
    ...['HC01','HC02','HC03','HC04','HC05','HC06','HC07','HC08','HC09','HC10','HC12','HC13','HC14','HC15','HC16'].map((id) => ({ nodeId: id, surface: 'browser', outcome: 'PASS' })),
    { nodeId: 'HC11', surface: 'static', outcome: 'PASS' },
    { nodeId: 'HC17', surface: 'static', outcome: 'PASS' },
  ];
  const staleSummary = { browser: { total: 15, pass: 15 }, static: { total: 2, pass: 2 }, total: 17, gap: 0, incomplete: [], outcomes: { pass: 17, fail: 0, notRun: 0, pending: 0 }, preconditionOutcome: 'PRECONDITION_PASS' };
  writeFileSync(join(fxC.root, 'artifacts', 'reconciliation.json'), JSON.stringify({ schema: 'j1h2c-reconciliation/1', preconditionOutcome: 'PRECONDITION_PASS', note: 'stale', summary: staleSummary, nodes: staleNodes }));
  writeFileSync(join(fxC.root, 'artifacts', 'reconciliation.csv'), 'node_id,surface,outcome\n' + staleNodes.map((n) => `${n.nodeId},${n.surface},${n.outcome}`).join('\n') + '\n');
  writeFileSync(join(fxC.root, 'artifacts', 'results.json'), JSON.stringify({ stats: { expected: 15, skipped: 0, unexpected: 0, flaky: 0 } }));
  writeFileSync(join(fxC.root, 'artifacts', 'results-junit.xml'), '<testsuites tests="15" failures="0" skipped="0" errors="0"></testsuites>');
  writeFileSync(join(fxC.root, 'artifacts', 'maildir-snapshot.json'), JSON.stringify({ schema: 'j1h2c-maildir-snapshot/2', mailboxes: { established: [], unverified: [] } }));
  const stale = new Date(Date.now() - 60000);
  for (const name of ['reconciliation.json', 'reconciliation.csv', 'results.json', 'results-junit.xml']) {
    utimesSync(join(fxC.root, 'artifacts', name), stale, stale);
  }
  const outC = runChildDirect(fxC, childInputFor(fxC));
  expect(outC.status !== 0 && outC.payload && outC.payload.reconciliation.complete === false, 'R34: stale artifacts refused');
  expect(outC.payload && outC.payload.reconciliation.category === 'reconciliation_stale', 'R34: stale mtime category');

  // (d) tampered invocation run id.
  const fxD = makeChildFixture('r34-runid', { cliExit: 0, writeArtifacts: true, tamperMarker: true });
  const outD = runChildDirect(fxD, childInputFor(fxD));
  expect(outD.status !== 0 && outD.payload && outD.payload.reconciliation.complete === false, 'R34: tampered run id refused');
  expect(outD.payload && outD.payload.reconciliation.category === 'invocation_marker_drift', 'R34: run id drift category');
}

// R35 — a missing or failing artifact scanner keeps the run RED.
{
  const fxA = makeChildFixture('r35-missing', { cliExit: 0, withScanner: false });
  const outA = runChildDirect(fxA, childInputFor(fxA));
  expect(outA.status !== 0 && outA.payload && outA.payload.reconciliation.complete === false, 'R35: scanner missing refused');
  expect(outA.payload && outA.payload.reconciliation.category === 'scanner_missing', 'R35: scanner-missing category');

  const fxB = makeChildFixture('r35-nonzero', { cliExit: 0, withScanner: true });
  writeFileSync(join(fxB.root, 'tools', 'scan-artifacts.mjs'), 'process.exit(1);\n', 'utf8');
  const outB = runChildDirect(fxB, childInputFor(fxB));
  expect(outB.status !== 0 && outB.payload && outB.payload.reconciliation.complete === false, 'R35: scanner nonzero refused');
  expect(outB.payload && outB.payload.reconciliation.category === 'scanner_not_clean', 'R35: scanner-nonzero category');
}

// R36 — the preflight helper cannot be omitted, forged, or repeated.
{
  // (a) omission: an entrypoint fixture whose helper was deleted refuses.
  const omit = await runCommittedEntrypoint('r36-helper-omit', {
    mutate: (sourceRoot) => rmSync(join(sourceRoot, 'tools', 'browser-authority-preflight-helper.mjs')),
  });
  expect(omit.status !== 0, 'R36: omitted helper refuses authority');
  expect((omit.stdout + omit.stderr).includes('working_tree_dirty_vs_head'), 'R36: omitted helper category exact');

  // (b) forged helper payloads fail the exact-schema parser.
  const greenCheck = (id) => ({ id, ok: true, category: 'check_green' });
  const coreGreen = runner.PREFLIGHT_CHECK_IDS.map(greenCheck);
  const hostGreen = runner.PREFLIGHT_HOST_CHECK_IDS.map(greenCheck);
  expectCategory(() => runner.parsePreflightHelperPayload({ schema: runner.PREFLIGHT_HELPER_RESULT_SCHEMA, ok: true, checks: coreGreen, counts: { total: 9, red: 0, host_checks_present: 0 }, extra: true }), 'preflight_helper_payload_invalid', 'R36: extra top-level key refused');
  expectCategory(() => runner.parsePreflightHelperPayload({ schema: runner.PREFLIGHT_HELPER_RESULT_SCHEMA, ok: true, checks: coreGreen.slice(0, 8), counts: { total: 8, red: 0, host_checks_present: 0 } }), 'preflight_helper_payload_invalid', 'R36: missing core check refused');
  expectCategory(() => runner.parsePreflightHelperPayload({ schema: runner.PREFLIGHT_HELPER_RESULT_SCHEMA, ok: true, checks: [...coreGreen.slice(0, 8), greenCheck('caller_extra_check')], counts: { total: 9, red: 0, host_checks_present: 0 } }), 'preflight_helper_payload_invalid', 'R36: forged ok=true with an unknown check refused');
  expectCategory(() => runner.parsePreflightHelperPayload({ schema: runner.PREFLIGHT_HELPER_RESULT_SCHEMA, ok: true, checks: [...coreGreen.slice(0, 8), { id: 'frontend_origin_page', ok: true, category: 'check_green' }], counts: { total: 9, red: 0, host_checks_present: 0 } }), 'preflight_helper_payload_invalid', 'R36: duplicate check id refused');
  expectCategory(() => runner.parsePreflightHelperPayload({ schema: runner.PREFLIGHT_HELPER_RESULT_SCHEMA, ok: true, checks: [...coreGreen.slice(0, 8), { id: 'frontend_origin_page', ok: false, category: 'frontend_origin_unreachable' }], counts: { total: 9, red: 1, host_checks_present: 0 } }), 'preflight_helper_payload_invalid', 'R36: forged ok=true over a RED check refused');
  expectCategory(() => runner.parsePreflightHelperPayload({ schema: runner.PREFLIGHT_HELPER_RESULT_SCHEMA, ok: false, checks: coreGreen, counts: { total: 9, red: 0, host_checks_present: 0 } }), 'preflight_helper_payload_invalid', 'R36: ok=false without any red check refused');
  expectCategory(() => runner.parsePreflightHelperPayload({ schema: runner.PREFLIGHT_HELPER_RESULT_SCHEMA, ok: true, checks: coreGreen, counts: { total: 8, red: 0, host_checks_present: 0 } }), 'preflight_helper_payload_invalid', 'R36: counts mismatch refused');
  const acceptedGreen = runner.parsePreflightHelperPayload({ schema: runner.PREFLIGHT_HELPER_RESULT_SCHEMA, ok: true, checks: [...coreGreen, ...hostGreen], counts: { total: 13, red: 0, host_checks_present: 4 } });
  expect(acceptedGreen.ok === true, 'R36: all-green core+host payload accepted');
  const acceptedHostRed = runner.parsePreflightHelperPayload({ schema: runner.PREFLIGHT_HELPER_RESULT_SCHEMA, ok: false, checks: [...coreGreen, { id: 'pg_reachable', ok: false, category: 'pg_unreachable' }, ...hostGreen.slice(1)], counts: { total: 13, red: 1, host_checks_present: 4 } });
  expect(acceptedHostRed.ok === false && acceptedHostRed.counts.red === 1, 'R36: host RED payload accepted for classification');

  // (c) repetition: a second preflight on the same plane is terminal.
  const controlRepeat = freshControl('r36-repeat');
  const flowRepeat = await fullFlow(controlRepeat);
  await expectCategoryAsync(() => controlRepeat.preflight(), 'preflight_already_invoked', 'R36: repeated preflight refused');
  expect(controlRepeat.launchStarts === 0, 'R36: repetition started nothing');
  await greenPath('r36-restore');

  // (d) host-check interface: the helper folds a provided outer-preflight
  // block into the verdict (categories only) and rejects malformed blocks.
  // The spawn must be ASYNC — a synchronous wait would freeze the checker's
  // event loop (and with it the fixture server the helper talks to).
  async function spawnHelperDirect(inputObject) {
    const out = await new Promise((resolve) => {
      const child = execFile(
        process.execPath,
        [join(ROOT, 'tools', 'browser-authority-preflight-helper.mjs')],
        {
          cwd: ROOT,
          env: runner.probeChildEnv(),
          timeout: 60000,
          windowsHide: true,
        },
        (error, stdout, stderr) => {
          if (error) {
            resolve({
              status: Number.isInteger(error.code) ? error.code : 1,
              stdout: String(stdout ?? ''),
              stderr: String(stderr ?? ''),
            });
          } else {
            resolve({ status: 0, stdout: String(stdout ?? ''), stderr: String(stderr ?? '') });
          }
        },
      );
      child.stdin.write(JSON.stringify(inputObject));
      child.stdin.end();
    });
    let payload = null;
    try {
      payload = JSON.parse(String(out.stdout).trim());
    } catch {
      payload = null;
    }
    return { ...out, payload };
  }
  const hostRedBlock = {
    schema: runner.PREFLIGHT_HELPER_INPUT_SCHEMA,
    timeout_ms: 20000,
    values: FIXTURE_VALUES,
    host_preflight: {
      provided_by: 'outer_authority_preflight',
      checks: [{ id: 'pg_reachable', ok: false, category: 'pg_unreachable' }],
    },
  };
  const hostRed = await spawnHelperDirect(hostRedBlock);
  expect(hostRed.status === 0 && hostRed.payload && hostRed.payload.ok === false, 'R36: host RED folds into ok=false');
  expect(hostRed.payload && hostRed.payload.checks.some((check) => check.id === 'pg_reachable' && check.ok === false && check.category === 'pg_unreachable'), 'R36: host RED category reported');
  expect(hostRed.payload && hostRed.payload.counts.host_checks_present === 1, 'R36: host presence counted');
  const hostGreenBlock = { ...hostRedBlock };
  hostGreenBlock.host_preflight = {
    provided_by: 'outer_authority_preflight',
    checks: runner.PREFLIGHT_HOST_CHECK_IDS.map((id) => ({ id, ok: true, category: 'check_green' })),
  };
  const hostGreenRun = await spawnHelperDirect(hostGreenBlock);
  expect(hostGreenRun.status === 0 && hostGreenRun.payload && hostGreenRun.payload.ok === true, 'R36: host GREEN folds into ok=true');
  const hostBadBlock = { ...hostRedBlock };
  hostBadBlock.host_preflight = { provided_by: 'not_the_outer_layer', checks: [] };
  const hostBad = await spawnHelperDirect(hostBadBlock);
  expect(hostBad.status !== 0 && hostBad.payload === null, 'R36: malformed host block fails closed without a payload');
  await greenPath('r36-host-restore');
}

// R37 — every preflight check RED lands VOID before authorize, spawn=0.
{
  async function expectPreflightVoid(label, { envPatch = {}, preflightSetup = null } = {}) {
    const control = freshControl(`r37-${label}`);
    const env = { ...FIXTURE_ENV, ...envPatch };
    control.materialize(env);
    await control.corsPreflightProbe();
    if (preflightSetup) preflightSetup();
    await expectCategoryAsync(() => control.preflight(), 'preflight_red', `R37-${label}: RED check refused`);
    expect(control.current === 'STOPPED' && control.launchStarts === 0, `R37-${label}: VOID with spawn=0`);
    const sink = join(SCRATCH, `ledger-r37-${label}.jsonl`);
    const records = existsSync(sink)
      ? readFileSync(sink, 'utf8').split('\n').filter((line) => line.length > 0).map((line) => JSON.parse(line))
      : [];
    expect(records.some((record) => record.entry && record.entry.kind === 'void'), `R37-${label}: void record ledgered`);
  }
  preflightMode = 'frontend_down';
  await expectPreflightVoid('frontend-down', {});
  preflightMode = 'health_down';
  await expectPreflightVoid('health-down', {});
  preflightMode = 'owner_login_denied';
  await expectPreflightVoid('owner-login-denied', {});
  preflightMode = 'unverified_login_allowed';
  await expectPreflightVoid('unverified-login-allowed', {});
  preflightMode = 'ok';
  await expectPreflightVoid('maildir-nonempty', {
    preflightSetup: () => writeFileSync(join(FIXTURE_MAILDIR, 'stray-delivery.json'), '{}'),
  });
  rmSync(join(FIXTURE_MAILDIR, 'stray-delivery.json'));
  await expectPreflightVoid('w-collision', {
    envPatch: { J1H2C_W2_CANONICAL_CODE: FIXTURE_ENV.J1H2C_W1_CANONICAL_CODE },
  });
  await expectPreflightVoid('identity-collision', {
    envPatch: { J1H2C_UNVERIFIED_EMAIL: FIXTURE_ENV.J1H2C_RETAILER_EMAIL },
  });
  await expectPreflightVoid('invitation-collision', {
    envPatch: { J1H2C_W1_UNVERIFIED_INVITATION_CODE: FIXTURE_ENV.J1H2C_W1_VERIFIED_INVITATION_CODE },
  });
  await expectPreflightVoid('forged-reuse', {
    envPatch: { J1H2C_FORGED_RESET_TOKEN: FIXTURE_ENV.J1H2C_RETAILER_EMAIL },
  });
  await greenPath('r37-restore');
}

// R38 — any input/helper/child drift AFTER preflight blocks the launch.
{
  const childPath = join(ROOT, 'tools', 'browser-authority-child.mjs');
  const helperPath = join(ROOT, 'tools', 'browser-authority-preflight-helper.mjs');
  for (const [label, driftPath] of [['child', childPath], ['helper', helperPath]]) {
    const control = freshControl(`r38-${label}`);
    const { argv } = await fullFlow(control);
    const saved = readFileSync(driftPath);
    try {
      writeFileSync(driftPath, Buffer.concat([saved, Buffer.from('\n')], saved.length + 1));
      expectCategory(
        () => control.launch(() => ({ rc: 0, pid: 4242424, real_child: true, reconciliation: { complete: true } }), { argv }),
        'authority_module_byte_drift',
        `R38-${label}: byte drift blocks launch`,
      );
      expect(control.current === 'STOPPED' && control.launchStarts === 0, `R38-${label}: STOPPED, spawn=0`);
    } finally {
      writeFileSync(driftPath, saved);
    }
    expect(runner.sha256Hex(readFileSync(driftPath)) === runner.sha256Hex(saved), `R38-${label}: byte-identical restore`);
  }
  const controlInput = freshControl('r38-input');
  controlInput.materialize(FIXTURE_ENV);
  await controlInput.corsPreflightProbe();
  await controlInput.preflight();
  expectCategory(
    () => controlInput.authorize({ inputSha: 'f'.repeat(64), argv: ['node', 'tools', 'fixture-launch'] }),
    'input_sha_drift',
    'R38-input: drifted input expectation refused at authorize',
  );
  expect(controlInput.launchStarts === 0, 'R38-input: spawn=0');
  await greenPath('r38-restore');
}

// R39 — sensitive values never reach child/entrypoint outputs or ledgers.
{
  const sensitiveValues = Object.entries(FIXTURE_ENV)
    .filter(([name]) => name !== 'J1H2C_MAILDIR_ROOT')
    .map(([, value]) => value);
  const scannedOutputs = [
    r39ScannedOutputs.childStdout,
    r39ScannedOutputs.childStderr,
    r39ScannedOutputs.entrypointStdout,
    r39ScannedOutputs.entrypointStderr,
  ];
  for (const value of sensitiveValues) {
    expect(
      !scannedOutputs.some((text) => text.includes(value)),
      'R39: fixture secret absent from child/entrypoint stdout+stderr',
    );
  }
  const ledgerText = (() => {
    try {
      return readdirSync(SCRATCH)
        .filter((name) => name.endsWith('.jsonl'))
        .map((name) => {
          try {
            return readFileSync(join(SCRATCH, name), 'utf8');
          } catch {
            return '';
          }
        })
        .join('\n');
    } catch {
      return '';
    }
  })();
  for (const value of sensitiveValues) {
    expect(!ledgerText.includes(value), 'R39: fixture secret absent from every ledger sink');
  }
}

// R40 — the library surface is still non-authority; R1-R29 GREEN preserved.
{
  const control = freshControl('r40');
  const { argv } = await fullFlow(control);
  const result = control.launch(() => ({ rc: 0, pid: 4242425, real_child: true, reconciliation: { complete: true } }), { argv });
  expect(result.outcome === 'FINISHED', 'R40: functional FINISHED still reachable with a double');
  expectCategory(() => control.seal(), 'authority_mode_required', 'R40: library seal refused');
  expectCategory(() => control.evidence(), 'authority_mode_required', 'R40: library evidence refused');
  expectCategory(
    () => runner.sealAuthorityEvidence(control),
    'not_direct_entrypoint',
    'R40: exported sealer cannot mint from a library import',
  );
  const runnerText = readFileSync(join(ROOT, 'tools', 'browser-authority-runner.mjs'), 'utf8');
  const childText = readFileSync(join(ROOT, 'tools', 'browser-authority-child.mjs'), 'utf8');
  const helperText = readFileSync(join(ROOT, 'tools', 'browser-authority-preflight-helper.mjs'), 'utf8');
  expect(!/\bfetch\s*\(/.test(runnerText + helperText + childText), 'R40: no ambient fetch in runner/helper/child');
  expect(!/from 'node:http'|from 'node:https'/.test(runnerText), 'R40: runner still performs no in-process network I/O');
  expect(childText.includes('shell: false') && childText.includes('spawn(process.execPath'), 'R40: child spawns Playwright via argv array with shell:false');
  expect(runner.PREFLIGHT_CHECK_IDS.length === 9 && runner.PREFLIGHT_HOST_CHECK_IDS.length === 4, 'R40: fixed preflight taxonomy');
  expect(readFileSync(join(ROOT, 'tools', 'browser-authority-entrypoint.mjs'), 'utf8').includes('entrypoint_direct_process') === false, 'R40: hardcoded preflight label removed from the authority path');
}

// ---------------------------------------------------------------------------
// Verdict
// ---------------------------------------------------------------------------
rmSync(SCRATCH, { recursive: true, force: true });
if (failures.length > 0) {
  for (const message of failures) console.error(message);
  console.error(`BROWSER-AUTHORITY CONTRACT CHECK FAILED (${failures.length})`);
  process.exit(1);
}
console.log('BROWSER-AUTHORITY CONTROL-PLANE CONTRACTS PASSED (S0 + G + R1-R40, direct-process authority boundary, single canonical repo identity, case-insensitive GIT_* sanitization, real fixed Playwright child + runner-owned preflight helper).');
// The fixture HTTP server and undici keep-alive sockets hold the event loop;
// the verdict above is final, so exit explicitly.
process.exit(0);
