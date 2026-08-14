import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { CurrentUserData, TokenData, IdentityTokenData } from '@/types/auth';

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  user: CurrentUserData | null;
  tenantCode: string | null;
  /**
   * DC-12R1-S2: the current retailer portal (wholesaler) code. Preserved
   * across logout so an expired/stale retailer session is redirected back to
   * the same supplier portal. Never reveals another code.
   */
  retailerPortalCode: string | null;
}

interface AuthActions {
  login: (tokens: TokenData | IdentityTokenData, user: CurrentUserData, tenantCode: string | null) => void;
  /**
   * DC-12R1-S2: retailer-scoped login stores the contextual session plus the
   * current wholesaler portal code so refresh-failure can redirect back to
   * the same portal.
   */
  retailerLogin: (tokens: TokenData, user: CurrentUserData, wholesalerCode: string) => void;
  logout: () => void;
  /**
   * PW1-R2 (D1 closure): updateTokens is reserved for the established-session
   * token-refresh flow (services/api.ts). It must NOT be used to start a
   * workspace selection — a token-only write leaves `user == null`, which the
   * route guards now treat as a *pending identity session* that is never a
   * contextual authenticated session. Use beginWorkspaceSelection instead.
   */
  updateTokens: (tokens: Pick<TokenData, 'access_token' | 'refresh_token'>) => void;
  setUser: (user: CurrentUserData) => void;
  /**
   * PW1-R2 (D1 closure): enter the workspace-selection phase of a multi-tenant
   * login. Stores the identity access/refresh tokens as a PENDING identity
   * session (`user == null`) and clears unrelated portal/tenant context.
   *
   * A pending identity session is deliberately NOT a contextual authenticated
   * session: the route guards keep it out of the business shell until
   * WorkspaceSelectorPage atomically commits a contextual session via
   * `login(...)` after BOTH select-tenant and /auth/me succeed.
   */
  beginWorkspaceSelection: (identityTokens: Pick<TokenData, 'access_token' | 'refresh_token'>) => void;
}

export type AuthStore = AuthState & AuthActions;

/**
 * PW1-R2 binding session contract — DERIVED facts only (no stored booleans
 * that could drift):
 *
 * - contextual session:           accessToken != null AND user != null
 * - pending identity session:     accessToken != null AND user == null
 * - anonymous:                    accessToken == null AND user == null
 *
 * (A token-less non-null user is treated as anonymous: without a token no
 * authenticated API call is possible, so it must never be admitted.)
 */
export type SessionKind = 'anonymous' | 'pending-identity' | 'contextual';

export function sessionKind(
  state: Pick<AuthState, 'accessToken' | 'user'>,
): SessionKind {
  if (state.accessToken == null) return 'anonymous';
  if (state.user == null) return 'pending-identity';
  return 'contextual';
}

const initialState: AuthState = {
  accessToken: null,
  refreshToken: null,
  user: null,
  tenantCode: null,
  retailerPortalCode: null,
};

export const useAuthStore = create<AuthStore>()(
  persist(
    (set, get) => ({
      ...initialState,

      login: (tokens, user, tenantCode) =>
        set({
          accessToken: tokens.access_token,
          refreshToken: tokens.refresh_token,
          user,
          tenantCode,
          // DC-12R1-S2: owner login clears any retailer portal context.
          retailerPortalCode: null,
        }),

      retailerLogin: (tokens, user, wholesalerCode) =>
        set({
          accessToken: tokens.access_token,
          refreshToken: tokens.refresh_token,
          user,
          tenantCode: wholesalerCode,
          retailerPortalCode: wholesalerCode,
        }),

      logout: () =>
        set({
          // DC-12R1-S2: preserve the portal code across logout so the
          // refresh-failure redirect returns the retailer to the same portal.
          retailerPortalCode: get().retailerPortalCode,
          accessToken: null,
          refreshToken: null,
          user: null,
          tenantCode: null,
        }),

      updateTokens: (tokens) =>
        set({
          accessToken: tokens.access_token,
          refreshToken: tokens.refresh_token,
        }),

      setUser: (user) => set({ user }),

      beginWorkspaceSelection: (identityTokens) =>
        set({
          accessToken: identityTokens.access_token,
          refreshToken: identityTokens.refresh_token,
          // Pending identity session: forced, never a contextual session.
          user: null,
          tenantCode: null,
          // Unrelated portal context must not leak into owner selection.
          retailerPortalCode: null,
        }),
    }),
    {
      name: 'mpango-auth',
      partialize: (state) => ({
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        user: state.user,
        tenantCode: state.tenantCode,
        retailerPortalCode: state.retailerPortalCode,
      }),
    }
  )
);
