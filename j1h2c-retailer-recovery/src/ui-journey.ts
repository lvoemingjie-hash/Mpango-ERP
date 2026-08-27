/**
 * Real-UI journey helpers — B1-R1 (Kilo F closure).
 *
 * Every forgot/reset journey action goes through the REAL rendered UI.
 * The HC06 double click uses Playwright's REAL dblclick action (full
 * actionability pipeline: visible, stable, receives events, enabled) —
 * never two synthetic dispatchEvent('click') calls (Kilo F).
 * No waitForTimeout, no fixed sleeps, no networkidle waits.
 */

import type { Page } from '@playwright/test';
import { fieldOnly } from './assertions.js';

export function portalLoginPage(page: Page, code: string): string {
  return `/retail/login?w=${encodeURIComponent(code)}`;
}

export function forgotPasswordPage(page: Page, code: string): string {
  return `/retailer/forgot-password?w=${encodeURIComponent(code)}`;
}

export async function expectForgotEntryVisible(page: Page): Promise<void> {
  const entry = page.getByRole('link', { name: /forgot password\?/i });
  if (!(await entry.isVisible())) {
    throw fieldOnly('ui', 'forgot_entry', 'not_visible');
  }
}

export async function expectForgotEntryAbsent(page: Page): Promise<void> {
  const entry = page.getByRole('link', { name: /forgot password\?/i });
  if (await entry.isVisible()) {
    throw fieldOnly('ui', 'forgot_entry', 'unexpectedly_visible');
  }
}

export async function expectInvalidPortalState(page: Page): Promise<void> {
  const heading = page.getByRole('heading', { name: /invalid portal/i });
  if (!(await heading.isVisible())) {
    throw fieldOnly('ui', 'invalid_portal', 'not_visible');
  }
}

export async function fillForgotEmailAndSubmitOnce(
  page: Page,
  email: string,
): Promise<void> {
  const input = page.getByLabel(/^email/i);
  await input.fill(email);
  await page.getByRole('button', { name: /send reset link/i }).click();
}

/**
 * HC06 genuine user double click (Kilo F): Playwright's real dblclick —
 * a single trusted OS-level double-click event sequence through the full
 * actionability pipeline. Never two synthetic dispatchEvent calls.
 */
export async function genuineDoubleClickSubmit(
  page: Page,
  email: string,
): Promise<void> {
  const input = page.getByLabel(/^email/i);
  await input.fill(email);
  await page.getByRole('button', { name: /send reset link/i }).dblclick();
}

export async function expectNeutralResultShown(page: Page): Promise<void> {
  await page.getByTestId('forgot-neutral-result').waitFor({ state: 'visible' });
}

export async function openResetLink(page: Page, resetLink: string): Promise<void> {
  // The fragment carries the secret; navigate once and let the page scrub.
  await page.goto(resetLink);
}

export async function fillNewPasswordAndSubmit(
  page: Page,
  newPassword: string,
): Promise<void> {
  const input = page.getByLabel(/new password/i);
  await input.fill(newPassword);
  await page.getByRole('button', { name: /reset password/i }).click();
}

export async function expectPortalReturnCta(page: Page): Promise<void> {
  const cta = page.getByTestId('reset-success-portal-link');
  await cta.waitFor({ state: 'visible' });
  const href = await cta.getAttribute('href');
  if (href === null || !href.startsWith('/retail/login?w=')) {
    throw fieldOnly('ui', 'reset_success_cta.href', 'not_canonical_portal');
  }
  if (href === '/login' || href.startsWith('/login?')) {
    throw fieldOnly('ui', 'reset_success_cta.href', 'wholesaler_login_forbidden');
  }
}

export async function expectLegacyGuidanceOnly(page: Page): Promise<void> {
  const legacy = page.getByTestId('reset-success-legacy');
  await legacy.waitFor({ state: 'visible' });
  const text = (await legacy.textContent()) ?? '';
  if (!/portal link your supplier provided/i.test(text)) {
    throw fieldOnly('ui', 'reset_success_legacy', 'guidance_text_missing');
  }
  const wholesalerCta = page.getByRole('link', { name: /go to login/i });
  if (await wholesalerCta.isVisible()) {
    throw fieldOnly('ui', 'reset_success_legacy', 'wholesaler_cta_forbidden');
  }
  const portalCta = page.getByTestId('reset-success-portal-link');
  if (await portalCta.isVisible()) {
    throw fieldOnly('ui', 'reset_success_legacy', 'portal_cta_forbidden');
  }
}

/**
 * 390px simulated viewport interactive-form proof (Kilo G): the REAL reset
 * form must be present (new-password control visible AND editable) and
 * BOTH documentElement and body must have zero horizontal overflow.
 * An invalid/missing-token neutral page can never satisfy this helper.
 * Explicitly NOT a real-device proof.
 */
export async function assertInteractiveNoOverflowAt390px(page: Page): Promise<void> {
  await page.setViewportSize({ width: 390, height: 844 });
  const control = page.getByLabel(/new password/i);
  await control.waitFor({ state: 'visible' });
  await control.fill('Probe-Pass-390px!');
  const controlEditable = await control.evaluate((node) => {
    return node instanceof HTMLInputElement && node.value === 'Probe-Pass-390px!';
  });
  if (!controlEditable) {
    throw fieldOnly('ui', 'viewport_390px.control', 'not_editable');
  }
  const overflow = await page.evaluate(() => {
    const doc = document.documentElement;
    const body = document.body;
    return {
      documentOverflow: doc.scrollWidth > doc.clientWidth,
      bodyOverflow: body.scrollWidth > body.clientWidth,
    };
  });
  if (overflow.documentOverflow || overflow.bodyOverflow) {
    throw fieldOnly('ui', 'viewport_390px', 'horizontal_overflow');
  }
}
