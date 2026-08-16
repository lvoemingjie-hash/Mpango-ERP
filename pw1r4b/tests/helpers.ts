/**
 * DC-12R1-MVP-L1-PW1-R1 — shared helpers (real JWT evidence).
 *
 * Rules enforced here (PW1-R1 repair):
 *  - loginWholesaler/loginRetailer WAIT for the real login API response and
 *    assert HTTP 200 + response structure before any "logged in" claim.
 *  - Retailer portal login MUST end on /client; failures are re-thrown, never
 *    masked by manual navigation (old PW1 defect).
 *  - Hydration uses ONLY the real `mpango-auth` zustand persist format.
 *  - Every page gets console/pageerror/requestfailed/HTTP-status collectors.
 */
import { test as base, expect, type Page, type TestInfo } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

export const FRONTEND = 'http://127.0.0.1:5173';
export const BACKEND = 'http://127.0.0.1:8000';
export const API = `${BACKEND}/api/v1`;

// ---------------------------------------------------------------------------
// Identities (task-private file; never committed, never in reports)
// ---------------------------------------------------------------------------
export interface Identity {
  email: string; password: string;
  tenant_code?: string; tenant_id?: string; tenant_schema?: string;
  tenant_codes?: string[]; phone?: string; retailer_name?: string;
}
export interface Identities { w1: Identity; w2: Identity; ra: Identity; rb: Identity; }

const IDENTITY_FILE = path.join(__dirname, '..', 'provision', 'identities.json');

export function loadIdentities(): Identities {
  const raw = JSON.parse(fs.readFileSync(IDENTITY_FILE, 'utf-8'));
  for (const k of ['w1', 'w2', 'ra', 'rb']) {
    if (!raw[k]?.email || !raw[k]?.password) throw new Error(`identity ${k} missing in identities.json`);
  }
  return raw as Identities;
}

// ---------------------------------------------------------------------------
// Browser evidence collectors
// ---------------------------------------------------------------------------
export interface Collector {
  consoleErrors: string[];
  pageErrors: string[];
  requestFailed: { url: string; failure: string }[];
  httpErrors: { url: string; status: number }[];
  expectedHttp: Set<string>;
  expectHttp(urlSub: string, status: number): void;
  summary(): Record<string, unknown>;
}

const BENIGN_CONSOLE = [
  /favicon\.ico/i,
  /Download the React DevTools/i,
  /sourcemap/i,
  /\[vite\]/i,
  /manifest\.json/i,
];

export async function attachCollectors(page: Page): Promise<Collector> {
  const c: Collector = {
    consoleErrors: [],
    pageErrors: [],
    requestFailed: [],
    httpErrors: [],
    expectedHttp: new Set(),
    expectHttp(urlSub: string, status: number) { this.expectedHttp.add(`${status}:${urlSub}`); },
    summary() {
      const isExpectedHttp = (e: { url: string; status: number }) =>
        [...c.expectedHttp].some(k => e.status === Number(k.split(':')[0]) && e.url.includes(k.split(':').slice(1).join(':')));
      return {
        consoleErrors: c.consoleErrors,
        pageErrors: c.pageErrors,
        requestFailed: c.requestFailed,
        httpErrors: c.httpErrors,
        unexpectedHttpErrors: c.httpErrors.filter(e => !isExpectedHttp(e)),
        benignConsoleFiltered: c.consoleErrors.filter(e => BENIGN_CONSOLE.some(re => re.test(e))),
        nonBenignConsoleErrors: c.consoleErrors.filter(e => !BENIGN_CONSOLE.some(re => re.test(e))),
      };
    },
  };
  page.on('console', m => { if (m.type() === 'error') c.consoleErrors.push(m.text()); });
  page.on('pageerror', e => c.pageErrors.push(e.message));
  page.on('requestfailed', r => c.requestFailed.push({ url: r.url(), failure: r.failure()?.errorText ?? '' }));
  page.on('response', r => { if (r.status() >= 400) c.httpErrors.push({ url: r.url(), status: r.status() }); });
  return c;
}

// Fixture: every test page is monitored; evidence attached at the end.
export const test = base.extend<{ collector: Collector }>({
  collector: async ({ page }, use, testInfo) => {
    const col = await attachCollectors(page);
    await use(col);
    await testInfo.attach('browser-evidence', {
      contentType: 'application/json',
      body: Buffer.from(JSON.stringify(col.summary(), null, 2)),
    });
  },
});

