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
  partial.markOutcomesAfterFailure('HC03');
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
  expect(parsed.nodes.some((n) => n.outcome === 'NOT_RUN'), 'H: NOT_RUN nodes distinguished from FAIL');
  expect(!parsed.nodes.some((n) => n.outcome === 'PENDING'), 'H: no PENDING left unclassified after failure marking');
  expect(parsed.summary.outcomes.fail >= 1 && parsed.summary.outcomes.notRun >= 1, 'H: outcome counters distinguish fail/notRun');
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

// ---------------------------------------------------------------------------
// B1-R2 D — strict register / lifecycle / W2 fixtures
// ---------------------------------------------------------------------------
{
  const specText = readFileSync(join(ROOT, 'tests', 'recovery.spec.ts'), 'utf8');
  const precondText = readFileSync(join(ROOT, 'src', 'preconditions.ts'), 'utf8');
  // 2xx-only register contract present; 409 never accepted.
  expect(
    precondText.includes('status !== 200 && status !== 201') &&
      !/status\s*===\s*409/.test(precondText),
    'D: strict 2xx-only register (no 409 acceptance)',
  );
  expect(precondText.includes('loginProofMustFail'), 'D: fail-proof helper for unverified/W2');
  expect(precondText.includes('must_differ_from_w1'), 'D: W1==W2 rejected');
  expect(
    precondText.includes('collides_with_provisioned_identity'),
    'D: unknown-email normalization collision rejected',
  );
  expect(precondText.includes('retailer_not_bound_to_w2_proof'), 'D: retailer-W2 binding fail-proof');
  // Full lifecycle anchors.
  expect(
    precondText.includes('SETUP_CONSUME_URL') && precondText.includes('loginProofSucceeds'),
    'D: register -> setup consume -> login proof lifecycle',
  );
}

