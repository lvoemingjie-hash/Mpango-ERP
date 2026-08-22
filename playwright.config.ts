import { defineConfig } from '@playwright/test';

/**
 * DC-12R1-MVP-L1-J1-H2-A-R2-V3 authoritative config.
 * One worker, zero retries, no sharding — a single authoritative run.
 */
export default defineConfig({
  testDir: '.',
  timeout: 120_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [
    ['list'],
    ['json', { outputFile: 'authoritative_playwright.json' }],
    ['junit', { outputFile: 'authoritative_junit.xml' }],
  ],
  use: {
    baseURL: 'http://localhost:5173',
    viewport: { width: 1280, height: 720 },
    actionTimeout: 15_000,
    trace: 'retain-on-failure',
  },
});
