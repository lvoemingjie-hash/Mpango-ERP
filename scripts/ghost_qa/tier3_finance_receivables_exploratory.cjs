const { spawn } = require('child_process');
const http = require('http');
const path = require('path');
const fs = require('fs');
const Module = require('module');
const os = require('os');

const frontendDir = process.cwd();
const port = Number(process.env.MPANGO_GHOST_QA_TIER3_PORT || 4174);
const baseUrl = `http://127.0.0.1:${port}`;

function addNodePath(extraPath) {
  if (!extraPath || !fs.existsSync(extraPath)) return;
  process.env.NODE_PATH = process.env.NODE_PATH
    ? `${extraPath}${path.delimiter}${process.env.NODE_PATH}`
    : extraPath;
  Module._initPaths();
}

function requirePlaywright() {
  addNodePath(path.join(os.homedir(), '.openclaw', 'mpango-validation-tools', 'playwright-runtime', 'node_modules'));
  try {
    return require('playwright');
  } catch (error) {
    throw new Error(`playwright module unavailable for Tier 3 exploratory QA: ${error.message}`);
  }
}

function waitForPreview(url, timeoutMs = 20000) {
  const started = Date.now();
  return new Promise((resolve, reject) => {
    const tick = () => {
      const req = http.get(url, (res) => {
        res.resume();
        resolve();
      });
      req.on('error', () => {
        if (Date.now() - started > timeoutMs) {
          reject(new Error(`vite preview did not become ready at ${url}`));
          return;
        }
        setTimeout(tick, 250);
      });
      req.setTimeout(1000, () => {
        req.destroy();
      });
    };
    tick();
  });
}

function fulfillJson(route, payload, status = 200) {
  return route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(payload),
  });
}

function summaryPayload(overrides = {}) {
  return {
    data: {
      total_revenue: 500000,
      total_cash_received: 320000,
      outstanding_receivables: 180000,
      overdue_receivables_count: 2,
      order_counts: { completed: 4, pending: 2 },
      total_orders: 6,
      generated_at: '2026-05-22T10:30:00Z',
      ...overrides,
    },
  };
}

function receivablesSummaryPayload(overrides = {}) {
  return {
    data: {
      total_outstanding: 180000,
      retailer_count: 3,
      order_count: 3,
      credit_receivables: 120000,
      unpaid_order_balance: 60000,
      by_retailer: [],
      ...overrides,
    },
  };
}

function receivableItem(overrides = {}) {
  return {
    order_id: 'order-tier3-0001',
    retailer_id: 'retailer-tier3-0001',
    retailer_name: 'Tier3 Exploratory Retailer',
    status: 'completed',
    classification: 'credit_receivable',
    payment_method: 'credit',
    total_amount: 120000,
    cash_paid: 20000,
    balance_due: 100000,
    age_days: 45,
    ...overrides,
  };
}

function ordersPayload(items, page = 1, total = items.length, pages = items.length ? 1 : 0) {
  return {
    data: {
      items,
      pagination: { page, size: 20, total, pages },
    },
  };
}

async function waitForBodyContains(page, text, label, timeoutMs = 10000) {
  await page.waitForFunction(
    (expectedText) => document.body && document.body.innerText.includes(expectedText),
    text,
    { timeout: timeoutMs },
  ).catch(() => {
    throw new Error(`${label} missing expected text after wait: ${text}`);
  });
}

async function waitForBodyExcludes(page, text, label, timeoutMs = 10000) {
  await page.waitForFunction(
    (unexpectedText) => document.body && !document.body.innerText.includes(unexpectedText),
    text,
    { timeout: timeoutMs },
  ).catch(() => {
    throw new Error(`${label} still contained unexpected text after wait: ${text}`);
  });
}

async function newAuthedPage(browser) {
  const context = await browser.newContext();
  await context.addInitScript(() => {
    localStorage.setItem('mpango-auth', JSON.stringify({
      state: {
        accessToken: 'ghost-tier3-access-token',
        refreshToken: 'ghost-tier3-refresh-token',
        tenantCode: 't_dev',
        user: {
          id: 'ghost-tier3-user',
          email: 'ghost.tier3@example.com',
          full_name: 'Ghost Tier3',
          roles: ['admin'],
        },
      },
      version: 0,
    }));
  });
  const page = await context.newPage();
  return { context, page };
}

async function runEmptyStateScenario(browser) {
  const { context, page } = await newAuthedPage(browser);
  try {
    await page.route('**/api/v1/finance/summary', (route) => fulfillJson(route, summaryPayload({
      total_revenue: 0,
      total_cash_received: 0,
      outstanding_receivables: 0,
      overdue_receivables_count: 0,
      order_counts: { completed: 0, pending: 0 },
      total_orders: 0,
    })));
    await page.route('**/api/v1/finance/receivables/summary', (route) => fulfillJson(route, receivablesSummaryPayload({
      total_outstanding: 0,
      retailer_count: 0,
      order_count: 0,
      credit_receivables: 0,
      unpaid_order_balance: 0,
    })));
    await page.route('**/api/v1/finance/receivables/orders**', (route) => fulfillJson(route, ordersPayload([])));

    await page.goto(`${baseUrl}/finance?tab=credit_receivable`, { waitUntil: 'domcontentloaded' });
    await waitForBodyContains(page, 'No outstanding receivables', 'empty receivables state');
    await waitForBodyContains(page, 'All visible credit accounts are settled', 'empty state guidance');
  } finally {
    await context.close();
  }
}

