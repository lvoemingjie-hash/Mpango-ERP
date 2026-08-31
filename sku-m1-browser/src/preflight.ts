/**
 * Fail-closed preflight for the SKU browser harness.
 *
 * Classification contract:
 *   - missing official provisioning data          => PRECONDITION_FAIL
 *   - wrong candidate SHA                         => VOID
 *   - wrong Alembic head/parent                   => VOID
 *   - Redis unavailable/nonempty/wrong DB         => VOID
 *   - sentinel reachable                          => VOID
 *   - backend/frontend health red                 => VOID
 *
 * Any VOID/PRECONDITION_FAIL aborts global setup: browser launch count stays 0
 * and browser nodes report NOT_RUN.
 */
import * as child_process from 'child_process';
import * as fs from 'fs';
import * as net from 'net';
import * as path from 'path';
import { HARNESS_CONFIG } from '../playwright.config';

export type PreflightOutcome =
  | { kind: 'OK' }
  | { kind: 'PRECONDITION_FAIL'; reasons: string[] }
  | { kind: 'VOID'; reasons: string[] };

export interface OfficialProvisioning {
  schema: string;
  tenant_a: {
    company_name: string;
    country: string;
    owner_email: string;
    owner_password: string;
    product_name: string;
    packages: { sku_code: string; unit: string; package_quantity: string; stock_adjust: number }[];
    retailer: { name: string; phone: string; email: string; password: string };
  };
  tenant_b: {
    company_name: string;
    country: string;
    owner_email: string;
    owner_password: string;
    product_name: string;
    packages: { sku_code: string; unit: string; package_quantity: string; stock_adjust: number }[];
  };
}

export function loadOfficialProvisioning(): OfficialProvisioning | { error: string } {
  try {
    const raw = fs.readFileSync(HARNESS_CONFIG.provisioningPath, 'utf-8');
    const parsed = JSON.parse(raw) as OfficialProvisioning;
    const missing: string[] = [];
    if (parsed.schema !== 'sku-m1-browser/official-provisioning/1') missing.push('schema');
    for (const tenantKey of ['tenant_a', 'tenant_b'] as const) {
      const tenant = parsed[tenantKey];
      if (!tenant) { missing.push(tenantKey); continue; }
      if (!tenant.company_name) missing.push(`${tenantKey}.company_name`);
      if (!tenant.owner_email) missing.push(`${tenantKey}.owner_email`);
      if (!tenant.owner_password) missing.push(`${tenantKey}.owner_password`);
      if (!tenant.product_name) missing.push(`${tenantKey}.product_name`);
      if (!tenant.packages?.length) missing.push(`${tenantKey}.packages`);
      if (tenantKey === 'tenant_a') {
        const retailerBlock = (tenant as OfficialProvisioning['tenant_a']).retailer;
        if (!retailerBlock?.email) missing.push(`${tenantKey}.retailer.email`);
        if (!retailerBlock?.password) missing.push(`${tenantKey}.retailer.password`);
      }
    }
    if (missing.length) return { error: `official provisioning data missing keys: ${missing.join(', ')}` };
    return parsed;
  } catch (err) {
    return { error: `official provisioning data unreadable: ${(err as Error).message}` };
  }
}

async function fetchOk(url: string, timeoutMs = 8000): Promise<{ ok: boolean; status: number; body: string }> {
  // The local frontend may run on a self-signed certificate (https://127.0.0.1).
  // Node's global fetch cannot bypass TLS verification, so health probes use
  // stdlib http/https with rejectUnauthorized disabled for THIS loopback probe
  // only. The browser layer handles the certificate via ignoreHTTPSErrors.
  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      try { req.destroy(); } catch { /* already closed */ }
      resolve({ ok: false, status: 0, body: 'timeout' });
    }, timeoutMs);
    const onResult = (res: { statusCode?: number; on: Function }) => {
      const chunks: Buffer[] = [];
      res.on('data', (d: Buffer) => chunks.push(d));
      res.on('end', () => {
        clearTimeout(timer);
        const status = res.statusCode ?? 0;
        resolve({ ok: status >= 200 && status < 400, status, body: Buffer.concat(chunks).toString('utf-8').slice(0, 400) });
      });
    };
    let req: import('http').ClientRequest;
    if (url.startsWith('https:')) {
      req = require('https').get(
        url,
        { rejectUnauthorized: false },
        onResult,
      );
    } else {
      req = require('http').get(url, onResult);
    }
    req.on('error', (err: Error) => {
      clearTimeout(timer);
      resolve({ ok: false, status: 0, body: err.message });
    });
  });
}

/** Minimal RESP probe over raw sockets — mirrors the runner's live Redis authority:
 *  PING, SELECT <authority db>, DBSIZE == 0, sentinel endpoint unreachable. */