// B1-R3 — multi-mailbox scanner truth fixtures (schema/2, both mailboxes)
// ---------------------------------------------------------------------------
{
  const scanner = join(ROOT, 'tools', 'scan-artifacts.mjs');
  const artifacts = mkdtempSync(join(tmpdir(), 'j1h2c-scan5-'));
  const maildir = mkdtempSync(join(tmpdir(), 'j1h2c-mail5-'));
  const est = 'est5@example.com';
  const unv = 'unv5@example.com';
  const estBox = join(maildir, est);
  const unvBox = join(maildir, unv);
  mkdirSync(estBox, { recursive: true });
  mkdirSync(unvBox, { recursive: true });
  // Historical (pre-run) tokens in BOTH mailboxes must be excluded.
  writeFileSync(join(estBox, '0000-old.json'), JSON.stringify({ link: '/retailer/reset-password#resetToken=historical-est-token&w=W1XC' }));
  writeFileSync(join(unvBox, '0000-old.json'), JSON.stringify({ link: '/retailer/setup-credential#setupToken=historical-unv-token&w=W1XC' }));
  writeFileSync(
    join(artifacts, 'maildir-snapshot.json'),
    JSON.stringify({
      schema: 'j1h2c-maildir-snapshot/2',
      mailboxes: { established: ['0000-old.json'], unverified: ['0000-old.json'] },
      note: 'identity labels + filenames only',
    }),
  );
  // THIS run: established setup + reset tokens; unverified setup token.
  writeFileSync(join(estBox, '0001-new.json'), JSON.stringify({ link: '/retailer/setup-credential#setupToken=est-setup-token-777&w=W1XC' }));
  writeFileSync(join(estBox, '0002-new.json'), JSON.stringify({ link: '/retailer/reset-password#resetToken=est-reset-token-888&w=W1XC' }));
  writeFileSync(join(unvBox, '0001-new.json'), JSON.stringify({ link: '/retailer/setup-credential#setupToken=unv-setup-token-999&w=W1XC' }));
  const env = {
    ...process.env,
    J1H2C_RETAILER_EMAIL: est,
    J1H2C_UNVERIFIED_EMAIL: unv,
    J1H2C_RETAILER_CURRENT_PASSWORD: 'CurrentPass_9!', // pragma: allowlist secret
    J1H2C_RETAILER_NEW_PASSWORD: 'NewPass_8x!', // pragma: allowlist secret
    J1H2C_FORGED_RESET_TOKEN: 'forged-run5-unique-8x',
    J1H2C_W1_CANONICAL_CODE: 'W1XC',
    J1H2C_MAILDIR_ROOT: maildir,
  };
  // Snapshot artifact hygiene: labels + filenames only (M31 truth).
  const snapText = readFileSync(join(artifacts, 'maildir-snapshot.json'), 'utf8');
  expect(!snapText.includes(est) && !snapText.includes(unv), 'M31: snapshot carries no email values');
  expect(!/token/i.test(snapText.split('note')[0]), 'M31: snapshot carries no token values');

  // Clean pass: 3 mail tokens + forged = 4 run secrets.
  const r = execFileSync('node', [scanner, '--artifacts-dir', artifacts, '--secrets-from-env'], {
    encoding: 'utf8', env, stdio: ['ignore', 'pipe', 'pipe'],
  });
  expect(r.includes('4 run secret'), 'B1-R3: both mailboxes collected (setup+setup+reset+forged)');

  // Leak probes: each secret category must be RED when present in artifacts.
  for (const [label, value] of [
    ['est_setup', 'est-setup-token-777'],
    ['unv_setup', 'unv-setup-token-999'],
    ['est_reset', 'est-reset-token-888'],
    ['forged', 'forged-run5-unique-8x'],
  ]) {
    writeFileSync(join(artifacts, 'probe.txt'), `oops ${value}`);
    let detected = false;
    try {
      execFileSync('node', [scanner, '--artifacts-dir', artifacts, '--secrets-from-env'], {
        encoding: 'utf8', env, stdio: ['ignore', 'pipe', 'pipe'],
      });
    } catch (error) {
      detected = String(error.stderr ?? '').includes('run_token');
    }
    expect(detected, `M28-RED: ${label} token leak detected`);
    rmSync(join(artifacts, 'probe.txt'), { force: true });
  }

  // Historical tokens (both mailboxes) must NOT be in the secret set.
  writeFileSync(join(artifacts, 'old-probe.txt'), 'contains historical-est-token and historical-unv-token');
  let oldFlagged = false;
  try {
    execFileSync('node', [scanner, '--artifacts-dir', artifacts, '--secrets-from-env'], {
      encoding: 'utf8', env, stdio: ['ignore', 'pipe', 'pipe'],
    });
  } catch (error) {
    oldFlagged = String(error.stderr ?? '').includes('run_token');
  }
  expect(!oldFlagged, 'B1-R3: historical tokens from BOTH mailboxes excluded');
  rmSync(join(artifacts, 'old-probe.txt'), { force: true });

  // Forged reuse fail-closed.
  const envReuse = { ...env, J1H2C_FORGED_RESET_TOKEN: 'est-reset-token-888' };
  let reuseClosed = false;
  try {
    execFileSync('node', [scanner, '--artifacts-dir', artifacts, '--secrets-from-env'], {
      encoding: 'utf8', env: envReuse, stdio: ['ignore', 'pipe', 'pipe'],
    });
  } catch (error) {
    reuseClosed = String(error.stderr ?? '').includes('reuse forbidden');
  }
  expect(reuseClosed, 'B1-R3-RED: forged==real token fails closed');

  // Missing mailbox snapshot entry fails closed.
  const artifacts6 = mkdtempSync(join(tmpdir(), 'j1h2c-scan6-'));
  writeFileSync(join(artifacts6, 'maildir-snapshot.json'), JSON.stringify({ schema: 'j1h2c-maildir-snapshot/2', mailboxes: { established: [] } }));
  let mailboxClosed = false;
  try {
    execFileSync('node', [scanner, '--artifacts-dir', artifacts6, '--secrets-from-env'], {
      encoding: 'utf8', env, stdio: ['ignore', 'pipe', 'pipe'],
    });
  } catch (error) {
    mailboxClosed = String(error.stderr ?? '').includes('expected mailbox');
  }
  expect(mailboxClosed, 'B1-R3-RED: missing unverified mailbox snapshot fails closed');
  rmSync(artifacts6, { recursive: true, force: true });

  // Missing dynamic env inputs still fail closed.
  const stripped = { ...env };
  delete stripped.J1H2C_RETAILER_CURRENT_PASSWORD;
  let missingClosed = false;
  try {
    execFileSync('node', [scanner, '--artifacts-dir', artifacts, '--secrets-from-env'], {
      encoding: 'utf8', env: stripped, stdio: ['ignore', 'pipe', 'pipe'],
    });
  } catch (error) {
    missingClosed = String(error.stderr ?? '').includes('FAIL-CLOSED');
  }
  expect(missingClosed, 'B1-R3-RED: missing dynamic inputs fails closed');
  rmSync(artifacts, { recursive: true, force: true });
  rmSync(maildir, { recursive: true, force: true });
}

