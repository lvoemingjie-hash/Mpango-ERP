/**
 * Leak-scan surfaces for R12 (task directive #14).
 *
 * Findings carry a SURFACE and a FIELD NAME only — never a value, never a
 * key's content, never a console message's text. The specs turn any finding
 * into a sanitized failure listing surface:field pairs.
 */

export type LeakSurface = 'url' | 'storage' | 'console' | 'network';

export interface LeakFinding {
  surface: LeakSurface;
  /** Field identifier only, e.g. `localStorage key "x"` pattern name or message index. */
  field: string;
}

/** Forbidden pattern for storage keys/values (protocol §6.2-5). */
export const FORBIDDEN_STORAGE_PATTERN = /resetToken|reset_token|password|authorization/i;

/** Forbidden pattern for any network URL (tokens must never leave the fragment). */
export const FORBIDDEN_URL_PATTERN = /resetToken|reset_token|token=/i;

/** Forbidden pattern for console output. */
export const FORBIDDEN_CONSOLE_PATTERN = /resetToken|reset_token|authorization\s*:|bearer\s+/i;

export interface StorageSnapshot {
  localStorage: Record<string, string>;
  sessionStorage: Record<string, string>;
}

export function scanStorage(snapshot: StorageSnapshot): LeakFinding[] {
  const findings: LeakFinding[] = [];
  for (const [store, bag] of [
    ['localStorage', snapshot.localStorage],
    ['sessionStorage', snapshot.sessionStorage],
  ] as const) {
    for (const key of Object.keys(bag)) {
      if (FORBIDDEN_STORAGE_PATTERN.test(key)) {
        findings.push({ surface: 'storage', field: `${store} key matched forbidden pattern` });
        continue;
      }
      if (FORBIDDEN_STORAGE_PATTERN.test(bag[key])) {
        findings.push({ surface: 'storage', field: `${store} value for key index matched forbidden pattern` });
      }
    }
  }
  return findings;
}

export function scanUrl(url: string): LeakFinding[] {
  return FORBIDDEN_URL_PATTERN.test(url)
    ? [{ surface: 'url', field: 'settled page URL matched forbidden pattern' }]
    : [];
}

export function scanConsoleText(text: string, index: number): LeakFinding[] {
  return FORBIDDEN_CONSOLE_PATTERN.test(text)
    ? [{ surface: 'console', field: `console message #${index} matched forbidden pattern` }]
    : [];
}

export function scanSecretSubstrings(
  text: string,
  secrets: Array<{ label: string; value: string }>,
  surface: LeakSurface,
  fieldBase: string,
): LeakFinding[] {
  const findings: LeakFinding[] = [];
  for (const secret of secrets) {
    if (secret.value.length > 0 && text.includes(secret.value)) {
      findings.push({ surface, field: `${fieldBase} contained secret (${secret.label})` });
    }
  }
  return findings;
}

export function scanNetworkRequest(requestUrl: string, index: number): LeakFinding[] {
  return FORBIDDEN_URL_PATTERN.test(requestUrl)
    ? [{ surface: 'network', field: `network request #${index} URL matched forbidden pattern` }]
    : [];
}

export function describeFindings(findings: LeakFinding[]): string {
  return findings.map((finding) => `${finding.surface}:${finding.field}`).join(', ');
}
