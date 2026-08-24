/**
 * Shared rendered-UI journey steps.
 *
 * Every forgot/reset journey action in the specs goes through these helpers
 * so that "the real UI is the only journey driver" is structurally true
 * (task directive #8). Selectors and copy are pinned to the frozen product
 * anchors reviewed at parent commit 8c462170:
 *   - LoginPage.tsx: "Forgot password?" link, #email/#password, "Sign In",
 *     server error "Invalid credentials", /select-workspace for multi-tenant.
 *   - ForgotPasswordPage.tsx: #email, "Send reset instructions", neutral copy
 *     "If an account exists, reset instructions will be sent."
 *   - ResetPasswordPage.tsx: #newPassword, "Reset password",
 *     "Password must be at least 8 characters",
 *     "This reset link is invalid or expired. Please request a new link.",
 *     "Invalid Link" / "Request new link",
 *     "Your password has been reset successfully." / "Go to login".
 *
 * Viewport note (task directive #16): the three CSV viewports are simulated
 * viewport sizes on a desktop browser engine — they are NOT real phones and
 * are never reported as such.
 */

import type { Page, Locator } from '@playwright/test';
import { expect } from '@playwright/test';
import { assertSan } from './assertions.js';

export const CSV_VIEWPORTS = {
  '1280x800': { width: 1280, height: 800 },
  '768x1024': { width: 768, height: 1024 },
  '390x844': { width: 390, height: 844 },
} as const;

export type CsvViewport = keyof typeof CSV_VIEWPORTS;

export function setViewportFromCsv(page: Page, viewport: CsvViewport): void {
  page.setViewportSize(CSV_VIEWPORTS[viewport]);
}

export const UI_COPY = {
  forgotLink: 'Forgot password?',
  forgotHeading: 'Reset your password',
  forgotSubmit: 'Send reset instructions',
  forgotNeutral: 'If an account exists, reset instructions will be sent.',
  resetHeading: 'Choose a new password',
  resetSubmit: 'Reset password',
  resetPolicyError: 'Password must be at least 8 characters',
  resetServerError: 'This reset link is invalid or expired. Please request a new link.',
  resetInvalidLink: 'Invalid Link',
  resetRequestNewLink: 'Request new link',
  resetSuccess: 'Your password has been reset successfully.',
  resetGoToLogin: 'Go to login',
  loginSubmit: 'Sign In',
  loginInvalidCredentials: 'Invalid credentials',
  workspaceHeading: 'Welcome Back',
} as const;

export function forgotLinkLocator(page: Page): Locator {
  return page.getByRole('link', { name: UI_COPY.forgotLink });
}

export async function expectForgotEntryVisible(page: Page): Promise<void> {
  await expect(forgotLinkLocator(page)).toBeVisible();
}

export async function clickForgotEntry(page: Page): Promise<void> {
  await forgotLinkLocator(page).click();
  await expect(page.getByRole('heading', { name: UI_COPY.forgotHeading })).toBeVisible();
}

export async function expectForgotFormStructure(page: Page): Promise<void> {
  await expect(page.getByRole('heading', { name: UI_COPY.forgotHeading })).toBeVisible();
  await expect(page.locator('#email')).toBeVisible();
  await expect(page.getByRole('button', { name: UI_COPY.forgotSubmit })).toBeVisible();
  // 表单无多余字段: exactly one input, and it is the email field.
  const inputCount = await page.locator('form input').count();
  assertSan(inputCount === 1, 'forgot-password form must expose exactly one input (field: form input count)');
}

export async function submitForgot(page: Page, email: string): Promise<void> {
  await page.locator('#email').fill(email);
  await page.getByRole('button', { name: UI_COPY.forgotSubmit }).click();
}

export async function expectNeutralForgotCopyVisible(page: Page): Promise<string> {
  const message = page.getByText(UI_COPY.forgotNeutral, { exact: true });
  await expect(message).toBeVisible();
  const text = await message.textContent();
  return (text ?? '').trim();
}

