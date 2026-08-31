#!/usr/bin/env node
/**
 * Browser authority control plane (B1-R5-R1) — live-binding, terminal-state
 * and audit-ledger truth closure over the B1-R5 state machine.
 *
 * R1 closures implemented (machine-checked by
 * tools/check-browser-authority-contracts.mjs, scenarios R1-R18):
 *
 *   A. LIVE BYTE BINDING — no caller self-attestation survives:
 *      - the protected profile is re-read from its canonical path and its
 *        SHA-256 recomputed at preflight, authorize and launch
 *        (profile_sha_drift -> STOPPED, starts preserved truthfully);
 *      - the task-private contract file is re-read and re-hashed at
 *        authorize and launch (contract_sha_drift);
 *      - the materialized input is PRIVATE and deep-frozen; authorize and
 *        launch recompute its canonical SHA (input_sha_drift);
 *      - the candidate is resolved through a LIVE `git rev-parse HEAD`
 *        argv-array subprocess against the task repo root — caller strings
 *        are never trusted (candidate_sha_drift).
 *      The B1-R5 self-comparison helper is gone; every binding is a live
 *      byte re-read.
 *
 *   B. TERMINAL STATE TRUTH — INIT, PREFLIGHTED, AUTHORIZED, RUNNING,
 *      FINISHED, TEST_RED, STOPPED. launch writes the start sentinel and
 *      enters RUNNING; only child rc==0 AND a complete reconciliation reach
 *      FINISHED; a started child with rc!=0 or an incomplete reconciliation
 *      lands TEST_RED (never FINISHED, never VOID); an executor exception
 *      before an actual start lands STOPPED with the TRUE starts count.
 *
 *   C. ONCE-ONLY FAIL-STOP — a second preflight/authorize/launch first
 *      persists the rejection into the durable ledger, then STOPPED; after
 *      catching, every further surface is terminal_stop with starts intact.
 *
 *   D. NON-WEAKENABLE PROFILE — inventory/browser-authority-profile.json is
 *      the protected field set, machine-reconciled against the J1H2C_*
 *      variables the harness actually consumes (env.ts contract);
 *      contract.fields must cover every profile field (weaker caller
 *      contract -> contract_weaker_than_profile); unknown contract fields
 *      are refused; no CLI/env/caller override exists.
 *
 *   E. DURABLE AUDIT LEDGER — entries are private; records go to a
 *      task-private JSONL sink as {seq, prev_sha, entry, event_sha}; every
 *      append re-reads the file and verifies the count and hash chain BEFORE
 *      writing, then flushes+fsyncs before returning; truncation, tail
 *      rewrite and duplicate seq fail closed. Terminal evidence requires a
 *      terminal_seal record — no seal, no PASS. Values never enter the
 *      ledger (sensitive_value_rejected).
 *
 * Subprocesses use argv arrays exclusively (git rev-parse; the injected
 * execFile-style launch implementation). The authoritative browser journey
 * itself remains a later, separately authorized gate.
 */

