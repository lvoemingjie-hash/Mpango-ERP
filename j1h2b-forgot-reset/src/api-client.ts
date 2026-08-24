/**
 * Official-API client and provisioning orchestrator (task directives #7, #8, #17).
 *
 * The HTTP API is used for exactly two purposes:
 *  1. Provisioning preconditions through the official lifecycle only —
 *     signup → maildir verification link (browser-external read) →
 *     verify-email → maildir owner-setup link → setup-credential → login →
 *     select-tenant; and the M1 shared-identity provisioning chain
 *     (POST /api/v1/users with the SAME normalized email and the SAME
 *     initial password on both tenants, PUT /users/{id}/roles with the formal
 *     admin role on both sides, precondition gate: M login sees EXACTLY
 *     W1/W2).
 *  2. Nothing else. Forgot/reset journey actions are performed exclusively
 *     through the rendered UI in the spec files.
 *
 * Prohibitions honored: no SQL, no direct ORM, no hand-written hashes, no
 * debug endpoints, no database patching. Errors are sanitized (endpoint name
 * + status only); response bodies stay in memory and are never logged.
 */

import { randomUUID } from 'node:crypto';
import type { JourneyEnv } from './env.js';
import { assertSan } from './assertions.js';
import { waitForLink } from './maildir.js';
import { a1State, m1State, type ProvisioningHandle } from './token-store.js';

interface ApiResult {
  status: number;
  ok: boolean;
  json: any | undefined;
}

async function apiFetch(
  url: string,
  init: RequestInit,
  label: string,
  expectedStatuses: number[],
): Promise<ApiResult> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 30_000);
  let response: Response;
  try {
    response = await fetch(url, { ...init, signal: controller.signal });
  } catch {
    throw new Error(`provisioning: network failure calling ${label} (details withheld)`);
  } finally {
    clearTimeout(timer);
  }
  let json: any | undefined;
  try {
    json = await response.json();
  } catch {
    json = undefined;
  }
  if (!expectedStatuses.includes(response.status)) {
    const code = typeof json?.detail?.code === 'string' ? json.detail.code : 'UNKNOWN';
    throw new Error(
      `provisioning: ${label} answered ${response.status} (code=${code}); expected ${expectedStatuses.join('|')}`,
    );
  }
  return { status: response.status, ok: true, json };
}

function bearer(token: string): { Authorization: string } {
  return { Authorization: `Bearer ${token}` };
}

const JSON_HEADERS = { 'Content-Type': 'application/json' };

// ---------------------------------------------------------------------------
// Official lifecycle primitives
// ---------------------------------------------------------------------------

export async function signupWholesaler(
  env: JourneyEnv,
  email: string,
  companyName: string,
): Promise<void> {
  await apiFetch(
    `${env.apiBaseUrl}/api/v1/auth/signup`,
    {
      method: 'POST',
      headers: { ...JSON_HEADERS, 'Idempotency-Key': randomUUID() },
      body: JSON.stringify({ companyName, country: env.signupCountry, email }),
    },
    'POST /api/v1/auth/signup',
    [202],
  );
}

export async function verifySignupEmail(
  env: JourneyEnv,
  email: string,
  sinceMs: number,
): Promise<void> {
  const hit = await waitForLink({
    root: env.maildirRoot,
    kind: 'verify',
    recipient: email,
    sinceMs,
  });
  await apiFetch(
    `${env.apiBaseUrl}/api/v1/auth/verify-email`,
    {
      method: 'POST',
      headers: JSON_HEADERS,
      body: JSON.stringify({ token: hit.token }),
    },
    'POST /api/v1/auth/verify-email',
    [200],
  );
}

export async function consumeOwnerSetup(
  env: JourneyEnv,
  email: string,
  password: string,
  sinceMs: number,
): Promise<void> {
  const hit = await waitForLink({
    root: env.maildirRoot,
    kind: 'setup',
    recipient: email,
    sinceMs,
  });
  await apiFetch(
    `${env.apiBaseUrl}/api/v1/auth/onboarding/setup-credential`,
    {
      method: 'POST',
      headers: JSON_HEADERS,
      body: JSON.stringify({ setupToken: hit.token, password }),
    },
    'POST /api/v1/auth/onboarding/setup-credential',
    [200],
  );
}

