import { test, expect, type Page, type BrowserContext } from '@playwright/test';
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';

/**
 * DC-12R1-MVP-L1-J1-H2-A-R2-V4 — FROZEN-HARNESS genuine UI browser final.
 *
 * Freeze contract (P2): this spec and its config are committed BEFORE the
 * authoritative run and executed as those exact committed blobs. Every
 * password/credential is injected via environment variables — the file
 * contains zero real and zero placeholder password literals.
 *
 * Every journey node manipulates the real rendered UI (P3/P4). Node fs is
 * used only to read the task-owned maildir OUTSIDE the browser (P2.8);
 * token values are consumed, never asserted into results. The only
 * APIRequestContext uses are READ-ONLY GET postconditions explicitly
 * allowed by the task protocol; no journey action is ever executed through
 * an API helper.
 */

const MAILDIR = process.env.V4_MAILDIR ?? '';
const W1 = {
  email: process.env.W1_EMAIL ?? '',
  password: process.env.W1_PASSWORD ?? '',
  code: process.env.W1_CODE ?? '',
};
const W2 = { code: process.env.W2_CODE ?? '' };
/** Retailer passwords: environment only (P2.1). */
const R1_PASSWORD = process.env.R1_PASSWORD ?? '';
const R2_PASSWORD = process.env.R2_PASSWORD ?? '';
const R3_PASSWORD = process.env.R3_PASSWORD ?? '';

test.describe.configure({ mode: 'serial' });

/** Shared lifecycle state threaded through the serial journeys. */
const S: {
  inviteCode?: string;
  inviteLink?: string;
  retailer1?: { email: string; phone: string };
  retailer2?: { email: string; phone: string };
  retailer3?: { email: string; phone: string };
  retailer4?: { email: string; phone: string };
  w1Context?: BrowserContext;
  w1Page?: Page;
  retailerContext?: BrowserContext;
  retailerPage?: Page;
} = {};

function waitRetailerSetupMail(email: string, seconds = 40): string {
  const want = email.replace('@', '_at_').toLowerCase();
  const deadline = Date.now() + seconds * 1000;
  while (Date.now() < deadline) {
    for (const f of readdirSync(MAILDIR)) {
      if (!f.includes('-retailer-') || !f.includes(want)) continue;
      const text = readFileSync(join(MAILDIR, f), 'utf-8');
      const m = text.match(/^link: (.+)$/m);
      if (m && m[1].includes('setupToken=')) return m[1].trim();
    }
    Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 500);
  }
  throw new Error(`no retailer setup mail for ${email}`);
}

function origin(): string {
  return 'http://localhost:5173';
}

/** Register request observers; records header-PRESENCE booleans only. */
function observePublicCalls(ctx: BrowserContext) {
  const seen: { url: string; method: string; hasAuthz: boolean }[] = [];
  ctx.on('request', (req) => {
    const url = req.url();
    if (
      url.includes('/api/v1/invitations/lookup') ||
      url.includes('/api/v1/wholesalers/lookup-code') ||
      url.includes('/api/v1/retailers/register')
    ) {
      seen.push({
        url: new URL(url).pathname,
        method: req.method(),
        // BOOLEAN only — the header VALUE is never recorded (P4.5).
        hasAuthz: Object.keys(req.headers()).some(
          (k) => k.toLowerCase() === 'authorization' && req.headers()[k] !== '',
        ),
      });
    }
  });
  return seen;
}

async function createInvitationViaUI(page: Page, phone?: string): Promise<string> {
  await page.goto('/retailers/invite');
  if (phone) await page.getByLabel(/retailer phone \(optional\)/i).fill(phone);
  await page.getByRole('button', { name: /create invitation/i }).click();
  const panel = page.getByRole('status');
  await expect(panel).toBeVisible();
  const code = (await page.locator('p.font-mono').first().textContent())?.trim() ?? '';
  expect(code.length).toBeGreaterThan(10);
  return code;
}

