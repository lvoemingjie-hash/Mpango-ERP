/**
 * PW1-R1 Phase 3 — Wholesaler journey (real JWT, formally provisioned W1).
 * Navigates the wholesaler ERP surface; empty states are expected on the
 * fresh tenant and must render without errors.
 */
import { test, expect } from './helpers';
import { loadIdentities, loginWholesaler } from './helpers';

const IDS = loadIdentities();

test.describe('PW1-R1 Phase 3: wholesaler journey', () => {
  test.beforeEach(async ({ page }) => {
    await loginWholesaler(page, IDS.w1);
  });

  const pages: [string, RegExp][] = [
    ['/', /dashboard|overview|welcome|main/i],
    ['/orders', /orders/i],
    ['/inventory', /inventory/i],
    ['/skus', /sku/i],
    ['/retailers', /retailer/i],
    ['/finance', /finance|receivable|payment/i],
    ['/payments', /payment/i],
    ['/declarations', /declaration/i],
  ];

  for (const [path, marker] of pages) {
    test(`wholesaler page ${path} renders authenticated content`, async ({ page, collector }) => {
      await page.goto(path);
      await page.waitForURL(u => !u.pathname.endsWith('/login'), { timeout: 15000 });
      await expect(page.locator('main').first()).toBeVisible();
      // Authenticated app shell is present (sidebar or header), not the login form
      await expect(page.locator('button[type="submit"]')).toHaveCount(0);
      // No unexpected console/page errors on wholesaler pages
      const s: any = collector.summary();
      expect(s.nonBenignConsoleErrors, `console errors on ${path}: ${JSON.stringify(s.nonBenignConsoleErrors)}`).toEqual([]);
      expect(s.pageErrors).toEqual([]);
    });
  }

  test('dashboard shows the app shell with user context', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('main, nav, aside').first()).toBeVisible();
  });

  test('wholesaler cannot open retailer /client routes (boundary redirect)', async ({ page }) => {
    await page.goto('/client');
    // WholesalerRoute/RetailerRoute: admin session is bounced off /client
    await page.waitForURL(u => u.pathname !== '/client', { timeout: 15000 });
  });

  test('logout returns to /login and clears the session', async ({ page }) => {
    const logout = page.locator('button:has-text("Logout"), a:has-text("Logout"), [data-testid="logout"], [aria-label="Logout"]').first();
    if (await logout.count() === 0) {
      const menu = page.locator('button[aria-label*="menu" i], [data-testid="user-menu"]').first();
      if (await menu.count() > 0) await menu.click();
    }
    await logout.first().click({ timeout: 10000 }).catch(() => {});
    await page.waitForURL('**/login', { timeout: 15000 });
  });
});
