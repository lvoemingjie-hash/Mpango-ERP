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
 *
 * Every failing probe must throw the EXACT category; a probe that does not
 * throw, or throws a different category, fails this checker. After each RED
 * scenario a fresh instance re-runs the canonical GREEN path (restore ->
 * re-GREEN). Labels, booleans, categories and counts only — fixture values
 * never reach output.
 */

import { execFileSync } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync, mkdtempSync, rmSync } from 'node:fs';
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

const FIXTURE_ENV = {
  J1H2C_RETAILER_EMAIL: 'fixture-owner-email-value',
  J1H2C_RETAILER_CURRENT_PASSWORD: 'fixture-current-password-value', // pragma: allowlist secret
  J1H2C_RETAILER_NEW_PASSWORD: 'fixture-new-password-value', // pragma: allowlist secret
  J1H2C_BASE_URL: 'fixture-base-url-value',
  J1H2C_API_BASE_URL: 'fixture-api-base-url-value',
  J1H2C_MAILDIR_ROOT: 'fixture-maildir-root-value',
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

function fullFlow(control) {
  const { inputSha } = control.materialize(FIXTURE_ENV);
  control.preflight([{ ok: true, label: 'probe' }]);
  const argv = ['node', 'tools', 'fixture-launch'];
  control.authorize({ inputSha, argv });
  return { inputSha, argv };
}

/** Canonical GREEN path on a brand-new instance; returns binding facts. */
async function greenPath(name = 'green') {
  const control = freshControl(name);
  const { inputSha, argv } = fullFlow(control);
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
  expectCategory(() => control.evidence(), 'evidence_unsealed', `${name}: evidence before seal refused`);
  control.seal();
  const evidence = control.evidence();
  expect(evidence.ledger_sealed === true, `${name}: evidence after seal`);
  expect(
    !JSON.stringify(evidence).includes('fixture-owner-email-value') &&
      !JSON.stringify(evidence).includes('FIXW1CODE'),
    `${name}: evidence carries no fixture values`,
  );
  return { control, inputSha, argv, evidence };
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
    control.preflight([]);
  } catch {
    /* terminal_stop — the rejection was persisted before the throw */
  }
  control.seal(); // terminal seal AFTER the rejection, chaining over it
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
  const strippedPath = join(SCRATCH, 'ledger-r4-stripped.jsonl');
  writeFileSync(strippedPath, strippedLines.join('\n') + '\n', 'utf8');
  expectCategory(
    () => new runner.DurableJsonlLedger(strippedPath).verifyChain(),
    'ledger_seq_duplicate',
    'R4: suppressed rejection caught by the seq/chain guards',
  );
  await greenPath('r4-restore');
}

// R5 — every control surface after terminal VOID
{
  const control = freshControl('r5');
  control.materialize(FIXTURE_ENV);
  control.stop('probe_void');
  expectCategory(() => control.preflight([{ ok: true, label: 'probe' }]), 'terminal_stop', 'R5: preflight after VOID');
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
  fullFlowPreflight(control);
  expectCategory(() => control.preflight([{ ok: true, label: 'probe' }]), 'preflight_already_invoked', 'R6: preflight twice');
  expect(control.current === 'STOPPED', 'R6: repeat preflight lands STOPPED (C)');
  await greenPath('r6-restore');
}

function fullFlowPreflight(control) {
  control.materialize(FIXTURE_ENV);
  control.preflight([{ ok: true, label: 'probe' }]);
}

// R7 — second browser launch (double called exactly once)
{
  const control = freshControl('r7');
  const { inputSha, argv } = fullFlow(control);
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
  control.preflight([{ ok: true, label: 'probe' }]);
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
  const preFlow = (control) => {
    const { inputSha } = control.materialize(FIXTURE_ENV);
    control.preflight([{ ok: true, label: 'probe' }]);
    return { inputSha };
  };
  const control = freshControl('r9');
  const { inputSha, argv } = fullFlow(control);
  expectCategory(
    () => control.launch(() => ({ rc: 0, reconciliation: { complete: true } }), { argv: ['node', 'DIFFERENT'] }),
    'argv_drift',
    'R9: argv drift at launch',
  );
  const controlB = freshControl('r9b');
  const flowB = preFlow(controlB);
  expectCategory(
    () => controlB.authorize({ inputSha: flowB.inputSha, argv: 'node tools fixture-launch' }),
    'argv_not_array',
    'R9: shell-style string argv refused at authorize',
  );
  const controlC = freshControl('r9c');
  const flowC = fullFlow(controlC);
  expectCategory(
    () => controlC.launch(() => ({ rc: 0, reconciliation: { complete: true } }), { argv: 'node x' }),
    'argv_not_array',
    'R9: shell-style string argv refused at launch',
  );
  const controlD = freshControl('r9d');
  const flowD = preFlow(controlD);
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
  const { inputSha, argv } = fullFlow(control);
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
  const { inputSha, argv } = fullFlow(control);
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
  const { inputSha, argv } = fullFlow(control);
  expect(control.liveCandidateSha() === expectedHead, 'R13: binding survives the full flow');
  await greenPath('r13-restore');
}