export interface LoginOutcome {
  ok: boolean;
  status: number;
  data?: {
    access_token: string;
    roles: string[];
    available_tenants: Array<{ id: string; code: string; name: string }>;
  };
}

export async function loginIdentity(
  env: JourneyEnv,
  email: string,
  password: string,
): Promise<LoginOutcome> {
  const result = await apiFetch(
    `${env.apiBaseUrl}/api/v1/auth/login`,
    {
      method: 'POST',
      headers: JSON_HEADERS,
      body: JSON.stringify({ email, password }),
    },
    'POST /api/v1/auth/login',
    [200, 401],
  );
  if (result.status === 401) return { ok: false, status: 401 };
  return { ok: true, status: 200, data: result.json?.data };
}

async function selectTenant(
  env: JourneyEnv,
  tenantId: string,
  identityToken: string,
): Promise<string> {
  const result = await apiFetch(
    `${env.apiBaseUrl}/api/v1/auth/select-tenant`,
    {
      method: 'POST',
      headers: { ...JSON_HEADERS, ...bearer(identityToken) },
      body: JSON.stringify({ tenant_id: tenantId }),
    },
    'POST /api/v1/auth/select-tenant',
    [200],
  );
  const token = result.json?.data?.access_token;
  assertSan(typeof token === 'string' && token.length > 0, 'provisioning: select-tenant returned no contextual token');
  return token as string;
}

// ---------------------------------------------------------------------------
// Tenant-scoped admin API (users/roles) — M1 provisioning only
// ---------------------------------------------------------------------------

async function listRoles(env: JourneyEnv, ctxToken: string): Promise<Array<{ id: string; name: string }>> {
  const result = await apiFetch(
    `${env.apiBaseUrl}/api/v1/roles`,
    { method: 'GET', headers: bearer(ctxToken) },
    'GET /api/v1/roles',
    [200],
  );
  return result.json?.data ?? [];
}

async function createUserInTenant(
  env: JourneyEnv,
  ctxToken: string,
  email: string,
  password: string,
  fullName: string,
): Promise<string> {
  const result = await apiFetch(
    `${env.apiBaseUrl}/api/v1/users`,
    {
      method: 'POST',
      headers: { ...JSON_HEADERS, ...bearer(ctxToken) },
      body: JSON.stringify({ email, password, full_name: fullName }),
    },
    'POST /api/v1/users',
    [201],
  );
  const id = result.json?.data?.id;
  assertSan(typeof id === 'string' && id.length > 0, 'provisioning: POST /users returned no user id');
  return id as string;
}

async function assignAdminRole(
  env: JourneyEnv,
  ctxToken: string,
  userId: string,
): Promise<void> {
  const roles = await listRoles(env, ctxToken);
  const admin = roles.find((role) => role.name === 'admin');
  assertSan(admin !== undefined, 'provisioning: tenant has no admin role in GET /api/v1/roles');
  const result = await apiFetch(
    `${env.apiBaseUrl}/api/v1/users/${userId}/roles`,
    {
      method: 'PUT',
      headers: { ...JSON_HEADERS, ...bearer(ctxToken) },
      body: JSON.stringify({ role_ids: [admin.id] }),
    },
    'PUT /api/v1/users/{id}/roles',
    [200],
  );
  const names: string[] = (result.json?.data?.roles ?? []).map((role: any) => role.name);
  assertSan(names.includes('admin'), 'provisioning: PUT roles response does not list the admin role for the user');
}

async function softDeleteUser(env: JourneyEnv, ctxToken: string, userId: string): Promise<void> {
  await apiFetch(
    `${env.apiBaseUrl}/api/v1/users/${userId}`,
    { method: 'DELETE', headers: bearer(ctxToken) },
    'DELETE /api/v1/users/{id}',
    [200, 204],
  );
}

// ---------------------------------------------------------------------------
// Provisioning orchestrators (idempotent within the single authoritative run)
// ---------------------------------------------------------------------------

