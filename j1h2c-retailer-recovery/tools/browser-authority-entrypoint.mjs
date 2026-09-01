#!/usr/bin/env node
/**
 * Browser authority entrypoint (B1-R6-R3).
 *
 * Production authority trust boundary. Must be executed DIRECTLY by the
 * shell or HE2 as a fresh Node process:
 *
 *   node tools/browser-authority-entrypoint.mjs
 *
 * When imported by another JS module, direct-process detection below fails,
 * preventing library-import launchers from minting authority evidence.
 *
 * Startup fail-closed checks (before any authority logic):
 *   1. original command line and process.argv[1] both name THIS file
 *   2. process.execArgv contains no --require/--import/--loader/--eval/-e
 *   3. process.env has no NODE_OPTIONS/NODE_PATH
 *   4. process.env has no GIT_* variables
 *
 * After the checks, this module imports the runner and executes the only
 * authority path: materialize -> isolated CORS probe -> runner-owned
 * preflight helper -> authorize -> fixed real child -> terminal seal ->
 * authority evidence.
 */

// ---------------------------------------------------------------------------
// Startup fail-closed checks
// ---------------------------------------------------------------------------

const { readFileSync, realpathSync } = await import('node:fs');
const { dirname, join, relative, resolve, sep } = await import('node:path');
const { fileURLToPath } = await import('node:url');

const ENTRYPOINT_PATH = realpathSync(fileURLToPath(import.meta.url));

function fail(category) {
  process.stderr.write(JSON.stringify({ authority: false, category }) + '\n');
  process.exit(1);
}

function originalCommandLine() {
  try {
    const commandLine = process.report?.getReport?.().header?.commandLine;
    return Array.isArray(commandLine) ? commandLine : [];
  } catch {
    return [];
  }
}

function sameRealFile(a, b) {
  try {
    return realpathSync(a).toLowerCase() === realpathSync(b).toLowerCase();
  } catch {
    return false;
  }
}

function resolveMainPath(raw) {
  if (typeof raw !== 'string' || raw.length === 0 || raw.startsWith('-')) return null;
  return resolve(process.cwd(), raw);
}

const originalMainPath = resolveMainPath(originalCommandLine()[1]);
const argvMainPath = resolveMainPath(process.argv[1]);

if (!originalMainPath || !sameRealFile(originalMainPath, ENTRYPOINT_PATH)) {
  fail('not_direct_entrypoint');
}

if (!argvMainPath || !sameRealFile(argvMainPath, ENTRYPOINT_PATH)) {
  fail('argv_entrypoint_drift');
}

for (const arg of process.execArgv) {
  const lower = arg.toLowerCase();
  if (
    process.execArgv.length > 0 ||
    lower === '-r' ||
    lower.startsWith('-r') ||
    lower.startsWith('-e') ||
    lower === '--require' ||
    lower.startsWith('--require=') ||
    lower === '--import' ||
    lower.startsWith('--import=') ||
    lower === '--loader' ||
    lower.startsWith('--loader=') ||
    lower === '--experimental-loader' ||
    lower.startsWith('--experimental-loader=') ||
    lower === '--eval' ||
    lower.startsWith('--eval=') ||
    lower === '--input-type' ||
    lower.startsWith('--input-type=')
  ) {
    fail('execargv_injection_detected');
  }
}

for (const key of Object.keys(process.env)) {
  const upper = key.toUpperCase();
  if (upper === 'NODE_OPTIONS' || upper === 'NODE_PATH' || upper.startsWith('GIT_')) {
    fail('env_injection_detected');
  }
}

// ---------------------------------------------------------------------------
// Fail-closed checks passed. Now import the runner and execute the direct
// authority chain.
// ---------------------------------------------------------------------------

const TOOL_DIR = dirname(fileURLToPath(import.meta.url));
const { execFileSync } = await import('node:child_process');

function sanitizedEnv() {
  const env = {};
  for (const [key, value] of Object.entries(process.env)) {
    const upper = key.toUpperCase();
    if (upper !== 'NODE_OPTIONS' && upper !== 'NODE_PATH' && !upper.startsWith('GIT_')) {
      env[key] = value;
    }
  }
  return env;
}

