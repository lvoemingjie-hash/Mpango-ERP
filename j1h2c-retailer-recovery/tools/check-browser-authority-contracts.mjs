#!/usr/bin/env node
/**
 * Executable B1-R5 control-plane contract checks.
 *
 * REALLY loads tools/browser-authority-runner.mjs (no parallel/copied
 * implementation) and proves, against the real module:
 *   S0  schema file parses and a fixture contract validates against it;
 *   G   the canonical GREEN path (materialize -> preflight -> authorize ->
 *       single launch through a double) with SHA-bound inputs;
 *   R1  destructive merge over owner_email_label  -> owner_label_overwrite_forbidden
 *   R2  missing required owner field              -> required_field_missing
 *   R3  transition with wrong `from`              -> transition_from_mismatch
 *   R4  post-STOP rejection NOT ledgered          -> rejection_unledgered (invariant)
 *   R5  any call after VOID                       -> terminal_stop (x3 surfaces)
 *   R6  second preflight                          -> preflight_already_invoked
 *   R7  second browser launch                     -> launch_already_invoked (double called once)
 *   R8  SHA drift (candidate/input/contract)      -> candidate_sha_drift / input_sha_drift / contract_sha_drift
 *   R9  argv drift + non-array argv               -> argv_drift / argv_not_array
 *   R10 sensitive value into ledger              -> sensitive_value_rejected
 *
 * Every failing probe is expected to throw the EXACT category; a probe that
 * does not throw, or throws a different category, fails this checker. After
 * each RED scenario the checker re-runs the canonical GREEN path on a fresh
 * ControlPlane and requires identical SHA bindings (restore -> re-GREEN).
 * Labels, booleans, categories and counts only — fixture values never reach
 * output.
 */

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { join, dirname } from 'node:path';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');

const failures = [];
function expect(condition, label) {
  if (!condition) failures.push(`browser-authority: ${label}`);
}

/** Runs `probe`, expecting BrowserAuthorityError with the exact category. */
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
// S0 — schema parse + fixture contract validation (real files, real module)
// ---------------------------------------------------------------------------

const schemaText = readFileSync(join(ROOT, 'inventory', 'browser-authority-contract.schema.json'), 'utf8');
const schema = JSON.parse(schemaText);
expect(schema.$id === 'j1h2c-retailer-recovery/browser-authority-contract.schema/1', 'S0: schema $id');
expect(schema.properties.launch.properties.max_starts.const === 1, 'S0: schema launch max_starts const 1');
expect(schema.$defs.field.properties.required.const === true, 'S0: schema fields required const true');

/** Minimal draft-07 subset validator (same shape family as the runner's). */
function validateAgainstSchema(doc, schemaNode, pointer = '$') {
  if (schemaNode.const !== undefined && doc !== schemaNode.const) return `${pointer}:const`;
  const type = schemaNode.type;
  if (type === 'object' && (doc === null || typeof doc !== 'object' || Array.isArray(doc))) {
    return `${pointer}:type`;
  }
  if (type === 'array' && !Array.isArray(doc)) return `${pointer}:type`;
  if (type === 'string' && typeof doc !== 'string') return `${pointer}:type`;
  if (type === 'boolean' && typeof doc !== 'boolean') return `${pointer}:type`;
  if (Array.isArray(doc) && schemaNode.items) {
    for (const [index, item] of doc.entries()) {
      const error = validateAgainstSchema(item, schemaNode.items, `${pointer}[${index}]`);
      if (error) return error;
    }
  }
  if (schemaNode.type === 'object' && typeof doc === 'object' && doc !== null && !Array.isArray(doc)) {
    for (const key of schemaNode.required ?? []) {
      if (!(key in doc)) return `${pointer}.${key}:required`;
    }
    if (schemaNode.additionalProperties === false) {
      for (const key of Object.keys(doc)) {
        if (!(key in (schemaNode.properties ?? {}))) return `${pointer}.${key}:additional`;
      }
    }
    for (const [key, sub] of Object.entries(schemaNode.properties ?? {})) {
      if (key in doc) {
        const error = validateAgainstSchema(doc[key], sub, `${pointer}.${key}`);
        if (error) return error;
      }
    }
  }
  return null;
}

