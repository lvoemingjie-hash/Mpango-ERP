/**
 * File 03/06 — RESET ENTRY nodes (CSV rows 11-15): R1, R2, R3, R4, R5.
 *
 * The journey token comes from F3's submission via the F6 maildir helper
 * (non-browser, in-memory). R1/R2 open the fragment link and prove
 * fragment-only transport plus post-load URL scrubbing; R3 proves a query
 * token is rejected client-side with the Invalid Link panel and no reset API
 * call; R4 proves a missing token fails closed without a request; R5 proves
 * a forged token yields the same neutral server error (POST 401).
 */

import { test } from '@playwright/test';
import { loadJourneyEnv, type JourneyEnv } from '../src/env.js';
import { assertSan } from '../src/assertions.js';
import { a1State, resetTokenFromLink } from '../src/token-store.js';
import { waitForLink } from '../src/maildir.js';
import { ensureA1Provisioned } from '../src/api-client.js';
import {
  setViewportFromCsv,
  openResetLink,
  expectResetFormRendered,
  expectResetServerErrorVisible,
  expectInvalidLinkPanelVisible,
  submitReset,
  collectApiRequests,
  apiUrls,
  urlsMatching,
  UI_COPY,
} from '../src/ui-journey.js';
import { expect } from '@playwright/test';

let env: JourneyEnv;
let journeyLink = '';

test.beforeAll(async () => {
  env = loadJourneyEnv('a1');
  await ensureA1Provisioned(env);
  const submittedAt = a1State().f3SubmittedAt;
  assertSan(
    submittedAt !== undefined,
    'R-series requires F3 to have submitted the forgot form first (journey order violated)',
  );
  // F6 surface: browser-external maildir read, link kept in memory only.
  const hit = await waitForLink({
    root: env.maildirRoot,
    kind: 'reset',
    recipient: env.a1.email,
    sinceMs: submittedAt,
  });
  journeyLink = hit.link;
  a1State().resetLink = hit.link;
});

test('R1', async ({ page }) => {
  setViewportFromCsv(page, '1280x800');
  const apiRequests = collectApiRequests(page);
  await openResetLink(page, journeyLink, env.baseUrl);
  await expectResetFormRendered(page);
  // 页面 GET 无后端调用: the reset page loads without any API request.
  assertSan(
    apiUrls(apiRequests).length === 0,
    `R1: reset page load fired backend API requests (count: ${apiUrls(apiRequests).length}; field: api request urls)`,
  );
  // Token must live in the fragment only — no request URL may carry it.
  assertSan(
    urlsMatching(apiRequests, /resetToken|reset_token/i).length === 0,
    'R1: a network request URL carried the reset token (field: request url)',
  );
  const currentUrl = page.url();
  assertSan(
    currentUrl === `${env.baseUrl}/reset-password`,
    'R1: settled URL is not the scrubbed /reset-password path (field: page url)',
  );
  const hash = await page.evaluate(() => window.location.hash);
  assertSan(hash === '', 'R1: location.hash is not empty after load (field: location.hash)');
});

test('R2', async ({ page }) => {
  setViewportFromCsv(page, '1280x800');
  await openResetLink(page, journeyLink, env.baseUrl);
  await expectResetFormRendered(page);
  // Allow the scrub effect to settle, then prove the address bar and the
  // current history entry no longer contain the fragment.
  await page.waitForTimeout(500);
  const currentUrl = page.url();
  assertSan(
    currentUrl === `${env.baseUrl}/reset-password`,
    'R2: address bar was not stripped to the pure path (field: page url)',
  );
  assertSan(!currentUrl.includes('#'), 'R2: address bar still contains a fragment (field: page url)');
  const hash = await page.evaluate(() => window.location.hash);
  assertSan(hash === '', 'R2: location.hash is not empty after scrub (field: location.hash)');
  const historyLength = await page.evaluate(() => window.history.length);
  assertSan(historyLength >= 1, 'R2: history.length is not a legal value (field: history.length)');
});

test('R3', async ({ page }) => {
  setViewportFromCsv(page, '1280x800');
  const apiRequests = collectApiRequests(page);
  const token = resetTokenFromLink(journeyLink);
  const queryUrl = `${env.baseUrl}/reset-password?resetToken=${encodeURIComponent(token)}`;
  await page.goto(queryUrl);
  await expectInvalidLinkPanelVisible(page);
  const resetCalls = urlsMatching(apiRequests, /\/api\/v1\/auth\/reset-password/);
  assertSan(
    resetCalls.length === 0,
    `R3: reset API was called despite query-token rejection (count: ${resetCalls.length}; field: request url)`,
  );
  const currentUrl = page.url();
  assertSan(
    currentUrl === `${env.baseUrl}/reset-password`,
    'R3: URL was not scrubbed after query-token rejection (field: page url)',
  );
});

test('R4', async ({ page }) => {
  setViewportFromCsv(page, '1280x800');
  const apiRequests = collectApiRequests(page);
  await page.goto('/reset-password');
  await expectResetFormRendered(page);
  await submitReset(page, env.a1.newPassword);
  await expectResetServerErrorVisible(page);
  const resetCalls = urlsMatching(apiRequests, /\/api\/v1\/auth\/reset-password/);
  assertSan(
    resetCalls.length === 0,
    `R4: missing-token submit still fired the reset API (count: ${resetCalls.length}; field: request url)`,
  );
});

test('R5', async ({ page }) => {
  setViewportFromCsv(page, '1280x800');
  await page.goto(`${env.baseUrl}/reset-password#resetToken=xyz`);
  await expectResetFormRendered(page);
  const responsePromise = page.waitForResponse(
    (response) => response.url().includes('/api/v1/auth/reset-password'),
    { timeout: 30_000 },
  );
  await submitReset(page, env.a1.newPassword);
  const response = await responsePromise;
  assertSan(response.status() === 401, `R5: forged token must answer 401 (field: status, got ${response.status()})`);
  await expectResetServerErrorVisible(page);
  // 与 R4 相同的中性错误文案: same constant the frontend maps every server
  // reset failure to.
  const errorText = await page.getByText(UI_COPY.resetServerError, { exact: true }).textContent();
  assertSan(
    (errorText ?? '').trim() === UI_COPY.resetServerError,
    'R5: server error copy differs from the neutral constant (field: visibleText)',
  );
});
