/**
 * CATALOG-HIST-001 — immutable order snapshots across catalog rename and
 * deactivation (P1, full_stack, desktop-and-mobile-390).
 *
 * Own namespace: CATHIST-DESKTOP / CATHIST-MOBILE-390. Creates its own
 * product, packages, stock and price through accepted API setup, then creates
 * the historical order via the public client-orders API with a stable
 * sellable_unit_id. All direct API requests carry explicit contextual bearer
 * tokens; 401 is terminal (no retry/replay). Nothing is mocked.
 */
import { test, expect } from '../src/fixtures';
import { executionNamespace, loadSharedState, provisionExecutionResources } from '../src/provision';
import { HARNESS_CONFIG } from '../playwright.config';
import { Viewport } from '../src/reconcile';

const ENTRY_RETAILER_LOGIN = '/client/login';
const API = HARNESS_CONFIG.backendBaseUrl;

function linkForSku(page: import('@playwright/test').Page, skuCode: string) {
  return page.getByRole('link', { name: new RegExp(skuCode.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')) });
}

interface CapturedSnapshot {
  productName: string;
  skuCode: string;
  quantity: string;
  unitPrice: string;
  amount: string;
  orderId: string;
}

test('CATALOG-HIST-001', async ({ page, markAssertion }, testInfo) => {
  const viewport = testInfo.project.name as Viewport;
  const shared = loadSharedState();

  // --- Own per-execution namespace (node x viewport) via API setup ---------
  const ns = executionNamespace('CATHIST', viewport);
  const exec = await provisionExecutionResources(
    shared, ns.tag, ns.productName, ns.codes,
  );
  const unit = exec.units[0];

  // --- 1. Create an order using a stable sellable_unit_id (public API) -----
  const created = await page.request.post(`${API}/api/v1/client/orders`, {
    headers: { Authorization: `Bearer ${shared.retailer.accessToken}` },
    data: { items: [{ sellable_unit_id: unit.sellableUnitId, sku_code: unit.skuCode, quantity: 2 }] },
  });
  expect(created.status()).toBe(201);
  const orderData = ((await created.json()).data ?? {}) as any;
  const orderId: string = orderData.id;
  expect(orderId).toMatch(/^[0-9a-f-]{36}$/i);
  markAssertion('order_created_with_stable_sellable_unit_id');

  // --- 2. Capture the displayed historical snapshot before catalog mutation -
  const retailerEntry: string = `/client/login?w=${shared.retailer.wholesalerCode}`;
  await page.goto(retailerEntry);
  await page.getByLabel('Email').fill(shared.retailer.email);
  await page.getByLabel('Password').fill(shared.retailer.password);
  await page.getByRole('button', { name: 'Sign In' }).click();
  await expect(page.getByRole('link', { name: 'Orders' })).toBeVisible({ timeout: 30_000 });

  await page.getByRole('link', { name: 'Orders' }).click();
  const orderRow = page.getByText(`#${orderId.slice(0, 8)}`).first();
  await expect(orderRow).toBeVisible({ timeout: 30_000 });
  await orderRow.click();
  await expect(page.getByText(/^items$/i)).toBeVisible();

  const itemRow = page.locator('div', { has: page.getByText(unit.skuCode) }).last();
  const before: CapturedSnapshot = {
    productName: (await itemRow.locator('p').first().innerText()).trim(),
    skuCode: unit.skuCode,
    quantity: '',
    unitPrice: '',
    amount: '',
    orderId,
  };
  const rowText = await itemRow.innerText();
  const qtyPrice = rowText.match(/(\d+)\s*[×x]\s*([0-9.,]+)/);
  before.quantity = qtyPrice ? qtyPrice[1] : '';
  before.unitPrice = qtyPrice ? qtyPrice[2] : '';
  const amounts = rowText.match(/([0-9][0-9.,]+)\s*$/);
  before.amount = amounts ? amounts[1] : '';
  expect(before.productName).toBe(ns.productName);
  markAssertion('historical_snapshot_captured_before_mutation');

  // --- 3. Rename the source CatalogProduct (wholesaler API) ----------------
  const rename = await page.request.put(
    `${API}/api/v1/catalog-products/${exec.productId}`,
    {
      headers: { Authorization: `Bearer ${shared.tenantA.accessToken}` },
      data: { name: ns.productName + ' Renamed B3' },
    },
  );
  expect([200, 201]).toContain(rename.status());
  markAssertion('source_product_renamed');

  // --- 4. Deactivate the source product/package (wholesaler API) -----------
  const deactivate = await page.request.put(
    `${API}/api/v1/catalog-products/${exec.productId}/sellable-units/${unit.sellableUnitId}`,
    {
      headers: { Authorization: `Bearer ${shared.tenantA.accessToken}` },
      data: { is_active: false },
    },
  );
  expect([200, 201]).toContain(deactivate.status());
  markAssertion('source_package_deactivated');

  // --- 5. New retailer selection hides the unavailable item ----------------
  await page.getByRole('button', { name: 'Back to orders' }).click();
  await expect(page.getByRole('link', { name: 'Products' })).toBeVisible({ timeout: 30_000 });
  await page.getByRole('link', { name: 'Products' }).click();
  await expect(linkForSku(page, ns.codes[1])).toBeVisible({ timeout: 30_000 });
  const unavailableUnitLink = linkForSku(page, unit.skuCode);

  // B1-ANCHOR:unavailable-item-hidden-or-disabled
  await expect(unavailableUnitLink).toHaveCount(0);
  markAssertion('unavailable_package_hidden_or_disabled_for_new_selection');

  // --- 6.+7. Historical order remains reachable and unchanged (UI) ---------
  await page.getByRole('link', { name: 'Orders' }).click();
  const historicalRow = page.getByText(`#${orderId.slice(0, 8)}`).first();
  await expect(historicalRow).toBeVisible({ timeout: 30_000 });
  await historicalRow.click();
  await expect(page.getByText(/^items$/i)).toBeVisible();
  const afterRow = page.locator('div', { has: page.getByText(unit.skuCode) }).last();
  const afterText = await afterRow.innerText();
  const afterName = (await afterRow.locator('p').first().innerText()).trim();
  const afterQtyPrice = afterText.match(/(\d+)\s*[×x]\s*([0-9.,]+)/);
  const afterAmounts = afterText.match(/([0-9][0-9.,]+)\s*$/);

  // B1-ANCHOR:historical-snapshot-immutable
  expect(afterName).toBe(before.productName);
  expect(afterText).toContain(unit.skuCode);
  expect(afterQtyPrice?.[1] ?? '').toBe(before.quantity);
  expect(afterQtyPrice?.[2] ?? '').toBe(before.unitPrice);
  expect(afterAmounts?.[1] ?? '').toBe(before.amount);
  markAssertion('historical_ui_presentation_unchanged_after_rename_and_deactivation');

  // --- 8. Historical response keeps original sellable_unit_id + snapshots --
  const historical = await page.request.get(`${API}/api/v1/client/orders/${orderId}`, {
    headers: { Authorization: `Bearer ${shared.retailer.accessToken}` },
  });
  expect(historical.ok(), `historical GET -> ${historical.status()}`).toBeTruthy();
  const historicalData = ((await historical.json()).data ?? {}) as any;
  const historicalItems: any[] = historicalData.items ?? [];
  const historicalItem = historicalItems.find(
    (i: any) => (i.sellableUnitId ?? i.sellable_unit_id) === unit.sellableUnitId,
  );
  expect(historicalItem).toBeTruthy();
  expect(String(historicalItem.productName ?? historicalItem.product_name)).toBe(
    before.productName,
  );
  expect(String(historicalItem.skuCode ?? historicalItem.sku_code)).toBe(unit.skuCode);
  markAssertion('historical_api_keeps_original_sellable_unit_id_and_snapshots');

  // --- 10. No live catalog join rewrote the historical presentation --------
  // Proven by 7: the live product is renamed, the historical view still shows
  // the original captured name/code/unit/quantity/price/amount.
});
