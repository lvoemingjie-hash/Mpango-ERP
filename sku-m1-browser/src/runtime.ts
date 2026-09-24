/**
 * DC-12R1-MVP-L1-SKU-R0-M1-R1-B4 — browser authority mode control plane.
 *
 * The harness supports EXACTLY two mutually exclusive runtime modes:
 *
 *   AUTHOR_DIAGNOSTIC     selected by B3_AUTHOR_DIAGNOSTIC=1
 *   INDEPENDENT_AUTHORITY selected by B4_INDEPENDENT_AUTHORITY=1
 *
 * Exactly one mode variable must equal the literal string '1'.
 *
 *   neither set                      -> fail closed before browser launch
 *   both set                         -> fail closed before browser launch
 *   any other (non-'1') value        -> fail closed (unknown mode)
 *   unknown mode label in evidence   -> fail closed
 *
 * Once an invocation has started, the selected mode is FROZEN. The frozen mode
 * is taken from the on-disk live execution contract first and from the
 * environment only while no contract exists, so no environment variable can
 * relabel or override the recorded mode after invocation start.
 */
import * as fs from 'fs';
import * as path from 'path';

export const RESULTS_DIR = path.resolve(__dirname, '..', 'results');
export const RECONCILIATION_IN = path.join(RESULTS_DIR, 'reconciliation-in.jsonl');
export const RECONCILIATION_OUT = path.join(RESULTS_DIR, 'reconciliation.json');
export const PLAYWRIGHT_REPORT = path.join(RESULTS_DIR, 'playwright-report.json');
export const PREFLIGHT_VERDICT = path.join(RESULTS_DIR, 'preflight-verdict.json');
export const INVOCATION_LEDGER = path.join(RESULTS_DIR, 'invocation-ledger.jsonl');
export const AUTHORITY_REPORT = path.join(RESULTS_DIR, 'authority-report.json');
export const LIVE_EXECUTION_CONTRACT = path.join(RESULTS_DIR, 'live-execution-contract.json');
export const TEST_ARTIFACTS_DIR = path.join(RESULTS_DIR, 'test-artifacts');
export const MAILDIR = path.join(RESULTS_DIR, 'maildir');

export const AUTHOR_DIAGNOSTIC_ENV = 'B3_AUTHOR_DIAGNOSTIC';
export const INDEPENDENT_AUTHORITY_ENV = 'B4_INDEPENDENT_AUTHORITY';

export type RuntimeMode = 'AUTHOR_DIAGNOSTIC' | 'INDEPENDENT_AUTHORITY';
export const AUTHOR_DIAGNOSTIC = 'AUTHOR_DIAGNOSTIC' as const;
export const INDEPENDENT_AUTHORITY = 'INDEPENDENT_AUTHORITY' as const;
export const RUNTIME_MODES: RuntimeMode[] = [AUTHOR_DIAGNOSTIC, INDEPENDENT_AUTHORITY];

export const EXPECTED_EXECUTION_COUNT = 4;
export const WORKERS = 1;
export const RETRIES = 0;

/** Single-occurrence sentinels: the control plane, the ledger and the
 *  validator all key off exactly these literals. */
export const CODE_BOTH_MODES_SET = 'both_modes_set' as const;
export const CODE_MODE_UNSET = 'mode_unset' as const;
export const CODE_MODE_VALUE_UNKNOWN = 'mode_value_unknown' as const;
export const CODE_MODE_LABEL_UNKNOWN = 'mode_label_unknown' as const;
export const REFUSAL_SECOND_INVOCATION = 'second_invocation_refused' as const;
export const REFUSAL_CROSS_MODE = 'cross_mode_invocation_refused' as const;
export const REFUSAL_CANDIDATE_SHA_MISMATCH = 'candidate_sha_mismatch_void' as const;

export type ModeResolutionCode =
  | typeof CODE_BOTH_MODES_SET
  | typeof CODE_MODE_UNSET
  | typeof CODE_MODE_VALUE_UNKNOWN
  | typeof CODE_MODE_LABEL_UNKNOWN
  | typeof REFUSAL_SECOND_INVOCATION
  | typeof REFUSAL_CROSS_MODE
  | typeof REFUSAL_CANDIDATE_SHA_MISMATCH;

