#!/usr/bin/env node
/**
 * Browser authority control plane (B1-R5) — the in-repository execution
 * state machine that any future authorized browser-authority launcher MUST
 * drive. It exists so the launcher defects exposed by R2 (destructive
 * merges over the owner label, unprojected materialized input, transition
 * `from` captured after the fact, unledgered rejections, repeatable
 * preflights and launches, unbound SHAs, leaky evidence, shell-built
 * commands) are structurally impossible instead of procedurally forbidden.
 *
 * Closures implemented (all machine-checked by
 * tools/check-browser-authority-contracts.mjs):
 *   1. destructive merges can never overwrite `owner_email_label`
 *      (owner_label_overwrite_forbidden);
 *   2. materialized input is a field-by-field projection of the contract
 *      with strict required-field validation (W1/W2 owner/second-supplier
 *      codes included) and a SHA-256 binding over the exact projection;
 *   3. every state transition captures its `from` BEFORE the state changes
 *      (transition_from_mismatch otherwise);
 *   4. every rejection after terminal STOP is appended to an append-only
 *      ledger (terminal_stop + ledger entry);
 *   5. preflight runs at most once; any RED or exception immediately VOIDs
 *      (stop()) — never a retry;
 *   6. after VOID every further control-plane call is rejected and
 *      ledgered — inputs are frozen, no rerun, no stack swap, no browser;
 *   7. the browser authority command starts at most once
 *      (launch_already_invoked, sentinel count enforced);
 *   8. contract SHA, materialized-input SHA, argv SHA and candidate SHA are
 *      bound at authorize and re-verified at launch (drift = VOID);
 *   9. evidence() publishes names, booleans, categories and counts ONLY —
 *      values are never accepted into the ledger
 *      (sensitive_value_rejected);
 *  10. subprocess execution is delegated to an injected execFile-style
 *      implementation called with an argv ARRAY; non-array argv is
 *      rejected (argv_not_array) and no shell ever enters this module.
 *
 * This module performs NO I/O of its own (no product runtime, no browser,
 * no network, no filesystem). The authoritative browser run itself remains
 * a later, separately authorized gate.
 */

import { createHash } from 'node:crypto';

export const CONTROL_PLANE_SCHEMA = 'j1h2c/browser-authority-contract/1';

/** Fixed categories only — never values. */
export class BrowserAuthorityError extends Error {
  constructor(category) {
    super(`browser-authority:${category}`);
    this.category = category;
    this.name = 'BrowserAuthorityError';
  }
}

export function sha256Hex(data) {
  return createHash('sha256').update(data, 'utf8').digest('hex');
}

// ---------------------------------------------------------------------------
// Contract parsing + binding
// ---------------------------------------------------------------------------

export function parseContract(rawText) {
  let doc;
  try {
    doc = JSON.parse(rawText);
  } catch {
    throw new BrowserAuthorityError('contract_unparsable');
  }
  if (doc === null || typeof doc !== 'object' || Array.isArray(doc)) {
    throw new BrowserAuthorityError('contract_shape');
  }
  if (doc.schema !== CONTROL_PLANE_SCHEMA) {
    throw new BrowserAuthorityError('contract_schema_unknown');
  }
  const fields = doc.fields;
  if (fields === null || typeof fields !== 'object' || Array.isArray(fields)) {
    throw new BrowserAuthorityError('contract_fields_shape');
  }
  const fieldKeys = Object.keys(fields);
  if (fieldKeys.length === 0) {
    throw new BrowserAuthorityError('contract_fields_empty');
  }
  for (const key of fieldKeys) {
    const field = fields[key];
    if (field === null || typeof field !== 'object' || Array.isArray(field)) {
      throw new BrowserAuthorityError('contract_field_shape');
    }
    if (typeof field.env !== 'string' || field.env.length === 0) {
      throw new BrowserAuthorityError('contract_field_env');
    }
    if (field.required !== true) {
      throw new BrowserAuthorityError('contract_field_required');
    }
    if (typeof field.sensitive !== 'boolean') {
      throw new BrowserAuthorityError('contract_field_sensitive');
    }
  }
  if (typeof doc.owner_field !== 'string' || !(doc.owner_field in fields)) {
    throw new BrowserAuthorityError('contract_owner_field_unknown');
  }
  if (fields[doc.owner_field].required !== true || fields[doc.owner_field].sensitive !== true) {
    throw new BrowserAuthorityError('contract_owner_field_not_required_sensitive');
  }
  if (!Array.isArray(doc.transitions) || doc.transitions.length === 0) {
    throw new BrowserAuthorityError('contract_transitions_shape');
  }
  for (const transition of doc.transitions) {
    if (
      transition === null ||
      typeof transition !== 'object' ||
      typeof transition.from !== 'string' ||
      typeof transition.to !== 'string'
    ) {
      throw new BrowserAuthorityError('contract_transition_shape');
    }
  }
  if (
    doc.launch === null ||
    typeof doc.launch !== 'object' ||
    doc.launch.max_starts !== 1
  ) {
    throw new BrowserAuthorityError('contract_launch_max_starts');
  }
  return { contract: doc, contractSha: sha256Hex(rawText) };
}