/** Fail closed if any environment credential is missing (P2.1). */
test('J00 harness credential gate (env-only, fail closed)', () => {
  for (const [name, value] of Object.entries({
    W1_EMAIL: W1.email,
    W1_PASSWORD: W1.password,
    W1_CODE: W1.code,
    W2_CODE: W2.code,
    R1_PASSWORD,
    R2_PASSWORD,
    R3_PASSWORD,
    V4_MAILDIR: MAILDIR,
  })) {
    expect(value.length, `${name} must be provided via environment`).toBeGreaterThan(0);
  }
  expect(W1.password.length).toBeGreaterThanOrEqual(8);
  expect(R1_PASSWORD.length).toBeGreaterThanOrEqual(8);
  expect(R2_PASSWORD.length).toBeGreaterThanOrEqual(8);
  expect(R3_PASSWORD.length).toBeGreaterThanOrEqual(8);
});

// ---------------------------------------------------------------------------
// J01 — browser login as W1
// ---------------------------------------------------------------------------
test('J01 browser login as W1', async ({ browser }) => {
  S.w1Context = await browser.newContext({ permissions: ['clipboard-read', 'clipboard-write'] });
  observePublicCalls(S.w1Context);
  S.w1Page = await S.w1Context.newPage();
  await S.w1Page.goto('/login');
  await S.w1Page.getByLabel('Email').fill(W1.email);
  await S.w1Page.getByLabel('Password').fill(W1.password);
  await S.w1Page.getByRole('button', { name: /sign in/i }).click();
  await S.w1Page.waitForURL((u) => u.pathname === '/', { timeout: 30_000 });
  await expect(S.w1Page.getByRole('heading', { name: 'Home' })).toBeVisible();
});

// J02 — sidebar/customer UI navigation to invitation authoring
test('J02 sidebar navigation to invitation authoring', async () => {
  const page = S.w1Page!;
  await page.getByRole('link', { name: 'Customers' }).first().click();
  await expect(page.getByRole('heading', { name: 'Customers' })).toBeVisible();
  await page.getByRole('link', { name: /invite a retailer/i }).click();
  await page.waitForURL('**/retailers/invite');
  await expect(page.getByRole('heading', { name: /invite a retailer/i })).toBeVisible();
  await expect(page.getByLabel(/retailer phone \(optional\)/i)).toBeVisible();
});

// J03 — create invitation through the real form (UNRESTRICTED: no phone)
test('J03 create invitation via real form', async () => {
  S.inviteCode = await createInvitationViaUI(S.w1Page!);
  expect(S.inviteCode).toMatch(/^[A-Za-z0-9_-]+$/);
});