import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { closeSync, existsSync, fsyncSync, openSync, readFileSync, writeSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

export const CONTROL_PLANE_SCHEMA = 'j1h2c/browser-authority-contract/1';
export const PROFILE_SCHEMA = 'j1h2c/browser-authority-profile/1';
const GENESIS_SHA = '0'.repeat(64);

/** Canonical profile path, resolved relative to THIS module (never cwd). */
export function canonicalProfilePath(moduleFile = fileURLToPath(import.meta.url)) {
  return join(dirname(moduleFile), '..', 'inventory', 'browser-authority-profile.json');
}

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

function deepFreeze(value) {
  if (value !== null && typeof value === 'object') {
    for (const key of Object.keys(value)) deepFreeze(value[key]);
    Object.freeze(value);
  }
  return value;
}

/**
 * LIVE candidate resolution: `git -C <repoRoot> rev-parse HEAD` via an argv
 * array. No caller string is ever trusted as the candidate.
 */
export function resolveLiveHead(repoRoot) {
  try {
    const out = execFileSync('git', ['-C', repoRoot, 'rev-parse', 'HEAD'], {
      stdio: ['ignore', 'pipe', 'ignore'],
    });
    const sha = out.toString('utf8').trim();
    if (!/^[0-9a-f]{40}$/.test(sha)) {
      throw new BrowserAuthorityError('live_head_unresolvable');
    }
    return sha;
  } catch (error) {
    if (error instanceof BrowserAuthorityError) throw error;
    throw new BrowserAuthorityError('live_head_unresolvable');
  }
}

function readRawSha256(path) {
  try {
    return sha256Hex(readFileSync(path));
  } catch {
    throw new BrowserAuthorityError('live_binding_read_failed');
  }
}

// ---------------------------------------------------------------------------
// Profile (protected, non-weakenable) and contract parsing
// ---------------------------------------------------------------------------

export function parseProfile(rawText) {
  let doc;
  try {
    doc = JSON.parse(rawText);
  } catch {
    throw new BrowserAuthorityError('profile_unparsable');
  }
  if (doc === null || typeof doc !== 'object' || Array.isArray(doc)) {
    throw new BrowserAuthorityError('profile_shape');
  }
  if (doc.schema !== PROFILE_SCHEMA) {
    throw new BrowserAuthorityError('profile_schema_unknown');
  }
  if (doc.fields === null || typeof doc.fields !== 'object' || Array.isArray(doc.fields)) {
    throw new BrowserAuthorityError('profile_fields_shape');
  }
  const keys = Object.keys(doc.fields);
  if (keys.length === 0) {
    throw new BrowserAuthorityError('profile_fields_empty');
  }
  for (const [key, field] of Object.entries(doc.fields)) {
    if (field === null || typeof field !== 'object') {
      throw new BrowserAuthorityError('profile_field_shape');
    }
    if (typeof field.env !== 'string' || !/^J1H2C_[A-Z0-9_]+$/.test(field.env)) {
      throw new BrowserAuthorityError('profile_field_env');
    }
    if (field.required !== true) {
      throw new BrowserAuthorityError('profile_field_required');
    }
    if (typeof field.sensitive !== 'boolean' || typeof field.role !== 'string') {
      throw new BrowserAuthorityError('profile_field_shape');
    }
  }
  if (typeof doc.owner_field !== 'string' || !(doc.owner_field in doc.fields)) {
    throw new BrowserAuthorityError('profile_owner_field_unknown');
  }
  if (doc.fields[doc.owner_field].sensitive !== true) {
    throw new BrowserAuthorityError('profile_owner_not_sensitive');
  }
  return { profile: doc, profileSha: sha256Hex(rawText) };
}

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
  if (doc.fields === null || typeof doc.fields !== 'object' || Array.isArray(doc.fields)) {
    throw new BrowserAuthorityError('contract_fields_shape');
  }
  for (const field of Object.values(doc.fields)) {
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
  if (typeof doc.owner_field !== 'string' || !(doc.owner_field in doc.fields)) {
    throw new BrowserAuthorityError('contract_owner_field_unknown');
  }
  if (
    !Array.isArray(doc.transitions) ||
    doc.transitions.length === 0 ||
    doc.transitions.some(
      (edge) =>
        edge === null ||
        typeof edge !== 'object' ||
        typeof edge.from !== 'string' ||
        typeof edge.to !== 'string',
    )
  ) {
    throw new BrowserAuthorityError('contract_transitions_shape');
  }
  if (doc.launch === null || typeof doc.launch !== 'object' || doc.launch.max_starts !== 1) {
    throw new BrowserAuthorityError('contract_launch_max_starts');
  }
  return doc;
}

/**
 * Profile reconciliation: a caller contract may never be weaker than the
 * protected profile (every profile field must be covered by the contract,
 * by env variable name), and may never invent fields the profile does not
 * know (no side doors).
 */
export function reconcileContractWithProfile(contract, profile) {
  const contractEnvs = new Set(Object.values(contract.fields).map((field) => field.env));
  const profileEnvs = new Set(Object.values(profile.fields).map((field) => field.env));
  for (const env of profileEnvs) {
    if (!contractEnvs.has(env)) {
      throw new BrowserAuthorityError('contract_weaker_than_profile');
    }
  }
  for (const env of contractEnvs) {
    if (!profileEnvs.has(env)) {
      throw new BrowserAuthorityError('contract_field_unknown_to_profile');
    }
  }
  const profileOwnerEnv = profile.fields[profile.owner_field].env;
  const ownerEntry = Object.entries(contract.fields).find(
    ([, field]) => field.env === profileOwnerEnv,
  );
  if (!ownerEntry || ownerEntry[1].sensitive !== true) {
    throw new BrowserAuthorityError('contract_weaker_than_profile');
  }
  return true;
}

// ---------------------------------------------------------------------------
// Materialized input: private, deep-frozen, strictly projected
// ---------------------------------------------------------------------------

export function materializeInput(contract, env) {
  if (env === null || typeof env !== 'object') {
    throw new BrowserAuthorityError('env_not_object');
  }
  const values = {};
  for (const [key, field] of Object.entries(contract.fields)) {
    const raw = env[field.env];
    if (field.required && (raw === undefined || raw === null || String(raw).length === 0)) {
      throw new BrowserAuthorityError('required_field_missing');
    }
    values[key] = String(raw);
  }
  const input = deepFreeze({ owner_email_label: contract.owner_field, values });
  return { input, inputSha: sha256Hex(JSON.stringify(input)) };
}

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
  const merged = deepFreeze({ owner_email_label: input.owner_email_label, values });
  return { input: merged, inputSha: sha256Hex(JSON.stringify(merged)) };
}

