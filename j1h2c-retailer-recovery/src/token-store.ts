/**
 * Single-process in-memory token store.
 *
 * The maildir reset token lives ONLY here for the lifetime of the single
 * serial run: no cross-file or cross-process caching, no persistence, no
 * globals on window, no storage APIs. Cleared when the run ends.
 */

interface InMemoryState {
  resetToken: string | null;
  portalCode: string | null;
  canonicalCodeFromEmail: string | null;
}

const state: InMemoryState = {
  resetToken: null,
  portalCode: null,
  canonicalCodeFromEmail: null,
};

export function storeResetToken(token: string, portalCode: string | null): void {
  state.resetToken = token;
  state.portalCode = portalCode;
}

export function getResetToken(): string | null {
  return state.resetToken;
}

export function getPortalCode(): string | null {
  return state.portalCode;
}

export function storeCanonicalCodeFromEmail(code: string): void {
  state.canonicalCodeFromEmail = code;
}

export function getCanonicalCodeFromEmail(): string | null {
  return state.canonicalCodeFromEmail;
}

export function clearMemoryState(): void {
  state.resetToken = null;
  state.portalCode = null;
  state.canonicalCodeFromEmail = null;
}
