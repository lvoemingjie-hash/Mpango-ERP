import { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { authService } from '@/services/authService';
import { readFragmentToken, type ReadTokenResult } from '@/utils/urlToken';

const setupSchema = z.object({
  password: z.string().min(8, 'Password must be at least 8 characters'),
});
type SetupFormData = z.infer<typeof setupSchema>;

/**
 * DC-12R1-S1 (+H2-A-R1): retailer credential setup page.
 *
 * Token transport is fragment-only (CTO decision):
 *  - a sensitive query param => reject, render Invalid Link, no API call;
 *  - otherwise read setupToken from location.hash, scrub the URL, submit via
 *    JSON body only. The token never enters localStorage/sessionStorage.
 *
 * R1: the setup email link also carries the supplier's PUBLIC portal code in
 * the fragment (#setupToken=...&w=CODE). It is captured BEFORE the scrub,
 * kept in memory, and used after a successful setup to hand the retailer to
 * /retail/login?w=<code>. Legacy links without w keep the previous behavior.
 */
export function RetailerSetupCredentialPage() {
  const location = useLocation();
  const [state, setState] = useState<ReadTokenResult>({ kind: 'missing' });
  const [serverError, setServerError] = useState<string | null>(null);
  const [isComplete, setIsComplete] = useState(false);
  // Public portal code from the fragment (validated; not a credential).
  const [portalCode, setPortalCode] = useState<string | null>(null);

  useEffect(() => {
    // Capture the non-secret portal param BEFORE readFragmentToken scrubs
    // the URL. Only ^[A-Z0-9]+$ is accepted (backend WHOLESALER_CODE_RE
    // parity); anything else is dropped, never rendered into a URL.
    const fragmentParams = new URLSearchParams(
      location.hash.startsWith('#') ? location.hash.slice(1) : location.hash,
    );
    const w = fragmentParams.get('w');
    if (w && /^[A-Z0-9]+$/.test(w)) {
      setPortalCode(w);
    }
    setState(readFragmentToken(location.search, location.hash, 'setupToken'));
  }, [location.search, location.hash]);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<SetupFormData>({
    resolver: zodResolver(setupSchema),
    defaultValues: { password: '' },
  });

  const onSubmit = async ({ password }: SetupFormData) => {
    setServerError(null);
    if (state.kind !== 'token') {
      setServerError('This setup link is invalid or expired. Please request a new link.');
      return;
    }
    try {
      await authService.retailerSetupCredential({ setupToken: state.token, newPassword: password });
      setIsComplete(true);
    } catch {
      setServerError('This setup link is invalid or expired. Please request a new link.');
    }
  };

  if (state.kind === 'rejected') {
    return <InvalidLink />;
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <h1 className="text-3xl font-bold text-primary-600">Set up your retailer password</h1>
          <p className="mt-2 text-sm text-gray-500">
            Choose a password to activate your retailer account.
          </p>
        </div>
        <div className="space-y-5 rounded-xl bg-white p-6 shadow-sm">
          {isComplete ? (
            <div className="space-y-4 text-center">
              <p className="text-sm text-gray-700">
                {portalCode
                  ? 'Your retailer account is ready. Sign in to your supplier portal.'
                  : 'Your retailer account is ready.'}
              </p>
              {portalCode ? (
                <Link
                  to={`/retail/login?w=${encodeURIComponent(portalCode)}`}
                  className="btn-primary inline-flex justify-center px-4 py-2"
                >
                  Go to supplier portal sign in
                </Link>
              ) : (
                <Link to="/login" className="btn-primary inline-flex justify-center px-4 py-2">
                  Go to login
                </Link>
              )}
            </div>
          ) : state.kind === 'missing' ? (
            <InvalidLink />
          ) : (
            <form onSubmit={handleSubmit(onSubmit)} className="space-y-5" noValidate>
              {serverError && (
                <div className="rounded-md bg-red-50 p-3 text-sm text-red-700">{serverError}</div>
              )}
              <div>
                <label htmlFor="password" className="mb-1 block text-sm font-medium text-gray-700">
                  Password
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
                {isSubmitting ? 'Setting up...' : 'Set password'}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}

function InvalidLink() {
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
              This setup link is no longer valid. Please contact your wholesaler for a new invitation.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
