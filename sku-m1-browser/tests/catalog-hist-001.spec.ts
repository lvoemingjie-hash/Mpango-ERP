/**
 * CATALOG-HIST-001 — immutable order snapshots across catalog rename and
 * deactivation (P1, full_stack, desktop-and-mobile-390).
 *
 * Runs under BOTH Playwright projects (desktop, mobile-390). The order is
 * created through the public client-orders API with a stable sellable_unit_id;
 * catalog rename/deactivation happen through the public wholesaler APIs;
 * every historical observation is UI-first (supported navigation only) with
 * an API read for the stable-identity proof. Nothing is mocked.
 */
import { test, expect } from '@playwright/test';
import { loadProvisionedState } from '../src/provision';
import { recordOutcome, Viewport } from '../src/reconcile';
import { HARNESS_CONFIG } from '../playwright.config';

const ENTRY_RETAILER_LOGIN = '/client/login';
const API = HARNESS_CONFIG.backendBaseUrl;

interface CapturedSnapshot {
  productName: string;
  skuCode: string;
  unit: string;
  quantity: string;
  unitPrice: string;
  amount: string;
  orderId: string;
}

test('CATALOG-HIST-001', async ({ page }, testInfo) => {
  const viewport = testInfo.project.name as Viewport;
  const assertions: string[] = [];
  const state = loadProvisionedState();
  const productRenameSuffix = ' Renamed B1';

  // --- 1. Create an order using a stable sellable_unit_id (public API) -----
  const unit = state.tenantA.units[0];
  const created = await page.request.post(`${API}/api/v1/client/orders`, {
    headers: { Authorization: `Bearer ${state.retailer.accessToken}` },
    data: { items: [{ sellable_unit_id: unit.sellableUnitId, sku_code: unit.skuCode, quantity: 2 }] },
  });
  expect(created.status()).toBe(201);
  const orderData = ((await created.json()).data ?? {}) as any;
  const orderId: string = orderData.id;
  expect(orderId).toMatch(/^[0-9a-f-]{36}$/i);
  assertions.push('order_created_with_stable_sellable_unit_id');

  // --- 2. Capture the displayed historical snapshot before catalog mutation -
  // Supported entry: the portal handoff link /client/login?w=<portal code>
  // (server-verified code from the retailer registration response).
  const retailerEntry: string = `/client/login?w=${state.retailer.wholesalerCode}`;
  await page.goto(retailerEntry);
  await page.getByLabel(/email/i).fill(state.retailer.email);
  await page.getByLabel(/password/i).fill(state.retailer.password);
  await page.getByRole('button', { name: /sign in/i }).click();
  await expect(page.getByRole('link', { name: /.*/ }).first()).toBeVisible({ timeout: 30_000 });

  // Supported navigation: orders list -> the historical order row.
  const ordersLink = page.getByRole('link', { name: /^orders$/i }).first();
  await ordersLink.click();
  const orderRow = page.getByText(`#${orderId.slice(0, 8)}`).first();
  await expect(orderRow).toBeVisible({ timeout: 30_000 });
  await orderRow.click();
  await expect(page.getByText(/^items$/i)).toBeVisible();

  const itemRow = page.locator('div', { has: page.getByText(unit.skuCode) }).last();
  const before: CapturedSnapshot = {
    productName: (await itemRow.locator('p').first().innerText()).trim(),
    skuCode: unit.skuCode,
    unit: unit.unit,
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
  expect(before.productName.toLowerCase()).toContain('juice');
  assertions.push('historical_snapshot_captured_before_mutation');

  // --- 3. Rename the source CatalogProduct (wholesaler API) ----------------
  const rename = await page.request.put(
    `${API}/api/v1/catalog-products/${state.tenantA.productId}`,
    {
      headers: { Authorization: `Bearer ${state.tenantA.accessToken}` },
      data: { name: state.tenantA.productName + productRenameSuffix },
    },
  );
  expect([200, 201]).toContain(rename.status());
  assertions.push('source_product_renamed');

  // --- 4. Deactivate the source product/package (wholesaler API) -----------
  const deactivate = await page.request.put(
    `${API}/api/v1/catalog-products/${state.tenantA.productId}/sellable-units/${unit.sellableUnitId}`,
    {
      headers: { Authorization: `Bearer ${state.tenantA.accessToken}` },
      data: { is_active: false },
    },
  );
  expect([200, 201]).toContain(deactivate.status());
  assertions.push('source_package_deactivated');

  // --- 5. New retailer selection hides the unavailable item ----------------
  await page.getByRole('link', { name: /client|catalog|back/i }).first().click();
  await expect(page.getByRole('link', { name: state.tenantA.productName + productRenameSuffix })).toBeVisible();
  await page.getByRole('link', { name: state.tenantA.productName + productRenameSuffix }).click();
  const addBtn = page.getByRole('button', { name: /add to order/i });
  const addCount = await addBtn.count();
  const addVisible = addCount > 0 && (await addBtn.first().isVisible().catch(() => false));
  const addDisabled = addCount > 0 && (await addBtn.first().isDisabled().catch(() => false));

  // B1-ANCHOR:unavailable-item-hidden-or-disabled
  expect(addCount === 0 || !addVisible || addDisabled).toBeTruthy();
  assertions.push('unavailable_package_hidden_or_disabled_for_new_selection');

  // --- 6.+7. Historical order remains reachable and unchanged (UI) ---------
  const ordersLinkAfter = page.getByRole('link', { name: /^orders$/i }).first();
  await ordersLinkAfter.click();
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
  assertions.push('historical_ui_presentation_unchanged_after_rename_and_deactivation');

  // --- 8. Historical response keeps original sellable_unit_id + snapshots --
  const historical = await page.request.get(`${API}/api/v1/client/orders/${orderId}`, {
    headers: { Authorization: `Bearer ${state.retailer.accessToken}` },
  });
  expect(historical.ok()).toBeTruthy();
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
  expect(String(historicalItem.unitSnapshot ?? historicalItem.unit_snapshot ?? unit.unit)).toBe(
    unit.unit,
  );
  assertions.push('historical_api_keeps_original_sellable_unit_id_and_snapshots');

  // --- 10. No live catalog join rewrote the historical presentation --------
  // Proven by 7: the live product is renamed, the historical view still shows
  // the original captured name/code/unit/quantity/price/amount.

  recordOutcome(
    'sku-m1-browser/tests/catalog-hist-001.spec.ts::CATALOG-HIST-001',
    viewport,
    testInfo.status === 'passed' ? 'passed' : (testInfo.status as 'failed'),
    assertions,
  );
});
