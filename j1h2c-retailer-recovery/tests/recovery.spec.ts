/**
 * DC-12R1-MVP-L1-J1-H2-C-R1-R2-R1-B1(+R1) — single serial spec.
 *
 * 15 browser-authoritative nodes in inventory order: HC01-HC10 then
 * HC12-HC16 (HC11/HC17 are static-class nodes accounted separately by the
 * run reconciliation — never as browser PASS).
 *
 * B1-R1 Kilo A-I closures implemented here:
 *   A  HC12 observes EXACTLY ONE reset POST via a waitForRequest installed
 *      BEFORE the click; asserts 200 + success UI; asserts the JSON body
 *      key set is exactly {reset_token, new_password} and reset_token
 *      equals the in-memory token; w and extra fields are forbidden.
 *      A missing reset POST is deterministically RED (wait timeout).
 *   B  the public w is scanned across request URLs/headers/bodies,
 *      storage, and console — allowed ONLY in the initial fragment and
 *      the canonical /retail/login?w= URL.
 *   C  HC09 uses a REAL second supplier (W2 canonical code from env); the
 *      target retailer belongs to W1 only. No fabricated codes.
 *   D  beforeAll runs the formal-API PRECONDITION provisioning
 *      (api-client.provisionPreconditions); it is a precondition, never a
 *      browser PASS; --list still works env-free (lazy env load).
 *   E  HC07 snapshots the maildir BEFORE submitting, polls for EXACTLY
 *      ONE new delivery, parses only that file, and validates the link
 *      exactly (pathname, empty query, fragment key set, canonical w).
 *   F  HC06 uses Playwright's genuine dblclick (actionability pipeline).
 *   G  HC16 opens a REAL fresh reset form (new token + w), proves the
 *      control is visible+editable at 390x844, and that BOTH
 *      documentElement and body have zero horizontal overflow.
 *   H  afterAll ALWAYS publishes reconciliation.json/.csv (true partial
 *      state on failure) and clears the token-store; the first browser
 *      failure is never masked.
 *
 * Frozen: single serial describe, maxFailures=1, no skip/fixme/only, no
 * waitForTimeout/sleep/network-idle waits; failure output names
 * surfaces/fields/categories only.
 */
import { test, expect, type Request } from '@playwright/test';
import { loadJourneyEnv } from '../src/env.js';
import {
  assertFourStateCanonicalEquality,
  fingerprintNeutralResponse,
} from '../src/neutrality.js';
import type { CanonicalFingerprint } from '../src/neutrality-core.js';
import {
  snapshotDeliveries,
  pollForExactlyOneNewDelivery,
  parseAndValidateResetLink,
} from '../src/maildir.js';
import { runPreconditions } from '../src/preconditions.js';
import {
  storeResetToken,
  getResetToken,
  clearMemoryState,
} from '../src/token-store.js';
import {
  installConsoleCapture,
  scanTokenLeak,
  assertNoTokenLeak,
  scanPublicCode,
  assertPublicCodeClean,
} from '../src/leak-scan.js';
import {
  portalLoginPage,
  forgotPasswordPage,
  expectForgotEntryVisible,
  expectForgotEntryAbsent,
  expectInvalidPortalState,
  fillForgotEmailAndSubmitOnce,
  genuineDoubleClickSubmit,
  expectNeutralResultShown,
  openResetLink,
  fillNewPasswordAndSubmit,
  expectPortalReturnCta,
  expectLegacyGuidanceOnly,
  assertInteractiveNoOverflowAt390px,
} from '../src/ui-journey.js';
import { RunReconciliation } from '../src/reconciliation.js';

const RESET_POST_URL_FRAGMENT = '/client/auth/reset-password';
const FORGOT_POST_URL_FRAGMENT = '/client/auth/forgot-password';
const CODE_CLASS = /^[A-Z0-9]+$/;

const reconciliation = new RunReconciliation();
// Fail-closed at RUN time only: lazy so `playwright test --list` works
// with zero env (Kilo D #6).
let journey: ReturnType<typeof loadJourneyEnv> | null = null;
let CANONICAL = '';
let LOWERCASE = '';
let W2 = '';

function env(): ReturnType<typeof loadJourneyEnv> {
  if (!journey) throw new Error('state:journey_env:not_loaded');
  return journey;
}

test.describe.configure({ mode: 'serial' });

