#!/usr/bin/env node
/**
 * DC-12R1-MVP-L1-PW1-R1 test runner.
 *
 * Execution order (Phase 5):
 *   Stage 1: auth matrix, desktop only  (gate)
 *   Stage 2: phases 1-6, desktop only   (after auth green)
 *   Stage 3: auth matrix + phases, tablet + mobile (full matrix)
 *
 * Evidence (Phase 4):
 *   - Real JSON + JUnit per stage (env-var output names)
 *   - Post-generation RE-PARSE of both files; count reconciliation
 *   - PW1_R1_RESULTS.json / PW1_R1_JUNIT.xml / PW1_R1_FINDINGS.csv / MD report
 *   - Strict UTF-8 output; blocked nodes accounted separately from failures
 */
const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const WS = __dirname;
const REPORTS = path.join(WS, 'reports');
fs.mkdirSync(REPORTS, { recursive: true });

const STAGES = [
  { name: 'stage1-auth-desktop', args: ['tests/auth-matrix.spec.ts'], projects: ['desktop'] },
  { name: 'stage2-phases-desktop', args: ['tests/phase1-routes.spec.ts', 'tests/phase2-identity.spec.ts', 'tests/phase3-wholesaler.spec.ts', 'tests/phase4-retailer.spec.ts', 'tests/phase5-isolation.spec.ts', 'tests/phase6-responsive.spec.ts'], projects: ['desktop'] },
  { name: 'stage3-matrix-tablet-mobile', args: [], projects: ['tablet', 'mobile'] },
];

function runPlaywright(stage, listOnly = false) {
  const jsonOut = path.join(REPORTS, `${stage.name}.json`);
  const junitOut = path.join(REPORTS, `${stage.name}.xml`);
  const projArgs = stage.projects.flatMap(p => ['--project', p]);
  const args = [...stage.args, ...projArgs];
  if (listOnly) args.push('--list');
  const env = {
    ...process.env,
    PLAYWRIGHT_JSON_OUTPUT_NAME: jsonOut,
    PLAYWRIGHT_JUNIT_OUTPUT_NAME: junitOut,
    PLAYWRIGHT_BROWSERS_PATH: 'C:\\Users\\Jeff0\\AppData\\Local\\ms-playwright',
  };
  const cmd = `npx playwright test ${args.join(' ')}`;
  try {
    execSync(cmd, { cwd: WS, stdio: 'pipe', timeout: 1800000, env, windowsHide: true });
    return { code: 0, stdout: '' };
  } catch (e) {
    return { code: e.status ?? 1, stdout: String(e.stdout ?? '') + String(e.stderr ?? '') };
  }
}

// ---------------------------------------------------------------------------
// Parse Playwright JSON -> flat node list
// ---------------------------------------------------------------------------
function flatten(json) {
  const nodes = [];
  function walkSuite(suite) {
    for (const s of suite.suites ?? []) walkSuite(s);
    for (const spec of suite.specs ?? []) {
      for (const t of spec.tests ?? []) {
        const results = t.results ?? [];
        const last = results[results.length - 1] ?? {};
        let outcome = t.expected ?? last.status ?? 'unknown';
        if (outcome === 'unexpected') outcome = 'failed';
        if (outcome === 'expected') outcome = 'failed-expected'; // xfail-like; treated as failure evidence
        nodes.push({
          title: spec.title,
          file: spec.file ?? '',
          line: spec.line ?? 0,
          project: t.projectName ?? '',
          outcome,
          duration: last.duration ?? 0,
          error: (last.errors ?? []).map(e => (e.message ?? '').split('\n').slice(0, 6).join(' | ')).join(' ;; '),
          attachments: (last.attachments ?? []).map(a => a.name),
          raw: t,
        });
      }
    }
  }
  for (const s of json.suites ?? []) walkSuite(s);
  return nodes;
}

