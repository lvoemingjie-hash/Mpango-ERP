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
 *        are never trusted (candidate_sha_drift);
 *      - the working-tree profile bytes must EQUAL the committed blob at
 *        the owning repository's live HEAD (B1-R5-R3: a dirty profile can
 *        never be the binding source — profile_dirty_vs_head);
 *      - the CORS probe travels over a module-PRIVATE native
 *        node:http/node:https OPTIONS transport: globalThis.fetch \— ambient
 *        or otherwise) is never referenced, so launcher-side substitution of
 *        the ambient fetch cannot forge CORS authority (B1-R6-R1);
 *      - ONE canonical repository root is derived from the profile's own
 *        location; the caller repoRoot must realpath-match it and every git
 *        subprocess runs with all GIT_* variables stripped
 *        CASE-INSENSITIVELY (B1-R5-R4/R4-R1: cross-repo candidate
 *        substitution and GIT_* hijacking in ANY letter case are refused —
 *        repo_root_mismatch).
 *      The B1-R5 self-comparison helper is gone; every binding is a live
 *      byte re-read plus a committed-byte proof.
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

import { execFileSync, execFile } from 'node:child_process';
import { createHash } from 'node:crypto';
import { closeSync, existsSync, fsyncSync, openSync, readFileSync, realpathSync, writeSync } from 'node:fs';
import { dirname, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

export const CONTROL_PLANE_SCHEMA = 'j1h2c/browser-authority-contract/1';
export const PROFILE_SCHEMA = 'j1h2c/browser-authority-profile/1';
export const CORS_PROBE_RESULT_SCHEMA = 'j1h2c/cors-probe-result/1';
export const AUTHORITY_CHILD_RESULT_SCHEMA = 'j1h2c/browser-authority-child-result/1';
export const AUTHORITY_CHILD_INPUT_SCHEMA = 'j1h2c/browser-authority-child-input/1';
const GENESIS_SHA = '0'.repeat(64);
const AUTHORITY_CHILD_TIMEOUT_MS = 30000;
const AUTHORITY_CAPABILITY_BRAND = Symbol('browser-authority-capability');
let authorityCapabilityIssued = false;

/**
 * Mandatory CORS preflight probe (B1-R6): the browser Origin is derived
 * EXCLUSIVELY from the bound base_url, the preflight target EXCLUSIVELY
 * from the bound api_base_url, and a side-effect-free OPTIONS declaring the
 * POST + content-type must be answered 2xx with
 * Access-Control-Allow-Origin EXACTLY equal to that Origin. Launchers can
 * neither skip the probe nor substitute an arbitrary ok=true check.
 */
export const CORS_PREFLIGHT_PATH = '/client/auth/forgot-password';
export const CORS_PROBE_TIMEOUT_MS = 10000;

export function deriveBrowserOrigin(baseUrl) {
  let parsed;
  try {
    parsed = new URL(baseUrl);
  } catch {
    throw new BrowserAuthorityError('cors_origin_invalid');
  }
  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    throw new BrowserAuthorityError('cors_origin_invalid');
  }
  return parsed.origin;
}

export function deriveCorsTarget(apiBaseUrl) {
  let target;
  try {
    target = new URL(CORS_PREFLIGHT_PATH, apiBaseUrl);
  } catch {
    throw new BrowserAuthorityError('cors_target_invalid');
  }
  if (target.pathname !== CORS_PREFLIGHT_PATH) {
    throw new BrowserAuthorityError('cors_target_invalid');
  }
  return target.toString();
}

/**
 * B1-R6-R2: the canonical CORS probe HELPER path — a sibling file executed
 * by a FRESH node child (fixed process.execPath, argv array, sanitized
 * environment). The authoritative probe never runs inside the launcher's
 * mutable JS process: node:http/node:https request bindings,
 * globalThis.fetch and syncBuiltinESMExports in that process cannot touch
 * the pristine child (MUTABLE_NODE_BUILTIN_TRANSPORT closure).
 */