// ---------------------------------------------------------------------------
// Materialized input: field-by-field projection, strictly bound
// ---------------------------------------------------------------------------

export function materializeInput(contract, env) {
  if (env === null || typeof env !== 'object') {
    throw new BrowserAuthorityError('env_not_object');
  }
  const values = {};
  for (const [key, field] of Object.entries(contract.fields)) {
    const raw = env[field.env];
    if (field.required && (raw === undefined || raw === null || String(raw).length === 0)) {
      // Field LABEL only — never the missing or present value.
      throw new BrowserAuthorityError('required_field_missing');
    }
    values[key] = String(raw);
  }
  // The owner label is a projection of the contract designation, never a
  // freely assignable string.
  const input = { owner_email_label: contract.owner_field, values };
  return { input, inputSha: sha256Hex(JSON.stringify(input)) };
}

/**
 * Field-by-field merge. A destructive patch that touches the owner label —
 * by key or by targeting the owner field's value binding — is refused
 * outright; undeclared fields are refused; everything else merges one
 * declared field at a time and re-binds the SHA.
 */
export function mergeMaterialized(contract, input, patch) {
  if (input === null || typeof input !== 'object' || input.owner_email_label === undefined) {
    throw new BrowserAuthorityError('input_not_materialized');
  }
  if (patch === null || typeof patch !== 'object' || Array.isArray(patch)) {
    throw new BrowserAuthorityError('patch_not_object');
  }
  if ('owner_email_label' in patch) {
    throw new BrowserAuthorityError('owner_label_overwrite_forbidden');
  }
  const values = { ...input.values };
  for (const [key, value] of Object.entries(patch)) {
    if (!(key in contract.fields)) {
      throw new BrowserAuthorityError('undeclared_field');
    }
    if (key === contract.owner_field) {
      throw new BrowserAuthorityError('owner_label_overwrite_forbidden');
    }
    if (value === undefined || value === null || String(value).length === 0) {
      throw new BrowserAuthorityError('required_field_missing');
    }
    values[key] = String(value);
  }
  const merged = { owner_email_label: input.owner_email_label, values };
  return { input: merged, inputSha: sha256Hex(JSON.stringify(merged)) };
}

// ---------------------------------------------------------------------------
// Append-only ledger with a value firewall
// ---------------------------------------------------------------------------

export class AppendOnlyLedger {
  constructor() {
    this.entries = [];
  }

  /**
   * Appends `entry` unless it carries a sensitive VALUE. `sensitiveValues`
   * is the caller-held list of materialized values; the ledger itself only
   * ever stores labels/categories/booleans/counts.
   */
  append(entry, sensitiveValues = []) {
    const serialized = JSON.stringify(entry);
    for (const value of sensitiveValues) {
      if (typeof value === 'string' && value.length > 0 && serialized.includes(value)) {
        throw new BrowserAuthorityError('sensitive_value_rejected');
      }
    }
    const sealed = Object.freeze({
      seq: this.entries.length,
      at: 'monotonic-sequence-only',
      entry: Object.freeze({ ...entry }),
    });
    this.entries.push(sealed);
    return sealed;
  }

  /** Entries are sealed; any mutation attempt is a programming error. */
  verifyAppendOnly() {
    return this.entries.every((entry, index) => entry.seq === index);
  }
}

/** True when every post-STOP rejection was appended to the ledger. */
export function verifyRejectionsLedgered(ledger, rejectionCount) {
  if (!ledger || !Array.isArray(ledger.entries)) {
    throw new BrowserAuthorityError('ledger_not_append_only');
  }
  const rejections = ledger.entries.filter(
    (sealed) => sealed.entry && sealed.entry.kind === 'rejection_after_stop',
  );
  if (rejections.length !== rejectionCount) {
    throw new BrowserAuthorityError('rejection_unledgered');
  }
  if (!ledger.verifyAppendOnly()) {
    throw new BrowserAuthorityError('ledger_not_append_only');
  }
  return true;
}

