import { useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { authService } from '@/services/authService';

/**
 * Wholesaler portal codes follow the DB regex ^[A-Z0-9]+$ (same semantics as
 * ClientLoginPage). A missing or malformed `w` param shows a controlled
 * invalid-portal state and performs ZERO recovery API calls.
 */
const WHOLESALER_CODE_RE = /^[A-Z0-9]+$/;

const forgotSchema = z.object({
  email: z.string().email('Please enter a valid email address'),
});
type ForgotFormData = z.infer<typeof forgotSchema>;

/**
 * DC-12R1-MVP-L1-J1-H2-C-R1: public retailer forgot-password page.
 *
 * Discovery entry: /retailer/forgot-password?w=<NORMALIZED_CODE>. The portal
 * code is normalized exactly like ClientLoginPage (trim -> UPPERCASE ->
 * ^[A-Z0-9]+$). Only the existing authService.retailerForgotPassword call is
 * used; the UI result is a FIXED neutral message for every outcome and never
 * renders account-existence information or raw API errors.
 */
export function RetailerForgotPasswordPage() {
  const [searchParams] = useSearchParams();
  const rawCode = searchParams.get('w') ?? '';
  const portalCode = rawCode.trim().toUpperCase();
  const isValidPortal = portalCode.length > 0 && WHOLESALER_CODE_RE.test(portalCode);

  const [serverError, setServerError] = useState<string | null>(null);
  const [isDone, setIsDone] = useState(false);
  // Synchronous in-flight guard: a fast double click can only ever produce
  // ONE recovery POST, even before react-hook-form re-renders with
  // isSubmitting.
  const submitInFlight = useRef(false);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ForgotFormData>({
    resolver: zodResolver(forgotSchema),
    defaultValues: { email: '' },
  });

  const onSubmit = async ({ email }: ForgotFormData) => {
    if (submitInFlight.current) return;
    submitInFlight.current = true;
    setServerError(null);
    try {
      await authService.retailerForgotPassword({
        email,
        wholesalerCode: portalCode,
      });
      setIsDone(true);
    } catch {
      // Fixed neutral copy only: never surface the raw error, response body,
      // or any account-existence signal.
      setServerError('Something went wrong. Please try again.');
    } finally {
      submitInFlight.current = false;
    }
  };

  // Controlled invalid-portal state: zero recovery POSTs.
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
          <h1 className="text-2xl font-bold text-gray-900">Reset your password</h1>
          <p className="mt-1 text-sm text-gray-500">
            Enter your account email and we will send a reset link.
          </p>
        </div>

        <div className="space-y-5 rounded-2xl bg-white p-6 shadow-xl">
          {isDone ? (
            <p className="text-sm text-gray-700" data-testid="forgot-neutral-result">
              If an account exists for this email at this supplier, a password reset link has been sent.
            </p>
          ) : (
            <form onSubmit={handleSubmit(onSubmit)} className="space-y-5" noValidate>
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

              <button
                type="submit"
                disabled={isSubmitting}
                className="w-full rounded-lg bg-primary-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition"
              >
                {isSubmitting ? 'Sending...' : 'Send reset link'}
              </button>
            </form>
          )}

          <p className="text-center text-sm">
            <Link
              to={`/retail/login?w=${portalCode}`}
              className="font-medium text-primary-600 hover:text-primary-500"
            >
              Back to sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