export class ModeResolutionError extends Error {
  readonly code: ModeResolutionCode;

  constructor(code: ModeResolutionCode, detail: string) {
    super(`[${code}] ${detail}`);
    this.code = code;
    this.name = 'ModeResolutionError';
  }
}

export type InvocationEvent = 'start' | 'end' | 'refused';

export interface InvocationLedgerRecord {
  schema: 'sku-m1-browser/invocation-ledger/1';
  event: InvocationEvent;
  mode: RuntimeMode;
  candidate_sha: string;
  invocation_count: number;
  status: string;
  workers: number;
  retries: number;
  expected_node_count: number;
  observed_node_count: number;
  reason?: string;
}

export interface LiveExecutionContract {
  schema: 'sku-m1-browser/live-execution-contract/1';
  execution_mode: RuntimeMode;
  candidate_sha: string;
  workers: number;
  retries: number;
  expected_execution_count: number;
  frozen_at_invocation_start: true;
}

interface FrozenInvocation {
  mode: RuntimeMode;
  candidateSha: string;
  workers: number;
  retries: number;
}

let frozen: FrozenInvocation | null = null;

export function assertKnownMode(mode: unknown, source: string): RuntimeMode {
  if (mode === AUTHOR_DIAGNOSTIC || mode === INDEPENDENT_AUTHORITY) {
    return mode;
  }
  throw new ModeResolutionError(
    CODE_MODE_LABEL_UNKNOWN,
    `${source} recorded unknown execution mode '${String(mode)}'`,
  );
}

/**
 * Resolve the single selected runtime mode from an environment block.
 * Throws ModeResolutionError for every non-conforming combination.
 */
export function resolveRuntimeMode(env: NodeJS.ProcessEnv = process.env): RuntimeMode {
  const author = (env[AUTHOR_DIAGNOSTIC_ENV] ?? '').trim();
  const independent = (env[INDEPENDENT_AUTHORITY_ENV] ?? '').trim();
  const authorSet = author === '1';
  const independentSet = independent === '1';
  if (authorSet && independentSet) {
    throw new ModeResolutionError(
      CODE_BOTH_MODES_SET,
      `${AUTHOR_DIAGNOSTIC_ENV}=1 and ${INDEPENDENT_AUTHORITY_ENV}=1 are mutually exclusive`,
    );
  }
  if (author.length > 0 && !authorSet) {
    throw new ModeResolutionError(
      CODE_MODE_VALUE_UNKNOWN,
      `${AUTHOR_DIAGNOSTIC_ENV} must be exactly '1' (got '${author}')`,
    );
  }
  if (independent.length > 0 && !independentSet) {
    throw new ModeResolutionError(
      CODE_MODE_VALUE_UNKNOWN,
      `${INDEPENDENT_AUTHORITY_ENV} must be exactly '1' (got '${independent}')`,
    );
  }
  if (authorSet) return AUTHOR_DIAGNOSTIC;
  if (independentSet) return INDEPENDENT_AUTHORITY;
  throw new ModeResolutionError(
    CODE_MODE_UNSET,
    `exactly one of ${AUTHOR_DIAGNOSTIC_ENV}=1 / ${INDEPENDENT_AUTHORITY_ENV}=1 is required for browser runtime execution`,
  );
}

/** Fail-closed guard used by the control plane before any browser launch. */
export function requireRuntimeMode(): RuntimeMode {
  return resolveRuntimeMode();
}

export function writeLiveExecutionContract(
  mode: RuntimeMode,
  candidateSha: string,
  workers: number,
  retries: number,
): LiveExecutionContract {
  assertKnownMode(mode, 'writeLiveExecutionContract');
  const contract: LiveExecutionContract = {
    schema: 'sku-m1-browser/live-execution-contract/1',
    execution_mode: mode,
    candidate_sha: candidateSha,
    workers,
    retries,
    expected_execution_count: EXPECTED_EXECUTION_COUNT,
    frozen_at_invocation_start: true,
  };
  fs.mkdirSync(RESULTS_DIR, { recursive: true });
  fs.writeFileSync(LIVE_EXECUTION_CONTRACT, JSON.stringify(contract, null, 2));
  frozen = { mode, candidateSha, workers, retries };
  return contract;
}