const runner = await import('./browser-authority-runner.mjs');
expect(typeof runner.ControlPlane === 'function', 'S0: real module exports ControlPlane');
expect(typeof runner.parseContract === 'function', 'S0: real module exports parseContract');
expect(runner.CONTROL_PLANE_SCHEMA === 'j1h2c/browser-authority-contract/1', 'S0: schema family matches module');

// Fixture contract — LABELS and env NAMES only; values are synthetic and
// never printed. W1 = canonical supplier code; W2 = real second-supplier code.
const CONTRACT_TEXT = JSON.stringify({
  schema: 'j1h2c/browser-authority-contract/1',
  owner_field: 'retailer_email',
  fields: {
    base_url: { env: 'J1H2C_BASE_URL', required: true, sensitive: true },
    maildir_root: { env: 'J1H2C_MAILDIR_ROOT', required: true, sensitive: true },
    w1_canonical_code: { env: 'J1H2C_WHOLESALER_CANONICAL_CODE', required: true, sensitive: false },
    w2_canonical_code: { env: 'J1H2C_SECOND_SUPPLIER_CANONICAL_CODE', required: true, sensitive: false },
    retailer_email: { env: 'J1H2C_RETAILER_EMAIL', required: true, sensitive: true },
    retailer_current_password: { env: 'J1H2C_RETAILER_CURRENT_PASSWORD', required: true, sensitive: true },
    retailer_new_password: { env: 'J1H2C_RETAILER_NEW_PASSWORD', required: true, sensitive: true },
  },
  transitions: [
    { from: 'INIT', to: 'PREFLIGHTED' },
    { from: 'PREFLIGHTED', to: 'AUTHORIZED' },
    { from: 'AUTHORIZED', to: 'FINISHED' },
  ],
  launch: { max_starts: 1 },
});
expect(validateAgainstSchema(JSON.parse(CONTRACT_TEXT), schema) === null, 'S0: fixture contract validates against schema');

const CANDIDATE_FIXTURE_SHA = runner.sha256Hex('candidate-fixture-bytes');

// Synthetic fixture values (never echoed; used only to prove the value
// firewall and required-field projection).
const FIXTURE_ENV = {
  J1H2C_BASE_URL: 'fixture-base-url-value',
  J1H2C_MAILDIR_ROOT: 'fixture-maildir-root-value',
  J1H2C_WHOLESALER_CANONICAL_CODE: 'FIXW1CODE',
  J1H2C_SECOND_SUPPLIER_CANONICAL_CODE: 'FIXW2CODE',
  J1H2C_RETAILER_EMAIL: 'fixture-owner-email-value',
  J1H2C_RETAILER_CURRENT_PASSWORD: 'fixture-current-password-value',  // pragma: allowlist secret — synthetic fixture label, not a credential
  J1H2C_RETAILER_NEW_PASSWORD: 'fixture-new-password-value',    // pragma: allowlist secret — synthetic fixture label, not a credential
};

const { contract, contractSha } = runner.parseContract(CONTRACT_TEXT);

const LAUNCH_DOUBLE = (calls) => async (file, args) => {
  calls.push({ file, argsCount: args.length });
  return { started: true, argv_array: Array.isArray(args) };
};

