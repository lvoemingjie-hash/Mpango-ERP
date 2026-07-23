import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { authService } from '@/services/authService';

type VerifyState = 'processing' | 'success' | 'invalid' | 'no-token' | 'query-rejected';

export function VerifyEmailPage() {
  const [state, setState] = useState<VerifyState>('processing');
  const [errorMsg, setErrorMsg] = useState('');
  const navigate = useNavigate();
  const submitted = useRef(false);

  useEffect(() => {
    if (submitted.current) return;
    submitted.current = true;

    // DC-12A-R3: Read token from URL fragment ONLY.
    // Fragment is never sent to the server/proxy, so the token
    // does not appear in access logs.
    const hash = window.location.hash;
    const params = new URLSearchParams(hash.startsWith('#') ? hash.slice(1) : hash);
    const token = params.get('token');

    // DC-12A-R3: Query-string tokens are rejected.
    // Scrub URL, show controlled invalid-link state, never submit.
    const queryToken = new URLSearchParams(window.location.search).get('token');
    if (queryToken && !token) {
      window.history.replaceState(null, '', window.location.pathname);
      setState('query-rejected');
      return;
    }

    // Immediately clear the URL so the token is not visible in
    // the address bar, history, or screenshots.
    window.history.replaceState(null, '', window.location.pathname);

    if (!token) {
      setState('no-token');
      return;
    }

    authService
      .verifyEmail({ token })
      .then(() => {
        setState('success');
      })
      .catch((err: unknown) => {
        setState('invalid');
        const detail = err as { response?: { data?: { detail?: string } } };
        setErrorMsg(
          detail?.response?.data?.detail ||
            'Verification link is invalid or expired.'
        );
      });
  }, []);

  if (state === 'processing') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="max-w-md w-full space-y-8 p-8 bg-white rounded-lg shadow">
          <div className="text-center">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto"></div>
            <p className="mt-4 text-gray-600">Verifying your email...</p>
          </div>
        </div>
      </div>
    );
  }

  if (state === 'success') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="max-w-md w-full space-y-8 p-8 bg-white rounded-lg shadow">
          <div className="text-center">
            <svg className="mx-auto h-12 w-12 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" />
            </svg>
            <h2 className="mt-4 text-xl font-bold text-gray-900">Email Verified!</h2>
            <p className="mt-2 text-gray-600">
              Your email has been verified successfully. Your tenant is being
              provisioned. You will receive an owner setup email shortly.
            </p>
            <button
              onClick={() => navigate('/login')}
              className="mt-6 w-full py-2 px-4 bg-indigo-600 text-white rounded-md hover:bg-indigo-700"
            >
              Go to Login
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (state === 'query-rejected') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="max-w-md w-full space-y-8 p-8 bg-white rounded-lg shadow">
          <div className="text-center">
            <svg className="mx-auto h-12 w-12 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
            <h2 className="mt-4 text-xl font-bold text-gray-900">Invalid Link</h2>
            <p className="mt-2 text-gray-600">
              This verification link is no longer valid. Please use the
              latest link from your signup email.
            </p>
            <button
              onClick={() => navigate('/login')}
              className="mt-6 w-full py-2 px-4 bg-indigo-600 text-white rounded-md hover:bg-indigo-700"
            >
              Go to Login
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (state === 'no-token') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="max-w-md w-full space-y-8 p-8 bg-white rounded-lg shadow">
          <div className="text-center">
            <svg className="mx-auto h-12 w-12 text-yellow-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <h2 className="mt-4 text-xl font-bold text-gray-900">Invalid Link</h2>
            <p className="mt-2 text-gray-600">
              No verification token was found. Please use the link from your
              signup email.
            </p>
            <button
              onClick={() => navigate('/login')}
              className="mt-6 w-full py-2 px-4 bg-indigo-600 text-white rounded-md hover:bg-indigo-700"
            >
              Go to Login
            </button>
          </div>
        </div>
      </div>
    );
  }

  // state === 'invalid'
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="max-w-md w-full space-y-8 p-8 bg-white rounded-lg shadow">
        <div className="text-center">
          <svg className="mx-auto h-12 w-12 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
          <h2 className="mt-4 text-xl font-bold text-gray-900">Verification Failed</h2>
          <p className="mt-2 text-gray-600">{errorMsg}</p>
          <button
            onClick={() => navigate('/login')}
            className="mt-6 w-full py-2 px-4 bg-indigo-600 text-white rounded-md hover:bg-indigo-700"
          >
            Go to Login
          </button>
        </div>
      </div>
    </div>
  );
}
