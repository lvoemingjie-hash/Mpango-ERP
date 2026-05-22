const { spawn } = require('child_process');
const http = require('http');
const path = require('path');
const fs = require('fs');
const Module = require('module');
const os = require('os');

const frontendDir = process.cwd();
const port = Number(process.env.MPANGO_GHOST_QA_PORT || 4173);
const baseUrl = `http://127.0.0.1:${port}`;
const orderId = 'order-tier2-credit-0001';

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
    throw new Error(`playwright module unavailable for Tier 2 browser journey: ${error.message}`);
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

function fulfillJson(route, payload) {
  return route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(payload),
  });
}

function summaryPayload() {
  return {
    data: {
      total_revenue: 240000,
      total_cash_received: 120000,
      outstanding_receivables: 120000,
      overdue_receivables_count: 1,
      order_counts: { completed: 3, pending: 1 },
      total_orders: 4,
      generated_at: '2026-05-22T09:00:00Z',
    },
  };
}

function receivablesSummaryPayload() {
  return {
    data: {
      total_outstanding: 120000,
      retailer_count: 2,
      order_count: 21,
      credit_receivables: 90000,
      unpaid_order_balance: 30000,
      by_retailer: [],
    },
  };
}

function receivableItem(classification = 'credit_receivable') {
  return {
    order_id: orderId,
    retailer_id: 'retailer-tier2-0001',
    retailer_name: 'Ghost QA Retailer',
    status: 'completed',
    classification,
    payment_method: classification === 'credit_receivable' ? 'credit' : 'cash',
    total_amount: 100000,
    cash_paid: 25000,
    balance_due: 75000,
    age_days: 31,
  };
}

function ordersPayload(requestUrl) {
  const url = new URL(requestUrl);
  const page = Number(url.searchParams.get('page') || '1');
  const classification = url.searchParams.get('classification') || 'all';
  if (page > 2) {
    return {
      data: {
        items: [],
        pagination: { page, size: 20, total: 21, pages: 2 },
      },
    };
  }
  return {
    data: {
      items: [receivableItem(classification === 'unpaid_order' ? 'unpaid_order' : 'credit_receivable')],
      pagination: { page, size: 20, total: 21, pages: 2 },
    },
  };
}

async function assertBodyContains(page, text, label) {
  const body = await page.textContent('body');
  if (!body || !body.includes(text)) {
    throw new Error(`${label} missing expected text: ${text}`);
  }
}

async function main() {
  if (!fs.existsSync(path.join(frontendDir, 'dist'))) {
    throw new Error('frontend dist directory missing; run build before Tier 2 browser journey');
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
    const context = await browser.newContext();
    await context.addInitScript(() => {
      localStorage.setItem('mpango-auth', JSON.stringify({
        state: {
          accessToken: 'ghost-access-token',
          refreshToken: 'ghost-refresh-token',
          tenantCode: 't_dev',
          user: {
            id: 'ghost-user',
            email: 'ghost.qa@example.com',
            full_name: 'Ghost QA',
            roles: ['admin'],
          },
        },
        version: 0,
      }));
    });

    const page = await context.newPage();
    let delayNextSummary = false;

    await page.route('**/api/v1/finance/summary', async (route) => {
      if (delayNextSummary) {
        delayNextSummary = false;
        await new Promise((resolve) => setTimeout(resolve, 800));
      }
      await fulfillJson(route, summaryPayload());
    });
    await page.route('**/api/v1/finance/receivables/summary', (route) => fulfillJson(route, receivablesSummaryPayload()));
    await page.route('**/api/v1/finance/receivables/orders**', (route) => fulfillJson(route, ordersPayload(route.request().url())));
    await page.route('**/api/v1/orders/**/invoice', (route) => fulfillJson(route, { data: { invoice_number: 'INV-GHOST' } }));

    await page.goto(`${baseUrl}/finance?page=999&collection=recorded&collectedOrder=${orderId}`, { waitUntil: 'domcontentloaded' });
    await page.waitForURL((url) => url.pathname === '/finance' && url.searchParams.get('page') === '2', { timeout: 10000 });
    await assertBodyContains(page, 'Payment recorded', 'collection notice');
    await assertBodyContains(page, 'Ghost QA Retailer', 'receivable row after stale page recovery');
    await assertBodyContains(page, 'Page 2 of 2', 'pagination recovery');

    delayNextSummary = true;
    await page.getByRole('button', { name: 'Refresh balances' }).click();
    const refreshingButtons = page.locator('button').filter({ hasText: 'Refreshing...' });
    await refreshingButtons.first().waitFor({ timeout: 3000 });
    await page.waitForFunction(() => !document.body.innerText.includes('Refreshing...'), null, { timeout: 10000 });

    await page.getByRole('button', { name: 'Credit' }).click();
    await page.waitForURL((url) => url.pathname === '/finance' && url.searchParams.get('tab') === 'credit_receivable' && !url.searchParams.has('page'), { timeout: 10000 });
    await assertBodyContains(page, 'Credit Exposure', 'credit tab summary');
    await assertBodyContains(page, 'Ghost QA Retailer', 'credit tab receivable row');

    await page.getByRole('button', { name: /^(Collect|Collect Now)$/ }).first().click();
    await page.waitForURL((url) => url.pathname === '/orders' && url.searchParams.get('collect') === orderId && url.searchParams.get('returnTo') === 'finance' && url.searchParams.get('financeTab') === 'credit_receivable', { timeout: 10000 });

    await browser.close();
    browser = null;
    console.log('ghost_qa_tier2_journey=pass(finance_receivables_browser)');
    console.log('stale_page_recovered=pass');
    console.log('collection_notice_preserved=pass');
    console.log('refresh_feedback=pass');
    console.log('tab_filter_url_state=pass');
    console.log('collect_navigation_context=pass');
  } catch (error) {
    console.error(`ghost_qa_tier2_journey=fail:${error.message}`);
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