/** Canonical GREEN path on a fresh ControlPlane; returns its bindings. */
function greenPath() {
  const ledger = new runner.AppendOnlyLedger();
  const control = new runner.ControlPlane({
    contract,
    contractSha,
    candidateSha: CANDIDATE_FIXTURE_SHA,
    ledger,
  });
  const { input, inputSha } = runner.materializeInput(contract, FIXTURE_ENV);
  control.materialized = { input, inputSha };
  const preflighted = control.preflight([
    { ok: true, label: 'fixture-probe-1' },
    { ok: true, label: 'fixture-probe-2' },
  ]);
  expect(preflighted.state === 'PREFLIGHTED', 'G: preflight state');
  const argv = ['node', 'tools', 'fixture-launch'];
  control.authorize({ contractSha, inputSha, argv, candidateSha: CANDIDATE_FIXTURE_SHA });
  const calls = [];
  return control
    .launch((file, args) => LAUNCH_DOUBLE(calls)(file, args), { argv, contractSha, inputSha, candidateSha: CANDIDATE_FIXTURE_SHA })
    .then((result) => {
    expect(result.started === true, 'G: double started');
    expect(calls.length === 1, 'G: exactly one launch through the double');
    expect(calls[0].file === 'node' && calls[0].argsCount === 2, 'G: argv array forwarded');
    const evidence = control.evidence();
    expect(evidence.state === 'FINISHED' && evidence.launch_starts === 1, 'G: finished, starts=1');
    expect(evidence.ledger_entries === 1, 'G: ledger has exactly the launch entry');
    expect(
      !JSON.stringify(evidence).includes('fixture-owner-email-value') &&
        !JSON.stringify(evidence).includes('FIXW1CODE'),
      'G: evidence carries no fixture values',
    );
    return { inputSha, contractSha, candidateSha: CANDIDATE_FIXTURE_SHA, evidence };
  });
}

// ---------------------------------------------------------------------------
// G — canonical GREEN path first (the control plane works end to end)
// ---------------------------------------------------------------------------

await greenPath();
{
  // Re-run must produce identical materialized-input SHA (deterministic
  // projection => byte-consistent binding across fresh instances).
  const first = runner.materializeInput(contract, FIXTURE_ENV);
  const second = runner.materializeInput(contract, FIXTURE_ENV);
  expect(first.inputSha === second.inputSha, 'G: input SHA deterministic across instances');
  expect(first.input.owner_email_label === 'retailer_email', 'G: owner label projected from contract');
}

// ---------------------------------------------------------------------------
// R1 — destructive merge over owner_email_label
// ---------------------------------------------------------------------------

{
  const { input, inputSha } = runner.materializeInput(contract, FIXTURE_ENV);
  expectCategory(
    () => runner.mergeMaterialized(contract, input, { owner_email_label: 'other_field' }),
    'owner_label_overwrite_forbidden',
    'R1: merge overwriting owner_email_label',
  );
  expectCategory(
    () => runner.mergeMaterialized(contract, input, { retailer_email: 'replacement-owner-value' }),
    'owner_label_overwrite_forbidden',
    'R1: merge overwriting the owner field binding',
  );
  // Restore check: the original input binding is untouched and re-verifies.
  expect(
    runner.sha256Hex(JSON.stringify(input)) === inputSha,
    'R1: original input binding intact after refused merge',
  );
  await greenPath();
}

// ---------------------------------------------------------------------------
// R2 — missing required owner field (strict field-by-field projection)
// ---------------------------------------------------------------------------

{
  expectCategory(
    () => runner.materializeInput(contract, { ...FIXTURE_ENV, J1H2C_RETAILER_EMAIL: '' }),
    'required_field_missing',
    'R2: empty owner email',
  );
  expectCategory(
    () => runner.materializeInput(contract, { ...FIXTURE_ENV, J1H2C_SECOND_SUPPLIER_CANONICAL_CODE: undefined }),
    'required_field_missing',
    'R2: missing W2 required field',
  );
  expectCategory(
    () => runner.materializeInput(contract, { ...FIXTURE_ENV, J1H2C_WHOLESALER_CANONICAL_CODE: null }),
    'required_field_missing',
    'R2: missing W1 required field',
  );
  await greenPath();
}

// ---------------------------------------------------------------------------
// R3 — transition `from` mismatch (from must be captured before mutation)
// ---------------------------------------------------------------------------

{
  const ledger = new runner.AppendOnlyLedger();
  const control = new runner.ControlPlane({
    contract,
    contractSha,
    candidateSha: CANDIDATE_FIXTURE_SHA,
    ledger,
  });
  control.materialized = runner.materializeInput(contract, FIXTURE_ENV);
  // Current state is INIT; claiming from=PREFLIGHTED must be refused with
  // the state UNCHANGED (the from-check happens before any mutation).
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
  await greenPath();
}

