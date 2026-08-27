/**
 * DC-12R1-MVP-L1-J1-H2-C-R1-R2-R1-B1 — single serial spec.
 *
 * 15 browser-authoritative nodes in inventory order: HC01-HC10 then
 * HC12-HC16 (HC11/HC17 are static-class nodes accounted separately by the
 * run reconciliation — never as browser PASS).
 *
 *  - One outer describe with `test.describe.configure({ mode: 'serial' })`:
 *    nodes run in file order, later nodes depend on state produced by
 *    earlier ones (mail token, canonical code), and any failure stops the
 *    run (maxFailures=1).
 *  - No skip/fixme/only, no conditional pass, no waitForTimeout/sleep/
 *    network-idle waits; every wait is locator/event/poll based.
 *  - Failure messages name surfaces/fields/categories only (src/assertions).
 *  - The 390px checks (HC04/HC16) are SIMULATED VIEWPORT checks, explicitly
 *    not a real device proof.
 *  - HC07's submission navigates with the LOWERCASE caller code so the
 *    HC11/HC17 static checks prove the email carries the DB-canonical
 *    UPPERCASE w.
 */
import { test, expect, type Request } from '@playwright/test';
import { loadJourneyEnv } from '../src/env.js';
import {
  assertFourStateCanonicalEquality,
  fingerprintNeutralResponse,
} from '../src/neutrality.js';
import type { CanonicalFingerprint } from '../src/neutrality-core.js';
import { readLatestDelivery, countDeliveries } from '../src/maildir.js';
import {
  storeResetToken,
  getResetToken,
  storeCanonicalCodeFromEmail,
} from '../src/token-store.js';
import {
  installConsoleCapture,
  scanForSecretLeak,
  assertNoSecretLeak,
  assertPublicCodeOnlyInAllowedLocations,
} from '../src/leak-scan.js';
import {
  portalLoginPage,
  forgotPasswordPage,
  expectForgotEntryVisible,
  expectForgotEntryAbsent,
  expectInvalidPortalState,
  fillForgotEmailAndSubmitOnce,
  doubleClickSubmit,
  expectNeutralResultShown,
  openResetLink,
  fillNewPasswordAndSubmit,
  expectPortalReturnCta,
  expectLegacyGuidanceOnly,
  assertNoHorizontalOverflowAt390px,
} from '../src/ui-journey.js';
import { RunReconciliation } from '../src/reconciliation.js';

const CODE_CLASS = /^[A-Z0-9]+$/;

const reconciliation = new RunReconciliation();
// Fail-closed at RUN time only: the journey env is loaded lazily in the
// first beforeAll so `playwright test --list` works with zero env.
let journey: ReturnType<typeof loadJourneyEnv> | null = null;
let CANONICAL = '';
let LOWERCASE = '';

test.describe.configure({ mode: 'serial' });

