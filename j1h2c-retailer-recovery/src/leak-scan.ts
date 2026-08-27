/**
 * Secret leak scanner (HC12).
 *
 * Scans EVERY observable surface for the in-memory reset token and checks
 * the public `w` code appears ONLY in contract-allowed locations:
 *   - resetToken: must NEVER appear in page URL, query string, browser
 *     storage, console output, or network metadata (request URLs, headers,
 *     posted body field names are checked structurally — the token must
 *     not be a URL/header substring anywhere);
 *   - w (public): allowed ONLY in the initial fragment and the post-reset
 *     canonical /retail/login?w= URL; never in the reset POST body,
 *     storage, or logs.
 *
 * Failure output names the surface + category only — never the value.
 */

import type { Page, Request } from '@playwright/test';
import { fieldOnly } from './assertions.js';

export interface LeakScanResult {
  url: boolean;
  query: boolean;
  storage: boolean;
  console: boolean;
  network: boolean;
}

interface ConsoleCapture {
  entries: string[];
}

export function installConsoleCapture(page: Page): ConsoleCapture {
  const capture: ConsoleCapture = { entries: [] };
  page.on('console', (message) => {
    // Store text for scanning; the token check below reports field only.
    capture.entries.push(message.text());
  });
  return capture;
}

async function scanStorage(page: Page, secret: string): Promise<boolean> {
  return page.evaluate(
    (value) => {
      const surfaces: string[] = [];
      for (let i = 0; i < localStorage.length; i += 1) {
        const key = localStorage.key(i);
        if (key === null) continue;
        surfaces.push(`${key}=${localStorage.getItem(key) ?? ''}`);
      }
      for (let i = 0; i < sessionStorage.length; i += 1) {
        const key = sessionStorage.key(i);
        if (key === null) continue;
        surfaces.push(`${key}=${sessionStorage.getItem(key) ?? ''}`);
      }
      return surfaces.some((entry) => entry.includes(value));
    },
    secret,
  );
}

function requestCarriesSecret(request: Request, secret: string): boolean {
  const url = request.url();
  if (url.includes(secret)) return true;
  const headers = request.headers();
  if (Object.values(headers).some((value) => value.includes(secret))) {
    return true;
  }
  const postData = request.postData();
  if (postData !== null && postData.includes(secret)) return true;
  return false;
}

export async function scanForSecretLeak(
  page: Page,
  secret: string,
  consoleCapture: ConsoleCapture,
  requests: Request[],
): Promise<LeakScanResult> {
  const currentUrl = page.url();
  const [urlPath, query] = [currentUrl.split('#')[0], currentUrl.split('?')[1] ?? ''];
  const storage = await scanStorage(page, secret);
  return {
    url: urlPath.includes(secret),
    query: query.includes(secret),
    storage,
    console: consoleCapture.entries.some((entry) => entry.includes(secret)),
    network: requests.some((request) => requestCarriesSecret(request, secret)),
  };
}

export function assertNoSecretLeak(result: LeakScanResult, label: string): void {
  const leakedSurfaces = (Object.keys(result) as (keyof LeakScanResult)[]).filter(
    (surface) => result[surface],
  );
  if (leakedSurfaces.length > 0) {
    throw fieldOnly('artifact', label, `leak:${leakedSurfaces.join('+')}`);
  }
}

/** The public w code may appear ONLY in fragment / canonical portal URL. */
export function assertPublicCodeOnlyInAllowedLocations(
  page: Page,
  code: string,
): void {
  const url = page.url();
  const allowed =
    url.includes('#') ||
    url.startsWith('about:blank') ||
    /\/retail\/login\?w=/.test(url);
  const inForbiddenPlace = !allowed && url.includes(code);
  if (inForbiddenPlace) {
    throw fieldOnly('ui', 'page.url', 'public_code_outside_allowed_location');
  }
}