/**
 * Open a maildir-derived reset link in the browser. The link origin must
 * equal the run's frontend origin (operator contract: PUBLIC_FRONTEND_URL ==
 * J1H2B_BASE_URL); mismatches fail closed with a names-only error.
 */
export async function openResetLink(page: Page, link: string, baseUrl: string): Promise<void> {
  let parsed: URL;
  try {
    parsed = new URL(link);
  } catch {
    throw new Error('reset link is not a parseable absolute URL (value withheld)');
  }
  assertSan(
    parsed.origin === baseUrl,
    'reset link origin does not match the configured frontend origin (field: link origin)',
  );
  await page.goto(link);
}

export async function expectResetFormRendered(page: Page): Promise<void> {
  await expect(page.getByRole('heading', { name: UI_COPY.resetHeading })).toBeVisible();
  await expect(page.locator('#newPassword')).toBeVisible();
}

export async function submitReset(page: Page, newPassword: string): Promise<void> {
  await page.locator('#newPassword').fill(newPassword);
  await page.getByRole('button', { name: UI_COPY.resetSubmit }).click();
}

export async function expectResetServerErrorVisible(page: Page): Promise<void> {
  await expect(page.getByText(UI_COPY.resetServerError, { exact: true })).toBeVisible();
}

export async function expectResetSuccessVisible(page: Page): Promise<void> {
  await expect(page.getByText(UI_COPY.resetSuccess, { exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: UI_COPY.resetGoToLogin })).toBeVisible();
}

export async function expectInvalidLinkPanelVisible(page: Page): Promise<void> {
  await expect(page.getByRole('heading', { name: UI_COPY.resetInvalidLink })).toBeVisible();
  await expect(page.getByRole('link', { name: UI_COPY.resetRequestNewLink })).toBeVisible();
}

export async function loginViaUi(
  page: Page,
  email: string,
  password: string,
): Promise<void> {
  await page.goto('/login');
  await page.locator('#email').fill(email);
  await page.locator('#password').fill(password);
  await page.getByRole('button', { name: UI_COPY.loginSubmit }).click();
}

export async function expectInvalidCredentialsVisible(page: Page): Promise<void> {
  await expect(page.getByText(UI_COPY.loginInvalidCredentials, { exact: true })).toBeVisible();
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

export async function expectWorkspaceSelectorWithBoth(
  page: Page,
  w1Name: string,
  w2Name: string,
): Promise<void> {
  await expect(page.getByRole('heading', { name: UI_COPY.workspaceHeading })).toBeVisible();
  await expect(page.getByRole('button', { name: new RegExp(escapeRegExp(w1Name)) })).toBeVisible();
  await expect(page.getByRole('button', { name: new RegExp(escapeRegExp(w2Name)) })).toBeVisible();
}

export async function selectWorkspace(page: Page, workspaceName: string): Promise<void> {
  await page.getByRole('button', { name: new RegExp(escapeRegExp(workspaceName)) }).click();
  await page.waitForURL((url) => url.pathname === '/', { timeout: 30_000 });
}

/** No-horizontal-overflow check used by the mobile-viewport nodes. */
export async function expectNoHorizontalOverflow(page: Page, viewportWidth: number): Promise<void> {
  const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  assertSan(
    scrollWidth <= viewportWidth,
    `mobile layout overflows horizontally (field: scrollWidth vs viewport ${viewportWidth})`,
  );
}

/**
 * Collect API request URLs fired on the page (for R1's no-backend-call and
 * R3/R4's no-reset-call assertions). Only URLs/metadata are retained.
 */
export function collectApiRequests(page: Page): string[] {
  const urls: string[] = [];
  page.on('request', (request) => {
    urls.push(request.url());
  });
  return urls;
}

export function apiUrls(urls: string[]): string[] {
  return urls.filter((url) => url.includes('/api/'));
}

export function urlsMatching(urls: string[], pattern: RegExp): string[] {
  return urls.filter((url) => pattern.test(url));
}
