/**
 * PW1-R1 Phase 1 — Route & navigation audit (real staging backend).
 * Anonymous access rules, health endpoints, 404, alias redirects.
 */
import { test, expect } from './helpers';
import { BACKEND } from './helpers';

test.describe('PW1-R1 Phase 1: routes & navigation', () => {

  test('backend health endpoints are 200 (live/ready)', async ({ request }) => {
    for (const p of ['/health/live', '/health/ready']) {
      const res = await request.get(`${BACKEND}${p}`);
      expect(res.status(), p).toBe(200);
    }
  });

  test('frontend serves the SPA shell', async ({ request }) => {
    const res = await request.get('/');
    expect(res.status()).toBe(200);
    const html = await res.text();
    expect(html).toContain('<div id="root">');
  });

  test('wholesaler routes redirect anonymous users to /login', async ({ page }) => {
    for (const path of ['/', '/orders', '/inventory', '/retailers', '/finance']) {
      await page.goto(path);
      await page.waitForURL('**/login', { timeout: 15000 });
      expect(page.url().endsWith('/login')).toBeTruthy();
    }
  });

  test('retailer /client routes redirect anonymous users to retailer portal or /login', async ({ page }) => {
    await page.goto('/client');
    await page.waitForURL(u => u.pathname === '/login' || u.pathname === '/retail/login', { timeout: 15000 });
  });

  test('/client/login alias redirects to /retail/login preserving w', async ({ page }) => {
    await page.goto('/client/login?w=ABC123');
    await page.waitForURL(u => u.pathname === '/retail/login' && u.searchParams.get('w') === 'ABC123', { timeout: 15000 });
  });

  test('public auth pages are reachable anonymously', async ({ page }) => {
    for (const path of ['/login', '/forgot-password']) {
      await page.goto(path);
      // PW1-R4-B F4: one unique semantic locator (the form's submit control).
      // The old 'button[type="submit"], form' union matched BOTH the form and
      // its button and violated strict mode; this descendant locator resolves
      // to exactly one element per auth page.
      await expect(page.locator('form button[type="submit"]')).toBeVisible();
      expect(page.url().includes(path)).toBeTruthy();
    }
  });

  test('unknown route renders the 404 page (no crash)', async ({ page }) => {
    await page.goto('/this-route-does-not-exist');
    await expect(page.locator('text=404').first()).toBeVisible({ timeout: 15000 });
  });

  test('invalid portal code shows controlled invalid-portal state with zero login API calls', async ({ page, collector }) => {
    await page.goto('/retail/login?w=bad-code!');
    await expect(page.locator('text=Invalid Portal').first()).toBeVisible();
    // No login API call may fire for an invalid portal
    await page.waitForTimeout(1000);
    expect(collector.httpErrors.filter(e => e.url.includes('/client/auth/login'))).toHaveLength(0);
    expect(collector.requestFailed.filter(e => e.url.includes('/api/'))).toHaveLength(0);
  });
});
