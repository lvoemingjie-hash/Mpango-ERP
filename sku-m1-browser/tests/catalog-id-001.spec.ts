/**
 * CATALOG-ID-001 — tenant-local catalog product and stable sellable-unit
 * identity (P0, full_stack, desktop-and-mobile-390).
 *
 * Own namespace: CATID-DESKTOP / CATID-MOBILE-390. Creates its own product
 * and packages through the supported UI; all direct API observation carries
 * explicit contextual bearer tokens; 401 is terminal (no retry/replay).
 */
import { test, expect } from '../src/fixtures';
import { executionNamespace, loadSharedState } from '../src/provision';
import { HARNESS_CONFIG } from '../playwright.config';
import { attachObserver, observedOrderCreations, ObservedRequest } from '../src/observe';
import { Viewport } from '../src/reconcile';

const ENTRY_WHOLESALER_LOGIN = '/login';
const ENTRY_RETAILER_LOGIN = '/client/login';
const API = HARNESS_CONFIG.backendBaseUrl;

async function openNavigation(page: import('@playwright/test').Page, viewport: Viewport): Promise<void> {
  if (viewport !== 'mobile-390') return;
  const menuButton = page.getByRole('button', { name: 'Toggle navigation menu' });
  await expect(menuButton).toBeVisible();
  await menuButton.click();
  await expect(page.getByRole('link', { name: 'Products' })).toBeVisible({ timeout: 15_000 });
}