let firstFailedNodeId: string | undefined;

test.describe('j1h2c retailer recovery journey', () => {
  test.afterEach(async ({}, testInfo) => {
    if (testInfo.status !== testInfo.expectedStatus && firstFailedNodeId === undefined) {
      firstFailedNodeId = undefined; // resolved from title below
      const match = testInfo.title.match(/^(HC\d+)/);
      firstFailedNodeId = match ? match[1] : undefined;
    }
  });

  test.beforeAll(async () => {
    journey = loadJourneyEnv();
    CANONICAL = journey.w1CanonicalCode;
    LOWERCASE = CANONICAL.toLowerCase();
    W2 = journey.w2CanonicalCode;
    // Kilo D (B1-R2): STRICT executable launcher/precondition contract —
    // fresh invitations, 2xx-only register, full official lifecycle,
    // unverified stop-proof, W2 proofs, dual-mailbox snapshot persistence.
    // Never a browser node PASS.
    // B1-R3: a precondition failure is accounted as PRECONDITION_FAIL with
    // ALL 17 nodes NOT_RUN — never fabricated as node FAILs — and the
    // truthful artifact is still published before rethrowing.
    try {
      await runPreconditions(journey);
    } catch (error) {
      reconciliation.recordPreconditionFail();
      reconciliation.publishArtifacts('artifacts');
      throw error;
    }
  });

  test.afterAll(async () => {
    // B1-R3-R1 PUBLICATION ORDERING TRUTH:
    //   1. classify the true outcomes FIRST (precondition failure keeps the
    //      17 NOT_RUN set recorded by recordPreconditionFail; a browser
    //      failure is classified exactly via markOutcomesAfterFailure);
    //   2. PUBLISH the reconciliation artifact BEFORE any completeness
    //      judgment, so a missing record can never leave the run without
    //      its truthful (possibly incomplete) reconciliation.json/csv;
    //   3. ONLY on surface success (no first failure, precondition pass)
    //      assert completeness — a missing record then throws (teardown
    //      error -> non-zero exit) WITH the truthful artifact already on
    //      disk. Publication/classification errors never mask the first
    //      browser failure; clearMemoryState always runs in finally.
    try {
      if (firstFailedNodeId !== undefined) {
        // Browser-node failure path: exact PASS/FAIL/NOT_RUN, then publish.
        reconciliation.markOutcomesAfterFailure(firstFailedNodeId);
        reconciliation.publishArtifacts('artifacts');
      } else if (reconciliation.summary().preconditionOutcome === 'PRECONDITION_FAIL') {
        // Precondition-failure path: 17 NOT_RUN already recorded; publish.
        reconciliation.publishArtifacts('artifacts');
      } else {
        // Surface-success path: publish the TRUE state first, THEN judge.
        reconciliation.publishArtifacts('artifacts');
        reconciliation.assertComplete();
      }
    } finally {
      clearMemoryState();
    }
  });

  // HC01 — valid portal shows the discovery entry carrying the code.
  test('HC01 valid portal shows Forgot password entry', async ({ page }) => {
    await page.goto(portalLoginPage(page, CANONICAL));
    await expectForgotEntryVisible(page);
    const href = await page
      .getByRole('link', { name: /forgot password\?/i })
      .getAttribute('href');
    expect(href, 'ui:forgot_entry.href:missing_canonical_code').toContain(
      `/retailer/forgot-password?w=${CANONICAL}`,
    );
    reconciliation.recordBrowserPass('HC01');
  });

  // HC02 — missing w AND malformed w=BAD%21: entry absent, neutral state,
  // zero recovery POST.
  test('HC02 invalid portal hides entry with zero POST', async ({ page }) => {
    const posts: string[] = [];
    page.on('request', (request) => {
      if (request.method() === 'POST' && request.url().includes('/client/auth/')) {
        posts.push(request.url());
      }
    });
    await page.goto('/retail/login');
    await expectInvalidPortalState(page);
    await expectForgotEntryAbsent(page);
    await page.goto(`/retail/login?w=${encodeURIComponent('BAD!')}`);
    await expectInvalidPortalState(page);
    await expectForgotEntryAbsent(page);
    // ANCHOR(HC02): zero recovery POST on invalid portal.
    expect(posts.length, 'http:recovery_post_count:must_be_zero').toBe(0);
    reconciliation.recordBrowserPass('HC02');
  });

  // HC03 — discovery route renders the email form for a valid portal.
  test('HC03 forgot page renders email form', async ({ page }) => {
    await page.goto(forgotPasswordPage(page, CANONICAL));
    await expect(page.getByLabel(/^email/i)).toBeVisible();
    await expect(page.getByRole('button', { name: /send reset link/i })).toBeVisible();
    const back = await page
      .getByRole('link', { name: /back to sign in/i })
      .getAttribute('href');
    expect(back, 'ui:back_link.href:not_portal').toBe(`/retail/login?w=${CANONICAL}`);
    reconciliation.recordBrowserPass('HC03');
  });

  // HC04 — 390px SIMULATED viewport, no horizontal overflow (not a real
  // device).
  test('HC04 forgot page 390px no overflow (simulated)', async ({ page }) => {
    await page.goto(forgotPasswordPage(page, CANONICAL));
    await page.setViewportSize({ width: 390, height: 844 });
    const overflow = await page.evaluate(() => {
      const doc = document.documentElement;
      const body = document.body;
      return {
        doc: doc.scrollWidth > doc.clientWidth,
        body: body.scrollWidth > body.clientWidth,
      };
    });
    expect(overflow.doc || overflow.body, 'ui:viewport_390px:horizontal_overflow').toBe(false);
    reconciliation.recordBrowserPass('HC04');
  });

  // HC05 — client-side validation blocks empty/malformed email with zero
  // recovery POST.
  test('HC05 invalid email blocked with zero POST', async ({ page }) => {
    const posts: string[] = [];
    page.on('request', (request) => {
      if (request.method() === 'POST' && request.url().includes('/client/auth/')) {
        posts.push(request.url());
      }
    });
    await page.goto(forgotPasswordPage(page, CANONICAL));
    await page.getByRole('button', { name: /send reset link/i }).click();
    await expect(page.getByText(/valid email address/i)).toBeVisible();
    await page.getByLabel(/^email/i).fill('not-an-email');
    await page.getByRole('button', { name: /send reset link/i }).click();
    await expect(page.getByText(/valid email address/i)).toBeVisible();
    // ANCHOR(HC05): zero recovery POST on validation failure.
    expect(posts.length, 'http:recovery_post_count:must_be_zero').toBe(0);
    reconciliation.recordBrowserPass('HC05');
  });

  // HC06 — GENUINE user double click (Kilo F): exactly ONE POST and no
  // duplicate issuance (maildir snapshot + poll post-proof).
  test('HC06 genuine double click single POST single issuance', async ({ page }) => {
    const before = await snapshotDeliveries(env().maildirRoot, env().retailer.email);
    const posts: Request[] = [];
    page.on('request', (request) => {
      if (
        request.method() === 'POST' &&
        request.url().includes(FORGOT_POST_URL_FRAGMENT)
      ) {
        posts.push(request);
      }
    });
    await page.goto(forgotPasswordPage(page, CANONICAL));
    await genuineDoubleClickSubmit(page, env().retailer.email);
    await expectNeutralResultShown(page);
    // ANCHOR(HC06): exactly one POST for a genuine double click.
    expect(posts.length, 'http:recovery_post_count:must_be_exactly_one').toBe(1);
    // Read-only post-proof: EXACTLY one new delivery settles; a duplicate
    // issuance (two new files) fails deterministically.
    const fresh = await pollForExactlyOneNewDelivery(
      env().maildirRoot,
      env().retailer.email,
      before,
      { timeoutMs: 30_000 },
    );
    void fresh;
    reconciliation.recordBrowserPass('HC06');
  });

  // Shared four-state fingerprint store (single serial run, memory only).
  const fingerprints: Partial<
    Record<'HC07' | 'HC08' | 'HC09' | 'HC10', CanonicalFingerprint>
  > = {};

  // HC07 — established W1 retailer, LOWERCASE caller URL code (feeds
  // HC11/HC17 with fresh-mail evidence).
  test('HC07 established retailer correct supplier', async ({ page }) => {
    // Kilo E #1: snapshot BEFORE the submission.
    const mailSnapshot = await snapshotDeliveries(
      env().maildirRoot,
      env().retailer.email,
    );
    await page.goto(forgotPasswordPage(page, LOWERCASE));
    const responsePromise = page.waitForResponse(
      (response) => response.url().includes(FORGOT_POST_URL_FRAGMENT),
      { timeout: 30_000 },
    );
    await fillForgotEmailAndSubmitOnce(page, env().retailer.email);
    fingerprints.HC07 = await fingerprintNeutralResponse(await responsePromise);
    await expectNeutralResultShown(page);
    reconciliation.recordBrowserPass('HC07');

    // Kilo E #2/#3: poll for EXACTLY ONE new delivery; parse only it.
    const fresh = await pollForExactlyOneNewDelivery(
      env().maildirRoot,
      env().retailer.email,
      mailSnapshot,
      { timeoutMs: 30_000 },
    );
    // Kilo E #6: exact validation — pathname, empty query, fragment key
    // set, canonical w. Supports relative AND absolute links.
    const delivery = parseAndValidateResetLink(fresh.link, {
      requireCanonicalW: CANONICAL,
    });
    storeResetToken(delivery.resetToken, delivery.portalCode);

    // HC17 (static-class, runtime check): the HC07 request used the
    // LOWERCASE caller input; the email w must be the DB-canonical
    // UPPERCASE code. ANCHOR(HC17).
    if ((delivery.portalCode ?? '') !== (delivery.portalCode ?? '').toUpperCase()) {
      throw new Error('mail:reset_link.w:hc17_not_db_canonical_uppercase');
    }
    if (!CODE_CLASS.test(delivery.portalCode ?? '')) {
      throw new Error('mail:reset_link.w:hc17_code_class_violation');
    }
    reconciliation.recordStaticPass('HC11');
    reconciliation.recordStaticPass('HC17');
  });

  // HC08 — unknown account.
  test('HC08 unknown account neutral result', async ({ page }) => {
    await page.goto(forgotPasswordPage(page, CANONICAL));
    const responsePromise = page.waitForResponse(
      (response) => response.url().includes(FORGOT_POST_URL_FRAGMENT),
      { timeout: 30_000 },
    );
    await fillForgotEmailAndSubmitOnce(page, env().unknownEmail);
    fingerprints.HC08 = await fingerprintNeutralResponse(await responsePromise);
    await expectNeutralResultShown(page);
    reconciliation.recordBrowserPass('HC08');
  });

  // HC09 — REAL second supplier (Kilo C): the retailer belongs to W1; a
  // valid W2 portal form is shown; exactly one POST; neutral result.
  test('HC09 genuine wrong supplier neutral result', async ({ page }) => {
    // ANCHOR(HC09): real W2 canonical code from env — never fabricated.
    await page.goto(forgotPasswordPage(page, W2));
    await expect(page.getByLabel(/^email/i)).toBeVisible();
    const posts: Request[] = [];
    page.on('request', (request) => {
      if (
        request.method() === 'POST' &&
        request.url().includes(FORGOT_POST_URL_FRAGMENT)
      ) {
        posts.push(request);
      }
    });
    const responsePromise = page.waitForResponse(
      (response) => response.url().includes(FORGOT_POST_URL_FRAGMENT),
      { timeout: 30_000 },
    );
    await fillForgotEmailAndSubmitOnce(page, env().retailer.email);
    fingerprints.HC09 = await fingerprintNeutralResponse(await responsePromise);
    await expectNeutralResultShown(page);
    expect(posts.length, 'http:recovery_post_count:must_be_exactly_one').toBe(1);
    reconciliation.recordBrowserPass('HC09');
  });

  // HC10 — registered but unverified W1 account.
  test('HC10 unverified account neutral result', async ({ page }) => {
    await page.goto(forgotPasswordPage(page, CANONICAL));
    const responsePromise = page.waitForResponse(
      (response) => response.url().includes(FORGOT_POST_URL_FRAGMENT),
      { timeout: 30_000 },
    );
    await fillForgotEmailAndSubmitOnce(page, env().unverifiedEmail);
    fingerprints.HC10 = await fingerprintNeutralResponse(await responsePromise);
    await expectNeutralResultShown(page);
    // ANCHOR(HC07-HC10): canonical equality with ONLY the timestamp
    // sentinel replaced; raw bodies already released.
    assertFourStateCanonicalEquality({
      HC07: fingerprints.HC07 as CanonicalFingerprint,
      HC08: fingerprints.HC08 as CanonicalFingerprint,
      HC09: fingerprints.HC09 as CanonicalFingerprint,
      HC10: fingerprints.HC10 as CanonicalFingerprint,
    });
    reconciliation.recordBrowserPass('HC10');
  });

  // HC12 — Kilo A/B closure: exactly-one reset POST observed; body shape
  // asserted; token/w leak scanned across every surface.
  test('HC12 reset POST observed with full leak scan', async ({ page }) => {
    const token = getResetToken();
    if (!token) {
      throw new Error('state:reset_token:missing_for_hc12');
    }
    const capture = installConsoleCapture(page);
    const requests: Request[] = [];
    page.on('request', (request) => requests.push(request));
    await openResetLink(
      page,
      `${env().baseUrl}/retailer/reset-password#resetToken=${encodeURIComponent(token)}&w=${CANONICAL}`,
    );
    await expect(page.getByLabel(/new password/i)).toBeVisible();
    await expect
      .poll(() => page.url(), { timeout: 15_000 })
      .not.toContain('resetToken');
    // Kilo A #1: waitForRequest installed BEFORE the click.
    const resetPostPromise = page.waitForRequest(
      (request) =>
        request.method() === 'POST' &&
        request.url().includes(RESET_POST_URL_FRAGMENT),
      { timeout: 30_000 },
    );
    await fillNewPasswordAndSubmit(page, env().retailer.newPassword);
    const resetPost = await resetPostPromise; // missing POST => timeout RED
    // Kilo A #2: exactly one reset POST.
    const resetPosts = requests.filter(
      (request) =>
        request.method() === 'POST' &&
        request.url().includes(RESET_POST_URL_FRAGMENT),
    );
    expect(resetPosts.length, 'http:reset_post_count:must_be_exactly_one').toBe(1);
    // Kilo A #3: contract-conformant response and success UI.
    const resetResponse = await resetPost.response();
    expect(resetResponse?.status(), 'http:reset_post.status:expected_200').toBe(200);
    await expect(page.getByText(/has been reset successfully/i)).toBeVisible();
    // Kilo A #4/#5: JSON body exact key set; reset_token equals the
    // in-memory token; w and extra fields forbidden.
    const bodyText = resetPost.postData() ?? '';
    let body: Record<string, unknown>;
    try {
      body = JSON.parse(bodyText) as Record<string, unknown>;
    } catch {
      throw new Error('http:reset_post.body:not_json');
    }
    expect(
      Object.keys(body).sort().join(','),
      'http:reset_post.body.keys:exact_set',
    ).toBe('new_password,reset_token');
    if (body.reset_token !== token) {
      throw new Error('http:reset_post.body.reset_token:mismatch_with_memory');
    }
    if (bodyText.includes(CANONICAL)) {
      throw new Error('http:reset_post.body:public_code_forbidden');
    }
    // Kilo A #7 + B: full-surface scans (legitimate reset_token body
    // field excluded by the scanner itself).
    const tokenLeak = await scanTokenLeak(page, token, capture, requests);
    assertNoTokenLeak(tokenLeak);
    const codeLeak = await scanPublicCode(page, CANONICAL, capture, requests);
    assertPublicCodeClean(codeLeak);
    reconciliation.recordBrowserPass('HC12');
  });

  // HC13 — success CTA returns to the CANONICAL supplier portal, never the
  // wholesaler /login. Its own real journey (fresh token from a fresh
  // forgot submission with exact fresh-mail parsing).
  test('HC13 success returns to canonical portal', async ({ page }) => {
    // ANCHOR(HC13): canonical portal return, wholesaler /login forbidden.
    const mailSnapshot = await snapshotDeliveries(
      env().maildirRoot,
      env().retailer.email,
    );
    await page.goto(forgotPasswordPage(page, CANONICAL));
    const responsePromise = page.waitForResponse(
      (response) => response.url().includes(FORGOT_POST_URL_FRAGMENT),
      { timeout: 30_000 },
    );
    await fillForgotEmailAndSubmitOnce(page, env().retailer.email);
    await responsePromise;
    await expectNeutralResultShown(page);
    const fresh = await pollForExactlyOneNewDelivery(
      env().maildirRoot,
      env().retailer.email,
      mailSnapshot,
      { timeoutMs: 30_000 },
    );
    const delivery = parseAndValidateResetLink(fresh.link, {
      requireCanonicalW: CANONICAL,
    });
    await openResetLink(
      page,
      delivery.resetLink.startsWith('http')
        ? delivery.resetLink
        : `${env().baseUrl}${delivery.resetLink}`,
    );
    await fillNewPasswordAndSubmit(page, env().retailer.newPassword);
    await expectPortalReturnCta(page);
    const href = await page
      .getByTestId('reset-success-portal-link')
      .getAttribute('href');
    expect(href, 'ui:reset_success_cta.href:not_canonical_portal').toBe(
      `/retail/login?w=${CANONICAL}`,
    );
    const wholesalerCta = page.getByRole('link', { name: /go to login/i });
    await expect(wholesalerCta).toHaveCount(0);
    reconciliation.recordBrowserPass('HC13');
  });

  // HC14 — legacy link: REAL valid token WITHOUT w; still resets through
  // the UI; success shows ONLY the neutral supplier guidance.
  test('HC14 legacy valid-token link neutral guidance', async ({ page }) => {
    // ANCHOR(HC14): legacy = real token, no w; UI reset; guidance only.
    const mailSnapshot = await snapshotDeliveries(
      env().maildirRoot,
      env().retailer.email,
    );
    await page.goto(forgotPasswordPage(page, CANONICAL));
    const responsePromise = page.waitForResponse(
      (response) => response.url().includes(FORGOT_POST_URL_FRAGMENT),
      { timeout: 30_000 },
    );
    await fillForgotEmailAndSubmitOnce(page, env().retailer.email);
    await responsePromise;
    await expectNeutralResultShown(page);
    const fresh = await pollForExactlyOneNewDelivery(
      env().maildirRoot,
      env().retailer.email,
      mailSnapshot,
      { timeoutMs: 30_000 },
    );
    const delivery = parseAndValidateResetLink(fresh.link);
    // Re-strip w to construct the legacy shape from the REAL token.
    const legacyLink = `${env().baseUrl}/retailer/reset-password#resetToken=${encodeURIComponent(
      delivery.resetToken,
    )}`;
    await openResetLink(page, legacyLink);
    await fillNewPasswordAndSubmit(page, env().retailer.currentPassword);
    await expectLegacyGuidanceOnly(page);
    reconciliation.recordBrowserPass('HC14');
  });

  // HC15 — runtime-forged token: neutral invalid/expired behavior; the
  // failure output never includes the token value.
  test('HC15 forged token neutral failure', async ({ page }) => {
    // B1-R2 (Kilo I #4): the launcher-injected unique forged token.
    const forged = env().forgedResetToken;
    await openResetLink(
      page,
      `${env().baseUrl}/retailer/reset-password#resetToken=${encodeURIComponent(
        forged,
      )}&w=${CANONICAL}`,
    );
    await fillNewPasswordAndSubmit(page, env().retailer.newPassword);
    await expect(page.getByText(/invalid or expired/i)).toBeVisible();
    reconciliation.recordBrowserPass('HC15');
  });

  // HC16 — Kilo G closure: REAL fresh reset form at 390x844; control
  // visible+editable; documentElement AND body zero horizontal overflow.
  test('HC16 real reset form 390px interactive no overflow', async ({ page }) => {
    // ANCHOR(HC16): fresh valid token + w; genuine interactive form.
    const mailSnapshot = await snapshotDeliveries(
      env().maildirRoot,
      env().retailer.email,
    );
    await page.goto(forgotPasswordPage(page, CANONICAL));
    const responsePromise = page.waitForResponse(
      (response) => response.url().includes(FORGOT_POST_URL_FRAGMENT),
      { timeout: 30_000 },
    );
    await fillForgotEmailAndSubmitOnce(page, env().retailer.email);
    await responsePromise;
    await expectNeutralResultShown(page);
    const fresh = await pollForExactlyOneNewDelivery(
      env().maildirRoot,
      env().retailer.email,
      mailSnapshot,
      { timeoutMs: 30_000 },
    );
    const delivery = parseAndValidateResetLink(fresh.link, {
      requireCanonicalW: CANONICAL,
    });
    await openResetLink(
      page,
      delivery.resetLink.startsWith('http')
        ? delivery.resetLink
        : `${env().baseUrl}${delivery.resetLink}`,
    );
    await assertInteractiveNoOverflowAt390px(page);
    reconciliation.recordBrowserPass('HC16');
  });
});
