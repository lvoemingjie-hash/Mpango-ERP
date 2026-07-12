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
};
