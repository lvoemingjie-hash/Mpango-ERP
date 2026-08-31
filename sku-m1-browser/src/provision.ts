/**
 * Public-API provisioning for the SKU browser harness.
 *
 * Every precondition (tenants, users, catalog products, sellable-unit
 * packages, inventory stock, retailer binding/credentials) is created through
 * accepted public API flows. No direct database rows are written anywhere.
 * Verification / credential-setup emails are received by the harness-owned
 * local SMTP sink (tools/smtp_sink.py) and parsed from the maildir.
 */
import * as fs from 'fs';
import * as path from 'path';
import { HARNESS_CONFIG } from '../playwright.config';
import { OfficialProvisioning } from './preflight';

const MAILDIR = path.resolve(__dirname, '..', 'results', 'maildir');

export interface ProvisionedUnit {
  skuCode: string;
  unit: string;
  packageQuantity: string;
  sellableUnitId: string;
  stockOnHand: string;
}
export interface ProvisionedTenant {
  key: 'tenant_a' | 'tenant_b';
  ownerEmail: string;
  ownerPassword: string;
  wholesalerCode: string;
  productId: string;
  productName: string;
  units: ProvisionedUnit[];
  accessToken: string;
}
export interface ProvisionedRetailer {
  email: string;
  password: string;
  wholesalerCode: string;
  accessToken: string;
  retailerId: string;
}
export interface ProvisionedState {
  tenantA: ProvisionedTenant;
  tenantB: ProvisionedTenant;
  retailer: ProvisionedRetailer;
}

