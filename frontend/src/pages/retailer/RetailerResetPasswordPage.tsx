import { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { authService } from '@/services/authService';
import { readFragmentToken, type ReadTokenResult } from '@/utils/urlToken';

/**
 * Wholesaler portal codes follow the DB regex ^[A-Z0-9]+$ (same semantics as
 * ClientLoginPage). `w` is a PUBLIC code: it may appear in the initial
 * fragment and, after a successful reset, in the canonical
 * /retail/login?w=<CODE> URL. It never enters the reset POST body, storage,
 * or logs.
 */
const WHOLESALER_CODE_RE = /^[A-Z0-9]+$/;

const resetSchema = z.object({
  newPassword: z.string().min(8, 'Password must be at least 8 characters'),
});
type ResetFormData = z.infer<typeof resetSchema>;

/**
 * DC-12R1-S1: retailer password-reset page (self-service).
 *
 * Fragment-only token transport, identical strict policy to the setup page:
 * sensitive query param => reject; otherwise read resetToken from the fragment,
 * scrub the URL, submit via JSON body only.
 *
 * H2-C-R1: the public `w` code is read from the SAME pre-scrub fragment and
 * kept in memory only. With a valid `w` the success CTA returns the retailer
 * to /retail/login?w=<CODE>. A legacy link (no usable `w`) still allows a
 * valid token to complete the reset; its success state shows only the neutral
 * "return to the portal link your supplier provided" guidance — never the
 * wholesaler /login, never a guessed portal.
 */
export function RetailerResetPasswordPage() {
  const location = useLocation();
  const [state, setState] = useState<ReadTokenResult>({ kind: 'missing' });
  const [portalCode, setPortalCode] = useState<string | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  const [isComplete, setIsComplete] = useState(false);

  useEffect(() => {
    // Both reads use the same pre-scrub fragment: readFragmentToken scrubs
    // the URL as a side effect when a token is found, so `w` MUST be parsed
    // from location.hash before/alongside that call, never after.
    const fragmentParams = new URLSearchParams(
      location.hash.startsWith('#') ? location.hash.slice(1) : location.hash,
    );
    const rawCode = (fragmentParams.get('w') ?? '').trim().toUpperCase();
    setPortalCode(WHOLESALER_CODE_RE.test(rawCode) ? rawCode : null);
    setState(readFragmentToken(location.search, location.hash, 'resetToken'));
  }, [location.search, location.hash]);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ResetFormData>({
    resolver: zodResolver(resetSchema),
    defaultValues: { newPassword: '' },
  });

  const onSubmit = async ({ newPassword }: ResetFormData) => {
    setServerError(null);
    if (state.kind !== 'token') {
      setServerError('This reset link is invalid or expired. Please request a new link.');
      return;
    }
    try {
      // Body is reset_token + new_password only; the public `w` code and the
      // raw token never travel anywhere else.
      await authService.retailerResetPassword({ resetToken: state.token, newPassword });
      setIsComplete(true);
    } catch {
      setServerError('This reset link is invalid or expired. Please request a new link.');
    }
  };

  if (state.kind === 'rejected') {
    return <InvalidLink />;
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <h1 className="text-3xl font-bold text-primary-600">Reset your retailer password</h1>
          <p className="mt-2 text-sm text-gray-500">
            Enter a new password for your retailer account.
          </p>
        </div>
        <div className="space-y-5 rounded-xl bg-white p-6 shadow-sm">
          {isComplete ? (
            portalCode ? (
              <div className="space-y-4 text-center">
                <p className="text-sm text-gray-700">Your password has been reset successfully.</p>
                <Link
                  to={`/retail/login?w=${portalCode}`}
                  className="btn-primary inline-flex justify-center px-4 py-2"
                  data-testid="reset-success-portal-link"
                >
                  Back to sign in
                </Link>
              </div>
            ) : (
              // Legacy link (no usable `w`): neutral guidance only. No
              // wholesaler /login CTA and no portal guessing.
              <div className="space-y-4 text-center" data-testid="reset-success-legacy">
                <p className="text-sm text-gray-700">Your password has been reset successfully.</p>
                <p className="text-sm text-gray-500">
                  Return to the portal link your supplier provided to sign in.
                </p>
              </div>
            )
          ) : state.kind === 'missing' ? (
            <InvalidLink />
          ) : (
            <form onSubmit={handleSubmit(onSubmit)} className="space-y-5" noValidate>
              {serverError && (
                <div className="rounded-md bg-red-50 p-3 text-sm text-red-700">{serverError}</div>
              )}
              <div>
                <label htmlFor="newPassword" className="mb-1 block text-sm font-medium text-gray-700">
                  New password
                </label>
                <input
                  id="newPassword"
                  type="password"
                  autoComplete="new-password"
                  className="input-field"
                  {...register('newPassword')}
                />
                {errors.newPassword && (
                  <p className="mt-1 text-xs text-red-600">{errors.newPassword.message}</p>
                )}
              </div>
              <button
                type="submit"
                disabled={isSubmitting}
                className="btn-primary w-full disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isSubmitting ? 'Saving password...' : 'Reset password'}
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
              This reset link is no longer valid. Please request a new password reset.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