// B1-R3 — reconciliation truth fixtures
// ---------------------------------------------------------------------------
{
  const { load, dir } = transpile('src/reconciliation.ts');
  const rec = await load();

  // M29 truth: precondition failure => precondition FAIL + ALL 17 NOT_RUN.
  {
    const preconditionFail = new rec.RunReconciliation();
    preconditionFail.recordPreconditionFail();
    const summary = preconditionFail.summary();
    expect(summary.preconditionOutcome === 'PRECONDITION_FAIL', 'M29: precondition outcome FAIL');
    expect(summary.outcomes.fail === 0, 'M29: zero fabricated node FAILs');
    expect(summary.outcomes.notRun === 17, 'M29: all 17 nodes NOT_RUN');
    expect(summary.outcomes.pending === 0 && summary.outcomes.pass === 0, 'M29: no pass/pending leaks');
    let completeRejected = false;
    try {
      preconditionFail.assertComplete();
    } catch (error) {
      completeRejected = String(error.message).includes('precondition_failed');
    }
    expect(completeRejected, 'M29-RED: precondition-failed run cannot assert complete');
  }

  // HC03 first-failure exactness: prior PASS, HC03 FAIL, later NOT_RUN.
  {
    const run = new rec.RunReconciliation();
    run.recordBrowserPass('HC01');
    run.recordBrowserPass('HC02');
    // Static HC11/HC17 follow their HC07 dependency: HC07 not reached =>
    // they stay NOT_RUN alongside the unreached browser nodes.
    run.markOutcomesAfterFailure('HC03');
    const byId = new Map(run.snapshot().map((n) => [n.nodeId, n.outcome]));
    expect(byId.get('HC01') === 'PASS' && byId.get('HC02') === 'PASS', 'HC03-fail: prior nodes stay PASS');
    expect(byId.get('HC03') === 'FAIL', 'HC03-fail: exact failed node FAIL');
    expect(byId.get('HC04') === 'NOT_RUN' && byId.get('HC16') === 'NOT_RUN', 'HC03-fail: later browser nodes NOT_RUN');
    expect(byId.get('HC11') === 'NOT_RUN' && byId.get('HC17') === 'NOT_RUN', 'HC03-fail: HC11/HC17 NOT_RUN (HC07 dependency)');
    const summary = run.summary();
    expect(summary.outcomes.pass === 2 && summary.outcomes.fail === 1 && summary.outcomes.notRun === 14, 'HC03-fail: counters exact');
  }

  // Full success: 17/17 PASS, gap 0; M30: a missing record must throw.
  {
    const complete = new rec.RunReconciliation();
    for (const id of ['HC01','HC02','HC03','HC04','HC05','HC06','HC07','HC08','HC09','HC10','HC12','HC13','HC14','HC15']) {
      complete.recordBrowserPass(id);
    }
    complete.recordStaticPass('HC11');
    // M30 variant: omit HC16 -> assertComplete must throw (command RED).
    let incompleteRejected = false;
    try {
      complete.assertComplete();
    } catch {
      incompleteRejected = true;
    }
    expect(incompleteRejected, 'M30-RED: missing recordBrowserPass(HC16) cannot pass assertComplete');
    complete.recordBrowserPass('HC16');
    complete.recordStaticPass('HC17');
    let ok = true;
    try {
      complete.assertComplete();
    } catch {
      ok = false;
    }
    expect(ok, 'B1-R3: full 17/17 gap-0 reconciliation passes');
    expect(complete.summary().outcomes.notRun === 0 && complete.summary().outcomes.fail === 0, 'B1-R3: success has zero FAIL/NOT_RUN');
  }
  rmSync(dir, { recursive: true, force: true });
}

