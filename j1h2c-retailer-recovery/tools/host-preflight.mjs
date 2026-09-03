#!/usr/bin/env node
/**
 * Version-controlled host preflight (B1-R6-R5-R1) — the authority host
 * gate, owned and invoked by the authority RUNNER itself.
 *
 * This module replaces every ad hoc, unversioned host script: another
 * runtime attempt MUST run THIS file, never another inline script. In a
 * DIRECT authority run the runner derives THIS module's path from its own
 * location, proves the working-tree bytes equal the HEAD committed blob,
 * spawns it as a fresh node child (fixed argv, shell:false, sanitized
 * environment, private stdin) and folds the result block
 * (`provided_by: 'outer_authority_preflight'` + `checks`) into the
 * preflight helper verdict over the frozen `host_preflight` interface.
 * No caller, entrypoint or environment can supply host results. A DIRECT
 * authority run requires EXACTLY the four configured checks:
 * `host_checks_present = 0`, a missing configuration or a module that was
 * never invoked VOIDs the plane BEFORE authorize — spawn = 0. Any RED
 * check VOIDs identically (preflight_red -> STOPPED, starts = 0).
 * Library / non-authority fixtures stay transparent (checks = []) and can
 * never mint authority seal/evidence.
 *
 * Fixed check ids (byte-identical with the runner's
 * PREFLIGHT_HOST_CHECK_IDS; the helper refuses any other id):
 *   pg_reachable, redis_reachable, alembic_head_current,
 *   authority_ports_owned
 *
 * Fixed-categories-only output (single stdout line; never a URL, host,
 * port, password, token, code or raw command output):
 *   { schema, ok, configured, provided_by,
 *     checks: [{ id, ok, category }...], counts }
 *
 * Defect closures carried from the retired ad hoc script:
 *   - PostgreSQL booleans are parsed SEMANTICALLY — every display format
 *     ('t'/'f', 'true'/'false', 'on'/'off', 'yes'/'no', '1'/'0', any
 *     letter case, surrounding space) normalizes to the same truth; an
 *     unparsable representation is a RED, never a silent falsy.
 *   - Invitation availability is checked with a PARAMETER-SAFE psql
 *     probe: the relation/column SQL text is fixed, values travel as psql
 *     variables in separate argv elements ( :'name' quoting), and the
 *     module REFUSES to spawn when a value would end up inside the SQL
 *     text. There is no shell anywhere (shell: false).
 *   - Authority port ownership is proven WITHOUT trusting the mutable PID
 *     file alone: the PID file must carry a positive integer, the recorded
 *     process must be ALIVE in the process table, and its command line
 *     must carry the expected ownership token. A truncated, stale or
 *     foreign-owned PID file is a RED.
 *
 * Runtime-truth contract (B1-R6-R5-R2 — closes the confirmed causes of the
 * R5-R1 candidate's non-executable probes):
 *   - psql SQL reaches the psql PREPROCESSOR through stdin (`psql -f -`,
 *     SQL on the child's stdin): a `-c` argument can never process
 *     :'variable' interpolation, so no :'placeholder' ever travels in -c;
 *   - the connection target is EXPLICITLY bound — J1H2C_HOST_PG* become
 *     -h/-p/-d/-U argv elements; every ambient PG* variable (any letter
 *     case) is stripped from the child environment except the task-bound
 *     PGPASSWORD;
 *   - Alembic proves EXACTLY ONE heads revision and EXACTLY ONE current
 *     revision, equal as FULL revision IDs (real IDs contain underscores;
 *     whole-token equality, never a prefix match);
 *   - Redis REALLY exchanges PING -> +PONG, SELECT 15 -> +OK and
 *     DBSIZE -> :0 (task DB 15 proven EMPTY) and the sentinel on the SAME
 *     host at 26379 must be UNREACHABLE (`sentinel_reachable` otherwise).
 *
 * Configuration contract (host-level; the outer layer's environment):
 *   J1H2C_HOST_PREFLIGHT = '1'  — the configuration marker. When it is not
 *     exactly '1', the module emits the TRANSPARENT result
 *     (checks = [], counts.total = 0, ok = true): an unconfigured host is
 *     not a RED, and the runner-side report stays host_checks_present = 0.
 *   When configured, ALL descriptors below are required; a missing one is
 *     a RED of the owning check (never a silent skip):
 *     J1H2C_HOST_PGHOST, J1H2C_HOST_PGPORT, J1H2C_HOST_PGDATABASE,
 *     J1H2C_HOST_PGUSER, J1H2C_HOST_PGROLE, PGPASSWORD,
 *     J1H2C_HOST_REDIS_HOST, J1H2C_HOST_REDIS_PORT,
 *     J1H2C_HOST_BACKEND_DIR, J1H2C_HOST_PID_FILE, J1H2C_HOST_SERVICE_TOKEN
 *
 * Input (exact schema, private stdin):
 *   { schema, timeout_ms, values }
 * `values` keys must equal the canonical profile field keys exactly (the
 * profile is re-read from THIS module's own location); only the invitation
 * code/phone values are consumed, solely as bound probe variables.
 *
 * Dependency injection: the exported check functions (checkRoleCapabilities,
 * checkInvitationAvailability, checkPidOwnership, runHostPreflight) accept
 * injected runners for testing; the default implementations (spawnPsql,
 * redis PING, alembic, ps) are assembled in main() from the descriptor
 * environment and never run during contract tests — no PG, Redis, Alembic
 * or browser runtime is required to prove this module's contract.
 */