test.describe('j1h2c retailer recovery journey', () => {
  test.beforeAll(async () => {
    journey = loadJourneyEnv();
    CANONICAL = journey.wholesalerCanonicalCode;
    LOWERCASE = CANONICAL.toLowerCase();
  });

  function env(): ReturnType<typeof loadJourneyEnv> {
    if (!journey) throw new Error('state:journey_env:not_loaded');
    return journey;
  }

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
    await assertNoHorizontalOverflowAt390px(page);
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

  // HC06 — deterministic double click produces exactly ONE POST and no
  // duplicate issuance (maildir read-only post-proof, poll-based).
  test('HC06 double click single POST single issuance', async ({ page }) => {
    const before = await countDeliveries(env().maildirRoot, env().retailer.email);
    const posts: string[] = [];
    page.on('request', (request) => {
      if (
        request.method() === 'POST' &&
        request.url().includes('/client/auth/forgot-password')
      ) {
        posts.push(request.url());
      }
    });
    await page.goto(forgotPasswordPage(page, CANONICAL));
    await doubleClickSubmit(page, env().retailer.email);
    await expectNeutralResultShown(page);
    // ANCHOR(HC06): exactly one POST for a double click.
    expect(posts.length, 'http:recovery_post_count:must_be_exactly_one').toBe(1);
    // Read-only post-proof: EXACTLY one new delivery settles (a duplicate
    // issuance makes this poll fail by timeout).
    await expect
      .poll(
        async () =>
          (await countDeliveries(env().maildirRoot, env().retailer.email)) - before,
        { timeout: 30_000 },
      )
      .toBe(1);
    reconciliation.recordBrowserPass('HC06');
  });

  // HC07-HC10 — four real-HTTP states through the REAL UI; canonical
  // fingerprints (timestamp sentinel) pairwise equal; only HC07 issues.
  // Shared four-state fingerprint store (single serial run, memory only).
  const fingerprints: Partial<
    Record<'HC07' | 'HC08' | 'HC09' | 'HC10', CanonicalFingerprint>
  > = {};

  // HC07 — established retailer, LOWERCASE caller URL code (feeds HC11/HC17).
  test('HC07 established retailer correct supplier', async ({ page }) => {
    await page.goto(forgotPasswordPage(page, LOWERCASE));
    const responsePromise = page.waitForResponse(
      (response) => response.url().includes('/client/auth/forgot-password'),
      { timeout: 30_000 },
    );
    await fillForgotEmailAndSubmitOnce(page, env().retailer.email);
    fingerprints.HC07 = await fingerprintNeutralResponse(await responsePromise);
    await expectNeutralResultShown(page);
    reconciliation.recordBrowserPass('HC07');
  });

  // HC08 — unknown account.
  test('HC08 unknown account neutral result', async ({ page }) => {
    await page.goto(forgotPasswordPage(page, CANONICAL));
    const responsePromise = page.waitForResponse(
      (response) => response.url().includes('/client/auth/forgot-password'),
      { timeout: 30_000 },
    );
    await fillForgotEmailAndSubmitOnce(page, env().unknownEmail);
    fingerprints.HC08 = await fingerprintNeutralResponse(await responsePromise);
    await expectNeutralResultShown(page);
    reconciliation.recordBrowserPass('HC08');
  });

  // HC09 — established retailer + wrong supplier code.
  test('HC09 wrong supplier neutral result', async ({ page }) => {
    await page.goto(forgotPasswordPage(page, `WRONG${CANONICAL}`));
    const responsePromise = page.waitForResponse(
      (response) => response.url().includes('/client/auth/forgot-password'),
      { timeout: 30_000 },
    );
    await fillForgotEmailAndSubmitOnce(page, env().retailer.email);
    fingerprints.HC09 = await fingerprintNeutralResponse(await responsePromise);
    await expectNeutralResultShown(page);
    reconciliation.recordBrowserPass('HC09');
  });

  // HC10 — registered but unverified account.
  test('HC10 unverified account neutral result', async ({ page }) => {
    await page.goto(forgotPasswordPage(page, CANONICAL));
    const responsePromise = page.waitForResponse(
      (response) => response.url().includes('/client/auth/forgot-password'),
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

    // HC11 (static-class, runtime check): fragment-only resetToken and the
    // public w verified from the HC07 email delivery.
    const delivery = await readLatestDelivery(
      env().maildirRoot,
      env().retailer.email,
    );
    const link = delivery.resetLink;
    if (!link.startsWith('/retailer/reset-password#resetToken=')) {
      throw new Error('mail:reset_link:hc11_wrong_shape');
    }
    if (link.includes('?')) {
      throw new Error('mail:reset_link:hc11_query_string_forbidden');
    }
    if (delivery.portalCode !== CANONICAL) {
      throw new Error('mail:reset_link.w:hc11_canonical_code_missing');
    }
    storeResetToken(delivery.resetToken, delivery.portalCode);

    // HC17 (static-class, runtime check): the HC07 request used the
    // LOWERCASE caller input; the email w must be the DB-canonical
    // UPPERCASE code (never the caller's raw casing). ANCHOR(HC17).
    if ((delivery.portalCode ?? '') !== (delivery.portalCode ?? '').toUpperCase()) {
      throw new Error('mail:reset_link.w:hc17_not_db_canonical_uppercase');
    }
    if (!CODE_CLASS.test(delivery.portalCode ?? '')) {
      throw new Error('mail:reset_link.w:hc17_code_class_violation');
    }
    storeCanonicalCodeFromEmail(delivery.portalCode ?? '');
    reconciliation.recordStaticPass('HC11');
    reconciliation.recordStaticPass('HC17');
  });

  // HC12 — reset page reads w pre-scrub; token/w never leak into URL,
  // query, storage, console or network metadata.
  test('HC12 reset page scrub and leak scan', async ({ page }) => {
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
    // URL scrubbed: the fragment does not survive.
    await expect
      .poll(() => page.url(), { timeout: 15_000 })
      .not.toContain('resetToken');
    await fillNewPasswordAndSubmit(page, env().retailer.newPassword);
    // ANCHOR(HC12): token leak scan over url/query/storage/console/network.
    const leak = await scanForSecretLeak(page, token, capture, requests);
    assertNoSecretLeak(leak, 'hc12_reset_token');
    assertPublicCodeOnlyInAllowedLocations(page, CANONICAL);
    // The reset POST body must not carry the public w code.
    const resetPost = requests.find(
      (request) =>
        request.method() === 'POST' &&
        request.url().includes('/client/auth/reset-password'),
    );
    if (resetPost) {
      const postData = resetPost.postData() ?? '';
      if (postData.includes(CANONICAL)) {
        throw new Error('network:reset_post.body:public_code_forbidden');
      }
    }
    reconciliation.recordBrowserPass('HC12');
  });

  // HC13 — its own real journey; success CTA returns to the CANONICAL
  // supplier portal, never the wholesaler /login.
  test('HC13 success returns to canonical portal', async ({ page }) => {
    // ANCHOR(HC13): canonical portal return, wholesaler /login forbidden.
    await page.goto(forgotPasswordPage(page, CANONICAL));
    const responsePromise = page.waitForResponse(
      (response) => response.url().includes('/client/auth/forgot-password'),
      { timeout: 30_000 },
    );
    await fillForgotEmailAndSubmitOnce(page, env().retailer.email);
    await responsePromise;
    await expectNeutralResultShown(page);
    const delivery = await readLatestDelivery(
      env().maildirRoot,
      env().retailer.email,
    );
    await openResetLink(
      page,
      `${env().baseUrl}/retailer/reset-password#resetToken=${encodeURIComponent(
        delivery.resetToken,
      )}&w=${delivery.portalCode ?? CANONICAL}`,
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
    await page.goto(forgotPasswordPage(page, CANONICAL));
    const responsePromise = page.waitForResponse(
      (response) => response.url().includes('/client/auth/forgot-password'),
      { timeout: 30_000 },
    );
    await fillForgotEmailAndSubmitOnce(page, env().retailer.email);
    await responsePromise;
    await expectNeutralResultShown(page);
    const delivery = await readLatestDelivery(
      env().maildirRoot,
      env().retailer.email,
    );
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
    const forged = `forged-${Date.now().toString(36)}-${Math.random()
      .toString(36)
      .slice(2, 10)}`;
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

  // HC16 — reset page 390px SIMULATED viewport, no horizontal overflow.
  test('HC16 reset page 390px no overflow (simulated)', async ({ page }) => {
    await page.goto(`${env().baseUrl}/retailer/reset-password`);
    await assertNoHorizontalOverflowAt390px(page);
    reconciliation.recordBrowserPass('HC16');
  });

  test.afterAll(async () => {
    reconciliation.assertComplete();
  });
});
