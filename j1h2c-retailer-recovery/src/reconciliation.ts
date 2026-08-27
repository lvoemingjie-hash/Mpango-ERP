/**
 * Run reconciliation: 15 browser + 2 static-class = 17, gap = 0 — B1-R1
 * (Kilo H closure).
 *
 * Browser nodes (HC01-HC10, HC12-HC16) are accounted from the actual
 * Playwright run. The two static-class nodes are accounted SEPARATELY and
 * can be marked PASS only when their runtime checks actually succeeded in
 * THIS run:
 *   HC11 — fragment-only resetToken + public w verified from the HC07
 *          email delivery (fresh-delivery parsed by src/maildir.ts);
 *   HC17 — lowercase caller input produced a DB-canonical UPPERCASE w in
 *          the email.
 * They are NEVER reported as browser PASS. No results are pre-written: the
 * reconciliation starts every run from PENDING and only records what the
 * run itself proved.
 *
 * ARTIFACT PUBLICATION (Kilo H): publishArtifacts() writes an auditable
 * reconciliation.json + reconciliation.csv into the run artifacts dir.
 * It is called from the spec's afterAll REGARDLESS of run outcome, so a
 * failed run publishes its true PARTIAL state — never a fabricated
 * complete one, and never masked by a second error. The artifact contains
 * node ids, surfaces, and outcomes ONLY — no tokens, passwords, emails,
 * or full URLs.
 */

import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

export type NodeOutcome = 'PENDING' | 'PASS' | 'FAIL' | 'NOT_RUN';

export interface ReconciliationEntry {
  nodeId: string;
  surface: 'browser' | 'static';
  outcome: NodeOutcome;
}

const BROWSER_NODES = [
  'HC01', 'HC02', 'HC03', 'HC04', 'HC05',
  'HC06', 'HC07', 'HC08', 'HC09', 'HC10',
  'HC12', 'HC13', 'HC14', 'HC15', 'HC16',
] as const;

const STATIC_NODES = ['HC11', 'HC17'] as const;

export class RunReconciliation {
  private readonly entries = new Map<string, ReconciliationEntry>();

  constructor() {
    for (const nodeId of BROWSER_NODES) {
      this.entries.set(nodeId, { nodeId, surface: 'browser', outcome: 'PENDING' });
    }
    for (const nodeId of STATIC_NODES) {
      this.entries.set(nodeId, { nodeId, surface: 'static', outcome: 'PENDING' });
    }
  }

  recordBrowserPass(nodeId: (typeof BROWSER_NODES)[number]): void {
    const entry = this.entries.get(nodeId);
    if (!entry || entry.surface !== 'browser') {
      throw new Error(`reconciliation:${nodeId}:not_a_browser_node`);
    }
    entry.outcome = 'PASS';
  }

  /** Static nodes flip to PASS only on actual runtime-check success. */
  recordStaticPass(nodeId: (typeof STATIC_NODES)[number]): void {
    const entry = this.entries.get(nodeId);
    if (!entry || entry.surface !== 'static') {
      throw new Error(`reconciliation:${nodeId}:not_a_static_node`);
    }
    entry.outcome = 'PASS';
  }

  /**
   * B1-R2 (Kilo H #4): distinguish FAILED nodes from NOT_RUN nodes. A run
   * that stopped at its first failure marks reached-but-unpassed nodes as
   * FAIL and everything after the stopping point as NOT_RUN — never a
   * blanket FAIL that erases the distinction.
   */
  markOutcomesAfterFailure(firstFailedNodeId?: string): void {
    const order = [...this.entries.values()];
    let stopIndex = order.findIndex(
      (entry) => entry.nodeId === firstFailedNodeId,
    );
    if (stopIndex < 0) stopIndex = order.length;
    order.forEach((entry, index) => {
      if (entry.outcome === 'PENDING') {
        entry.outcome = index <= stopIndex ? 'FAIL' : 'NOT_RUN';
      }
    });
  }

  snapshot(): ReconciliationEntry[] {
    return [...this.entries.values()].map((entry) => ({ ...entry }));
  }

  summary(): {
    browser: { total: number; pass: number };
    static: { total: number; pass: number };
    total: number;
    gap: number;
    incomplete: string[];
    outcomes: { pass: number; fail: number; notRun: number; pending: number };
  } {
    const values = [...this.entries.values()];
    const browser = values.filter((entry) => entry.surface === 'browser');
    const statics = values.filter((entry) => entry.surface === 'static');
    const total = values.length;
    const accounted = browser.length + statics.length;
    return {
      browser: {
        total: browser.length,
        pass: browser.filter((entry) => entry.outcome === 'PASS').length,
      },
      static: {
        total: statics.length,
        pass: statics.filter((entry) => entry.outcome === 'PASS').length,
      },
      total,
      gap: total - accounted,
      incomplete: values
        .filter((entry) => entry.outcome !== 'PASS')
        .map((entry) => entry.nodeId),
      outcomes: {
        pass: values.filter((e) => e.outcome === 'PASS').length,
        fail: values.filter((e) => e.outcome === 'FAIL').length,
        notRun: values.filter((e) => e.outcome === 'NOT_RUN').length,
        pending: values.filter((e) => e.outcome === 'PENDING').length,
      },
    };
  }

  /** 15 browser + 2 static = 17 with gap 0 and nothing PENDING. */
  assertComplete(): void {
    const summary = this.summary();
    if (
      summary.browser.total !== 15 ||
      summary.static.total !== 2 ||
      summary.total !== 17 ||
      summary.gap !== 0 ||
      summary.incomplete.length !== 0
    ) {
      throw new Error(
        `reconciliation:incomplete:${summary.incomplete.join('+') || 'structural'}`,
      );
    }
  }

  /**
   * Publish the auditable artifacts (Kilo H #1/#2). Safe to call on
   * success OR failure — a failed run publishes its true partial state
   * with PENDING/FAIL outcomes. Contains ids/surfaces/outcomes ONLY.
   */
  publishArtifacts(artifactsDir: string): void {
    mkdirSync(artifactsDir, { recursive: true });
    const entries = this.snapshot();
    const payload = {
      schema: 'j1h2c-reconciliation/1',
      note: 'ids/surfaces/outcomes only; no secrets, emails, tokens, or URLs',
      summary: this.summary(),
      nodes: entries,
    };
    writeFileSync(
      join(artifactsDir, 'reconciliation.json'),
      `${JSON.stringify(payload, null, 2)}\n`,
      'utf8',
    );
    const csvLines = ['node_id,surface,outcome'];
    for (const entry of entries) {
      csvLines.push(`${entry.nodeId},${entry.surface},${entry.outcome}`);
    }
    writeFileSync(join(artifactsDir, 'reconciliation.csv'), `${csvLines.join('\n')}\n`, 'utf8');
  }
}