import { readFileSync, readSync, realpathSync, writeSync } from 'node:fs';
import net from 'node:net';
import childProcess from 'node:child_process';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const INPUT_SCHEMA = 'j1h2c/host-preflight-input/1';
const RESULT_SCHEMA = 'j1h2c/host-preflight-result/1';
const MAX_STDIN_BYTES = 262144;
const CONFIG_MARKER = '1';
const REDIS_PING_TIMEOUT_MS = 5000;
const SPAWN_BUDGET_MS = 20000;

// Byte-identical with the runner's PREFLIGHT_HOST_CHECK_IDS; the helper
// refuses any other id, so this list is a frozen interface.
const HOST_CHECK_IDS = [
  'pg_reachable',
  'redis_reachable',
  'alembic_head_current',
  'authority_ports_owned',
];

const TOOL_DIR = dirname(fileURLToPath(import.meta.url));

const PG_DESCRIPTOR_ENV = [
  'J1H2C_HOST_PGHOST',
  'J1H2C_HOST_PGPORT',
  'J1H2C_HOST_PGDATABASE',
  'J1H2C_HOST_PGUSER',
  'J1H2C_HOST_PGROLE',
  'PGPASSWORD',
];
const REDIS_DESCRIPTOR_ENV = ['J1H2C_HOST_REDIS_HOST', 'J1H2C_HOST_REDIS_PORT'];
const ALEMBIC_DESCRIPTOR_ENV = ['J1H2C_HOST_BACKEND_DIR'];
const PID_DESCRIPTOR_ENV = ['J1H2C_HOST_PID_FILE', 'J1H2C_HOST_SERVICE_TOKEN'];

// Least-privilege runtime role policy: the authority role MUST be able to
// log in (the backend connects with it) and MUST NOT carry any
// administrative capability.
const ROLE_MUST_BE_TRUE = ['rolcanlogin'];
const ROLE_MUST_BE_FALSE = ['rolsuper', 'rolcreaterole', 'rolcreatedb', 'rolreplication'];

// Parameter-safe invitation availability probe: fixed relation/column SQL
// text; values travel OUT OF BAND as psql variables (separate argv
// elements, :'name' quoting). The relation/column names are the backend's
// frozen public.invitations schema (migration 002).
const INVITATION_PROBE_SQL = [
  'SELECT count(*) AS n FROM public.invitations',
  "WHERE code = :'invitation_code'",
  "AND retailer_phone = :'invitation_phone'",
  "AND status = 'active'",
  'AND used_at IS NULL',
  'AND is_deleted = false',
].join(' ');

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
  // No payload: the outer layer classifies a missing/invalid payload as a
  // host preflight failure and must not fold anything into the verdict.
  process.exit(3);
}

