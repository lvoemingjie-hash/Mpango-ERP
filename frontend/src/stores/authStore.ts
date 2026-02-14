import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { CurrentUserData, TokenData } from '@/types/auth';

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  user: CurrentUserData | null;
  tenantCode: string | null;
}

interface AuthActions {
  login: (tokens: TokenData, user: CurrentUserData, tenantCode: string) => void;
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
};

export const useAuthStore = create<AuthStore>()(
  persist(
    (set) => ({
      ...initialState,

      login: (tokens, user, tenantCode) =>
        set({
          accessToken: tokens.access_token,
          refreshToken: tokens.refresh_token,
          user,
          tenantCode,
        }),

      logout: () => set({ ...initialState }),

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
      }),
    }
  )
);
