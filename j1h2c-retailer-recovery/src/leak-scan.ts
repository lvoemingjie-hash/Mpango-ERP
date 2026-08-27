/**
 * Secret leak scanners (B1-R1: Kilo A + B closures).
 *
 * RESET TOKEN scan (HC12, Kilo A):
 *   The reset POST /client/auth/reset-password legitimately carries the
 *   token in its `reset_token` JSON body field — that is the product
 *   contract and is NOT a leak. The token must be ZERO everywhere else:
 *   page URL, query string, browser storage, console output, request
 *   URLs, request headers, and any OTHER body field of any request.
 *
 * PUBLIC W CODE scan (HC12, Kilo B):
 *   `w` is public but may appear ONLY in (1) the initial fragment and
 *   (2) the post-reset canonical /retail/login?w=<CANONICAL> URL. It is
 *   FORBIDDEN in: any API request URL, any request header, any request
 *   body (including the reset POST), localStorage, sessionStorage,
 *   console output, and any evidence artifact.
 *
 * Failure output names surface + category only — never a value.
 */

import type { Page, Request } from '@playwright/test';
import { fieldOnly } from './assertions.js';

const RESET_POST_URL_FRAGMENT = '/client/auth/reset-password';

export interface TokenLeakScanResult {
  url: boolean;
  query: boolean;
  storage: boolean;
  console: boolean;
  networkUrl: boolean;
  networkHeader: boolean;
  networkBodyOtherFields: boolean;
}

export interface PublicCodeScanResult {
  requestUrl: boolean;
  requestHeader: boolean;
  requestBody: boolean;
  storage: boolean;
  console: boolean;
}

interface ConsoleCapture {
  entries: string[];
}

export function installConsoleCapture(page: Page): ConsoleCapture {
  const capture: ConsoleCapture = { entries: [] };
  page.on('console', (message) => {
    capture.entries.push(message.text());
  });
  return capture;
}

async function readStorageSurfaces(page: Page): Promise<string[]> {
  return page.evaluate(() => {
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
    return surfaces;
  });
}

function parseBodyFields(postData: string | null): Record<string, unknown> | null {
  if (postData === null) return null;
  try {
    const parsed: unknown = JSON.parse(postData);
    if (typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>;
    }
    return null;
  } catch {
    return null;
  }
}

/** Token scan: the reset POST's reset_token field is legitimate (Kilo A). */
export async function scanTokenLeak(
  page: Page,
  token: string,
  consoleCapture: ConsoleCapture,
  requests: Request[],
): Promise<TokenLeakScanResult> {
  const currentUrl = page.url();
  const [urlPath, query] = [
    currentUrl.split('#')[0],
    currentUrl.split('?')[1] ?? '',
  ];
  const storageSurfaces = await readStorageSurfaces(page);

  let networkUrl = false;
  let networkHeader = false;
  let networkBodyOtherFields = false;
  for (const request of requests) {
    const isResetPost =
      request.method() === 'POST' && request.url().includes(RESET_POST_URL_FRAGMENT);
    if (request.url().split('#')[0].includes(token)) networkUrl = true;
    if (Object.values(request.headers()).some((value) => value.includes(token))) {
      networkHeader = true;
    }
    const fields = parseBodyFields(request.postData());
    if (fields !== null) {
      for (const [key, value] of Object.entries(fields)) {
        const valueText = typeof value === 'string' ? value : JSON.stringify(value) ?? '';
        if (!valueText.includes(token)) continue;
        // Legitimate ONLY as the reset POST's reset_token field (Kilo A #6).
        if (isResetPost && key === 'reset_token') continue;
        networkBodyOtherFields = true;
      }
    } else if ((request.postData() ?? '').includes(token) && !isResetPost) {
      networkBodyOtherFields = true;
    }
  }

  return {
    url: urlPath.includes(token),
    query: query.includes(token),
    storage: storageSurfaces.some((entry) => entry.includes(token)),
    console: consoleCapture.entries.some((entry) => entry.includes(token)),
    networkUrl,
    networkHeader,
    networkBodyOtherFields,
  };
}

export function assertNoTokenLeak(result: TokenLeakScanResult): void {
  const leaked = (Object.keys(result) as (keyof TokenLeakScanResult)[]).filter(
    (surface) => result[surface],
  );
  if (leaked.length > 0) {
    throw fieldOnly('artifact', 'hc12_reset_token', `leak:${leaked.join('+')}`);
  }
}

/** Public w scan across every forbidden surface (Kilo B). */
export async function scanPublicCode(
  page: Page,
  code: string,
  consoleCapture: ConsoleCapture,
  requests: Request[],
): Promise<PublicCodeScanResult> {
  const storageSurfaces = await readStorageSurfaces(page);
  let requestUrl = false;
  let requestHeader = false;
  let requestBody = false;
  for (const request of requests) {
    const requestUrlNoFragment = request.url().split('#')[0];
    if (
      requestUrlNoFragment.includes(code) &&
      !requestUrlNoFragment.includes('/retail/login')
    ) {
      requestUrl = true;
    }
    if (Object.values(request.headers()).some((value) => value.includes(code))) {
      requestHeader = true;
    }
    if ((request.postData() ?? '').includes(code)) {
      requestBody = true;
    }
  }
  return {
    requestUrl,
    requestHeader,
    requestBody,
    storage: storageSurfaces.some((entry) => entry.includes(code)),
    console: consoleCapture.entries.some((entry) => entry.includes(code)),
  };
}

export function assertPublicCodeClean(result: PublicCodeScanResult): void {
  const leaked = (Object.keys(result) as (keyof PublicCodeScanResult)[]).filter(
    (surface) => result[surface],
  );
  if (leaked.length > 0) {
    throw fieldOnly(
      'artifact',
      'hc12_public_code',
      `forbidden_surface:${leaked.join('+')}`,
    );
  }
}
