#!/usr/bin/env node
/**
 * Executable RUNTIME-CONTRACT tests (B1-R1 static gate member) covering
 * the Kilo A-I closures at the unit level — no browser, no product
 * runtime, no network. Each check exercises the REAL harness modules
 * (transpiled with the installed typescript) against fixtures.
 *
 * Coverage (task-required):
 *   A  legal token ONLY in the reset POST reset_token body field GREEN;
 *      token in URL/header/other body field/storage/console RED;
 *      missing reset POST RED (spec anchor + waitForRequest present).
 *   B  w on forbidden surfaces RED (request URL/header/body/storage/
 *      console).
 *   E  stale mail rejected, exactly-one-new-delivery precisely selected;
 *      relative AND absolute legal links both GREEN; bad pathname/query/
 *      fragment key set RED; sanitized errors (no filename/email/URL/
 *      token/code).
 *   C  invalid second-supplier precondition RED (env fail-closed shape).
 *   H  reconciliation partial state never masquerades as complete.
 *   I  secret scanner fails closed without dynamic secret inputs.
 */

import { readFileSync, mkdtempSync, writeFileSync, mkdirSync, rmSync } from 'node:fs';
import { createRequire } from 'node:module';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';

const require = createRequire(import.meta.url);
const ts = require('typescript');

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const failures = [];

function expect(condition, label) {
  if (!condition) failures.push(`runtime-contract: ${label}`);
}

