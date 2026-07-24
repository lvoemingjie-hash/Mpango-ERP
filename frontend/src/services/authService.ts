import { api } from '@/services/api';
import type {
  LoginRequest,
  LoginResponse,
  IdentityLoginResponse,
  SelectTenantRequest,
  CurrentUserResponse,
} from '@/types/auth';

/**
 * Auth API service - thin wrapper over api.ts.
 * No business logic here (per frontend_contract.md section 3).
 */
export const authService = {
  login: (payload: LoginRequest) =>
    api.post<IdentityLoginResponse>('/auth/login', payload),

  selectTenant: (payload: SelectTenantRequest, token?: string) =>
    api.post<LoginResponse>('/auth/select-tenant', payload,
      token ? { headers: { Authorization: `Bearer ${token}` } } : undefined,
    ),

  refresh: (refreshToken: string) =>
    api.post<LoginResponse>('/auth/refresh', { refresh_token: refreshToken }),

  me: (token?: string) =>
    api.get<CurrentUserResponse>('/auth/me',
      token ? { headers: { Authorization: `Bearer ${token}` } } : undefined,
    ),

  logout: () => api.post('/auth/logout'),

  setupCredential: (payload: { setupToken: string; password: string }) =>
    api.post('/auth/onboarding/setup-credential', payload),

  forgotPassword: (payload: { email: string }) =>
    api.post('/auth/forgot-password', payload),

  resetPassword: (payload: { resetToken: string; newPassword: string }) =>
    api.post('/auth/reset-password', payload),

  verifyEmail: (payload: { token: string }) =>
    api.post('/auth/verify-email', payload),

  // DC-12R1-S1: retailer-owned credential flows (fragment-only token transport).
  // Redeem endpoints accept the token in the JSON body only.
  retailerSetupCredential: (payload: { setupToken: string; newPassword: string }) =>
    api.post('/retailers/setup-credential', {
      setup_token: payload.setupToken,
      new_password: payload.newPassword,
    }),

  retailerForgotPassword: (payload: { email: string; wholesalerCode: string }) =>
    api.post('/client/auth/forgot-password', {
      email: payload.email,
      wholesaler_code: payload.wholesalerCode,
    }),

  retailerResetPassword: (payload: { resetToken: string; newPassword: string }) =>
    api.post('/client/auth/reset-password', {
      reset_token: payload.resetToken,
      new_password: payload.newPassword,
    }),
};