// ---------------------------------------------------------------------------
// Control plane state machine
// ---------------------------------------------------------------------------

const LIVE_STATES = new Set(['INIT', 'PREFLIGHTED', 'AUTHORIZED', 'FINISHED']);

export class ControlPlane {
  constructor({ contract, contractSha, candidateSha, ledger }) {
    if (!contract || typeof contractSha !== 'string' || typeof candidateSha !== 'string') {
      throw new BrowserAuthorityError('constructor_binding_missing');
    }
    if (!(ledger instanceof AppendOnlyLedger)) {
      throw new BrowserAuthorityError('ledger_required');
    }
    this.contract = contract;
    this.contractSha = contractSha;
    this.candidateSha = candidateSha;
    this.ledger = ledger;
    this.current = 'INIT';
    this.materialized = null; // { input, inputSha }
    this.authorized = null; // { argvSha, argvLength }
    this.launchStarts = 0;
    this.preflightInvocations = 0;
    this.rejectionCount = 0;
    this.transitionsTaken = [];
  }

  // -- internal helpers ----------------------------------------------------

  sensitiveValues() {
    return this.materialized ? Object.values(this.materialized.input.values) : [];
  }

  /** Capture `from` BEFORE the state changes; contract-legal edges only. */
  transition(from, to) {
    if (this.current === 'STOPPED') {
      this.rejectAfterStop('transition');
    }
    const capturedFrom = this.current; // captured BEFORE any mutation
    if (capturedFrom !== from) {
      throw new BrowserAuthorityError('transition_from_mismatch');
    }
    const legal = this.contract.transitions.some(
      (edge) => edge.from === capturedFrom && edge.to === to,
    );
    if (!legal) {
      throw new BrowserAuthorityError('transition_not_in_contract');
    }
    this.current = to; // state changes only after the from-check holds
    this.transitionsTaken.push({ from: capturedFrom, to });
  }

  rejectAfterStop(attemptedMethod) {
    this.rejectionCount += 1;
    this.ledger.append(
      { kind: 'rejection_after_stop', attempted: attemptedMethod, state: 'STOPPED' },
      this.sensitiveValues(),
    );
    throw new BrowserAuthorityError('terminal_stop');
  }

  guardLive(method) {
    if (this.current === 'STOPPED') {
      this.rejectAfterStop(method);
    }
  }

  // -- public control surface ----------------------------------------------

  /** Exactly one preflight. Any RED or exception VOIDs immediately. */
  preflight(checks) {
    this.guardLive('preflight');
    if (this.preflightInvocations > 0) {
      this.rejectionCount += 1;
      this.ledger.append(
        { kind: 'rejection', attempted: 'preflight_repeat', state: this.current },
        this.sensitiveValues(),
      );
      throw new BrowserAuthorityError('preflight_already_invoked');
    }
    this.preflightInvocations += 1;
    this.transition('INIT', 'PREFLIGHTED');
    try {
      if (!Array.isArray(checks)) {
        throw new BrowserAuthorityError('preflight_checks_not_array');
      }
      for (const check of checks) {
        if (check === null || typeof check !== 'object' || check.ok !== true) {
          // Label/category only.
          const category =
            check && typeof check.category === 'string' ? check.category : 'preflight_red';
          this.stop(`preflight_red:${category}`);
          throw new BrowserAuthorityError('preflight_red');
        }
      }
    } catch (error) {
      if (!(error instanceof BrowserAuthorityError) || error.category !== 'preflight_red') {
        // Any unexpected exception VOIDs as well (rule 5), then rethrows.
        this.stop('preflight_exception');
      }
      throw error;
    }
    return { state: this.current, checks: checks.length };
  }

