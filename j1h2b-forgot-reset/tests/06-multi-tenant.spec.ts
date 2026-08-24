/**
 * File 06/06 — MULTI-COPY node (CSV row 27): M1.
 *
 * Execution class BROWSER_WITH_OFFICIAL_API_PRECONDITION:
 *  - beforeAll provisions through the OFFICIAL API ONLY: W1/W2 owners via the
 *    official lifecycle (different emails), the shared identity M created in
 *    BOTH tenants via POST /api/v1/users with the SAME normalized email and
 *    the SAME initial password P1, the formal admin role assigned on BOTH
 *    sides via PUT /users/{id}/roles, and the precondition gate asserting M's
 *    login exposes EXACTLY {W1, W2}.
 *  - The journey itself is pure rendered UI: forgot-password for M → maildir
 *    link (in-memory, F6 surface) → reset to P2 → success.
 *  - Postcondition: two INDEPENDENT browser contexts each prove P1 is
 *    rejected (401 + Invalid credentials) and P2 is accepted with BOTH
 *    workspaces selectable; each context then enters a different workspace.
 */

import { test, type Browser } from '@playwright/test';
import { loadJourneyEnv, type JourneyEnv } from '../src/env.js';
import { assertSan } from '../src/assertions.js';
import { m1State } from '../src/token-store.js';
import { ensureM1Provisioned } from '../src/api-client.js';
import { waitForLink } from '../src/maildir.js';
import {
  CSV_VIEWPORTS,
  openResetLink,
  expectResetFormRendered,
  expectResetSuccessVisible,
  submitReset,
  submitForgot,
  expectNeutralForgotCopyVisible,
  loginViaUi,
  expectInvalidCredentialsVisible,
  expectWorkspaceSelectorWithBoth,
  selectWorkspace,
} from '../src/ui-journey.js';

let env: JourneyEnv;

test.beforeAll(async () => {
  env = loadJourneyEnv('m1');
  await ensureM1Provisioned(env);
});

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