async function api(
  method: string,
  url: string,
  opts: { token?: string; body?: unknown; expect?: number[] } = {},
): Promise<{ status: number; json: any; text: string }> {
  const res = await fetch(`${HARNESS_CONFIG.backendBaseUrl}${url}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(opts.token ? { Authorization: `Bearer ${opts.token}` } : {}),
    },
    body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
  });
  const text = await res.text();
  let json: any = null;
  try { json = JSON.parse(text); } catch { /* non-JSON body */ }
  const expected = opts.expect;
  if (expected && !expected.includes(res.status)) {
    throw new Error(`API ${method} ${url} -> ${res.status} (expected ${expected}): ${text.slice(0, 300)}`);
  }
  return { status: res.status, json, text };
}

function dataPayload(json: any): any {
  // Product envelope: {success, data: {...}} — tolerate both envelopes.
  return json?.data !== undefined ? json.data : json;
}

/** Decode a quoted-printable email body (soft breaks + =XX sequences). */
function decodeQuotedPrintable(text: string): string {
  return text
    .replace(/=\r?\n/g, '')
    .replace(/=([0-9A-Fa-f]{2})/g, (_, hex) => String.fromCharCode(parseInt(hex, 16)));
}

function extractTokenFromEmail(
  mhContent: string,
  kind: 'verify' | 'setup' | 'retailer_setup',
): string {
  const body = decodeQuotedPrintable(mhContent);
  const linkMatch = body.match(/https?:\/\/[^\s"'<>]+/g) ?? [];
  for (const link of linkMatch) {
    const url = new URL(link);
    // Token may travel as a query parameter OR inside the URL fragment.
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

/** Wait for a kind-specific, not-yet-consumed mail; consume it on return. */
async function waitForMail(
  recipient: string,
  kind: 'verify' | 'setup' | 'retailer_setup',
  timeoutMs = 45_000,
): Promise<string> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const mail = findMail(recipient, kind);
    if (mail) {
      // Read first, then consume (move out of new/) so no reader can race
      // the rename and no later lookup can reuse this message.
      const content = fs.readFileSync(mail, 'utf-8');
      fs.renameSync(mail, `${mail}.consumed`);
      return content;
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`mail for ${recipient} (kind=${kind}) did not arrive within ${timeoutMs}ms`);
}

async function provisionTenant(
  key: 'tenant_a' | 'tenant_b',
  tenant: Omit<OfficialProvisioning['tenant_a'], 'retailer'>,
): Promise<ProvisionedTenant> {
  // 1. Public signup (tenant registration; verification email via local SMTP).
  await api('POST', '/api/v1/auth/signup', {
    body: { companyName: tenant.company_name, country: tenant.country, email: tenant.owner_email },
    expect: [202, 409],
  });
  const verifyContent = await waitForMail(tenant.owner_email, 'verify');
  const verifyToken = extractTokenFromEmail(verifyContent, 'verify');
  await api('POST', '/api/v1/auth/verify-email', { body: { token: verifyToken }, expect: [200] });

  // 2. Owner credential setup.
  const setupContent = await waitForMail(tenant.owner_email, 'setup');
  const setupToken = extractTokenFromEmail(setupContent, 'setup');
  await api('POST', '/api/v1/auth/onboarding/setup-credential', {
    body: { setupToken, password: tenant.owner_password },
    expect: [200],
  });

  // 3. Login (identity level) then tenant selection.
  const login = await api('POST', '/api/v1/auth/login', {
    body: { email: tenant.owner_email, password: tenant.owner_password },
    expect: [200],
  });
  const loginData = dataPayload(login.json);
  const identityToken: string = loginData.accessToken ?? loginData.access_token
    ?? loginData.tokens?.accessToken ?? loginData.tokens?.access_token;
  // Identity login returns available_tenants [{id, code, name}]; upgrade to a
  // contextual JWT via /auth/select-tenant {tenant_id}.
  let accessToken = identityToken;
  const firstTenant = loginData.availableTenants?.[0] ?? loginData.available_tenants?.[0];
  if (firstTenant?.id) {
    const selected = await api('POST', '/api/v1/auth/select-tenant', {
      token: identityToken,
      body: { tenant_id: firstTenant.id },
      expect: [200],
    });
    accessToken = dataPayload(selected.json).access_token
      ?? dataPayload(selected.json).accessToken;
  }

  // 4. Wholesaler portal code (needed for the retailer login).
  const wsList = await api('GET', '/api/v1/wholesalers', { token: accessToken, expect: [200] });
  const wsData = dataPayload(wsList.json);
  const wsItems: any[] = wsData.items ?? wsData.wholesalers ?? [];
  const wholesalerCode: string = String(wsItems[0]?.code ?? '');
  if (!wholesalerCode) {
    throw new Error(`wholesaler code unavailable from /wholesalers: ${wsList.text.slice(0, 200)}`);
  }

  // 5. Catalog product with >= 2 sellable-unit packages.
  const product = await api('POST', '/api/v1/catalog-products', {
    token: accessToken,
    body: {
      name: tenant.product_name,
      category: 'staples',
      is_active: true,
      sellable_units: tenant.packages.map((p) => ({
        sku_code: p.sku_code,
        unit: p.unit,
        package_quantity: p.package_quantity,
        is_active: true,
      })),
    },
    expect: [201, 200],
  });
  const productData = dataPayload(product.json);
  const productId: string = productData.id;
  const rawUnits: any[] = productData.sellableUnits ?? productData.sellable_units ?? productData.skus ?? [];
  const units: ProvisionedUnit[] = tenant.packages.map((p) => {
    const match = rawUnits.find((u: any) => (u.skuCode ?? u.sku_code) === p.sku_code)
      ?? rawUnits.find((u: any) => u.name === p.sku_code)
      ?? {};
    return {
      skuCode: p.sku_code,
      unit: p.unit,
      packageQuantity: p.package_quantity,
      sellableUnitId: match.id ?? match.sellableUnitId ?? match.sellable_unit_id ?? '',
      stockOnHand: '',
    };
  });
  for (const unit of units) {
    if (!/^[0-9a-f-]{36}$/i.test(unit.sellableUnitId)) {
      throw new Error(`sellable unit id missing for ${unit.skuCode}: ${JSON.stringify(unit).slice(0, 200)}`);
    }
  }

  // 6. Independent inventory stock per sellable unit (public inventory adjust API).
  for (const p of tenant.packages) {
    await api('POST', '/api/v1/inventory/adjust', {
      token: accessToken,
      body: { sku_code: p.sku_code, quantity: p.stock_adjust, reason: 'stocktake' },
      expect: [200, 201],
    });
  }
  for (const unit of units) {
    const stock = await api(
      'GET',
      `/api/v1/inventory/stocks/${encodeURIComponent(unit.skuCode)}`,
      { token: accessToken, expect: [200] },
    );
    const stockData = dataPayload(stock.json);
    unit.stockOnHand = String(
      stockData.quantityOnHand ?? stockData.quantity_on_hand ?? stockData.quantity ?? '',
    );
  }

  return {
    key,
    ownerEmail: tenant.owner_email,
    ownerPassword: tenant.owner_password,
    wholesalerCode,
    productId,
    productName: tenant.product_name,
    units,
    accessToken,
  };
}

async function provisionRetailer(
  tenant: ProvisionedTenant,
  retailerSpec: OfficialProvisioning['tenant_a']['retailer'],
): Promise<ProvisionedRetailer> {
  // 1. Wholesaler invites the retailer (public invitation API).
  const invitation = await api('POST', '/api/v1/invitations', {
    token: tenant.accessToken,
    body: { retailer_phone: retailerSpec.phone },
    expect: [201, 200],
  });
  const invitationCode: string = dataPayload(invitation.json).code;

  // 2. Retailer self-registers through the dual-entry public flow.
  const registered = await api('POST', '/api/v1/retailers/register', {
    body: {
      invitation_code: invitationCode,
      phone: retailerSpec.phone,
      name: retailerSpec.name,
      email: retailerSpec.email,
    },
    expect: [201],
  });
  const registeredData = dataPayload(registered.json);
  // Register response: {retailer: {...}, binding: {...}, wholesaler_code}.
  const retailerId: string = String(
    registeredData.retailer?.id ?? registeredData.retailerId ?? registeredData.retailer_id ?? '',
  );
  if (!/^[0-9a-f-]{36}$/i.test(retailerId)) {
    throw new Error(`retailer id missing from register response: ${registered.text.slice(0, 300)}`);
  }

  // 3. Retailer credential setup email -> set password (body-only token).
  const setupContent = await waitForMail(retailerSpec.email, 'retailer_setup');
  const setupToken = extractTokenFromEmail(setupContent, 'retailer_setup');
  await api('POST', '/api/v1/retailers/setup-credential', {
    body: { setup_token: setupToken, new_password: retailerSpec.password },
    expect: [200],
  });

  // 4. Retailer portal login (per-supplier).
  const login = await api('POST', '/api/v1/client/auth/login', {
    body: {
      email: retailerSpec.email,
      password: retailerSpec.password,
      wholesaler_code: tenant.wholesalerCode,
    },
    expect: [200],
  });
  const loginData = dataPayload(login.json);
  const accessToken: string = loginData.accessToken ?? loginData.access_token
    ?? loginData.tokens?.accessToken ?? loginData.tokens?.access_token;
  return {
    email: retailerSpec.email,
    password: retailerSpec.password,
    wholesalerCode: tenant.wholesalerCode,
    accessToken,
    retailerId,
  };
}

export async function provisionAll(): Promise<ProvisionedState> {
  const raw = fs.readFileSync(HARNESS_CONFIG.provisioningPath, 'utf-8');
  const official = JSON.parse(raw) as OfficialProvisioning;
  const tenantA = await provisionTenant('tenant_a', official.tenant_a);
  const tenantB = await provisionTenant('tenant_b', official.tenant_b);
  const retailer = await provisionRetailer(tenantA, official.tenant_a.retailer);

  // Retailer prices (client orders refuse to price without them).
  for (const unit of tenantA.units) {
    await api('PUT', '/api/v1/pricing/prices', {
      token: tenantA.accessToken,
      body: { retailer_id: retailer.retailerId, sku_id: unit.sellableUnitId, price: '25.50' },
      expect: [200, 201],
    });
  }

  const state: ProvisionedState = { tenantA, tenantB, retailer };
  fs.mkdirSync(path.dirname(path.join(MAILDIR, 'provisioned.json')), { recursive: true });
  fs.writeFileSync(path.join(MAILDIR, 'provisioned.json'), JSON.stringify(state, null, 2));
  return state;
}

export function loadProvisionedState(): ProvisionedState {
  const file = path.join(MAILDIR, 'provisioned.json');
  if (!fs.existsSync(file)) throw new Error('provisioned state absent — global setup did not run');
  return JSON.parse(fs.readFileSync(file, 'utf-8')) as ProvisionedState;
}
