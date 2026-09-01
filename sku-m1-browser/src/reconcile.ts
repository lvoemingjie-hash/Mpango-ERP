/**
 * Reconciliation accounting for the two frozen browser nodes.
 *
 * Every required viewport/state combination must be accounted for exactly
 * once; the builder fails closed if any combination is missing or duplicated.
 */
import * as fs from 'fs';
import {
  RECONCILIATION_IN,
  RECONCILIATION_OUT,
  assertKnownMode,
  readInvocationLedger,
  readLiveExecutionContract,
  RuntimeMode,
} from './runtime';

export const NODE_IDS = {
  catalogId: 'sku-m1-browser/tests/catalog-id-001.spec.ts::CATALOG-ID-001',
  catalogHist: 'sku-m1-browser/tests/catalog-hist-001.spec.ts::CATALOG-HIST-001',
} as const;

export type Viewport = 'desktop' | 'mobile-390';
export const REQUIRED_VIEWPORTS: Viewport[] = ['desktop', 'mobile-390'];

export interface NodeViewportReconciliation {
  schema?: 'sku-m1-browser/reconciliation-record/1';
  node: string;
  viewport: Viewport;
  status: 'passed' | 'failed';
  failure_class: string;
  assertions: string[];
  mode?: RuntimeMode;
  candidate_sha?: string;
}

export interface PlaywrightObservedResult {
  node: string;
  viewport: string;
  status: 'passed' | 'failed';
}

/** Mode/candidate-SHA binding carried by the Playwright config metadata. */
export interface PlaywrightReportBinding {
  execution_mode?: string;
  candidate_sha?: string;
}

export interface ReconciliationInput {
  mode: RuntimeMode;
  candidateSha: string;
  observed: PlaywrightObservedResult[];
  reportBindings: PlaywrightReportBinding[];
}

export interface Reconciliation {
  schema: 'sku-m1-browser/reconciliation/1';
  nodes: Record<string, NodeViewportReconciliation[]>;
  errors: string[];
  accounting: {
    required_combinations: number;
    pass: number;
    fail: number;
    skipped: number;
    not_run: number;
    recorded_combinations: number;
    duplicates: number;
    unknown_nodes: number;
    unknown_viewports: number;
    report_disagreements: number;
    playwright_without_reconciliation: number;
    reconciliation_without_playwright: number;
    mode_mismatches: number;
    candidate_sha_mismatches: number;
    gap: number;
  };
}

export function recordExecution(record: NodeViewportReconciliation): void {
  fs.mkdirSync(RECONCILIATION_IN.replace(/\/[^/]+$/, ''), { recursive: true });
  fs.appendFileSync(
    RECONCILIATION_IN,
    JSON.stringify({ schema: 'sku-m1-browser/reconciliation-record/1', ...record }) + '\n',
  );
}

function key(node: string, viewport: string): string {
  return `${node}|${viewport}`;
}

/**
 * Require ONE execution mode and ONE candidate SHA across every evidence
 * source. `label` names the source so a disagreement is attributable.
 */
function checkBinding(
  label: string,
  actualMode: unknown,
  actualSha: unknown,
  expectedMode: RuntimeMode,
  expectedSha: string,
  errors: string[],
  tally: { mode: number; sha: number },
): void {
  if (actualMode !== expectedMode) {
    errors.push(`mode_mismatch:${label}:${String(actualMode)}`);
    tally.mode += 1;
  }
  if (actualSha !== expectedSha) {
    errors.push(`candidate_sha_mismatch:${label}:${String(actualSha)}`);
    tally.sha += 1;
  }
}