/** Read the canonical profile's field keys from THIS module's own location. */
function readCanonicalProfileFieldKeys() {
  const profilePath = join(TOOL_DIR, '..', 'inventory', 'browser-authority-profile.json');
  const doc = JSON.parse(readFileSync(profilePath, 'utf8'));
  if (
    doc === null ||
    typeof doc !== 'object' ||
    doc.schema !== 'j1h2c/browser-authority-profile/1' ||
    doc.fields === null ||
    typeof doc.fields !== 'object' ||
    Array.isArray(doc.fields)
  ) {
    throw new Error('profile_shape');
  }
  const keys = [];
  for (const [key, field] of Object.entries(doc.fields)) {
    if (
      field === null ||
      typeof field !== 'object' ||
      typeof field.env !== 'string' ||
      !/^J1H2C_[A-Z0-9_]+$/.test(field.env) ||
      field.required !== true
    ) {
      throw new Error('profile_shape');
    }
    keys.push(key);
  }
  return keys;
}

/**
 * SEMANTIC PostgreSQL boolean normalization. Every server/client display
 * format of a boolean collapses to exactly true or exactly false; anything
 * else is null (the caller must RED on null — never treat it as falsy).
 */
export function parsePgBoolean(raw) {
  if (raw === null || raw === undefined) return null;
  if (typeof raw === 'boolean') return raw;
  if (typeof raw === 'number') {
    if (raw === 1) return true;
    if (raw === 0) return false;
    return null;
  }
  if (typeof raw !== 'string') return null;
  const normalized = raw.trim().toLowerCase();
  if (['t', 'true', 'on', 'yes', '1'].includes(normalized)) return true;
  if (['f', 'false', 'off', 'no', '0'].includes(normalized)) return false;
  return null;
}

/**
 * Build the parameter-safe invitation availability probe: fixed SQL text
 * with :'name' placeholders and the values strictly OUT OF BAND.
 */
export function buildInvitationProbe(invitationCode, invitationPhone) {
  return {
    text: INVITATION_PROBE_SQL,
    vars: { invitation_code: String(invitationCode), invitation_phone: String(invitationPhone) },
  };
}

/** True when the probe would smuggle a raw value into the SQL text. */
export function invitationProbeIsParameterSafe(probe) {
  if (probe === null || typeof probe !== 'object') return false;
  if (typeof probe.text !== 'string') return false;
  for (const value of Object.values(probe.vars ?? {})) {
    if (typeof value === 'string' && value.length > 0 && probe.text.includes(value)) {
      return false;
    }
  }
  return probe.text.includes(":'invitation_code'") && probe.text.includes(":'invitation_phone'");
}

function normalizedResult(outcome) {
  if (outcome === null || typeof outcome !== 'object') {
    return { ok: false, category: 'host_check_exception' };
  }
  return {
    ok: outcome.ok === true,
    category:
      typeof outcome.category === 'string' && outcome.category.length > 0
        ? outcome.category
        : 'host_check_exception',
  };
}

/**
 * Role capabilities: read SEMANTICALLY (every boolean display format), and
 * fail closed on any wrong or unparsable capability. `psql({sql, vars})`
 * is the injected parameter-safe runner returning {ok, rows}.
 */
