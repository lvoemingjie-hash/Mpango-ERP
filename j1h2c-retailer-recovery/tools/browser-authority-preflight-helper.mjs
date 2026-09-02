#!/usr/bin/env node
/**
 * Runner-owned authority preflight helper (B1-R6-R5).
 *
 * Spawned ONLY by tools/browser-authority-runner.mjs as a fresh node child
 * at the canonical module-relative path (fixed process.execPath, argv
 * array, sanitized NODE-x and GIT-x stripped environment, private stdin). It is
 * intentionally self-contained — it imports nothing from the runner — so a
 * pristine process performs the checks; launcher-process mutations cannot
 * touch it, and the runner re-validates the exact output payload shape.
 *
 * B1-R6-R5 LIFECYCLE TRUTH: the pre-run proof is
 * `owner_identity_fresh_unregistered` — the J1H2C retailer identity MUST
 * NOT be able to log in before the run (login refused = fresh /
 * unregistered). This is lifecycle-compatible with the harness beforeAll,
 * which stays the SOLE register -> setup-credential -> login lifecycle: a
 * pre-run login that SUCCEEDED would prove the identity already
 * established, and the harness registration would then conflict (409). The
 * former pre-run established-login requirement
 * contradicted the harness precondition and is removed.
 *
 * Inputs (exact schema, private stdin):
 *   { schema, timeout_ms, values }                              (required)
 *   { schema, timeout_ms, values, host_preflight }              (extended)
 * `values` keys must equal the canonical profile field keys exactly; the
 * profile is re-read from THIS module's own location, never from a caller.
 *
 * `host_preflight` belongs to the task-private execution contract that the
 * OUTER authority preflight (future Lubuntu gate) owns: PG/Redis/Alembic
 * reachability and authority port ownership are host-level checks this
 * helper never executes itself. When an outer layer supplies results
 * (e.g. the version-controlled tools/host-preflight.mjs result block),
 * they are validated (fixed ids, exact shape) and folded into the verdict;
 * when absent, the report is transparent (host_checks_present = 0).
 *
 * Output (exact schema, single stdout line, labels/booleans/categories and
 * counts ONLY — never a URL, email, password, token, or code value):
 *   { schema, ok, checks: [{ id, ok, category }...], counts }
 *
 * Any RED check, exception, or timeout is a reported RED — the runner VOIDs
 * before authorize. Malformed input exits nonzero without a payload.
 */

import { createHash } from 'node:crypto';
import { readFileSync, readSync, writeSync } from 'node:fs';
import { accessSync, existsSync, readdirSync, realpathSync, statSync } from 'node:fs';
import { constants as fsConstants } from 'node:fs';
import http from 'node:http';
import https from 'node:https';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const INPUT_SCHEMA = 'j1h2c/browser-authority-preflight-input/1';
const RESULT_SCHEMA = 'j1h2c/browser-authority-preflight-result/1';
const MAX_STDIN_BYTES = 262144;
const PAGE_MARKER = '<div id="root"></div>';
const HEALTH_PATH = '/healthz';
const LOGIN_PATH = '/api/v1/client/auth/login';
const FORGED_TOKEN_MIN_LENGTH = 8;

// Keep byte-identical with the runner's exported fixed taxonomy; the runner
// re-validates every payload and any divergence fails closed.
const CORE_CHECK_IDS = [
  'frontend_origin_page',
  'backend_health_reachable',
  'maildir_ready_and_empty',
  'w1_w2_canonical_and_distinct',
  'identities_distinct_after_normalization',
  'invitation_pairs_present_and_distinct',
  'forged_token_not_reused',
  'owner_identity_fresh_unregistered',
  'unverified_login_refused',
];
const HOST_CHECK_IDS = [
  'pg_reachable',
  'redis_reachable',
  'alembic_head_current',
  'authority_ports_owned',
];

const TOOL_DIR = dirname(fileURLToPath(import.meta.url));

function readStdinText() {
  const chunks = [];
  let total = 0;
  const buffer = Buffer.alloc(65536);
  for (;;) {
    const read = readSync(0, buffer, 0, buffer.length, null);
    if (read <= 0) break;
    chunks.push(buffer.subarray(0, read));
    total += read;
    if (total > MAX_STDIN_BYTES) break;
  }
  return Buffer.concat(chunks, total).toString('utf8');
}

