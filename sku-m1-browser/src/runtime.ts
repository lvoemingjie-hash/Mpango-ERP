import * as fs from 'fs';
import * as path from 'path';

export const RESULTS_DIR = path.resolve(__dirname, '..', 'results');
export const RECONCILIATION_IN = path.join(RESULTS_DIR, 'reconciliation-in.jsonl');
export const RECONCILIATION_OUT = path.join(RESULTS_DIR, 'reconciliation.json');
export const PLAYWRIGHT_REPORT = path.join(RESULTS_DIR, 'playwright-report.json');
export const PREFLIGHT_VERDICT = path.join(RESULTS_DIR, 'preflight-verdict.json');
export const INVOCATION_LEDGER = path.join(RESULTS_DIR, 'invocation-ledger.jsonl');
export const TEST_ARTIFACTS_DIR = path.join(RESULTS_DIR, 'test-artifacts');
export const MAILDIR = path.join(RESULTS_DIR, 'maildir');

export const AUTHOR_DIAGNOSTIC_MODE = 'B3_AUTHOR_DIAGNOSTIC';
export const EXPECTED_EXECUTION_COUNT = 4;

export type RuntimeMode = 'AUTHOR_DIAGNOSTIC';
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

export function isAuthorDiagnosticMode(): boolean {
  return process.env[AUTHOR_DIAGNOSTIC_MODE] === '1';
}

export function requireAuthorDiagnosticMode(): void {
  if (!isAuthorDiagnosticMode()) {
    throw new Error(`${AUTHOR_DIAGNOSTIC_MODE}=1 is required for browser runtime execution`);
  }
}

function appendLedger(record: InvocationLedgerRecord): void {
  fs.mkdirSync(RESULTS_DIR, { recursive: true });
  fs.appendFileSync(INVOCATION_LEDGER, JSON.stringify(record) + '\n');
}

function readLedger(): InvocationLedgerRecord[] {
  if (!fs.existsSync(INVOCATION_LEDGER)) return [];
  return fs.readFileSync(INVOCATION_LEDGER, 'utf-8')
    .split('\n')
    .filter(Boolean)
    .map((line) => JSON.parse(line) as InvocationLedgerRecord);
}

export function beginInvocation(candidateSha: string, workers: number, retries: number): number {
  requireAuthorDiagnosticMode();
  const existing = readLedger().filter((r) => r.mode === 'AUTHOR_DIAGNOSTIC' && r.event === 'start');
  const invocationCount = existing.length + 1;
  if (existing.length >= 1) {
    appendLedger({
      schema: 'sku-m1-browser/invocation-ledger/1',
      event: 'refused',
      mode: 'AUTHOR_DIAGNOSTIC',
      candidate_sha: candidateSha,
      invocation_count: invocationCount,
      status: 'refused',
      workers,
      retries,
      expected_node_count: EXPECTED_EXECUTION_COUNT,
      observed_node_count: 0,
      reason: 'second_author_diagnostic_invocation_refused',
    });
    throw new Error('second author-diagnostic invocation refused');
  }
  appendLedger({
    schema: 'sku-m1-browser/invocation-ledger/1',
    event: 'start',
    mode: 'AUTHOR_DIAGNOSTIC',
    candidate_sha: candidateSha,
    invocation_count: invocationCount,
    status: 'started',
    workers,
    retries,
    expected_node_count: EXPECTED_EXECUTION_COUNT,
    observed_node_count: 0,
  });
  return invocationCount;
}

export function endInvocation(
  candidateSha: string,
  workers: number,
  retries: number,
  observedNodeCount: number,
  status: string,
): void {
  const starts = readLedger().filter((r) => r.mode === 'AUTHOR_DIAGNOSTIC' && r.event === 'start');
  appendLedger({
    schema: 'sku-m1-browser/invocation-ledger/1',
    event: 'end',
    mode: 'AUTHOR_DIAGNOSTIC',
    candidate_sha: candidateSha,
    invocation_count: starts.length,
    status,
    workers,
    retries,
    expected_node_count: EXPECTED_EXECUTION_COUNT,
    observed_node_count: observedNodeCount,
  });
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
  requireAuthorDiagnosticMode();
  fs.mkdirSync(RESULTS_DIR, { recursive: true });
  for (const file of [RECONCILIATION_IN, RECONCILIATION_OUT, PLAYWRIGHT_REPORT, PREFLIGHT_VERDICT]) {
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