export function checkRoleCapabilities(psql, authorityRole) {
  const roleSql =
    'SELECT rolcanlogin, rolsuper, rolcreaterole, rolcreatedb, rolreplication ' +
    "FROM pg_roles WHERE rolname = :'authority_role'";
  const probe = psql({ sql: roleSql, vars: { authority_role: String(authorityRole) } });
  if (!probe || probe.ok !== true) return { ok: false, category: 'pg_role_unresolvable' };
  const columns = String(probe.rows ?? '').trim().split('|');
  if (columns.length !== ROLE_MUST_BE_TRUE.length + ROLE_MUST_BE_FALSE.length) {
    return { ok: false, category: 'pg_role_capabilities_invalid' };
  }
  const capabilities = {};
  for (const [index, name] of [...ROLE_MUST_BE_TRUE, ...ROLE_MUST_BE_FALSE].entries()) {
    const parsed = parsePgBoolean(columns[index]);
    if (parsed === null) return { ok: false, category: 'pg_role_capabilities_invalid' };
    capabilities[name] = parsed;
  }
  for (const name of ROLE_MUST_BE_TRUE) {
    if (capabilities[name] !== true) return { ok: false, category: 'pg_role_capabilities_invalid' };
  }
  for (const name of ROLE_MUST_BE_FALSE) {
    if (capabilities[name] !== false) return { ok: false, category: 'pg_role_capabilities_invalid' };
  }
  return { ok: true, category: 'check_green' };
}

/**
 * Invitation availability: one parameter-safe probe per invitation pair; a
 * pair whose values would leak into the SQL text, whose runner fails, or
 * with no unconsumed active invitation is a RED.
 */
export function checkInvitationAvailability(psql, values) {
  const pairs = [
    [values.w1_verified_invitation_code, values.w1_verified_invitation_phone],
    [values.w1_unverified_invitation_code, values.w1_unverified_invitation_phone],
  ];
  for (const [code, phone] of pairs) {
    const probe = buildInvitationProbe(code, phone);
    if (!invitationProbeIsParameterSafe(probe)) {
      return { ok: false, category: 'pg_invitation_parameterization_invalid' };
    }
    const found = psql({ sql: probe.text, vars: probe.vars });
    if (!found || found.ok !== true) {
      return { ok: false, category: 'pg_invitation_parameterization_invalid' };
    }
    const count = Number.parseInt(String(found.rows ?? '').trim(), 10);
    if (!Number.isInteger(count) || count < 1) {
      return { ok: false, category: 'pg_invitation_missing' };
    }
  }
  return { ok: true, category: 'check_green' };
}

/**
 * Authority port ownership WITHOUT trusting the mutable PID file alone:
 * the record must be a full positive integer, the recorded process must be
 * ALIVE in the process table, and its command line must carry the expected
 * ownership token.
 */
export function checkPidOwnership({ readPidFile, processEvidence, ownershipToken }) {
  const record = readPidFile();
  if (!record || record.ok !== true) {
    return {
      ok: false,
      category:
        record && typeof record.category === 'string' ? record.category : 'authority_ports_pid_truncated',
    };
  }
  const evidence = processEvidence(record.pid);
  if (evidence === null || evidence === undefined) {
    return { ok: false, category: 'authority_ports_pid_stale' };
  }
  const token = ownershipToken();
  if (typeof token !== 'string' || token.length === 0 || !String(evidence.args).includes(token)) {
    return { ok: false, category: 'authority_ports_owner_mismatch' };
  }
  return { ok: true, category: 'check_green' };
}

// ---------------------------------------------------------------------------
// Fixed four-check execution (configured mode) + transparent mode.
// ---------------------------------------------------------------------------

/**
 * Run the host preflight. `deps` may carry test doubles; every missing
 * implementation in configured mode is a RED (`host_check_missing`) — a
 * removed host check can never pass silently. The result carries the
 * `configured` flag so the authority runner can distinguish a transparent
 * (unconfigured) block — which VOIDs a DIRECT authority run — from a
 * configured four-check block.
 */
