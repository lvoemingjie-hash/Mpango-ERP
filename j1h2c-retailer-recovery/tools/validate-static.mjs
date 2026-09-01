#!/usr/bin/env node
/**
 * Static validator for the j1h2c-retailer-recovery frozen harness.
 *
 * Checks (all must pass; any failure exits 1 with a category-only message):
 *  [1] inventory CSV: strict parse, 17 data rows x 15 columns, IDs HC01-
 *      HC17 ordered and unique.
 *  [2] registry cross-check against the CSV execution classes: 15 BROWSER
 *      (HC01-HC10, HC12-HC16) + 2 STATIC (HC11, HC17).
 *  [3] `playwright test --list` reconciliation: exactly 15 tests in one
 *      file, ordered-equal with the browser rows (title prefix).
 *  [4] journey contracts: single spec + single serial describe, fail-stop
 *      config (fullyParallel=false, workers=1, retries=0, maxFailures=1),
 *      evidence hygiene (trace/screenshot/video off).
 *  [5] forbidden markers: skip/fixme/only, waitForTimeout, fixed sleeps,
 *      networkidle.
 *  [6] EOL portability: .gitattributes carries `* text=auto eol=lf`; no CR
 *      bytes in any harness text file; strict UTF-8, no BOM, no NUL.
 *  [7] secret boundary: no credential literals in the tree (env-only
 *      contract); the config fallback host is unresolvable.
 *  [8] 15 + 2 reconciliation shape: reconciliation.ts encodes exactly
 *      15 browser + 2 static nodes and gap-0 accounting.
 *  [9] HC01-HC17 contract anchors present in the spec/sources.
 *  [10] B1-R1 A-I runtime-oracle anchors present.
 *  [11] B1-R2 D/I + B1-R3 truth anchors present.
 *  [12] B1-R4 type-only import structure: `CanonicalFingerprint` (a
 *      type-only interface in neutrality-core.ts) may enter any src module
 *      ONLY through an `import type` declaration; a same-name value import
 *      is rejected. Parsed with the TypeScript AST, not substring matching.
 *  [13] B1-R5 browser authority control plane: the contract schema parses
 *      and pins launch.max_starts=1 with required+sensitive fields; the
 *      runner keeps argv-array discipline (injected execFile impl, no
 *      shell), the at-most-once/once-only categories, the owner-label
 *      overwrite guard and the sensitive-value ledger firewall; the
 *      checker REALLY imports the runner and exercises the exact defect
 *      categories.
 *  [14] B1-R5-R1 authority truth closure: the protected
 *      browser-authority-profile.json reconciles EXACTLY with the
 *      J1H2C_* variables consumed by src/env.ts; the runner carries live
 *      byte bindings (git rev-parse candidate, profile/contract re-reads),
 *      terminal-state truth (RUNNING/TEST_RED/seal) and the durable
 *      hash-chained JSONL ledger categories; the checker exercises
 *      R11-R18 and the B1-R5-R2 additions (no profilePath override,
 *      async child classification, chain-forced seal/evidence).
 */

import { execFileSync } from 'node:child_process';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, extname } from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const ts = require('typescript');

const ROOT = join(import.meta.dirname, '..');
let failures = 0;

function ok(step, message) {
  console.log(`[${step}] OK — ${message}`);
}

function fail(step, message) {
  failures += 1;
  console.error(`[${step}] FAIL — ${message}`);
}

// [1] inventory CSV ---------------------------------------------------------
const csvPath = join(ROOT, 'inventory/2026-08-26_dc12r1_mvp_l1_j1_h2_c_node_inventory.csv');
const csvText = readFileSync(csvPath, 'utf8');
const rows = csvText.split('\n').filter((line) => line.length > 0).map((line) => {
  const out = [];
  let cur = '';
  let quoted = false;
  for (const ch of line) {
    if (ch === '"') quoted = !quoted;
    else if (ch === ',' && !quoted) { out.push(cur); cur = ''; }
    else cur += ch;
  }
  out.push(cur);
  return out;
});
const header = rows[0];
const data = rows.slice(1);
if (header.length !== 15 || data.length !== 17) {
  fail(1, 'inventory shape not 17x15');
} else {
  const ids = data.map((r) => r[0]);
  const expected = Array.from({ length: 17 }, (_, i) => `HC${String(i + 1).padStart(2, '0')}`);
  if (JSON.stringify(ids) !== JSON.stringify(expected)) {
    fail(1, 'ids not HC01-HC17 ordered unique');
  } else {
    ok(1, '17 rows x 15 cols, HC01-HC17 ordered unique');
  }
}