// B1-R3-R1 — publication ordering truth (publish BEFORE completeness)
// ---------------------------------------------------------------------------
{
  const specText = readFileSync(join(ROOT, 'tests', 'recovery.spec.ts'), 'utf8');
  const publishIdx = specText.indexOf(["reconciliation.publishArtifacts('artifacts');", '        reconciliation.assertComplete();'].join('\n'));
  expect(publishIdx >= 0, 'M32: success path must publish BEFORE assertComplete');
  // The old reversed order must not exist anywhere.
  const reversed = specText.indexOf('reconciliation.assertComplete();');
  const publishAll = [];
  let searchFrom = 0;
  while (true) {
    const idx = specText.indexOf("reconciliation.publishArtifacts('artifacts');", searchFrom);
    if (idx < 0) break;
    publishAll.push(idx);
    searchFrom = idx + 1;
  }
  // Every assertComplete call must have a publish BEFORE it on the same
  // success path (the first publish precedes the only assertComplete).
  expect(publishAll.length >= 1 && reversed > publishAll[0], 'M32: publish index precedes assert index');

  // M33: missing record -> artifact published AND command RED. Use the
  // reconciliation module: publish then assert (exact spec order).
  const { load, dir } = transpile('src/reconciliation.ts');
  const rec = await load();
  const artifacts = mkdtempSync(join(tmpdir(), 'j1h2c-scan7-'));
  const run = new rec.RunReconciliation();
  for (const id of ['HC01','HC02','HC03','HC04','HC05','HC06','HC07','HC08','HC09','HC10','HC12','HC13','HC14','HC15','HC16']) {
    run.recordBrowserPass(id);
  }
  run.recordStaticPass('HC11');
  // HC17 missing => publish truthful (incomplete) state, THEN assert -> throw.
  run.publishArtifacts(artifacts); // publish first (spec order)
  const json = readFileSync(join(artifacts, 'reconciliation.json'), 'utf8');
  const parsed = JSON.parse(json);
  expect(parsed.nodes.some((n) => n.nodeId === 'HC17' && n.outcome === 'PENDING'), 'M33: truthful PENDING published for the missing record');
  let asserted = false;
  try {
    run.assertComplete(); // then judge -> must throw
  } catch {
    asserted = true;
  }
  expect(asserted, 'M33: command-equivalent assertComplete throws (non-zero exit)');
  expect(parsed.summary.outcomes.pending >= 1, 'M33: published artifact shows the incomplete truth');
  rmSync(artifacts, { recursive: true, force: true });
  rmSync(dir, { recursive: true, force: true });
}

