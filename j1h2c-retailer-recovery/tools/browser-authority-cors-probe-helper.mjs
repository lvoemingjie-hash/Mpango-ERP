#!/usr/bin/env node
/**
 * B1-R6-R2 process-isolated CORS probe helper.
 *
 * Executed by a FRESH `node` child (fixed process.execPath, argv array,
 * sanitized environment: NODE_* and GIT_* stripped) launched by
 * tools/browser-authority-runner.mjs. It exists for the process-level
 * authority trust boundary: whatever a hostile launcher mutates inside ITS
 * OWN process — globalThis.fetch, the node:http/node:https request
 * bindings, syncBuiltinESMExports — cannot reach this pristine process,
 * where the builtins load untouched and the real network request really
 * happens.
 *
 * I/O contract:
 *   stdin  : JSON { origin, target, timeoutMs }   (private; nothing enters
 *            argv, logs or evidence)
 *   stdout : JSON { ok, category, status_2xx, allow_origin_present,
 *                   allow_origin_exact }            (exit 0)
 *   crash / non-JSON / no output : parent fails closed with
 *            cors_probe_no_response
 *
 * Criteria (identical to the control plane's): pass iff the OPTIONS response
 * is 2xx AND Access-Control-Allow-Origin is EXACTLY the requested Origin.
 * No response body is ever read.
 */

import { readSync, writeSync } from 'node:fs';
import http from 'node:http';
import https from 'node:https';

const CORS_PREFLIGHT_PATH = '/client/auth/forgot-password';
const CORS_PROBE_RESULT_SCHEMA = 'j1h2c/cors-probe-result/1';
const FALLBACK_TIMEOUT_MS = 10000;
const MAX_STDIN_BYTES = 1048576;

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

const request = JSON.parse(readStdinText());
const timeoutMs =
  typeof request.timeoutMs === 'number' && request.timeoutMs > 0
    ? request.timeoutMs
    : FALLBACK_TIMEOUT_MS;
const origin = String(request.origin);
const target = String(request.target);
const transport = target.startsWith('https:') ? https : http;

let settled = false;
const finish = (payload) => {
  if (settled) return;
  settled = true;
  // Synchronous stdout: the verdict must survive process.exit(0).
  writeSync(1, Buffer.from(JSON.stringify({ schema: CORS_PROBE_RESULT_SCHEMA, ...payload }) + '\n', 'utf8'));
  process.exit(0);
};

const timer = setTimeout(() => {
  finish({
    ok: false,
    category: 'cors_probe_timeout',
    status_2xx: false,
    allow_origin_present: false,
    allow_origin_exact: false,
  });
}, timeoutMs);

const req = transport.request(
  target,
  {
    method: 'OPTIONS',
    headers: {
      Origin: origin,
      'Access-Control-Request-Method': 'POST',
      'Access-Control-Request-Headers': 'content-type',
      Connection: 'close',
    },
  },
  (res) => {
    res.resume(); // drain; the body is never read
    res.on('end', () => {
      clearTimeout(timer);
      const status2xx = res.statusCode >= 200 && res.statusCode < 300;
      const allowOrigin = res.headers['access-control-allow-origin'] ?? null;
      const allowOriginExact = allowOrigin !== null && allowOrigin === origin;
      finish({
        ok: status2xx && allowOriginExact,
        category: status2xx && allowOriginExact ? 'cors_probe_passed' : status2xx ? 'cors_allow_origin_mismatch' : 'cors_probe_http_error',
        status_2xx: status2xx,
        allow_origin_present: allowOrigin !== null,
        allow_origin_exact: allowOriginExact,
      });
    });
    res.on('error', () => {
      clearTimeout(timer);
      finish({
        ok: false,
        category: 'cors_probe_no_response',
        status_2xx: false,
        allow_origin_present: false,
        allow_origin_exact: false,
      });
    });
  },
);
req.on('error', () => {
  clearTimeout(timer);
  finish({
    ok: false,
    category: 'cors_probe_no_response',
    status_2xx: false,
    allow_origin_present: false,
    allow_origin_exact: false,
  });
});
req.end();