async function runErrorRecoveryScenario(browser) {
  const { context, page } = await newAuthedPage(browser);
  try {
    let failOnce = true;
    await page.route('**/api/v1/finance/summary', (route) => {
      if (failOnce) {
        failOnce = false;
        return fulfillJson(route, { error: 'temporary ghost QA failure' }, 500);
      }
      return fulfillJson(route, summaryPayload());
    });
    await page.route('**/api/v1/finance/receivables/summary', (route) => fulfillJson(route, receivablesSummaryPayload()));
    await page.route('**/api/v1/finance/receivables/orders**', (route) => fulfillJson(route, ordersPayload([receivableItem()])));

    await page.goto(`${baseUrl}/finance`, { waitUntil: 'domcontentloaded' });
    await waitForBodyContains(page, 'Failed to load accounts receivable data.', 'temporary API error');
    await page.getByRole('button', { name: 'Retry' }).click();
    await waitForBodyContains(page, 'Tier3 Exploratory Retailer', 'error recovery receivable row');
    await waitForBodyExcludes(page, 'Failed to load accounts receivable data.', 'error recovery clears alert');
  } finally {
    await context.close();
  }
}

async function runInvalidUrlRecoveryScenario(browser) {
  const { context, page } = await newAuthedPage(browser);
  try {
    await page.route('**/api/v1/finance/summary', (route) => fulfillJson(route, summaryPayload()));
    await page.route('**/api/v1/finance/receivables/summary', (route) => fulfillJson(route, receivablesSummaryPayload()));
    await page.route('**/api/v1/finance/receivables/orders**', (route) => fulfillJson(route, ordersPayload([receivableItem()])));

    await page.goto(`${baseUrl}/finance?tab=not_a_real_tab&page=-9&collection=bad`, { waitUntil: 'domcontentloaded' });
    await page.waitForURL((url) => url.pathname === '/finance' && !url.searchParams.has('tab') && !url.searchParams.has('page'), { timeout: 10000 });
    await waitForBodyContains(page, 'Tier3 Exploratory Retailer', 'invalid URL recovery row');
    await waitForBodyContains(page, 'All (1)', 'invalid URL recovery all filter');
  } finally {
    await context.close();
  }
}

async function runUnpaidFilterScenario(browser) {
  const { context, page } = await newAuthedPage(browser);
  try {
    await page.route('**/api/v1/finance/summary', (route) => fulfillJson(route, summaryPayload()));
    await page.route('**/api/v1/finance/receivables/summary', (route) => fulfillJson(route, receivablesSummaryPayload()));
    await page.route('**/api/v1/finance/receivables/orders**', (route) => {
      const url = new URL(route.request().url());
      if (url.searchParams.get('classification') !== 'unpaid_order') {
        return fulfillJson(route, ordersPayload([receivableItem()]));
      }
      return fulfillJson(route, ordersPayload([receivableItem({
        order_id: 'order-tier3-unpaid-0001',
        retailer_name: 'Tier3 Unpaid Retailer',
        classification: 'unpaid_order',
        payment_method: 'cash',
        cash_paid: 0,
        balance_due: 60000,
        age_days: 12,
      })]));
    });

    await page.goto(`${baseUrl}/finance`, { waitUntil: 'domcontentloaded' });
    await page.getByRole('button', { name: 'Unpaid' }).click();
    await page.waitForURL((url) => url.pathname === '/finance' && url.searchParams.get('tab') === 'unpaid_order', { timeout: 10000 });
    await waitForBodyContains(page, 'Tier3 Unpaid Retailer', 'unpaid filter row');
    await waitForBodyContains(page, 'Unpaid', 'unpaid filter badge');
  } finally {
    await context.close();
  }
}

async function main() {
  if (!fs.existsSync(path.join(frontendDir, 'dist'))) {
    throw new Error('frontend dist directory missing; run build before Tier 3 exploratory QA');
  }

  const { chromium } = requirePlaywright();
  const preview = spawn('pnpm', ['--ignore-workspace', 'exec', 'vite', 'preview', '--host', '127.0.0.1', '--port', String(port)], {
    cwd: frontendDir,
    stdio: ['ignore', 'pipe', 'pipe'],
    shell: process.platform === 'win32',
  });

  let previewLog = '';
  preview.stdout.on('data', (chunk) => {
    previewLog += chunk.toString();
  });
  preview.stderr.on('data', (chunk) => {
    previewLog += chunk.toString();
  });

  let browser;
  try {
    await waitForPreview(baseUrl);
    browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });

    await runEmptyStateScenario(browser);
    await runErrorRecoveryScenario(browser);
    await runInvalidUrlRecoveryScenario(browser);
    await runUnpaidFilterScenario(browser);

    await browser.close();
    browser = null;
    console.log('ghost_qa_tier3_exploratory=pass(finance_receivables_edge_cases)');
    console.log('tier3_empty_state=pass');
    console.log('tier3_error_recovery=pass');
    console.log('tier3_invalid_url_recovery=pass');
    console.log('tier3_unpaid_filter=pass');
  } catch (error) {
    console.error(`ghost_qa_tier3_exploratory=fail:${error.message}`);
    if (previewLog.trim()) {
      console.error('vite_preview_log_start');
      console.error(previewLog.trim().slice(-4000));
      console.error('vite_preview_log_end');
    }
    process.exitCode = 1;
  } finally {
    if (browser) await browser.close().catch(() => {});
    preview.kill('SIGTERM');
  }
}

main();
