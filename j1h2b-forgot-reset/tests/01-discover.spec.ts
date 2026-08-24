/**
 * File 01/06 — DISCOVER + FORM nodes (CSV rows 1-6).
 * F1-D, F1-T, F1-M: forgot-password entry discovery on /login across the
 * three CSV viewports. F2-D, F2-T, F2-M: /forgot-password form structure.
 *
 * Execution order matters: files run 01→06 serially under workers=1; this
 * file has no journey-state dependency and needs only the common env group.
 */

import { test } from '@playwright/test';
import { loadJourneyEnv } from '../src/env.js';
import {
  setViewportFromCsv,
  expectForgotEntryVisible,
  clickForgotEntry,
  expectForgotFormStructure,
  expectNoHorizontalOverflow,
} from '../src/ui-journey.js';

test.beforeAll(() => {
  // Fail closed on missing common env before any navigation happens.
  loadJourneyEnv('common');
});

test('F1-D', async ({ page }) => {
  setViewportFromCsv(page, '1280x800');
  await page.goto('/login');
  await expectForgotEntryVisible(page);
  await clickForgotEntry(page);
  await expectForgotFormStructure(page);
});

test('F1-T', async ({ page }) => {
  setViewportFromCsv(page, '768x1024');
  await page.goto('/login');
  await expectForgotEntryVisible(page);
  await clickForgotEntry(page);
  await expectForgotFormStructure(page);
});

test('F1-M', async ({ page }) => {
  setViewportFromCsv(page, '390x844');
  await page.goto('/login');
  await expectForgotEntryVisible(page);
  await clickForgotEntry(page);
  await expectForgotFormStructure(page);
});

test('F2-D', async ({ page }) => {
  setViewportFromCsv(page, '1280x800');
  await page.goto('/login');
  await clickForgotEntry(page);
  await expectForgotFormStructure(page);
});

test('F2-T', async ({ page }) => {
  setViewportFromCsv(page, '768x1024');
  await page.goto('/login');
  await clickForgotEntry(page);
  await expectForgotFormStructure(page);
});

test('F2-M', async ({ page }) => {
  setViewportFromCsv(page, '390x844');
  await page.goto('/login');
  await clickForgotEntry(page);
  await expectForgotFormStructure(page);
  await expectNoHorizontalOverflow(page, 390);
});