// ---------------------------------------------------------------------------
// Durable append-only JSONL ledger (private entries, hash chain, fsync)
// ---------------------------------------------------------------------------

export class DurableJsonlLedger {
  constructor(sinkPath) {
    if (typeof sinkPath !== 'string' || sinkPath.length === 0) {
      throw new BrowserAuthorityError('ledger_sink_required');
    }
    this.#sinkPath = sinkPath;
  }

  #sinkPath;
  #lastSeq = null;
  #lastTail = GENESIS_SHA;

  #readRecords() {
    if (!existsSync(this.#sinkPath)) return [];
    const text = readFileSync(this.#sinkPath, 'utf8');
    const lines = text.split('\n').filter((line) => line.length > 0);
    return lines.map((line) => {
      try {
        return JSON.parse(line);
      } catch {
        throw new BrowserAuthorityError('ledger_line_unparsable');
      }
    });
  }

  /**
   * Re-reads the sink from disk and verifies: line count, strict seq
   * ordering (no duplicates, no gaps), and the prev_sha/event_sha chain.
   * Tail deletion, tail rewrite and duplicate seq all fail closed here. An
   * instance that has appended before also holds its own private expected
   * tail, so a silent truncation of records it wrote is detected even
   * though the remaining prefix chain would still be valid.
   */
  verifyChain() {
    const records = this.#readRecords();
    let prev = GENESIS_SHA;
    for (const [index, record] of records.entries()) {
      if (record.seq !== index) {
        throw new BrowserAuthorityError('ledger_seq_duplicate');
      }
      if (record.prev_sha !== prev) {
        throw new BrowserAuthorityError('ledger_chain_broken');
      }
      const expected = sha256Hex(
        JSON.stringify({ seq: record.seq, prev_sha: prev, entry: record.entry }),
      );
      if (record.event_sha !== expected) {
        throw new BrowserAuthorityError('ledger_chain_broken');
      }
      prev = record.event_sha;
    }
    if (this.#lastSeq !== null) {
      const last = records[records.length - 1];
      if (records.length < this.#lastSeq + 1 || !last || last.event_sha !== this.#lastTail) {
        throw new BrowserAuthorityError('ledger_truncated');
      }
    }
    return { count: records.length, tail: prev };
  }

  append(entry, sensitiveValues = []) {
    // Verify the on-disk chain BEFORE every write.
    const { count, tail } = this.verifyChain();
    const serializedCheck = JSON.stringify(entry);
    for (const value of sensitiveValues) {
      if (typeof value === 'string' && value.length > 0 && serializedCheck.includes(value)) {
        throw new BrowserAuthorityError('sensitive_value_rejected');
      }
    }
    const record = {
      seq: count,
      prev_sha: tail,
      entry,
      event_sha: sha256Hex(JSON.stringify({ seq: count, prev_sha: tail, entry })),
    };
    const line = JSON.stringify(record) + '\n';
    // Append + flush + fsync BEFORE returning (or throwing).
    const fd = openSync(this.#sinkPath, 'a');
    try {
      writeSync(fd, line);
      fsyncSync(fd);
    } finally {
      closeSync(fd);
    }
    this.#lastSeq = record.seq;
    this.#lastTail = record.event_sha;
    return record;
  }

  hasTerminalSeal() {
    return this.#readRecords().some(
      (record) => record.entry && record.entry.kind === 'terminal_seal',
    );
  }
}

/** Retained for surface compatibility with the B1-R5 checker. */
export class AppendOnlyLedger extends DurableJsonlLedger {}

// ---------------------------------------------------------------------------
// Control plane
// ---------------------------------------------------------------------------

export const LIVE_STATES = [
  'INIT',
  'PREFLIGHTED',
  'AUTHORIZED',
  'RUNNING',
  'FINISHED',
  'TEST_RED',
  'STOPPED',
];

export class ControlPlane {
  /**
   * @param {object} options
   *   contractPath  task-private contract JSON file (live byte source)
   *   repoRoot      task repository root for the live git candidate
   *   ledger        DurableJsonlLedger
   * The protected profile is ALWAYS the canonical module-relative
   * browser-authority-profile.json — there is no profilePath override: a
   * caller-supplied weaker profile cannot exist by construction.
   */
  constructor({ contractPath, repoRoot, ledger }) {
    if (typeof contractPath !== 'string' || contractPath.length === 0) {
      throw new BrowserAuthorityError('contract_path_missing');
    }
    if (typeof repoRoot !== 'string' || repoRoot.length === 0) {
      throw new BrowserAuthorityError('repo_root_missing');
    }
    if (!(ledger instanceof DurableJsonlLedger)) {
      throw new BrowserAuthorityError('ledger_required');
    }
    this.#contractPath = contractPath;
    this.#repoRoot = repoRoot;
    this.#ledger = ledger;
    this.#profilePath = canonicalProfilePath();

    // Initial binding — all four from LIVE sources, none from the caller.
    const { profile, profileSha } = this.#readProfileLive();
    this.#profile = profile;
    this.#profileSha = profileSha;
    this.#contract = parseContract(readFileSync(this.#contractPath, 'utf8'));
    this.#contractSha = readRawSha256(this.#contractPath);
    reconcileContractWithProfile(this.#contract, profile);
    this.#candidateSha = resolveLiveHead(this.#repoRoot);

    this.current = 'INIT';
    this.#materialized = null; // { input, inputSha } — private, deep-frozen
    this.#authorized = null;
    this.launchStarts = 0;
    this.preflightInvocations = 0;
    this.transitionsTaken = [];
  }

  #contractPath;
  #repoRoot;
  #ledger;
  #profilePath;
  #profile;
  #profileSha;
  #contract;
  #contractSha;
  #candidateSha;
  #materialized;
  #authorized;

  // -- live byte sources ----------------------------------------------------

  #readProfileLive() {
    const raw = readFileSync(this.#profilePath, 'utf8');
    return parseProfile(raw);
  }

  #assertLiveBindings({ expectInputSha = null } = {}) {
    const { profileSha } = this.#readProfileLive();
    if (profileSha !== this.#profileSha) {
      this.stop('profile_sha_drift');
      throw new BrowserAuthorityError('profile_sha_drift');
    }
    const contractSha = readRawSha256(this.#contractPath);
    if (contractSha !== this.#contractSha) {
      this.stop('contract_sha_drift');
      throw new BrowserAuthorityError('contract_sha_drift');
    }
    if (this.#materialized) {
      const recomputedInputSha = sha256Hex(JSON.stringify(this.#materialized.input));
      if (recomputedInputSha !== this.#materialized.inputSha) {
        this.stop('input_sha_drift');
        throw new BrowserAuthorityError('input_sha_drift');
      }
      if (expectInputSha !== null && recomputedInputSha !== expectInputSha) {
        this.stop('input_sha_drift');
        throw new BrowserAuthorityError('input_sha_drift');
      }
    }
    const liveHead = resolveLiveHead(this.#repoRoot);
    if (liveHead !== this.#candidateSha) {
      this.stop('candidate_sha_drift');
      throw new BrowserAuthorityError('candidate_sha_drift');
    }
  }

  // -- private helpers ------------------------------------------------------

  #sensitiveValues() {
    return this.#materialized ? Object.values(this.#materialized.input.values) : [];
  }

  transition(from, to) {
    if (this.current === 'STOPPED') {
      this.#rejectAfterStop('transition');
    }
    const capturedFrom = this.current; // captured BEFORE any mutation
    if (capturedFrom !== from) {
      throw new BrowserAuthorityError('transition_from_mismatch');
    }
    const legal =
      this.#contract.transitions.some((edge) => edge.from === capturedFrom && edge.to === to) ||
      (capturedFrom === 'AUTHORIZED' && to === 'RUNNING') ||
      (capturedFrom === 'RUNNING' && (to === 'FINISHED' || to === 'TEST_RED'));
    if (!legal) {
      throw new BrowserAuthorityError('transition_not_in_contract');
    }
    this.current = to;
    this.transitionsTaken.push({ from: capturedFrom, to });
  }

  #rejectAfterStop(attemptedMethod) {
    this.#ledger.append(
      { kind: 'rejection_after_stop', attempted: attemptedMethod, state: 'STOPPED' },
      this.#sensitiveValues(),
    );
    throw new BrowserAuthorityError('terminal_stop');
  }

  #guardLive(method) {
    if (this.current === 'STOPPED') {
      this.#rejectAfterStop(method);
    }
  }

  #appendRejection(kind, details = {}) {
    this.#ledger.append({ kind, ...details }, this.#sensitiveValues());
  }

  // -- public control surface ----------------------------------------------

  /** Read-only view of the deep-frozen materialized input. */
  materializedInput() {
    return this.#materialized ? this.#materialized.input : null;
  }

  materializedInputSha() {
    return this.#materialized ? this.#materialized.inputSha : null;
  }

  liveContractSha() {
    return readRawSha256(this.#contractPath);
  }

  boundContractSha() {
    return this.#contractSha;
  }

  boundProfileSha() {
    return this.#profileSha;
  }

  liveCandidateSha() {
    return resolveLiveHead(this.#repoRoot);
  }

  materialize(env) {
    this.#guardLive('materialize');
    const { input, inputSha } = materializeInput(this.#contract, env);
    this.#materialized = { input, inputSha };
    return { inputSha };
  }

  /** Exactly one preflight; live profile/contract/candidate re-check. */
  preflight(checks) {
    this.#guardLive('preflight');
    if (this.preflightInvocations > 0) {
      // C: persist the rejection FIRST, then STOPPED.
      this.#appendRejection('rejection', { attempted: 'preflight_repeat', state: this.current });
      this.stop('preflight_already_invoked');
      throw new BrowserAuthorityError('preflight_already_invoked');
    }
    this.preflightInvocations += 1;
    this.#assertLiveBindings();
    this.transition('INIT', 'PREFLIGHTED');
    try {
      if (!Array.isArray(checks)) {
        throw new BrowserAuthorityError('preflight_checks_not_array');
      }
      for (const check of checks) {
        if (check === null || typeof check !== 'object' || check.ok !== true) {
          const category =
            check && typeof check.category === 'string' ? check.category : 'preflight_red';
          this.stop(`preflight_red:${category}`);
          throw new BrowserAuthorityError('preflight_red');
        }
      }
    } catch (error) {
      if (!(error instanceof BrowserAuthorityError) || error.category !== 'preflight_red') {
        this.stop('preflight_exception');
      }
      throw error;
    }
    return { state: this.current, checks: checks.length };
  }

  /** Bind argv discipline; live contract/input/profile/candidate re-checks. */
  authorize({ inputSha, argv }) {
    this.#guardLive('authorize');
    if (!this.#materialized) {
      throw new BrowserAuthorityError('input_not_materialized');
    }
    if (this.#authorized) {
      this.#appendRejection('rejection', { attempted: 'authorize_repeat', state: this.current });
      this.stop('authorize_already_invoked');
      throw new BrowserAuthorityError('authorize_already_invoked');
    }
    // Live re-reads: contract bytes, input bytes, profile bytes, live git
    // HEAD. inputSha is the caller-held expectation that must match both the
    // materialize-time binding and the live recompute.
    this.#assertLiveBindings({ expectInputSha: inputSha });
    assertArgvArray(argv);
    this.transition('PREFLIGHTED', 'AUTHORIZED');
    this.#authorized = {
      argvSha: sha256Hex(JSON.stringify(argv)),
      argvLength: argv.length,
    };
    return { state: this.current, argvLength: this.#authorized.argvLength };
  }

  /**
   * Start the browser authority command AT MOST once. Sentinel first, then
   * RUNNING; only rc==0 AND complete reconciliation reach FINISHED, a real
   * child failure lands TEST_RED, and an executor exception before an actual
   * start lands STOPPED with the TRUE starts count.
   */
  launch(execFileImpl, { argv }) {
    this.#guardLive('launch');
    if (!this.#authorized) {
      throw new BrowserAuthorityError('not_authorized');
    }
    if (this.launchStarts >= 1 || this.#contract.launch.max_starts !== 1) {
      this.#appendRejection('rejection', { attempted: 'launch_repeat', starts: this.launchStarts });
      this.stop('launch_already_invoked');
      throw new BrowserAuthorityError('launch_already_invoked');
    }
    assertArgvArray(argv);
    if (sha256Hex(JSON.stringify(argv)) !== this.#authorized.argvSha) {
      this.stop('argv_drift');
      throw new BrowserAuthorityError('argv_drift');
    }
    // Full live re-check immediately before the single start.
    this.#assertLiveBindings();

    // Start sentinel FIRST, then RUNNING.
    this.launchStarts += 1;
    this.transition('AUTHORIZED', 'RUNNING');
    let childOutcome;
    try {
      // The implementation may return the child result directly OR a Promise
      // that settles when the real process ends — the control plane ALWAYS
      // awaits the real outcome before classifying (B1-R5-R2 closure).
      childOutcome = execFileImpl(argv[0], argv.slice(1));
    } catch (error) {
      // The executor threw without an actual start: revert the sentinel to
      // the TRUE value and land STOPPED (never TEST_RED, never FINISHED).
      if (this.current === 'RUNNING') {
        this.launchStarts -= 1;
        this.current = 'STOPPED';
        this.#ledger.append(
          { kind: 'executor_exception', started: false, starts: this.launchStarts },
          this.#sensitiveValues(),
        );
      }
      throw error;
    }
    if (
      childOutcome === null ||
      typeof childOutcome !== 'object' ||
      typeof childOutcome.then !== 'function'
    ) {
      return this.#classifyChildResult(childOutcome, argv);
    }
    return Promise.resolve(childOutcome)
      .then((result) => this.#classifyChildResult(result, argv))
      .catch((error) => {
        // An asynchronously failing child DID start: real child failure ->
        // TEST_RED (never FINISHED, never VOID, never executor STOPPED).
        if (this.current === 'RUNNING') {
          this.transition('RUNNING', 'TEST_RED');
          this.#ledger.append(
            {
              kind: 'test_red',
              child_rc_zero: false,
              reconciliation_complete: false,
              async_failure: true,
              starts: this.launchStarts,
            },
            this.#sensitiveValues(),
          );
          const wrapped = new BrowserAuthorityError('test_red_async_child_failure');
          wrapped.async_reason = 'child_promise_rejected';
          throw wrapped;
        }
        throw error;
      });
  }

  /** Classify a settled child result: FINISHED only on rc==0 AND complete. */
  #classifyChildResult(result, argv) {
    if (result === null || typeof result !== 'object') {
      // Post-start executor contract breach: truthful starts, VOID.
      this.stop('executor_result_shape');
      throw new BrowserAuthorityError('executor_result_shape');
    }
    const rc = result.rc;
    const complete = Boolean(result.reconciliation && result.reconciliation.complete === true);
    if (rc === 0 && complete) {
      this.transition('RUNNING', 'FINISHED');
      this.#ledger.append(
        { kind: 'finish', argv_count: argv.length, starts: this.launchStarts },
        this.#sensitiveValues(),
      );
      return { outcome: 'FINISHED', rc, reconciliation_complete: true };
    }
    // A started child that failed — or failed to reconcile — is TEST_RED:
    // never FINISHED, never VOID.
    this.transition('RUNNING', 'TEST_RED');
    this.#ledger.append(
      {
        kind: 'test_red',
        child_rc_zero: rc === 0,
        reconciliation_complete: complete,
        starts: this.launchStarts,
      },
      this.#sensitiveValues(),
    );
    return { outcome: 'TEST_RED', rc, reconciliation_complete: complete };
  }

