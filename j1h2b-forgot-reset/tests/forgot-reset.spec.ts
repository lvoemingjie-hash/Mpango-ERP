/**
 * Single-file serial journey spec — the ONLY spec file in this harness
 * (B1-R1 global serial + fail-stop closure).
 *
 * Contract:
 *  - One outer describe with `test.describe.configure({ mode: 'serial' })`:
 *    the 24 browser nodes run in registration order, which MUST equal the
 *    CSV browser row order exactly (enforced by tools/validate-static.mjs,
 *    which compares `playwright --list` order against the inventory).
 *  - Fail-stop: `maxFailures: 1` in playwright.config.ts aborts the run on
 *    the first failing node — no cascade of downstream red nodes, no
 *    rerun-to-green, no skip/fixme/only anywhere.
 *  - In-process journey state (maildir-derived reset links, fingerprints,
 *    provisioning handles) lives ONLY in src/token-store.ts and is passed
 *    exclusively between the serial tests of this single file. workers=1
 *    keeps the whole journey in one worker process; nothing ever reaches
 *    disk, logs or artifacts.
 *
 * Provisioning is idempotent and happens at the point of first need:
 *  - F3 provisions A1 (official lifecycle) and X (official create +
 *    soft-delete) via the official API — API is authorized for provisioning
 *    preconditions only.
 *  - M1 provisions the dual-tenant shared identity M (same normalized email,
 *    same initial password P1 on both tenants, formal admin role on both
 *    sides, gate: M login exposes EXACTLY {W1, W2}).
 *  - Every forgot/reset journey action goes through the rendered UI.
 *
 * No fixed sleeps: waits are bounded conditions (waitForFunction /
 * waitForLoadState / waitForResponse / locator visibility); the Playwright
 * fixed-delay API is banned by the static gate, in code and in comment
 * text alike.
 */

