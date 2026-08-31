/**
 * CATALOG-ID-001 — tenant-local catalog product and stable sellable-unit
 * identity (P0, full_stack, desktop-and-mobile-390).
 *
 * Runs under BOTH Playwright projects (desktop, mobile-390). Every positive
 * navigation happens through supported UI (sidebar/buttons); `page.goto` is
 * used ONLY for the two whitelisted entry points (/login, /client/login).
 * Network observation is passive (page.on('request')); nothing is mocked.
 */
import { test, expect } from '@playwright/test';
import { loadProvisionedState } from '../src/provision';
import { attachObserver, observedOrderCreations, ObservedRequest } from '../src/observe';
import { recordOutcome, Viewport } from '../src/reconcile';
import { HARNESS_CONFIG } from '../playwright.config';

const ENTRY_WHOLESALER_LOGIN = '/login';
const ENTRY_RETAILER_LOGIN = '/client/login';
const API = HARNESS_CONFIG.backendBaseUrl;

async function openSidebar(page: import('@playwright/test').Page, viewport: Viewport): Promise<void> {
  if (viewport === 'desktop') return;
  const menu = page.getByRole('button', { name: /menu|navigation/i }).first();
  if (await menu.isVisible().catch(() => false)) await menu.click();
}

test('CATALOG-ID-001', async ({ page }, testInfo) => {
  const viewport = testInfo.project.name as Viewport;
  const assertions: string[] = [];
  const observed: ObservedRequest[] = [];
  attachObserver(page, observed);
  const state = loadProvisionedState();
  const productUniqueToken = process.env.B1_RUN_TOKEN ?? state.tenantA.productName;
  const productName = state.tenantA.productName;
  const bottleCode = state.tenantA.units[0].skuCode;
  const caseCode = state.tenantA.units[1].skuCode;

  // --- 1. Wholesaler signs in through the supported UI ---------------------
  await page.goto(ENTRY_WHOLESALER_LOGIN);
  await page.getByLabel(/email/i).fill(state.tenantA.ownerEmail);
  await page.getByLabel(/password/i).first().fill(state.tenantA.ownerPassword);
  await page.getByRole('button', { name: /sign in/i }).click();
  await expect(page.getByRole('link', { name: 'Products' })).toBeVisible({ timeout: 30_000 });

  // --- 2.+3. Create one CatalogProduct with two package variants via UI ----
  await openSidebar(page, viewport);
  await page.getByRole('link', { name: 'Products' }).click();
  await expect(page).toHaveURL(/\/skus$/);
  await page.getByRole('button', { name: 'Add Product' }).click();
  const form = page.locator('body');
  await form.getByLabel('Product Name').fill(productName);
  await form.getByLabel('Category').fill('staples');
  await form.getByLabel('SKU Code').first().fill(bottleCode);
  await form.getByLabel('Pack quantity').first().fill('1');
  await form.getByLabel('Unit').first().fill('bottle');
  // Second sellable-unit row: add another packaging line in the form.
  const addUnitButton = form.getByRole('button', { name: /add (sellable unit|packaging|unit)/i });
  if (await addUnitButton.count()) await addUnitButton.first().click();
  const codeInputs = form.getByLabel('SKU Code');
  if (await codeInputs.count() > 1) {
    await codeInputs.nth(1).fill(caseCode);
    await form.getByLabel('Pack quantity').nth(1).fill('12');
    await form.getByLabel('Unit').nth(1).fill('case');
  }
  await form.getByRole('button', { name: /save product/i }).click();

  // The product must appear in the catalog product list.
  await expect(page.getByTestId('catalog-product-list')).toContainText(productName, { timeout: 30_000 });
  assertions.push('catalog_product_created_via_ui');

  // --- 4.+5. Stable UUIDs + independent stock rows (real API observation) --
  const listResponse = await page.request.get(
    `${API}/api/v1/catalog-products?q=${encodeURIComponent(productUniqueToken)}`,
    { headers: { Authorization: `Bearer ${state.tenantA.accessToken}` } },
  );
  expect(listResponse.status(), `catalog list GET -> ${listResponse.status()}: ${(await listResponse.text()).slice(0, 200)}`).toBeLessThan(400);
  const productList = (await listResponse.json()).data ?? {};
  const items: any[] = productList.items ?? productList.products ?? [];
  const created = items.find((p: any) => (p.name ?? '') === productName);
  expect(created, 'created catalog product found via catalog API').toBeTruthy();
  const units: any[] = created.sellableUnits ?? created.sellable_units ?? created.skus ?? [];
  const bottle = units.find((u: any) => (u.skuCode ?? u.sku_code) === bottleCode);
  const caseUnit = units.find((u: any) => (u.skuCode ?? u.sku_code) === caseCode);
  expect(bottle).toBeTruthy();
  expect(caseUnit).toBeTruthy();

  // B1-ANCHOR:distinct-stable-uuid
  expect(String(bottle.id ?? bottle.sellableUnitId)).not.toBe(String(caseUnit.id ?? caseUnit.sellableUnitId));
  assertions.push('packages_have_distinct_stable_uuids');

  const uuidRe = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  const bottleUuid = String(bottle.id ?? bottle.sellableUnitId);
  const caseUuid = String(caseUnit.id ?? caseUnit.sellableUnitId);
  expect(bottleUuid).toMatch(uuidRe);
  expect(caseUuid).toMatch(uuidRe);

  const bottleStock = await (async () => {
    const res = await page.request.get(`${API}/api/v1/inventory/stocks/${encodeURIComponent(bottleCode)}`);
    expect(res.status(), `inventory stocks GET for ${bottleCode} -> ${res.status()}: ${(await res.text()).slice(0, 200)}`).toBeLessThan(400);
    return (await res.json()).data ?? {};
  })();
  const caseStock = await (async () => {
    const res = await page.request.get(`${API}/api/v1/inventory/stocks/${encodeURIComponent(caseCode)}`);
    expect(res.status(), `inventory stocks GET for ${caseCode} -> ${res.status()}: ${(await res.text()).slice(0, 200)}`).toBeLessThan(400);
    return (await res.json()).data ?? {};
  })();

  // B1-ANCHOR:independent-stock
  expect(String(bottleStock.skuId ?? bottleStock.sku_id ?? '')).not.toBe(
    String(caseStock.skuId ?? caseStock.sku_id ?? ''),
  );
  assertions.push('packages_own_independent_stock_rows');

  // --- 6. SKU/package code cannot be reused after retirement ---------------
  const deactivate = await page.request.put(
    `${API}/api/v1/catalog-products/${created.id}/sellable-units/${caseUuid}`,
    { data: { is_active: false } },
  );
  expect([200, 201]).toContain(deactivate.status());
  const reuse = await page.request.post(`${API}/api/v1/skus`, {
    data: {
      sku_code: caseCode,
      name: caseCode,
      unit: 'case',
      package_quantity: '12.000',
      catalog_product_id: created.id,
    },
  });
  // B1-ANCHOR:code-reuse-rejected
  expect([400, 409, 422]).toContain(reuse.status());
  assertions.push('retired_package_code_not_reusable');
  await page.request.put(`${API}/api/v1/catalog-products/${created.id}/sellable-units/${caseUuid}`, {
    data: { is_active: true },
  });

  // --- 7.+8. Retailer reaches the catalog; packaging selection visible -----
  // Supported entry: the portal handoff link /client/login?w=<portal code>
  // (server-verified code from the retailer registration response).
  const retailerEntry: string = `/client/login?w=${state.retailer.wholesalerCode}`;
  await page.goto(retailerEntry);
  await page.getByLabel(/email/i).fill(state.retailer.email);
  await page.getByLabel(/password/i).fill(state.retailer.password);
  await page.getByRole('button', { name: /sign in/i }).click();
  await expect(page.getByRole('link', { name: productName })).toBeVisible({ timeout: 30_000 });
  assertions.push('retailer_sees_product_in_catalog');

  // Open product detail through supported navigation (product link click).
  await page.getByRole('link', { name: productName }).click();
  await expect(page.getByRole('button', { name: /add to order/i })).toBeVisible();
  // Packaging selection: both package units are offered on the product page.
  await expect(page.getByText(/bottle/i).first()).toBeVisible();
  await expect(page.getByText(/case/i).first()).toBeVisible();
  assertions.push('product_level_packaging_selection_visible');

  // --- 9.+10. Order creation sends the selected sellable_unit_id -----------
  await page.getByRole('button', { name: /add to order/i }).click();
  const orderNav = page.getByRole('button', { name: /place order|checkout|submit order/i });
  if (await orderNav.count()) {
    await orderNav.first().click();
  } else {
    await page.getByRole('link', { name: /order|cart/i }).first().click();
  }
  const placeButton = page.getByRole('button', { name: /place order|submit order|confirm order/i });
  await expect(placeButton).toBeVisible();
  await placeButton.first().click();
  await expect(page.getByText(/order.*created|created.*order|#[0-9a-f]{8}/i).first()).toBeVisible({
    timeout: 30_000,
  });

  const creations = observedOrderCreations(observed);
  expect(creations.length).toBeGreaterThan(0);
  const payload = creations[creations.length - 1];
  const payloadUnitIds: string[] = (payload.items ?? []).map((i: any) => String(i.sellable_unit_id ?? i.sellableUnitId ?? ''));
  // B1-ANCHOR:payload-binds-selected-uuid
  expect(payloadUnitIds).toContain(bottleUuid);
  assertions.push('order_request_carried_selected_sellable_unit_uuid');
  expect(payloadUnitIds.every((id) => uuidRe.test(id))).toBeTruthy();

  // --- 11. Mismatched sellable_unit_id + SKU code is rejected --------------
  const mismatch = await page.request.post(`${API}/api/v1/client/orders`, {
    headers: { Authorization: `Bearer ${state.retailer.accessToken}` },
    data: {
      items: [{ sellable_unit_id: bottleUuid, sku_code: caseCode, quantity: 1 }],
    },
  });
  // B1-ANCHOR:mismatch-rejected
  expect([400, 404, 409, 422]).toContain(mismatch.status());
  assertions.push('mismatched_uuid_and_code_rejected');

  // --- 12. Cross-tenant UUID is rejected -----------------------------------
  const foreign = await page.request.post(`${API}/api/v1/client/orders`, {
    headers: { Authorization: `Bearer ${state.retailer.accessToken}` },
    data: {
      items: [{ sellable_unit_id: state.tenantB.units[0].sellableUnitId, quantity: 1 }],
    },
  });
  // B1-ANCHOR:cross-tenant-rejected
  expect([400, 403, 404, 409, 422]).toContain(foreign.status());
  assertions.push('cross_tenant_uuid_rejected');

  // --- 13. Tenant/session identity unchanged -------------------------------
  const me = await page.request.get(`${API}/api/v1/auth/me`);
  expect(me.ok()).toBeTruthy();
  const meData = (await me.json()).data ?? {};
  const tenantLabel = JSON.stringify(meData).toLowerCase();
  expect(tenantLabel).not.toContain('skum1browser-b');
  assertions.push('tenant_session_identity_unchanged');

  // --- 14. No manual URL entry was used for positive navigation ------------
  // Enforced by the static validator's goto allowlist; the only gotos here
  // are the two whitelisted entry points above.

  recordOutcome(
    'sku-m1-browser/tests/catalog-id-001.spec.ts::CATALOG-ID-001',
    viewport,
    testInfo.status === 'passed' ? 'passed' : (testInfo.status as 'failed'),
    assertions,
  );
});
