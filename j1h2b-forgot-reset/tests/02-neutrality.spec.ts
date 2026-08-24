/**
 * File 02/06 — NEUTRALITY nodes (CSV rows 7-9): F3, F4, F5.
 *
 * F3 submits the forgot form for the ACTIVE identity A1 (provisioned through
 * the official lifecycle in beforeAll — API is authorized for provisioning
 * preconditions only). F4 submits a never-registered email. F5 submits an
 * ineligible email (exists only as a soft-deleted user, provisioned through
 * the official API). All three submissions go through the rendered UI.
 *
 * F3's fingerprint (status/body-hash/body-length, raw body discarded) and the
 * visible neutral copy are the comparison anchors for F4/F5. F3's submission
 * is also the mail event that F6 (non-browser maildir helper) later reads the
 * journey reset link from — a1State().f3SubmittedAt is the maildir `since`
 * anchor for the R-series.
 */

import { test } from '@playwright/test';
import { loadJourneyEnv, type JourneyEnv } from '../src/env.js';
import { assertSan } from '../src/assertions.js';
import { a1State } from '../src/token-store.js';
import { captureForgotFingerprint, sameFingerprint, firstFingerprintDifference } from '../src/neutrality.js';
import { ensureA1Provisioned, ensureIneligibleEmailProvisioned } from '../src/api-client.js';
import { negativeWindowHasLink } from '../src/maildir.js';
import {
  setViewportFromCsv,
  submitForgot,
  expectNeutralForgotCopyVisible,
} from '../src/ui-journey.js';

let env: JourneyEnv;

test.beforeAll(async () => {
  env = loadJourneyEnv('a1', 'unknown', 'ineligible');
  await ensureA1Provisioned(env);
  await ensureIneligibleEmailProvisioned(env);
});

test('F3', async ({ page }) => {
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
  assertSan(f3 !== undefined, 'F4: F3 anchor fingerprint missing (journey order violated)');
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
  assertSan(f3 !== undefined, 'F5: F3 anchor fingerprint missing (journey order violated)');
  assertSan(f5 !== undefined, 'F5: forgot-password response was not captured (field: response fingerprint)');
  assertSan(f5.status === 200, 'F5: forgot-password must answer HTTP 200 neutral (field: status)');
  assertSan(
    visibleText === a1State().neutralVisibleText,
    'F5: visible neutral copy differs from F3 (field: visibleText)',
  );
  // Read-only postcondition (protocol §4): zero mail for the ineligible
  // identity over the negative window ⇒ zero token issued (reset tokens are
  // only ever delivered through the email sink).
  const mailAppeared = await negativeWindowHasLink({
    root: env.maildirRoot,
    kind: 'reset',
    recipient: env.ineligible.email,
    sinceMs: submittedAt,
    windowMs: 15_000,
  });
  assertSan(!mailAppeared, 'F5: a reset link appeared in the maildir for the ineligible identity (field: recipient)');
});