function committedBytesOk(path) {
  try {
    const toplevel = execFileSync('git', ['-C', dirname(path), 'rev-parse', '--show-toplevel'], {
      stdio: ['ignore', 'pipe', 'ignore'],
      env: sanitizedEnv(),
    }).toString('utf8').trim();
    const rel = relative(toplevel, path).split(sep).join('/');
    const committed = execFileSync('git', ['-C', toplevel, 'cat-file', 'blob', `HEAD:${rel}`], {
      stdio: ['ignore', 'pipe', 'ignore'],
      env: sanitizedEnv(),
    });
    const working = readFileSync(path);
    return committed.equals(working);
  } catch {
    return false;
  }
}

const criticalPaths = [
  join(TOOL_DIR, 'browser-authority-entrypoint.mjs'),
  join(TOOL_DIR, 'browser-authority-runner.mjs'),
  join(TOOL_DIR, 'browser-authority-cors-probe-helper.mjs'),
  join(TOOL_DIR, 'browser-authority-preflight-helper.mjs'),
  join(TOOL_DIR, 'browser-authority-child.mjs'),
  join(TOOL_DIR, '..', 'inventory', 'browser-authority-profile.json'),
];

for (const path of criticalPaths) {
  if (!committedBytesOk(path)) {
    process.stderr.write(
      JSON.stringify({ authority: false, category: 'working_tree_dirty_vs_head', path: '<committed-path-redacted>' }) + '\n',
    );
    process.exit(1);
  }
}

const runner = await import('./browser-authority-runner.mjs');
if (
  typeof runner.ControlPlane !== 'function' ||
  typeof runner.DurableJsonlLedger !== 'function' ||
  typeof runner.sealAuthorityEvidence !== 'function'
) {
  fail('runner_contract_unavailable');
}

function parseEntrypointArgs(argv) {
  const args = argv.slice(2);
  if (args.length !== 4 || args[0] !== '--contract' || args[2] !== '--ledger') {
    throw new runner.BrowserAuthorityError('entrypoint_args_invalid');
  }
  return {
    contractPath: resolve(process.cwd(), args[1]),
    ledgerPath: resolve(process.cwd(), args[3]),
  };
}

function writeStdout(payload) {
  process.stdout.write(JSON.stringify(payload) + '\n');
}

try {
  runner.assertDirectAuthorityEntrypointProcess();
  runner.assertAuthorityCriticalPathsClean();
  const { contractPath, ledgerPath } = parseEntrypointArgs(process.argv);
  const repoRoot = runner.canonicalRepoRoot();
  const ledger = new runner.DurableJsonlLedger(ledgerPath);
  const control = new runner.ControlPlane({ contractPath, repoRoot, ledger });

  const { inputSha } = control.materialize(process.env);
  await control.corsPreflightProbe();
  // B1-R6-R4: the runner-OWNED preflight helper — the entrypoint supplies
  // no checks and no results; every check runs in the process-isolated,
  // committed-byte-bound helper from the deep-frozen materialized values.
  await control.preflight();
  const argv = runner.canonicalAuthorityChildArgv();
  control.authorize({ inputSha, argv, cwd: repoRoot });

  let launchResult;
  try {
    launchResult = await control.launchAuthorityChild({ argv, cwd: repoRoot });
  } catch (error) {
    if (control.current !== 'TEST_RED') throw error;
    launchResult = {
      outcome: 'TEST_RED',
      category: error && error.name === 'BrowserAuthorityError' ? error.category : '<child_error>',
    };
  }

  const evidence = runner.sealAuthorityEvidence(control);
  writeStdout({
    schema: 'j1h2c/browser-authority-entrypoint-result/1',
    authority: true,
    boundary: 'direct_process_only',
    outcome: control.current,
    launch: launchResult,
    evidence,
  });
  process.exit(control.current === 'FINISHED' ? 0 : 1);
} catch (error) {
  const category = error && error.name === 'BrowserAuthorityError' ? error.category : 'entrypoint_exception';
  process.stderr.write(JSON.stringify({ authority: false, category }) + '\n');
  process.exit(1);
}
