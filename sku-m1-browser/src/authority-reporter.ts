/**
 * Mode-neutral browser authority reporter.
 *
 * Writes results/authority-report.json: execution mode, candidate SHA, workers,
 * retries, expected/observed execution counts, and one row per execution
 * (node, viewport, status, sanitized failure class).
 *
 * Reconciliation is rebuilt here and must agree on mode + candidate SHA across
 * ALL FOUR sources: live execution contract, invocation ledger, reconciliation
 * records and the Playwright config metadata carried by the Playwright report.
 */
import type {
  FullConfig,
  FullResult,
  Reporter,
  Suite,
  TestCase,
  TestResult,
} from '@playwright/test/reporter';
import * as fs from 'fs';
import { buildReconciliation, PlaywrightObservedResult, PlaywrightReportBinding } from './reconcile';
import {
  AUTHORITY_REPORT,
  EXPECTED_EXECUTION_COUNT,
  RETRIES,
  WORKERS,
  endInvocation,
  hasRecordedInvocation,
  recordedCandidateSha,
  recordedMode,
  RuntimeMode,
  sanitizedFailureClass,
} from './runtime';
import { HARNESS_CONFIG } from '../playwright.config';

const SCHEMA = 'sku-m1-browser/authority-report/1';

export interface AuthorityExecution {
  node: string;
  viewport: string;
  status: 'passed' | 'failed';
  failure_class: string;
}

export interface AuthorityReport {
  schema: typeof SCHEMA;
  execution_mode: RuntimeMode;
  candidate_sha: string;
  workers: number;
  retries: number;
  expected_execution_count: number;
  observed_execution_count: number;
  status: string;
  executions: AuthorityExecution[];
}

function nodeId(test: TestCase): string {
  return `sku-m1-browser/tests/${test.location.file.split('/').pop()}::${test.title}`;
}

function bindingOf(project: FullConfig['projects'][number]): PlaywrightReportBinding {
  const metadata = (project.metadata ?? {}) as {
    execution_mode?: unknown;
    candidate_sha?: unknown;
  };
  return {
    execution_mode: typeof metadata.execution_mode === 'string' ? metadata.execution_mode : undefined,
    candidate_sha: typeof metadata.candidate_sha === 'string' ? metadata.candidate_sha : undefined,
  };
}

export default class BrowserAuthorityReporter implements Reporter {
  private observed: PlaywrightObservedResult[] = [];
  private executions: AuthorityExecution[] = [];
  private bindings: PlaywrightReportBinding[] = [];

  onBegin(config: FullConfig, suite: Suite): void {
    const expected = suite.allTests().length;
    if (expected !== EXPECTED_EXECUTION_COUNT) {
      process.exitCode = 1;
    }
    this.bindings = config.projects.map(bindingOf);
  }

  onTestEnd(test: TestCase, result: TestResult): void {
    const status: 'passed' | 'failed' = result.status === 'passed' ? 'passed' : 'failed';
    const node = nodeId(test);
    const viewport = test.parent.project()?.name ?? '';
    this.observed.push({ node, viewport, status });
    this.executions.push({
      node,
      viewport,
      status,
      failure_class: sanitizedFailureClass(result.status, result.errors),
    });
  }

  onEnd(result: FullResult): void {
    if (!hasRecordedInvocation()) {
      process.exitCode = 1;
      return;
    }
    let status = result.status;
    const mode = recordedMode();
    const candidateSha = recordedCandidateSha();
    try {
      const reconciliation = buildReconciliation({
        mode,
        candidateSha,
        observed: this.observed,
        reportBindings: this.bindings,
      });
      if (reconciliation.accounting.gap !== 0 || reconciliation.errors.length) {
        status = 'failed';
        process.exitCode = 1;
      } else if (candidateSha !== HARNESS_CONFIG.candidateSha) {
        status = 'failed';
        process.exitCode = 1;
      }
    } catch {
      status = 'failed';
      process.exitCode = 1;
    } finally {
      const report: AuthorityReport = {
        schema: SCHEMA,
        execution_mode: mode,
        candidate_sha: candidateSha,
        workers: WORKERS,
        retries: RETRIES,
        expected_execution_count: EXPECTED_EXECUTION_COUNT,
        observed_execution_count: this.executions.length,
        status,
        executions: this.executions,
      };
      fs.mkdirSync(HARNESS_CONFIG.resultsDir, { recursive: true });
      fs.writeFileSync(AUTHORITY_REPORT, JSON.stringify(report, null, 2));
      endInvocation(candidateSha, WORKERS, RETRIES, this.observed.length, status);
    }
  }
}