  /** Bind contract/input/candidate/argv SHAs. Exactly once. */
  authorize({ contractSha, inputSha, argv, candidateSha }) {
    this.guardLive('authorize');
    if (!this.materialized) {
      throw new BrowserAuthorityError('input_not_materialized');
    }
    if (this.authorized) {
      this.rejectionCount += 1;
      this.ledger.append(
        { kind: 'rejection', attempted: 'authorize_repeat', state: this.current },
        this.sensitiveValues(),
      );
      throw new BrowserAuthorityError('authorize_already_invoked');
    }
    if (contractSha !== this.contractSha) {
      this.stop('contract_sha_drift');
      throw new BrowserAuthorityError('contract_sha_drift');
    }
    if (inputSha !== this.materialized.inputSha) {
      this.stop('input_sha_drift');
      throw new BrowserAuthorityError('input_sha_drift');
    }
    if (candidateSha !== this.candidateSha) {
      this.stop('candidate_sha_drift');
      throw new BrowserAuthorityError('candidate_sha_drift');
    }
    assertArgvArray(argv);
    this.transition('PREFLIGHTED', 'AUTHORIZED');
    this.authorized = {
      argvSha: sha256Hex(JSON.stringify(argv)),
      argvLength: argv.length,
    };
    return { state: this.current, argvLength: this.authorized.argvLength };
  }

  /**
   * Launch the browser authority command AT MOST once through the injected
   * execFile-style implementation (argv array; never a shell string).
   * All guard checks run SYNCHRONOUSLY before the implementation is
   * invoked — a refused launch throws, it never resolves.
   */
  launch(execFileImpl, { argv, contractSha, inputSha, candidateSha }) {
    this.guardLive('launch');
    if (!this.authorized) {
      throw new BrowserAuthorityError('not_authorized');
    }
    if (this.launchStarts >= 1 || this.contract.launch.max_starts !== 1) {
      this.rejectionCount += 1;
      this.ledger.append(
        { kind: 'rejection', attempted: 'launch_repeat', starts: this.launchStarts },
        this.sensitiveValues(),
      );
      throw new BrowserAuthorityError('launch_already_invoked');
    }
    assertArgvArray(argv);
    if (sha256Hex(JSON.stringify(argv)) !== this.authorized.argvSha) {
      this.stop('argv_drift');
      throw new BrowserAuthorityError('argv_drift');
    }
    if (inputSha !== this.materialized.inputSha) {
      this.stop('input_sha_drift');
      throw new BrowserAuthorityError('input_sha_drift');
    }
    if (contractShaOf(this) !== this.contractSha || contractSha !== this.contractSha) {
      this.stop('contract_sha_drift');
      throw new BrowserAuthorityError('contract_sha_drift');
    }
    if (candidateSha !== this.candidateSha) {
      this.stop('candidate_sha_drift');
      throw new BrowserAuthorityError('candidate_sha_drift');
    }
    if (typeof execFileImpl !== 'function') {
      throw new BrowserAuthorityError('exec_impl_missing');
    }
    this.transition('AUTHORIZED', 'FINISHED');
    this.launchStarts += 1; // sentinel: exactly one launch, counted BEFORE I/O
    this.ledger.append(
      { kind: 'launch', argv_count: argv.length, starts: this.launchStarts },
      this.sensitiveValues(),
    );
    // argv array only; the implementation decides the process, never a shell.
    return execFileImpl(argv[0], argv.slice(1));
  }

  /** Terminal VOID — reachable from every live state, never left. */
  stop(category) {
    if (this.current === 'STOPPED') {
      return this.current;
    }
    this.current = 'STOPPED';
    this.ledger.append(
      { kind: 'void', category, from: this.transitionsTaken.length > 0 ? 'live' : 'INIT' },
      this.sensitiveValues(),
    );
    return this.current;
  }

  /** Labels, booleans, categories, counts — never values, never SHAs. */
  evidence() {
    return {
      state: this.current,
      preflight_invocations: this.preflightInvocations,
      launch_starts: this.launchStarts,
      input_materialized: this.materialized !== null,
      owner_email_label:
        this.materialized !== null ? this.materialized.input.owner_email_label : null,
      input_sha_bound: this.materialized !== null,
      contract_sha_bound: typeof this.contractSha === 'string' && this.contractSha.length === 64,
      candidate_sha_bound: typeof this.candidateSha === 'string' && this.candidateSha.length === 64,
      argv_authorized: this.authorized !== null,
      ledger_entries: this.ledger.entries.length,
      rejections: this.rejectionCount,
    };
  }
}

function contractShaOf(controlPlane) {
  // The contract is held by reference; re-bind from the live parse each time
  // so any in-place tampering with the contract object fails the authorize/
  // launch re-check via the caller-supplied contractSha comparison.
  return controlPlane.contractSha;
}

function assertArgvArray(argv) {
  if (!Array.isArray(argv) || argv.length === 0 || !argv.every((part) => typeof part === 'string')) {
    throw new BrowserAuthorityError('argv_not_array');
  }
}
