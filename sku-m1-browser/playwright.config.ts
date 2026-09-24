/**
 * DC-12R1-MVP-L1-SKU-R0-M1-R1-B1 — authoritative SKU browser harness config.
 *
 * Frozen node identities (deterministic, no timestamps/uuids/ports/paths):
 *   sku-m1-browser/tests/catalog-id-001.spec.ts::CATALOG-ID-001
 *   sku-m1-browser/tests/catalog-hist-001.spec.ts::CATALOG-HIST-001
 * Both nodes execute under BOTH viewports (desktop, mobile-390).
 *
 * Runtime authenticity: real PG16 + Redis 7 + backend process + production
 * frontend build + real Chromium. No API mocks, no route fulfillment, no
 * direct database seeding (provisioning goes through public API flows with a
 * local SMTP sink for verification/credential emails).
 */
import { defineConfig, devices } from '@playwright/test';
import * as path from 'path';
import { RETRIES, WORKERS, resolveRuntimeMode, RuntimeMode } from './src/runtime';

const resultsDir = path.resolve(__dirname, 'results');

export const REQUIRED_NODE_TITLES = ['CATALOG-ID-001', 'CATALOG-HIST-001'] as const;

function readCandidateSha(): string {
  const fromEnv = process.env.B1_CANDIDATE_SHA?.trim();
  if (fromEnv) return fromEnv;
  return '';
}

export const HARNESS_CONFIG = {
  candidateSha: readCandidateSha(),
  backendBaseUrl: process.env.B1_BACKEND_BASE_URL ?? 'http://127.0.0.1:8101',
  frontendBaseUrl: process.env.B1_FRONTEND_BASE_URL ?? 'http://127.0.0.1:8102',
  smtpHost: process.env.B1_SMTP_HOST ?? '127.0.0.1',
  smtpPort: Number(process.env.B1_SMTP_PORT ?? 8103),
  redisHost: process.env.B1_REDIS_HOST ?? '127.0.0.1',
  redisPort: Number(process.env.B1_REDIS_PORT ?? 8104),
  redisAuthorityDb: 15,
  sentinelEndpoint: { host: '127.0.0.1', port: 26379 },
  backendAlembicVersionsDir:
    process.env.B1_ALEMBIC_VERSIONS_DIR ??
    path.resolve(__dirname, '..', 'backend', 'alembic', 'versions'),
  expectedAlembicHead: '038_catalog_identity_vertical_slice',
  expectedAlembicParent: '037_payment_declarations_schema',
  provisioningPath: path.resolve(__dirname, 'provisioning', 'official.json'),
  resultsDir,
};

/**
 * B4 authority modes — exactly two, mutually exclusive:
 *
 *   B3_AUTHOR_DIAGNOSTIC=1      -> AUTHOR_DIAGNOSTIC     (author evidence)
 *   B4_INDEPENDENT_AUTHORITY=1  -> INDEPENDENT_AUTHORITY (independent evidence)
 *
 * `--list` is read-only and ignores BOTH mode variables: no runtime reporter,
 * no runtime evidence, no mode binding.
 *
 * Every other invocation must select exactly one mode; resolution fails closed
 * here, before Playwright can launch a browser.
 */
const isListMode = process.argv.some((arg) => arg === '--list' || arg === 'list');
export const RUNTIME_MODE: RuntimeMode | null = isListMode ? null : resolveRuntimeMode();
const runtimeMode = RUNTIME_MODE;

const reportBinding = runtimeMode
  ? {
      execution_mode: runtimeMode,
      candidate_sha: HARNESS_CONFIG.candidateSha,
      workers: WORKERS,
      retries: RETRIES,
    }
  : undefined;

const reporter: NonNullable<ReturnType<typeof defineConfig>['reporter']> = runtimeMode ? [
  ['list'],
  [
    'json',
    {
      outputFile: path.join(resultsDir, 'playwright-report.json'),
    },
  ],
  [require.resolve('./src/authority-reporter')],
] : [['list']];

export default defineConfig({
  testDir: path.resolve(__dirname, 'tests'),
  metadata: reportBinding,
  timeout: 240_000,
  globalTimeout: 1_800_000,
  workers: 1,
  fullyParallel: false,
  retries: 0,
  forbidOnly: true,
  outputDir: path.join(resultsDir, 'test-artifacts'),
  globalSetup: require.resolve('./src/global-setup'),
  projects: [
    {
      name: 'desktop',
      metadata: reportBinding,
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1280, height: 800 },
        browserName: 'chromium',
        baseURL: HARNESS_CONFIG.frontendBaseUrl,
        channel: process.env.B1_CHROMIUM_CHANNEL || undefined,
        launchOptions: {
          args: ['--no-sandbox'],
          executablePath: process.env.B1_CHROMIUM_EXECUTABLE || undefined,
        },
        ignoreHTTPSErrors: true,
      },
    },
    {
      name: 'mobile-390',
      metadata: reportBinding,
      use: {
        ...devices['Pixel 7'],
        viewport: { width: 390, height: 844 },
        browserName: 'chromium',
        baseURL: HARNESS_CONFIG.frontendBaseUrl,
        channel: process.env.B1_CHROMIUM_CHANNEL || undefined,
        launchOptions: {
          args: ['--no-sandbox'],
          executablePath: process.env.B1_CHROMIUM_EXECUTABLE || undefined,
        },
        ignoreHTTPSErrors: true,
      },
    },
  ],
  reporter,
});
