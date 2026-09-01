/**
 * Public-API provisioning for the SKU browser harness (B3).
 *
 * Resource isolation contract:
 * - global setup creates ONLY shared immutable identities: tenant A
 *   owner/session, tenant B owner/session, retailer identity/binding/session,
 *   and the local-mail prerequisites.
 * - each Playwright execution (node x viewport) creates its OWN product,
 *   packages, stock and retailer prices through accepted public API flows,
 *   in a deterministic namespace derived ONLY from the frozen node ID and
 *   the viewport ID (e.g. CATID-DESKTOP-UNIT). No uuid/timestamp/random
 *   bytes enter any name.
 * - one execution never renames, deactivates, prices or orders another
 *   execution's product.
 * - every direct API request carries the correct contextual bearer token;
 *   401 is terminal for the current execution (no retry, no replay).
 */
import * as fs from 'fs';
import * as path from 'path';
import { HARNESS_CONFIG } from '../playwright.config';
import { OfficialProvisioning } from './preflight';

const MAILDIR = path.resolve(__dirname, '..', 'results', 'maildir');

export type ViewportId = 'DESKTOP' | 'MOBILE-390';

export function executionNamespace(nodeShort: 'CATID' | 'CATHIST', viewport: string): {
  productName: string;
  codes: [string, string];
  tag: string;
} {
  const vp: ViewportId = viewport === 'mobile-390' ? 'MOBILE-390' : 'DESKTOP';
  const tag = `${nodeShort}-${vp}`;
  return {
    tag,
    productName: `SKU M1 Browser Juice ${tag}`,
    codes: [`${nodeShort}-${vp}-UNIT`, `${nodeShort}-${vp}-PACK`],
  };
}

export class ApiError extends Error {
  constructor(public readonly method: string, public readonly urlPath: string,
              public readonly status: number, public readonly bodySnippet: string) {
    // Sanitized: route, status and response class only — never tokens.
    super(`API ${method} ${urlPath} -> ${status}: ${bodySnippet.slice(0, 300)}`);
  }
}

export async function api(
  backendBase: string, method: string, urlPath: string,
  opts: { token?: string; body?: unknown; expect?: number[] } = {},
): Promise<{ status: number; json: any; text: string }> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (opts.token) headers.Authorization = `Bearer ${opts.token}`;
  const res = await fetch(`${backendBase}${urlPath}`, {
    method,
    headers,
    body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
  });
  const text = await res.text();
  let json: any = null;
  try { json = JSON.parse(text); } catch { /* non-JSON body */ }
  const expected = opts.expect;
  if (expected && !expected.includes(res.status)) {
    throw new ApiError(method, urlPath, res.status, text);
  }
  return { status: res.status, json, text };
}

function dataPayload(json: any): any {
  return json?.data !== undefined ? json.data : json;
}

function decodeQuotedPrintable(text: string): string {
  return text
    .replace(/=\r?\n/g, '')
    .replace(/=([0-9A-Fa-f]{2})/g, (_, hex) => String.fromCharCode(parseInt(hex, 16)));
}

