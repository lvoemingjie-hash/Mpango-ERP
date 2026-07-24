/**
 * DC-12R1-S1: retailer credential token URL handling.
 *
 * Strict, fragment-only token transport (CTO decision):
 *  1. If location.search contains ANY sensitive param, the link is rejected:
 *     scrub to pathname, render Invalid Link, do NOT read the fragment, do NOT
 *     call the API. Mixed query+fragment is rejected because a sensitive query
 *     param takes precedence.
 *  2. Otherwise read the token from location.hash ONLY.
 *  3. Immediately scrub the URL to the pathname (token never stays in history).
 *  4. Keep the token only in component memory; never localStorage/sessionStorage.
 */

export const SENSITIVE_QUERY_PARAMS = [
  'setupToken',
  'setup_token',
  'resetToken',
  'reset_token',
  'token',
  'newPassword',
  'new_password',
] as const;

export type ReadTokenResult =
  | { kind: 'rejected' }
  | { kind: 'token'; token: string }
  | { kind: 'missing' };

/**
 * Inspect the current location and extract a fragment token under the strict
 * policy. Side effect: scrubs the URL to the pathname whenever a sensitive
 * query param is present OR a fragment token is read.
 */
export function readFragmentToken(
  search: string,
  hash: string,
  fragmentParam: 'setupToken' | 'resetToken',
): ReadTokenResult {
  const queryParams = new URLSearchParams(search);
  if (SENSITIVE_QUERY_PARAMS.some((p) => queryParams.has(p))) {
    scrubUrlToPathname();
    return { kind: 'rejected' };
  }

  const fragmentParams = new URLSearchParams(
    hash.startsWith('#') ? hash.slice(1) : hash,
  );
  const token = fragmentParams.get(fragmentParam);
  if (token) {
    scrubUrlToPathname();
    return { kind: 'token', token };
  }
  return { kind: 'missing' };
}

function scrubUrlToPathname(): void {
  if (typeof window === 'undefined') return;
  window.history.replaceState(window.history.state, document.title, window.location.pathname);
}

/**
 * Assert the token never lands in browser storage. Used in tests to prove the
 * "no browser storage contains the token" invariant.
 */
export function tokenInStorage(): string | null {
  if (typeof window === 'undefined') return null;
  for (const key of SENSITIVE_QUERY_PARAMS) {
    const ls = window.localStorage.getItem(key);
    if (ls) return ls;
    const ss = window.sessionStorage.getItem(key);
    if (ss) return ss;
  }
  return null;
}
