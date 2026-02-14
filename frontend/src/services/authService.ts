import { api } from '@/services/api';
import type {
  LoginRequest,
  LoginResponse,
  CurrentUserResponse,
} from '@/types/auth';

/**
 * Auth API service — thin wrapper over api.ts.
 * No business logic here (per frontend_contract.md §3).
 */
export const authService = {
  login: (payload: LoginRequest) =>
    api.post<LoginResponse>('/auth/login', payload),

  refresh: (refreshToken: string) =>
    api.post<LoginResponse>('/auth/refresh', { refresh_token: refreshToken }),

  me: () => api.get<CurrentUserResponse>('/auth/me'),

  logout: () => api.post('/auth/logout'),
};
