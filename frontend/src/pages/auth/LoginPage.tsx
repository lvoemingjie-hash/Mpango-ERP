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
  tenant_code: z
    .string()
    .min(1, 'Tenant code is required')
    .max(32, 'Tenant code must be 32 characters or less'),
  email: z.string().email('Please enter a valid email address'),
  password: z.string().min(6, 'Password must be at least 6 characters'),
});

type LoginFormData = z.infer<typeof loginSchema>;

export function LoginPage() {
  const navigate = useNavigate();
  const login = useAuthStore((s) => s.login);
  const tenantCode = useAuthStore((s) => s.tenantCode);
  const [serverError, setServerError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
    defaultValues: {
      tenant_code: tenantCode ?? '',
      email: '',
      password: '',
    },
  });

  const onSubmit = async (formData: LoginFormData) => {
    setServerError(null);

    try {
      // 1. Login — get tokens
      const loginRes = await authService.login(formData);
      const tokens = loginRes.data.data;

      // 2. Fetch user profile with the new token
      // Temporarily set token so the /me request is authenticated
      useAuthStore.getState().updateTokens({
        access_token: tokens.access_token,
        refresh_token: tokens.refresh_token,
      });

      const meRes = await authService.me();
      const user = meRes.data.data;

      // 3. Commit to store (persisted)
      login(tokens, user, formData.tenant_code);

      // 4. Navigate to dashboard
      navigate('/', { replace: true });
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

          {/* Tenant Code */}
          <div>
            <label
              htmlFor="tenant_code"
              className="mb-1 block text-sm font-medium text-gray-700"
            >
              Tenant Code
            </label>
            <input
              id="tenant_code"
              type="text"
              autoComplete="organization"
              placeholder="e.g. ACME01"
              className="input-field"
              {...register('tenant_code')}
            />
            {errors.tenant_code && (
              <p className="mt-1 text-xs text-red-600">
                {errors.tenant_code.message}
              </p>
            )}
          </div>

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
