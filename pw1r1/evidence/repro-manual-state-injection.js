const { chromium } = require('playwright');
const fs = require('fs');
const IDS = JSON.parse(fs.readFileSync('provision/identities.json', 'utf-8'));

(async () => {
  const browser = await chromium.launch({
    executablePath: 'C:/Users/Jeff0/AppData/Local/ms-playwright/chromium-1217/chrome-win64/chrome.exe',
    headless: true,
  });
  const page = await browser.newPage();
  await page.goto('http://127.0.0.1:5173/login');
  await page.fill('#email', IDS.ra.email);
  await page.fill('#password', IDS.ra.password);
  await page.click('button[type="submit"]');
  await page.waitForTimeout(2500); // let the (broken) flow settle at /

  // Manually push the /select-workspace entry WITH state, then notify RR via popstate
  await page.evaluate((tenants) => {
    history.pushState(
      { usr: { availableTenants: tenants }, key: 'manual-probe', idx: 1 },
      '', '/select-workspace',
    );
    dispatchEvent(new PopStateEvent('popstate', { state: history.state }));
  }, [
    { id: 'x1', code: 'TR16BB078F3A444E409D0BA80AE9D3CE', name: 'PW1R1 W1 Wholesale' },
    { id: 'x2', code: 'TR683EC9D1C5414CC6AE7F760ADB0406', name: 'PW1R1 W2 Wholesale' },
  ]);
  await page.waitForTimeout(1200);
  console.log('[url after manual popstate]', page.url());
  const btns = await page.locator('button').allTextContents();
  console.log('[buttons]', JSON.stringify(btns.map(b => b.trim()).filter(Boolean)));
  const h1 = await page.locator('h1, h3').allTextContents().catch(() => []);
  console.log('[headings]', JSON.stringify(h1));
  await browser.close();
})();