async function provisionOwner(
  env: JourneyEnv,
  email: string,
  password: string,
  companyName: string,
): Promise<ProvisioningHandle> {
  const startedAt = Date.now();
  await signupWholesaler(env, email, companyName);
  await verifySignupEmail(env, email, startedAt);
  await consumeOwnerSetup(env, email, password, startedAt);
  const login = await loginIdentity(env, email, password);
  assertSan(login.ok && login.data !== undefined, `provisioning: owner login failed for ${email}`);
  const tenants = login.data!.available_tenants;
  assertSan(tenants.length === 1, `provisioning: fresh owner ${email} must expose exactly one workspace`);
  const ctxToken = await selectTenant(env, tenants[0].id, login.data!.access_token);
  return { ctxToken, tenantId: tenants[0].id, tenantName: tenants[0].name };
}

/** Provision A1 (single-copy journey protagonist) via the official lifecycle. */
export async function ensureA1Provisioned(env: JourneyEnv): Promise<ProvisioningHandle> {
  const store = a1State();
  if (store.provisioned) return store.provisioned;
  const handle = await provisionOwner(env, env.a1.email, env.a1.initialPassword, env.a1.companyName);
  store.provisioned = handle;
  return handle;
}

/**
 * Provision X (ineligible email): create a tenant user through the official
 * API, then soft-delete it through the official API, so the email exists only
 * as a deleted user — no active tenant copy, hence ineligible for forgot.
 */
export async function ensureIneligibleEmailProvisioned(env: JourneyEnv): Promise<void> {
  const store = a1State();
  if (store.ineligibleProvisioned) return;
  const owner = await ensureA1Provisioned(env);
  const userId = await createUserInTenant(
    env,
    owner.ctxToken,
    env.ineligible.email,
    env.ineligible.tempPassword,
    'J1H2B Ineligible Fixture',
  );
  await softDeleteUser(env, owner.ctxToken, userId);
  store.ineligibleProvisioned = true;
}

/**
 * Provision the M1 shared identity through the official API only:
 *  1. W1/W2 owners (different emails) via the official lifecycle;
 *  2. M created in BOTH tenants via POST /api/v1/users — same normalized
 *     email, SAME initial password P1 on both sides;
 *  3. formal admin role assigned on BOTH sides via PUT /users/{id}/roles;
 *  4. precondition gate: M login with P1 exposes EXACTLY {W1, W2}.
 */
export async function ensureM1Provisioned(env: JourneyEnv): Promise<void> {
  const store = m1State();
  if (store.provisionGatePassed) return;

  const w1 = await provisionOwner(
    env,
    env.m1.w1.ownerEmail,
    env.m1.w1.ownerPassword,
    env.m1.w1.companyName,
  );
  const w2 = await provisionOwner(
    env,
    env.m1.w2.ownerEmail,
    env.m1.w2.ownerPassword,
    env.m1.w2.companyName,
  );

  const userId1 = await createUserInTenant(
    env,
    w1.ctxToken,
    env.m1.m.email,
    env.m1.m.initialPassword,
    env.m1.m.fullName,
  );
  await assignAdminRole(env, w1.ctxToken, userId1);

  const userId2 = await createUserInTenant(
    env,
    w2.ctxToken,
    env.m1.m.email,
    env.m1.m.initialPassword,
    env.m1.m.fullName,
  );
  await assignAdminRole(env, w2.ctxToken, userId2);

  const mLogin = await loginIdentity(env, env.m1.m.email, env.m1.m.initialPassword);
  assertSan(mLogin.ok && mLogin.data !== undefined, 'M1 precondition gate: M login with the shared initial password failed');
  const names = mLogin.data!.available_tenants.map((tenant) => tenant.name).sort();
  const expected = [env.m1.w1.companyName, env.m1.w2.companyName].sort();
  assertSan(
    names.length === 2 && names[0] === expected[0] && names[1] === expected[1],
    'M1 precondition gate: M login must expose exactly the two expected workspaces (W1/W2); observed count/names withheld',
  );

  store.w1 = w1;
  store.w2 = w2;
  store.provisionGatePassed = true;
}