// B1-R3-R1 — setup token cardinality truth (M34/M35)
// ---------------------------------------------------------------------------
{
  const scanner = join(ROOT, 'tools', 'scan-artifacts.mjs');
  for (const variant of ['unverified', 'established']) {
    const artifacts = mkdtempSync(join(tmpdir(), 'j1h2c-scan8-'));
    const maildir = mkdtempSync(join(tmpdir(), 'j1h2c-mail8-'));
    const est = 'est8@example.com';
    const unv = 'unv8@example.com';
    const estBox = join(maildir, est);
    const unvBox = join(maildir, unv);
    mkdirSync(estBox, { recursive: true });
    mkdirSync(unvBox, { recursive: true });
    writeFileSync(join(estBox, '0001.json'), JSON.stringify({ link: '/retailer/setup-credential#setupToken=est8-setup-main-token&w=W1XC' }));
    writeFileSync(join(unvBox, '0001.json'), JSON.stringify({ link: '/retailer/setup-credential#setupToken=unv8-setup-main-token&w=W1XC' }));
    // The variant mailbox gets a SECOND distinct setup token (M34/M35).
    const targetBox = variant === 'unverified' ? unvBox : estBox;
    writeFileSync(join(targetBox, '0002.json'), JSON.stringify({ link: `/retailer/setup-credential#setupToken=${variant}-8-setup-extra-token&w=W1XC` }));
    writeFileSync(
      join(artifacts, 'maildir-snapshot.json'),
      JSON.stringify({ schema: 'j1h2c-maildir-snapshot/2', mailboxes: { established: [], unverified: [] } }),
    );
    const env = {
      ...process.env,
      J1H2C_RETAILER_EMAIL: est,
      J1H2C_UNVERIFIED_EMAIL: unv,
      J1H2C_RETAILER_CURRENT_PASSWORD: 'CurrentPass_9!', // pragma: allowlist secret
      J1H2C_RETAILER_NEW_PASSWORD: 'NewPass_8x!', // pragma: allowlist secret
      J1H2C_FORGED_RESET_TOKEN: 'forged-run8-unique-8x',
      J1H2C_W1_CANONICAL_CODE: 'W1XC',
      J1H2C_MAILDIR_ROOT: maildir,
    };
    let cardinalityClosed = false;
    try {
      execFileSync('node', [scanner, '--artifacts-dir', artifacts, '--secrets-from-env'], {
        encoding: 'utf8', env, stdio: ['ignore', 'pipe', 'pipe'],
      });
    } catch (error) {
      const err = String(error.stderr ?? '');
      cardinalityClosed = err.includes('setup_token_cardinality') && err.includes(variant);
    }
    expect(cardinalityClosed, `M${variant === 'unverified' ? '34' : '35'}-RED: dual setup tokens in ${variant} mailbox fail closed`);
    rmSync(artifacts, { recursive: true, force: true });
    rmSync(maildir, { recursive: true, force: true });
  }
  // Zero-setup also still fails closed (label+category only).
  {
    const artifacts = mkdtempSync(join(tmpdir(), 'j1h2c-scan9-'));
    const maildir = mkdtempSync(join(tmpdir(), 'j1h2c-mail9-'));
    const est = 'est9@example.com';
    const unv = 'unv9@example.com';
    mkdirSync(join(maildir, est), { recursive: true });
    mkdirSync(join(maildir, unv), { recursive: true });
    writeFileSync(join(maildir, est, '0001.json'), JSON.stringify({ link: '/retailer/setup-credential#setupToken=est9-setup-token-xx&w=W1XC' }));
    writeFileSync(join(artifacts, 'maildir-snapshot.json'), JSON.stringify({ schema: 'j1h2c-maildir-snapshot/2', mailboxes: { established: [], unverified: [] } }));
    const env = {
      ...process.env,
      J1H2C_RETAILER_EMAIL: est,
      J1H2C_UNVERIFIED_EMAIL: unv,
      J1H2C_RETAILER_CURRENT_PASSWORD: 'CurrentPass_9!', // pragma: allowlist secret
      J1H2C_RETAILER_NEW_PASSWORD: 'NewPass_8x!', // pragma: allowlist secret
      J1H2C_FORGED_RESET_TOKEN: 'forged-run9-unique-8x',
      J1H2C_W1_CANONICAL_CODE: 'W1XC',
      J1H2C_MAILDIR_ROOT: maildir,
    };
    let zeroClosed = false;
    try {
      execFileSync('node', [scanner, '--artifacts-dir', artifacts, '--secrets-from-env'], {
        encoding: 'utf8', env, stdio: ['ignore', 'pipe', 'pipe'],
      });
    } catch (error) {
      zeroClosed = String(error.stderr ?? '').includes('setup_token_cardinality:unverified:0');
    }
    expect(zeroClosed, 'B1-R3-R1-RED: zero unverified setup tokens fail closed (label+category only)');
    rmSync(artifacts, { recursive: true, force: true });
    rmSync(maildir, { recursive: true, force: true });
  }
}

// B1-R3 — spec wiring anchors
// ---------------------------------------------------------------------------
{
  const specText = readFileSync(join(ROOT, 'tests', 'recovery.spec.ts'), 'utf8');
  expect(specText.includes('recordPreconditionFail();'), 'spec: beforeAll catch records precondition failure');
  expect(specText.includes('reconciliation.assertComplete();'), 'spec: success afterAll asserts completeness');
  expect(specText.includes('clearMemoryState();'), 'H: clearMemoryState called in spec');
}

