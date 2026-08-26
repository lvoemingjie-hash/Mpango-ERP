import { api } from '@/services/api';
import type {
  LoginRequest,
  LoginResponse,
  IdentityLoginResponse,
  SelectTenantRequest,
  SignupRequest,
  SignupResponse,
  CurrentUserResponse,
  RetailerLoginRequest,
  RetailerLoginResponse,
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

  // DC-12R1-MVP-L1-J1-R1: wholesaler self-service signup. Reuses the existing
  // POST /auth/signup contract verbatim (202, neutral response, no tokens).
  // The Idempotency-Key header is supplied by the caller, which keeps the key
  // stable across retries and rotates it only after an accepted success.
  signup: (payload: SignupRequest, idempotencyKey: string) =>
    api.post<SignupResponse>('/auth/signup', payload, {
      headers: { 'Idempotency-Key': idempotencyKey },
    }),

  refresh: (refreshToken: string) =>
    api.post<LoginResponse>('/auth/refresh', { refresh_token: refreshToken }),

  me: (token?: string) =>
    api.get<CurrentUserResponse>('/auth/me',
      token ? { headers: { Authorization: `Bearer ${token}` } } : undefined,
    ),

  logout: () => api.post('/auth/logout'),

  setupCredential: (payload: { setupToken: string; password: string }) =>
    api.post('/auth/onboarding/setup-credential', payload),

  // DC-12R1-MVP-L1-J1-H2-B-R3: public password-recovery calls are anonymous
  // by contract. The explicitly EMPTY Authorization header blocks stale-store
  // token injection (PW1-R2-R2 precedence) and skipAuthInterceptors lets a
  // 401 reject straight to the page's fixed neutral copy — no refresh, no
  // queue, no logout, no navigation, no global toast.
  forgotPassword: (payload: { email: string }) =>
    api.post('/auth/forgot-password', payload, {
      headers: { Authorization: '' },
      skipAuthInterceptors: true,
    }),

  resetPassword: (payload: { resetToken: string; newPassword: string }) =>
    api.post('/auth/reset-password', payload, {
      headers: { Authorization: '' },
      skipAuthInterceptors: true,
    }),

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
    }, {
      headers: { Authorization: '' },
      skipAuthInterceptors: true,
    }),

  retailerResetPassword: (payload: { resetToken: string; newPassword: string }) =>
    api.post('/client/auth/reset-password', {
      reset_token: payload.resetToken,
      new_password: payload.newPassword,
    }, {
      headers: { Authorization: '' },
      skipAuthInterceptors: true,
    }),

  // DC-12R1-S2: supplier-scoped retailer login. Calls only /client/auth/login.
  // Never calls /auth/login or /auth/select-tenant.
  retailerLogin: (payload: RetailerLoginRequest) =>
    api.post<RetailerLoginResponse>('/client/auth/login', payload),
};