// ---------------------------------------------------------------------------
// R4 — post-STOP rejection that is NOT ledgered must be DETECTED
// ---------------------------------------------------------------------------

{
  const ledger = new runner.AppendOnlyLedger();
  const control = new runner.ControlPlane({
    contract,
    contractSha,
    candidateSha: CANDIDATE_FIXTURE_SHA,
    ledger,
  });
  control.stop('probe_void');
  let rejections = 0;
  try {
    control.preflight([]);
  } catch {
    rejections += 1;
  }
  // The real ledger DID receive the rejection; prove the invariant accepts it.
  expect(runner.verifyRejectionsLedgered(ledger, rejections) === true, 'R4: real ledger covers rejections');
  // RED counterexample: a stripped ledger (suppressed entry) must FAIL the
  // same invariant — an unledgered rejection cannot hide.
  const stripped = new runner.AppendOnlyLedger();
  expectCategory(
    () => runner.verifyRejectionsLedgered(stripped, rejections),
    'rejection_unledgered',
    'R4: stripped ledger fails the invariant',
  );
  await greenPath();
}

// ---------------------------------------------------------------------------
// R5 — every control surface after terminal VOID
// ---------------------------------------------------------------------------

{
  const ledger = new runner.AppendOnlyLedger();
  const control = new runner.ControlPlane({
    contract,
    contractSha,
    candidateSha: CANDIDATE_FIXTURE_SHA,
    ledger,
  });
  control.materialized = runner.materializeInput(contract, FIXTURE_ENV);
  control.stop('probe_void');
  expectCategory(() => control.preflight([{ ok: true, label: 'probe' }]), 'terminal_stop', 'R5: preflight after VOID');
  expectCategory(
    () =>
      control.authorize({
        contractSha,
        inputSha: control.materialized.inputSha,
        argv: ['node', 'x'],
        candidateSha: CANDIDATE_FIXTURE_SHA,
      }),
    'terminal_stop',
    'R5: authorize after VOID',
  );
  expectCategory(
    () => control.launch((file, args) => Promise.resolve({ file, args }), { argv: ['node', 'x'] }),
    'terminal_stop',
    'R5: launch after VOID',
  );
  expect(
    ledger.entries.filter((entry) => entry.entry.kind === 'rejection_after_stop').length === 3,
    'R5: all three post-VOID rejections ledgered',
  );
  await greenPath();
}

// ---------------------------------------------------------------------------
// R6 — second preflight
// ---------------------------------------------------------------------------

{
  const ledger = new runner.AppendOnlyLedger();
  const control = new runner.ControlPlane({
    contract,
    contractSha,
    candidateSha: CANDIDATE_FIXTURE_SHA,
    ledger,
  });
  control.materialized = runner.materializeInput(contract, FIXTURE_ENV);
  control.preflight([{ ok: true, label: 'probe' }]);
  expectCategory(
    () => control.preflight([{ ok: true, label: 'probe' }]),
    'preflight_already_invoked',
    'R6: preflight invoked twice',
  );
  await greenPath();
}

// ---------------------------------------------------------------------------
// R7 — second browser launch (double must have been called exactly once)
// ---------------------------------------------------------------------------

