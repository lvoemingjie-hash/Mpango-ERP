#!/usr/bin/env node
/**
 * Static gate for the frozen j1h2b harness (task directive: 静态门禁;
 * B1-R1 adds actively-enforced serial/fail-stop contracts).
 *
 * Pure static validation — reads committed data and source only, never reads
 * credential env values, never starts any product runtime. Steps:
 *   1. Inventory CSV strict parse: 29 data rows x 15 columns,
 *      24 browser + 5 non-browser nodes.
 *   2. Registry cross-check: node-registry.json matches the CSV sets;
 *      RT0 stays BLOCKED_BY_H2_C.
 *   3. `playwright test --list` yields exactly 24 titles IN THE CSV BROWSER
 *      ROW ORDER (ordered equality, not just set equality; duplicates and
 *      unregistered nodes fail).
 *   4. Journey-structure contracts (mutation-tested at each freeze):
 *      exactly ONE spec file named forgot-reset.spec.ts; it declares
 *      test.describe.configure({ mode: 'serial' }); the frozen config holds
 *      maxFailures:1 (fail-stop); no waitForTimeout anywhere in tests/ or
 *      src/ (bounded-condition-wait discipline); the R12 test must wait on
 *      the real application settle conditions (exact pathname + empty hash
 *      + visible-and-interactable #newPassword); the generic network-quiet
 *      wait (networkidle) is banned; plus the original forbidden-marker
 *      scan and frozen config invariants.
 *   5. EOL portability contract (B1-R2): .gitattributes exists with the
 *      '* text=auto eol=lf' rule and no eol=crlf rule anywhere.
 *   6. UTF-8 (strict decode) + no BOM + no CR for every committed harness file.
 */