function extractTokenFromEmail(mhContent: string, kind: 'verify' | 'setup' | 'retailer_setup'): string {
  const body = decodeQuotedPrintable(mhContent);
  const linkMatch = body.match(/https?:\/\/[^\s"'<>]+/g) ?? [];
  for (const link of linkMatch) {
    const url = new URL(link);
    const params = new URLSearchParams(
      `${url.search.replace(/^\?/, '')}&${url.hash.replace(/^#/, '')}`,
    );
    const token = params.get('token') ?? params.get('setupToken') ?? params.get('setup_token');
    if (token) return token;
  }
  throw new Error(`no ${kind} token found (consumed mail, kind=${kind})`);
}

const MAIL_KIND_MARKERS: Record<'verify' | 'setup' | 'retailer_setup', string[]> = {
  verify: ['verify your mpango erp email', 'verification link'],
  setup: ['set up your mpango erp owner account', 'owner administrator password'],
  retailer_setup: ['retailer', 'set up'],
};

function findMail(recipient: string, kind: 'verify' | 'setup' | 'retailer_setup'): string | null {
  const newDir = path.join(MAILDIR, 'new');
  const files = fs.existsSync(newDir) ? fs.readdirSync(newDir).map((f) => path.join(newDir, f)) : [];
  const markers = MAIL_KIND_MARKERS[kind];
  const candidates = files
    .filter((f) => !f.endsWith('.consumed'))
    .filter((f) => fs.readFileSync(f, 'latin1').toLowerCase().includes(recipient.toLowerCase()))
    .filter((f) => {
      const text = fs.readFileSync(f, 'utf-8').toLowerCase();
      return markers.some((m) => text.includes(m));
    })
    .sort((a, b) => fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs);
  return candidates[0] ?? null;
}

async function waitForMail(
  recipient: string,
  kind: 'verify' | 'setup' | 'retailer_setup',
  timeoutMs = 45_000,
): Promise<string> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const mail = findMail(recipient, kind);
    if (mail) {
      const content = fs.readFileSync(mail, 'utf-8');
      fs.renameSync(mail, `${mail}.consumed`);
      return content;
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`mail for ${recipient} (kind=${kind}) did not arrive within ${timeoutMs}ms`);
}

export interface SharedIdentity {
  ownerEmail: string;
  ownerPassword: string;
  accessToken: string;
  wholesalerCode: string;
  wholesalerId: string;
}
export interface SharedRetailer {
  email: string;
  password: string;
  wholesalerCode: string;
  accessToken: string;
  retailerId: string;
}
export interface SharedState {
  tenantA: SharedIdentity;
  tenantB: SharedIdentity;
  retailer: SharedRetailer;
  /** Immutable tenant-B sellable unit used ONLY for cross-tenant negatives. */
  tenantBForeignUnitId: string;
}

async function provisionOwner(
  tenant: { company_name: string; country: string; owner_email: string; owner_password: string },
): Promise<SharedIdentity> {
  await api(HARNESS_CONFIG.backendBaseUrl, 'POST', '/api/v1/auth/signup', {
    body: { companyName: tenant.company_name, country: tenant.country, email: tenant.owner_email },
    expect: [202],
  });
  const verifyContent = await waitForMail(tenant.owner_email, 'verify');
  const verifyToken = extractTokenFromEmail(verifyContent, 'verify');
  await api(HARNESS_CONFIG.backendBaseUrl, 'POST', '/api/v1/auth/verify-email', {
    body: { token: verifyToken }, expect: [200],
  });
  const setupContent = await waitForMail(tenant.owner_email, 'setup');
  const setupToken = extractTokenFromEmail(setupContent, 'setup');
  await api(HARNESS_CONFIG.backendBaseUrl, 'POST', '/api/v1/auth/onboarding/setup-credential', {
    body: { setupToken, password: tenant.owner_password }, expect: [200],
  });
  const login = await api(HARNESS_CONFIG.backendBaseUrl, 'POST', '/api/v1/auth/login', {
    body: { email: tenant.owner_email, password: tenant.owner_password }, expect: [200],
  });
  const loginData = dataPayload(login.json);
  const identityToken: string = loginData.access_token ?? loginData.accessToken;
  if (!identityToken) {
    throw new ApiError('POST', '/api/v1/auth/login', 200, 'owner login access token missing');
  }
  // Response is snake_case (plain BaseModel): available_tenants.
  const tenants: any[] = loginData.available_tenants ?? loginData.availableTenants ?? [];
  if (!tenants.length) {
    throw new ApiError('POST', '/api/v1/auth/login', 200, 'no available tenants for owner login');
  }
  const selected = await api(HARNESS_CONFIG.backendBaseUrl, 'POST', '/api/v1/auth/select-tenant', {
    token: identityToken,
    body: { tenant_id: tenants[0].id },
    expect: [200],
  });
  const selectedData = dataPayload(selected.json);
  const accessToken: string = selectedData.access_token ?? selectedData.accessToken;
  if (!accessToken) {
    throw new ApiError('POST', '/api/v1/auth/select-tenant', 200, 'contextual access token missing');
  }
  const wsList = await api(HARNESS_CONFIG.backendBaseUrl, 'GET', '/api/v1/wholesalers', {
    token: accessToken, expect: [200],
  });
  const wsData = dataPayload(wsList.json);
  const wsItems: any[] = wsData.items ?? wsData.wholesalers ?? [];
  const wholesalerCode = String(wsItems[0]?.code ?? '');
  if (!wholesalerCode) {
    throw new ApiError('GET', '/api/v1/wholesalers', 200, 'wholesaler code missing');
  }
  return {
    ownerEmail: tenant.owner_email,
    ownerPassword: tenant.owner_password,
    accessToken,
    wholesalerCode,
    wholesalerId: String(wsItems[0]?.id ?? tenants[0].id),
  };
}

async function provisionRetailer(
  tenantA: SharedIdentity,
  retailerSpec: OfficialProvisioning['tenant_a']['retailer'],
): Promise<SharedRetailer> {
  const invitation = await api(HARNESS_CONFIG.backendBaseUrl, 'POST', '/api/v1/invitations', {
    token: tenantA.accessToken,
    body: { retailer_phone: retailerSpec.phone },
    expect: [201, 200],
  });
  const invitationCode: string = dataPayload(invitation.json).code;
  const registered = await api(HARNESS_CONFIG.backendBaseUrl, 'POST', '/api/v1/retailers/register', {
    body: {
      invitation_code: invitationCode,
      phone: retailerSpec.phone,
      name: retailerSpec.name,
      email: retailerSpec.email,
    },
    expect: [201],
  });
  const registeredData = dataPayload(registered.json);
  const retailerId = String(
    registeredData.retailer?.id ?? registeredData.retailerId ?? registeredData.retailer_id ?? '',
  );
  if (!/^[0-9a-f-]{36}$/i.test(retailerId)) {
    throw new ApiError('POST', '/api/v1/retailers/register', 201, `retailer id missing: ${registered.text.slice(0, 200)}`);
  }
  const setupContent = await waitForMail(retailerSpec.email, 'retailer_setup');
  const setupToken = extractTokenFromEmail(setupContent, 'retailer_setup');
  await api(HARNESS_CONFIG.backendBaseUrl, 'POST', '/api/v1/retailers/setup-credential', {
    body: { setup_token: setupToken, new_password: retailerSpec.password }, expect: [200],
  });
  const login = await api(HARNESS_CONFIG.backendBaseUrl, 'POST', '/api/v1/client/auth/login', {
    body: {
      email: retailerSpec.email,
      password: retailerSpec.password,
      wholesaler_code: tenantA.wholesalerCode,
    },
    expect: [200],
  });
  const loginData = dataPayload(login.json);
  const accessToken: string = loginData.tokens?.access_token
    ?? loginData.tokens?.accessToken
    ?? loginData.access_token
    ?? loginData.accessToken;
  if (!accessToken) {
    throw new ApiError('POST', '/api/v1/client/auth/login', 200, 'retailer login access token missing');
  }
  return {
    email: retailerSpec.email,
    password: retailerSpec.password,
    wholesalerCode: tenantA.wholesalerCode,
    accessToken,
    retailerId,
  };
}

export async function provisionShared(official: OfficialProvisioning): Promise<SharedState> {
  const tenantA = await provisionOwner(official.tenant_a);
  const tenantB = await provisionOwner(official.tenant_b);
  const retailer = await provisionRetailer(tenantA, official.tenant_a.retailer);
  // Immutable tenant-B sellable unit: created once, never mutated by any
  // execution; used exclusively for cross-tenant negative assertions.
  const foreignName = 'SKU M1 Browser Foreign Juice';
  const foreignCode = 'B1-FOREIGN-UNIT';
  const created = await api(HARNESS_CONFIG.backendBaseUrl, 'POST', '/api/v1/catalog-products', {
    token: tenantB.accessToken,
    body: {
      name: foreignName,
      category: 'staples',
      is_active: true,
      sellable_units: [
        { sku_code: foreignCode, unit: 'bottle', package_quantity: '1.000', is_active: true },
      ],
    },
    expect: [201, 200],
  });
  const createdData = dataPayload(created.json);
  const foreignUnits: any[] = createdData.sellableUnits ?? createdData.sellable_units ?? [];
  const tenantBForeignUnitId = String(foreignUnits[0]?.id ?? '');
  if (!/^[0-9a-f-]{36}$/i.test(tenantBForeignUnitId)) {
    throw new ApiError('POST', '/api/v1/catalog-products', 201, 'tenant-B foreign unit id missing');
  }
  const state: SharedState = { tenantA, tenantB, retailer, tenantBForeignUnitId };
  fs.mkdirSync(MAILDIR, { recursive: true });
  fs.writeFileSync(path.join(MAILDIR, 'provisioned.json'), JSON.stringify(state, null, 2));
  return state;
}

export function loadSharedState(): SharedState {
  const file = path.join(MAILDIR, 'provisioned.json');
  if (!fs.existsSync(file)) throw new Error('shared provisioning state absent — global setup did not run');
  return JSON.parse(fs.readFileSync(file, 'utf-8')) as SharedState;
}

export interface ExecutionUnit {
  skuCode: string;
  unit: string;
  sellableUnitId: string;
  stockOnHand: string;
}
export interface ExecutionResources {
  tag: string;
  productId: string;
  productName: string;
  units: ExecutionUnit[];
}

/** Per-execution catalog resources (product + 2 packages + stock + price). */
export async function provisionExecutionResources(
  shared: SharedState,
  tag: string,
  productName: string,
  codes: [string, string],
): Promise<ExecutionResources> {
  const created = await api(HARNESS_CONFIG.backendBaseUrl, 'POST', '/api/v1/catalog-products', {
    token: shared.tenantA.accessToken,
    body: {
      name: productName,
      category: 'staples',
      is_active: true,
      sellable_units: [
        { sku_code: codes[0], unit: 'bottle', package_quantity: '1.000', is_active: true },
        { sku_code: codes[1], unit: 'case', package_quantity: '12.000', is_active: true },
      ],
    },
    expect: [201, 200],
  });
  const productData = dataPayload(created.json);
  const productId: string = productData.id;
  const rawUnits: any[] = productData.sellableUnits ?? productData.sellable_units ?? productData.skus ?? [];
  const units: ExecutionUnit[] = codes.map((code, idx) => {
    const match = rawUnits.find((u: any) => (u.skuCode ?? u.sku_code) === code) ?? {};
    const id = String(match.id ?? match.sellableUnitId ?? match.sellable_unit_id ?? '');
    if (!/^[0-9a-f-]{36}$/i.test(id)) {
      throw new ApiError('POST', '/api/v1/catalog-products', 201, `unit id missing for ${code}`);
    }
    return { skuCode: code, unit: idx === 0 ? 'bottle' : 'case', sellableUnitId: id, stockOnHand: '' };
  });
  for (const [idx, unit] of units.entries()) {
    await api(HARNESS_CONFIG.backendBaseUrl, 'POST', '/api/v1/inventory/adjust', {
      token: shared.tenantA.accessToken,
      body: { sku_code: unit.skuCode, quantity: idx === 0 ? 50 : 5, reason: 'stocktake' },
      expect: [200, 201],
    });
  }
  for (const unit of units) {
    const stock = await api(
      HARNESS_CONFIG.backendBaseUrl, 'GET',
      `/api/v1/inventory/stocks/${encodeURIComponent(unit.skuCode)}`,
      { token: shared.tenantA.accessToken, expect: [200] },
    );
    const stockData = dataPayload(stock.json);
    unit.stockOnHand = String(stockData.quantityOnHand ?? stockData.quantity_on_hand ?? '');
  }
  for (const unit of units) {
    await api(HARNESS_CONFIG.backendBaseUrl, 'PUT', '/api/v1/pricing/prices', {
      token: shared.tenantA.accessToken,
      body: { retailer_id: shared.retailer.retailerId, sku_id: unit.sellableUnitId, price: '25.50' },
      expect: [200, 201],
    });
  }
  return { tag, productId, productName, units };
}
