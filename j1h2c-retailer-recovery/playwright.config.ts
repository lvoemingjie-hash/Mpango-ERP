/**
 * DC-12R1-MVP-L1-J1-H2-C-R1-R2-R1-B1 — frozen harness configuration.
 *
 * Frozen contract:
 *   fullyParallel=false, workers=1, retries=0, maxFailures=1 — the single
 *   serial spec (tests/recovery.spec.ts) runs the 15 browser nodes (HC01-
 *   HC10, HC12-HC16) in inventory order and the whole run aborts on the
 *   first failure: deterministic, fail-stop, no skip/fixme/only, no
 *   conditional pass, no rerun-to-green.
 *
 * Evidence hygiene: trace, screenshot and video are OFF so no maildir
 * reset token, password or URL fragment can ever reach an artifact file.
 * The JSON and JUnit reporters are enabled for the single authoritative
 * run; every assertion failure names surfaces/fields/categories only,
 * never secret values (see src/assertions.ts).
 */
import { defineConfig } from '@playwright/test';

const BASE_URL_FALLBACK_FOR_LISTING =
  'http://j1h2c.invalid.frozen-harness.local';

export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  // Fail-stop: abort the entire run on the FIRST failing node — combined
  // with the single serial spec this is the protocol's "any failure ⇒
  // STOP" contract; no cascade of downstream red nodes.
  maxFailures: 1,
  timeout: 120_000,
  expect: {
    timeout: 15_000,
  },
  reporter: [
    ['list'],
    ['json', { outputFile: 'artifacts/results.json' }],
    ['junit', { outputFile: 'artifacts/results-junit.xml' }],
  ],
  outputDir: 'artifacts/test-results',
  use: {
    // Read at RUN time only. `--list` must work without any env; the
    // fallback host is intentionally unresolvable so an accidental run
    // without env fails closed instead of touching a real origin.
    baseURL: process.env.J1H2C_BASE_URL ?? BASE_URL_FALLBACK_FOR_LISTING,
    trace: 'off',
    screenshot: 'off',
    video: 'off',
  },
});