import { test, expect, type Browser } from '@playwright/test';
import { loadJourneyEnv, type JourneyEnv } from '../src/env.js';
import { assertSan } from '../src/assertions.js';
import { a1State, m1State, resetTokenFromLink } from '../src/token-store.js';
import {
  ensureA1Provisioned,
  ensureIneligibleEmailProvisioned,
  ensureM1Provisioned,
} from '../src/api-client.js';
import { waitForLink, negativeWindowHasLink } from '../src/maildir.js';
import {
  captureForgotFingerprint,
  sameFingerprint,
  firstFingerprintDifference,
} from '../src/neutrality.js';
import {
  setViewportFromCsv,
  expectForgotEntryVisible,
  clickForgotEntry,
  expectForgotFormStructure,
  expectNoHorizontalOverflow,
  submitForgot,
  expectNeutralForgotCopyVisible,
  openResetLink,
  expectResetFormRendered,
  submitReset,
  expectResetServerErrorVisible,
  expectInvalidLinkPanelVisible,
  expectResetSuccessVisible,
  loginViaUi,
  expectInvalidCredentialsVisible,
  expectWorkspaceSelectorWithBoth,
  selectWorkspace,
  collectApiRequests,
  apiUrls,
  urlsMatching,
  CSV_VIEWPORTS,
  UI_COPY,
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

test.describe('j1h2b-forgot-reset journey', () => {
  test.describe.configure({ mode: 'serial' });

  let env: JourneyEnv;

  test.beforeAll(() => {
    // Fail closed on the full superset before the journey starts; errors
    // name missing VARIABLE NAMES only.
    env = loadJourneyEnv('a1', 'unknown', 'ineligible', 'm1');
  });

  // ---------------------------------------------------------------------
  // DISCOVER + FORM (CSV rows 1-6)
  // ---------------------------------------------------------------------

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

  // ---------------------------------------------------------------------
  // NEUTRALITY (CSV rows 7-9)
  // ---------------------------------------------------------------------

  test('F3', async ({ page }) => {
    // Official-API provisioning preconditions, at first need (idempotent).
    await ensureA1Provisioned(env);
    await ensureIneligibleEmailProvisioned(env);

    setViewportFromCsv(page, '1280x800');
    await captureForgotFingerprint(page, 'F3');
    await page.goto('/forgot-password');
    a1State().f3SubmittedAt = Date.now();
    await submitForgot(page, env.a1.email);
    const visibleText = await expectNeutralForgotCopyVisible(page);
    const fingerprint = a1State().fingerprints.F3;
    assertSan(fingerprint !== undefined, 'F3: forgot-password response was not captured (field: response fingerprint)');
    assertSan(fingerprint.status === 200, 'F3: forgot-password must answer HTTP 200 (field: status)');
    a1State().neutralVisibleText = visibleText;
  });

  test('F4', async ({ page }) => {
    setViewportFromCsv(page, '1280x800');
    await captureForgotFingerprint(page, 'F4');
    await page.goto('/forgot-password');
    await submitForgot(page, env.unknownEmail);
    const visibleText = await expectNeutralForgotCopyVisible(page);
    const f3 = a1State().fingerprints.F3;
    const f4 = a1State().fingerprints.F4;
    assertSan(f3 !== undefined, 'F4: F3 anchor fingerprint missing (serial order violated)');
    assertSan(f4 !== undefined, 'F4: forgot-password response was not captured (field: response fingerprint)');
    assertSan(f4.status === 200, 'F4: forgot-password must answer HTTP 200 (field: status)');
    assertSan(
      sameFingerprint(f3, f4),
      `F4: response differs from F3 (first differing field: ${firstFingerprintDifference(f3, f4)})`,
    );
    assertSan(
      visibleText === a1State().neutralVisibleText,
      'F4: visible neutral copy differs from F3 (field: visibleText)',
    );
  });

  test('F5', async ({ page }) => {
    setViewportFromCsv(page, '1280x800');
    await captureForgotFingerprint(page, 'F5');
    await page.goto('/forgot-password');
    const submittedAt = Date.now();
    await submitForgot(page, env.ineligible.email);
    const visibleText = await expectNeutralForgotCopyVisible(page);
    const f3 = a1State().fingerprints.F3;
    const f5 = a1State().fingerprints.F5;
    assertSan(f3 !== undefined, 'F5: F3 anchor fingerprint missing (serial order violated)');
    assertSan(f5 !== undefined, 'F5: forgot-password response was not captured (field: response fingerprint)');
    assertSan(f5.status === 200, 'F5: forgot-password must answer HTTP 200 neutral (field: status)');
    assertSan(
      visibleText === a1State().neutralVisibleText,
      'F5: visible neutral copy differs from F3 (field: visibleText)',
    );
    // Read-only postcondition (protocol §4): zero mail for the ineligible
    // identity over the negative window ⇒ zero token issued (reset tokens
    // are only ever delivered through the email sink).
    const mailAppeared = await negativeWindowHasLink({
      root: env.maildirRoot,
      kind: 'reset',
      recipient: env.ineligible.email,
      sinceMs: submittedAt,
      windowMs: 15_000,
    });
    assertSan(!mailAppeared, 'F5: a reset link appeared in the maildir for the ineligible identity (field: recipient)');
  });

  // ---------------------------------------------------------------------
  // RESET ENTRY (CSV rows 11-15)
  // ---------------------------------------------------------------------

  test('R1', async ({ page }) => {
    const submittedAt = a1State().f3SubmittedAt;
    assertSan(
      submittedAt !== undefined,
      'R-series requires F3 to have submitted the forgot form first (serial order violated)',
    );
    // F6 surface: browser-external maildir read, link kept in memory only.
    const hit = await waitForLink({
      root: env.maildirRoot,
      kind: 'reset',
      recipient: env.a1.email,
      sinceMs: submittedAt,
    });
    a1State().resetLink = hit.link;

    setViewportFromCsv(page, '1280x800');
    const apiRequests = collectApiRequests(page);
    await openResetLink(page, hit.link, env.baseUrl);
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
    assertSan(
      page.url() === `${env.baseUrl}/reset-password`,
      'R1: settled URL is not the scrubbed /reset-password path (field: page url)',
    );
    const hash = await page.evaluate(() => window.location.hash);
    assertSan(hash === '', 'R1: location.hash is not empty after load (field: location.hash)');
  });

  test('R2', async ({ page }) => {
    const journeyLink = a1State().resetLink;
    assertSan(journeyLink !== undefined, 'R2 requires the R1-era journey link (serial order violated)');
    setViewportFromCsv(page, '1280x800');
    await openResetLink(page, journeyLink as string, env.baseUrl);
    await expectResetFormRendered(page);
    // Bounded condition wait (no fixed sleep): the scrub is a replaceState
    // effect — wait until the fragment is gone and the path is exact.
    await page.waitForFunction(
      () => window.location.hash === '' && window.location.pathname === '/reset-password',
      null,
      { timeout: 15_000 },
    );
    assertSan(
      page.url() === `${env.baseUrl}/reset-password`,
      'R2: address bar was not stripped to the pure path (field: page url)',
    );
    assertSan(!page.url().includes('#'), 'R2: address bar still contains a fragment (field: page url)');
    const historyLength = await page.evaluate(() => window.history.length);
    assertSan(historyLength >= 1, 'R2: history.length is not a legal value (field: history.length)');
  });

  test('R3', async ({ page }) => {
    const journeyLink = a1State().resetLink;
    assertSan(journeyLink !== undefined, 'R3 requires the journey link (serial order violated)');
    setViewportFromCsv(page, '1280x800');
    const apiRequests = collectApiRequests(page);
    const token = resetTokenFromLink(journeyLink as string);
    const queryUrl = `${env.baseUrl}/reset-password?resetToken=${encodeURIComponent(token)}`;
    await page.goto(queryUrl);
    await expectInvalidLinkPanelVisible(page);
    const resetCalls = urlsMatching(apiRequests, /\/api\/v1\/auth\/reset-password/);
    assertSan(
      resetCalls.length === 0,
      `R3: reset API was called despite query-token rejection (count: ${resetCalls.length}; field: request url)`,
    );
    assertSan(
      page.url() === `${env.baseUrl}/reset-password`,
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

  // ---------------------------------------------------------------------
  // POLICY + SUCCESS (CSV rows 17-20)
  // ---------------------------------------------------------------------

  test('R7-POLICY', async ({ page }) => {
    const journeyLink = a1State().resetLink;
    assertSan(journeyLink !== undefined, 'R7-POLICY requires the journey link (serial order violated)');
    setViewportFromCsv(page, '1280x800');
    const apiRequests = collectApiRequests(page);
    await openResetLink(page, journeyLink as string, env.baseUrl);
    await expectResetFormRendered(page);
    // 7-character password — a synthetic weak value, not a credential.
    await page.locator('#newPassword').fill('x'.repeat(7));
    await page.getByRole('button', { name: 'Reset password' }).click();
    await expect(page.getByText('Password must be at least 8 characters')).toBeVisible();
    assertSan(
      urlsMatching(apiRequests, /\/api\/v1\/auth\/reset-password/).length === 0,
      'R7-POLICY: weak password must be stopped by the UI without a request (field: request url)',
    );
  });

  test('R7-POLICY-M', async ({ page }) => {
    const journeyLink = a1State().resetLink;
    assertSan(journeyLink !== undefined, 'R7-POLICY-M requires the journey link (serial order violated)');
    setViewportFromCsv(page, '390x844');
    const apiRequests = collectApiRequests(page);
    await openResetLink(page, journeyLink as string, env.baseUrl);
    await expectResetFormRendered(page);
    await page.locator('#newPassword').fill('x'.repeat(7));
    await page.getByRole('button', { name: 'Reset password' }).click();
    await expect(page.getByText('Password must be at least 8 characters')).toBeVisible();
    assertSan(
      urlsMatching(apiRequests, /\/api\/v1\/auth\/reset-password/).length === 0,
      'R7-POLICY-M: weak password must be stopped by the UI without a request (field: request url)',
    );
  });

  test('R8', async ({ page }) => {
    const journeyLink = a1State().resetLink;
    assertSan(journeyLink !== undefined, 'R8 requires the journey link (serial order violated)');
    setViewportFromCsv(page, '1280x800');
    await openResetLink(page, journeyLink as string, env.baseUrl);
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
    // Fresh UI cycle at 390x844: forgot → maildir link (in-memory) → reset
    // to the SAME new password → success panel usable at mobile width.
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

  // ---------------------------------------------------------------------
  // POST-RESET (CSV rows 21-25)
  // ---------------------------------------------------------------------

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
    const usedLink = a1State().usedResetLink;
    assertSan(usedLink !== undefined, 'R11 requires R8 to have consumed the journey link (serial order violated)');
    setViewportFromCsv(page, '1280x800');
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
    // Bounded settle condition (no fixed sleep): the page is rendered and
    // the network is quiet, so the console/network observers have observed
    // the full load before the sweep.
    await page.waitForLoadState('networkidle', { timeout: 15_000 });

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

  // ---------------------------------------------------------------------
  // MULTI-COPY (CSV row 27)
  // ---------------------------------------------------------------------

  async function proveOldPasswordRejectedNewAccepted(
    browser: Browser,
    workspaceName: string,
    otherWorkspaceName: string,
    contextLabel: string,
  ): Promise<void> {
    const context = await browser.newContext({
      viewport: CSV_VIEWPORTS['1280x800'],
    });
    const page = await context.newPage();
    try {
      // P1 (pre-reset) must be rejected — dual-tenant rejection.
      const rejectPromise = page.waitForResponse(
        (response) => response.url().includes('/api/v1/auth/login'),
        { timeout: 30_000 },
      );
      await loginViaUi(page, env.m1.m.email, env.m1.m.initialPassword);
      const rejected = await rejectPromise;
      assertSan(
        rejected.status() === 401,
        `M1/${contextLabel}: pre-reset shared password must be rejected with 401 (field: status, got ${rejected.status()})`,
      );
      await expectInvalidCredentialsVisible(page);

      // P2 must be accepted and expose EXACTLY the two workspaces.
      await loginViaUi(page, env.m1.m.email, env.m1.m.newPassword);
      await expectWorkspaceSelectorWithBoth(page, workspaceName, otherWorkspaceName);
      await selectWorkspace(page, workspaceName);
    } finally {
      await context.close();
    }
  }

  test('M1', async ({ browser }) => {
    test.setTimeout(300_000);
    // Official-API provisioning precondition chain (idempotent): W1/W2
    // owners, shared identity M (same email + same P1 both sides, formal
    // admin role both sides), gate: M login exposes EXACTLY {W1, W2}.
    await ensureM1Provisioned(env);

    // Journey leg — fresh logged-out context, rendered UI only.
    const journeyContext = await browser.newContext({
      viewport: CSV_VIEWPORTS['1280x800'],
    });
    const journeyPage = await journeyContext.newPage();
    try {
      await journeyPage.goto('/forgot-password');
      const submittedAt = Date.now();
      m1State().forgotSubmittedAt = submittedAt;
      await submitForgot(journeyPage, env.m1.m.email);
      await expectNeutralForgotCopyVisible(journeyPage);
      // F6 surface: task-private maildir read, in-memory only.
      const hit = await waitForLink({
        root: env.maildirRoot,
        kind: 'reset',
        recipient: env.m1.m.email,
        sinceMs: submittedAt,
      });
      m1State().resetLink = hit.link;
      await openResetLink(journeyPage, hit.link, env.baseUrl);
      await expectResetFormRendered(journeyPage);
      const responsePromise = journeyPage.waitForResponse(
        (response) => response.url().includes('/api/v1/auth/reset-password'),
        { timeout: 30_000 },
      );
      await submitReset(journeyPage, env.m1.m.newPassword);
      const response = await responsePromise;
      assertSan(
        response.status() === 200,
        `M1: multi-copy reset must answer 200 (field: status, got ${response.status()})`,
      );
      await expectResetSuccessVisible(journeyPage);
    } finally {
      await journeyContext.close();
    }

    // Dual-context postcondition: two independent browser contexts.
    await proveOldPasswordRejectedNewAccepted(
      browser,
      env.m1.w1.companyName,
      env.m1.w2.companyName,
      'contextA',
    );
    await proveOldPasswordRejectedNewAccepted(
      browser,
      env.m1.w2.companyName,
      env.m1.w1.companyName,
      'contextB',
    );
  });
});