export { expect };

// ---------------------------------------------------------------------------
// mpango-auth (zustand persist) localStorage helpers
// ---------------------------------------------------------------------------
export async function readMpangoAuth(page: Page): Promise<any | null> {
  const raw = await page.evaluate(() => window.localStorage.getItem('mpango-auth'));
  return raw ? JSON.parse(raw) : null;
}

export async function writeMpangoAuth(page: Page, state: Record<string, unknown>): Promise<void> {
  await page.evaluate(s => {
    window.localStorage.setItem('mpango-auth', JSON.stringify({ state: s, version: 0 }));
  }, state);
}

// ---------------------------------------------------------------------------
// Real login flows (browser-driven, real API responses asserted)
// ---------------------------------------------------------------------------

/** Wholesaler/owner login via /login. Asserts the real login API 200 and the
 *  documented post-login routing. Single-tenant -> auto select-tenant -> '/'.
 *  Multi-tenant -> /select-workspace (state carries availableTenants). */
export async function loginWholesaler(page: Page, identity: Identity): Promise<void> {
  await page.goto('/login');
  await expect(page.locator('button[type="submit"]')).toBeVisible();

  const loginRespP = page.waitForResponse(
    r => r.url().includes('/api/v1/auth/login') && r.request().method() === 'POST',
    { timeout: 20000 },
  );
  await page.fill('#email', identity.email);
  await page.fill('#password', identity.password);
  await page.click('button[type="submit"]');

  const resp = await loginRespP;
  expect(resp.status(), `login API for ${identity.email}`).toBe(200); // REAL 200 required
  const body = await resp.json();
  expect(body.data?.access_token, 'identity access_token in response').toBeTruthy();
  expect(body.data?.token_type).toBe('bearer');
  const tenants: any[] = body.data?.available_tenants ?? [];
  expect(tenants.length, 'available_tenants non-empty').toBeGreaterThan(0);

  if (tenants.length === 1) {
    // Auto-select: frontend calls /auth/select-tenant then lands on '/'
    const selectP = page.waitForResponse(
      r => r.url().includes('/api/v1/auth/select-tenant') && r.request().method() === 'POST',
      { timeout: 20000 },
    );
    const sel = await selectP;
    expect(sel.status(), 'auto select-tenant').toBe(200); // REAL 200 (old PW1 403 class defect)
    await page.waitForURL(u => !u.pathname.endsWith('/login') && !u.pathname.includes('select-workspace'), { timeout: 20000 });
    await expect(page).toHaveURL(/\/$/);
  } else {
    await page.waitForURL('**/select-workspace', { timeout: 20000 });
  }

  // mpango-auth persisted with a real token
  const auth = await readMpangoAuth(page);
  expect(auth?.state?.accessToken, 'mpango-auth.state.accessToken persisted').toBeTruthy();
}

/** Retailer portal login via /retail/login?w=CODE. Asserts the real
 *  /client/auth/login API 200 and that the app lands on /client. A 401/other
 *  status FAILS the test (no fake "logged in"). */
export async function loginRetailerPortal(page: Page, wCode: string, identity: Identity): Promise<void> {
  await page.goto(`/retail/login?w=${wCode}`);
  await expect(page.locator('button[type="submit"]')).toBeVisible();

  const loginRespP = page.waitForResponse(
    r => r.url().includes('/api/v1/client/auth/login') && r.request().method() === 'POST',
    { timeout: 20000 },
  );
  await page.fill('#email', identity.email);
  await page.fill('#password', identity.password);
  await page.click('button[type="submit"]');

  const resp = await loginRespP;
  expect(resp.status(), `client login API for ${identity.email} @${wCode}`).toBe(200);
  const body = await resp.json();
  expect(body.data?.tokens?.access_token, 'client contextual token').toBeTruthy();
  expect(body.data?.wholesaler?.code, 'wholesaler code in response').toBe(wCode);

  // Retailer success MUST land on /client
  await page.waitForURL('**/client', { timeout: 20000 });
  await expect(page).toHaveURL(/\/client$/);

  const auth = await readMpangoAuth(page);
  expect(auth?.state?.accessToken).toBeTruthy();
  expect(auth?.state?.retailerPortalCode, 'portal code preserved').toBe(wCode);
}