// Parse JUnit XML -> counts (regex-based, no deps)
function parseJUnit(xml) {
  const text = fs.readFileSync(xml, 'utf-8');
  const tests = (text.match(/<testcase\b/g) || []).length;
  const failures = (text.match(/<failure\b/g) || []).length;
  const errors = (text.match(/<error\b/g) || []).length;
  const skipped = (text.match(/<skipped\b/g) || []).length;
  return { tests, failures, errors, skipped };
}

// ---------------------------------------------------------------------------
// Run stages
// ---------------------------------------------------------------------------
console.log('=== PW1-R1 staged execution ===');
const stageResults = [];
let authGateFailed = false;

for (const stage of STAGES) {
  if (stage !== STAGES[0] && authGateFailed) {
    console.log(`[stage] ${stage.name}: BLOCKED (auth matrix gate failed)`);
    stageResults.push({ stage: stage.name, blocked: true, nodes: [] });
    continue;
  }
  console.log(`[stage] running ${stage.name}: ${stage.projects.join('+')}`);
  const r = runPlaywright(stage);
  const jsonPath = path.join(REPORTS, `${stage.name}.json`);
  const junitPath = path.join(REPORTS, `${stage.name}.xml`);
  let nodes = [];
  if (fs.existsSync(jsonPath)) {
    nodes = flatten(JSON.parse(fs.readFileSync(jsonPath, 'utf-8')));
  }
  const junit = fs.existsSync(junitPath) ? parseJUnit(junitPath) : null;
  const pass = nodes.filter(n => n.outcome === 'passed').length;
  const fail = nodes.filter(n => n.outcome === 'failed' || n.outcome === 'failed-expected').length;
  const skip = nodes.filter(n => n.outcome === 'skipped').length;
  console.log(`[stage] ${stage.name}: nodes=${nodes.length} pass=${pass} fail=${fail} skip=${skip} exit=${r.code}`);
  if (junit) console.log(`[stage] ${stage.name} junit: tests=${junit.tests} failures=${junit.failures + junit.errors} skipped=${junit.skipped}`);
  // Reconciliation JSON vs JUnit
  const junitTotal = junit ? junit.tests : -1;
  const gap = junit ? (junitTotal !== nodes.length ? nodes.length - junitTotal : 0) : null;
  if (junit && gap !== 0) console.log(`[RECONCILE-GAP] ${stage.name}: json nodes=${nodes.length} vs junit tests=${junitTotal}`);
  if (junit && junit.failures + junit.errors !== fail) console.log(`[RECONCILE-GAP] ${stage.name}: json fail=${fail} vs junit failures=${junit.failures + junit.errors}`);
  stageResults.push({ stage: stage.name, blocked: false, nodes, junit, exit: r.code, log: r.stdout.slice(-4000) });
  if (stage === STAGES[0] && fail > 0) {
    authGateFailed = true;
    console.log('[gate] AUTH MATRIX FAILED — later stages will be BLOCKED (not product FAIL)');
  }
}

// ---------------------------------------------------------------------------
// Aggregate + blocked accounting
// ---------------------------------------------------------------------------
const allNodes = [];
const blockedStages = [];
for (const sr of stageResults) {
  if (sr.blocked) { blockedStages.push(sr.stage); continue; }
  allNodes.push(...sr.nodes.map(n => ({ ...n, stage: sr.stage })));
}

// Planned node inventory for blocked accounting (from --list)
const blockedNodes = [];
if (authGateFailed) {
  for (const stage of STAGES.slice(1)) {
    runPlaywright(stage, true); // --list writes JSON to the env-var output file
    const jsonPath = path.join(REPORTS, `${stage.name}.json`);
    if (fs.existsSync(jsonPath)) {
      try {
        const listed = flatten(JSON.parse(fs.readFileSync(jsonPath, 'utf-8')));
        for (const n of listed) {
          blockedNodes.push({ ...n, stage: stage.name, outcome: 'blocked' });
        }
      } catch { /* parse failure -> no detail for this stage */ }
    }
  }
}
const plannedBlocked = blockedNodes.length;