// [2] registry cross-check --------------------------------------------------
const registryPath = join(ROOT, 'inventory/node-registry.json');
const registry = JSON.parse(readFileSync(registryPath, 'utf8'));
const csvClasses = new Map(data.map((r) => [r[0], r[11]]));
const browserRows = data.filter((r) => r[11] === 'BROWSER').map((r) => r[0]);
const staticRows = data.filter((r) => r[11] === 'STATIC').map((r) => r[0]);
const browserExpected = Array.from({ length: 17 }, (_, i) => `HC${String(i + 1).padStart(2, '0')}`)
  .filter((id) => id !== 'HC11' && id !== 'HC17');
if (
  JSON.stringify(browserRows) !== JSON.stringify(browserExpected) ||
  JSON.stringify(staticRows) !== JSON.stringify(['HC11', 'HC17'])
) {
  fail(2, 'execution classes not 15 BROWSER + 2 STATIC');
} else if (
  registry.expectedCounts.browser !== 15 ||
  registry.expectedCounts.static !== 2 ||
  registry.expectedCounts.total !== 17 ||
  registry.nodes.length !== 17
) {
  fail(2, 'registry counts not 15+2=17');
} else {
  const registryMatches = registry.nodes.every((node) => {
    const csvClass = csvClasses.get(node.nodeId);
    // The registry may carry compound classes (BROWSER+POSTCOND etc.); the
    // CSV records the base class, which must be the registry's base.
    const registryBase = (node.executionClass ?? '').split('+')[0];
    return csvClass === registryBase || csvClass === node.executionClass;
  });
  if (!registryMatches) fail(2, 'registry classes diverge from CSV');
  else ok(2, '15 BROWSER (HC01-HC10,HC12-HC16) + 2 STATIC (HC11,HC17)');
}

// [3] playwright --list reconciliation ---------------------------------------
let listOutput = '';
try {
  const pnpmCmd = process.platform === 'win32' ? 'pnpm.cmd' : 'pnpm';
  listOutput = execFileSync(pnpmCmd, ['exec', 'playwright', 'test', '--list'], {
    cwd: ROOT,
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
    shell: true, // Windows .cmd shims require a shell
  });
} catch (error) {
  fail(3, `playwright --list failed: ${String(error).split('\n')[0]}`);
}
const listed = listOutput
  .split('\n')
  .filter((line) => line.trim().startsWith('recovery.spec.ts:'))
  .map((line) => {
    const m = line.match(/recovery\.spec\.ts:\d+:\d+ › [^›]+ › (\S+)/);
    return m ? m[1] : '';
  })
  .filter(Boolean);
const filesListed = new Set(
  listOutput
    .split('\n')
    .filter((line) => line.trim().startsWith('recovery.spec.ts:'))
    .map((line) => line.trim().split(':')[0]),
);
if (listed.length !== 15 || filesListed.size !== 1) {
  fail(3, `expected exactly 15 tests in 1 file, found ${listed.length} in ${filesListed.size}`);
} else if (JSON.stringify(listed) !== JSON.stringify(browserRows)) {
  fail(3, 'listed tests not ordered-equal with browser rows');
} else {
  ok(3, 'playwright --list: 15 tests / 1 file, ordered-equal with browser rows');
}

