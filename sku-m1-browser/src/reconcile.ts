/**
 * Reconciliation accounting for the two frozen browser nodes.
 *
 * Every required viewport/state combination must be accounted for exactly
 * once; the builder fails closed if any combination is missing or duplicated.
 */
import * as fs from 'fs';
import * as path from 'path';

export const NODE_IDS = {
  catalogId: 'sku-m1-browser/tests/catalog-id-001.spec.ts::CATALOG-ID-001',
  catalogHist: 'sku-m1-browser/tests/catalog-hist-001.spec.ts::CATALOG-HIST-001',
} as const;

export type Viewport = 'desktop' | 'mobile-390';
export const REQUIRED_VIEWPORTS: Viewport[] = ['desktop', 'mobile-390'];

export interface NodeViewportReconciliation {
  node: string;
  viewport: Viewport;
  status: 'passed' | 'failed';
  assertions: string[];
}

export interface Reconciliation {
  schema: 'sku-m1-browser/reconciliation/1';
  nodes: Record<string, NodeViewportReconciliation[]>;
  accounting: {
    required_combinations: number;
    recorded_combinations: number;
    duplicates: number;
    gap: number;
  };
}

export function recordOutcome(
  node: string,
  viewport: Viewport,
  status: 'passed' | 'failed',
  assertions: string[],
): void {
  const file = path.resolve(__dirname, '..', 'results', 'reconciliation-in.jsonl');
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.appendFileSync(
    file,
    JSON.stringify({ node, viewport, status, assertions }) + '\n',
  );
}

export function buildReconciliation(): Reconciliation {
  const file = path.resolve(__dirname, '..', 'results', 'reconciliation-in.jsonl');
  const combos: NodeViewportReconciliation[] = [];
  const seen = new Set<string>();
  let duplicates = 0;
  if (fs.existsSync(file)) {
    for (const line of fs.readFileSync(file, 'utf-8').split('\n').filter(Boolean)) {
      const rec = JSON.parse(line) as NodeViewportReconciliation;
      const key = `${rec.node}|${rec.viewport}`;
      if (seen.has(key)) duplicates += 1;
      seen.add(key);
      combos.push(rec);
    }
  }
  const required = Object.values(NODE_IDS).flatMap((node) =>
    REQUIRED_VIEWPORTS.map((viewport) => `${node}|${viewport}`),
  );
  const missing = required.filter((r) => !seen.has(r));
  const nodes: Reconciliation['nodes'] = {
    [NODE_IDS.catalogId]: combos.filter((c) => c.node === NODE_IDS.catalogId),
    [NODE_IDS.catalogHist]: combos.filter((c) => c.node === NODE_IDS.catalogHist),
  };
  const reconciliation: Reconciliation = {
    schema: 'sku-m1-browser/reconciliation/1',
    nodes,
    accounting: {
      required_combinations: required.length,
      recorded_combinations: seen.size,
      duplicates,
      gap: missing.length + Math.max(0, seen.size - required.length) + duplicates,
    },
  };
  const out = path.resolve(__dirname, '..', 'results', 'reconciliation.json');
  fs.writeFileSync(out, JSON.stringify(reconciliation, null, 2));
  return reconciliation;
}