export async function runHostPreflight(deps = {}, options = {}) {
  const impl = { ...deps };
  const configured = options.configured ?? process.env.J1H2C_HOST_PREFLIGHT === CONFIG_MARKER;
  const values = options.values ?? null;
  if (!configured) {
    // Transparent: an unconfigured host produces ZERO checks. Library /
    // non-authority fixtures may stay transparent, but a DIRECT authority
    // run treats this as host_preflight_not_configured and VOIDs before
    // authorize.
    return {
      schema: RESULT_SCHEMA,
      ok: true,
      configured: false,
      provided_by: 'outer_authority_preflight',
      checks: [],
      counts: { total: 0, red: 0 },
    };
  }
  if (values === null || typeof values !== 'object' || Array.isArray(values)) {
    failClosed();
  }
  const checks = [];
  checks.push({ id: 'pg_reachable', ...(await safeCheck(impl.pgProbe, values)) });
  checks.push({ id: 'redis_reachable', ...(await safeCheck(impl.redisProbe, values)) });
  checks.push({ id: 'alembic_head_current', ...(await safeCheck(impl.alembicRevisions, values)) });
  checks.push({ id: 'authority_ports_owned', ...(await safeCheck(impl.portsOwnership, values)) });

  // Fail-closed guard: the fixed taxonomy must be complete. A removed or
  // renamed check is a hard module failure, never an absent id.
  const ids = checks.map((check) => check.id);
  for (const id of HOST_CHECK_IDS) {
    if (!ids.includes(id)) failClosed();
  }
  const red = checks.filter((check) => check.ok === false).length;
  return {
    schema: RESULT_SCHEMA,
    ok: red === 0,
    configured: true,
    provided_by: 'outer_authority_preflight',
    checks,
    counts: { total: checks.length, red },
  };
}

async function safeCheck(impl, values) {
  if (typeof impl !== 'function') {
    // A removed host check implementation is a RED, never a silent skip.
    return { ok: false, category: 'host_check_missing' };
  }
  try {
    return normalizedResult(await impl(values));
  } catch {
    return { ok: false, category: 'host_check_exception' };
  }
}

// ---------------------------------------------------------------------------
// Default (production) dependency implementations — Lubuntu host contract.
// Every subprocess is an argv array with shell:false; raw outputs never
// reach the result payload.
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// B1-R6-R5-R2 Alembic runtime truth: real alembic revision IDs contain
// underscores (e.g. 002_phase_b2_invitation_binding) — a hex-only validator
// rejected every REAL head. The verdict requires EXACTLY ONE heads revision,
// EXACTLY ONE current revision, and FULL revision-ID equality (whole token,
// never a prefix match).
// ---------------------------------------------------------------------------

const ALEMBIC_REVISION_CHARSET = /^[A-Za-z0-9_]+$/;

/** First token of every non-empty line (the complete revision ID token). */
export function alembicTokens(stdoutText) {
  return String(stdoutText ?? '')
    .split('\n')
    .map((line) => line.trim().split(/\s+/)[0] ?? '')
    .filter((token) => token.length > 0);
}

export function alembicRevisionsVerdict(headsStdout, currentStdout) {
  const heads = alembicTokens(headsStdout);
  if (heads.length > 1) return { ok: false, category: 'alembic_multi_head' };
  if (heads.length !== 1 || !ALEMBIC_REVISION_CHARSET.test(heads[0])) {
    return { ok: false, category: 'alembic_unresolvable' };
  }
  const currents = alembicTokens(currentStdout);
  if (currents.length !== 1 || !ALEMBIC_REVISION_CHARSET.test(currents[0])) {
    return { ok: false, category: 'alembic_unresolvable' };
  }
  if (heads[0] !== currents[0]) return { ok: false, category: 'alembic_head_diverged' };
  return { ok: true, category: 'check_green' };
}

// ---------------------------------------------------------------------------
// B1-R6-R5-R2 Redis runtime truth: a bare PING proves nothing about the
// task database. The session must REALLY exchange PING -> +PONG,
// SELECT 15 -> +OK and DBSIZE -> :0 (task DB 15 proven EMPTY), and the
// sentinel on the SAME host at 26379 must be proven UNREACHABLE (a running
// sentinel would let the gate drift to another node mid-run).
// ---------------------------------------------------------------------------