  /** Terminal VOID — reachable from every live state, never left. */
  stop(category) {
    if (this.current === 'STOPPED') {
      return this.current;
    }
    this.current = 'STOPPED';
    this.#ledger.append(
      { kind: 'void', category, started: this.launchStarts },
      this.#sensitiveValues(),
    );
    return this.current;
  }

  /** Terminal seal: terminal evidence cannot exist (nor PASS) without it. */
  seal() {
    if (!['FINISHED', 'TEST_RED', 'STOPPED'].includes(this.current)) {
      throw new BrowserAuthorityError('seal_requires_terminal_state');
    }
    // Full on-disk chain re-verification BEFORE sealing: a tampered history
    // can never be sealed into terminal evidence.
    this.#ledger.verifyChain();
    if (this.#ledger.hasTerminalSeal()) {
      throw new BrowserAuthorityError('seal_already_present');
    }
    this.#ledger.append({ kind: 'terminal_seal', state: this.current }, this.#sensitiveValues());
    return true;
  }

  /**
   * Labels, booleans, categories, counts — requires the terminal seal AND a
   * fully verified on-disk ledger chain: a record tampered after sealing
   * fails the chain recompute and can never yield evidence.
   */
  evidence() {
    this.#ledger.verifyChain();
    if (!this.#ledger.hasTerminalSeal()) {
      throw new BrowserAuthorityError('evidence_unsealed');
    }
    return {
      state: this.current,
      preflight_invocations: this.preflightInvocations,
      launch_starts: this.launchStarts,
      input_materialized: this.#materialized !== null,
      owner_email_label: this.#materialized ? this.#materialized.input.owner_email_label : null,
      input_sha_bound: this.#materialized !== null,
      profile_sha_bound: typeof this.#profileSha === 'string' && this.#profileSha.length === 64,
      contract_sha_bound: typeof this.#contractSha === 'string' && this.#contractSha.length === 64,
      candidate_sha_live_resolved: /^[0-9a-f]{40}$/.test(this.#candidateSha),
      argv_authorized: this.#authorized !== null,
      ledger_sealed: true,
    };
  }
}

function assertArgvArray(argv) {
  if (!Array.isArray(argv) || argv.length === 0 || !argv.every((part) => typeof part === 'string')) {
    throw new BrowserAuthorityError('argv_not_array');
  }
}