export function readLiveExecutionContract(): LiveExecutionContract | null {
  if (!fs.existsSync(LIVE_EXECUTION_CONTRACT)) return null;
  const parsed = JSON.parse(fs.readFileSync(LIVE_EXECUTION_CONTRACT, 'utf-8')) as LiveExecutionContract;
  assertKnownMode(parsed.execution_mode, LIVE_EXECUTION_CONTRACT);
  return parsed;
}

/**
 * The mode RECORDED for the current invocation.
 *
 * Precedence: in-process frozen value -> on-disk live execution contract ->
 * environment. The environment is consulted ONLY while no invocation has been
 * recorded, so no environment variable can override the recorded mode once the
 * invocation has started.
 */
export function recordedMode(): RuntimeMode {
  if (frozen) return frozen.mode;
  const contract = readLiveExecutionContract();
  if (contract) return assertKnownMode(contract.execution_mode, LIVE_EXECUTION_CONTRACT);
  return resolveRuntimeMode();
}

export function recordedCandidateSha(): string {
  if (frozen) return frozen.candidateSha;
  const contract = readLiveExecutionContract();
  if (contract) return contract.candidate_sha;
  throw new ModeResolutionError(
    CODE_MODE_UNSET,
    'no invocation has been recorded; the runtime mode is not frozen',
  );
}

export function hasRecordedInvocation(): boolean {
  return frozen !== null || fs.existsSync(LIVE_EXECUTION_CONTRACT);
}

function appendLedger(record: InvocationLedgerRecord): void {
  fs.mkdirSync(RESULTS_DIR, { recursive: true });
  fs.appendFileSync(INVOCATION_LEDGER, JSON.stringify(record) + '\n');
}

/** Append-only ledger reader; every record must carry a known mode label. */
export function readInvocationLedger(): InvocationLedgerRecord[] {
  if (!fs.existsSync(INVOCATION_LEDGER)) return [];
  return fs
    .readFileSync(INVOCATION_LEDGER, 'utf-8')
    .split('\n')
    .filter(Boolean)
    .map((line) => {
      const record = JSON.parse(line) as InvocationLedgerRecord;
      assertKnownMode(record.mode, INVOCATION_LEDGER);
      return record;
    });
}

function ledgerRecord(
  event: InvocationEvent,
  mode: RuntimeMode,
  candidateSha: string,
  invocationCount: number,
  status: string,
  workers: number,
  retries: number,
  observedNodeCount: number,
  reason?: string,
): InvocationLedgerRecord {
  return {
    schema: 'sku-m1-browser/invocation-ledger/1',
    event,
    mode,
    candidate_sha: candidateSha,
    invocation_count: invocationCount,
    status,
    workers,
    retries,
    expected_node_count: EXPECTED_EXECUTION_COUNT,
    observed_node_count: observedNodeCount,
    ...(reason === undefined ? {} : { reason }),
  };
}

/**
 * Start exactly one runtime invocation for the selected mode.
 *
 * Refusals (each appended to the append-only ledger before throwing):
 *   REFUSAL_CANDIDATE_SHA_MISMATCH   ledger holds evidence for another candidate
 *   REFUSAL_CROSS_MODE               ledger holds a start in the other mode
 *   REFUSAL_SECOND_INVOCATION        the selected mode already started once
 */
