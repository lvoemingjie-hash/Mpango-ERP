import { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { AxiosError } from 'axios';
import { useAuthStore } from '@/stores/authStore';
import { authService } from '@/services/authService';
import type { ApiErrorResponse } from '@/types/api';

const loginSchema = z.object({
  email: z.string().email('Please enter a valid email address'),
  password: z.string().min(6, 'Password must be at least 6 characters'),
});

type LoginFormData = z.infer<typeof loginSchema>;

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const login = useAuthStore((s) => s.login);
  const [serverError, setServerError] = useState<string | null>(null);

  // Extract tenant code from URL query string
  const queryParams = new URLSearchParams(location.search);
  const urlTenantCode = queryParams.get('tenant_code');

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
    defaultValues: {
      email: '',
      password: '',
    },
  });

  const onSubmit = async (formData: LoginFormData) => {
    setServerError(null);

    try {
      // 1. Identity Phase — get identity tokens + available tenants
      const loginRes = await authService.login(formData);
      const identityData = loginRes.data.data;

      // Keep identity token in a local variable — do NOT store in global
      // auth store yet, because ProtectedRoute checks accessToken and would
      // render dashboard components before tenant selection completes.
      const idToken = identityData.access_token;

      // Task 2: Routing Logic
      if (identityData.roles.includes('super_admin')) {
        // Condition A: Super Admin goes directly to dashboard (which handles system perms)
        const meRes = await authService.me(idToken);
        login(identityData, meRes.data.data, null);
        navigate('/', { replace: true });
        return;
      }

      if (identityData.available_tenants.length === 1) {
        // Condition B: Single Tenant -> auto select
        const tenant = identityData.available_tenants[0];
        const ctxRes = await authService.selectTenant({ tenant_id: tenant.id }, idToken);
        const ctxTokens = ctxRes.data.data;

        const meRes = await authService.me(ctxTokens.access_token);
        login(ctxTokens, meRes.data.data, tenant.code);
        navigate('/', { replace: true });
        return;
      }

      if (identityData.available_tenants.length > 1) {
        // Condition C: Multi-Tenant -> handle invite code auto-resolution or redirect to workspace selector
        if (urlTenantCode) {
          const matchedTenant = identityData.available_tenants.find(t => t.code === urlTenantCode);
          if (matchedTenant) {
            const ctxRes = await authService.selectTenant({ tenant_id: matchedTenant.id }, idToken);
            const ctxTokens = ctxRes.data.data;

            const meRes = await authService.me(ctxTokens.access_token);
            login(ctxTokens, meRes.data.data, matchedTenant.code);
            navigate('/', { replace: true });
            return;
          }
        }

        // Store identity token only for workspace selector navigation —
        // this is the one case where we need the token in the store before
        // tenant selection, but the target page is /select-workspace, not /.
        useAuthStore.getState().updateTokens({
          access_token: identityData.access_token,
          refresh_token: identityData.refresh_token,
        });
        navigate('/select-workspace', {
          replace: true,
          state: { availableTenants: identityData.available_tenants }
        });
        return;
      }

      // Condition D: Cold Start -> no tenants
      navigate('/onboarding/create-tenant', { replace: true });

    } catch (err) {
      const axiosErr = err as AxiosError<ApiErrorResponse>;
      const detail = axiosErr.response?.data;

      if (detail && 'error' in detail) {
        setServerError(detail.error.message);
      } else if (axiosErr.message) {
        setServerError(axiosErr.message);
      } else {
        setServerError('An unexpected error occurred. Please try again.');
      }

      // Clear partial tokens on failure
      useAuthStore.getState().logout();
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <h1 className="text-3xl font-bold text-primary-600">Mpango ERP</h1>
          <p className="mt-2 text-sm text-gray-500">
            Sign in to your account
          </p>
        </div>

        <form
          onSubmit={handleSubmit(onSubmit)}
          className="space-y-5 rounded-xl bg-white p-6 shadow-sm"
          noValidate
        >
          {serverError && (
            <div className="rounded-md bg-red-50 p-3 text-sm text-red-700">
              {serverError}
            </div>
          )}

          {/* Email */}
          <div>
            <label
              htmlFor="email"
              className="mb-1 block text-sm font-medium text-gray-700"
            >
              Email
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              placeholder="admin@acme.com"
              className="input-field"
              {...register('email')}
            />
            {errors.email && (
              <p className="mt-1 text-xs text-red-600">
                {errors.email.message}
              </p>
            )}
          </div>

          {/* Password */}
          <div>
            <label
              htmlFor="password"
              className="mb-1 block text-sm font-medium text-gray-700"
            >
              Password
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              placeholder="••••••••"
              className="input-field"
              {...register('password')}
            />
            {errors.password && (
              <p className="mt-1 text-xs text-red-600">
                {errors.password.message}
              </p>
            )}
          </div>

          {/* Submit */}
          <button
            type="submit"
            disabled={isSubmitting}
            className="btn-primary w-full disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isSubmitting ? 'Signing in…' : 'Sign In'}
          </button>
        </form>
      </div>
    </div>
  );
}
