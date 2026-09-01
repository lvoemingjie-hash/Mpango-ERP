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
}

export interface PlaywrightObservedResult {
  node: string;
  viewport: string;
  status: 'passed' | 'failed';
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

export function buildReconciliation(observedResults: PlaywrightObservedResult[] = []): Reconciliation {
  const combos: NodeViewportReconciliation[] = [];
  const errors: string[] = [];
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
      gap: missing.length + Math.max(0, seen.size - required.length) + duplicates
        + unknownNodes + unknownViewports + reportDisagreements
        + playwrightWithoutReconciliation + reconciliationWithoutPlaywright,
    },
  };
  fs.writeFileSync(RECONCILIATION_OUT, JSON.stringify(reconciliation, null, 2));
  return reconciliation;
}