async function redisAuthorityProbe(): Promise<string[]> {
  const problems: string[] = [];
  const execute = (payload: string[]): Promise<string[]> =>
    new Promise((resolve, reject) => {
      const socket = net.createConnection(
        { host: HARNESS_CONFIG.redisHost, port: HARNESS_CONFIG.redisPort },
        () => socket.write(payload.map((line) => line + '\r\n').join('')),
      );
      const chunks: Buffer[] = [];
      socket.on('data', (d) => chunks.push(d));
      socket.on('error', reject);
      setTimeout(() => {
        const text = Buffer.concat(chunks).toString('latin1');
        socket.destroy();
        // RESP replies arrive as simple strings (+PONG), integers (:0) or
        // errors (-ERR ...). Strip the type prefixes for uniform matching.
        resolve(
          text
            .split('\r\n')
            .filter((l) => l && !l.startsWith('*') && !l.startsWith('$'))
            .map((l) => (l.startsWith('+') || l.startsWith('-') || l.startsWith(':') ? l.slice(1) : l)),
        );
      }, 1500);
    });
  let replies: string[];
  try {
    replies = await execute(['PING', `SELECT ${HARNESS_CONFIG.redisAuthorityDb}`, 'DBSIZE']);
  } catch (err) {
    return [`redis:connect_failed (${(err as Error).message})`];
  }
  if (!replies.includes('PONG')) problems.push('redis:ping_failed');
  const selectIdx = replies.findIndex((r) => r === '+OK' || r === 'OK');
  if (selectIdx < 0) problems.push('redis:select_failed');
  const numeric = replies.filter((r) => /^\d+$/.test(r));
  if (!numeric.includes('0')) {
    problems.push(`redis:db_nonempty(${numeric.join(',') || 'missing'})`);
  }
  // Sentinel must remain unreachable.
  await new Promise<void>((resolve) => {
    const probe = net.createConnection(
      { host: HARNESS_CONFIG.sentinelEndpoint.host, port: HARNESS_CONFIG.sentinelEndpoint.port },
      () => { probe.destroy(); problems.push('redis:sentinel_reachable'); resolve(); },
    );
    probe.on('error', () => resolve());
    probe.setTimeout(1500, () => { probe.destroy(); resolve(); });
  });
  return problems;
}

function gitHead(repoRoot: string): string {
  const out = child_process.execSync('git rev-parse HEAD', { cwd: repoRoot, encoding: 'utf-8' });
  return out.trim();
}

/** Static alembic tree verification: exactly one head, byte-equal to the
 *  expected head, whose down_revision is the exact expected parent. */
function alembicTreeProblems(): string[] {
  const dir = HARNESS_CONFIG.backendAlembicVersionsDir;
  let entries: string[];
  try {
    entries = fs.readdirSync(dir);
  } catch (err) {
    return [`alembic:tree_unreadable (${(err as Error).message})`];
  }
  const revs = new Map<string, string | null>();
  const fileRe = /revision(?::\s*str)?\s*=\s*['"]([^'"]+)['"]/;
  const downRe = /down_revision(?::[^=]*)?\s*=\s*(?:['"]([^'"]+)['"]|None)/;
  for (const name of entries) {
    if (!name.endsWith('.py')) continue;
    const text = fs.readFileSync(path.join(dir, name), 'utf-8');
    const rev = text.match(fileRe)?.[1];
    const down = text.match(downRe);
    if (rev) revs.set(rev, down ? (down[1] ?? null) : null);
  }
  const downs = new Set([...revs.values()].filter((d): d is string => d !== null));
  const heads = [...revs.keys()].filter((r) => !downs.has(r));
  if (heads.length !== 1) return [`alembic:multiple_heads (${heads.length})`];
  if (heads[0] !== HARNESS_CONFIG.expectedAlembicHead) return [`alembic:head_mismatch`];
  if (revs.get(heads[0]) !== HARNESS_CONFIG.expectedAlembicParent) return [`alembic:parent_mismatch`];
  return [];
}

export async function runPreflight(repoRoot: string): Promise<{
  outcome: PreflightOutcome;
  provisioning: OfficialProvisioning | null;
}> {
  const voidReasons: string[] = [];
  const preconditionReasons: string[] = [];

  // 1. Official provisioning data.
  const provisioning = loadOfficialProvisioning();
  if ('error' in provisioning) preconditionReasons.push(provisioning.error);

  // 2. Candidate SHA binding.
  let head = '';
  try {
    head = gitHead(repoRoot);
  } catch (err) {
    voidReasons.push(`candidate:git_head_unreadable (${(err as Error).message})`);
  }
  if (head && HARNESS_CONFIG.candidateSha && head !== HARNESS_CONFIG.candidateSha) {
    voidReasons.push(`candidate:sha_mismatch(live=${head.slice(0, 12)} expected=${HARNESS_CONFIG.candidateSha.slice(0, 12)})`);
  }
  if (head && !HARNESS_CONFIG.candidateSha) {
    voidReasons.push('candidate:expected_sha_absent');
  }

  // 3. Alembic head/parent.
  voidReasons.push(...alembicTreeProblems().map((p) => `alembic-tree:${p.replace('alembic:', '')}`));

  // 4. Redis authority + sentinel.
  voidReasons.push(...(await redisAuthorityProbe()));

  // 5. Backend / frontend health.
  try {
    const health = await fetchOk(`${HARNESS_CONFIG.backendBaseUrl}/health`);
    if (!health.ok) voidReasons.push(`backend:health_red(status=${health.status})`);
  } catch (err) {
    voidReasons.push(`backend:health_unreachable (${(err as Error).message})`);
  }
  try {
    const home = await fetchOk(HARNESS_CONFIG.frontendBaseUrl);
    if (!home.ok) voidReasons.push(`frontend:health_red(status=${home.status})`);
    else if (!/<!doctype html|<div id="root"/i.test(home.body)) {
      voidReasons.push('frontend:not_the_production_bundle');
    }
  } catch (err) {
    voidReasons.push(`frontend:health_unreachable (${(err as Error).message})`);
  }

  const provisioned: OfficialProvisioning | null =
    'error' in provisioning ? null : provisioning;
  if (preconditionReasons.length) {
    return { outcome: { kind: 'PRECONDITION_FAIL', reasons: preconditionReasons }, provisioning: null };
  }
  if (voidReasons.length) {
    return { outcome: { kind: 'VOID', reasons: voidReasons }, provisioning: null };
  }
  return { outcome: { kind: 'OK' }, provisioning: provisioned };
}