export function canonicalCorsHelperPath(moduleFile = fileURLToPath(import.meta.url)) {
  return join(dirname(moduleFile), 'browser-authority-cors-probe-helper.mjs');
}

export function canonicalAuthorityEntrypointPath(moduleFile = fileURLToPath(import.meta.url)) {
  return join(dirname(moduleFile), 'browser-authority-entrypoint.mjs');
}

export function canonicalAuthorityChildPath(moduleFile = fileURLToPath(import.meta.url)) {
  return join(dirname(moduleFile), 'browser-authority-child.mjs');
}

export function canonicalAuthorityChildArgv(moduleFile = fileURLToPath(import.meta.url)) {
  return [process.execPath, canonicalAuthorityChildPath(moduleFile)];
}

function exactKeys(value, keys) {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) return false;
  const actual = Object.keys(value).sort();
  const expected = [...keys].sort();
  return actual.length === expected.length && actual.every((key, index) => key === expected[index]);
}

function resolveMainPath(raw) {
  if (typeof raw !== 'string' || raw.length === 0 || raw.startsWith('-')) return null;
  return resolve(process.cwd(), raw);
}

function originalCommandLine() {
  try {
    const commandLine = process.report?.getReport?.().header?.commandLine;
    return Array.isArray(commandLine) ? commandLine : [];
  } catch {
    return [];
  }
}

function sameRealFile(a, b) {
  try {
    return realpathSync(a).toLowerCase() === realpathSync(b).toLowerCase();
  } catch {
    return false;
  }
}

function assertNoProcessInjection() {
  if (process.execArgv.length > 0) {
    throw new BrowserAuthorityError('execargv_injection_detected');
  }
  for (const arg of process.execArgv) {
    const lower = arg.toLowerCase();
    if (
      lower === '-r' ||
      lower.startsWith('-r') ||
      lower.startsWith('-e') ||
      lower === '--require' ||
      lower.startsWith('--require=') ||
      lower === '--import' ||
      lower.startsWith('--import=') ||
      lower === '--loader' ||
      lower.startsWith('--loader=') ||
      lower === '--experimental-loader' ||
      lower.startsWith('--experimental-loader=') ||
      lower === '--eval' ||
      lower.startsWith('--eval=') ||
      lower === '--input-type' ||
      lower.startsWith('--input-type=')
    ) {
      throw new BrowserAuthorityError('execargv_injection_detected');
    }
  }
  for (const key of Object.keys(process.env)) {
    const upper = key.toUpperCase();
    if (upper === 'NODE_OPTIONS' || upper === 'NODE_PATH' || upper.startsWith('GIT_')) {
      throw new BrowserAuthorityError('env_injection_detected');
    }
  }
}

export function assertDirectAuthorityEntrypointProcess(moduleFile = fileURLToPath(import.meta.url)) {
  const entrypointPath = canonicalAuthorityEntrypointPath(moduleFile);
  const originalMainPath = resolveMainPath(originalCommandLine()[1]);
  const argvMainPath = resolveMainPath(process.argv[1]);
  if (!originalMainPath || !sameRealFile(originalMainPath, entrypointPath)) {
    throw new BrowserAuthorityError('not_direct_entrypoint');
  }
  if (!argvMainPath || !sameRealFile(argvMainPath, entrypointPath)) {
    throw new BrowserAuthorityError('argv_entrypoint_drift');
  }
  assertNoProcessInjection();
  return true;
}

/**
 * Committed-blob bytes for ANY tracked path at the owning repository's live
 * HEAD (git cat-file blob HEAD:<rel>, argv array, GIT_*-stripped env).
 * Untracked or dirty paths fail closed at the comparison site.
 */
function readCommittedBytesViaGit(path) {
  try {
    const toplevel = execFileSync('git', ['-C', dirname(path), 'rev-parse', '--show-toplevel'], {
      stdio: ['ignore', 'pipe', 'ignore'],
      env: gitEnv(),
    })
      .toString('utf8')
      .trim();
    const rel = relative(toplevel, path).split(sep).join('/');
    return execFileSync('git', ['-C', toplevel, 'cat-file', 'blob', `HEAD:${rel}`], {
      stdio: ['ignore', 'pipe', 'ignore'],
      env: gitEnv(),
    });
  } catch {
    throw new BrowserAuthorityError('cors_helper_dirty_vs_head');
  }
}

