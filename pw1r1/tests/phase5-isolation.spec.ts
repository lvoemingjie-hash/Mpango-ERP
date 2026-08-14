/**
 * PW1-R1 Phase 5 — Cross-tenant / cross-retailer isolation & negative paths.
 * All evidence is gathered with real JWTs from formally provisioned identities:
 *   W1 admin, W2 admin, RA (bound to W1+W2), RB (bound to W1).
 */
import { test, expect } from './helpers';
import {
  loadIdentities, apiLogin, apiSelectTenant, apiGet, apiPost, loginRetailerPortal,
} from './helpers';

const IDS = loadIdentities();

test.describe('PW1-R1 Phase 5: isolation & negative paths', () => {

  test('cross-retailer: RB cannot read RA order by id (API isolation)', async () => {
    // RA creates an order in W1 (RA context)
    const ra = await apiLogin(IDS.ra.email, IDS.ra.password);
    const raToken = await apiSelectTenant(ra.token, IDS.w1.tenant_id!);
    const order = await apiPost('/client/orders', raToken, {
      items: [], notes: 'isolation probe (may be rejected for empty items)',
    });
    let raOrderId: string | null = order.body?.data?.id ?? null;
    if (!raOrderId) {
      // Empty-item order may be invalid; create a real one via SKU
      const w1 = await apiLogin(IDS.w1.email, IDS.w1.password);
      const w1Token = await apiSelectTenant(w1.token, IDS.w1.tenant_id!);
      const skuCode = `ISO-SKU-${Date.now().toString(36)}`;
      const sku = await apiPost('/skus', w1Token, { sku_code: skuCode, name: 'Isolation SKU', unit: 'pcs' });
      expect(sku.status).toBe(201);
      const raOrder = await apiPost('/client/orders', raToken, { items: [{ sku_code: skuCode, quantity: 1 }] });
      expect(raOrder.status).toBe(201);
      raOrderId = raOrder.body.data.id;
    }

    // RB attempts to read RA's order
    const rb = await apiLogin(IDS.rb.email, IDS.rb.password);
    const rbToken = await apiSelectTenant(rb.token, IDS.rb.tenant_id!);
    const attempt = await apiGet(`/client/orders/${raOrderId}`, rbToken);
    expect([403, 404]).toContain(attempt.status); // neutral, no data leak
    expect(JSON.stringify(attempt.body)).not.toContain('items'); // no order content leak
  });

  test('cross-tenant: W2 admin retailer list does NOT contain W1-only retailer RB', async () => {
    const w2 = await apiLogin(IDS.w2.email, IDS.w2.password);
    const w2Token = await apiSelectTenant(w2.token, IDS.w2.tenant_id!);
    const list = await apiGet('/retailers?size=100', w2Token);
    expect(list.status).toBe(200);
    const items: any[] = list.body.data?.items ?? [];
    const names = items.map((i: any) => i.retailer?.name);
    expect(names).toContain('PW1R1 Retailer A'); // RA is bound to W2 (multi-tenant)
    expect(names).not.toContain('PW1R1 Retailer B'); // RB is W1-only
  });

  test('cross-tenant: RA W2-context cannot use W1-only data paths', async () => {
    // RA token scoped to W2 has no access to W1 retailer-scoped resources of RB
    const ra = await apiLogin(IDS.ra.email, IDS.ra.password);
    const raW2 = await apiSelectTenant(ra.token, IDS.w2.tenant_id!);
    // W2 tenant has no RB orders; listing own orders in W2 context is empty
    const own = await apiGet('/client/orders?page=1&size=100', raW2);
    expect(own.status).toBe(200);
    const items: any[] = own.body.data?.items ?? [];
    // Any order visible to RA@W2 must not reference W1-side notes
    for (const o of items) {
      expect(String(o.notes ?? '')).not.toContain('PW1R1 phase4 order');
      expect(String(o.notes ?? '')).not.toContain('PW1R1 idempotency order');
    }
  });

  test('malformed IDs return neutral structured errors (no internals leaked)', async () => {
    const rb = await apiLogin(IDS.rb.email, IDS.rb.password);
    const rbToken = await apiSelectTenant(rb.token, IDS.rb.tenant_id!);
    const res = await apiGet('/client/orders/not-a-uuid', rbToken);
    expect([400, 404]).toContain(res.status);
    const bodyStr = JSON.stringify(res.body);
    expect(bodyStr).not.toMatch(/Traceback|sqlalchemy|psycopg|internal server error/i);
    // Structured envelope: code+message (+request_id), no stack internals
    expect(res.body?.code ?? res.body?.detail?.code).toBeTruthy();
  });

  test('unauthenticated API access is rejected with structured 401 (no leak)', async () => {
    const res = await apiGet('/orders', 'not-a-real-token');
    expect(res.status).toBe(401);
    expect(res.body?.code).toBe('UNAUTHENTICATED');
    expect(JSON.stringify(res.body)).not.toMatch(/Traceback|sqlalchemy/i);
  });

  test('browser: RB portal session never exposes W2 tenant data', async ({ page }) => {
    await loginRetailerPortal(page, IDS.rb.tenant_code!, IDS.rb);
    await page.goto('/client/orders');
    await page.waitForTimeout(1200);
    const body = await page.locator('body').innerText();
    expect(body).not.toContain(IDS.w2.tenant_code!);
    expect(body).not.toContain('PW1R1 W2 Wholesale');
  });

  test('RB orders page contains no RA-created orders (page-level isolation)', async ({ page }) => {
    // RA creates an order with a distinctive note
    const ra = await apiLogin(IDS.ra.email, IDS.ra.password);
    const raToken = await apiSelectTenant(ra.token, IDS.w1.tenant_id!);
    const w1 = await apiLogin(IDS.w1.email, IDS.w1.password);
    const w1Token = await apiSelectTenant(w1.token, IDS.w1.tenant_id!);
    const skuCode = `ISO5-SKU-${Date.now().toString(36)}`;
    await apiPost('/skus', w1Token, { sku_code: skuCode, name: 'ISO5 SKU', unit: 'pcs' });
    const raOrder = await apiPost('/client/orders', raToken, {
      items: [{ sku_code: skuCode, quantity: 1 }], notes: 'RA-ONLY-VISIBLE-ORDER',
    });
    expect(raOrder.status).toBe(201);

    // RB views own orders page — must not see RA's order note anywhere
    await loginRetailerPortal(page, IDS.rb.tenant_code!, IDS.rb);
    await page.goto('/client/orders');
    await page.waitForTimeout(1500);
    const body = await page.locator('body').innerText();
    expect(body).not.toContain('RA-ONLY-VISIBLE-ORDER');
  });
});