export function buildReconciliation(input: ReconciliationInput): Reconciliation {
  const observedResults = input.observed;
  const combos: NodeViewportReconciliation[] = [];
  const errors: string[] = [];
  const bindingTally = { mode: 0, sha: 0 };
  const counts = new Map<string, number>();
  const expectedNodes = new Set<string>(Object.values(NODE_IDS));
  const expectedViewports = new Set<string>(REQUIRED_VIEWPORTS);
  let duplicates = 0;
  let unknownNodes = 0;
  let unknownViewports = 0;
  if (fs.existsSync(RECONCILIATION_IN)) {
    for (const line of fs.readFileSync(RECONCILIATION_IN, 'utf-8').split('\n').filter(Boolean)) {
      const rec = JSON.parse(line) as NodeViewportReconciliation;
      const recKey = key(rec.node, rec.viewport);
      counts.set(recKey, (counts.get(recKey) ?? 0) + 1);
      if ((counts.get(recKey) ?? 0) > 1) duplicates += 1;
      if (!expectedNodes.has(rec.node)) {
        unknownNodes += 1;
        errors.push(`unknown_node:${rec.node}`);
      }
      if (!expectedViewports.has(rec.viewport)) {
        unknownViewports += 1;
        errors.push(`unknown_viewport:${rec.viewport}`);
      }
      if (rec.status !== 'passed' && rec.status !== 'failed') {
        errors.push(`unknown_status:${rec.status}`);
      }
      combos.push(rec);
    }
  }

  // ---- Mode / candidate-SHA binding: all four sources must agree. -----------
  let expectedMode: RuntimeMode;
  try {
    expectedMode = assertKnownMode(input.mode, 'reconciliation input');
  } catch (error) {
    errors.push(`unknown_mode:${String(input.mode)}`);
    bindingTally.mode += 1;
    expectedMode = input.mode as RuntimeMode;
    void error;
  }
  const expectedSha = input.candidateSha;

  const contract = readLiveExecutionContract();
  if (!contract) {
    errors.push('live_execution_contract_missing');
  } else {
    checkBinding('live_execution_contract', contract.execution_mode, contract.candidate_sha,
      expectedMode, expectedSha, errors, bindingTally);
  }

  const ledger = readInvocationLedger();
  if (ledger.length === 0) {
    errors.push('invocation_ledger_missing');
  }
  for (const record of ledger) {
    checkBinding(`invocation_ledger:${record.event}`, record.mode, record.candidate_sha,
      expectedMode, expectedSha, errors, bindingTally);
  }

  for (const rec of combos) {
    checkBinding(`reconciliation_record:${key(rec.node, rec.viewport)}`, rec.mode, rec.candidate_sha,
      expectedMode, expectedSha, errors, bindingTally);
  }

  if (input.reportBindings.length === 0) {
    errors.push('playwright_report_binding_missing');
  }
  for (const binding of input.reportBindings) {
    checkBinding('playwright_report', binding.execution_mode, binding.candidate_sha,
      expectedMode, expectedSha, errors, bindingTally);
  }
  // -------------------------------------------------------------------------

  const required = Object.values(NODE_IDS).flatMap((node) =>
    REQUIRED_VIEWPORTS.map((viewport) => `${node}|${viewport}`),
  );
  const seen = new Set([...counts.keys()].filter((k) => counts.get(k) === 1));
  const missing = required.filter((r) => !seen.has(r));
  const pass = combos.filter((c) => c.status === 'passed').length;
  const fail = combos.filter((c) => c.status === 'failed').length;
  // skipped/not_run are combinations that never recorded an outcome (e.g.
  // VOID preflight, browser launch abort). Every required combination must
  // be accounted in exactly one of the four classes.
  const skipped = 0; // the harness forbids skipping; kept explicit for the contract
  const notRun = Math.max(0, required.length - seen.size);
  const recByKey = new Map(combos.map((c) => [key(c.node, c.viewport), c]));
  const reportByKey = new Map(observedResults.map((r) => [key(r.node, r.viewport), r]));
  let reportDisagreements = 0;
  let playwrightWithoutReconciliation = 0;
  let reconciliationWithoutPlaywright = 0;
  for (const observed of observedResults) {
    if (!expectedNodes.has(observed.node)) {
      errors.push(`report_unknown_node:${observed.node}`);
    }
    if (!expectedViewports.has(observed.viewport)) {
      errors.push(`report_unknown_viewport:${observed.viewport}`);
    }
  }
  for (const requiredKey of required) {
    const rec = recByKey.get(requiredKey);
    const report = reportByKey.get(requiredKey);
    if (report && !rec) {
      playwrightWithoutReconciliation += 1;
      errors.push(`playwright_without_reconciliation:${requiredKey}`);
    }
    if (rec && observedResults.length > 0 && !report) {
      reconciliationWithoutPlaywright += 1;
      errors.push(`reconciliation_without_playwright:${requiredKey}`);
    }
    if (rec && report && rec.status !== report.status) {
      reportDisagreements += 1;
      errors.push(`report_disagreement:${requiredKey}:${rec.status}:playwright_${report.status}`);
    }
  }
  for (const [recKey, count] of counts.entries()) {
    if (count > 1) errors.push(`duplicate_combination:${recKey}`);
  }
  const nodes: Reconciliation['nodes'] = {
    [NODE_IDS.catalogId]: combos.filter((c) => c.node === NODE_IDS.catalogId),
    [NODE_IDS.catalogHist]: combos.filter((c) => c.node === NODE_IDS.catalogHist),
  };
  const reconciliation: Reconciliation = {
    schema: 'sku-m1-browser/reconciliation/1',
    nodes,
    errors,
    accounting: {
      required_combinations: required.length,
      pass,
      fail,
      skipped,
      not_run: notRun,
      recorded_combinations: seen.size,
      duplicates,
      unknown_nodes: unknownNodes,
      unknown_viewports: unknownViewports,
      report_disagreements: reportDisagreements,
      playwright_without_reconciliation: playwrightWithoutReconciliation,
      reconciliation_without_playwright: reconciliationWithoutPlaywright,
      mode_mismatches: bindingTally.mode,
      candidate_sha_mismatches: bindingTally.sha,
      gap: missing.length + Math.max(0, seen.size - required.length) + duplicates
        + unknownNodes + unknownViewports + reportDisagreements
        + playwrightWithoutReconciliation + reconciliationWithoutPlaywright
        + bindingTally.mode + bindingTally.sha,
    },
  };
  fs.writeFileSync(RECONCILIATION_OUT, JSON.stringify(reconciliation, null, 2));
  return reconciliation;
}