function readCommittedBytesGeneric(path) {
  const toplevel = execFileSync('git', ['-C', dirname(path), 'rev-parse', '--show-toplevel'], {
    stdio: ['ignore', 'pipe', 'ignore'],
    env: gitEnv(),
  })
    .toString('utf8')
    .trim();
  const rel = relative(toplevel, path).split(sep).join('/');
  return execFileSync('git', ['-C', toplevel, 'cat-file', 'blob', `HEAD:${rel}`], {
    stdio: ['ignore', 'pipe', 'ignore'],
    env: gitEnv(),
  });
}

function assertPathEqualsHeadBlob(path) {
  try {
    if (!readCommittedBytesGeneric(path).equals(readFileSync(path))) {
      throw new BrowserAuthorityError('working_tree_dirty_vs_head');
    }
  } catch (error) {
    if (error instanceof BrowserAuthorityError) throw error;
    throw new BrowserAuthorityError('working_tree_dirty_vs_head');
  }
}

/**
 * The probe child's environment: every NODE_* and GIT_* variable is
 * STRIPPED — NODE_OPTIONS/NODE_PATH/preload entries cannot inject loaders
 * into the pristine probe process, GIT_* cannot hijack repository identity.
 */
export function probeChildEnv() {
  const env = {};
  for (const [key, value] of Object.entries(process.env)) {
    const upper = key.toUpperCase();
    if (!upper.startsWith('NODE_') && !upper.startsWith('GIT_')) env[key] = value;
  }
  return env;
}

export function parseCorsProbePayload(payload) {
  const keys = ['schema', 'ok', 'category', 'status_2xx', 'allow_origin_present', 'allow_origin_exact'];
  if (!exactKeys(payload, keys) || payload.schema !== CORS_PROBE_RESULT_SCHEMA) {
    throw new BrowserAuthorityError('cors_probe_payload_invalid');
  }
  if (
    typeof payload.ok !== 'boolean' ||
    typeof payload.category !== 'string' ||
    typeof payload.status_2xx !== 'boolean' ||
    typeof payload.allow_origin_present !== 'boolean' ||
    typeof payload.allow_origin_exact !== 'boolean'
  ) {
    throw new BrowserAuthorityError('cors_probe_payload_invalid');
  }
  const knownCategories = new Set([
    'cors_probe_passed',
    'cors_allow_origin_mismatch',
    'cors_probe_http_error',
    'cors_probe_timeout',
    'cors_probe_no_response',
  ]);
  if (!knownCategories.has(payload.category)) {
    throw new BrowserAuthorityError('cors_probe_payload_invalid');
  }
  const exactPass =
    payload.status_2xx === true &&
    payload.allow_origin_present === true &&
    payload.allow_origin_exact === true;
  if (payload.ok === true && (payload.category !== 'cors_probe_passed' || !exactPass)) {
    throw new BrowserAuthorityError('cors_probe_payload_invalid');
  }
  if (payload.ok === false && (payload.category === 'cors_probe_passed' || exactPass)) {
    throw new BrowserAuthorityError('cors_probe_payload_invalid');
  }
  return payload;
}