export function redisSessionVerdict(pingReply, selectReply, dbsizeReply) {
  const ping = String(pingReply ?? '').trim();
  const select = String(selectReply ?? '').trim();
  const dbsize = String(dbsizeReply ?? '').trim();
  if (ping !== '+PONG') return { ok: false, category: 'redis_unreachable' };
  if (select !== '+OK') return { ok: false, category: 'redis_select_failed' };
  if (dbsize === ':0') return { ok: true, category: 'check_green' };
  if (/^:\d+$/.test(dbsize)) return { ok: false, category: 'redis_db15_not_empty' };
  return { ok: false, category: 'redis_protocol_invalid' };
}

export function sentinelVerdict(sentinelReachable) {
  return sentinelReachable === true
    ? { ok: false, category: 'sentinel_reachable' }
    : { ok: true, category: 'check_green' };
}

/** REAL redis conversation over one socket: PING, SELECT 15, DBSIZE. */
export function redisConversation(host, port) {
  return new Promise((resolve) => {
    const socket = net.connect({ host, port });
    const replies = [];
    const commands = ['PING', 'SELECT 15', 'DBSIZE'];
    let sent = 0;
    let received = 0;
    let buffer = '';
    let settled = false;
    const finish = (verdict) => {
      if (settled) return;
      settled = true;
      socket.destroy();
      resolve({ ...verdict, replies });
    };
    socket.setTimeout(REDIS_PING_TIMEOUT_MS, () => finish({ ok: false, category: 'redis_unreachable' }));
    socket.on('error', () => finish({ ok: false, category: 'redis_unreachable' }));
    socket.on('connect', () => socket.write(`${commands[sent++]}\r\n`));
    socket.on('data', (chunk) => {
      buffer += String(chunk);
      let index;
      while ((index = buffer.indexOf('\n')) >= 0) {
        const line = buffer.slice(0, index).replace(/\r$/, '');
        buffer = buffer.slice(index + 1);
        if (line.length === 0) continue;
        replies.push(line);
        received += 1;
        if (received < commands.length) {
          socket.write(`${commands[sent++]}\r\n`);
        } else {
          finish(redisSessionVerdict(replies[0], replies[1], replies[2]));
          return;
        }
      }
    });
  });
}

/** REAL sentinel reachability probe on the SAME host at fixed port 26379. */
export function sentinelProbe(host) {
  return new Promise((resolve) => {
    const socket = net.connect({ host, port: 26379 });
    let settled = false;
    const done = (reachable) => {
      if (settled) return;
      settled = true;
      socket.destroy();
      resolve(reachable);
    };
    socket.setTimeout(REDIS_PING_TIMEOUT_MS, () => done(true));
    socket.on('error', () => done(false));
    socket.on('connect', () => done(true));
  });
}

function descriptorMissing(names) {
  return names.some((name) => {
    const value = process.env[name];
    return value === undefined || value === null || value.length === 0;
  });
}

// ---------------------------------------------------------------------------
// B1-R6-R5-R2 psql invocation contract (RUNTIME TRUTH):
//   - the SQL text travels through psql PREPROCESSING via stdin
//     (`psql -f -` with the text on the child's stdin) — a `-c` argument
//     can never carry `:'variable'` placeholders, because `-c` bypasses
//     the psql preprocessor entirely;
//   - the connection target is EXPLICITLY bound: J1H2C_HOST_PG* become
//     -h/-p/-d/-U argv elements, so ambient PGHOST/PGDATABASE/... can
//     never redirect the probe;
//   - the child environment strips every ambient PG* variable (any letter
//     case) and keeps ONLY the task-bound PGPASSWORD;
//   - variables travel as -v name=value argv elements, values NEVER enter
//     the SQL text (invitationProbeIsParameterSafe guards this).
// ---------------------------------------------------------------------------

/** Strip every ambient PG* variable (any letter case) except PGPASSWORD. */
export function stripAmbientPgEnv(baseEnv) {
  const env = {};
  for (const [key, value] of Object.entries(baseEnv ?? {})) {
    if (key !== 'PGPASSWORD' && /^pg/i.test(key)) continue;
    env[key] = value;
  }
  return env;
}

