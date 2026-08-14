const { chromium } = require('playwright');
const fs = require('fs');
const IDS = JSON.parse(fs.readFileSync('provision/identities.json', 'utf-8'));

(async () => {
  const browser = await chromium.launch({
    executablePath: 'C:/Users/Jeff0/AppData/Local/ms-playwright/chromium-1217/chrome-win64/chrome.exe',
    headless: true,
  });
  const page = await browser.newPage();
  await page.addInitScript(() => {
    const origReplace = history.replaceState.bind(history);
    history.replaceState = (s, t, u) => { console.log('[replaceState]', u, JSON.stringify(s)); return origReplace(s, t, u); };
  });
  page.on('console', m => { const t = m.text(); if (t.startsWith('[')) console.log(t); });
  page.on('response', async r => {
    if (r.url().includes('/api/v1/auth/login') && r.request().method() === 'POST') {
      const b = await r.json().catch(() => null);
      console.log('[login-resp]', JSON.stringify({ roles: b?.data?.roles, tenants: b?.data?.available_tenants?.map(t => t.code) }));
    }
    if (r.url().includes('/api/v1/auth/me')) console.log('[me-call]', r.url());
    if (r.url().includes('/api/v1/auth/select-tenant')) console.log('[select-tenant-call]');
  });

  await page.goto('http://127.0.0.1:5173/login');
  await page.fill('#email', IDS.ra.email);
  await page.fill('#password', IDS.ra.password);
  await page.click('button[type="submit"]');
  await page.waitForTimeout(4000);
  console.log('[final]', page.url());
  await browser.close();
})();
