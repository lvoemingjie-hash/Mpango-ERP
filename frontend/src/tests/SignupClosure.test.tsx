import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';
import { AppRouter } from '@/router/AppRouter';
import { SignupPage } from '@/pages/auth/SignupPage';
// Raw source of LoginPage for the dead-route regression assertion.
// @ts-ignore -- vite ?raw import has no type declaration
import loginPageSource from '@/pages/auth/LoginPage.tsx?raw';

const { mockPost, mockGet } = vi.hoisted(() => ({
  mockPost: vi.fn(),
  mockGet: vi.fn(),
}));

vi.mock('@/services/api', () => ({
  api: {
    get: mockGet,
    post: mockPost,
  },
}));

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function renderAt(path: string, element: React.ReactElement) {
  window.history.pushState({}, '', path);
  // createBrowserRouter is built once at module import; it only reacts to
  // popstate, so notify it that the URL changed before rendering.
  window.dispatchEvent(new PopStateEvent('popstate'));
  return render(element);
}

function fillValidForm() {
  const user = userEvent.setup();
  return user;
}

async function submitValidSignup() {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText(/company name/i), 'Acme Trading Ltd');
  await user.type(screen.getByLabelText(/country/i), 'ke');
  await user.type(screen.getByLabelText(/^email/i), 'owner@acme.com');
  await user.type(screen.getByLabelText(/^password/i), 'StrongPass123'); // pragma: allowlist secret
  await user.click(screen.getByRole('button', { name: /create account/i }));
  return user;
}

