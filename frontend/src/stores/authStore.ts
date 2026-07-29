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
  updateTokens: (tokens: Pick<TokenData, 'access_token' | 'refresh_token'>) => void;
  setUser: (user: CurrentUserData) => void;
}

export type AuthStore = AuthState & AuthActions;

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