export function parseAuthorityChildStdout(stdout, { pid, exitCode }) {
  let payload;
  try {
    const text = String(stdout).trim();
    if (text.length === 0 || text.includes('\n')) {
      throw new Error('invalid stdout');
    }
    payload = JSON.parse(text);
  } catch {
    throw new BrowserAuthorityError('authority_child_stdout_unparsable');
  }
  if (
    !exactKeys(payload, ['schema', 'pid', 'exit', 'reconciliation']) ||
    payload.schema !== AUTHORITY_CHILD_RESULT_SCHEMA ||
    !Number.isInteger(payload.pid) ||
    payload.pid <= 0 ||
    !Number.isInteger(payload.exit) ||
    payload.pid !== pid ||
    payload.exit !== exitCode ||
    !exactKeys(payload.reconciliation, ['complete']) ||
    typeof payload.reconciliation.complete !== 'boolean'
  ) {
    throw new BrowserAuthorityError('authority_child_result_shape');
  }
  return {
    rc: payload.exit,
    pid: payload.pid,
    real_child: true,
    reconciliation: { complete: payload.reconciliation.complete },
  };
}

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
 * Git subprocess environment: every GIT_* variable is STRIPPED. Repository
 * hijacking via GIT_DIR / GIT_WORK_TREE / GIT_INDEX_FILE / GIT_OBJECT_DIRECTORY
 * injections can never redirect a git subprocess away from the canonical
 * repository (B1-R5-R4, R24).
 */
export function gitEnv() {
  const env = {};
  for (const [key, value] of Object.entries(process.env)) {
    // Case-INSENSITIVE: on Windows the environment block is case-insensitive,
    // so a lowercase `git_dir` would still hijack git.exe if only the exact
    // `GIT_` spelling were filtered.
    if (!key.toUpperCase().startsWith('GIT_')) env[key] = value;
  }
  return env;
}

function gitOutput(args, cwd) {
  return execFileSync('git', args, {
    cwd,
    stdio: ['ignore', 'pipe', 'ignore'],
    env: gitEnv(),
  })
    .toString('utf8')
    .trim();
}

function sameRealDirectory(a, b) {
  try {
    return realpathSync(a).toLowerCase() === realpathSync(b).toLowerCase();
  } catch {
    return false;
  }
}

/**
 * The SINGLE canonical repository root, derived from the module/profile
 * location itself (never from a caller).
 */
export function canonicalRepoRoot(profilePath = canonicalProfilePath()) {
  return gitOutput(['rev-parse', '--show-toplevel'], dirname(profilePath));
}

/**
 * LIVE candidate resolution: `git -C <repoRoot> rev-parse HEAD` via an argv
 * array with a GIT_*-stripped environment. No caller string is ever trusted
 * as the candidate.
 */