/**
 * Build the full psql invocation: explicit -h/-p/-d/-U from the task
 * descriptors, -v variables out of band, and the SQL text on STDIN
 * (`-f -`) so psql preprocessing resolves the :'name' placeholders.
 */
export function buildPsqlInvocation(descriptors, sql, vars = {}) {
  const argv = [
    process.env.J1H2C_HOST_PSQL_BIN ?? 'psql',
    '-X',
    '-A',
    '-t',
    '-v',
    'ON_ERROR_STOP=1',
    '-h',
    String(descriptors.host),
    '-p',
    String(descriptors.port),
    '-d',
    String(descriptors.database),
    '-U',
    String(descriptors.user),
  ];
  for (const [name, value] of Object.entries(vars ?? {})) {
    argv.push('-v', `${name}=${value}`);
  }
  argv.push('-f', '-');
  return {
    argv,
    input: `${sql}\n`,
    env: stripAmbientPgEnv(process.env),
  };
}

/** The real psql transport: argv array, shell:false, SQL on stdin. */
export function psqlTransport(invocation) {
  const result = childProcess.spawnSync(invocation.argv[0], invocation.argv.slice(1), {
    input: invocation.input,
    env: invocation.env,
    stdio: ['pipe', 'pipe', 'pipe'],
    timeout: SPAWN_BUDGET_MS,
    encoding: 'utf8',
    windowsHide: true,
    shell: false,
  });
  if (result.error || result.status !== 0) {
    return { ok: false, rows: null };
  }
  return { ok: true, rows: String(result.stdout ?? '') };
}

function spawnPsql({ sql, vars }) {
  return psqlTransport(
    buildPsqlInvocation(
      {
        host: process.env.J1H2C_HOST_PGHOST,
        port: process.env.J1H2C_HOST_PGPORT,
        database: process.env.J1H2C_HOST_PGDATABASE,
        user: process.env.J1H2C_HOST_PGUSER,
      },
      sql,
      vars,
    ),
  );
}

export function defaultHostDeps() {
  return {
    async pgProbe(values) {
      if (descriptorMissing(PG_DESCRIPTOR_ENV)) return { ok: false, category: 'pg_descriptor_missing' };
      const reach = spawnPsql({ sql: 'SELECT 1', vars: {} });
      if (!reach.ok) return { ok: false, category: 'pg_unreachable' };
      const role = await checkRoleCapabilities(spawnPsql, process.env.J1H2C_HOST_PGROLE);
      if (!role.ok) return role;
      return checkInvitationAvailability(spawnPsql, values);
    },

    async redisProbe() {
      if (descriptorMissing(REDIS_DESCRIPTOR_ENV)) {
        return { ok: false, category: 'redis_descriptor_missing' };
      }
      const port = Number.parseInt(process.env.J1H2C_HOST_REDIS_PORT, 10);
      if (!Number.isInteger(port) || port <= 0 || port > 65535) {
        return { ok: false, category: 'redis_descriptor_missing' };
      }
      const session = await redisConversation(process.env.J1H2C_HOST_REDIS_HOST, port);
      if (!session.ok) return { ok: session.ok, category: session.category };
      const sentinel = await sentinelProbe(process.env.J1H2C_HOST_REDIS_HOST);
      return sentinelVerdict(sentinel);
    },

    alembicRevisions() {
      if (descriptorMissing(ALEMBIC_DESCRIPTOR_ENV)) {
        return { ok: false, category: 'alembic_descriptor_missing' };
      }
      const run = (args) =>
        childProcess.spawnSync('alembic', args, {
          cwd: process.env.J1H2C_HOST_BACKEND_DIR,
          stdio: ['ignore', 'pipe', 'ignore'],
          timeout: SPAWN_BUDGET_MS,
          encoding: 'utf8',
          windowsHide: true,
          shell: false,
        });
      const heads = run(['heads']);
      const current = run(['current']);
      if (heads.error || heads.status !== 0 || current.error || current.status !== 0) {
        return { ok: false, category: 'alembic_unresolvable' };
      }
      return alembicRevisionsVerdict(String(heads.stdout ?? ''), String(current.stdout ?? ''));
    },

    async portsOwnership() {
      if (descriptorMissing(PID_DESCRIPTOR_ENV)) {
        return { ok: false, category: 'authority_ports_descriptor_missing' };
      }
      return checkPidOwnership({
        readPidFile() {
          let text = '';
          try {
            text = readFileSync(process.env.J1H2C_HOST_PID_FILE, 'utf8');
          } catch {
            return { ok: false, category: 'authority_ports_pid_truncated' };
          }
          const pid = Number.parseInt(text.trim(), 10);
          // The retired ad hoc script trusted a truncated PID file; a
          // truncated, non-numeric or non-positive record is a RED, never a
          // guessed PID.
          if (!Number.isInteger(pid) || pid <= 0 || `${pid}` !== text.trim()) {
            return { ok: false, category: 'authority_ports_pid_truncated' };
          }
          return { ok: true, pid };
        },
        processEvidence(pid) {
          // Process-table cross-proof (POSIX): the PID file alone is
          // mutable and never trusted by itself — the recorded process must
          // be alive here AND its command line must carry the token.
          const result = childProcess.spawnSync('ps', ['-p', String(pid), '-ww', '-o', 'args='], {
            stdio: ['ignore', 'pipe', 'ignore'],
            timeout: SPAWN_BUDGET_MS,
            encoding: 'utf8',
            windowsHide: true,
            shell: false,
          });
          if (result.error || result.status !== 0) return null;
          const args = String(result.stdout ?? '').trim();
          return args.length > 0 ? { args } : null;
        },
        ownershipToken: () => process.env.J1H2C_HOST_SERVICE_TOKEN ?? '',
      });
    },
  };
}

