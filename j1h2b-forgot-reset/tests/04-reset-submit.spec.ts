/**
 * File 04/06 — POLICY + SUCCESS nodes (CSV rows 17-20): R7-POLICY,
 * R7-POLICY-M, R8, R8-M.
 *
 * R7* prove the frontend zod policy (>=8 chars) rejects a 7-char password
 * with an instant inline error and NO network request. R8 consumes the
 * journey token through the UI with the new password P2 and proves the
 * success panel; its consumed link is kept for R11's replay. R8-M proves the
 * success panel at 390x844 through its own fresh UI cycle (forgot → maildir
 * link → reset to the same P2), keeping R9/R10/R11 semantics intact
 * (pre-reset password dead, P2 alive).
 */

import { test, expect } from '@playwright/test';
import { loadJourneyEnv, type JourneyEnv } from '../src/env.js';
import { assertSan } from '../src/assertions.js';
import { a1State } from '../src/token-store.js';
import { waitForLink } from '../src/maildir.js';
import { ensureA1Provisioned } from '../src/api-client.js';
import {
  setViewportFromCsv,
  openResetLink,
  expectResetFormRendered,
  expectResetSuccessVisible,
  submitForgot,
  expectNeutralForgotCopyVisible,
  submitReset,
  collectApiRequests,
  urlsMatching,
} from '../src/ui-journey.js';

let env: JourneyEnv;
let journeyLink = '';

test.beforeAll(async () => {
  env = loadJourneyEnv('a1');
  await ensureA1Provisioned(env);
  const link = a1State().resetLink;
  assertSan(link !== undefined, 'R7/R8 require the R1-era journey link (journey order violated)');
  journeyLink = link;
});

test('R7-POLICY', async ({ page }) => {
  setViewportFromCsv(page, '1280x800');
  const apiRequests = collectApiRequests(page);
  await openResetLink(page, journeyLink, env.baseUrl);
  await expectResetFormRendered(page);
  // 7-character password — a synthetic weak value, not a credential.
  await page.locator('#newPassword').fill('x'.repeat(7));
  await page.getByRole('button', { name: 'Reset password' }).click();
  await expect(
    page.getByText('Password must be at least 8 characters'),
  ).toBeVisible();
  assertSan(
    urlsMatching(apiRequests, /\/api\/v1\/auth\/reset-password/).length === 0,
    'R7-POLICY: weak password must be stopped by the UI without a request (field: request url)',
  );
});

test('R7-POLICY-M', async ({ page }) => {
  setViewportFromCsv(page, '390x844');
  const apiRequests = collectApiRequests(page);
  await openResetLink(page, journeyLink, env.baseUrl);
  await expectResetFormRendered(page);
  await page.locator('#newPassword').fill('x'.repeat(7));
  await page.getByRole('button', { name: 'Reset password' }).click();
  await expect(
    page.getByText('Password must be at least 8 characters'),
  ).toBeVisible();
  assertSan(
    urlsMatching(apiRequests, /\/api\/v1\/auth\/reset-password/).length === 0,
    'R7-POLICY-M: weak password must be stopped by the UI without a request (field: request url)',
  );
});

test('R8', async ({ page }) => {
  setViewportFromCsv(page, '1280x800');
  await openResetLink(page, journeyLink, env.baseUrl);
  await expectResetFormRendered(page);
  const responsePromise = page.waitForResponse(
    (response) => response.url().includes('/api/v1/auth/reset-password'),
    { timeout: 30_000 },
  );
  await submitReset(page, env.a1.newPassword);
  const response = await responsePromise;
  assertSan(response.status() === 200, `R8: reset must answer 200 (field: status, got ${response.status()})`);
  await expectResetSuccessVisible(page);
  a1State().usedResetLink = journeyLink;
});

test('R8-M', async ({ page }) => {
  setViewportFromCsv(page, '390x844');
  // Fresh UI cycle at 390x844: forgot → maildir link (in-memory) → reset to
  // the SAME new password → success panel usable at mobile width.
  await page.goto('/forgot-password');
  const submittedAt = Date.now();
  await submitForgot(page, env.a1.email);
  await expectNeutralForgotCopyVisible(page);
  const hit = await waitForLink({
    root: env.maildirRoot,
    kind: 'reset',
    recipient: env.a1.email,
    sinceMs: submittedAt,
  });
  await openResetLink(page, hit.link, env.baseUrl);
  await expectResetFormRendered(page);
  const responsePromise = page.waitForResponse(
    (response) => response.url().includes('/api/v1/auth/reset-password'),
    { timeout: 30_000 },
  );
  await submitReset(page, env.a1.newPassword);
  const response = await responsePromise;
  assertSan(response.status() === 200, `R8-M: second-cycle reset must answer 200 (field: status, got ${response.status()})`);
  await expectResetSuccessVisible(page);
});
