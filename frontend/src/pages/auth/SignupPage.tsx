import { useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { authService } from '@/services/authService';

/**
 * DC-12R1-MVP-L1-J1-R1: public wholesaler self-service signup entry.
 *
 * Reuses the existing POST /auth/signup contract verbatim:
 *   - request fields/validation mirror backend schemas/auth_signup.py;
 *   - Idempotency-Key stays stable across failed submissions and is rotated
 *     only AFTER an accepted (2xx) success;
 *   - the 202 response is neutral and carries no tokens; nothing is ever
 *     written to localStorage/sessionStorage by this page;
 *   - accepted lifecycle: signup -> verify email -> setup credential ->
 *     login -> select tenant.
 */

// Mirrors backend SignupRequest (camelCase aliases accepted by Pydantic).
const signupSchema = z.object({
  companyName: z
    .string()
    .trim()
    .min(2, 'Company name must be at least 2 characters')
    .max(255, 'Company name must be at most 255 characters'),
  country: z
    .string()
    .trim()
    .regex(/^[A-Za-z]{2}$/, 'Country must be a 2-letter code (e.g. KE)')
    .transform((v) => v.toUpperCase()),
  email: z.string().trim().email('Please enter a valid email address'),
  password: z
    .string()
    .min(8, 'Password must be at least 8 characters')
    .max(128, 'Password must be at most 128 characters'),
  phone: z
    .string()
    .trim()
    .max(32, 'Phone must be at most 32 characters')
    .optional()
    .or(z.literal('')),
  businessType: z
    .string()
    .trim()
    .max(64, 'Business type must be at most 64 characters')
    .optional()
    .or(z.literal('')),
});

type SignupFormData = z.infer<typeof signupSchema>;

function newIdempotencyKey(): string {
  // crypto.randomUUID is available in all supported modern browsers.
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function SignupPage() {
  const [serverError, setServerError] = useState<string | null>(null);
  const [accepted, setAccepted] = useState(false);

  // Kept in component memory only. Stable across failures; rotated only
  // after an accepted success so a retry never reuses a consumed key and
  // a failure never burns one.
  const idempotencyKeyRef = useRef<string>(newIdempotencyKey());

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<SignupFormData>({
    resolver: zodResolver(signupSchema),
    defaultValues: {
      companyName: '',
      country: '',
      email: '',
      password: '',
      phone: '',
      businessType: '',
    },
  });

  const onSubmit = async (formData: SignupFormData) => {
    setServerError(null);

    const payload = {
      companyName: formData.companyName,
      country: formData.country,
      email: formData.email.toLowerCase(),
      password: formData.password,
      ...(formData.phone ? { phone: formData.phone } : {}),
      ...(formData.businessType ? { businessType: formData.businessType } : {}),
    };

    try {
      await authService.signup(payload, idempotencyKeyRef.current);
      // Accepted success: rotate the key for any future submission, then
      // show neutral email-verification guidance. Never navigate away with
      // any token — none exist in the 202 response.
      idempotencyKeyRef.current = newIdempotencyKey();
      setAccepted(true);
    } catch {
      // Neutral copy only. Never render the axios error, the backend
      // message, error codes, request_id, or any response body content —
      // the signup endpoint intentionally does not disclose whether the
      // email is already registered.
      setServerError('Unable to create your account. Please try again.');
      // Keep the same idempotencyKeyRef: a retry with identical payload is
      // a safe replay; rotating here would burn the key on a failure.
    }
  };

  if (accepted) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
        <div className="w-full max-w-sm">
          <div className="mb-8 text-center">
            <h1 className="text-3xl font-bold text-primary-600">Mpango ERP</h1>
            <p className="mt-2 text-sm text-gray-500">Wholesaler account</p>
          </div>
          <div
            className="space-y-5 rounded-xl bg-white p-6 shadow-sm"
            role="status"
          >
            <h2 className="text-lg font-semibold text-gray-900">
              Check your email
            </h2>
            <p className="text-sm text-gray-600">
              If this email can be used, verification instructions have been
              sent to it. Follow the link in the email to verify your address,
              set up your password, and sign in.
            </p>
            <div className="text-center text-sm">
              <Link
                to="/login"
                className="font-medium text-primary-600 hover:text-primary-700"
              >
                Back to sign in
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
          <h1 className="text-3xl font-bold text-primary-600">Mpango ERP</h1>
          <p className="mt-2 text-sm text-gray-500">
            Create your wholesaler account
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

          <div>
            <label
              htmlFor="companyName"
              className="mb-1 block text-sm font-medium text-gray-700"
            >
              Company name
            </label>
            <input
              id="companyName"
              type="text"
              autoComplete="organization"
              placeholder="Acme Trading Ltd"
              className="input-field"
              {...register('companyName')}
            />
            {errors.companyName && (
              <p className="mt-1 text-xs text-red-600">
                {errors.companyName.message}
              </p>
            )}
          </div>

          <div>
            <label
              htmlFor="country"
              className="mb-1 block text-sm font-medium text-gray-700"
            >
              Country (2-letter code)
            </label>
            <input
              id="country"
              type="text"
              autoComplete="country"
              placeholder="KE"
              className="input-field"
              {...register('country')}
            />
            {errors.country && (
              <p className="mt-1 text-xs text-red-600">
                {errors.country.message}
              </p>
            )}
          </div>

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
              placeholder="owner@acme.com"
              className="input-field"
              {...register('email')}
            />
            {errors.email && (
              <p className="mt-1 text-xs text-red-600">
                {errors.email.message}
              </p>
            )}
          </div>

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
              autoComplete="new-password"
              placeholder="At least 8 characters"
              className="input-field"
              {...register('password')}
            />
            {errors.password && (
              <p className="mt-1 text-xs text-red-600">
                {errors.password.message}
              </p>
            )}
          </div>

          <div>
            <label
              htmlFor="phone"
              className="mb-1 block text-sm font-medium text-gray-700"
            >
              Phone (optional)
            </label>
            <input
              id="phone"
              type="tel"
              autoComplete="tel"
              placeholder="+254 700 000 000"
              className="input-field"
              {...register('phone')}
            />
            {errors.phone && (
              <p className="mt-1 text-xs text-red-600">
                {errors.phone.message}
              </p>
            )}
          </div>

          <div>
            <label
              htmlFor="businessType"
              className="mb-1 block text-sm font-medium text-gray-700"
            >
              Business type (optional)
            </label>
            <input
              id="businessType"
              type="text"
              placeholder="Wholesale, distribution, retail..."
              className="input-field"
              {...register('businessType')}
            />
            {errors.businessType && (
              <p className="mt-1 text-xs text-red-600">
                {errors.businessType.message}
              </p>
            )}
          </div>

          <button
            type="submit"
            disabled={isSubmitting}
            className="btn-primary w-full disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isSubmitting ? 'Creating account...' : 'Create Account'}
          </button>

          <div className="text-center text-sm">
            <Link
              to="/login"
              className="font-medium text-primary-600 hover:text-primary-700"
            >
              Already have an account? Sign in
            </Link>
          </div>
        </form>
      </div>
    </div>
  );
}
