import type {
  FullConfig,
  FullResult,
  Reporter,
  Suite,
  TestCase,
  TestResult,
} from '@playwright/test/reporter';
import { buildReconciliation, PlaywrightObservedResult } from './reconcile';
import { endInvocation, EXPECTED_EXECUTION_COUNT } from './runtime';
import { HARNESS_CONFIG } from '../playwright.config';

const WORKERS = 1;
const RETRIES = 0;

function nodeId(test: TestCase): string {
  return `sku-m1-browser/tests/${test.location.file.split('/').pop()}::${test.title}`;
}

export default class B3DiagnosticReporter implements Reporter {
  private observed: PlaywrightObservedResult[] = [];

  onBegin(_config: FullConfig, suite: Suite): void {
    const expected = suite.allTests().length;
    if (expected !== EXPECTED_EXECUTION_COUNT) {
      process.exitCode = 1;
    }
  }

  onTestEnd(test: TestCase, result: TestResult): void {
    this.observed.push({
      node: nodeId(test),
      viewport: test.parent.project()?.name ?? '',
      status: result.status === 'passed' ? 'passed' : 'failed',
    });
  }

  onEnd(result: FullResult): void {
    let status = result.status;
    try {
      const reconciliation = buildReconciliation(this.observed);
      if (reconciliation.accounting.gap !== 0 || reconciliation.errors.length) {
        status = 'failed';
        process.exitCode = 1;
      }
    } catch {
      status = 'failed';
      process.exitCode = 1;
    } finally {
      endInvocation(HARNESS_CONFIG.candidateSha, WORKERS, RETRIES, this.observed.length, status);
    }
  }
}