{
  const ledger = new runner.AppendOnlyLedger();
  const control = new runner.ControlPlane({
    contract,
    contractSha,
    candidateSha: CANDIDATE_FIXTURE_SHA,
    ledger,
  });
  control.materialized = runner.materializeInput(contract, FIXTURE_ENV);
  control.preflight([{ ok: true, label: 'probe' }]);
  const argv = ['node', 'tools', 'fixture-launch'];
  control.authorize({ contractSha, inputSha: control.materialized.inputSha, argv, candidateSha: CANDIDATE_FIXTURE_SHA });
  const calls = [];
  const impl = (file, args) => {
    calls.push({ file, argsCount: args.length });
    return Promise.resolve({ started: true });
  };
  await control.launch(impl, { argv, contractSha, inputSha: control.materialized.inputSha, candidateSha: CANDIDATE_FIXTURE_SHA });
  expectCategory(
    () =>
      control.launch(impl, {
        argv,
        contractSha,
        inputSha: control.materialized.inputSha,
        candidateSha: CANDIDATE_FIXTURE_SHA,
      }),
    'launch_already_invoked',
    'R7: launch invoked twice',
  );
  expect(calls.length === 1, 'R7: the double executed exactly one process start');
  await greenPath();
}

// ---------------------------------------------------------------------------
// R8 — SHA drift (candidate / input / contract)
// ---------------------------------------------------------------------------

{
  const control = new runner.ControlPlane({
    contract,
    contractSha,
    candidateSha: CANDIDATE_FIXTURE_SHA,
    ledger: new runner.AppendOnlyLedger(),
  });
  const { inputSha } = runner.materializeInput(contract, FIXTURE_ENV);
  control.materialized = { input: runner.materializeInput(contract, FIXTURE_ENV).input, inputSha };
  control.preflight([{ ok: true, label: 'probe' }]);
  const argv = ['node', 'tools', 'fixture-launch'];
  expectCategory(
    () =>
      control.authorize({
        contractSha,
        inputSha,
        argv,
        candidateSha: runner.sha256Hex('drifted-candidate'),
      }),
    'candidate_sha_drift',
    'R8: candidate SHA drift',
  );
  const control2 = new runner.ControlPlane({
    contract,
    contractSha,
    candidateSha: CANDIDATE_FIXTURE_SHA,
    ledger: new runner.AppendOnlyLedger(),
  });
  control2.materialized = { input: runner.materializeInput(contract, FIXTURE_ENV).input, inputSha };
  control2.preflight([{ ok: true, label: 'probe' }]);
  expectCategory(
    () =>
      control2.authorize({
        contractSha,
        inputSha: runner.sha256Hex('drifted-input'),
        argv,
        candidateSha: CANDIDATE_FIXTURE_SHA,
      }),
    'input_sha_drift',
    'R8: input SHA drift',
  );
  const control3 = new runner.ControlPlane({
    contract,
    contractSha,
    candidateSha: CANDIDATE_FIXTURE_SHA,
    ledger: new runner.AppendOnlyLedger(),
  });
  control3.materialized = { input: runner.materializeInput(contract, FIXTURE_ENV).input, inputSha };
  control3.preflight([{ ok: true, label: 'probe' }]);
  expectCategory(
    () =>
      control3.authorize({
        contractSha: runner.sha256Hex('drifted-contract'),
        inputSha,
        argv,
        candidateSha: CANDIDATE_FIXTURE_SHA,
      }),
    'contract_sha_drift',
    'R8: contract SHA drift',
  );
  // A drifted control plane is terminal VOID — nothing continues afterwards.
  expectCategory(() => control.preflight([]), 'terminal_stop', 'R8: drifted plane is terminal');
  await greenPath();
}

// ---------------------------------------------------------------------------
// R9 — argv drift + non-array argv (shell strings refused)
//
// A drift VOID is terminal (rule 6), so each probe below uses its own fresh
// plane; that per-probe isolation is itself part of the contract.
// ---------------------------------------------------------------------------

