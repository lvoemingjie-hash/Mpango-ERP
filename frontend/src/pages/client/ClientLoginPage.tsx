import { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { AxiosError } from 'axios';
import { useAuthStore } from '@/stores/authStore';
import { authService } from '@/services/authService';
import type { ApiErrorResponse } from '@/types/api';

/**
 * Wholesaler portal codes follow the DB regex ^[A-Z0-9]+$. A missing or
 * malformed `w` param shows a controlled invalid-portal state and performs
 * ZERO login API calls.
 */
const WHOLESALER_CODE_RE = /^[A-Z0-9]+$/;

const loginSchema = z.object({
  email: z.string().email('Please enter a valid email address'),
  password: z.string().min(1, 'Password is required'),
});

type LoginFormData = z.infer<typeof loginSchema>;

export function ClientLoginPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const retailerLogin = useAuthStore((s) => s.retailerLogin);
  const [serverError, setServerError] = useState<string | null>(null);

  const rawCode = searchParams.get('w') ?? '';
  // Uppercase preference (matches the backend): a lowercase/mixed-case code
  // is normalized to UPPERCASE before the validity check and before any API
  // call. Only genuinely malformed codes (symbols, empty, whitespace) reach
  // the controlled invalid-portal state.
  const portalCode = rawCode.trim().toUpperCase();
  const isValidPortal = portalCode.length > 0 && WHOLESALER_CODE_RE.test(portalCode);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: '', password: '' },
  });

  const onSubmit = async (formData: LoginFormData) => {
    setServerError(null);

    // Guard: portal code must be valid before any API call.
    if (!isValidPortal) {
      setServerError('This supplier portal link is invalid. Please use the link your supplier provided.');
      return;
    }

    try {
      // DC-12R1-S2: single supplier-scoped login call. Never calls
      // /auth/login or /auth/select-tenant.
      const res = await authService.retailerLogin({
        email: formData.email,
        password: formData.password,
        wholesaler_code: portalCode,
      });
      const data = res.data.data;

      // Build the contextual session and store it. The portal code is
      // preserved for refresh-failure redirect back to this portal.
      retailerLogin(
        {
          access_token: data.tokens.access_token,
          refresh_token: data.tokens.refresh_token,
          token_type: data.tokens.token_type,
          user_id: data.tokens.user_id,
          tenant_id: data.tokens.tenant_id,
          tenant_schema: data.tokens.tenant_schema,
          roles: data.tokens.roles,
        },
        {
          id: data.user.id,
          email: data.user.email,
          full_name: data.user.full_name,
          tenant_id: data.tokens.tenant_id,
          tenant_schema: data.tokens.tenant_schema,
          roles: data.tokens.roles,
          permissions: [],
        },
        data.wholesaler.code,
      );
      navigate('/client', { replace: true });
    } catch (err) {
      // The backend may emit either the legacy envelope {error:{code,message}}
      // or the production flat envelope {code,message,request_id}; read the
      // body loosely so both shapes are handled without favoring either.
      const axiosErr = err as AxiosError<ApiErrorResponse>;
      const status = axiosErr.response?.status;
      const detail = axiosErr.response?.data as
        | (ApiErrorResponse & { message?: string; code?: string })
        | undefined;

      // DC-12R1-S2-R2: a 401 is ALWAYS rendered as the fixed neutral
      // "Invalid credentials" — regardless of which error envelope the
      // backend emits (production flat {code,message,request_id}, legacy
      // {error:{code,message}}, or a raw axios fallback). We never surface
      // the raw response body, a dict repr, or the attempted credential.
      if (status === 401) {
        setServerError('Invalid credentials');
      } else if (detail && 'error' in detail && detail.error?.message) {
        setServerError(detail.error.message);
      } else if (detail && typeof detail.message === 'string') {
        setServerError(detail.message);
      } else {
        setServerError('An unexpected error occurred. Please try again.');
      }

      // DC-12R1-S2-R2: on a failed login the retained portal code must
      // become the portal being ATTEMPTED (portalCode), never a previously
      // selected one. We do NOT call logout() (which would preserve a stale
      // code from a prior successful login, e.g. A). Instead we clear any
      // authenticated session while pinning the portal code to the current
      // attempt, so a later refresh-failure redirects to THIS portal.
      useAuthStore.setState({
        accessToken: null,
        refreshToken: null,
        user: null,
        tenantCode: null,
        retailerPortalCode: portalCode,
      });
    }
  };

  // Controlled invalid-portal state: zero API calls.
  if (!isValidPortal) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-primary-50 to-primary-100 px-4">
        <div className="w-full max-w-sm">
          <div className="mb-8 text-center">
            <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-red-500 text-white shadow-lg">
              <svg className="h-8 w-8" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
              </svg>
            </div>
            <h1 className="text-2xl font-bold text-gray-900">Invalid Portal</h1>
            <p className="mt-1 text-sm text-gray-500">
              This supplier portal link is invalid or incomplete. Please contact your supplier for the correct link.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-primary-50 to-primary-100 px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-primary-600 text-white shadow-lg">
            <svg className="h-8 w-8" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 10.5V6a3.75 3.75 0 10-7.5 0v4.5m11.356-1.993l1.263 12c.07.665-.45 1.243-1.119 1.243H4.25a1.125 1.125 0 01-1.12-1.243l1.264-12A1.125 1.125 0 015.513 7.5h12.974c.576 0 1.059.435 1.119 1.007zM8.625 10.5a.375.375 0 11-.75 0 .375.375 0 01.75 0zm7.5 0a.375.375 0 11-.75 0 .375.375 0 01.75 0z" />
            </svg>
          </div>
          <h1 className="text-2xl font-bold text-gray-900">Mpango</h1>
          <p className="mt-1 text-sm text-gray-500">
            Sign in to order from your supplier
          </p>
        </div>

        <form
          onSubmit={handleSubmit(onSubmit)}
          className="space-y-5 rounded-2xl bg-white p-6 shadow-xl"
          noValidate
        >
          {serverError && (
            <div className="rounded-lg bg-red-50 p-3 text-sm text-red-700">
              {serverError}
            </div>
          )}

          <div>
            <label htmlFor="email" className="mb-1 block text-sm font-medium text-gray-700">
              Email
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              placeholder="you@example.com"
              className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm shadow-sm focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none transition"
              {...register('email')}
            />
            {errors.email && (
              <p className="mt-1 text-xs text-red-600">{errors.email.message}</p>
            )}
          </div>

          <div>
            <label htmlFor="password" className="mb-1 block text-sm font-medium text-gray-700">
              Password
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              placeholder="••••••••"
              className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm shadow-sm focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none transition"
              {...register('password')}
            />
            {errors.password && (
              <p className="mt-1 text-xs text-red-600">{errors.password.message}</p>
            )}
          </div>

          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full rounded-lg bg-primary-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition"
          >
            {isSubmitting ? 'Signing in...' : 'Sign In'}
          </button>
        </form>
      </div>
    </div>
  );
}
