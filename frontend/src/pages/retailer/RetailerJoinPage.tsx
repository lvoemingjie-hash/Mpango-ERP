import { useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { selfJoinService, type WholesalerJoinPreview } from '@/services/selfJoinService';
import { retailerService } from '@/services/retailerService';
import { invitationService } from '@/services/invitationService';

/**
 * DC-12R1-MVP-L1-J1-H2-A-R1: /retail/join — dual-entry retailer self-join.
 *
 * Entry A (preferred): join via a wholesaler-shared invitation link/code
 * (the canonical link format remains /invite#code=<opaque>; pasting a link
 * or a bare code here re-uses the same POST /invitations/lookup).
 * Entry B (fallback): join by the supplier's PUBLIC portal code — a safe
 * preview (name / region / masked contact) plus a short-lived signed
 * join_intent is fetched, the retailer must EXPLICITLY confirm the
 * previewed supplier identity, and registration submits the signed intent
 * (never a client-chosen wholesaler id).
 *
 * Shared contracts:
 *  - email is REQUIRED (the setup-password email is the credential path);
 *  - every public call carries an explicitly EMPTY Authorization and full
 *    interceptor opt-out (no toast echo, no 401 refresh hijack);
 *  - after registration the guidance hands off to the SERVER-VERIFIED
 *    portal login /retail/login?w=<wholesaler_code from the register
 *    response> — never a guessed code, never a bare /retail/login;
 *  - credentials (invitation code, join_intent) live only in component
 *    memory; the URL is never used to carry them.
 */

const LOOKUP_FAILURE_COPY = 'We could not check that supplier code. Please try again.';
const REGISTER_FAILURE_COPY =
  'We could not complete your registration. Please check your details and try again.';

const WHOLESALER_CODE_RE = /^[A-Z0-9]+$/;

const codeSchema = z.object({
  supplierCode: z
    .string()
    .trim()
    .min(1, 'Enter your supplier code')
    .max(32, 'Code must be at most 32 characters')
    .refine((v) => WHOLESALER_CODE_RE.test(v.toUpperCase()), {
      message: 'Supplier codes use letters and numbers only',
    }),
});

type CodeFormData = z.infer<typeof codeSchema>;

const registerSchema = z.object({
  phone: z.string().min(1, 'Phone is required').max(32, 'Phone must be at most 32 characters'),
  name: z.string().max(255, 'Name must be at most 255 characters').optional().or(z.literal('')),
  email: z.string().min(1, 'Email is required').email('Enter a valid email'),
  address: z.string().max(255, 'Address must be at most 255 characters').optional().or(z.literal('')),
});

type RegisterFormData = z.infer<typeof registerSchema>;

type Stage =
  | { kind: 'entry' }
  | { kind: 'code-checking' }
  | { kind: 'code-failed' }
  | { kind: 'code-miss'; code: string }
  | { kind: 'preview'; preview: WholesalerJoinPreview }
  | { kind: 'invite-checking' }
  | { kind: 'invite-failed' }
  | { kind: 'invite-unusable' }
  | { kind: 'register'; mode: 'code' | 'invite'; intent?: string; invitationCode?: string; supplierName?: string | null }
  | { kind: 'registered'; portalCode: string };

export function RetailerJoinPage() {
  const [tab, setTab] = useState<'invite' | 'code'>('invite');
  const [stage, setStage] = useState<Stage>({ kind: 'entry' });

  // Entry A state (invitation).
  const [inviteInput, setInviteInput] = useState('');
  const [inviteError, setInviteError] = useState<string | null>(null);

  // Entry B state (supplier code) — form + preview confirm.
  const codeForm = useForm<CodeFormData>({
    resolver: zodResolver(codeSchema),
    defaultValues: { supplierCode: '' },
  });

  const onLookupCode = codeForm.handleSubmit(async ({ supplierCode }) => {
    setStage({ kind: 'code-checking' });
    try {
      const res = await selfJoinService.lookupByCode(supplierCode.trim().toUpperCase());
      if (!res.data.found) {
        setStage({ kind: 'code-miss', code: supplierCode.trim().toUpperCase() });
        return;
      }
      setStage({ kind: 'preview', preview: res.data });
    } catch {
      setStage({ kind: 'code-failed' });
    }
  });

  /** Accept a pasted invitation link or bare code (entry A). */
  const onInviteLookup = async () => {
    const raw = inviteInput.trim();
    let code: string | null = null;
    if (raw.includes('#')) {
      // Pasted link: only the FRAGMENT credential of a /invite link is
      // honored — never a query string (fragment-only transport contract).
      try {
        const fragment = raw.slice(raw.indexOf('#') + 1);
        const params = new URLSearchParams(fragment);
        code = params.get('code');
      } catch {
        code = null;
      }
    } else if (raw && raw.length <= 64) {
      code = raw;
    }
    if (!code) {
      setInviteError('Paste the invitation link or code your supplier shared.');
      return;
    }
    setInviteError(null);
    setStage({ kind: 'invite-checking' });
    try {
      const res = await invitationService.lookup(code);
      if (!res.data.usable) {
        setStage({ kind: 'invite-unusable' });
        return;
      }
      setStage({
        kind: 'register',
        mode: 'invite',
        invitationCode: code,
        supplierName: res.data.wholesaler_name ?? null,
      });
    } catch {
      setStage({ kind: 'invite-failed' });
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4 py-10">
      <div className="w-full max-w-md">
        <div className="mb-6 text-center">
          <h1 className="text-3xl font-bold text-primary-600">Mpango ERP</h1>
          <p className="mt-2 text-sm text-gray-500">Join your supplier</p>
        </div>

        <div className="rounded-xl bg-white p-6 shadow-sm">
          {/* Entry tabs */}
          <div className="mb-4 grid grid-cols-2 gap-2" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={tab === 'invite'}
              onClick={() => {
                setTab('invite');
                setStage({ kind: 'entry' });
              }}
              className={`rounded-md px-3 py-2 text-sm font-medium ${
                tab === 'invite' ? 'bg-primary-600 text-white' : 'bg-gray-100 text-gray-700'
              }`}
            >
              Invitation link
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={tab === 'code'}
              onClick={() => {
                setTab('code');
                setStage({ kind: 'entry' });
              }}
              className={`rounded-md px-3 py-2 text-sm font-medium ${
                tab === 'code' ? 'bg-primary-600 text-white' : 'bg-gray-100 text-gray-700'
              }`}
            >
              Supplier code
            </button>
          </div>

          {tab === 'invite' && (
            <div className="space-y-4">
              <p className="text-sm text-gray-500">
                Preferred: open the invitation link your supplier shared, or paste
                it (or the invitation code) below.
              </p>
              <input
                type="text"
                className="input-field"
                placeholder="Invitation link or code"
                aria-label="Invitation link or code"
                value={inviteInput}
                onChange={(e) => setInviteInput(e.target.value)}
              />
              {inviteError && <p className="text-xs text-red-600">{inviteError}</p>}
              {stage.kind === 'invite-checking' && (
                <p className="text-sm text-gray-400">Checking invitation…</p>
              )}
              {stage.kind === 'invite-failed' && (
                <div className="text-sm">
                  <p className="text-gray-700">{LOOKUP_FAILURE_COPY}</p>
                  <button type="button" onClick={onInviteLookup} className="btn-secondary mt-2 text-sm">
                    Try again
                  </button>
                </div>
              )}
              {stage.kind === 'invite-unusable' && (
                <p className="text-sm text-gray-700">
                  This invitation can no longer be used. Please ask your supplier
                  for a new invitation, or join with a supplier code instead.
                </p>
              )}
              {stage.kind === 'entry' && (
                <button type="button" onClick={onInviteLookup} className="btn-primary w-full text-sm">
                  Continue with invitation
                </button>
              )}
              {stage.kind === 'register' && stage.mode === 'invite' && (
                <RegisterForm
                  heading="You're Invited!"
                  supplierName={stage.supplierName}
                  onSubmit={async (values) => {
                    const portal = await submitRegister({
                      invitation_code: stage.invitationCode,
                      ...values,
                    });
                    return { ok: portal };
                  }}
                  onPortal={(code) => setStage({ kind: 'registered', portalCode: code })}
                />
              )}
            </div>
          )}

          {tab === 'code' && (
            <div className="space-y-4">
              <p className="text-sm text-gray-500">
                Enter your supplier's public code (they can share it with you
                directly). You will confirm their identity before joining.
              </p>
              <form onSubmit={onLookupCode} noValidate className="space-y-3">
                <input
                  type="text"
                  className="input-field"
                  placeholder="Supplier code"
                  aria-label="Supplier code"
                  {...codeForm.register('supplierCode')}
                />
                {codeForm.formState.errors.supplierCode && (
                  <p className="text-xs text-red-600">
                    {codeForm.formState.errors.supplierCode.message}
                  </p>
                )}
                <button type="submit" className="btn-primary w-full text-sm">
                  Find my supplier
                </button>
              </form>

              {stage.kind === 'code-checking' && (
                <p className="text-sm text-gray-400">Checking supplier code…</p>
              )}
              {stage.kind === 'code-failed' && (
                <div className="text-sm">
                  <p className="text-gray-700">{LOOKUP_FAILURE_COPY}</p>
                  <button type="button" onClick={onLookupCode} className="btn-secondary mt-2 text-sm">
                    Try again
                  </button>
                </div>
              )}
              {stage.kind === 'code-miss' && (
                <p className="text-sm text-gray-700" role="status">
                  We could not find a supplier for code{' '}
                  <span className="font-mono">{stage.code}</span>. Please check the
                  code with your supplier and try again.
                </p>
              )}
              {stage.kind === 'preview' && (
                <div className="space-y-3" data-testid="supplier-preview">
                  <div className="rounded-lg border border-gray-200 bg-gray-50 p-4">
                    <p className="text-xs uppercase tracking-wide text-gray-400">
                      Supplier
                    </p>
                    <p className="mt-1 text-base font-semibold text-gray-900" data-testid="preview-name">
                      {stage.preview.name}
                    </p>
                    {stage.preview.region && (
                      <p className="mt-1 text-sm text-gray-600">{stage.preview.region}</p>
                    )}
                    {stage.preview.contact_masked && (
                      <p className="mt-1 text-sm text-gray-500">
                        Contact: {stage.preview.contact_masked}
                      </p>
                    )}
                  </div>
                  <button
                    type="button"
                    className="btn-primary w-full text-sm"
                    onClick={() =>
                      setStage({
                        kind: 'register',
                        mode: 'code',
                        intent: stage.preview.join_intent ?? undefined,
                        supplierName: stage.preview.name ?? null,
                      })
                    }
                  >
                    Confirm joining this supplier
                  </button>
                  <p className="text-center text-xs text-gray-400">
                    Make sure this is your supplier before continuing.
                  </p>
                  <p className="text-center text-xs text-gray-400">
                    Already registered?{' '}
                    {/* F4: portal link ONLY with the positively verified,
                        normalized supplier code this lookup just resolved. */}
                    <Link
                      to={`/retail/login?w=${encodeURIComponent(
                        codeForm.getValues('supplierCode').trim().toUpperCase(),
                      )}`}
                      className="text-primary-600 hover:text-primary-700"
                    >
                      Sign in to this supplier&apos;s portal
                    </Link>
                  </p>
                </div>
              )}
              {stage.kind === 'register' && stage.mode === 'code' && (
                <RegisterForm
                  heading="Join your supplier"
                  supplierName={stage.supplierName}
                  onSubmit={async (values) => {
                    const portal = await submitRegister({
                      join_intent: stage.intent,
                      ...values,
                    });
                    return { ok: portal };
                  }}
                  onPortal={(code) => setStage({ kind: 'registered', portalCode: code })}
                />
              )}
            </div>
          )}

          {stage.kind === 'registered' && <RegisteredGuidance portalCode={stage.portalCode} />}
        </div>

        {/* H2-A-R2/F4: NO global bare /retail/login link. An already
            registered retailer gets a portal link ONLY inside the verified
            supplier-code preview, carrying the positively verified code. */}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Shared register form (both entries; email REQUIRED)
// ---------------------------------------------------------------------------

type SubmitResult = { ok: string | null };

function RegisterForm({
  heading,
  supplierName,
  onSubmit,
  onPortal,
}: {
  heading: string;
  supplierName?: string | null;
  onSubmit: (values: RegisterFormData) => Promise<SubmitResult>;
  onPortal: (portalCode: string) => void;
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
  const inFlight = useRef(false);

  const submit = handleSubmit(async (values) => {
    if (inFlight.current) return;
    inFlight.current = true;
    setServerError(null);
    try {
      const { ok } = await onSubmit(values);
      if (ok) {
        onPortal(ok);
      } else {
        setServerError(REGISTER_FAILURE_COPY);
      }
    } catch {
      setServerError(REGISTER_FAILURE_COPY);
    } finally {
      inFlight.current = false;
    }
  });

  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      <div className="text-center">
        <h2 className="text-lg font-semibold text-gray-900">{heading}</h2>
        {supplierName && (
          <p className="mt-1 text-sm font-medium text-primary-600">{supplierName}</p>
        )}
      </div>
      {serverError && (
        <div role="alert" className="rounded-md bg-red-50 p-3 text-sm text-red-700">
          {serverError}
        </div>
      )}
      <div>
        <label htmlFor="join-phone" className="mb-1 block text-sm font-medium text-gray-700">
          Phone <span className="text-red-600">*</span>
        </label>
        <input id="join-phone" type="tel" autoComplete="tel" className="input-field" {...register('phone')} />
        {errors.phone && <p className="mt-1 text-xs text-red-600">{errors.phone.message}</p>}
      </div>
      <div>
        <label htmlFor="join-name" className="mb-1 block text-sm font-medium text-gray-700">
          Business name (optional)
        </label>
        <input id="join-name" type="text" autoComplete="organization" className="input-field" {...register('name')} />
      </div>
      <div>
        <label htmlFor="join-email" className="mb-1 block text-sm font-medium text-gray-700">
          Email <span className="text-red-600">*</span>
        </label>
        <input
          id="join-email"
          type="email"
          autoComplete="email"
          className="input-field"
          aria-describedby="join-email-hint"
          {...register('email')}
        />
        <p id="join-email-hint" className="mt-1 text-xs text-gray-500">
          Your password setup email is delivered here — it is required.
        </p>
        {errors.email && <p className="mt-1 text-xs text-red-600">{errors.email.message}</p>}
      </div>
      <div>
        <label htmlFor="join-address" className="mb-1 block text-sm font-medium text-gray-700">
          Address (optional)
        </label>
        <input id="join-address" type="text" autoComplete="street-address" className="input-field" {...register('address')} />
      </div>
      <button
        type="submit"
        disabled={isSubmitting}
        className="btn-primary w-full text-sm disabled:cursor-not-allowed disabled:opacity-50"
      >
        {isSubmitting ? 'Registering…' : 'Complete registration'}
      </button>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Submission: exactly one credential, portal code from the RESPONSE
// ---------------------------------------------------------------------------

async function submitRegister(
  payload: {
    invitation_code?: string;
    join_intent?: string | undefined;
    phone: string;
    name?: string;
    email: string;
    address?: string;
  },
): Promise<string | null> {
  const body: Record<string, unknown> = {
    phone: payload.phone.trim(),
    email: payload.email.trim().toLowerCase(),
  };
  if (payload.name?.trim()) body.name = payload.name.trim();
  if (payload.address?.trim()) body.address = payload.address.trim();
  if (payload.invitation_code) body.invitation_code = payload.invitation_code;
  if (payload.join_intent) body.join_intent = payload.join_intent;
  try {
    const res = await retailerService.registerWithInvitation(
      body as unknown as Parameters<typeof retailerService.registerWithInvitation>[0],
    );
    // Portal code comes from the SERVER-VERIFIED response context.
    return res.data.data.wholesaler_code || null;
  } catch {
    return null;
  }
}

function RegisteredGuidance({ portalCode }: { portalCode: string }) {
  return (
    <div className="space-y-4 text-center">
      <h2 className="text-lg font-semibold text-gray-900">Registration complete</h2>
      <p className="text-sm text-gray-600">
        We have sent you an email with a link to set your password. Open that
        link to activate your account.
      </p>
      <p className="text-sm text-gray-600">
        After setting your password, sign in to your supplier&apos;s portal below.
      </p>
      <Link
        to={`/retail/login?w=${encodeURIComponent(portalCode)}`}
        className="btn-primary inline-block text-sm"
      >
        Go to supplier portal sign in
      </Link>
    </div>
  );
}