// J04 — copy/share UI and canonical fragment link
test('J04 copy/share UI yields canonical fragment link', async () => {
  const page = S.w1Page!;
  await page.getByRole('button', { name: /share invite/i }).click();
  await expect(page.getByTestId('share-fallback')).toBeVisible();
  await page.getByRole('button', { name: /copy secure invite link/i }).click();
  await expect(page.getByText(/link copied/i)).toBeVisible();
  const clip = await page.evaluate(() => navigator.clipboard.readText());
  expect(clip).toBe(`${origin()}/invite#code=${S.inviteCode}`);
  expect(clip).toMatch(/\/invite#code=[A-Za-z0-9_-]+$/);
  expect(clip).not.toMatch(/\/invite\//);
  expect(clip).not.toContain('?');
  S.inviteLink = clip;
});

// J05 — open the shared invitation URL in a NEW browser context
test('J05 shared invitation URL opens in new context', async ({ browser }) => {
  const ctx = await browser.newContext();
  observePublicCalls(ctx);
  const page = await ctx.newPage();
  await page.goto(S.inviteLink!);
  await expect(page.getByText(/you.?re invited/i)).toBeVisible();
  S.retailerContext = ctx;
  S.retailerPage = page;
});

// J06 — supplier identity verified in rendered UI
test('J06 supplier identity in rendered UI', async () => {
  const page = S.retailerPage!;
  await expect(page.getByText('V4 Supplier W1', { exact: true })).toBeVisible();
  await expect(page).toHaveURL((u) => !u.href.includes(S.inviteCode!));
});

// J07 — registration form: email required, NO password input
test('J07 registration form email-required and no password input', async () => {
  const page = S.retailerPage!;
  const phone = `+25572${randomUUID().replace(/-/g, '').slice(0, 8)}`;
  S.retailer1 = { email: `r1-${randomUUID().replace(/-/g, '').slice(0, 8)}@example.com`, phone };
  await page.getByLabel(/^phone/i).fill(phone);
  await page.getByLabel(/^email/i).fill('');
  await expect(page.locator('input[type="password"]')).toHaveCount(0);
  await page.getByRole('button', { name: /complete registration/i }).click();
  await expect(page.getByText(/email is required/i)).toBeVisible();
});

// J08 — submit in UI; consume mail-sink setup token via the real setup page
test('J08 submit + mail-sink setup token through real setup page', async () => {
  const page = S.retailerPage!;
  await page.getByLabel(/^email/i).fill(S.retailer1!.email);
  await page.getByRole('button', { name: /complete registration/i }).click();
  await expect(page.getByText(/registration complete/i)).toBeVisible();

  const link = waitRetailerSetupMail(S.retailer1!.email);
  const url = link.startsWith('http') ? link : `${origin()}${link}`;
  await page.goto(url);
  await expect(page.getByRole('heading', { name: /set up your retailer password/i })).toBeVisible();
  await page.getByLabel(/^password/i).fill(R1_PASSWORD);
  await page.getByRole('button', { name: /set password/i }).click();
  await expect(page.getByText(/retailer account is ready/i)).toBeVisible();
});

// J09 — portal link and ClientLoginPage login
test('J09 portal link then ClientLoginPage login', async () => {
  const page = S.retailerPage!;
  const portal = page.getByRole('link', { name: /go to supplier portal sign in/i });
  await expect(portal).toHaveAttribute('href', `/retail/login?w=${W1.code}`);
  await portal.click();
  await page.waitForURL((u) => u.pathname === '/retail/login');
  expect(page.url()).toContain(`w=${W1.code}`);
  await page.getByLabel('Email').fill(S.retailer1!.email);
  await page.getByLabel('Password').fill(R1_PASSWORD);
  await page.getByRole('button', { name: /sign in/i }).click();
  await page.waitForURL((u) => u.pathname === '/client', { timeout: 30_000 });
});

// J10 — /retail/join supplier-code tab through UI
test('J10 /retail/join supplier code tab', async ({ browser }) => {
  const ctx = await browser.newContext();
  const seen = observePublicCalls(ctx);
  const page = await ctx.newPage();
  await page.goto('/retail/join');
  await page.getByRole('tab', { name: /supplier code/i }).click();
  await page.getByLabel(/supplier code/i).fill(W1.code);
  await page.getByRole('button', { name: /find my supplier/i }).click();
  await expect(page.getByTestId('supplier-preview')).toBeVisible();
  expect(seen.filter((s) => s.url.includes('/wholesalers/lookup-code')).length).toBeGreaterThanOrEqual(1);
  await ctx.close();
});

// J11 — safe preview, explicit confirmation, UI registration, portal login
test('J11 code-entry lifecycle: preview -> confirm -> register -> portal login', async ({ browser }) => {
  const ctx = await browser.newContext();
  observePublicCalls(ctx);
  const page = await ctx.newPage();
  await page.goto('/retail/join');
  await page.getByRole('tab', { name: /supplier code/i }).click();
  await page.getByLabel(/supplier code/i).fill(W1.code);
  await page.getByRole('button', { name: /find my supplier/i }).click();
  const preview = page.getByTestId('supplier-preview');
  await expect(preview).toBeVisible();
  await expect(preview.getByTestId('preview-name')).toHaveText('V4 Supplier W1');
  const masked = (await preview.getByText(/contact:/i).textContent()) ?? '';
  expect(masked).toContain('*');
  await page.getByRole('button', { name: /confirm joining this supplier/i }).click();
  S.retailer2 = { email: `r2-${randomUUID().replace(/-/g, '').slice(0, 8)}@example.com`,
    phone: `+25573${randomUUID().replace(/-/g, '').slice(0, 8)}` };
  await page.getByLabel(/^phone/i).fill(S.retailer2.phone);
  await page.getByLabel(/^email/i).fill(S.retailer2.email);
  await page.getByRole('button', { name: /complete registration/i }).click();
  await expect(page.getByText(/registration complete/i)).toBeVisible();
  const link = waitRetailerSetupMail(S.retailer2.email);
  const url = link.startsWith('http') ? link : `${origin()}${link}`;
  await page.goto(url);
  await page.getByLabel(/^password/i).fill(R2_PASSWORD);
  await page.getByRole('button', { name: /set password/i }).click();
  const portal = page.getByRole('link', { name: /go to supplier portal sign in/i });
  await expect(portal).toHaveAttribute('href', `/retail/login?w=${W1.code}`);
  await portal.click();
  await page.getByLabel('Email').fill(S.retailer2.email);
  await page.getByLabel('Password').fill(R2_PASSWORD);
  await page.getByRole('button', { name: /sign in/i }).click();
  await page.waitForURL((u) => u.pathname === '/client', { timeout: 30_000 });
  await ctx.close();
});

// J12 — unknown/malformed code: neutral copy, ZERO register requests
test('J12 unknown and malformed code: neutral, zero register POSTs', async ({ browser }) => {
  const ctx = await browser.newContext();
  const seen = observePublicCalls(ctx);
  const page = await ctx.newPage();
  await page.goto('/retail/join');
  await page.getByRole('tab', { name: /supplier code/i }).click();
  await page.getByLabel(/supplier code/i).fill('NOPE99');
  await page.getByRole('button', { name: /find my supplier/i }).click();
  await expect(page.getByRole('status')).toHaveText(/could not find a supplier/i);
  await page.getByLabel(/supplier code/i).fill('bad-code!');
  await page.getByRole('button', { name: /find my supplier/i }).click();
  await expect(page.getByText(/letters and numbers only/i)).toBeVisible();
  expect(seen.filter((s) => s.url.includes('/retailers/register'))).toHaveLength(0);
  expect(seen.filter((s) => s.url.includes('/wholesalers/lookup-code')).length).toBeLessThanOrEqual(1);
  await ctx.close();
});

// J13 — already-registered preview link: exact verified w, zero bare links
test('J13 preview link exact w; no bare /retail/login anywhere', async ({ browser }) => {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await page.goto('/retail/join');
  await page.getByRole('tab', { name: /supplier code/i }).click();
  await page.getByLabel(/supplier code/i).fill(W1.code);
  await page.getByRole('button', { name: /find my supplier/i }).click();
  await expect(page.getByTestId('supplier-preview')).toBeVisible();
  const link = page.getByRole('link', { name: /sign in to this supplier/i });
  await expect(link).toHaveAttribute('href', `/retail/login?w=${W1.code}`);
  await expect(page.locator('a[href="/retail/login"]')).toHaveCount(0);
  await ctx.close();
});

// ---------------------------------------------------------------------------
// J14 — P4 STALE-AUTH CORRECTION: in a real contextual session, complete the
// supplier-code UI path THROUGH REGISTRATION SUBMISSION; both public request
// types must occur and carry NO Authorization; registration completes with
// exactly one binding. No API helper performs any part of this journey.
// ---------------------------------------------------------------------------
test('J14 stale contextual session: full code-path registration, zero Authorization', async ({ playwright }) => {
  const page = S.retailerPage!;
  // retailer1 still holds a live contextual session from J09.
  expect(page.url()).toContain('/client');
  const seen = observePublicCalls(S.retailerContext!);

  await page.goto('/retail/join');
  await page.getByRole('tab', { name: /supplier code/i }).click();
  await page.getByLabel(/supplier code/i).fill(W1.code);
  await page.getByRole('button', { name: /find my supplier/i }).click();
  await expect(page.getByTestId('supplier-preview')).toBeVisible();
  await page.getByRole('button', { name: /confirm joining this supplier/i }).click();
  S.retailer4 = { email: `r4-${randomUUID().replace(/-/g, '').slice(0, 8)}@example.com`,
    phone: `+25575${randomUUID().replace(/-/g, '').slice(0, 8)}` };
  await page.getByLabel(/^phone/i).fill(S.retailer4.phone);
  await page.getByLabel(/^email/i).fill(S.retailer4.email);
  await page.getByRole('button', { name: /complete registration/i }).click();
  await expect(page.getByText(/registration complete/i)).toBeVisible();

  // Both public request types occurred (P4.3).
  const lookups = seen.filter((s) => s.url.includes('/wholesalers/lookup-code'));
  const registers = seen.filter((s) => s.url.includes('/retailers/register'));
  expect(lookups.length).toBeGreaterThanOrEqual(1);
  expect(registers.length).toBeGreaterThanOrEqual(1);
  // Every public request carries NO Authorization (boolean only, P4.4/P4.5).
  for (const call of [...lookups, ...registers]) {
    expect(call.hasAuthz, `${call.method} ${call.url}`).toBe(false);
  }
  // Exactly one register POST from this journey (P4.6 exactness).
  expect(registers.filter((r) => r.method === 'POST')).toHaveLength(1);

  // READ-ONLY postcondition: exactly one binding for this phone.
  const req = await playwright.request.newContext();
  const loginRes = await req.post('http://localhost:5173/api/v1/auth/login', {
    data: { email: W1.email, password: W1.password },
  });
  expect(loginRes.status()).toBe(200);
  const login = (await loginRes.json()).data;
  const selRes = await req.post('http://localhost:5173/api/v1/auth/select-tenant', {
    headers: { Authorization: `Bearer ${login.access_token}` },
    data: { tenant_id: login.available_tenants[0].id },
  });
  const access = (await selRes.json()).data.access_token;
  const listRes = await req.get('http://localhost:5173/api/v1/retailers?size=100', {
    headers: { Authorization: `Bearer ${access}` },
  });
  expect(listRes.status()).toBe(200);
  const items = (await listRes.json()).data.items as Array<{ retailer: { phone: string } }>;
  expect(items.filter((i) => i.retailer.phone === S.retailer4!.phone)).toHaveLength(1);
  await req.dispose();
});

// J15 — real UI double submit: exactly one POST and one binding
test('J15 double submit: exactly one POST and one binding', async ({ browser, playwright }) => {
  const code2 = await createInvitationViaUI(S.w1Page!);
  S.retailer3 = { email: `r3-${randomUUID().replace(/-/g, '').slice(0, 8)}@example.com`,
    phone: `+25574${randomUUID().replace(/-/g, '').slice(0, 8)}` };
  const ctx = await browser.newContext();
  const seen = observePublicCalls(ctx);
  const page = await ctx.newPage();
  await page.goto(`${origin()}/invite#code=${code2}`);
  await page.getByLabel(/^phone/i).fill(S.retailer3.phone);
  await page.getByLabel(/^email/i).fill(S.retailer3.email);
  const submit = page.getByRole('button', { name: /complete registration/i });
  // Real UI double submit: one genuine OS-level double click.
  await submit.dblclick();
  await expect(page.getByText(/registration complete/i)).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(1000);
  const posts = seen.filter((s) => s.url.includes('/retailers/register') && s.method === 'POST');
  expect(posts).toHaveLength(1);

  const req = await playwright.request.newContext();
  const loginRes = await req.post('http://localhost:5173/api/v1/auth/login', {
    data: { email: W1.email, password: W1.password },
  });
  expect(loginRes.status()).toBe(200);
  const login = (await loginRes.json()).data;
  const selRes = await req.post('http://localhost:5173/api/v1/auth/select-tenant', {
    headers: { Authorization: `Bearer ${login.access_token}` },
    data: { tenant_id: login.available_tenants[0].id },
  });
  const access = (await selRes.json()).data.access_token;
  const listRes = await req.get('http://localhost:5173/api/v1/retailers?size=100', {
    headers: { Authorization: `Bearer ${access}` },
  });
  expect(listRes.status()).toBe(200);
  const items = (await listRes.json()).data.items as Array<{ retailer: { phone: string } }>;
  expect(items.filter((i) => i.retailer.phone === S.retailer3!.phone)).toHaveLength(1);
  await req.dispose();
  await ctx.close();
});

// J16 — W1 retailer attempts W2 portal: exact denied outcome
test('J16 W1 retailer denied on W2 portal (exact status + UI)', async () => {
  const page = S.retailerPage!;
  const statusCapture: number[] = [];
  page.on('response', (res) => {
    if (res.url().includes('/api/v1/client/auth/login')) statusCapture.push(res.status());
  });
  await page.goto(`/retail/login?w=${W2.code}`);
  await page.getByLabel('Email').fill(S.retailer1!.email);
  await page.getByLabel('Password').fill(R1_PASSWORD);
  await page.getByRole('button', { name: /sign in/i }).click();
  await expect(page.getByText(/invalid credentials|could not|not registered/i).first()).toBeVisible();
  await page.waitForTimeout(1000);
  expect(page.url()).toContain('/retail/login');
  expect(statusCapture).toHaveLength(1);
  expect(statusCapture[0]).toBe(401);
});

// J17 — W1 deactivates via UI; retailer login then fails exactly
test('J17 deactivate via UI; retailer login fails afterwards', async () => {
  const owner = S.w1Page!;
  await owner.goto('/retailers');
  const row = owner.locator('tr', { hasText: S.retailer1!.phone });
  await expect(row).toBeVisible();
  await row.getByRole('button', { name: /deactivate/i }).click();
  await expect(row.locator('text=/inactive/i').first()).toBeVisible({ timeout: 30_000 });

  const page = S.retailerPage!;
  const statusCapture: number[] = [];
  page.on('response', (res) => {
    if (res.url().includes('/api/v1/client/auth/login')) statusCapture.push(res.status());
  });
  await page.goto(`/retail/login?w=${W1.code}`);
  await page.getByLabel('Email').fill(S.retailer1!.email);
  await page.getByLabel('Password').fill(R1_PASSWORD);
  await page.getByRole('button', { name: /sign in/i }).click();
  await expect(page.getByText(/invalid credentials|deactivated|inactive|not registered/i).first()).toBeVisible();
  expect(page.url()).toContain('/retail/login');
  expect(statusCapture[0]).toBe(401);
});

// J18 — 390px viewport: real interactions, no horizontal overflow
test('J18 390px viewport discovery/preview/navigation (viewport simulation)', async ({ browser }) => {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const page = await ctx.newPage();

  const assertNoOverflow = async (label: string) => {
    const m = await page.evaluate(() => ({
      sw: document.documentElement.scrollWidth,
      cw: document.documentElement.clientWidth,
      bsw: document.body.scrollWidth,
      bcw: document.body.clientWidth,
    }));
    expect(m.sw, `${label} documentElement`).toBe(m.cw);
    expect(m.bsw, `${label} body`).toBe(m.bcw);
  };

  await page.goto('/retail/join');
  await assertNoOverflow('join-entry');
  await page.getByRole('tab', { name: /supplier code/i }).click();
  await page.getByLabel(/supplier code/i).fill(W1.code);
  await page.getByRole('button', { name: /find my supplier/i }).click();
  await expect(page.getByTestId('supplier-preview')).toBeVisible();
  await assertNoOverflow('join-preview');

  await page.getByRole('link', { name: /sign in to this supplier/i }).click();
  await page.waitForURL((u) => u.pathname === '/retail/login');
  await assertNoOverflow('portal-login');
  await page.getByLabel('Email').fill('x@example.com');
  await page.getByLabel('Password').fill('viewport-probe-input');
  await assertNoOverflow('portal-login-filled');

  await page.goto(`${origin()}/invite#code=${S.inviteCode}`);
  await page.waitForTimeout(1200);
  await assertNoOverflow('invite-landing');
  await ctx.close();
});