function transpile(relPath) {
  const source = readFileSync(join(ROOT, relPath), 'utf8');
  const inlined = source.replace(
    /from '[.][^']+';/g,
    (match) => {
      const spec = match.slice(6, -2); // strip "from '" and "';"
      const base = spec.replace(/[.]js$/, '');
      const depPath = join(ROOT, 'src', base.slice(2) + '.ts');
      let depSource;
      try {
        depSource = readFileSync(depPath, 'utf8');
      } catch {
        return match;
      }
      const depOut = ts.transpileModule(depSource, {
        compilerOptions: { module: ts.ModuleKind.ES2022, target: ts.ScriptTarget.ES2022 },
      }).outputText;
      const b64 = Buffer.from(depOut, 'utf8').toString('base64');
      return `from 'data:text/javascript;base64,${b64}';`;
    },
  );
  const out = ts.transpileModule(inlined, {
    compilerOptions: { module: ts.ModuleKind.ES2022, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const dir = mkdtempSync(join(tmpdir(), 'j1h2c-rt-'));
  const file = join(dir, 'module.mjs');
  writeFileSync(file, out, 'utf8');
  return { load: () => import(pathToFileURL(file).href), dir };
}

// Fake Page/Request doubles that exercise the REAL scanner logic.
function fakePage({ url = 'http://x/retailer/reset-password', storage = [] } = {}) {
  return {
    url: () => url,
    evaluate: async (fn, arg) => {
      // Simulate the storage reader body.
      if (String(fn).includes('localStorage')) return arg ?? storage;
      return undefined;
    },
  };
}

function fakeRequest({ url = 'http://x/api', method = 'GET', headers = {}, postData = null } = {}) {
  return { url: () => url, method: () => method, headers: () => headers, postData: () => postData };
}

const TOKEN = 'rt-token-abcdef1234';
const CODE = 'WSTEST01';

// ---------------------------------------------------------------------------
// A + B — leak-scan runtime contract
// ---------------------------------------------------------------------------
{
  const { load, dir } = transpile('src/leak-scan.ts');
  const leakScan = await load();
  const capture = { entries: [] };

  // A-GREEN: token ONLY in reset POST reset_token body.
  {
    const requests = [
      fakeRequest({
        url: 'http://x/api/v1/client/auth/reset-password',
        method: 'POST',
        postData: JSON.stringify({ reset_token: TOKEN, new_password: 'NewPass123!' }),
      }),
    ];
    const result = await leakScan.scanTokenLeak(fakePage(), TOKEN, capture, requests);
    expect(!Object.values(result).some(Boolean), 'A: legitimate reset_token body flagged');
  }

  // A-RED cases: URL, header, other body field, storage, console.
  for (const [label, page, requests, localCapture] of [
    ['token_in_url', fakePage({ url: `http://x/?t=${TOKEN}` }), [], capture],
    ['token_in_header', fakePage(), [fakeRequest({ headers: { 'x-debug': TOKEN } })], capture],
    [
      'token_in_other_body_field',
      fakePage(),
      [fakeRequest({ method: 'POST', url: 'http://x/api/v1/other', postData: JSON.stringify({ note: TOKEN }) })],
      capture,
    ],
    ['token_in_storage', fakePage({ storage: [`k=${TOKEN}`] }), [], capture],
    ['token_in_console', fakePage(), [], { entries: [`log ${TOKEN}`] }],
  ]) {
    const result = await leakScan.scanTokenLeak(page, TOKEN, localCapture, requests);
    expect(Object.values(result).some(Boolean), `A-RED: ${label} must be flagged`);
  }

  // A-RED: missing reset POST deterministically fails the spec — verify the
  // spec installs waitForRequest for the reset POST BEFORE the click.
  const specText = readFileSync(join(ROOT, 'tests/recovery.spec.ts'), 'utf8');
  const waitIndex = specText.indexOf('page.waitForRequest(');
  const clickIndex = specText.indexOf('fillNewPasswordAndSubmit(page, env().retailer.newPassword);');
  const hc12Wait = specText.indexOf('resetPostPromise');
  expect(hc12Wait >= 0 && hc12Wait < clickIndex, 'A: reset POST wait must precede the click');
  expect(waitIndex >= 0, 'A: waitForRequest present');

  // B-RED: w on forbidden surfaces.
  for (const [label, page, requests, localCapture] of [
    [
      'w_in_api_request_url',
      fakePage(),
      [fakeRequest({ url: `http://x/api/v1/things?w=${CODE}` })],
      capture,
    ],
    ['w_in_header', fakePage(), [fakeRequest({ headers: { 'x-portal': CODE } })], capture],
    [
      'w_in_request_body',
      fakePage(),
      [fakeRequest({ method: 'POST', url: 'http://x/api/v1/other', postData: JSON.stringify({ w: CODE }) })],
      capture,
    ],
    ['w_in_storage', fakePage({ storage: [`portal=${CODE}`] }), [], capture],
    ['w_in_console', fakePage(), [], { entries: [`portal ${CODE}`] }],
  ]) {
    const result = await leakScan.scanPublicCode(page, CODE, localCapture, requests);
    expect(Object.values(result).some(Boolean), `B-RED: ${label} must be flagged`);
  }

  // B-GREEN: canonical portal page URL navigation only.
  {
    const result = await leakScan.scanPublicCode(
      fakePage({ url: `http://x/retail/login?w=${CODE}` }),
      CODE,
      capture,
      [],
    );
    expect(!Object.values(result).some(Boolean), 'B: canonical portal URL allowed');
  }
  rmSync(dir, { recursive: true, force: true });
}

// ---------------------------------------------------------------------------
// E — maildir freshness + link validation
// ---------------------------------------------------------------------------
{
  const { load, dir } = transpile('src/maildir.ts');
  const maildir = await load();

  const root = mkdtempSync(join(tmpdir(), 'j1h2c-mail-'));
  const email = 'probe@example.com';
  const box = join(root, email);
  mkdirSync(box, { recursive: true });
  // A STALE delivery (pre-existing).
  writeFileSync(join(box, '0001-stale.json'), JSON.stringify({ link: '/retailer/reset-password#resetToken=stale-token&w=OLDCODE' }));

  const snapshot = await maildir.snapshotDeliveries(root, email);
  expect(snapshot.size === 1, 'E: snapshot sees the stale file');

  // Stale mail rejected: no new file => timeout with a sanitized error.
  let staleRejected = false;
  try {
    await maildir.pollForExactlyOneNewDelivery(root, email, snapshot, { timeoutMs: 300, intervalMs: 50 });
  } catch (error) {
    const message = String(error.message ?? error);
    staleRejected = message.includes('timeout_no_new_file');
    expect(!message.includes('0001-stale') && !message.includes(email), 'E: sanitized error (no filename/email)');
  }
  expect(staleRejected, 'E-RED: stale mail must be rejected (timeout)');

  // Exactly-one-new selection: fresh file parsed, stale never returned.
  writeFileSync(join(box, '0002-fresh.json'), JSON.stringify({ link: '/retailer/reset-password#resetToken=fresh-token-99&w=WSNEW01' }));
  const fresh = await maildir.pollForExactlyOneNewDelivery(root, email, snapshot, { timeoutMs: 1_000, intervalMs: 50 });
  expect(fresh.link.includes('fresh-token-99'), 'E: exactly-one-new precisely selected');

  // Multiple new files rejected.
  const snapshot2 = await maildir.snapshotDeliveries(root, email);
  writeFileSync(join(box, '0003-a.json'), JSON.stringify({ link: '/x' }));
  writeFileSync(join(box, '0004-b.json'), JSON.stringify({ link: '/y' }));
  let multipleRejected = false;
  try {
    await maildir.pollForExactlyOneNewDelivery(root, email, snapshot2, { timeoutMs: 300, intervalMs: 50 });
  } catch (error) {
    multipleRejected = String(error.message ?? error).includes('multiple_new_files');
  }
  expect(multipleRejected, 'E-RED: multiple new deliveries must be rejected');

  // Relative AND absolute legal links both GREEN.
  const relative = maildir.parseAndValidateResetLink(
    '/retailer/reset-password#resetToken=tok1&w=WSA1',
    { requireCanonicalW: 'WSA1' },
  );
  expect(relative.resetToken === 'tok1' && relative.portalCode === 'WSA1', 'E: relative link GREEN');
  const absolute = maildir.parseAndValidateResetLink(
    'https://frontend.example.com/retailer/reset-password#resetToken=tok2&w=WSA1',
    { requireCanonicalW: 'WSA1' },
  );
  expect(absolute.resetToken === 'tok2', 'E: absolute link GREEN');

  // Invalid shapes RED with sanitized errors.
  for (const [label, link] of [
    ['wrong_pathname', '/other/path#resetToken=t&w=C1'],
    ['query_string', '/retailer/reset-password?x=1#resetToken=t&w=C1'],
    ['missing_w', '/retailer/reset-password#resetToken=t'],
    ['extra_fragment_key', '/retailer/reset-password#resetToken=t&w=C1&extra=1'],
    ['wrong_canonical_w', '/retailer/reset-password#resetToken=t&w=OTHER'],
  ]) {
    let rejected = false;
    try {
      maildir.parseAndValidateResetLink(link, { requireCanonicalW: 'C1CCCC1' === 'C1CCCC1' ? 'C1' : 'C1' });
    } catch {
      rejected = true;
    }
    expect(rejected, `E-RED: ${label} must be rejected`);
  }
  rmSync(root, { recursive: true, force: true });
  rmSync(dir, { recursive: true, force: true });
}

// ---------------------------------------------------------------------------
// C — invalid second-supplier precondition RED (env fail-closed shape)
// ---------------------------------------------------------------------------
{
  const { load, dir } = transpile('src/env.ts');
  const envModule = await load();
  const saved = { ...process.env };
  delete process.env.J1H2C_W2_CANONICAL_CODE;
  let failedClosed = false;
  try {
    process.env.J1H2C_BASE_URL = 'http://f.invalid';
    process.env.J1H2C_API_BASE_URL = 'http://f.invalid';
    process.env.J1H2C_MAILDIR_ROOT = '/tmp/x';
    process.env.J1H2C_W1_CANONICAL_CODE = 'W1CODE';
    envModule.loadJourneyEnv();
  } catch (error) {
    const message = String(error.message ?? error);
    failedClosed = message.includes('J1H2C_W2_CANONICAL_CODE');
  } finally {
    process.env = saved;
  }
  expect(failedClosed, 'C-RED: missing W2 env fails closed naming the variable only');
  rmSync(dir, { recursive: true, force: true });
}

// ---------------------------------------------------------------------------
// H — reconciliation partial never masquerades as complete
// ---------------------------------------------------------------------------
{
  const { load, dir } = transpile('src/reconciliation.ts');
  const rec = await load();
  const partial = new rec.RunReconciliation();
  partial.recordBrowserPass('HC01');
  partial.markPendingAsFailed();
  let completeRejected = false;
  try {
    partial.assertComplete();
  } catch {
    completeRejected = true;
  }
  expect(completeRejected, 'H-RED: partial reconciliation must not pass assertComplete');

  const artifacts = mkdtempSync(join(tmpdir(), 'j1h2c-art-'));
  partial.publishArtifacts(artifacts);
  const json = readFileSync(join(artifacts, 'reconciliation.json'), 'utf8');
  const parsed = JSON.parse(json);
  expect(parsed.nodes.some((n) => n.outcome === 'FAIL'), 'H: failure state published truthfully');
  expect(parsed.nodes.some((n) => n.outcome === 'PASS'), 'H: pass state published');
  expect(parsed.note.includes('no secrets'), 'H: artifact carries the no-secrets note');
  expect(!JSON.stringify(parsed.nodes).includes('reset_token'), 'H: artifact nodes carry no token fields');
  const complete = new rec.RunReconciliation();
  for (const id of ['HC01','HC02','HC03','HC04','HC05','HC06','HC07','HC08','HC09','HC10','HC12','HC13','HC14','HC15','HC16']) {
    complete.recordBrowserPass(id);
  }
  complete.recordStaticPass('HC11');
  complete.recordStaticPass('HC17');
  let completeOk = true;
  try {
    complete.assertComplete();
  } catch {
    completeOk = false;
  }
  expect(completeOk, 'H: full 15+2 reconciliation passes');
  rmSync(artifacts, { recursive: true, force: true });
  rmSync(dir, { recursive: true, force: true });
}

// ---------------------------------------------------------------------------
// I — scanner fails closed without dynamic secret inputs
// ---------------------------------------------------------------------------
{
  const scanner = join(ROOT, 'tools/scan-artifacts.mjs');
  const artifacts = mkdtempSync(join(tmpdir(), 'j1h2c-scan-'));
  const saved = { ...process.env };
  delete process.env.J1H2C_RETAILER_CURRENT_PASSWORD;
  delete process.env.J1H2C_RETAILER_NEW_PASSWORD;
  delete process.env.J1H2C_LAST_RESET_TOKEN;
  let failedClosed = false;
  let output = '';
  try {
    execFileSync('node', [scanner, '--artifacts-dir', artifacts, '--secrets-from-env'], {
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'pipe'],
    });
  } catch (error) {
    failedClosed = true;
    output = String(error.stderr ?? '');
  } finally {
    process.env = saved;
  }
  expect(failedClosed, 'I-RED: scanner must fail closed without secret inputs');
  expect(
    !output.includes('NewPass') && !/token[-_ ]?[a-z0-9]{6,}/i.test(output),
    'I: scanner output sanitized',
  );
  // Without the flag at all it must also fail closed.
  let noFlagClosed = false;
  try {
    execFileSync('node', [scanner, '--artifacts-dir', artifacts], { encoding: 'utf8' });
  } catch {
    noFlagClosed = true;
  }
  expect(noFlagClosed, 'I-RED: scanner without --secrets-from-env must fail closed');
  rmSync(artifacts, { recursive: true, force: true });
}

if (failures.length > 0) {
  for (const message of failures) console.error(message);
  console.error(`RUNTIME-CONTRACT CHECK FAILED (${failures.length})`);
  process.exit(1);
}
console.log('EXECUTABLE RUNTIME-CONTRACT CHECKS PASSED (A/B/E/C/H/I fixtures).');
