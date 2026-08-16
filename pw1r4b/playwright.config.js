// DC-12R1-MVP-L1-PW1-R1 — Playwright config (real JWT, staging backend)
// Frontend: 127.0.0.1:5173 (Vite dev server, frozen source d2e7e44c)
// Backend:  127.0.0.1:8000  (MPANGO_ENV=staging, JwtAuthStrategy)
const path = require('path');

const CHROME = 'C:\\Users\\Jeff0\\AppData\\Local\\ms-playwright\\chromium-1217\\chrome-win64\\chrome.exe';

module.exports = {
  testDir: './tests',
  timeout: 60000,
  expect: { timeout: 10000 },
  fullyParallel: false,
  workers: 1,
  retries: 0, // no retry masking
  reporter: [
    ['list'],
    ['json'],  // output file via PLAYWRIGHT_JSON_OUTPUT_NAME (per-stage, set by run-tests.js)
    ['junit'], // output file via PLAYWRIGHT_JUNIT_OUTPUT_NAME
  ],
  use: {
    baseURL: 'http://127.0.0.1:5173',
    headless: true,
    viewport: { width: 1440, height: 900 },
    ignoreHTTPSErrors: true,
    actionTimeout: 15000,
    navigationTimeout: 20000,
    trace: 'retain-on-failure',
    launchOptions: {
      executablePath: CHROME,
      args: ['--no-sandbox', '--disable-setuid-sandbox'],
    },
  },
  projects: [
    { name: 'desktop', use: { viewport: { width: 1440, height: 900 } } },
    { name: 'tablet', use: { viewport: { width: 1024, height: 768 } } },
    { name: 'mobile', use: { viewport: { width: 390, height: 844 } } },
  ],
};