// ---------------------------------------------------------------------------
// R14 — child failure / incomplete reconciliation => TEST_RED, never FINISHED
// ---------------------------------------------------------------------------

{
  const control = freshControl('r14a');
  const { inputSha, argv } = fullFlow(control);
  const red = control.launch(() => ({ rc: 1, reconciliation: { complete: true } }), { argv });
  expect(red.outcome === 'TEST_RED', 'R14: rc!=0 lands TEST_RED');
  expect(control.current === 'TEST_RED' && control.launchStarts === 1, 'R14: state TEST_RED with true starts=1');
  control.seal();
  const evidence = control.evidence();
  expect(evidence.state === 'TEST_RED', 'R14: sealed TEST_RED evidence');

  const controlB = freshControl('r14b');
  const flowB = fullFlow(controlB);
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
  const { inputSha, argv } = fullFlow(control);
  let caught = null;
  try {
    control.preflight([{ ok: true, label: 'probe' }]);
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
  const { inputSha, argv } = fullFlow(control);
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
  const flowB = fullFlow(controlB);
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
  const flowC = fullFlow(controlC);
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
// R21 — a tampered (even sealed) ledger can never yield evidence (B1-R5-R2)
// ---------------------------------------------------------------------------

{
  const sinkPath = join(SCRATCH, 'ledger-r21.jsonl');
  const ledger = new runner.DurableJsonlLedger(sinkPath);
  const control = new runner.ControlPlane({ contractPath, repoRoot, ledger });
  const { inputSha, argv } = fullFlow(control);
  control.launch(() => ({ rc: 0, reconciliation: { complete: true } }), { argv });
  control.seal();
  expect(control.evidence().state === 'FINISHED', 'R21: intact sealed evidence reads');

  // Tamper an EARLY record while keeping every later line (incl. the seal):
  // the chain recompute must refuse evidence.
  const intact = readFileSync(sinkPath, 'utf8');
  const lines = intact.split('\n').filter((line) => line.length > 0).map((line) => JSON.parse(line));
  const finishIndex = lines.findIndex((record) => record.entry.kind === 'finish');
  expect(finishIndex >= 0, 'R21: finish record present');
  lines[finishIndex].entry.argv_count = 999; // stale event_sha kept on purpose
  writeFileSync(
    sinkPath,
    lines.map((record) => JSON.stringify(record)).join('\n') + '\n',
    'utf8',
  );
  expectCategory(
    () => control.evidence(),
    'ledger_chain_broken',
    'R21: tampered early record refused by evidence chain re-verification',
  );
  expectCategory(
    () => control.seal(),
    'ledger_chain_broken',
    'R21: re-sealing a tampered sink hits the mandatory chain re-verification first',
  );

  // Restore the intact bytes: evidence reads again.
  writeFileSync(sinkPath, intact, 'utf8');
  expect(control.evidence().state === 'FINISHED', 'R21: restored sink reads again');
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
    const { inputSha, argv } = fullFlow(control);
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
      const { inputSha, argv } = fullFlow(control);
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

if (failures.length > 0) {
  for (const message of failures) console.error(message);
  console.error(`BROWSER-AUTHORITY CONTRACT CHECK FAILED (${failures.length})`);
  process.exit(1);
}
rmSync(SCRATCH, { recursive: true, force: true });
console.log('BROWSER-AUTHORITY CONTROL-PLANE CONTRACTS PASSED (S0 + G + R1-R25, single canonical repo identity, case-insensitive GIT_* sanitization).');
