import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
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

export function ClientLoginPage() {
  const navigate = useNavigate();
  const login = useAuthStore((s) => s.login);
  const [serverError, setServerError] = useState<string | null>(null);

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

    try {
      // 1. Identity Phase
      const loginRes = await authService.login(formData);
      const identityData = loginRes.data.data;
      const idToken = identityData.access_token;

      // 2. Auto-select first tenant (retailer typically has 1 tenant)
      if (identityData.available_tenants.length === 0) {
        setServerError('No supplier accounts linked. Please contact your supplier.');
        return;
      }

      const tenant = identityData.available_tenants[0];
      const ctxRes = await authService.selectTenant({ tenant_id: tenant.id }, idToken);
      const ctxTokens = ctxRes.data.data;

      const meRes = await authService.me(ctxTokens.access_token);
      login(ctxTokens, meRes.data.data, tenant.code);
      navigate('/client', { replace: true });
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

      useAuthStore.getState().logout();
    }
  };

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
            Sign in to order from your suppliers
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
