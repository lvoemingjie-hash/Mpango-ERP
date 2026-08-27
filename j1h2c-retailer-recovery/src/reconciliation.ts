/**
 * Run reconciliation: 15 browser + 2 static-class = 17, gap = 0.
 *
 * Browser nodes (HC01-HC10, HC12-HC16) are accounted from the actual
 * Playwright run. The two static-class nodes are accounted SEPARATELY and
 * can be marked PASS only when their runtime checks actually succeeded in
 * THIS run:
 *   HC11 — fragment-only resetToken + public w verified from the HC07
 *          email delivery;
 *   HC17 — lowercase caller input produced a DB-canonical UPPERCASE w in
 *          the email.
 * They are NEVER reported as browser PASS. No results are pre-written: the
 * reconciliation starts every run from PENDING and only records what the
 * run itself proved.
 */

export type NodeOutcome = 'PENDING' | 'PASS';

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

  summary(): {
    browser: { total: number; pass: number };
    static: { total: number; pass: number };
    total: number;
    gap: number;
    incomplete: string[];
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
      incomplete: values.filter((entry) => entry.outcome === 'PENDING').map(
        (entry) => entry.nodeId,
      ),
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
}