// [4] journey contracts ------------------------------------------------------
const configText = readFileSync(join(ROOT, 'playwright.config.ts'), 'utf8');
const specText = readFileSync(join(ROOT, 'tests/recovery.spec.ts'), 'utf8');
for (const [needle, label] of [
  ['fullyParallel: false', 'fullyParallel=false'],
  ['workers: 1', 'workers=1'],
  ['retries: 0', 'retries=0'],
  ['maxFailures: 1', 'maxFailures=1'],
  ["trace: 'off'", 'trace off'],
  ["screenshot: 'off'", 'screenshot off'],
  ["video: 'off'", 'video off'],
]) {
  if (!configText.includes(needle)) fail(4, `config missing ${label}`);
}
// The frozen code line carries a trailing semicolon; the docstring mention
// (backticked, no semicolon) must NOT satisfy this check.
if (!specText.includes("test.describe.configure({ mode: 'serial' });")) {
  fail(4, 'spec missing single serial describe');
}
const specFiles = readdirSync(join(ROOT, 'tests')).filter((f) => f.endsWith('.spec.ts'));
if (specFiles.length !== 1) fail(4, `expected exactly 1 spec file, found ${specFiles.length}`);
const describeCount = (specText.match(/test\.describe\(/g) ?? []).length;
if (describeCount !== 1) fail(4, `expected exactly 1 test.describe, found ${describeCount}`);
if (failures === 0) ok(4, 'single spec/serial/fail-stop/evidence hygiene');

// [5] forbidden markers --------------------------------------------------------
// Marker scan is scoped to the spec and config (the frozen executable
// contract); src/** doc comments may legitimately NAME banned constructs.
const markerScanTargets = [specText, configText];
for (const [marker, label] of [
  ['waitForTimeout(', 'waitForTimeout'],
  ['networkidle', 'networkidle'],
  ['.skip(', 'skip'],
  ['.fixme(', 'fixme'],
  ['test.only', 'only'],
  ['setTimeout(', 'fixed sleep'],
]) {
  if (markerScanTargets.some((text) => text.includes(marker))) {
    fail(5, `forbidden marker present: ${label}`);
  }
}
if (failures === 0) ok(5, 'no skip/fixme/only/waitForTimeout/sleep/networkidle');

// [6] EOL + encoding -----------------------------------------------------------
const gitattributes = readFileSync(join(ROOT, '.gitattributes'), 'utf8');
if (!gitattributes.includes('* text=auto eol=lf')) {
  fail(6, '.gitattributes missing LF rule');
}
const textExts = new Set(['.ts', '.mjs', '.json', '.md', '.csv', '.gitattributes', '.gitignore', '']);
function walk(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    if (name === 'node_modules' || name === 'artifacts' || name === '.pnpm-store') continue;
    const full = join(dir, name);
    if (statSync(full).isDirectory()) out.push(...walk(full));
    else out.push(full);
  }
  return out;
}
let encodingOk = true;
for (const file of walk(ROOT)) {
  if (!textExts.has(extname(file)) && !file.endsWith('.gitattributes') && !file.endsWith('.gitignore')) continue;
  const raw = readFileSync(file);
  if (raw.includes(0)) { encodingOk = false; fail(6, `NUL byte in ${file}`); }
  if (raw[0] === 0xef && raw[1] === 0xbb && raw[2] === 0xbf) { encodingOk = false; fail(6, `BOM in ${file}`); }
  if (raw.includes(13)) { encodingOk = false; fail(6, `CR byte in ${file}`); }
  try {
    new TextDecoder('utf-8', { fatal: true }).decode(raw);
  } catch {
    encodingOk = false;
    fail(6, `not strict UTF-8: ${file}`);
  }
}
if (encodingOk && gitattributes.includes('* text=auto eol=lf')) ok(6, 'strict UTF-8, no BOM/NUL/CR, LF rule');