function emit(exitCode, payload) {
  writeSync(1, Buffer.from(JSON.stringify(payload) + '\n', 'utf8'));
  process.exit(exitCode);
}

function failClosed() {
  // No payload: the runner classifies a missing/invalid payload as
  // preflight_helper_no_response and VOIDs before authorize.
  process.exit(3);
}

function sha256Hex(data) {
  return createHash('sha256').update(data, 'utf8').digest('hex');
}

/** Read the canonical profile from THIS module's own location. */
function readCanonicalProfile() {
  const profilePath = join(TOOL_DIR, '..', 'inventory', 'browser-authority-profile.json');
  const doc = JSON.parse(readFileSync(profilePath, 'utf8'));
  if (
    doc === null ||
    typeof doc !== 'object' ||
    doc.schema !== 'j1h2c/browser-authority-profile/1' ||
    doc.fields === null ||
    typeof doc.fields !== 'object' ||
    typeof doc.owner_field !== 'string' ||
    !(doc.owner_field in doc.fields)
  ) {
    throw new Error('profile_shape');
  }
  const keys = Object.keys(doc.fields);
  if (keys.length === 0) throw new Error('profile_shape');
  for (const field of Object.values(doc.fields)) {
    if (
      field === null ||
      typeof field !== 'object' ||
      typeof field.env !== 'string' ||
      !/^J1H2C_[A-Z0-9_]+$/.test(field.env) ||
      field.required !== true ||
      typeof field.sensitive !== 'boolean'
    ) {
      throw new Error('profile_shape');
    }
  }
  return { fields: doc.fields, ownerField: doc.owner_field };
}

/** Native, module-private HTTP transport. Never fetch. */
function requestStatusAndMaybeBody(urlString, options) {
  return new Promise((resolve, reject) => {
    let target;
    try {
      target = new URL(urlString);
    } catch {
      reject(new Error('url_invalid'));
      return;
    }
    if (target.protocol !== 'http:' && target.protocol !== 'https:') {
      reject(new Error('url_invalid'));
      return;
    }
    const transport = target.protocol === 'https:' ? https : http;
    const request = transport.request(
      target,
      {
        method: options.method,
        headers: options.headers,
      },
      (response) => {
        const status = response.statusCode ?? 0;
        let body = '';
        response.setEncoding('utf8');
        response.on('data', (chunk) => {
          if (options.wantBody && body.length < 65536) body += chunk;
        });
        response.on('end', () => resolve({ status, body }));
        response.on('error', () => reject(new Error('response_error')));
      },
    );
    request.setTimeout(options.timeoutMs, () => {
      request.destroy(new Error('timeout'));
    });
    request.on('error', (error) => {
      reject(error && error.message === 'timeout' ? error : new Error('request_error'));
    });
    if (options.body !== undefined) request.write(options.body);
    request.end();
  });
}

async function requestJsonStatus(urlString, payloadObject, timeoutMs) {
  const { status } = await requestStatusAndMaybeBody(urlString, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(payloadObject),
    timeoutMs,
    wantBody: false,
  });
  return status;
}

function normalizeIdentity(value) {
  return String(value).trim().toLowerCase();
}

/** Run one check; any exception becomes a RED with a fixed category. */
async function runCheck(id, run) {
  try {
    const category = await run();
    return { id, ok: category === 'check_green', category: category ?? 'check_exception' };
  } catch {
    return { id, ok: false, category: 'check_exception' };
  }
}

async function checkFrontendPage(values, deadline) {
  const remaining = deadline - Date.now();
  if (remaining <= 0) return 'check_timeout';
  const { status, body } = await requestStatusAndMaybeBody(values.base_url, {
    method: 'GET',
    headers: { accept: 'text/html' },
    timeoutMs: remaining,
    wantBody: true,
  });
  if (status < 200 || status > 299) return 'frontend_origin_unreachable';
  if (!body.includes(PAGE_MARKER)) return 'frontend_page_marker_missing';
  return 'check_green';
}

