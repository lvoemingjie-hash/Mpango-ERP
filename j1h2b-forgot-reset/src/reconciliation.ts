/**
 * 29-node reconciliation model (task directive #3).
 *
 * Single source of truth: inventory/node-registry.json (data), kept in lock
 * step with the byte-identical protocol CSV by tools/validate-static.mjs.
 * The five non-browser nodes — F6, R6, M2, R13, RT0 — are accounted here and
 * can NEVER surface as browser PASSes: they are not Playwright nodes at all.
 * RT0 stays BLOCKED_BY_H2_C with no API bypass.
 */

import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

export interface NodeRegistryEntry {
  nodeId: string;
  surface: 'browser' | 'non-browser';
  executionClass: string;
  status: string;
  accounting?: string;
}

export interface NodeRegistry {
  /** Provenance pointer — the actual protocol SHA lives in README/FROZEN-REPORT. */
  protocolCommitRef: string;
  inventoryCsvPath: string;
  expectedCounts: { browser: number; nonBrowser: number; total: number };
  nodes: NodeRegistryEntry[];
}

// Read + parse at module load (committed data only; no env, no network).
// fs-based on purpose: the Playwright transpile loader is not guaranteed to
// support JSON module imports under NodeNext.
const REGISTRY_PATH = join(
  dirname(fileURLToPath(import.meta.url)),
  '..',
  'inventory',
  'node-registry.json',
);
export const NODE_REGISTRY: NodeRegistry = JSON.parse(
  readFileSync(REGISTRY_PATH, 'utf8'),
);

export const BROWSER_NODE_IDS: string[] = NODE_REGISTRY.nodes
  .filter((node) => node.surface === 'browser')
  .map((node) => node.nodeId);

export const NON_BROWSER_NODE_IDS: string[] = NODE_REGISTRY.nodes
  .filter((node) => node.surface === 'non-browser')
  .map((node) => node.nodeId);

export const EXPECTED_NON_BROWSER_IDS = ['F6', 'R6', 'M2', 'R13', 'RT0'] as const;

function invariant(condition: boolean, message: string): asserts condition {
  if (!condition) {
    throw new Error(`reconciliation registry invariant violated: ${message}`);
  }
}

invariant(NODE_REGISTRY.nodes.length === 29, 'registry must hold exactly 29 nodes');
invariant(BROWSER_NODE_IDS.length === 24, 'registry must hold exactly 24 browser nodes');
invariant(NON_BROWSER_NODE_IDS.length === 5, 'registry must hold exactly 5 non-browser nodes');
invariant(
  NON_BROWSER_NODE_IDS.every((id) =>
    (EXPECTED_NON_BROWSER_IDS as readonly string[]).includes(id),
  ),
  'non-browser set must be exactly F6/R6/M2/R13/RT0',
);
invariant(
  NODE_REGISTRY.nodes.find((node) => node.nodeId === 'RT0')?.status === 'BLOCKED_BY_H2_C',
  'RT0 must stay BLOCKED_BY_H2_C',
);

/** Reconciliation snapshot for the post-run accounting table (gap must be 0). */
export function reconciliationSnapshot(): Array<NodeRegistryEntry & { accountingSource: string }> {
  return NODE_REGISTRY.nodes.map((node) => ({
    ...node,
    accountingSource:
      node.surface === 'browser'
        ? 'playwright-single-authoritative-run'
        : node.nodeId === 'F6'
          ? 'harness-maildir-helper (in-memory)'
          : node.nodeId === 'R13'
            ? 'tools/scan-artifacts.mjs post-run evidence scan'
            : node.nodeId === 'RT0'
              ? 'protocol blocker ledger (H2-C)'
              : 'backend pre-gate evidence',
  }));
}

// Referenced by specs/docs so the reconciliation model is imported where the
// journey reads it (keeps the model a live dependency, not dead data).
export const RECONCILIATION_TOTALS = {
  browser: BROWSER_NODE_IDS.length,
  nonBrowser: NON_BROWSER_NODE_IDS.length,
  total: NODE_REGISTRY.nodes.length,
} as const;

export function accountingSummaryFor(nodeId: string): string {
  const node = NODE_REGISTRY.nodes.find((entry) => entry.nodeId === nodeId);
  return node?.accounting ?? node?.status ?? 'unknown node';
}
