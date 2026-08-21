import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { invitationService, type InvitationLookupData } from '@/services/invitationService';
import { retailerService } from '@/services/retailerService';
import { readFragmentToken, type ReadTokenResult } from '@/utils/urlToken';

/**
 * DC-12R1-MVP-L1-J1-H2-A (+R1): public invitation landing page — the
 * retailer CONSUMPTION end of the invitation funnel.
 *
 * Canonical entry: `/invite#code=<opaque-code>` (fragment-only credential
 * transport, same CTO contract as the retailer credential pages):
 *  1. a `code` in the query string (or any other sensitive query param) is
 *     REJECTED — invalid-link state, zero API calls;
 *  2. otherwise the code is read from the fragment and the URL is scrubbed
 *     immediately (replaceState) so the code never stays in the address bar,
 *     history, or referrer;
 *  3. the code is then used ONLY inside JSON bodies: POST /invitations/lookup
 *     and POST /retailers/register (both sent with an explicitly EMPTY
 *     Authorization header and full interceptor opt-out — a logged-in
 *     session can never leak into, or be hijacked by, these public calls);
 *  4. the code lives only in component memory — never localStorage or
 *     sessionStorage. Lookup RETRY re-POSTs from this in-memory code; the
 *     page never reloads.
 *
 * R1 lifecycle contract:
 *  - the register form requires EMAIL (the backend credential lifecycle
 *    needs it to deliver the setup-password email; a no-email submission is
 *    blocked client-side and never reaches the backend);
 *  - the lookup response must carry a verifiable `wholesaler_code`
 *    (^[A-Z0-9]+$ — parity with the backend WHOLESALER_CODE_RE); an unusable
 *    or unverifiable code never renders the register form;
 *  - after registration the guidance hands off to the real supplier portal
 *    login `/retail/login?w=<verified-wholesaler-code>`.
 *
 * The legacy `/invite/:code` page (path token) remains mounted as a
 * DEPRECATED compatibility entry; this page is the only format new UI
 * generates.
 */

const LOOKUP_FAILURE_COPY = 'We could not verify this invitation. Please try again later.';
const REGISTER_FAILURE_COPY =
  'We could not complete your registration. Please check your details and try again.';

/** Parity with backend WHOLESALER_CODE_RE (schemas/retailer_credentials.py). */
const WHOLESALER_CODE_RE = /^[A-Z0-9]+$/;

/** Verified portal code — only ever derived from a validated lookup field. */
function verifyWholesalerCode(code: unknown): string | null {
  return typeof code === 'string' && WHOLESALER_CODE_RE.test(code) ? code : null;
}

type Stage =
  | { kind: 'checking' }
  | { kind: 'invalid-link' }
  | { kind: 'unusable' }
  | { kind: 'ready'; lookup: InvitationLookupData; portalCode: string }
  | { kind: 'registered'; portalCode: string }
  | { kind: 'lookup-failed' };

export function InvitationLandingPage() {
  const location = useLocation();
  const [stage, setStage] = useState<Stage>({ kind: 'checking' });
  // Code in short-lived memory state only (never persisted to storage).
  // Kept across lookup RETRIES — a retry re-POSTs from memory, never a
  // window reload (a reload would lose the scrubbed fragment forever).
  const codeRef = useRef<string | null>(null);
  const [lookup, setLookup] = useState<InvitationLookupData | null>(null);

  const runLookup = useCallback(async (code: string) => {
    try {
      // Code travels ONLY in the JSON body — never a path/query param.
      const res = await invitationService.lookup(code);
      setLookup(res.data);
      const portalCode = verifyWholesalerCode(res.data.wholesaler_code);
      if (res.data.usable && portalCode) {
        setStage({ kind: 'ready', lookup: res.data, portalCode });
      } else if (res.data.usable && !portalCode) {
        // Usable invitation but an unverifiable portal code: the login
        // handoff cannot be built safely — fail closed, neutral copy.
        setStage({ kind: 'lookup-failed' });
      } else {
        setStage({ kind: 'unusable' });
      }
    } catch {
      setStage({ kind: 'lookup-failed' });
    }
  }, []);

  useEffect(() => {
    // Capture the fragment ONCE on mount, then scrub the URL synchronously.
    const result: ReadTokenResult = readFragmentToken(
      location.search,
      location.hash,
      'code',
    );
    if (result.kind === 'rejected' || result.kind === 'missing') {
      setStage({ kind: 'invalid-link' });
      return;
    }
    codeRef.current = result.token;
    void runLookup(result.token);
    // Intentionally mount-once: the fragment is consumed on first paint; a
    // dependency on location.hash would re-read an already-scrubbed URL.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onRetry = () => {
    // R1: retry re-POSTs the in-memory code. No reload — the URL fragment
    // is already scrubbed and can never be re-read.
    if (codeRef.current) {
      setStage({ kind: 'checking' });
      void runLookup(codeRef.current);
    } else {
      setStage({ kind: 'invalid-link' });
    }
  };

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
              <button type="button" onClick={onRetry} className="btn-primary mt-4 inline-block text-sm">
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
              code={codeRef.current ?? stage.lookup.code}
              onRegistered={() =>
                setStage({ kind: 'registered', portalCode: stage.portalCode })
              }
            />
          )}

          {stage.kind === 'registered' && (
            <RegisteredGuidance portalCode={stage.portalCode} />
          )}
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
  // R1: email REQUIRED — the backend credential lifecycle delivers the
  // setup-password email to this address; a no-email submission is blocked
  // here and never reaches POST /retailers/register.
  email: z.string().min(1, 'Email is required').email('Enter a valid email'),
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
        email: values.email.trim().toLowerCase(),
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
            Email <span className="text-red-600">*</span>
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
            Your password setup email is delivered here — it is required.
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

function RegisteredGuidance({ portalCode }: { portalCode: string }) {
  return (
    <div className="space-y-4 text-center">
      <h2 className="text-lg font-semibold text-gray-900">Registration complete</h2>
      <p className="text-sm text-gray-600">
        We have sent you an email with a link to set your password. Open that
        link to activate your account.
      </p>
      <p className="text-sm text-gray-600">
        After setting your password, sign in to your supplier&apos;s portal
        below.
      </p>
      {/* R1: verified portal handoff — w is the validated wholesaler_code
          from the lookup response, never a raw user-controlled value. */}
      <Link to={`/retail/login?w=${encodeURIComponent(portalCode)}`} className="btn-primary inline-block text-sm">
        Go to supplier portal sign in
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