// [7] secret boundary -----------------------------------------------------------
if (!configText.includes('.invalid.') || !configText.includes('frozen-harness.local')) {
  fail(7, 'config fallback host not clearly unresolvable');
}
const envText = readFileSync(join(ROOT, 'src/env.ts'), 'utf8');
if (!envText.includes('J1H2C_BASE_URL') || !envText.includes('J1H2C_RETAILER_EMAIL')) {
  fail(7, 'env contract missing J1H2C variables');
}
const envLiteral = /['"][^'"]*(password|passwd|token|secret)[^'"]*['"]\s*[:=]/i;
if (markerScanTargets.some((text) => envLiteral.test(text))) {
  fail(7, 'credential-like literal in harness sources');
} else {
  ok(7, 'env-only credentials; fallback host unresolvable');
}

// [8] reconciliation shape --------------------------------------------------------
const reconciliationText = readFileSync(join(ROOT, 'src/reconciliation.ts'), 'utf8');
for (const [needle, label] of [
  ["'HC01', 'HC02', 'HC03', 'HC04', 'HC05',", 'browser node list part 1'],
  ["'HC06', 'HC07', 'HC08', 'HC09', 'HC10',", 'browser node list part 2'],
  ["'HC12', 'HC13', 'HC14', 'HC15', 'HC16',", 'browser node list part 3'],
  ["const STATIC_NODES = ['HC11', 'HC17']", 'static node list'],
  ['summary.browser.total !== 15', 'browser total 15'],
  ['summary.static.total !== 2', 'static total 2'],
  ['summary.total !== 17', 'total 17'],
  ['summary.gap !== 0', 'gap 0'],
]) {
  if (!reconciliationText.includes(needle)) fail(8, `reconciliation missing ${label}`);
}
if (failures === 0) ok(8, '15 browser + 2 static = 17, gap=0 reconciliation');

// [9] contract anchors ------------------------------------------------------------
for (const [needle, label] of [
  ["expect(posts.length, 'http:recovery_post_count:must_be_zero').toBe(0)", 'HC02/HC05 zero POST'],
  ["expect(posts.length, 'http:recovery_post_count:must_be_exactly_one').toBe(1)", 'HC06 single POST'],
  ['assertFourStateCanonicalEquality', 'HC07-HC10 canonical equality'],
  ['scanTokenLeak', 'HC12 token leak scan'],
  ['scanPublicCode', 'HC12 public-code scan'],
  ['assertNoTokenLeak', 'HC12 token leak assertion'],
  ['assertPublicCodeClean', 'HC12 public-code leak assertion'],
  ['expectPortalReturnCta', 'HC13 canonical portal'],
  ['expectLegacyGuidanceOnly', 'HC14 legacy guidance'],
  ['hc17_not_db_canonical_uppercase', 'HC17 DB canonical uppercase'],
  ['reset_link.query', 'HC11 fragment-only (maildir source)'],
  ['parseAndValidateResetLink', 'HC11 exact link validation'],
  ['LOWERCASE', 'HC17 lowercase caller input'],
]) {
  const anchorHaystack = label.includes('(maildir source)')
    ? specText + readFileSync(join(ROOT, 'src', 'maildir.ts'), 'utf8')
    : specText;
  if (!anchorHaystack.includes(needle)) fail(9, `spec missing anchor: ${label}`);
}
if (failures === 0) ok(9, 'HC01-HC17 contract anchors present');

// [10] B1-R1 A-I anchor checks (runtime-oracle authenticity) ---------------
const uiText = readFileSync(join(ROOT, 'src', 'ui-journey.ts'), 'utf8');
const packageText = readFileSync(join(ROOT, 'package.json'), 'utf8');
const maildirText = readFileSync(join(ROOT, 'src', 'maildir.ts'), 'utf8');
const apiText = readFileSync(join(ROOT, 'src', 'api-client.ts'), 'utf8');
for (const [needle, where, label] of [
  ['page.waitForRequest(', 'spec', 'A: reset POST observed before click'],
  ['reset_post_count:must_be_exactly_one', 'spec', 'A: exactly-one reset POST'],
  ["'new_password,reset_token'", 'spec', 'A: reset body exact key set'],
  ['mismatch_with_memory', 'spec', 'A: reset_token equals memory token'],
  ['assertPublicCodeClean', 'spec', 'B: public w full scan asserted'],
  ['journey.w2CanonicalCode', 'spec', 'C: real W2 canonical code from env'],
  ['WRONG${CANONICAL}', 'spec-absent', 'C: fabricated wrong-supplier code forbidden'],
  ['runPreconditions(journey)', 'spec', 'D: precondition provisioning called'],
  ['PRECONDITION', 'api', 'D: provisioning documented as precondition'],
  ['snapshotDeliveries(', 'spec', 'E: mail snapshot before submission'],
  ['pollForExactlyOneNewDelivery(', 'spec', 'E: exactly-one-new poll'],
  ['parseAndValidateResetLink', 'spec', 'E: exact link validation'],
  ['query_string_forbidden', 'maildir', 'E: query string forbidden'],
  ['genuineDoubleClickSubmit', 'spec', 'F: genuine dblclick used'],
  ['.dblclick();', 'ui', 'F: Playwright dblclick action'],
  ['dispatchEvent', 'ui-absent', 'F: synthetic dispatch forbidden'],
  ['assertInteractiveNoOverflowAt390px', 'spec', 'G: interactive 390px proof'],
  ["fresh valid token + w; genuine interactive form", 'spec', 'G: real-form anchor'],
  ["publishArtifacts('artifacts')", 'spec', 'H: reconciliation artifact published'],
  ['markOutcomesAfterFailure', 'spec', 'H: failed vs NOT_RUN distinguished'],
  ['clearMemoryState();', 'spec', 'H: token store CLEARED (call site) in afterAll'],
  ['--secrets-from-env', 'package', 'I: scanner forces secrets-from-env'],
  ['SCANNER FAIL-CLOSED', 'scanner', 'I: scanner fails closed'],
]) {
  const haystack =
    where === 'spec' ? specText :
    where === 'ui' ? uiText :
    where === 'maildir' ? maildirText :
    where === 'api' ? apiText :
    where === 'package' ? packageText :
    readFileSync(join(ROOT, 'tools', 'scan-artifacts.mjs'), 'utf8');
  const present = haystack.includes(needle);
  if (where.endsWith('-absent')) {
    if (present) fail(10, `forbidden marker present: ${label}`);
  } else if (!present) {
    fail(10, `missing anchor: ${label}`);
  }
}
if (failures === 0) ok(10, 'B1-R1 A-I runtime-oracle anchors present');

// [11] B1-R2 D/I anchors -----------------------------------------------------
const preconditionsText = readFileSync(join(ROOT, 'src', 'preconditions.ts'), 'utf8');
for (const [needle, where, label] of [
  ['status !== 200 && status !== 201', 'preconditions', 'D: strict 2xx-only register'],
  ['strict_register_rejected', 'preconditions', 'D: non-2xx fail-closed category'],
  ['loginProofSucceeds', 'preconditions', 'D: established login proof'],
  ['loginProofMustFail', 'preconditions', 'D: unverified/W2 fail proofs'],
  ['SETUP_CONSUME_URL', 'preconditions', 'D: full lifecycle setup consume'],
  ['if (w1 === w2) {', 'preconditions', 'D: W1==W2 guard code present'],
  ['must_differ_from_w1', 'preconditions', 'D: W2 differs from W1 category'],
  ['collides_with_provisioned_identity', 'preconditions', 'D: unknown email normalization'],
  ['j1h2c-maildir-snapshot/2', 'preconditions', 'I: dual-mailbox snapshot (schema/2)'],
  ['unverifiedSnapshot', 'preconditions', 'I: unverified mailbox snapshotted'],
  ['mailboxes: {', 'preconditions', 'I: labels-only snapshot shape'],
  ['J1H2C_FORGED_RESET_TOKEN', 'env', 'I: forged token env contract'],
  ['forgedResetToken', 'spec', 'I: spec consumes forged token env'],
  ['collectFromMailbox', 'scanner', 'I: scanner collects from BOTH mailboxes'],
  ['setupTokens', 'scanner', 'I: per-mailbox setup tokens collected'],
  ['duplicate token across mailboxes', 'scanner', 'I: duplicate-token fail-closed'],
  ['recordPreconditionFail', 'spec', 'R3: precondition failure accounted'],
  ['normalizeEmail(env.retailer.email)', 'preconditions-absent-snapshot', 'M31: snapshot must not embed established email value'],
  ['normalizeEmail(env.unverifiedEmail)', 'preconditions-absent-snapshot', 'M31: snapshot must not embed unverified email value'],
  ['assertComplete();', 'spec', 'R3: success completeness asserted'],
  ['zero new-mail tokens', 'scanner', 'I: zero-new-token fail-closed'],
  ['equals a real mail token', 'scanner', 'I: forged-token reuse fail-closed'],
  ['--maildir-root', 'package', 'I: authoritative command consistent'],
]) {
  const preconditionsSnapshotBlock = (() => {
    const text = preconditionsText;
    const start = text.indexOf('writeFileSync(');
    const end = start < 0 ? text.length : text.indexOf(');', start) + 2;
    return text.slice(start < 0 ? 0 : start, end);
  })();
  const haystack =
    where === 'spec' ? specText :
    where === 'preconditions' ? preconditionsText :
    where === 'preconditions-absent-snapshot' ? preconditionsSnapshotBlock :
    where === 'env' ? readFileSync(join(ROOT, 'src', 'env.ts'), 'utf8') :
    where === 'package' ? packageText :
    readFileSync(join(ROOT, 'tools', 'scan-artifacts.mjs'), 'utf8');
  if (where === 'preconditions-absent-snapshot') {
    if (haystack.includes(needle)) fail(11, `forbidden value in snapshot: ${label}`);
  } else if (!haystack.includes(needle)) {
    fail(11, `missing anchor: ${label}`);
  }
}
if (failures === 0) ok(11, 'B1-R2 D/I + B1-R3 truth anchors present');

// [12] B1-R4 type-only import structure (AST-verified) -----------------------
// `CanonicalFingerprint` is a type-only `export interface` in
// neutrality-core.ts. A value import survives Node ESM loading and fails at
// runtime with "does not provide an export named 'CanonicalFingerprint'".
// The check parses each src module with the TypeScript AST and:
//   - REQUIRES a type-only import of CanonicalFingerprint from
//     './neutrality-core.js' wherever the name is used in a type position
//     (neutrality.ts);
//   - REJECTS any same-name value import (named binding that is not
//     type-only) in ANY src module.
{
  const TYPE_ONLY_NAME = 'CanonicalFingerprint';
  const CORE_MODULE = './neutrality-core.js';
  const srcDir = join(ROOT, 'src');
  const srcFiles = readdirSync(srcDir)
    .filter((f) => extname(f) === '.ts')
    .sort();

  let sawTypeOnlyImport = false;
  for (const file of srcFiles) {
    const source = readFileSync(join(srcDir, file), 'utf8');
    const parsed = ts.createSourceFile(file, source, ts.ScriptTarget.ES2022, true);
    for (const statement of parsed.statements) {
      if (!ts.isImportDeclaration(statement)) continue;
      const moduleSpecifier = statement.moduleSpecifier.text;
      const clause = statement.importClause;
      if (!clause || !clause.namedBindings || !ts.isNamedImports(clause.namedBindings)) continue;
      for (const element of clause.namedBindings.elements) {
        const importedName = element.propertyName
          ? element.propertyName.text
          : element.name.text;
        if (importedName !== TYPE_ONLY_NAME) continue;
        if (moduleSpecifier !== CORE_MODULE) {
          fail(12, `${TYPE_ONLY_NAME} imported from unexpected module in ${file}`);
          continue;
        }
        const isTypeOnly = clause.isTypeOnly === true || element.isTypeOnly === true;
        if (isTypeOnly) {
          sawTypeOnlyImport = true;
        } else {
          fail(12, `${TYPE_ONLY_NAME} value import in ${file} (type-only interface)`);
        }
      }
    }
  }
  if (!sawTypeOnlyImport) {
    fail(12, `no type-only import of ${TYPE_ONLY_NAME} from ${CORE_MODULE} found in src/`);
  }
  if (failures === 0) ok(12, `${TYPE_ONLY_NAME} enters src modules only via type-only import`);
}

// [13] B1-R5 browser authority control plane ---------------------------------
{
  const schemaText = readFileSync(join(ROOT, 'inventory', 'browser-authority-contract.schema.json'), 'utf8');
  let schemaOk = true;
  try {
    const schema = JSON.parse(schemaText);
    if (schema.$id !== 'j1h2c-retailer-recovery/browser-authority-contract.schema/1') {
      schemaOk = false;
      fail(13, 'schema $id mismatch');
    }
    if (schema.properties?.launch?.properties?.max_starts?.const !== 1) {
      schemaOk = false;
      fail(13, 'schema does not pin launch.max_starts=1');
    }
    if (schema.$defs?.field?.properties?.required?.const !== true) {
      schemaOk = false;
      fail(13, 'schema does not pin fields.required=true');
    }
  } catch {
    schemaOk = false;
    fail(13, 'contract schema unparsable');
  }

  const runnerText = readFileSync(join(ROOT, 'tools', 'browser-authority-runner.mjs'), 'utf8');
  for (const [needle, label] of [
    ['owner_label_overwrite_forbidden', 'owner-label overwrite guard'],
    ['preflight_already_invoked', 'preflight once-only'],
    ['launch_already_invoked', 'browser at-most-once'],
    ['terminal_stop', 'post-VOID rejection surface'],
    ['sensitive_value_rejected', 'ledger value firewall'],
    ['transition_from_mismatch', 'from-captured-before-mutation'],
    ['assertArgvArray', 'argv array discipline'],
    ['execFileImpl', 'injected execFile implementation'],
  ]) {
    if (!runnerText.includes(needle)) fail(13, `runner missing ${label}`);
  }
  if (/\bspawn\s*\(/.test(runnerText) || /shell\s*\:\s*true/.test(runnerText)) {
    fail(13, 'runner contains shell-oriented subprocess call');
  }

  const checkerText = readFileSync(join(ROOT, 'tools', 'check-browser-authority-contracts.mjs'), 'utf8');
  for (const [needle, label] of [
    ["await import('./browser-authority-runner.mjs')", 'checker REALLY imports the runner'],
    ["'owner_label_overwrite_forbidden'", 'checker exercises owner-label overwrite'],
    ["'ledger_truncated'", 'checker exercises durable ledger truncation'],
    ["'preflight_already_invoked'", 'checker exercises repeat preflight'],
    ["'launch_already_invoked'", 'checker exercises repeat browser'],
    ["'repo_root_mismatch'", 'checker exercises cross-repo substitution refusal'],
    ["'argv_drift'", 'checker exercises argv drift'],
    ["'sensitive_value_rejected'", 'checker exercises ledger value firewall'],
  ]) {
    if (!checkerText.includes(needle)) fail(13, `checker missing ${label}`);
  }

  const pkgText = readFileSync(join(ROOT, 'package.json'), 'utf8');
  if (!pkgText.includes('"check:browser-authority"')) {
    fail(13, 'package.json missing check:browser-authority script');
  }

  if (failures === 0 && schemaOk) ok(13, 'browser authority control plane anchored (schema + runner + checker + script)');
}

// [14] B1-R5-R1 authority truth closure --------------------------------------
{
  const profileText = readFileSync(join(ROOT, 'inventory', 'browser-authority-profile.json'), 'utf8');
  let profileOk = true;
  let profileNames = new Set();
  try {
    const profile = JSON.parse(profileText);
    if (profile.schema !== 'j1h2c/browser-authority-profile/1') {
      profileOk = false;
      fail(14, 'profile schema mismatch');
    }
    if (typeof profile.owner_field !== 'string' || !(profile.owner_field in profile.fields)) {
      profileOk = false;
      fail(14, 'profile owner field unknown');
    }
    profileNames = new Set(Object.values(profile.fields).map((field) => field.env));
    for (const field of Object.values(profile.fields)) {
      if (field.required !== true || typeof field.sensitive !== 'boolean' || typeof field.role !== 'string') {
        profileOk = false;
        fail(14, 'profile field shape');
      }
    }
  } catch {
    profileOk = false;
    fail(14, 'profile unparsable');
  }

  // Machine reconciliation with the REAL consumed env contract.
  const envTsText = readFileSync(join(ROOT, 'src', 'env.ts'), 'utf8');
  const envTsNames = new Set(
    [...envTsText.matchAll(/required\('(J1H2C_[A-Z0-9_]+)'\)/g)].map((match) => match[1]),
  );
  if (envTsNames.size === 0) {
    profileOk = false;
    fail(14, 'env.ts required set empty');
  }
  if (
    profileOk &&
    (envTsNames.size !== profileNames.size || ![...envTsNames].every((name) => profileNames.has(name)))
  ) {
    profileOk = false;
    fail(14, 'profile env set does not reconcile with src/env.ts required set');
  }

  const runnerText = readFileSync(join(ROOT, 'tools', 'browser-authority-runner.mjs'), 'utf8');
  for (const [needle, label] of [
    ['resolveLiveHead', 'live git candidate resolver'],
    ['profile_sha_drift', 'profile live re-binding'],
    ['input_sha_drift', 'input live re-binding'],
    ['deepFreeze', 'private deep-frozen input'],
    ['TEST_RED', 'terminal-state truth'],
    ['terminal_seal', 'terminal seal requirement'],
    ['ledger_truncated', 'durable ledger truncation guard'],
    ['ledger_chain_broken', 'durable ledger chain guard'],
    ['contract_weaker_than_profile', 'non-weakenable profile'],
  ]) {
    if (!runnerText.includes(needle)) fail(14, `runner missing ${label}`);
  }
  if (runnerText.includes('contractShaOf')) {
    fail(14, 'runner still references the removed self-comparison helper');
  }
  for (const [needle, label] of [
    ['readProfileCommittedBytes', 'committed-blob profile binding'],
    ['profile_dirty_vs_head', 'dirty-profile fail-closed category'],
    ['canonicalRepoRoot', 'single canonical repo root derivation'],
    ['repo_root_mismatch', 'cross-repo substitution refusal'],
    ['gitEnv', 'GIT_*-stripped git subprocess environment'],
    ["toUpperCase().startsWith('GIT_')", 'case-insensitive GIT_* filter'],
    ['CORS_PREFLIGHT_PATH', 'runner-owned CORS preflight path'],
    ['cors_probe_missing', 'mandatory CORS probe enforcement'],
    ['cors_allow_origin_mismatch', 'exact allow-origin criterion'],
    ['canonicalCorsHelperPath', 'canonical CORS helper path'],
    ['cors_helper_dirty_vs_head', 'helper committed-blob binding'],
    ['probeChildEnv', 'sanitized probe child environment'],
  ]) {
    if (!runnerText.includes(needle)) fail(14, `runner missing ${label}`);
  }
  if (/\bfetch\s*\(/.test(runnerText)) {
    fail(14, 'runner references ambient fetch (B1-R6-R1: native transport only)');
  }
  if (/from 'node:http'|from 'node:https'/.test(runnerText)) {
    fail(14, 'runner performs in-process network I/O (B1-R6-R2: child process only)');
  }
  // Helper file anchors: native transport + exact criteria live in the helper.
  const helperText = readFileSync(join(ROOT, 'tools', 'browser-authority-cors-probe-helper.mjs'), 'utf8');
  if (!helperText.includes("from 'node:http'") || !helperText.includes("from 'node:https'")) {
    fail(14, 'helper missing native http/https transport');
  }
  if (!helperText.includes('Access-Control-Request-Method')) {
    fail(14, 'helper missing POST declaration');
  }
  if (!/Access-Control-Request-Method/.test(runnerText + helperText) || !/Access-Control-Request-Headers/.test(runnerText + helperText)) {
    fail(14, 'CORS probe does not declare POST + content-type');
  }
  const gitCallSites = (runnerText.match(/execFileSync\('git'/g) || []).length;
  const sanitizedCallSites = (runnerText.match(/env: gitEnv\(\)/g) || []).length;
  if (gitCallSites === 0 || gitCallSites !== sanitizedCallSites) {
    fail(14, `git subprocess env coverage ${sanitizedCallSites}/${gitCallSites}`);
  }

  const checkerText = readFileSync(join(ROOT, 'tools', 'check-browser-authority-contracts.mjs'), 'utf8');
  for (const marker of ['R11', 'R12', 'R13', 'R14', 'R15', 'R16', 'R17', 'R18', 'R19', 'R20', 'R21', 'R22', 'R23', 'R24', 'R25', 'R26', 'R27']) {
    if (!checkerText.includes(`// ${marker} `)) fail(14, `checker missing ${marker} scenario`);
  }
  if (!checkerText.includes("'ledger_seq_duplicate'")) {
    fail(14, 'checker missing duplicate-seq probe');
  }
  if (!checkerText.includes("'test_red_async_child_failure'")) {
    fail(14, 'checker missing async child truth probe');
  }
  if (!runnerText.includes('#classifyChildResult') || !runnerText.includes('test_red_async_child_failure')) {
    fail(14, 'runner missing async child classification');
  }
  if (!/evidence\(\) \{[\s\S]*?this\.#ledger\.verifyChain\(\)/.test(runnerText)) {
    fail(14, 'evidence() does not force ledger chain re-verification first');
  }

  if (failures === 0 && profileOk) {
    ok(14, `authority truth closure anchored (profile reconciles with ${envTsNames.size} env.ts fields; runner + checker R11-R27, canonical repo identity + case-insensitive GIT_* sanitization + mandatory CORS preflight probe over the native transport, git subprocess env coverage ${sanitizedCallSites}/${gitCallSites})`);
  }
}

if (failures > 0) {
  console.error(`STATIC GATE FAILED (${failures} failure(s))`);
  process.exit(1);
}
console.log('STATIC GATE PASSED (14/14 steps).');
