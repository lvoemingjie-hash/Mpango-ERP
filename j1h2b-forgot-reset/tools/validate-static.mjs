#!/usr/bin/env node
/**
 * Static gate for the frozen j1h2b harness (task directive: 静态门禁).
 *
 * Pure static validation — reads committed data and source only, never reads
 * credential env values, never starts any product runtime. Steps:
 *   1. Inventory CSV strict parse: 29 data rows x 15 columns,
 *      24 browser + 5 non-browser nodes.
 *   2. Registry cross-check: node-registry.json matches the CSV sets;
 *      RT0 stays BLOCKED_BY_H2_C.
 *   3. `playwright test --list` yields exactly the 24 browser IDs (set
 *      equality, no duplicates, no unregistered nodes).
 *   4. Forbidden markers: no test.only/test.skip/test.fixme (and friends)
 *      anywhere in tests/ or src/; frozen config invariants literal-checked
 *      (fullyParallel:false, workers:1, retries:0, trace/screenshot/video off).
 *   5. UTF-8 (strict decode) + no BOM + no CR for every committed harness file.
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

// --- 3. playwright --list set equality --------------------------------------

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
    const marker = line.indexOf('›');
    if (marker === -1) continue;
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
  for (const id of seen) {
    if (!csvBrowserSet.has(id)) fail(`listed test ${id} is not a registered browser node`);
  }
  for (const id of csvBrowserSet) {
    if (!seen.has(id)) fail(`browser node ${id} has no listed test`);
  }
  console.log(`[3] playwright --list: exactly 24 titles, set-equal with the browser inventory — OK`);
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
const CONFIG_INVARIANTS = [
  [/fullyParallel:\s*false/, 'fullyParallel: false'],
  [/workers:\s*1\b/, 'workers: 1'],
  [/retries:\s*0\b/, 'retries: 0'],
  [/trace:\s*'off'/, "trace: 'off'"],
  [/screenshot:\s*'off'/, "screenshot: 'off'"],
  [/video:\s*'off'/, "video: 'off'"],
];
for (const [pattern, label] of CONFIG_INVARIANTS) {
  if (!pattern.test(configText)) fail(`playwright.config.ts is missing frozen invariant ${label}`);
}
console.log('[4] forbidden-marker scan + frozen config invariants — OK');

// --- 5. UTF-8 / no BOM / no CR -----------------------------------------------

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
console.log(`[5] UTF-8 / no-BOM / no-CR over ${allFiles.length} harness files — OK`);

// --- verdict ------------------------------------------------------------------

if (failures.length > 0) {
  console.error('\nSTATIC GATE FAILED:');
  for (const message of failures) console.error(` - ${message}`);
  process.exit(1);
}
console.log('\nSTATIC GATE PASSED (5/5 steps).');
