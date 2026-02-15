import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api } from '@/services/api';
import type { ApiResponse } from '@/types/api';

interface InvitationLookup {
  code: string;
  usable: boolean;
  reason: string | null;
  status?: string;
  wholesaler_id?: string;
  wholesaler_name?: string | null;
  expires_at?: string | null;
}

export function InvitePage() {
  const { code } = useParams<{ code: string }>();
  const [data, setData] = useState<InvitationLookup | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!code) return;
    async function lookup() {
      setLoading(true);
      setError(null);
      try {
        const res = await api.get<ApiResponse<InvitationLookup>>(
          `/invitations/${code}`
        );
        setData(res.data.data);
      } catch (err: unknown) {
        const axErr = err as { response?: { status?: number } };
        if (axErr.response?.status === 400 || axErr.response?.status === 403) {
          setError('This invitation link is invalid or has expired.');
        } else if (axErr.response?.status === 404) {
          setError('Invitation not found. Please check the link and try again.');
        } else {
          setError('Unable to verify invitation. Please try again later.');
        }
      } finally {
        setLoading(false);
      }
    }
    lookup();
  }, [code]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-md">
        <div className="mb-6 text-center">
          <h1 className="text-3xl font-bold text-primary-600">Mpango ERP</h1>
          <p className="mt-2 text-sm text-gray-500">Tenant Onboarding</p>
        </div>

        <div className="rounded-xl bg-white p-6 shadow-sm">
          {loading && (
            <p className="text-center text-sm text-gray-400">
              Verifying invitation…
            </p>
          )}

          {error && (
            <div className="text-center">
              <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-red-100">
                <svg className="h-6 w-6 text-red-600" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z" />
                </svg>
              </div>
              <h2 className="text-lg font-semibold text-gray-900">
                Invitation Expired or Invalid
              </h2>
              <p className="mt-2 text-sm text-gray-500">{error}</p>
              <Link
                to="/login"
                className="mt-4 inline-block text-sm font-medium text-primary-600 hover:text-primary-700"
              >
                Go to Login
              </Link>
            </div>
          )}

          {!loading && !error && data && !data.usable && (
            <div className="text-center">
              <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-yellow-100">
                <svg className="h-6 w-6 text-yellow-600" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
                </svg>
              </div>
              <h2 className="text-lg font-semibold text-gray-900">
                Invitation Unavailable
              </h2>
              <p className="mt-2 text-sm text-gray-500">
                {data.reason || 'This invitation can no longer be used.'}
              </p>
              <Link
                to="/login"
                className="mt-4 inline-block text-sm font-medium text-primary-600 hover:text-primary-700"
              >
                Go to Login
              </Link>
            </div>
          )}

          {!loading && !error && data && data.usable && (
            <div className="text-center">
              <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-green-100">
                <svg className="h-6 w-6 text-green-600" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
                </svg>
              </div>
              <h2 className="text-lg font-semibold text-gray-900">
                You&apos;re Invited!
              </h2>
              {data.wholesaler_name && (
                <p className="mt-1 text-sm font-medium text-primary-600">
                  {data.wholesaler_name}
                </p>
              )}
              <p className="mt-2 text-sm text-gray-500">
                This invitation is valid. Complete your registration to join.
              </p>
              {data.expires_at && (
                <p className="mt-1 text-xs text-gray-400">
                  Expires: {new Date(data.expires_at).toLocaleDateString()}
                </p>
              )}
              <div className="mt-4 space-y-2">
                <p className="text-xs text-gray-400">
                  Code: <span className="font-mono">{data.code}</span>
                </p>
                <Link
                  to="/login"
                  className="btn-primary inline-block text-sm"
                >
                  Continue to Login
                </Link>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