// ---------------------------------------------------------------------------
// Node-side API helpers (fingerprint + data setup with real JWT)
// ---------------------------------------------------------------------------
export interface ApiTokens { access_token: string; refresh_token: string; tenant_id?: string; }

export async function apiLogin(email: string, password: string): Promise<{ token: string; tenants: any[]; userId: string }> {
  const res = await fetch(`${API}/auth/login`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  if (res.status !== 200) throw new Error(`apiLogin ${email}: HTTP ${res.status}`);
  const body = await res.json();
  return { token: body.data.access_token, tenants: body.data.available_tenants, userId: body.data.user_id };
}

export async function apiSelectTenant(token: string, tenantId: string): Promise<string> {
  const res = await fetch(`${API}/auth/select-tenant`, {
    method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ tenant_id: tenantId }),
  });
  if (res.status !== 200) throw new Error(`apiSelectTenant: HTTP ${res.status}`);
  const body = await res.json();
  return body.data.access_token;
}

export async function apiGet(path: string, token: string): Promise<{ status: number; body: any }> {
  const res = await fetch(`${API}${path}`, { headers: { Authorization: `Bearer ${token}` } });
  let body: any = null;
  try { body = await res.json(); } catch { /* empty */ }
  return { status: res.status, body };
}

export async function apiPost(path: string, token: string, payload: unknown, headers: Record<string, string> = {}): Promise<{ status: number; body: any }> {
  const res = await fetch(`${API}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}`, ...headers },
    body: JSON.stringify(payload),
  });
  let body: any = null;
  try { body = await res.json(); } catch { /* empty */ }
  return { status: res.status, body };
}

export async function apiPut(path: string, token: string, payload: unknown): Promise<{ status: number; body: any }> {
  const res = await fetch(`${API}${path}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify(payload),
  });
  let body: any = null;
  try { body = await res.json(); } catch { /* empty */ }
  return { status: res.status, body };
}

/** PW1-R4-B F3: request WITHOUT any Authorization header (missing-credential
 * negative path — distinct from a malformed bearer token). */
export async function apiGetNoAuth(path: string): Promise<{ status: number; body: any }> {
  const res = await fetch(`${API}${path}`);
  let body: any = null;
  try { body = await res.json(); } catch { /* empty */ }
  return { status: res.status, body };
}

/**
 * PW1-R4-B F1 correction: make a freshly created SKU orderable through the
 * SUPPORTED product lifecycles ONLY (no direct SQL, no backdoors):
 *   1. POST /inventory/adjust — manual stocktake adjustment adds
 *      quantity_on_hand (audit-trailed in inventory_movements).
 *   2. GET  /retailers       — resolve the invited retailer's id for this
 *      wholesaler (formal invitation lifecycle already bound them).
 *   3. PUT  /pricing/prices  — set the retailer-specific price row that the
 *      order endpoint's server-side P0 pricing resolves.
 */
export async function ensureStockAndPrice(
  adminToken: string,
  opts: { skuCode: string; skuId: string; retailerEmail: string; quantity: number; price: string },
): Promise<void> {
  const adj = await apiPost('/inventory/adjust', adminToken, {
    sku_code: opts.skuCode,
    quantity: opts.quantity,
    reason: 'PW1R4-B harness stocktake provisioning',
  });
  expect(adj.status, `inventory adjust for ${opts.skuCode} (${JSON.stringify(adj.body).slice(0, 200)})`).toBe(200);

  const list = await apiGet('/retailers?page=1&size=100', adminToken);
  expect(list.status, `retailers list (${JSON.stringify(list.body).slice(0, 200)})`).toBe(200);
  const items: any[] = list.body.data?.items ?? [];
  const match = items.find((i: any) => i.retailer?.email === opts.retailerEmail);
  expect(match, `retailer bound for ${opts.retailerEmail} in wholesaler CRM list`).toBeTruthy();
  const retailerId: string = match.retailer.id;

  const price = await apiPut('/pricing/prices', adminToken, {
    retailer_id: retailerId,
    sku_id: opts.skuId,
    price: opts.price,
  });
  expect(price.status, `set retailer price for ${opts.skuCode} (${JSON.stringify(price.body).slice(0, 200)})`).toBe(200);
}
