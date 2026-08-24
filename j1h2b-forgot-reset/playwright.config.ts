/**
 * DC-12R1-MVP-L1-J1-H2-B-R2-R4-R2-B1 — frozen harness configuration.
 *
 * Frozen contract (task directive #5):
 *   fullyParallel=false, workers=1, retries=0 — one deterministic serial pass,
 *   no skip/fixme/only, no conditional pass, no rerun-to-green.
 *
 * Evidence hygiene (task directive #9): trace, screenshot and video are OFF so
 * no maildir token, password or URL fragment can ever reach an artifact file.
 * The JSON and JUnit reporters are enabled for the single authoritative run;
 * every assertion in this harness is written so failure messages name fields
 * only, never secret values (see src/assertions.ts).
 */
import { defineConfig } from '@playwright/test';

const BASE_URL_FALLBACK_FOR_LISTING =
  'http://j1h2b.invalid.frozen-harness.local';

export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  workers: 1,
  retries: 0,
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
    // Read at RUN time only. `--list` must work without any env; the fallback
    // host is intentionally unresolvable so an accidental run without env
    // fails closed instead of touching a real origin.
    baseURL: process.env.J1H2B_BASE_URL ?? BASE_URL_FALLBACK_FOR_LISTING,
    trace: 'off',
    screenshot: 'off',
    video: 'off',
  },
});