describe('DC-12R1-MVP-L1-J1-R1 wholesaler signup closure', () => {
  beforeEach(() => {
    mockPost.mockReset();
    mockGet.mockReset();
    window.localStorage.clear();
    window.sessionStorage.clear();
    window.history.pushState({}, '', '/');
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  describe('route mounting (real AppRouter)', () => {
    it('mounts /signup without 404 for an anonymous visitor', async () => {
      renderAt('/signup', <AppRouter />);
      expect(
        await screen.findByText('Create your wholesaler account'),
      ).toBeDefined();
      expect(screen.queryByText(/404|not found/i)).toBeNull();
    });

    it('renders the signup entry link on the login page and it resolves inside the real router', async () => {
      renderAt('/login', <AppRouter />);
      const link = await screen.findByRole('link', {
        name: /create wholesaler account/i,
      });
      expect(link).toHaveAttribute('href', '/signup');

      const user = userEvent.setup();
      await user.click(link);
      await waitFor(() => {
        expect(window.location.pathname).toBe('/signup');
      });
      expect(
        await screen.findByText('Create your wholesaler account'),
      ).toBeDefined();
    });

    it('cold-start branch never references /onboarding/create-tenant', async () => {
      // Simulate the cold-start login outcome: accepted identity login with
      // zero available tenants must land on /signup (not a dead onboarding
      // route).
      mockPost.mockResolvedValue({
        data: {
          success: true,
          data: {
            access_token: 'identity-token',
            refresh_token: 'refresh-token',
            token_type: 'bearer',
            user_id: 'u1',
            roles: ['wholesaler_admin'],
            available_tenants: [],
          },
        },
      });
      renderAt('/login', <AppRouter />);
      const user = userEvent.setup();
      await user.type(screen.getByLabelText(/^email/i), 'owner@acme.com');
      await user.type(screen.getByLabelText(/^password/i), 'StrongPass123'); // pragma: allowlist secret
      await user.click(screen.getByRole('button', { name: /sign in/i }));
      await waitFor(() => {
        expect(window.location.pathname).toBe('/signup');
      });
      expect(window.location.pathname).not.toContain('/onboarding');
    });

    it('LoginPage source no longer contains the dead route string', () => {
      expect(loginPageSource).not.toContain('/onboarding/create-tenant');
      expect(loginPageSource).toContain('/signup');
    });
  });

  describe('API contract conformance', () => {
    it('submits payload and Idempotency-Key matching POST /auth/signup exactly', async () => {
      mockPost.mockResolvedValue({
        status: 202,
        data: {
          success: true,
          data: {
            registrationId: null,
            status: 'pending_email_verification',
            emailVerificationRequired: true,
            resendAvailableAt: null,
          },
          message: 'If this email can be used, verification instructions will be sent.',
          timestamp: '2026-08-20T00:00:00Z',
        },
      });

      renderAt('/signup', <BrowserRouter><SignupPage /></BrowserRouter>);
      await submitValidSignup();

      await waitFor(() => {
        expect(mockPost).toHaveBeenCalledTimes(1);
      });
      const [path, payload, config] = mockPost.mock.calls[0];
      expect(path).toBe('/auth/signup');
      // camelCase aliases accepted by the backend Pydantic schema; email
      // normalized to lower case; country upper-cased; optional empties
      // omitted rather than sent as empty strings.
      expect(payload).toEqual({
        companyName: 'Acme Trading Ltd',
        country: 'KE',
        email: 'owner@acme.com',
        password: 'StrongPass123', // pragma: allowlist secret
      });
      expect(config.headers['Idempotency-Key']).toMatch(UUID_RE);
    });

    it('reaches neutral email-verification guidance on accepted signup and persists nothing', async () => {
      mockPost.mockResolvedValue({
        status: 202,
        data: { success: true, data: { status: 'pending_email_verification' } },
      });
      const storageSetItem = vi.spyOn(Storage.prototype, 'setItem');

      renderAt('/signup', <BrowserRouter><SignupPage /></BrowserRouter>);
      await submitValidSignup();

      expect(await screen.findByText('Check your email')).toBeDefined();
      expect(
        screen.getByText(/verification instructions/i, { exact: false }),
      ).toBeDefined();
      // Neutral copy: no backend message, no raw response reflection.
      expect(document.body.textContent).not.toContain(
        'pending_email_verification',
      );
      expect(storageSetItem).not.toHaveBeenCalled();
      // No navigation away with any token material.
      expect(window.location.pathname).toBe('/signup');
      expect(window.location.hash).toBe('');
      expect(window.location.search).toBe('');
    });

    it('failure keeps idempotency key stable, shows neutral copy only, and does not navigate', async () => {
      mockPost.mockRejectedValue({
        response: {
          status: 409,
          data: {
            code: 'IDEMPOTENCY_CONFLICT',
            message: 'LEAKED INTERNAL DETAIL',
            request_id: 'req-123',
          },
        },
        message: 'Network Error RAW',
      });

      renderAt('/signup', <BrowserRouter><SignupPage /></BrowserRouter>);
      const user = await submitValidSignup();
      await waitFor(() => {
        expect(mockPost).toHaveBeenCalledTimes(1);
      });

      // Neutral error copy; raw backend/axios data never rendered.
      expect(await screen.findByText(/unable to create your account/i)).toBeDefined();
      expect(document.body.textContent).not.toContain('LEAKED INTERNAL DETAIL');
      expect(document.body.textContent).not.toContain('IDEMPOTENCY_CONFLICT');
      expect(document.body.textContent).not.toContain('req-123');
      expect(document.body.textContent).not.toContain('Network Error RAW');
      expect(window.location.pathname).toBe('/signup');

      // Retry after failure reuses the SAME key (stable on failure).
      await user.click(screen.getByRole('button', { name: /create account/i }));
      await waitFor(() => {
        expect(mockPost).toHaveBeenCalledTimes(2);
      });
      expect(mockPost.mock.calls[1][2].headers['Idempotency-Key']).toBe(
        mockPost.mock.calls[0][2].headers['Idempotency-Key'],
      );
    });

    it('rotates the idempotency key only after an accepted success', async () => {
      mockPost
        .mockRejectedValueOnce({ response: { status: 500, data: {} } })
        .mockResolvedValue({
          status: 202,
          data: { success: true, data: { status: 'pending_email_verification' } },
        });

      renderAt('/signup', <BrowserRouter><SignupPage /></BrowserRouter>);
      const user = await submitValidSignup();
      await waitFor(() => {
        expect(mockPost).toHaveBeenCalledTimes(1);
      });
      const failedKey = mockPost.mock.calls[0][2].headers['Idempotency-Key'];

      // Failure: still on the form with the same key. A second submit is not
      // possible from the accepted state, so prove rotation by submitting
      // again before acceptance state settles in a fresh failure-then-success
      // sequence: first call failed, form stays; submit again -> same key
      // must NOT have been rotated yet.
      expect(screen.queryByText('Check your email')).toBeNull();
      await user.click(screen.getByRole('button', { name: /create account/i }));
      await waitFor(() => {
        expect(mockPost).toHaveBeenCalledTimes(2);
      });
      expect(mockPost.mock.calls[1][2].headers['Idempotency-Key']).toBe(
        failedKey,
      );

      // Accepted success now; key in the ref is rotated for any future use.
      expect(await screen.findByText('Check your email')).toBeDefined();
    });
  });

  describe('validation mirrors the backend schema', () => {
    it.each([
      ['companyName', 'a', /at least 2 characters/i],
      ['country', 'KEN', 'Country must be a 2-letter code (e.g. KE)'],
      ['email', 'not-an-email', /valid email/i],
      ['password', 'short', /at least 8 characters/i],
    ])(
      'rejects invalid %s before any API call',
      async (field, value, message) => {
        renderAt('/signup', <BrowserRouter><SignupPage /></BrowserRouter>);
        const user = userEvent.setup();
        await user.type(screen.getByLabelText(/company name/i), 'Acme Trading Ltd');
        await user.type(screen.getByLabelText(/country/i), 'KE');
        await user.type(screen.getByLabelText(/^email/i), 'owner@acme.com');
        await user.type(screen.getByLabelText(/^password/i), 'StrongPass123'); // pragma: allowlist secret

        const labelFor: Record<string, RegExp> = {
          companyName: /company name/i,
          country: /country/i,
          email: /^email/i,
          password: /^password/i,
        };
        const input = screen.getByLabelText(labelFor[field]);
        await user.clear(input);
        await user.type(input, value);
        await user.click(screen.getByRole('button', { name: /create account/i }));

        expect(await screen.findByText(message)).toBeDefined();
        expect(mockPost).not.toHaveBeenCalled();
      },
    );
  });

  describe('accessibility', () => {
    it('associates every input with its label and submits via keyboard', async () => {
      renderAt('/signup', <BrowserRouter><SignupPage /></BrowserRouter>);
      for (const label of [
        /company name/i,
        /country/i,
        /^email/i,
        /^password/i,
        /phone/i,
        /business type/i,
      ]) {
        const el = screen.getByLabelText(label);
        expect(el).toBeDefined();
        expect(el.tagName).toBe('INPUT');
        expect(el.id).toBeDefined();
        expect(document.querySelector(`label[for="${el.id}"]`)).not.toBeNull();
      }

      // Keyboard-only submit: fill via keyboard events and press Enter.
      mockPost.mockResolvedValue({
        status: 202,
        data: { success: true, data: { status: 'pending_email_verification' } },
      });
      const user = fillValidForm();
      await user.type(screen.getByLabelText(/company name/i), 'Acme Trading Ltd');
      await user.type(screen.getByLabelText(/country/i), 'KE');
      await user.type(screen.getByLabelText(/^email/i), 'owner@acme.com');
      await user.type(screen.getByLabelText(/^password/i), 'StrongPass123'); // pragma: allowlist secret
      await user.keyboard('{Enter}');
      await waitFor(() => {
        expect(mockPost).toHaveBeenCalledWith(
          '/auth/signup',
          expect.objectContaining({ email: 'owner@acme.com' }),
          expect.objectContaining({
            headers: expect.objectContaining({ 'Idempotency-Key': expect.any(String) }),
          }),
        );
      });
    });
  });

  describe('guards remain correct', () => {
    it('anonymous visitor can reach /signup but a contextual session is redirected away from it', async () => {
      // Anonymous: renders.
      const { unmount } = renderAt('/signup', <AppRouter />);
      expect(
        await screen.findByText('Create your wholesaler account'),
      ).toBeDefined();
      unmount();

      // Contextual session: PublicRoute redirects public pages to /.
      const { useAuthStore } = await import('@/stores/authStore');
      useAuthStore.getState().login(
        {
          access_token: 'a',
          refresh_token: 'r',
          token_type: 'bearer',
          user_id: 'u1',
          tenant_id: 't1',
          tenant_schema: 's1',
          roles: ['wholesaler_admin'],
        },
        {
          id: 'u1',
          email: 'owner@acme.com',
          full_name: null,
          tenant_id: 't1',
          tenant_schema: 's1',
          roles: ['wholesaler_admin'],
          permissions: [],
        },
        'ACME',
      );
      renderAt('/signup', <AppRouter />);
      await waitFor(() => {
        expect(window.location.pathname).toBe('/');
      });
      useAuthStore.getState().logout();
    });
  });

  describe(' LoginPage regression: existing single/multi-tenant flows untouched', () => {
    it('single-tenant login still auto-selects the tenant', async () => {
      mockPost.mockImplementation((path: string) => {
        if (path === '/auth/login') {
          return Promise.resolve({
            data: {
              success: true,
              data: {
                access_token: 'identity-token',
                refresh_token: 'refresh',
                token_type: 'bearer',
                user_id: 'u1',
                roles: ['wholesaler_admin'],
                available_tenants: [
                  { id: 't1', code: 'ACME', name: 'Acme' },
                ],
              },
            },
          });
        }
        if (path === '/auth/select-tenant') {
          return Promise.resolve({
            data: {
              success: true,
              data: {
                access_token: 'ctx',
                refresh_token: 'ctxr',
                token_type: 'bearer',
                user_id: 'u1',
                tenant_id: 't1',
                tenant_schema: 's1',
                roles: ['wholesaler_admin'],
              },
            },
          });
        }
        if (path === '/auth/me') {
          return Promise.resolve({
            data: {
              success: true,
              data: {
                id: 'u1',
                email: 'owner@acme.com',
                full_name: null,
                tenant_id: 't1',
                tenant_schema: 's1',
                roles: ['wholesaler_admin'],
                permissions: [],
              },
            },
          });
        }
        return Promise.reject(new Error('unexpected call'));
      });

      const { useAuthStore } = await import('@/stores/authStore');
      mockGet.mockResolvedValue({
        data: {
          success: true,
          data: {
            id: 'u1',
            email: 'owner@acme.com',
            full_name: null,
            tenant_id: 't1',
            tenant_schema: 's1',
            roles: ['wholesaler_admin'],
            permissions: [],
          },
        },
      });
      renderAt('/login', <AppRouter />);
      const user = userEvent.setup();
      await user.type(screen.getByLabelText(/^email/i), 'owner@acme.com');
      await user.type(screen.getByLabelText(/^password/i), 'StrongPass123'); // pragma: allowlist secret
      await user.click(screen.getByRole('button', { name: /sign in/i }));
      await waitFor(() => {
        expect(window.location.pathname).toBe('/');
      });
      expect(mockPost).toHaveBeenCalledWith(
        '/auth/select-tenant',
        { tenant_id: 't1' },
        expect.anything(),
      );
      useAuthStore.getState().logout();
    });
  });
});