const pass = allNodes.filter(n => n.outcome === 'passed').length;
const fail = allNodes.filter(n => n.outcome === 'failed' || n.outcome === 'failed-expected').length;
const skip = allNodes.filter(n => n.outcome === 'skipped').length;
const flaky = allNodes.filter(n => n.outcome === 'flaky').length;
const total = allNodes.length;

// Root-cause grouping for failures
function rootCauseSig(n) {
  const m = n.error || '';
  if (/TimeoutError.*waiting for/i.test(m)) return 'timeout-wait';
  if (/expect\(received\)\.toBe\(/i.test(m)) return 'assert-equality';
  if (/toHaveURL/i.test(m)) return 'url-redirect';
  if (/toBeVisible/i.test(m)) return 'element-not-visible';
  if (/HTTP [45]\d\d/i.test(m)) return 'http-status';
  if (/toEqual/i.test(m)) return 'assert-array';
  return 'other';
}
const failGroups = {};
for (const n of allNodes.filter(n => n.outcome === 'failed' || n.outcome === 'failed-expected')) {
  const sig = rootCauseSig(n);
  (failGroups[sig] ??= []).push(`${n.project}:${n.title}`);
}

// ---------------------------------------------------------------------------
// Deliverables
// ---------------------------------------------------------------------------
const results = {
  task: 'DC-12R1-MVP-L1-PW1-R1',
  generated_at: new Date().toISOString(),
  source_sha: 'd2e7e44cf23e91cabfab545c494abd342fec3062',
  backend_env: 'staging (JwtAuthStrategy)',
  stages: stageResults.map(s => ({
    name: s.stage, blocked: !!s.blocked, exit: s.exit ?? null,
    json_nodes: s.nodes ? s.nodes.length : null,
    junit: s.junit ?? null,
  })),
  accounting: { total, pass, fail, skip, flaky, blocked: plannedBlocked },
  accounting_gap: null, // computed below
  failure_root_causes: failGroups,
  nodes: allNodes.map(n => ({
    stage: n.stage, project: n.project, file: path.basename(n.file), title: n.title,
    outcome: n.outcome, duration_ms: n.duration,
    evidence_attachments: n.attachments, error: n.error || null,
  })),
};
// Final accounting check: pass+fail+skip+flaky+blocked === total+plannedBlocked
const accounted = pass + fail + skip + flaky + plannedBlocked;
results.accounting_gap = accounted - (total + plannedBlocked);

fs.writeFileSync(path.join(REPORTS, 'PW1_R1_RESULTS.json'), JSON.stringify(results, null, 2), 'utf-8');

// Canonical JUnit (merge stage XMLs into one testsuite document)
function esc(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
let junitXml = `<?xml version="1.0" encoding="UTF-8"?>\n<testsuites name="PW1_R1" tests="${total + plannedBlocked}" failures="${fail}" skipped="${skip + plannedBlocked}">\n`;
for (const n of allNodes) {
  junitXml += `  <testsuite name="${esc(n.stage)}/${esc(n.project)}" tests="1" failures="${n.outcome === 'failed' || n.outcome === 'failed-expected' ? 1 : 0}" skipped="${n.outcome === 'skipped' ? 1 : 0}">\n`;
  junitXml += `    <testcase classname="${esc(path.basename(n.file))}" name="${esc(n.title)}" time="${(n.duration / 1000).toFixed(3)}"${n.outcome === 'passed' ? ' /' : ''}>\n`;
  if (n.outcome === 'failed' || n.outcome === 'failed-expected') junitXml += `      <failure message="${esc((n.error || '').slice(0, 300))}"/>\n`;
  if (n.outcome === 'skipped') junitXml += `      <skipped/>\n`;
  junitXml += `    </testcase>\n  </testsuite>\n`;
}
for (const n of blockedNodes) {
  junitXml += `  <testsuite name="${esc(n.stage)}/${esc(n.project)}" tests="1" failures="0" skipped="1">\n`;
  junitXml += `    <testcase classname="${esc(path.basename(n.file))}" name="${esc(n.title)}"><skipped message="BLOCKED: auth matrix gate failed (not a product FAIL)"/></testcase>\n`;
  junitXml += `  </testsuite>\n`;
}
junitXml += '</testsuites>\n';
fs.writeFileSync(path.join(REPORTS, 'PW1_R1_JUNIT.xml'), junitXml, 'utf-8');

// Findings CSV
function csvEsc(s) { s = String(s ?? ''); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; }
const phaseOf = (f, t) => {
  if (f.includes('auth-matrix')) return 'Auth Matrix';
  const m = f.match(/phase(\d)/);
  if (m) return `Phase ${m[1]}`;
  return 'Other';
};
let csv = 'Stage,Project,Phase,Test Title,Outcome,Severity,Role,Notes\n';
for (const n of allNodes) {
  const sev = n.outcome !== 'passed' ? (/isolation|idempoten|duplicate/i.test(n.title) ? 'P0' : /login|route|hydrat|workspace/i.test(n.title) ? 'P1' : 'P2') : 'INFO';
  csv += [n.stage, n.project, phaseOf(n.file, n.title), n.title, n.outcome.toUpperCase(), sev, '', n.outcome === 'passed' ? '' : (n.error || '').slice(0, 200)].map(csvEsc).join(',') + '\n';
}
for (const n of blockedNodes) {
  csv += [n.stage, n.project, phaseOf(n.file, n.title), n.title, 'BLOCKED', '-', '', 'BLOCKED: auth matrix gate failed (upstream product defect PW1R1-D1); not an independent product failure'].map(csvEsc).join(',') + '\n';
}
fs.writeFileSync(path.join(REPORTS, 'PW1_R1_FINDINGS.csv'), '\ufeff' + csv, 'utf-8');

// Post-generation re-parse reconciliation (Phase 4.8)
const reJson = JSON.parse(fs.readFileSync(path.join(REPORTS, 'PW1_R1_RESULTS.json'), 'utf-8'));
const reJUnit = parseJUnit(path.join(REPORTS, 'PW1_R1_JUNIT.xml'));
const csvRows = fs.readFileSync(path.join(REPORTS, 'PW1_R1_FINDINGS.csv'), 'utf-8').trim().split('\n').length - 1;
const recon = {
  executed_nodes: reJson.nodes.length,
  blocked_nodes: plannedBlocked,
  collected_total: reJson.nodes.length + plannedBlocked,
  junit_tests: reJUnit.tests,
  junit_failures: reJUnit.failures,
  csv_rows: csvRows,
  json_pass: reJson.accounting.pass,
  json_fail: reJson.accounting.fail,
  gap: Math.abs((reJson.nodes.length + plannedBlocked) - reJUnit.tests) + Math.abs(csvRows - (reJson.nodes.length + plannedBlocked)),
};
fs.writeFileSync(path.join(REPORTS, 'reconciliation.json'), JSON.stringify(recon, null, 2), 'utf-8');
console.log('\n=== RECONCILIATION (post-generation re-parse) ===');
console.log(JSON.stringify(recon, null, 2));
console.log(`\nAccounting: total=${total} pass=${pass} fail=${fail} skip=${skip} flaky=${flaky} blocked=${plannedBlocked}`);
console.log(`Accounting gap: ${results.accounting_gap === 0 ? '0 (OK)' : results.accounting_gap + ' (MISMATCH!)'}`);
process.exit(fail === 0 && plannedBlocked === 0 && results.accounting_gap === 0 && recon.gap === 0 ? 0 : 1);