export function resolveLiveHead(repoRoot) {
  try {
    const out = execFileSync('git', ['-C', repoRoot, 'rev-parse', 'HEAD'], {
      stdio: ['ignore', 'pipe', 'ignore'],
      env: gitEnv(),
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

/**
 * Committed-blob binding: reads the profile's bytes AS COMMITTED at the
 * owning repository's live HEAD (`git cat-file blob HEAD:<relpath>`, argv
 * array). A working-tree profile that differs from its HEAD blob — or that
 * is not tracked at HEAD — is a dirty profile and fails closed.
 */
export function readProfileCommittedBytes(profilePath) {
  try {
    const toplevel = gitOutput(['rev-parse', '--show-toplevel'], dirname(profilePath));
    const rel = relative(toplevel, profilePath).split(sep).join('/');
    return execFileSync('git', ['-C', toplevel, 'cat-file', 'blob', `HEAD:${rel}`], {
      stdio: ['ignore', 'pipe', 'ignore'],
      env: gitEnv(),
    });
  } catch {
    throw new BrowserAuthorityError('profile_dirty_vs_head');
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
   *   repoRoot      MUST resolve (realpath) to the SINGLE canonical
   *                 repository root derived from the profile's own location;
   *                 any other repository is refused (repo_root_mismatch,
   *                 B1-R5-R4 cross-repo candidate substitution closure)
   *   ledger        DurableJsonlLedger
   *   authority     PUBLIC authority elevation is forbidden. Library-import
   *                 ControlPlanes can exercise all functional paths for
   *                 testing but CANNOT mint authority PASS, terminal seal, or
   *                 merge-worthy evidence (B1-R6-R3). The direct process
   *                 entrypoint is the production trust boundary and does not
   *                 expose an in-process authority token.
   * The protected profile is ALWAYS the canonical module-relative
   * browser-authority-profile.json — there is no profilePath override: a
   * caller-supplied weaker profile cannot exist by construction. Profile
   * committed-blob verification and candidate HEAD resolution share the ONE
   * canonical toplevel.
   */
  constructor(options) {
    const { contractPath, repoRoot, ledger } = options || {};
    if (typeof contractPath !== 'string' || contractPath.length === 0) {
      throw new BrowserAuthorityError('contract_path_missing');
    }
    if (Object.prototype.hasOwnProperty.call(options || {}, 'authority') && options.authority !== false) {
      throw new BrowserAuthorityError('authority_mode_required');
    }
    if (typeof repoRoot !== 'string' || repoRoot.length === 0) {
      throw new BrowserAuthorityError('repo_root_missing');
    }
    if (!(ledger instanceof DurableJsonlLedger)) {
      throw new BrowserAuthorityError('ledger_required');
    }
    const canonicalRoot = canonicalRepoRoot(canonicalProfilePath());
    if (!sameRealDirectory(repoRoot, canonicalRoot)) {
      // Cross-repo candidate substitution: a foreign repository (whatever
      // its HEAD) can never become the candidate source.
      throw new BrowserAuthorityError('repo_root_mismatch');
    }
    this.#contractPath = contractPath;
    this.#repoRoot = canonicalRoot;
    this.#ledger = ledger;
    this.#authority = false;
    this.#profilePath = canonicalProfilePath();

    // Initial binding — all four from LIVE sources, none from the caller.
    // The profile must additionally prove it equals its committed blob at
    // the owning repository's live HEAD: a dirty working tree can never be
    // the binding source (B1-R5-R3).
    const { profile, profileSha } = this.#readProfileLive();
    const committed = readProfileCommittedBytes(this.#profilePath);
    if (sha256Hex(committed) !== profileSha) {
      throw new BrowserAuthorityError('profile_dirty_vs_head');
    }
    this.#profile = profile;
    this.#profileSha = profileSha;
    this.#contract = parseContract(readFileSync(this.#contractPath, 'utf8'));
    this.#contractSha = readRawSha256(this.#contractPath);
    reconcileContractWithProfile(this.#contract, profile);
    this.#candidateSha = resolveLiveHead(this.#repoRoot);

    this.current = 'INIT';
    this.#materialized = null; // { input, inputSha } — private, deep-frozen
    this.#authorized = null;
    this.#cwdSha = null;
    this.#childResult = null;
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
  #cwdSha;
  #childResult;
  #authority;
  #corsProbeInvocations = 0;
  #corsProbePassed = false;

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
    // The working-tree profile must still equal its committed blob at the
    // owning repository's live HEAD (dirty profile => VOID, always).
    const committed = readProfileCommittedBytes(this.#profilePath);
    if (sha256Hex(committed) !== profileSha) {
      this.stop('profile_dirty_vs_head');
      throw new BrowserAuthorityError('profile_dirty_vs_head');
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

  assertLiveBindingSurface() {
    this.#assertLiveBindings();
    return true;
  }

  authorityBindingFacts() {
    return {
      state: this.current,
      candidate_sha_bound: /^[0-9a-f]{40}$/.test(this.#candidateSha),
      profile_sha_bound: typeof this.#profileSha === 'string' && this.#profileSha.length === 64,
      contract_sha_bound: typeof this.#contractSha === 'string' && this.#contractSha.length === 64,
      input_sha_bound: this.#materialized !== null && typeof this.#materialized.inputSha === 'string',
      argv_sha_bound: this.#authorized !== null && typeof this.#authorized.argvSha === 'string',
      cwd_sha_bound: typeof this.#cwdSha === 'string' && this.#cwdSha.length === 64,
      child_real_process_observed: this.#childResult !== null && this.#childResult.real_child === true,
      child_pid: this.#childResult ? this.#childResult.pid : null,
      child_exit_code: this.#childResult ? this.#childResult.exit : null,
    };
  }

  materialize(env) {
    this.#guardLive('materialize');
    const { input, inputSha } = materializeInput(this.#contract, env);
    this.#materialized = { input, inputSha };
    return { inputSha };
  }

  /**
   * B1-R6: the runner-OWNED CORS preflight probe. Exactly once, before
   * preflight; the Origin/target are derived from the BOUND materialized
   * input and a side-effect-free OPTIONS declaring POST + content-type must
   * be answered 2xx with Access-Control-Allow-Origin EXACTLY equal to the
   * derived Origin. Any failure lands STOPPED before authorize with
   * launchStarts untouched (0). The caller cannot skip it, cannot fake it
   * with an ok=true boolean, and cannot point it anywhere but the bound
   * origins — the request construction and pass criteria live HERE.
   */
  async corsPreflightProbe() {
    this.#guardLive('cors_preflight_probe');
    if (this.#corsProbeInvocations > 0) {
      this.#appendRejection('rejection', { attempted: 'cors_probe_repeat', state: this.current });
      this.stop('cors_probe_already_invoked');
      throw new BrowserAuthorityError('cors_probe_already_invoked');
    }
    this.#corsProbeInvocations += 1;
    if (!this.#materialized) {
      throw new BrowserAuthorityError('input_not_materialized');
    }
    this.#assertLiveBindings();
    const origin = deriveBrowserOrigin(this.#materialized.input.values.base_url);
    const target = deriveCorsTarget(this.#materialized.input.values.api_base_url);
    // B1-R6-R2: the probe runs in a FRESH node child (fixed
    // process.execPath, argv array, sanitized environment). The helper's
    // working-tree bytes must equal its committed blob at the owning
    // repository's live HEAD, the probe input travels via private stdin,
    // and the classification comes back as categories/booleans on stdout.
    // The launcher process's mutable builtins are irrelevant here.
    const helperPath = canonicalCorsHelperPath();
    const helperWorkingSha = sha256Hex(readFileSync(helperPath));
    const helperCommittedSha = sha256Hex(readCommittedBytesViaGit(helperPath));
    if (helperWorkingSha !== helperCommittedSha) {
      this.stop('cors_helper_dirty_vs_head');
      throw new BrowserAuthorityError('cors_helper_dirty_vs_head');
    }
    const childInput = JSON.stringify({
      origin,
      target,
      timeoutMs: CORS_PROBE_TIMEOUT_MS,
    });
    let payload;
    try {
      // Async execFile: the parent's event loop stays free so the fixture
      // server can answer the child's request (no execFileSync deadlock).
      const childOut = await new Promise((resolve, reject) => {
        const child = execFile(
          process.execPath,
          [helperPath],
          {
            env: probeChildEnv(),
            stdio: ['pipe', 'pipe', 'pipe'],
            timeout: CORS_PROBE_TIMEOUT_MS + 5000,
            windowsHide: true,
          },
          (error, stdout) => {
            if (error) {
              error.stdout_text = typeof stdout === 'string' ? stdout : '';
              reject(error);
            } else {
              resolve(stdout);
            }
          },
        );
        child.stdin.write(childInput);
        child.stdin.end();
      });
      payload = parseCorsProbePayload(JSON.parse(childOut));
    } catch {
      // Child crash, kill (runaway), or unparseable output: fail closed.
      this.stop('cors_probe_no_response');
      throw new BrowserAuthorityError('cors_probe_no_response');
    }
    if (process.env.R6R2_DEBUG) console.error('DEBUG probe payload:', JSON.stringify(payload));
    const status2xx = payload.status_2xx === true;
    const allowOriginPresent = payload.allow_origin_present === true;
    const allowOriginExact = payload.allow_origin_exact === true;
    const KNOWN_CATEGORIES = new Set([
      'cors_allow_origin_mismatch',
      'cors_probe_http_error',
      'cors_probe_timeout',
      'cors_probe_no_response',
      'cors_probe_payload_invalid',
    ]);
    if (payload.ok !== true) {
      const category =
        typeof payload.category === 'string' && KNOWN_CATEGORIES.has(payload.category)
          ? payload.category
          : 'cors_probe_no_response';
      this.stop(category);
      this.#ledger.append(
        {
          kind: 'cors_preflight',
          ok: false,
          status_2xx: status2xx,
          allow_origin_present: allowOriginPresent,
          allow_origin_exact: false,
        },
        this.#sensitiveValues(),
      );
      throw new BrowserAuthorityError(category);
    }
    this.#corsProbePassed = true;
    this.#ledger.append(
      {
        kind: 'cors_preflight',
        ok: true,
        status_2xx: true,
        allow_origin_present: true,
        allow_origin_exact: true,
      },
      this.#sensitiveValues(),
    );
    return { state: this.current, allow_origin_exact: true };
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
    if (!this.#corsProbePassed) {
      // B1-R6: a caller ok=true check can never stand in for the runner-owned
      // probe — omitting or faking it stops the plane before authorize.
      this.#appendRejection('rejection', { attempted: 'preflight_without_cors_probe' });
      this.stop('cors_probe_missing');
      throw new BrowserAuthorityError('cors_probe_missing');
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
  authorize({ inputSha, argv, cwd = this.#repoRoot }) {
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
    if (!sameRealDirectory(cwd, this.#repoRoot)) {
      this.stop('cwd_mismatch');
      throw new BrowserAuthorityError('cwd_mismatch');
    }
    this.transition('PREFLIGHTED', 'AUTHORIZED');
    this.#authorized = {
      argvSha: sha256Hex(JSON.stringify(argv)),
      argvLength: argv.length,
    };
    this.#cwdSha = sha256Hex(realpathSync(cwd));
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

  launchAuthorityChild({ argv, cwd = this.#repoRoot }) {
    const canonicalArgv = canonicalAuthorityChildArgv();
    if (JSON.stringify(argv) !== JSON.stringify(canonicalArgv)) {
      throw new BrowserAuthorityError('authority_child_argv_not_canonical');
    }
    if (!sameRealDirectory(cwd, this.#repoRoot)) {
      throw new BrowserAuthorityError('cwd_mismatch');
    }
    return this.launch(
      (file, args) => this.#execAuthorityChild(file, args, cwd),
      { argv },
    );
  }

  #execAuthorityChild(file, args, cwd) {
    const canonicalArgv = canonicalAuthorityChildArgv();
    if (file !== canonicalArgv[0] || JSON.stringify(args) !== JSON.stringify(canonicalArgv.slice(1))) {
      throw new BrowserAuthorityError('authority_child_argv_not_canonical');
    }
    const childInput = JSON.stringify({
      schema: AUTHORITY_CHILD_INPUT_SCHEMA,
      input_sha: this.#materialized.inputSha,
      cwd_sha: this.#cwdSha,
      values: this.#materialized.input.values,
    });
    return new Promise((resolve, reject) => {
      const child = execFile(
        file,
        args,
        {
          cwd,
          env: probeChildEnv(),
          stdio: ['pipe', 'pipe', 'pipe'],
          timeout: AUTHORITY_CHILD_TIMEOUT_MS,
          windowsHide: true,
        },
        (error, stdout) => {
          const exitCode = error && Number.isInteger(error.code) ? error.code : 0;
          try {
            resolve(parseAuthorityChildStdout(stdout, { pid: child.pid, exitCode }));
          } catch (parseError) {
            reject(parseError);
          }
        },
      );
      child.stdin.write(childInput);
      child.stdin.end();
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
    this.#childResult = {
      pid: Number.isInteger(result.pid) ? result.pid : null,
      exit: Number.isInteger(rc) ? rc : null,
      real_child: result.real_child === true,
    };
    const complete = Boolean(result.reconciliation && result.reconciliation.complete === true);
    if (rc === 0 && complete) {
      this.transition('RUNNING', 'FINISHED');
      this.#ledger.append(
        { kind: 'finish', argv_count: argv.length, starts: this.launchStarts },
        this.#sensitiveValues(),
      );
      return {
        outcome: 'FINISHED',
        rc,
        reconciliation_complete: true,
        child_pid: this.#childResult.pid,
        child_exit_code: this.#childResult.exit,
        real_child: this.#childResult.real_child,
      };
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
    return {
      outcome: 'TEST_RED',
      rc,
      reconciliation_complete: complete,
      child_pid: this.#childResult.pid,
      child_exit_code: this.#childResult.exit,
      real_child: this.#childResult.real_child,
    };
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

  enableAuthorityForEntrypoint(capability) {
    if (!capability || capability[AUTHORITY_CAPABILITY_BRAND] !== true) {
      throw new BrowserAuthorityError('authority_mode_required');
    }
    this.#authority = true;
    return true;
  }

  /** Terminal seal: terminal evidence cannot exist (nor PASS) without it. */
  seal() {
    if (!this.#authority) {
      throw new BrowserAuthorityError('authority_mode_required');
    }
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
   * Labels, booleans, categories, counts — requires authority mode (not
   * exposed through the library constructor), the terminal seal, and a fully
   * verified on-disk ledger chain: a record tampered after sealing fails the
   * chain recompute and can never yield evidence.
   */
  evidence() {
    if (!this.#authority) {
      throw new BrowserAuthorityError('authority_mode_required');
    }
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
      argv_sha_bound: this.#authorized !== null && typeof this.#authorized.argvSha === 'string',
      cwd_sha_bound: typeof this.#cwdSha === 'string' && this.#cwdSha.length === 64,
      child_real_process_observed: this.#childResult !== null && this.#childResult.real_child === true,
      child_pid: this.#childResult ? this.#childResult.pid : null,
      child_exit_code: this.#childResult ? this.#childResult.exit : null,
      cors_probe_invocations: this.#corsProbeInvocations,
      cors_probe_passed: this.#corsProbePassed,
      ledger_sealed: true,
    };
  }
}

export function authorityCriticalPaths(moduleFile = fileURLToPath(import.meta.url)) {
  return [
    canonicalAuthorityEntrypointPath(moduleFile),
    moduleFile,
    canonicalCorsHelperPath(moduleFile),
    canonicalAuthorityChildPath(moduleFile),
    canonicalProfilePath(moduleFile),
  ];
}

export function assertAuthorityCriticalPathsClean(moduleFile = fileURLToPath(import.meta.url)) {
  for (const path of authorityCriticalPaths(moduleFile)) {
    assertPathEqualsHeadBlob(path);
  }
  return true;
}

function mintAuthorityCapability(control) {
  if (authorityCapabilityIssued) {
    throw new BrowserAuthorityError('authority_capability_already_used');
  }
  control.assertLiveBindingSurface();
  const facts = control.authorityBindingFacts();
  if (!['FINISHED', 'TEST_RED'].includes(facts.state)) {
    throw new BrowserAuthorityError('seal_requires_terminal_state');
  }
  if (
    facts.candidate_sha_bound !== true ||
    facts.profile_sha_bound !== true ||
    facts.contract_sha_bound !== true ||
    facts.input_sha_bound !== true ||
    facts.argv_sha_bound !== true ||
    facts.cwd_sha_bound !== true ||
    facts.child_real_process_observed !== true
  ) {
    throw new BrowserAuthorityError('authority_bindings_incomplete');
  }
  assertDirectAuthorityEntrypointProcess();
  assertAuthorityCriticalPathsClean();
  authorityCapabilityIssued = true;
  return Object.freeze({ [AUTHORITY_CAPABILITY_BRAND]: true });
}

export function sealAuthorityEvidence(control) {
  if (!(control instanceof ControlPlane)) {
    throw new BrowserAuthorityError('control_plane_required');
  }
  const capability = mintAuthorityCapability(control);
  control.enableAuthorityForEntrypoint(capability);
  control.seal();
  return control.evidence();
}

function assertArgvArray(argv) {
  if (!Array.isArray(argv) || argv.length === 0 || !argv.every((part) => typeof part === 'string')) {
    throw new BrowserAuthorityError('argv_not_array');
  }
}