async function checkBackendHealth(values, deadline) {
  const remaining = deadline - Date.now();
  if (remaining <= 0) return 'check_timeout';
  const target = new URL(HEALTH_PATH, values.api_base_url).toString();
  const { status } = await requestStatusAndMaybeBody(target, {
    method: 'GET',
    headers: { accept: 'application/json' },
    timeoutMs: remaining,
    wantBody: false,
  });
  if (status < 200 || status > 299) return 'backend_health_unreachable';
  return 'check_green';
}

function checkMaildir(values) {
  if (!existsSync(values.maildir_root)) return 'maildir_missing';
  let stats;
  try {
    stats = statSync(values.maildir_root);
  } catch {
    return 'maildir_missing';
  }
  if (!stats.isDirectory()) return 'maildir_not_directory';
  try {
    accessSync(values.maildir_root, fsConstants.R_OK | fsConstants.W_OK);
  } catch {
    return 'maildir_permission_denied';
  }
  let entries;
  try {
    entries = readdirSync(realpathSync(values.maildir_root));
  } catch {
    return 'maildir_permission_denied';
  }
  if (entries.length !== 0) return 'maildir_not_empty';
  return 'check_green';
}

function checkCanonicalCodes(values) {
  const w1 = values.w1_canonical_code;
  const w2 = values.w2_canonical_code;
  if (!/^[A-Z0-9]+$/.test(w1) || !/^[A-Z0-9]+$/.test(w2)) {
    return 'canonical_code_format_invalid';
  }
  if (w1 === w2) return 'w1_w2_not_distinct';
  return 'check_green';
}

function checkIdentities(values) {
  const owner = normalizeIdentity(values.owner);
  const unknown = normalizeIdentity(values.unknown_identity);
  const unverified = normalizeIdentity(values.unverified_identity);
  if (
    owner.length === 0 ||
    unknown.length === 0 ||
    unverified.length === 0 ||
    owner === unknown ||
    owner === unverified ||
    unknown === unverified
  ) {
    return 'identity_collision';
  }
  return 'check_green';
}

function checkInvitations(values) {
  const codeV = values.w1_verified_invitation_code;
  const phoneV = values.w1_verified_invitation_phone;
  const codeU = values.w1_unverified_invitation_code;
  const phoneU = values.w1_unverified_invitation_phone;
  if (
    codeV.length === 0 ||
    phoneV.length === 0 ||
    codeU.length === 0 ||
    phoneU.length === 0
  ) {
    return 'invitation_pair_incomplete';
  }
  const all = [codeV, phoneV, codeU, phoneU];
  if (new Set(all).size !== all.length) return 'invitation_collision';
  return 'check_green';
}

function checkForgedToken(values) {
  const forged = values.forged_reset_token;
  if (forged.trim().length < FORGED_TOKEN_MIN_LENGTH) return 'forged_token_missing_or_short';
  const others = Object.entries(values)
    .filter(([key]) => key !== 'forged_reset_token')
    .map(([, value]) => value);
  if (others.includes(forged)) return 'forged_token_reuse';
  return 'check_green';
}

/**
 * B1-R6-R5 lifecycle-compatible pre-run proof: the retailer identity must
 * be FRESH / not established BEFORE the harness beforeAll registers it.
 * A refused login (any non-200) proves freshness; a 200 login proves the
 * identity is already established and the harness registration lifecycle
 * could never run — RED (`owner_identity_already_established`).
 */
async function checkOwnerIdentityFresh(values, deadline) {
  const remaining = deadline - Date.now();
  if (remaining <= 0) return 'check_timeout';
  const status = await requestJsonStatus(
    new URL(LOGIN_PATH, values.api_base_url).toString(),
    {
      email: values.owner,
      password: values.owner_current_password,
      wholesaler_code: values.w1_canonical_code,
    },
    remaining,
  );
  if (status === 200) return 'owner_identity_already_established';
  return 'check_green';
}

async function checkUnverifiedLogin(values, deadline) {
  const remaining = deadline - Date.now();
  if (remaining <= 0) return 'check_timeout';
  const status = await requestJsonStatus(
    new URL(LOGIN_PATH, values.api_base_url).toString(),
    {
      email: values.unverified_identity,
      password: values.owner_current_password,
      wholesaler_code: values.w1_canonical_code,
    },
    remaining,
  );
  if (status === 200) return 'unverified_login_accepted';
  return 'check_green';
}

// ---------------------------------------------------------------------------
// Input parsing (strict)
// ---------------------------------------------------------------------------

