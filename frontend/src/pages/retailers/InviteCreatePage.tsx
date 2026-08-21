import { useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { PageHeader } from '@/components/layout/PageHeader';
import { invitationService, type InvitationData } from '@/services/invitationService';
import { copyToClipboard } from '@/utils/clipboard';

/** Fixed share text — never embeds anything but the supplier-facing words. */
const SHARE_TITLE = 'Join me on Mpango ERP';

/**
 * DC-12R1-MVP-L1-J1-H2-A: wholesaler-side retailer invitation authoring page.
 *
 * Closes F-13/F-14 (single root cause): the wholesaler production end of the
 * invitation funnel. Mounted at /retailers/invite under
 * WholesalerPermissionRoute('invitations:create') — a session without the
 * permission never reaches this page, and the backend POST /invitations
 * independently enforces RequirePermission('invitations:create').
 *
 * Contract fidelity:
 *  - the form submits EXACTLY the backend InvitationCreateRequest fields
 *    (retailer_phone?, expires_at?; snake_case, no new backend fields);
 *  - exactly ONE POST per submit — a synchronous in-flight lock swallows
 *    double clicks (no duplicate invitations, no fake success);
 *  - failure copy is FIXED and neutral: the backend message, request_id and
 *    response body are never echoed to the user.
 *
 * Credential transport (CTO contract): the secure link format is
 * `${origin}/invite#code=<opaque-code>` — the code lives in the URL fragment
 * only. This page must NEVER generate a `/invite/:code` path link.
 */

const createSchema = z.object({
  retailer_phone: z
    .string()
    .max(32, 'Phone must be at most 32 characters')
    .optional()
    .or(z.literal('')),
  expires_at: z.string().optional().or(z.literal('')),
});

type CreateFormData = z.infer<typeof createSchema>;

/** Fixed neutral copy — deliberately independent of the backend response. */
const CREATE_FAILURE_COPY =
  'We could not create the invitation. Please try again.';

export function InviteCreatePage() {
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<CreateFormData>({
    resolver: zodResolver(createSchema),
    defaultValues: { retailer_phone: '', expires_at: '' },
  });

  // Synchronous in-flight lock: set BEFORE any await, so a second click in
  // the same tick (or before React re-renders the disabled button) can never
  // issue a second POST.
  const inFlight = useRef(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [created, setCreated] = useState<InvitationData | null>(null);

  const onSubmit = async (values: CreateFormData) => {
    if (inFlight.current) return;
    inFlight.current = true;
    setSubmitError(null);
    try {
      // Backend InvitationCreateRequest verbatim (snake_case, optional).
      const payload: Record<string, string> = {};
      if (values.retailer_phone) payload.retailer_phone = values.retailer_phone.trim();
      if (values.expires_at) payload.expires_at = new Date(values.expires_at).toISOString();

      const res = await invitationService.create(payload);
      setCreated(res.data);
    } catch {
      // Fixed neutral copy only — no backend message/request_id echo.
      setSubmitError(CREATE_FAILURE_COPY);
    } finally {
      inFlight.current = false;
    }
  };

  const onReset = () => {
    setCreated(null);
    setSubmitError(null);
    reset({ retailer_phone: '', expires_at: '' });
  };

  return (
    <div>
      <PageHeader
        title="Invite a Retailer"
        description="Create an invitation and share it with your retailer."
        action={
          <Link to="/retailers" className="btn-secondary text-sm">
            Back to Customers
          </Link>
        }
      />

      <div className="mt-6 max-w-xl">
        {created ? (
          <InvitationCreated invitation={created} onAnother={onReset} />
        ) : (
          <form
            onSubmit={handleSubmit(onSubmit)}
            className="space-y-5 rounded-lg border border-gray-200 bg-white p-6"
            noValidate
          >
            {submitError && (
              <div
                role="alert"
                className="rounded-md bg-red-50 px-4 py-3 text-sm text-red-700"
              >
                {submitError}
              </div>
            )}

            <div>
              <label
                htmlFor="retailer_phone"
                className="mb-1 block text-sm font-medium text-gray-700"
              >
                Retailer phone (optional)
              </label>
              <input
                id="retailer_phone"
                type="tel"
                autoComplete="off"
                className="input-field"
                aria-describedby="retailer_phone_hint"
                {...register('retailer_phone')}
              />
              <p id="retailer_phone_hint" className="mt-1 text-xs text-gray-500">
                If set, only this phone number can accept the invitation.
              </p>
              {errors.retailer_phone && (
                <p className="mt-1 text-xs text-red-600">
                  {errors.retailer_phone.message}
                </p>
              )}
            </div>

            <div>
              <label
                htmlFor="expires_at"
                className="mb-1 block text-sm font-medium text-gray-700"
              >
                Expiry date and time (optional)
              </label>
              <input
                id="expires_at"
                type="datetime-local"
                className="input-field"
                {...register('expires_at')}
              />
              <p className="mt-1 text-xs text-gray-500">
                If set, the invitation can no longer be accepted after this time.
              </p>
              {errors.expires_at && (
                <p className="mt-1 text-xs text-red-600">
                  {errors.expires_at.message}
                </p>
              )}
            </div>

            <button type="submit" className="btn-primary text-sm">
              Create invitation
            </button>
          </form>
        )}
      </div>
    </div>
  );
}

/**
 * Success panel: status, expiry and the two MVP share actions — copy the
 * secure invite link (fragment-based) and copy the bare code. The QR-code
 * share action is a recorded follow-up enhancement (requires a new frontend
 * dependency, which is out of scope for this fix).
 */
function InvitationCreated({
  invitation,
  onAnother,
}: {
  invitation: InvitationData;
  onAnother: () => void;
}) {
  const [copied, setCopied] = useState<'link' | 'code' | null>(null);
  const [copyFailed, setCopyFailed] = useState(false);
  const [shared, setShared] = useState<boolean | null>(null);

  // Secure link contract: code ONLY in the fragment, never a path segment.
  const secureLink = `${window.location.origin}/invite#code=${encodeURIComponent(invitation.code)}`;

  const copy = async (what: 'link' | 'code') => {
    const ok = await copyToClipboard(what === 'link' ? secureLink : invitation.code);
    setCopied(ok ? what : null);
    setCopyFailed(!ok);
  };

  // Web Share API (mobile): lets the wholesaler pick WhatsApp or any
  // installed app directly. The invitation code rides ONLY in the shared
  // URL's fragment (never a wa.me query string, never WhatsApp Business
  // API). Any failure — unsupported browser, dismissed sheet, OS error —
  // falls back to the copy actions below (neutral, no error details).
  const share = async () => {
    try {
      if (typeof navigator !== 'undefined' && typeof navigator.share === 'function') {
        await navigator.share({ title: SHARE_TITLE, url: secureLink });
        setShared(true);
        return;
      }
    } catch {
      // Swallowed: user dismissal or unsupported — the copy fallback below
      // is the path; never surface share internals.
    }
    setShared(false);
    setCopyFailed(false);
  };

  return (
    <div
      role="status"
      className="space-y-5 rounded-lg border border-green-200 bg-green-50 p-6"
    >
      <div>
        <h2 className="text-lg font-semibold text-gray-900">Invitation created</h2>
        <p className="mt-1 text-sm text-gray-600">
          Share it with your retailer. They register with this link, then set
          their password from the email we send them.
        </p>
      </div>

      <dl className="space-y-2 text-sm">
        <div className="flex items-center gap-2">
          <dt className="font-medium text-gray-700">Status:</dt>
          <dd>
            <span className="inline-flex items-center rounded-full bg-green-100 px-2.5 py-0.5 text-xs font-medium text-green-800">
              {invitation.status.charAt(0).toUpperCase() + invitation.status.slice(1)}
            </span>
          </dd>
        </div>
        <div className="flex items-center gap-2">
          <dt className="font-medium text-gray-700">Expires:</dt>
          <dd className="text-gray-700">
            {invitation.expires_at
              ? new Date(invitation.expires_at).toLocaleString()
              : 'No expiry set'}
          </dd>
        </div>
        {invitation.retailer_phone && (
          <div className="flex items-center gap-2">
            <dt className="font-medium text-gray-700">Restricted to phone:</dt>
            <dd className="text-gray-700">{invitation.retailer_phone}</dd>
          </div>
        )}
      </dl>

      <div className="flex flex-wrap gap-3">
        <button type="button" onClick={share} className="btn-primary text-sm">
          Share invite
        </button>
        <button
          type="button"
          onClick={() => copy('link')}
          className="btn-secondary text-sm"
        >
          {copied === 'link' ? 'Link copied' : 'Copy secure invite link'}
        </button>
        <button
          type="button"
          onClick={() => copy('code')}
          className="btn-secondary text-sm"
        >
          {copied === 'code' ? 'Code copied' : 'Copy invitation code'}
        </button>
        {shared === true && (
          <p className="w-full text-xs text-green-700" data-testid="share-done">
            Shared.
          </p>
        )}
        {shared === false && (
          <p className="w-full text-xs text-gray-500" data-testid="share-fallback">
            Sharing is not available here — use the copy buttons instead.
          </p>
        )}
        <button type="button" onClick={onAnother} className="btn-secondary text-sm">
          Create another
        </button>
      </div>
      {copyFailed && (
        <p className="text-xs text-red-600">
          Copy failed. Please copy manually from the screen.
        </p>
      )}

      <p className="rounded-md bg-white px-3 py-2 font-mono text-xs text-gray-700 break-all">
        {invitation.code}
      </p>
    </div>
  );
}
