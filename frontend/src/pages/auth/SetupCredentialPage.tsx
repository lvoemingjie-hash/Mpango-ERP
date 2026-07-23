import { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { authService } from '@/services/authService';

const setupCredentialSchema = z.object({
  password: z.string().min(8, 'Password must be at least 8 characters'),
});

type SetupCredentialFormData = z.infer<typeof setupCredentialSchema>;

export function SetupCredentialPage() {
  const location = useLocation();
  const [setupToken, setSetupToken] = useState<string | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  const [isComplete, setIsComplete] = useState(false);
  const [queryRejected, setQueryRejected] = useState(false);

  useEffect(() => {
    // DC-12A-R3: Read token from URL fragment ONLY.
    const hash = location.hash;
    const fragmentParams = new URLSearchParams(hash.startsWith('#') ? hash.slice(1) : hash);
    const token = fragmentParams.get('setupToken');

    // DC-12A-R3: Query-string tokens are rejected.
    // Scrub URL, show controlled invalid-link state, never submit.
    const queryToken = new URLSearchParams(location.search).get('setupToken');
    if (queryToken && !token) {
      window.history.replaceState(window.history.state, document.title, location.pathname);
      setQueryRejected(true);
      return;
    }

    setSetupToken(token);
    if (token) {
      window.history.replaceState(window.history.state, document.title, location.pathname);
    }
  }, [location.hash, location.pathname, location.search]);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<SetupCredentialFormData>({
    resolver: zodResolver(setupCredentialSchema),
    defaultValues: { password: '' },
  });

  const onSubmit = async ({ password }: SetupCredentialFormData) => {
    setServerError(null);
    if (!setupToken) {
      setServerError('This setup link is invalid or expired. Please request a new link.');
      return;
    }

    try {
      await authService.setupCredential({ setupToken, password });
      setIsComplete(true);
    } catch {
      setServerError('This setup link is invalid or expired. Please request a new link.');
    }
  };

  if (queryRejected) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
        <div className="w-full max-w-sm">
          <div className="space-y-5 rounded-xl bg-white p-6 shadow-sm">
            <div className="text-center">
              <svg className="mx-auto h-12 w-12 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
              <h2 className="mt-4 text-xl font-bold text-gray-900">Invalid Link</h2>
              <p className="mt-2 text-sm text-gray-600">
                This setup link is no longer valid. Please use the latest link from your email.
              </p>
              <Link to="/login" className="btn-primary mt-4 inline-flex justify-center px-4 py-2">
                Go to login
              </Link>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <h1 className="text-3xl font-bold text-primary-600">Set your password</h1>
          <p className="mt-2 text-sm text-gray-500">
            Create a password to finish setting up your account.
          </p>
        </div>

        <div className="space-y-5 rounded-xl bg-white p-6 shadow-sm">
          {isComplete ? (
            <div className="space-y-4 text-center">
              <p className="text-sm text-gray-700">Your password has been set successfully.</p>
              <Link to="/login" className="btn-primary inline-flex justify-center px-4 py-2">
                Go to login
              </Link>
            </div>
          ) : (
            <form onSubmit={handleSubmit(onSubmit)} className="space-y-5" noValidate>
              {serverError && (
                <div className="rounded-md bg-red-50 p-3 text-sm text-red-700">
                  {serverError}
                </div>
              )}

              <div>
                <label htmlFor="password" className="mb-1 block text-sm font-medium text-gray-700">
                  New password
                </label>
                <input
                  id="password"
                  type="password"
                  autoComplete="new-password"
                  className="input-field"
                  {...register('password')}
                />
                {errors.password && (
                  <p className="mt-1 text-xs text-red-600">{errors.password.message}</p>
                )}
              </div>

              <button
                type="submit"
                disabled={isSubmitting}
                className="btn-primary w-full disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isSubmitting ? 'Saving password...' : 'Set password'}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