import { readFileSync, readdirSync, statSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { join, dirname, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const failures = [];

function fail(message) {
  failures.push(message);
}

// --- 1. Inventory CSV strict parse -----------------------------------------

const CSV_PATH = join(
  ROOT,
  'inventory',
  '2026-08-23_dc12r1_mvp_l1_j1_h2_b_r2_r3_b0_forgot_reset_node_inventory.csv',
);
const HEADER_COLUMNS = [
  'node_id', 'phase', 'actor', 'viewport', 'precondition', 'ui_route',
  'ui_action', 'expected_ui', 'expected_http', 'security_assertion',
  'source_anchor', 'execution_class', 'authoritative', 'stop_on_failure',
  'notes',
];
const BROWSER_CLASSES = new Set([
  'BROWSER',
  'BROWSER+POSTCOND',
  'BROWSER_WITH_OFFICIAL_API_PRECONDITION',
]);
const EXPECTED_NON_BROWSER = ['F6', 'R6', 'M2', 'R13', 'RT0'];

const csvRaw = readFileSync(CSV_PATH);
const csvText = csvRaw.toString('utf8');
const csvLines = csvText.split('\n').filter((line) => line.length > 0);
if (csvLines.length !== 30) {
  fail(`inventory CSV must have exactly 30 lines (header + 29 rows), found ${csvLines.length}`);
}
const header = csvLines[0].split(',');
if (header.length !== 15 || header.some((name, i) => name !== HEADER_COLUMNS[i])) {
  fail('inventory CSV header must be exactly the 15 expected column names');
}
const rows = csvLines.slice(1).map((line) => line.split(','));
for (const row of rows) {
  if (row.length !== 15) {
    fail(`inventory row ${row[0]} has ${row.length} columns, expected 15`);
  }
}
const browserIds = [];
const nonBrowserIds = [];
for (const row of rows) {
  if (row.length !== 15) continue;
  if (BROWSER_CLASSES.has(row[11])) browserIds.push(row[0]);
  else nonBrowserIds.push(row[0]);
}
if (browserIds.length !== 24) fail(`expected 24 browser nodes, found ${browserIds.length}`);
if (nonBrowserIds.length !== 5) fail(`expected 5 non-browser nodes, found ${nonBrowserIds.length}`);
if ([...nonBrowserIds].sort().join(',') !== [...EXPECTED_NON_BROWSER].sort().join(',')) {
  fail(`non-browser node set must be exactly ${EXPECTED_NON_BROWSER.join('/')}, found ${nonBrowserIds.join('/')}`);
}
const csvBrowserSet = new Set(browserIds);
if (csvBrowserSet.size !== 24) fail('browser node IDs must be unique (duplicates found)');
console.log(`[1] inventory CSV: 29 rows x 15 cols, ${browserIds.length} browser + ${nonBrowserIds.length} non-browser — OK`);

// --- 2. Registry cross-check -------------------------------------------------

const registry = JSON.parse(
  readFileSync(join(ROOT, 'inventory', 'node-registry.json'), 'utf8'),
);
const registryBrowser = registry.nodes.filter((n) => n.surface === 'browser').map((n) => n.nodeId);
const registryNonBrowser = registry.nodes.filter((n) => n.surface === 'non-browser').map((n) => n.nodeId);
if (registry.nodes.length !== 29) fail(`registry must hold 29 nodes, found ${registry.nodes.length}`);
const registryBrowserSet = new Set(registryBrowser);
for (const id of csvBrowserSet) {
  if (!registryBrowserSet.has(id)) fail(`registry is missing browser node ${id}`);
}
for (const id of registryBrowser) {
  if (!csvBrowserSet.has(id)) fail(`registry holds unregistered browser node ${id}`);
}
if ([...registryNonBrowser].sort().join(',') !== [...EXPECTED_NON_BROWSER].sort().join(',')) {
  fail(`registry non-browser set must be exactly ${EXPECTED_NON_BROWSER.join('/')}`);
}
const rt0 = registry.nodes.find((n) => n.nodeId === 'RT0');
if (!rt0 || rt0.status !== 'BLOCKED_BY_H2_C') fail('RT0 must carry status BLOCKED_BY_H2_C');
console.log('[2] registry cross-check against CSV sets — OK');

// --- 3. playwright --list ordered equality ------------------------------------

const listRun = spawnSync('npx', ['playwright', 'test', '--list'], {
  cwd: ROOT,
  encoding: 'utf8',
  shell: process.platform === 'win32',
});
if (listRun.status !== 0) {
  fail(`playwright --list exited with status ${listRun.status}`);
} else {
  const titles = [];
  for (const line of (listRun.stdout ?? '').split('\n')) {
    const marker = line.lastIndexOf('›');
    if (marker === -1) continue;
    // After the LAST '›' so describe-chain prefixes never pollute the title.
    const title = line.slice(marker + 1).trim();
    if (title) titles.push(title);
  }
  const seen = new Set();
  for (const title of titles) {
    if (seen.has(title)) fail(`duplicate listed test title ${title}`);
    seen.add(title);
  }
  if (titles.length !== 24) {
    fail(`playwright --list must yield exactly 24 tests, found ${titles.length}`);
  }
  // Ordered equality with the CSV browser row order (B1-R1 contract):
  // swapping ANY two node titles must fail here.
  for (let i = 0; i < Math.max(titles.length, browserIds.length); i += 1) {
    if (titles[i] !== browserIds[i]) {
      fail(
        `listed order diverges from inventory browser row order at position ${i + 1}: ` +
          `expected ${browserIds[i] ?? '<missing>'}, found ${titles[i] ?? '<missing>'}`,
      );
      break;
    }
  }
  console.log(`[3] playwright --list: exactly 24 titles, ordered-equal with the inventory browser rows — OK`);
}

// --- 4. Forbidden markers + config invariants --------------------------------

const FORBIDDEN_MARKERS = [
  [/test\.only\b/, 'test.only'],
  [/test\.skip\b/, 'test.skip'],
  [/test\.fixme\b/, 'test.fixme'],
  [/describe\.only\b/, 'describe.only'],
  [/describe\.skip\b/, 'describe.skip'],
  [/describe\.fixme\b/, 'describe.fixme'],
  [/\bskip\(/, 'skip('],
  [/\bfixme\(/, 'fixme('],
  [/\bxit\(/, 'xit('],
  [/\bxdescribe\(/, 'xdescribe('],
  // B1-R1: fixed sleeps are banned — waits must be bounded conditions.
  [/\bwaitForTimeout\b/, 'waitForTimeout'],
  // B1-R2: the generic network-quiet wait is banned — R12 must settle on
  // real application conditions instead (host-mode-dependent risk under
  // the Vite dev host's HMR socket).
  [/\bnetworkidle\b/, 'networkidle'],
];

function listSourceFiles(dir) {
  const out = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === 'node_modules' || entry.name === 'artifacts') continue;
      out.push(...listSourceFiles(full));
    } else if (/\.(ts|mjs|json|md)$/.test(entry.name)) {
      out.push(full);
    }
  }
  return out;
}

const sourceFiles = [
  ...listSourceFiles(join(ROOT, 'tests')),
  ...listSourceFiles(join(ROOT, 'src')),
  ...listSourceFiles(join(ROOT, 'tools')).filter(
    // The validator itself must NAME the forbidden markers to detect them;
    // it is infrastructure, not journey code, so it is exempt from its own
    // marker scan (but not from the UTF-8 scan below).
    (file) => !file.endsWith('validate-static.mjs'),
  ),
  join(ROOT, 'playwright.config.ts'),
];
for (const file of sourceFiles) {
  const text = readFileSync(file, 'utf8');
  for (const [pattern, label] of FORBIDDEN_MARKERS) {
    if (pattern.test(text)) {
      fail(`forbidden marker ${label} found in ${relative(ROOT, file)}`);
    }
  }
}

const configText = readFileSync(join(ROOT, 'playwright.config.ts'), 'utf8');

/**
 * Strip JS comments so textual invariants cannot be defeated by commenting
 * the contract line out (mutation-tested at freeze). `//` is only stripped
 * when preceded by whitespace/line-start so http(s):// literals survive.
 */
function stripComments(text) {
  return text
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|\s)\/\/[^\n]*/g, '$1');
}

const configCode = stripComments(configText);
const CONFIG_INVARIANTS = [
  [/fullyParallel:\s*false/, 'fullyParallel: false'],
  [/workers:\s*1\b/, 'workers: 1'],
  [/retries:\s*0\b/, 'retries: 0'],
  // B1-R1 fail-stop contract.
  [/maxFailures:\s*1\b/, 'maxFailures: 1'],
  [/trace:\s*'off'/, "trace: 'off'"],
  [/screenshot:\s*'off'/, "screenshot: 'off'"],
  [/video:\s*'off'/, "video: 'off'"],
];
for (const [pattern, label] of CONFIG_INVARIANTS) {
  if (!pattern.test(configCode)) fail(`playwright.config.ts is missing frozen invariant ${label}`);
}

// B1-R1 journey-structure contracts:
//  (a) exactly ONE spec file, named forgot-reset.spec.ts — reintroducing a
//      second spec (filename-order dependency) fails here;
//  (b) the spec declares the single outer serial mode — removing it fails.
const specFiles = listSourceFiles(join(ROOT, 'tests')).filter((file) => file.endsWith('.spec.ts'));
const specNames = specFiles.map((file) => relative(join(ROOT, 'tests'), file.replace(/\\/g, '/')));
if (specNames.length !== 1 || specNames[0] !== 'forgot-reset.spec.ts') {
  fail(
    `tests/ must contain exactly one spec file named forgot-reset.spec.ts (found: ${
      specNames.length === 0 ? '<none>' : specNames.join(', ')
    })`,
  );
}
const specText = specFiles.length === 1 ? readFileSync(specFiles[0], 'utf8') : '';
if (!/test\.describe\.configure\(\{\s*mode:\s*'serial'\s*\}\)/.test(stripComments(specText))) {
  fail('forgot-reset.spec.ts must declare test.describe.configure({ mode: \'serial\' })');
}

// B1-R2: the R12 test must settle on REAL application conditions before the
// leak sweep — (a) exact pathname, (b) empty hash, (c) visible-and-
// interactable #newPassword. Removing any of these must fail here.
function testRegion(text, testId) {
  const start = text.indexOf(`test('${testId}'`);
  if (start === -1) return null;
  const next = text.indexOf("test('", start + 1);
  return text.slice(start, next === -1 ? undefined : next);
}
const r12Region = testRegion(specText, 'R12');
if (r12Region === null) {
  fail('forgot-reset.spec.ts must contain the R12 test');
} else {
  if (!/window\.location\.pathname === '\/reset-password'/.test(r12Region)) {
    fail("R12 must wait for the application-settle pathname condition (pathname === '/reset-password')");
  }
  if (!/window\.location\.hash === ''/.test(r12Region)) {
    fail("R12 must wait for the empty-hash condition (location.hash === '')");
  }
  if (!/locator\('#newPassword'\)/.test(r12Region) || !/toBeEditable\(\)/.test(r12Region)) {
    fail('R12 must wait for the reset form #newPassword to be visible and interactable');
  }
}

// B1-R3: semantic neutrality spec contracts — F3/F4/F5 must all capture
// through the canonicalizer, F4 AND F5 must assert canonical equality
// against the F3 anchor (deleting the F5 assertion must fail here).
for (const nodeId of ['F3', 'F4', 'F5']) {
  const region = testRegion(specText, nodeId);
  if (region === null) {
    fail(`forgot-reset.spec.ts must contain the ${nodeId} test`);
    continue;
  }
  if (!/captureForgotFingerprint\(\s*page\s*,\s*'F[345]'\s*\)/.test(region)) {
    fail(`${nodeId} must capture its forgot-password response through the canonicalizer (captureForgotFingerprint)`);
  }
  if (!/pinnedMessageMatches\(/.test(region)) {
    fail(`${nodeId} must assert the pinned neutral-constant predicate (pinnedMessageMatches)`);
  }
}
const f4Region = testRegion(specText, 'F4');
if (f4Region !== null && !/sameFingerprint\(\s*f3\s*,\s*f4\s*\)/.test(f4Region)) {
  fail('F4 must assert canonical response equality against F3 (sameFingerprint(f3, f4))');
}
const f5Region = testRegion(specText, 'F5');
if (f5Region !== null && !/sameFingerprint\(\s*f3\s*,\s*f5\s*\)/.test(f5Region)) {
  fail('F5 must assert canonical response equality against F3 (sameFingerprint(f3, f5)) — B1-R3 contract');
}

// B1-R3: the real canonicalizer module must exist and pin the contract
// surface; generic ignore mechanisms (key deletion / key filtering) are
// banned inside it — only the explicit timestamp sentinel substitution is
// permitted (see tools/check-neutrality.mjs for the executable contract).
const corePath = join(ROOT, 'src', 'neutrality-core.ts');
try {
  const coreText = readFileSync(corePath, 'utf8');
  const coreCode = stripComments(coreText);
  for (const marker of ['NEUTRAL_ENVELOPE_KEYS', 'NEUTRAL_MESSAGE_CONSTANT', 'TIMESTAMP_SENTINEL', 'canonicalizeNeutralEnvelope']) {
    if (!coreCode.includes(marker)) {
      fail(`src/neutrality-core.ts must define/pin ${marker}`);
    }
  }
  if (/\bdelete\s/.test(coreCode)) {
    fail('src/neutrality-core.ts must not delete keys (generic ignore banned; only the explicit timestamp sentinel substitution is allowed)');
  }
  if (/\.filter\s*\(/.test(coreCode)) {
    fail('src/neutrality-core.ts must not filter key sets (generic ignore banned; the exact-key-set membership check is explicit)');
  }
} catch {
  fail('src/neutrality-core.ts must exist (B1-R3 canonicalizer module)');
}
console.log('[4] journey contracts (single serial spec, maxFailures:1, no waitForTimeout, R12 app-settle conditions, no networkidle) + B1-R3 neutrality spec/core contracts + marker scan + config invariants — OK');

// --- 5. EOL portability contract (B1-R2) -------------------------------------

const gitattributesPath = join(ROOT, '.gitattributes');
let gitattributesText = '';
try {
  gitattributesText = readFileSync(gitattributesPath, 'utf8');
} catch {
  fail('j1h2b-forgot-reset/.gitattributes must exist (EOL portability contract)');
}
if (!/^\s*\*\s+text=auto eol=lf\s*$/m.test(gitattributesText)) {
  fail(".gitattributes must contain the rule '* text=auto eol=lf'");
}
if (/eol\s*=\s*crlf/i.test(gitattributesText)) {
  fail('.gitattributes must not contain any eol=crlf rule');
}
console.log("[5] EOL portability: .gitattributes present with '* text=auto eol=lf' and no crlf rule — OK");

// --- 6. UTF-8 / no BOM / no CR -----------------------------------------------

function listAllFiles(dir) {
  const out = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === 'node_modules' || entry.name === 'artifacts' || entry.name === '.git') continue;
      out.push(...listAllFiles(full));
    } else {
      out.push(full);
    }
  }
  return out;
}

