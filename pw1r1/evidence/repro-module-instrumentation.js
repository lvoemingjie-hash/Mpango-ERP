const { chromium } = require('playwright');
const fs = require('fs');
const IDS = JSON.parse(fs.readFileSync('provision/identities.json', 'utf-8'));

(async () => {
  const browser = await chromium.launch({
    executablePath: 'C:/Users/Jeff0/AppData/Local/ms-playwright/chromium-1217/chrome-win64/chrome.exe',
    headless: true,
  });
  const page = await browser.newPage();
  page.on('console', m => { const t = m.text(); if (t.startsWith('[WSP]') || t.startsWith('[LP]') || t.startsWith('[PR]')) console.log(t.slice(0, 220)); });

  // Diagnostic-only module instrumentation (never persisted; this browser session only)
  await page.route('**/src/pages/auth/WorkspaceSelectorPage.tsx*', async route => {
    const resp = await route.fetch();
    let text = await resp.text();
    text = text.replace('const state = location.state;',
      'console.log("[WSP] render path=" + location.pathname + " state=" + JSON.stringify(location.state)); const state = location.state;');
    await route.fulfill({ body: text, contentType: 'application/javascript' });
  });
  await page.route('**/src/router/guards.tsx*', async route => {
    const resp = await route.fetch();
    let text = await resp.text();
    text = text.replace('export function PublicRoute() {',
      'export function PublicRoute() { console.log("[PR] PublicRoute render, accessToken=", !!useAuthStore.getState().accessToken);');
    await route.fulfill({ body: text, contentType: 'application/javascript' });
  });

  await page.goto('http://127.0.0.1:5173/login');
  await page.fill('#email', IDS.ra.email);
  await page.fill('#password', IDS.ra.password);
  await page.click('button[type="submit"]');
  await page.waitForTimeout(3500);
  console.log('[final]', page.url());
  await browser.close();
})();
