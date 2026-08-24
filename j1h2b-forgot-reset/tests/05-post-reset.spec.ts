/**
 * File 05/06 — POST-RESET nodes (CSV rows 21-25): R9, R10, R10-M, R11, R12.
 *
 * R9 proves the pre-reset password is rejected through the login UI; R10/R10-M
 * prove the new password is accepted (single workspace → straight to /).
 * R11 replays the consumed journey link with a third password value, proves
 * the replay is rejected (401 + same neutral copy) and that P2 STILL logs in.
 * R12 runs a self-contained journey slice and sweeps URL/storage/console/
 * network surfaces for secret leakage — findings name fields only.
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
  submitReset,
  loginViaUi,
  expectInvalidCredentialsVisible,
  submitForgot,
  expectNeutralForgotCopyVisible,
  collectApiRequests,
} from '../src/ui-journey.js';
import {
  scanStorage,
  scanUrl,
  scanConsoleText,
  scanSecretSubstrings,
  scanNetworkRequest,
  describeFindings,
  type LeakFinding,
  type StorageSnapshot,
} from '../src/leak-scan.js';

let env: JourneyEnv;

test.beforeAll(async () => {
  env = loadJourneyEnv('a1');
  await ensureA1Provisioned(env);
});

test('R9', async ({ page }) => {
  setViewportFromCsv(page, '1280x800');
  const responsePromise = page.waitForResponse(
    (response) => response.url().includes('/api/v1/auth/login'),
    { timeout: 30_000 },
  );
  await loginViaUi(page, env.a1.email, env.a1.initialPassword);
  const response = await responsePromise;
  assertSan(response.status() === 401, `R9: pre-reset password must be rejected with 401 (field: status, got ${response.status()})`);
  await expectInvalidCredentialsVisible(page);
});

test('R10', async ({ page }) => {
  setViewportFromCsv(page, '1280x800');
  await loginViaUi(page, env.a1.email, env.a1.newPassword);
  // Single workspace auto-selects and lands on the dashboard root.
  await page.waitForURL((url) => url.pathname === '/', { timeout: 30_000 });
});

test('R10-M', async ({ page }) => {
  setViewportFromCsv(page, '390x844');
  await loginViaUi(page, env.a1.email, env.a1.newPassword);
  await page.waitForURL((url) => url.pathname === '/', { timeout: 30_000 });
});

test('R11', async ({ page }) => {
  setViewportFromCsv(page, '1280x800');
  const usedLink = a1State().usedResetLink;
  assertSan(usedLink !== undefined, 'R11 requires R8 to have consumed the journey link (journey order violated)');
  await openResetLink(page, usedLink as string, env.baseUrl);
  await expectResetFormRendered(page);
  const responsePromise = page.waitForResponse(
    (response) => response.url().includes('/api/v1/auth/reset-password'),
    { timeout: 30_000 },
  );
  await submitReset(page, env.a1.replayPassword);
  const response = await responsePromise;
  assertSan(response.status() === 401, `R11: token replay must be rejected with 401 (field: status, got ${response.status()})`);
  await expectResetServerErrorVisible(page);
  // P2 复验: the new password still logs in after the replay attempt.
  await loginViaUi(page, env.a1.email, env.a1.newPassword);
  await page.waitForURL((url) => url.pathname === '/', { timeout: 30_000 });
});

test('R12', async ({ page }) => {
  setViewportFromCsv(page, '1280x800');
  const findings: LeakFinding[] = [];

  const consoleTexts: string[] = [];
  page.on('console', (message) => {
    consoleTexts.push(message.text());
  });
  const networkUrls = collectApiRequests(page);

  // Journey slice: forgot (UI) → maildir link (in-memory) → reset page.
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
  await page.waitForTimeout(500);

  // Secret values for substring matching — in memory only, never printed.
  const secrets = [
    { label: 'resetToken', value: resetTokenFromLink(hit.link) },
    { label: 'a1 initial password', value: env.a1.initialPassword },
    { label: 'a1 new password', value: env.a1.newPassword },
  ];

  // Surface 1 — settled URL.
  findings.push(...scanUrl(page.url()));
  for (const secret of secrets) {
    if (page.url().includes(secret.value)) {
      findings.push({ surface: 'url', field: `settled page URL contained secret (${secret.label})` });
    }
  }

  // Surface 2 — storage keys/values.
  const storage = await page.evaluate((): StorageSnapshot => {
    const dump = (bag: Storage): Record<string, string> => {
      const out: Record<string, string> = {};
      for (let i = 0; i < bag.length; i += 1) {
        const key = bag.key(i);
        if (key !== null) out[key] = bag.getItem(key) ?? '';
      }
      return out;
    };
    return { localStorage: dump(window.localStorage), sessionStorage: dump(window.sessionStorage) };
  });
  findings.push(...scanStorage(storage));
  for (const secret of secrets) {
    findings.push(
      ...scanSecretSubstrings(
        JSON.stringify(storage),
        [secret],
        'storage',
        'a storage key or value',
      ),
    );
  }

  // Surface 3 — console output.
  consoleTexts.forEach((text, index) => {
    findings.push(...scanConsoleText(text, index));
    findings.push(...scanSecretSubstrings(text, secrets, 'console', `console message #${index}`));
  });

  // Surface 4 — network metadata (request URLs; no Authorization header is
  // expected anywhere on this unauthenticated journey slice).
  networkUrls.forEach((url, index) => {
    findings.push(...scanNetworkRequest(url, index));
    findings.push(...scanSecretSubstrings(url, secrets, 'network', `network request #${index} URL`));
  });

  assertSan(
    findings.length === 0,
    `R12 leak-scan findings (values withheld): ${describeFindings(findings)}`,
  );
});
