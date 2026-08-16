/**
 * PW1-R1 Phase 6 — Responsive & usability (runs per viewport project).
 * No horizontal overflow on key journeys; real console/pageerror collection.
 */
import { test, expect } from './helpers';
import { loadIdentities, loginWholesaler, loginRetailerPortal } from './helpers';

const IDS = loadIdentities();

async function assertNoHorizontalOverflow(page: import('@playwright/test').Page, label: string) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow, `${label} horizontal overflow (scrollWidth-clientWidth)`).toBeLessThanOrEqual(1);
}

test.describe('PW1-R1 Phase 6: responsive & usability', () => {

  test('wholesaler dashboard: no horizontal overflow, no console/page errors', async ({ page, collector }) => {
    await loginWholesaler(page, IDS.w1);
    await assertNoHorizontalOverflow(page, 'wholesaler dashboard');
    const s: any = collector.summary();
    expect(s.nonBenignConsoleErrors, JSON.stringify(s.nonBenignConsoleErrors)).toEqual([]);
    expect(s.pageErrors).toEqual([]);
  });

  test('wholesaler orders page: no horizontal overflow', async ({ page }) => {
    await loginWholesaler(page, IDS.w1);
    await page.goto('/orders');
    await expect(page.locator('main').first()).toBeVisible();
    await assertNoHorizontalOverflow(page, 'wholesaler orders');
  });

  test('retailer catalog: no horizontal overflow, no console/page errors', async ({ page, collector }) => {
    await loginRetailerPortal(page, IDS.rb.tenant_code!, IDS.rb);
    await assertNoHorizontalOverflow(page, 'retailer catalog');
    const s: any = collector.summary();
    expect(s.nonBenignConsoleErrors, JSON.stringify(s.nonBenignConsoleErrors)).toEqual([]);
    expect(s.pageErrors).toEqual([]);
  });

  test('retailer orders page: no horizontal overflow', async ({ page }) => {
    await loginRetailerPortal(page, IDS.rb.tenant_code!, IDS.rb);
    await page.goto('/client/orders');
    await expect(page.locator('main').first()).toBeVisible();
    await assertNoHorizontalOverflow(page, 'retailer orders');
  });

  test('login forms have labels and keyboard-accessible inputs', async ({ page }) => {
    await page.goto('/login');
    const email = page.locator('#email');
    const password = page.locator('#password');
    await expect(email).toBeVisible();
    await expect(password).toBeVisible();
    expect(await email.getAttribute('type')).toBe('email');
    expect(await password.getAttribute('type')).toBe('password');
    // Associated labels exist
    expect(await page.locator('label[for="email"]').count()).toBeGreaterThan(0);
    expect(await page.locator('label[for="password"]').count()).toBeGreaterThan(0);
  });

  test('no unexpected network failures during a login journey', async ({ page, collector }) => {
    await loginWholesaler(page, IDS.w1);
    const s: any = collector.summary();
    const apiFailures = s.requestFailed.filter((f: any) => f.url.includes('/api/'));
    expect(apiFailures, JSON.stringify(apiFailures)).toEqual([]);
    expect(s.unexpectedHttpErrors, JSON.stringify(s.unexpectedHttpErrors)).toEqual([]);
  });

  test('print stub: window.print callable on print pages without errors', async ({ page, collector }) => {
    await page.addInitScript(() => {
      (window as any).print = () => { (window as any).__printCalled = true; };
    });
    await loginWholesaler(page, IDS.w1);
    await page.goto('/orders/00000000-0000-0000-0000-000000000000/print');
    await page.waitForTimeout(1500);
    // Print route with an unknown order must render a neutral state, not crash
    const s: any = collector.summary();
    expect(s.pageErrors).toEqual([]);
  });
});
