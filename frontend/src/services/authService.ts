import { api } from '@/services/api';
import type {
  LoginRequest,
  LoginResponse,
  IdentityLoginResponse,
  SelectTenantRequest,
  CurrentUserResponse,
} from '@/types/auth';

/**
 * Auth API service — thin wrapper over api.ts.
 * No business logic here (per frontend_contract.md §3).
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
};