export function beginInvocation(
  candidateSha: string,
  workers: number,
  retries: number,
): RuntimeMode {
  const mode = resolveRuntimeMode();
  const prior = readInvocationLedger();

  const foreignSha = prior.filter((record) => record.candidate_sha !== candidateSha);
  if (foreignSha.length > 0) {
    appendLedger(
      ledgerRecord(
        'refused',
        mode,
        candidateSha,
        prior.filter((r) => r.event === 'start').length + 1,
        'refused',
        workers,
        retries,
        0,
        REFUSAL_CANDIDATE_SHA_MISMATCH,
      ),
    );
    throw new ModeResolutionError(
      REFUSAL_CANDIDATE_SHA_MISMATCH,
      `invocation ledger holds evidence for candidate_sha '${foreignSha[0].candidate_sha}' (refusing candidate '${candidateSha}')`,
    );
  }

  const starts = prior.filter((record) => record.event === 'start');
  const foreignMode = starts.filter((record) => record.mode !== mode);
  if (foreignMode.length > 0) {
    appendLedger(
      ledgerRecord('refused', mode, candidateSha, starts.length + 1, 'refused', workers, retries, 0,
        REFUSAL_CROSS_MODE),
    );
    throw new ModeResolutionError(
      REFUSAL_CROSS_MODE,
      `this worktree/results directory already recorded a '${foreignMode[0].mode}' invocation; switching to '${mode}' is refused`,
    );
  }

  if (starts.length >= 1) {
    appendLedger(
      ledgerRecord('refused', mode, candidateSha, starts.length + 1, 'refused', workers, retries, 0,
        REFUSAL_SECOND_INVOCATION),
    );
    throw new ModeResolutionError(
      REFUSAL_SECOND_INVOCATION,
      `a '${mode}' invocation has already started in this worktree/results directory`,
    );
  }

  appendLedger(
    ledgerRecord('start', mode, candidateSha, 1, 'started', workers, retries, 0),
  );
  frozen = { mode, candidateSha, workers, retries };
  return mode;
}

export function endInvocation(
  candidateSha: string,
  workers: number,
  retries: number,
  observedNodeCount: number,
  status: string,
): void {
  const mode = recordedMode();
  if (candidateSha !== recordedCandidateSha()) {
    throw new ModeResolutionError(
      REFUSAL_CANDIDATE_SHA_MISMATCH,
      `invocation end carries candidate_sha '${candidateSha}' but the recorded candidate is '${recordedCandidateSha()}'`,
    );
  }
  const starts = readInvocationLedger().filter(
    (record) => record.event === 'start' && record.mode === mode,
  );
  appendLedger(
    ledgerRecord('end', mode, candidateSha, starts.length, status, workers, retries, observedNodeCount),
  );
}

function moveAsideAndRemove(target: string): void {
  if (!fs.existsSync(target)) return;
  fs.mkdirSync(RESULTS_DIR, { recursive: true });
  const trash = path.join(
    RESULTS_DIR,
    `.cleanup-${process.pid}-${path.basename(target)}-${Date.now()}`,
  );
  fs.renameSync(target, trash);
  fs.rmSync(trash, { recursive: true, force: true });
}

export function clearGeneratedRuntimeOutputs(): void {
  requireRuntimeMode();
  fs.mkdirSync(RESULTS_DIR, { recursive: true });
  for (const file of [
    RECONCILIATION_IN,
    RECONCILIATION_OUT,
    PLAYWRIGHT_REPORT,
    PREFLIGHT_VERDICT,
    AUTHORITY_REPORT,
    LIVE_EXECUTION_CONTRACT,
  ]) {
    moveAsideAndRemove(file);
  }
  for (const dir of [TEST_ARTIFACTS_DIR, MAILDIR]) {
    moveAsideAndRemove(dir);
    fs.mkdirSync(dir, { recursive: true });
  }
  fs.mkdirSync(path.join(MAILDIR, 'new'), { recursive: true });
}

export function sanitizedFailureClass(status: string, errors: Array<{ message?: string }>): string {
  if (status === 'passed') return 'NO_FAILURE';
  const message = errors.map((e) => e.message ?? '').join('\n').toLowerCase();
  if (status === 'timedOut' || message.includes('timeout')) return 'TIMEOUT';
  if (message.includes('-> 401') || message.includes('status 401') || message.includes('unauthorized')) {
    return 'HTTP_401';
  }
  if (message.includes('strict mode violation')) return 'ACCESSIBLE_SELECTOR_STRICTNESS';
  if (message.includes('to be visible') || message.includes('locator') || message.includes('getbyrole')) {
    return 'ACCESSIBLE_SELECTOR_OR_VISIBILITY';
  }
  if (message.includes('api ') || /->\s*[45]\d\d/.test(message)) return 'API_STATUS';
  return 'ASSERTION_FAILURE';
}
