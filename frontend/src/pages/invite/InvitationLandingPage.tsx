import { useEffect, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { invitationService, type InvitationLookupData } from '@/services/invitationService';
import { retailerService } from '@/services/retailerService';
import { readFragmentToken, type ReadTokenResult } from '@/utils/urlToken';

/**
 * DC-12R1-MVP-L1-J1-H2-A: public invitation landing page — the retailer
 * CONSUMPTION end of the invitation funnel.
 *
 * Canonical entry: `/invite#code=<opaque-code>` (fragment-only credential
 * transport, same CTO contract as the retailer credential pages):
 *  1. a `code` in the query string (or any other sensitive query param) is
 *     REJECTED — invalid-link state, zero API calls;
 *  2. otherwise the code is read from the fragment and the URL is scrubbed
 *     immediately (replaceState) so the code never stays in the address bar,
 *     history, or referrer;
 *  3. the code is then used ONLY inside JSON bodies: POST /invitations/lookup
 *     and POST /retailers/register. No path-token or query-token request is
 *     ever issued from this page;
 *  4. the code lives only in component memory — never localStorage or
 *     sessionStorage.
 *
 * The legacy `/invite/:code` page (path token) remains mounted as a
 * DEPRECATED compatibility entry; this page is the only format new UI
 * generates.
 */

const LOOKUP_FAILURE_COPY = 'We could not verify this invitation. Please try again later.';
const REGISTER_FAILURE_COPY =
  'We could not complete your registration. Please check your details and try again.';

type Stage =
  | { kind: 'checking' }
  | { kind: 'invalid-link' }
  | { kind: 'unusable' }
  | { kind: 'ready'; lookup: InvitationLookupData }
  | { kind: 'registered' }
  | { kind: 'lookup-failed' };

export function InvitationLandingPage() {
  const location = useLocation();
  const [stage, setStage] = useState<Stage>({ kind: 'checking' });
  // Code in short-lived memory state only (never persisted to storage).
  const [code, setCode] = useState<string | null>(null);
  const [lookup, setLookup] = useState<InvitationLookupData | null>(null);

  useEffect(() => {
    // Capture the fragment ONCE on mount, then scrub the URL synchronously.
    const result: ReadTokenResult = readFragmentToken(
      location.search,
      location.hash,
      'code',
    );
    if (result.kind === 'rejected') {
      setStage({ kind: 'invalid-link' });
      return;
    }
    if (result.kind === 'missing') {
      setStage({ kind: 'invalid-link' });
      return;
    }
    setCode(result.token);

    let cancelled = false;
    (async () => {
      try {
        // Code travels ONLY in the JSON body — never a path/query param.
        const res = await invitationService.lookup(result.token);
        if (cancelled) return;
        setLookup(res.data);
        setStage(
          res.data.usable
            ? { kind: 'ready', lookup: res.data }
            : { kind: 'unusable' },
        );
      } catch {
        if (!cancelled) setStage({ kind: 'lookup-failed' });
      }
    })();

    return () => {
      cancelled = true;
    };
    // Intentionally mount-once: the fragment is consumed on first paint; a
    // dependency on location.hash would re-read an already-scrubbed URL.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-md">
        <div className="mb-6 text-center">
          <h1 className="text-3xl font-bold text-primary-600">Mpango ERP</h1>
          <p className="mt-2 text-sm text-gray-500">Retailer Registration</p>
        </div>

        <div className="rounded-xl bg-white p-6 shadow-sm">
          {stage.kind === 'checking' && (
            <p className="text-center text-sm text-gray-400">
              Verifying invitation…
            </p>
          )}

          {stage.kind === 'invalid-link' && <InvalidLink />}

          {stage.kind === 'lookup-failed' && (
            <div className="text-center">
              <h2 className="text-lg font-semibold text-gray-900">
                Unable to verify invitation
              </h2>
              <p className="mt-2 text-sm text-gray-500">{LOOKUP_FAILURE_COPY}</p>
              <button
                type="button"
                onClick={() => window.location.reload()}
                className="btn-primary mt-4 inline-block text-sm"
              >
                Try again
              </button>
            </div>
          )}

          {stage.kind === 'unusable' && (
            <div className="text-center">
              <h2 className="text-lg font-semibold text-gray-900">
                Invitation Unavailable
              </h2>
              <p className="mt-2 text-sm text-gray-500">
                This invitation can no longer be used. Please ask your supplier
                for a new invitation.
              </p>
              {lookup?.expires_at && (
                <p className="mt-1 text-xs text-gray-400">
                  Expired: {new Date(lookup.expires_at).toLocaleString()}
                </p>
              )}
            </div>
          )}

          {stage.kind === 'ready' && (
            <RegisterPanel
              lookup={stage.lookup}
              code={code ?? stage.lookup.code}
              onRegistered={() => setStage({ kind: 'registered' })}
            />
          )}

          {stage.kind === 'registered' && <RegisteredGuidance />}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Register form (usable invitation)
// ---------------------------------------------------------------------------

const registerSchema = z.object({
  phone: z.string().min(1, 'Phone is required').max(32, 'Phone must be at most 32 characters'),
  name: z.string().max(255, 'Name must be at most 255 characters').optional().or(z.literal('')),
  email: z.string().email('Enter a valid email').optional().or(z.literal('')),
  address: z.string().max(255, 'Address must be at most 255 characters').optional().or(z.literal('')),
});

type RegisterFormData = z.infer<typeof registerSchema>;

function RegisterPanel({
  lookup,
  code,
  onRegistered,
}: {
  lookup: InvitationLookupData;
  code: string;
  onRegistered: () => void;
}) {
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<RegisterFormData>({
    resolver: zodResolver(registerSchema),
    defaultValues: { phone: '', name: '', email: '', address: '' },
  });

  const [serverError, setServerError] = useState<string | null>(null);
  // Synchronous in-flight lock: exactly one POST per submit even on double
  // clicks (an invitation can only ever be accepted once — a second POST
  // would surface INVITATION_ALREADY_USED instead of a quiet success).
  const inFlight = useRef(false);

  const onSubmit = async (values: RegisterFormData) => {
    if (inFlight.current) return;
    inFlight.current = true;
    setServerError(null);
    try {
      await retailerService.registerWithInvitation({
        // invitation_code travels ONLY in the JSON body.
        invitation_code: code,
        phone: values.phone.trim(),
        name: values.name?.trim() || undefined,
        email: values.email?.trim() || undefined,
        address: values.address?.trim() || undefined,
      });
      onRegistered();
    } catch {
      // Fixed neutral copy — no backend message/code echo.
      setServerError(REGISTER_FAILURE_COPY);
    } finally {
      inFlight.current = false;
    }
  };

  return (
    <div>
      <div className="text-center">
        <h2 className="text-lg font-semibold text-gray-900">You&apos;re Invited!</h2>
        {lookup.wholesaler_name && (
          <p className="mt-1 text-sm font-medium text-primary-600">
            {lookup.wholesaler_name}
          </p>
        )}
        <p className="mt-2 text-sm text-gray-500">
          Complete your registration to join your supplier.
        </p>
        {lookup.expires_at && (
          <p className="mt-1 text-xs text-gray-400">
            Expires: {new Date(lookup.expires_at).toLocaleString()}
          </p>
        )}
      </div>

      <form onSubmit={handleSubmit(onSubmit)} className="mt-4 space-y-4" noValidate>
        {serverError && (
          <div role="alert" className="rounded-md bg-red-50 p-3 text-sm text-red-700">
            {serverError}
          </div>
        )}

        <div>
          <label htmlFor="phone" className="mb-1 block text-sm font-medium text-gray-700">
            Phone <span className="text-red-600">*</span>
          </label>
          <input
            id="phone"
            type="tel"
            autoComplete="tel"
            className="input-field"
            {...register('phone')}
          />
          {errors.phone && (
            <p className="mt-1 text-xs text-red-600">{errors.phone.message}</p>
          )}
        </div>

        <div>
          <label htmlFor="name" className="mb-1 block text-sm font-medium text-gray-700">
            Business name (optional)
          </label>
          <input
            id="name"
            type="text"
            autoComplete="organization"
            className="input-field"
            {...register('name')}
          />
        </div>

        <div>
          <label htmlFor="email" className="mb-1 block text-sm font-medium text-gray-700">
            Email (optional)
          </label>
          <input
            id="email"
            type="email"
            autoComplete="email"
            className="input-field"
            aria-describedby="email_hint"
            {...register('email')}
          />
          <p id="email_hint" className="mt-1 text-xs text-gray-500">
            Needed to receive your password setup email.
          </p>
          {errors.email && (
            <p className="mt-1 text-xs text-red-600">{errors.email.message}</p>
          )}
        </div>

        <div>
          <label htmlFor="address" className="mb-1 block text-sm font-medium text-gray-700">
            Address (optional)
          </label>
          <input
            id="address"
            type="text"
            autoComplete="street-address"
            className="input-field"
            {...register('address')}
          />
        </div>

        <button
          type="submit"
          disabled={isSubmitting}
          className="btn-primary w-full disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isSubmitting ? 'Registering…' : 'Complete registration'}
        </button>
      </form>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Post-registration guidance (register → setup-credential → login lifecycle)
// ---------------------------------------------------------------------------

function RegisteredGuidance() {
  return (
    <div className="space-y-4 text-center">
      <h2 className="text-lg font-semibold text-gray-900">Registration complete</h2>
      <p className="text-sm text-gray-600">
        We have sent you an email with a link to set your password. Open that
        link to activate your account.
      </p>
      <p className="text-sm text-gray-600">
        After setting your password, sign in from your supplier&apos;s portal
        link (the address your supplier shared with you).
      </p>
      <Link
        to="/retail/login"
        className="btn-primary inline-block text-sm"
      >
        Go to retailer sign in
      </Link>
    </div>
  );
}

function InvalidLink() {
  return (
    <div className="text-center">
      <svg
        className="mx-auto h-12 w-12 text-red-600"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="2"
          d="M6 18L18 6M6 6l12 12"
        />
      </svg>
      <h2 className="mt-4 text-xl font-bold text-gray-900">Invalid Link</h2>
      <p className="mt-2 text-sm text-gray-600">
        This invitation link is not valid. Please contact your supplier for a
        new invitation.
      </p>
    </div>
  );
}
