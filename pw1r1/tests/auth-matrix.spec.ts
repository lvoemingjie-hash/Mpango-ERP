/**
 * PW1-R1 Auth Matrix — Phase 5.1 gate (must be green before phases 1-6 run).
 * Real JWT staging backend; formally provisioned identities (Phase 3).
 *
 * Covers: single-tenant wholesaler login (W1, W2), multi-tenant login through
 * the real workspace selector (RA), retailer portal logins (RA, RB), negative
 * auth paths, and the /select-workspace no-state guard.
 */
import { test, expect } from './helpers';
import {
  loadIdentities, loginWholesaler, loginRetailerPortal, readMpangoAuth, FRONTEND,
} from './helpers';

const IDS = loadIdentities();

test.describe('PW1-R1 auth matrix (real JWT)', () => {

  test('W1 single-tenant wholesaler admin: login API 200, auto select-tenant 200, lands on /', async ({ page, collector }) => {
    await loginWholesaler(page, IDS.w1);
    await expect(page).toHaveURL(/\/$/);
    // Authenticated page element (MainLayout sidebar renders)
    await expect(page.locator('main, [data-testid="dashboard"], nav, aside').first()).toBeVisible();
    const auth = await readMpangoAuth(page);
    expect(auth.state.user?.roles).toContain('admin');
    expect(auth.state.tenantCode).toBe(IDS.w1.tenant_code);
  });

  test('W2 second wholesaler admin: independent tenant, login + select-tenant 200', async ({ page }) => {
    await loginWholesaler(page, IDS.w2);
    await expect(page).toHaveURL(/\/$/);
    const auth = await readMpangoAuth(page);
    expect(auth.state.tenantCode).toBe(IDS.w2.tenant_code);
    expect(auth.state.tenantCode).not.toBe(IDS.w1.tenant_code);
  });

  test('RA multi-tenant login: response carries 2 availableTenants into workspace selector', async ({ page }) => {
    await page.goto('/login');
    const loginRespP = page.waitForResponse(r => r.url().includes('/api/v1/auth/login') && r.request().method() === 'POST');
    await page.fill('#email', IDS.ra.email);
    await page.fill('#password', IDS.ra.password);
    await page.click('button[type="submit"]');
    const resp = await loginRespP;
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    const tenants = body.data.available_tenants;
    expect(tenants.length).toBe(2); // multi-tenant identity via formal retailer double-binding
    const codes = tenants.map((t: any) => t.code).sort();
    expect(codes).toEqual([IDS.w1.tenant_code, IDS.w2.tenant_code].sort());

    // Workspace selector rendered from login-response navigation state
    await page.waitForURL('**/select-workspace');
    for (const t of tenants) {
      await expect(page.locator('button', { hasText: t.name })).toBeVisible();
      await expect(page.locator(`text=Code: ${t.code}`)).toBeVisible();
    }

    // Select W1 workspace -> real select-tenant 200 -> retailer role routed to /client
    const selectP = page.waitForResponse(r => r.url().includes('/api/v1/auth/select-tenant') && r.request().method() === 'POST');
    await page.locator('button', { hasText: tenants.find((t: any) => t.code === IDS.w1.tenant_code).name }).click();
    const sel = await selectP;
    expect(sel.status()).toBe(200);
    await page.waitForURL('**/client', { timeout: 20000 });
    const auth = await readMpangoAuth(page);
    expect(auth.state.accessToken).toBeTruthy();
    expect(auth.state.user?.roles).toContain('retailer_operator');
  });

  test('RB retailer portal login: client auth API 200, lands on /client', async ({ page }) => {
    await loginRetailerPortal(page, IDS.rb.tenant_code!, IDS.rb);
    await expect(page).toHaveURL(/\/client$/);
  });

  test('RA retailer portal login at W1 portal: lands on /client', async ({ page }) => {
    await loginRetailerPortal(page, IDS.w1.tenant_code!, IDS.ra);
    await expect(page).toHaveURL(/\/client$/);
  });

  test('wrong password on wholesaler login: API 401, stays on /login, no token persisted', async ({ page, collector }) => {
    collector.expectHttp('/api/v1/auth/login', 401);
    await page.goto('/login');
    const loginRespP = page.waitForResponse(r => r.url().includes('/api/v1/auth/login') && r.request().method() === 'POST');
    await page.fill('#email', IDS.w1.email);
    await page.fill('#password', 'Definitely-Wrong-Password!');
    await page.click('button[type="submit"]');
    const resp = await loginRespP;
    expect(resp.status()).toBe(401);
    const errBody = await resp.json();
    expect(errBody.code).toBe('INVALID_CREDENTIALS');
    await page.waitForTimeout(800);
    await expect(page).toHaveURL(/\/login/);
    await expect(page.locator('text=Invalid credentials').first()).toBeVisible();
    const auth = await readMpangoAuth(page);
    expect(auth?.state?.accessToken ?? null).toBeFalsy(); // no fake "logged in"
  });

  test('wrong password on retailer portal: API 401, stays on portal, neutral message', async ({ page, collector }) => {
    collector.expectHttp('/api/v1/client/auth/login', 401);
    await page.goto(`/retail/login?w=${IDS.w1.tenant_code}`);
    const loginRespP = page.waitForResponse(r => r.url().includes('/api/v1/client/auth/login') && r.request().method() === 'POST');
    await page.fill('#email', IDS.rb.email);
    await page.fill('#password', 'Wrong-Portal-Password!');
    await page.click('button[type="submit"]');
    const resp = await loginRespP;
    expect(resp.status()).toBe(401);
    await page.waitForTimeout(800);
    await expect(page).toHaveURL(new RegExp(`/retail/login`));
    await expect(page.locator('text=Invalid credentials').first()).toBeVisible();
    const auth = await readMpangoAuth(page);
    expect(auth?.state?.accessToken ?? null).toBeFalsy();
  });

  test('/select-workspace direct access without navigation state redirects to /login', async ({ page }) => {
    await page.goto('/select-workspace');
    await page.waitForURL('**/login', { timeout: 15000 });
    await expect(page).toHaveURL(/\/login$/);
  });

  test('logout clears mpango-auth session and returns to /login', async ({ page }) => {
    await loginWholesaler(page, IDS.w1);
    // Sidebar user menu -> Logout (MainLayout)
    const logout = page.locator('button:has-text("Logout"), a:has-text("Logout"), [data-testid="logout"], [aria-label="Logout"]').first();
    if (await logout.count() === 0) {
      // open user menu if needed
      const menu = page.locator('button[aria-label*="menu" i], [data-testid="user-menu"]').first();
      if (await menu.count() > 0) await menu.click();
    }
    await logout.first().click({ timeout: 10000 });
    await page.waitForURL('**/login', { timeout: 15000 });
    const auth = await readMpangoAuth(page);
    expect(auth?.state?.accessToken ?? null).toBeFalsy();
  });
});