// ---------------------------------------------------------------------------
// Input parsing (strict) — same discipline as the preflight helper.
// ---------------------------------------------------------------------------

async function main() {
  let input = null;
  try {
    const candidate = JSON.parse(readStdinText());
    if (
      candidate !== null &&
      typeof candidate === 'object' &&
      !Array.isArray(candidate) &&
      JSON.stringify(Object.keys(candidate).sort()) ===
        JSON.stringify(['schema', 'timeout_ms', 'values']) &&
      candidate.schema === INPUT_SCHEMA &&
      Number.isInteger(candidate.timeout_ms) &&
      candidate.timeout_ms > 0 &&
      candidate.timeout_ms <= 120000 &&
      candidate.values !== null &&
      typeof candidate.values === 'object' &&
      !Array.isArray(candidate.values)
    ) {
      input = candidate;
    }
  } catch {
    failClosed();
  }
  if (input === null) failClosed();

  // Values must cover EXACTLY the canonical profile field keys (the same
  // deep-frozen values shape the preflight helper and child receive);
  // values are consumed solely as bound probe variables and never emitted.
  try {
    const expectedKeys = readCanonicalProfileFieldKeys().sort();
    const actualKeys = Object.keys(input.values).sort();
    if (JSON.stringify(expectedKeys) !== JSON.stringify(actualKeys)) failClosed();
    for (const value of Object.values(input.values)) {
      if (typeof value !== 'string' || value.length === 0) failClosed();
    }
  } catch {
    failClosed();
  }

  const result = await runHostPreflight(defaultHostDeps(), {
    configured: process.env.J1H2C_HOST_PREFLIGHT === CONFIG_MARKER,
    values: input.values,
  });
  const serialized = JSON.stringify(result);
  for (const value of Object.values(input.values)) {
    if (value.length > 0 && serialized.includes(value)) failClosed();
  }
  emit(0, result);
}

function isDirectEntrypoint() {
  try {
    if (process.argv.length !== 2 || typeof process.argv[1] !== 'string' || process.argv[1].length === 0) {
      return false;
    }
    return realpathSync(process.argv[1]).toLowerCase() === realpathSync(fileURLToPath(import.meta.url)).toLowerCase();
  } catch {
    return false;
  }
}

if (isDirectEntrypoint()) {
  await main();
}
