/**
 * PW1-R1 Phase 2 — Identity & session integrity.
 * Legacy key injection is rejected; REAL mpango-auth format restores sessions.
 */
import { test, expect } from './helpers';
import {
  loadIdentities, readMpangoAuth, writeMpangoAuth, apiLogin, apiSelectTenant, apiGet, loginWholesaler,
} from './helpers';

const IDS = loadIdentities();

test.describe('PW1-R1 Phase 2: identity & hydration', () => {

  test('legacy localStorage keys (access_token/user) do NOT authenticate', async ({ page }) => {
    await page.goto('/login'); // establish origin
    await page.evaluate(() => {
      // Deprecated/independent keys — must be ignored by the real app
      window.localStorage.setItem('access_token', 'fake-token-value');
      window.localStorage.setItem('refresh_token', 'fake-refresh-value');
      window.localStorage.setItem('user', JSON.stringify({ id: 'x', roles: ['admin'] }));
    });
    await page.goto('/');
    await page.waitForURL('**/login', { timeout: 15000 });
    const auth = await readMpangoAuth(page);
    expect(auth?.state?.accessToken ?? null).toBeFalsy();
  });

  test('forged mpango-auth with invalid JWT is rejected by the backend', async ({ page, collector }) => {
    collector.expectHttp('/api/v1/auth/me', 401);
    await page.goto('/login');
    await writeMpangoAuth(page, {
      accessToken: 'eyJhbGciOiJIUzI1NiJ9.forged.payload',
      refreshToken: 'forged',
      user: { id: '00000000-0000-0000-0000-000000000001', roles: ['admin'] },
      tenantCode: IDS.w1.tenant_code,
    });
    await page.goto('/');
    // Forged token cannot pass JwtAuthStrategy: back to /login
    await page.waitForURL('**/login', { timeout: 15000 });
  });

  test('REAL mpango-auth format restores a wholesaler session (hydration)', async ({ page }) => {
    // Obtain a REAL contextual token through the API (same flow the browser uses)
    const login = await apiLogin(IDS.w1.email, IDS.w1.password);
    const token = await apiSelectTenant(login.token, IDS.w1.tenant_id!);
    const me = await apiGet('/auth/me', token);
    expect(me.status).toBe(200);

    await page.goto('/login'); // establish origin
    await writeMpangoAuth(page, {
      accessToken: token,
      refreshToken: login.token,
      user: me.body.data,
      tenantCode: IDS.w1.tenant_code,
      retailerPortalCode: null,
    });
    await page.goto('/');
    // Session restored: stays in the app (no /login redirect), layout renders
    await page.waitForURL(u => !u.pathname.endsWith('/login'), { timeout: 20000 });
    await expect(page.locator('main, nav, aside').first()).toBeVisible();
    const auth = await readMpangoAuth(page);
    expect(auth.state.accessToken).toBeTruthy();
  });

  test('REAL mpango-auth format restores a retailer session at /client', async ({ page }) => {
    // Retailer portal session via the real client login API
    const res = await fetch('http://127.0.0.1:8000/api/v1/client/auth/login', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: IDS.rb.email, password: IDS.rb.password, wholesaler_code: IDS.rb.tenant_code }),
    });
    expect(res.status).toBe(200);
    const body = await res.json();
    await page.goto('/login'); // establish origin
    await writeMpangoAuth(page, {
      accessToken: body.data.tokens.access_token,
      refreshToken: body.data.tokens.refresh_token,
      user: { ...body.data.user, tenant_id: body.data.tokens.tenant_id, roles: body.data.tokens.roles },
      tenantCode: body.data.wholesaler.code,
      retailerPortalCode: body.data.wholesaler.code,
    });
    await page.goto('/client');
    await page.waitForURL('**/client', { timeout: 20000 });
    await expect(page.locator('main').first()).toBeVisible();
  });

  test('login form submits real credentials to the real API (request body audit)', async ({ page }) => {
    let captured: { url: string; body: string } | null = null;
    page.on('request', r => {
      if (r.url().includes('/api/v1/auth/login') && r.method() === 'POST') {
        captured = { url: r.url(), body: r.postData() ?? '' };
      }
    });
    await loginWholesaler(page, IDS.w1);
    expect(captured).not.toBeNull();
    expect(captured!.url).toContain('/api/v1/auth/login');
    const payload = JSON.parse(captured!.body);
    expect(payload.email).toBe(IDS.w1.email);
    // password travels in the request (never logged/persisted by the harness)
    expect(Object.keys(payload).sort()).toEqual(['email', 'password']);
  });
});
