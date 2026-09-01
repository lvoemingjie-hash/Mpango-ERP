import { test as base, expect } from '@playwright/test';
import { recordExecution, Viewport } from './reconcile';
import { isAuthorDiagnosticMode, sanitizedFailureClass } from './runtime';

type B3Fixtures = {
  markAssertion: (label: string) => void;
  _b3ReconciliationRecorder: void;
};

function assertionLabels(testInfo: import('@playwright/test').TestInfo): string[] {
  const holder = testInfo as unknown as { _b3AssertionLabels?: string[] };
  if (!holder._b3AssertionLabels) holder._b3AssertionLabels = [];
  return holder._b3AssertionLabels;
}

export const test = base.extend<B3Fixtures>({
  _b3ReconciliationRecorder: [async ({}, use, testInfo) => {
    assertionLabels(testInfo);
    await use();
    if (!isAuthorDiagnosticMode()) return;
    const status = testInfo.status === 'passed' ? 'passed' : 'failed';
    recordExecution({
      node: `sku-m1-browser/tests/${(testInfo.file ?? '').split('/').pop()}::${testInfo.title}`,
      viewport: testInfo.project.name as Viewport,
      status,
      failure_class: sanitizedFailureClass(testInfo.status ?? 'failed', testInfo.errors),
      assertions: assertionLabels(testInfo),
    });
  }, { auto: true }],

  markAssertion: async ({}, use, testInfo) => {
    await use((label: string) => assertionLabels(testInfo).push(label));
  },
});

export { expect };