let parsedInput = null;
let hostBlock = null;
try {
  const candidate = JSON.parse(readStdinText());
  const keys = Object.keys(candidate ?? {}).sort();
  const baseKeys = ['schema', 'timeout_ms', 'values'];
  const extendedKeys = ['host_preflight', 'schema', 'timeout_ms', 'values'];
  if (
    candidate !== null &&
    typeof candidate === 'object' &&
    !Array.isArray(candidate) &&
    (JSON.stringify(keys) === JSON.stringify(baseKeys) ||
      JSON.stringify(keys) === JSON.stringify(extendedKeys)) &&
    candidate.schema === INPUT_SCHEMA &&
    Number.isInteger(candidate.timeout_ms) &&
    candidate.timeout_ms > 0 &&
    candidate.timeout_ms <= 120000 &&
    candidate.values !== null &&
    typeof candidate.values === 'object' &&
    !Array.isArray(candidate.values)
  ) {
    parsedInput = candidate;
    if ('host_preflight' in candidate) {
      const host = candidate.host_preflight;
      const okShape =
        host !== null &&
        typeof host === 'object' &&
        !Array.isArray(host) &&
        host.provided_by === 'outer_authority_preflight' &&
        Array.isArray(host.checks);
      if (!okShape) failClosed();
      const seen = new Set();
      for (const check of host.checks) {
        if (
          check === null ||
          typeof check !== 'object' ||
          !HOST_CHECK_IDS.includes(check.id) ||
          typeof check.ok !== 'boolean' ||
          typeof check.category !== 'string' ||
          check.category.length === 0 ||
          seen.has(check.id)
        ) {
          failClosed();
        }
        seen.add(check.id);
      }
      hostBlock = host.checks;
    }
  }
} catch {
  failClosed();
}
if (parsedInput === null) failClosed();

// Values must cover EXACTLY the canonical profile field keys.
let values;
try {
  const { fields, ownerField } = readCanonicalProfile();
  const expectedKeys = Object.keys(fields).sort();
  const actualKeys = Object.keys(parsedInput.values).sort();
  if (
    JSON.stringify(expectedKeys) !== JSON.stringify(actualKeys) ||
    typeof parsedInput.values[ownerField] !== 'string'
  ) {
    failClosed();
  }
  for (const value of Object.values(parsedInput.values)) {
    if (typeof value !== 'string' || value.length === 0) failClosed();
  }
  values = parsedInput.values;
} catch {
  failClosed();
}

// ---------------------------------------------------------------------------
// Checks (fixed order; core checks always run, host results are folded in)
// ---------------------------------------------------------------------------

const deadline = Date.now() + parsedInput.timeout_ms;
const checks = [];
checks.push(await runCheck('frontend_origin_page', () => checkFrontendPage(values, deadline)));
checks.push(await runCheck('backend_health_reachable', () => checkBackendHealth(values, deadline)));
checks.push(await runCheck('maildir_ready_and_empty', async () => checkMaildir(values)));
checks.push(await runCheck('w1_w2_canonical_and_distinct', async () => checkCanonicalCodes(values)));
checks.push(
  await runCheck('identities_distinct_after_normalization', async () => checkIdentities(values)),
);
checks.push(
  await runCheck(
    'invitation_pairs_present_and_distinct',
    async () => checkInvitations(values),
  ),
);
checks.push(await runCheck('forged_token_not_reused', async () => checkForgedToken(values)));
checks.push(
  await runCheck('owner_identity_fresh_unregistered', () => checkOwnerIdentityFresh(values, deadline)),
);
checks.push(
  await runCheck('unverified_login_refused', () => checkUnverifiedLogin(values, deadline)),
);
let hostChecksPresent = 0;
if (hostBlock !== null) {
  hostChecksPresent = hostBlock.length;
  for (const id of HOST_CHECK_IDS) {
    const provided = hostBlock.find((check) => check.id === id);
    if (provided) {
      checks.push({ id, ok: provided.ok, category: provided.ok ? 'check_green' : provided.category });
    }
  }
}
const red = checks.filter((check) => check.ok === false).length;
emit(0, {
  schema: RESULT_SCHEMA,
  ok: red === 0,
  checks,
  counts: { total: checks.length, red, host_checks_present: hostChecksPresent },
});