const allFiles = listAllFiles(ROOT).filter(
  (file) => !file.replace(/\\/g, '/').includes('/node_modules/'),
);
for (const file of allFiles) {
  const bytes = readFileSync(file);
  if (bytes.length >= 3 && bytes[0] === 0xef && bytes[1] === 0xbb && bytes[2] === 0xbf) {
    fail(`BOM found in ${relative(ROOT, file)}`);
  }
  if (bytes.includes(0x0d)) {
    fail(`CR byte found in ${relative(ROOT, file)}`);
  }
  try {
    new TextDecoder('utf-8', { fatal: true }).decode(bytes);
  } catch {
    fail(`file is not strict UTF-8: ${relative(ROOT, file)}`);
  }
}
console.log(`[6] UTF-8 / no-BOM / no-CR over ${allFiles.length} harness files — OK`);

// --- 7. Executable neutrality contract check (B1-R3) --------------------------

const neutralityCheck = spawnSync('node', ['tools/check-neutrality.mjs'], {
  cwd: ROOT,
  encoding: 'utf8',
});
if (neutralityCheck.error || neutralityCheck.status !== 0) {
  fail('executable neutrality contract check (tools/check-neutrality.mjs) must pass');
  if (neutralityCheck.stdout) process.stdout.write(neutralityCheck.stdout);
  if (neutralityCheck.stderr) process.stderr.write(neutralityCheck.stderr);
} else {
  process.stdout.write(`  ${neutralityCheck.stdout.trim()}\n`);
}
console.log('[7] executable neutrality contract check over the real canonicalizer — OK');

// --- verdict ------------------------------------------------------------------

if (failures.length > 0) {
  console.error('\nSTATIC GATE FAILED:');
  for (const message of failures) console.error(` - ${message}`);
  process.exit(1);
}
console.log('\nSTATIC GATE PASSED (7/7 steps).');