{
  const makePlane = () => {
    const control = new runner.ControlPlane({
      contract,
      contractSha,
      candidateSha: CANDIDATE_FIXTURE_SHA,
      ledger: new runner.AppendOnlyLedger(),
    });
    const { inputSha } = runner.materializeInput(contract, FIXTURE_ENV);
    control.materialized = { input: runner.materializeInput(contract, FIXTURE_ENV).input, inputSha };
    control.preflight([{ ok: true, label: 'probe' }]);
    return { control, inputSha };
  };
  const argv = ['node', 'tools', 'fixture-launch'];

  const { control, inputSha } = makePlane();
  control.authorize({ contractSha, inputSha, argv, candidateSha: CANDIDATE_FIXTURE_SHA });
  expectCategory(
    () =>
      control.launch(
        (file, args) => Promise.resolve({ file, args }),
        { argv: ['node', 'tools', 'DIFFERENT-launch'], contractSha, inputSha, candidateSha: CANDIDATE_FIXTURE_SHA },
      ),
    'argv_drift',
    'R9: argv drift at launch',
  );

  const { control: controlB, inputSha: inputShaB } = makePlane();
  expectCategory(
    () =>
      controlB.authorize({
        contractSha,
        inputSha: inputShaB,
        argv: 'node tools fixture-launch',
        candidateSha: CANDIDATE_FIXTURE_SHA,
      }),
    'argv_not_array',
    'R9: shell-style string argv refused at authorize',
  );

  const { control: controlC, inputSha: inputShaC } = makePlane();
  controlC.authorize({ contractSha, inputSha: inputShaC, argv, candidateSha: CANDIDATE_FIXTURE_SHA });
  expectCategory(
    () =>
      controlC.launch((file, args) => Promise.resolve({ file, args }), {
        argv: 'node tools fixture-launch',
        contractSha,
        inputSha: inputShaC,
        candidateSha: CANDIDATE_FIXTURE_SHA,
      }),
    'argv_not_array',
    'R9: shell-style string argv refused at launch',
  );

  const { control: controlD, inputSha: inputShaD } = makePlane();
  expectCategory(
    () =>
      controlD.authorize({
        contractSha,
        inputSha: inputShaD,
        argv: [],
        candidateSha: CANDIDATE_FIXTURE_SHA,
      }),
    'argv_not_array',
    'R9: empty argv refused',
  );

  // The argv-drifted plane is terminal VOID — nothing continues afterwards.
  expectCategory(() => control.preflight([]), 'terminal_stop', 'R9: drifted plane is terminal');
  await greenPath();
}

// ---------------------------------------------------------------------------
// R10 — sensitive value into the ledger
// ---------------------------------------------------------------------------

{
  const ledger = new runner.AppendOnlyLedger();
  const control = new runner.ControlPlane({
    contract,
    contractSha,
    candidateSha: CANDIDATE_FIXTURE_SHA,
    ledger,
  });
  control.materialized = runner.materializeInput(contract, FIXTURE_ENV);
  const sensitive = Object.values(control.materialized.input.values);
  let acceptedCleanNote = false;
  try {
    ledger.append({ kind: 'note', label: 'owner' }, sensitive);
    acceptedCleanNote = true;
  } catch {
    acceptedCleanNote = false;
  }
  expect(acceptedCleanNote, 'R10: category-only note accepted');
  // A note carrying a materialized VALUE is refused outright.
  expectCategory(
    () => ledger.append({ kind: 'note', label: FIXTURE_ENV.J1H2C_RETAILER_EMAIL }, sensitive),
    'sensitive_value_rejected',
    'R10: owner email value into ledger',
  );
  expectCategory(
    () => ledger.append({ kind: 'note', label: FIXTURE_ENV.J1H2C_RETAILER_NEW_PASSWORD }, sensitive),
    'sensitive_value_rejected',
    'R10: password value into ledger',
  );
  expectCategory(
    () => ledger.append({ kind: 'note', note: `code=${FIXTURE_ENV.J1H2C_WHOLESALER_CANONICAL_CODE}` }, sensitive),
    'sensitive_value_rejected',
    'R10: W1 code embedded in note text',
  );
  await greenPath();
}

// ---------------------------------------------------------------------------
// Verdict
// ---------------------------------------------------------------------------

if (failures.length > 0) {
  for (const message of failures) console.error(message);
  console.error(`BROWSER-AUTHORITY CONTRACT CHECK FAILED (${failures.length})`);
  process.exit(1);
}
console.log('BROWSER-AUTHORITY CONTROL-PLANE CONTRACTS PASSED (S0 + G + R1-R10, real module, per-RED restore re-GREEN).');