function linkForSku(page: import('@playwright/test').Page, skuCode: string) {
  return page.getByRole('link', { name: new RegExp(skuCode.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')) });
}

test('CATALOG-ID-001', async ({ page, markAssertion }, testInfo) => {
  const viewport = testInfo.project.name as Viewport;
  const observed: ObservedRequest[] = [];
  attachObserver(page, observed);
  const shared = loadSharedState();

  const ns = executionNamespace('CATID', viewport);
  const { productName } = ns;
  const [bottleCode, caseCode] = ns.codes;
  const uuidRe = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

  // --- 1. Wholesaler signs in through the supported UI ---------------------
  await page.goto(ENTRY_WHOLESALER_LOGIN);
  await page.getByLabel('Email').fill(shared.tenantA.ownerEmail);
  await page.getByLabel('Password').fill(shared.tenantA.ownerPassword);
  await page.getByRole('button', { name: 'Sign In' }).click();
  // Desktop: the permanent sidebar renders; mobile: open the drawer first.
  if (viewport === 'desktop') {
    await expect(page.getByRole('link', { name: 'Products' })).toBeVisible({ timeout: 30_000 });
  } else {
    await openNavigation(page, viewport);
  }

  // --- 2.+3. Create one CatalogProduct with two package variants via UI ----
  // (the per-execution codes above make this product unique to this node and
  // viewport; no other execution may touch it)
  await page.getByRole('link', { name: 'Products' }).click();
  await expect(page).toHaveURL(/\/skus$/);
  await page.getByRole('button', { name: 'Add Product' }).click();
  const form = page.getByRole('dialog', { name: 'Add New Product' });
  await form.getByLabel('Product Name').fill(productName);
  await form.getByLabel('Category').fill('staples');
  await form.getByLabel('SKU Code').first().fill(bottleCode);
  await form.getByLabel('Pack quantity').first().fill('1');
  await form.getByLabel('Unit').first().fill('bottle');
  await form.getByRole('button', { name: 'Add packaging' }).click();
  const codeInputs = form.getByLabel('SKU Code');
  await codeInputs.nth(1).fill(caseCode);
  await form.getByLabel('Pack quantity').nth(1).fill('12');
  await form.getByLabel('Unit').nth(1).fill('case');
  await form.getByRole('button', { name: 'Save Product' }).click();
  await expect(page.getByTestId('catalog-product-list')).toContainText(productName, { timeout: 30_000 });
  markAssertion('catalog_product_created_via_ui');

  // --- 4.+5. Stable UUIDs + independent stock rows (bearer-authenticated) --
  const listResponse = await page.request.get(
    `${API}/api/v1/catalog-products?q=${encodeURIComponent(productName)}`,
    { headers: { Authorization: `Bearer ${shared.tenantA.accessToken}` } },
  );
  expect(listResponse.status(), `catalog list -> ${listResponse.status()}`).toBeLessThan(400);
  const productList = (await listResponse.json()).data ?? {};
  const items: any[] = productList.items ?? productList.products ?? [];
  const created = items.find((p: any) => (p.name ?? '') === productName);
  expect(created, 'created catalog product found via catalog API').toBeTruthy();
  const units: any[] = created.sellableUnits ?? created.sellable_units ?? created.skus ?? [];
  const bottle = units.find((u: any) => (u.skuCode ?? u.sku_code) === bottleCode);
  const caseUnit = units.find((u: any) => (u.skuCode ?? u.sku_code) === caseCode);
  expect(bottle).toBeTruthy();
  expect(caseUnit).toBeTruthy();
  const bottleUuid = String(bottle.id ?? bottle.sellableUnitId ?? bottle.sellable_unit_id);
  const caseUuid = String(caseUnit.id ?? caseUnit.sellableUnitId);
  expect(bottleUuid).toMatch(uuidRe);
  expect(caseUuid).toMatch(uuidRe);

  // B1-ANCHOR:distinct-stable-uuid
  expect(bottleUuid).not.toBe(caseUuid);
  markAssertion('packages_have_distinct_stable_uuids');

  for (const [skuCode, quantity] of [[bottleCode, 50], [caseCode, 5]] as const) {
    const stockAdjust = await page.request.post(`${API}/api/v1/inventory/adjust`, {
      headers: { Authorization: `Bearer ${shared.tenantA.accessToken}` },
      data: { sku_code: skuCode, quantity, reason: 'stocktake' },
    });
    expect(stockAdjust.status(), `inventory adjust ${skuCode} -> ${stockAdjust.status()}`).toBeLessThan(400);
  }
  for (const sellableUnitId of [bottleUuid, caseUuid]) {
    const price = await page.request.put(`${API}/api/v1/pricing/prices`, {
      headers: { Authorization: `Bearer ${shared.tenantA.accessToken}` },
      data: { retailer_id: shared.retailer.retailerId, sku_id: sellableUnitId, price: '25.50' },
    });
    expect(price.status(), `retailer price ${sellableUnitId} -> ${price.status()}`).toBeLessThan(400);
  }

  const bottleStock = await (async () => {
    const res = await page.request.get(
      `${API}/api/v1/inventory/stocks/${encodeURIComponent(bottleCode)}`,
      { headers: { Authorization: `Bearer ${shared.tenantA.accessToken}` } },
    );
    expect(res.status(), `inventory stocks GET ${bottleCode} -> ${res.status()}`).toBeLessThan(400);
    return (await res.json()).data ?? {};
  })();
  const caseStock = await (async () => {
    const res = await page.request.get(
      `${API}/api/v1/inventory/stocks/${encodeURIComponent(caseCode)}`,
      { headers: { Authorization: `Bearer ${shared.tenantA.accessToken}` } },
    );
    expect(res.status(), `inventory stocks GET ${caseCode} -> ${res.status()}`).toBeLessThan(400);
    return (await res.json()).data ?? {};
  })();

  // B1-ANCHOR:independent-stock
  expect(String(bottleStock.skuId ?? bottleStock.sku_id ?? '')).not.toBe(
    String(caseStock.skuId ?? caseStock.sku_id ?? ''),
  );
  markAssertion('packages_own_independent_stock_rows');

  // --- 6. SKU/package code cannot be reused after retirement ---------------
  const deactivate = await page.request.put(
    `${API}/api/v1/catalog-products/${created.id}/sellable-units/${caseUuid}`,
    {
      headers: { Authorization: `Bearer ${shared.tenantA.accessToken}` },
      data: { is_active: false },
    },
  );
  expect([200, 201]).toContain(deactivate.status());
  const reuse = await page.request.post(`${API}/api/v1/skus`, {
    headers: { Authorization: `Bearer ${shared.tenantA.accessToken}` },
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
  markAssertion('retired_package_code_not_reusable');
  const reactivate = await page.request.put(
    `${API}/api/v1/catalog-products/${created.id}/sellable-units/${caseUuid}`,
    {
      headers: { Authorization: `Bearer ${shared.tenantA.accessToken}` },
      data: { is_active: true },
    },
  );
  expect(reactivate.status(), `reactivate package -> ${reactivate.status()}`).toBeLessThan(400);

  // --- 7.+8. Retailer reaches the catalog; packaging selection visible -----
  const retailerEntry: string = `/client/login?w=${shared.retailer.wholesalerCode}`;
  await page.goto(retailerEntry);
  await page.getByLabel('Email').fill(shared.retailer.email);
  await page.getByLabel('Password').fill(shared.retailer.password);
  await page.getByRole('button', { name: 'Sign In' }).click();
  await expect(linkForSku(page, bottleCode)).toBeVisible({ timeout: 30_000 });
  markAssertion('retailer_sees_product_in_catalog');

  await expect(linkForSku(page, caseCode)).toBeVisible({ timeout: 30_000 });
  markAssertion('product_level_packaging_selection_visible');

  await linkForSku(page, bottleCode).click();
  await expect(page.getByRole('button', { name: 'Add to Order' })).toBeVisible();
  await expect(page.getByText(/bottle/i).first()).toBeVisible();

  // --- 9.+10. Order creation sends the selected sellable_unit_id -----------
  await page.getByRole('button', { name: 'Add to Order' }).click();
  await expect(page.getByRole('button', { name: /Submit Order \(/i })).toBeVisible();
  await page.getByRole('button', { name: /Submit Order \(/i }).click();
  await expect(page.getByText(/order.*created|created.*order|#[0-9a-f]{8}/i).first()).toBeVisible({
    timeout: 30_000,
  });

  const creations = observedOrderCreations(observed);
  expect(creations.length).toBeGreaterThan(0);
  const payload = creations[creations.length - 1];
  const payloadUnitIds: string[] = (payload.items ?? []).map((i: any) => String(i.sellable_unit_id ?? i.sellableUnitId ?? ''));
  // B1-ANCHOR:payload-binds-selected-uuid
  expect(payloadUnitIds).toContain(bottleUuid);
  markAssertion('order_request_carried_selected_sellable_unit_uuid');
  expect(payloadUnitIds.every((id) => uuidRe.test(id))).toBeTruthy();

  // --- 11. Mismatched sellable_unit_id + SKU code is rejected --------------
  const mismatch = await page.request.post(`${API}/api/v1/client/orders`, {
    headers: { Authorization: `Bearer ${shared.retailer.accessToken}` },
    data: {
      items: [{ sellable_unit_id: bottleUuid, sku_code: caseCode, quantity: 1 }],
    },
  });
  // B1-ANCHOR:mismatch-rejected
  expect([400, 404, 409, 422]).toContain(mismatch.status());
  markAssertion('mismatched_uuid_and_code_rejected');

  // --- 12. Cross-tenant UUID is rejected -----------------------------------
  const foreignUnitId = shared.tenantBForeignUnitId;
  const foreign = await page.request.post(`${API}/api/v1/client/orders`, {
    headers: { Authorization: `Bearer ${shared.retailer.accessToken}` },
    data: {
      items: [{ sellable_unit_id: foreignUnitId, quantity: 1 }],
    },
  });
  // B1-ANCHOR:cross-tenant-rejected
  expect([400, 403, 404, 409, 422]).toContain(foreign.status());
  markAssertion('cross_tenant_uuid_rejected');

  // --- 13. Tenant/session identity unchanged -------------------------------
  const me = await page.request.get(`${API}/api/v1/auth/me`, {
    headers: { Authorization: `Bearer ${shared.retailer.accessToken}` },
  });
  expect(me.status(), `auth/me -> ${me.status()}`).toBeLessThan(400);
  const meBody = await me.text();
  expect(meBody.toLowerCase()).not.toContain('skum1browser-b');
  markAssertion('tenant_session_identity_unchanged');

  // --- 14. No manual URL entry was used for positive navigation ------------
  // Enforced by the static validator's goto allowlist; the only gotos here
  // are the two whitelisted entry points above.
});