// ---------------------------------------------------------------------------
// B1-R4 — type-only import runtime loader closure
//
// Transpiles the REAL three-module neutrality graph (neutrality-core.ts,
// assertions.ts, neutrality.ts — no copied implementation) with
// verbatimModuleSyntax=true, which preserves erroneous VALUE imports while
// eliding only explicit `import type` declarations, then loads the emitted
// ESM with the real Node loader. A value import of the type-only
// `CanonicalFingerprint` interface must fail the load; the type-only import
// must load and expose the existing runtime API.
// ---------------------------------------------------------------------------
{
  const dir = mkdtempSync(join(tmpdir(), 'j1h2c-b1r4-'));
  try {
    for (const rel of ['src/neutrality-core.ts', 'src/assertions.ts', 'src/neutrality.ts']) {
      const source = readFileSync(join(ROOT, rel), 'utf8');
      const out = ts.transpileModule(source, {
        compilerOptions: {
          module: ts.ModuleKind.ES2022,
          target: ts.ScriptTarget.ES2022,
          verbatimModuleSyntax: true,
        },
      }).outputText;
      writeFileSync(join(dir, rel.split('/').pop().replace(/[.]ts$/, '.js')), out, 'utf8');
    }

    let neutrality;
    try {
      neutrality = await import(pathToFileURL(join(dir, 'neutrality.js')).href);
    } catch (error) {
      expect(
        false,
        `B1-R4: neutrality.js failed to load under verbatimModuleSyntax (${String(
          error && error.message,
        ).slice(0, 100)})`,
      );
    }
    if (neutrality) {
      expect(typeof neutrality.fingerprintNeutralResponse === 'function', 'B1-R4: exports fingerprintNeutralResponse');
      expect(typeof neutrality.assertFourStateCanonicalEquality === 'function', 'B1-R4: exports assertFourStateCanonicalEquality');
      expect(typeof neutrality.NeutralEnvelopeError === 'function', 'B1-R4: exports NeutralEnvelopeError');
      expect(!('CanonicalFingerprint' in neutrality), 'B1-R4: CanonicalFingerprint is not a runtime binding');

      // Functional smoke over the REAL loaded module graph: the loaded core
      // still enforces canonical neutrality semantics unchanged.
      const core = await import(pathToFileURL(join(dir, 'neutrality-core.js')).href);
      const envelope = (overrides) => ({
        success: true,
        data: {},
        message: core.NEUTRAL_MESSAGE_CONSTANT,
        timestamp: '2026-08-30T00:00:00Z',
        ...overrides,
      });
      let semanticsOk = true;
      try {
        const fp = core.canonicalFingerprint(envelope());
        core.assertFingerprintsEqual(fp, core.canonicalFingerprint(envelope({ timestamp: '1999-01-01T00:00:00Z' })));
        for (const [drift, category] of [
          [{ message: 'different' }, 'MESSAGE_VALUE'],
          [{ extra: 1 }, 'KEY_SET'],
          [{ success: false }, 'SUCCESS_VALUE'],
          [{ timestamp: 123 }, 'TIMESTAMP_TYPE'],
        ]) {
          let threw = null;
          try {
            core.canonicalFingerprint(envelope(drift));
          } catch (error) {
            threw = error;
          }
          if (
            !(threw instanceof core.NeutralEnvelopeError) ||
            threw.category !== category
          ) {
            semanticsOk = false;
          }
        }
      } catch {
        semanticsOk = false;
      }
      expect(semanticsOk, 'B1-R4: loaded core keeps canonical neutrality semantics');
    }
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

if (failures.length > 0) {
  for (const message of failures) console.error(message);
  console.error(`RUNTIME-CONTRACT CHECK FAILED (${failures.length})`);
  process.exit(1);
}
console.log('EXECUTABLE RUNTIME-CONTRACT CHECKS PASSED (A/B/E/C/H/I + B1-R3 truth + B1-R3-R1 ordering/cardinality + B1-R4 loader).');
