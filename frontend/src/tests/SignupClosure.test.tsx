import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
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
  // popstate, so notify it that the URL changed before rendering. Wrapped
  // in act(): the router updates its state synchronously on popstate.
  act(() => {
    window.dispatchEvent(new PopStateEvent('popstate'));
  });
  return render(element);
}

/** Flush pending router/async state updates inside act() so no React
 *  "not wrapped in act" warning can escape after the assertions. */
async function settle() {
  await act(async () => {});
}

async function fillAndSubmit(email = 'owner@acme.com') {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText(/company name/i), 'Acme Trading Ltd');
  await user.type(screen.getByLabelText(/country/i), 'ke');
  await user.type(screen.getByLabelText(/^email/i), email);
  await user.click(screen.getByRole('button', { name: /create account/i }));
  return user;
}

function identityLoginResponse(tenants: unknown[] = []) {
  return {
    data: {
      success: true,
      data: {
        access_token: 'identity-token',
        refresh_token: 'refresh-token',
        token_type: 'bearer',
        user_id: 'u1',
        roles: ['wholesaler_admin'],
        available_tenants: tenants,
      },
    },
  };
}

const ME_RESPONSE = {
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
};

const DASHBOARD_GETS = (url: string) => {
  if (url.includes('/dashboards/kpi/summary')) {
    return { data: { success: true, data: { cards: [], currency: 'KES' } } };
  }
  if (url.includes('/dashboards/charts/sales-trend')) {
    return { data: { success: true, data: { data: [] } } };
  }
  if (url.includes('/orders')) {
    return { data: { success: true, data: { items: [] } } };
  }
  if (url.includes('/inventory/stocks')) {
    return { data: { success: true, data: { items: [] } } };
  }
  return { data: { success: true, data: {} } };
};

describe('DC-12R1-MVP-L1-J1-R1-R1 signup contract truth', () => {
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
      await settle();
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
      await settle();
    });

    it('LoginPage source contains neither the dead onboarding route nor an auto-redirect to /signup', () => {
      expect(loginPageSource).not.toContain('/onboarding/create-tenant');
      expect(loginPageSource).not.toContain("navigate('/signup'");
    });
  });

  describe('F-B: zero-tenant impossibility fails closed (defensive guard only)', () => {
    it('a defensively-impossible 200+[] identity response stays on /login, shows neutral error, persists nothing', async () => {
      // Truth (F-B): the real /auth/login answers 401 for zero tenant
      // matches and can never emit 200 + available_tenants=[]. This test
      // does NOT claim that state is reachable; it proves the defensive
      // branch fails closed IF it ever fired.
      mockPost.mockResolvedValue(identityLoginResponse([]));
      const storageSetItem = vi.spyOn(Storage.prototype, 'setItem');

      renderAt('/login', <AppRouter />);
      const user = userEvent.setup();
      await user.type(screen.getByLabelText(/^email/i), 'owner@acme.com');
      await user.type(screen.getByLabelText(/^password/i), 'WhateverPass1');
      await user.click(screen.getByRole('button', { name: /sign in/i }));

      await waitFor(() => {
        expect(screen.getByText('Invalid credentials')).toBeDefined();
      });
      // Stays on the login page; no auto-navigation anywhere.
      expect(window.location.pathname).toBe('/login');
      // Nothing persisted: no identity token, no pending session.
      expect(storageSetItem).not.toHaveBeenCalled();
      expect(window.localStorage.getItem('mpango-auth')).toBeNull();
      await settle();
    });
  });

  describe('F-A: passwordless contract', () => {
    it('submits a payload with NO password field and a UUID Idempotency-Key', async () => {
      mockPost.mockResolvedValue({
        status: 202,
        data: { success: true, data: { status: 'pending_email_verification' } },
      });

      renderAt('/signup', <BrowserRouter><SignupPage /></BrowserRouter>);
      await fillAndSubmit();

      await waitFor(() => {
        expect(mockPost).toHaveBeenCalledTimes(1);
      });
      const [path, payload, config] = mockPost.mock.calls[0];
      expect(path).toBe('/auth/signup');
      expect(payload).toEqual({
        companyName: 'Acme Trading Ltd',
        country: 'KE',
        email: 'owner@acme.com',
      });
      // F-A: no password key anywhere in the payload.
      expect(Object.keys(payload)).not.toContain('password');
      expect(config.headers['Idempotency-Key']).toMatch(UUID_RE);
    });

    it('the signup form never renders a password input', () => {
      renderAt('/signup', <BrowserRouter><SignupPage /></BrowserRouter>);
      expect(
        screen.queryByLabelText(/^password/i, { selector: 'input' }),
      ).toBeNull();
      expect(document.querySelector('input[type="password"]')).toBeNull();
    });

    it('accepted signup shows verify-email + set-password guidance and persists nothing', async () => {
      mockPost.mockResolvedValue({
        status: 202,
        data: { success: true, data: { status: 'pending_email_verification' } },
      });
      const storageSetItem = vi.spyOn(Storage.prototype, 'setItem');

      renderAt('/signup', <BrowserRouter><SignupPage /></BrowserRouter>);
      await fillAndSubmit();

      expect(await screen.findByText('Check your email')).toBeDefined();
      // Copy must tell the customer they will SET a password later, and
      // must not imply a password was already set.
      expect(screen.getByText(/set your password/i)).toBeDefined();
      expect(document.body.textContent).not.toMatch(/your password has been/i);
      expect(storageSetItem).not.toHaveBeenCalled();
      expect(window.location.pathname).toBe('/signup');
      expect(window.location.hash).toBe('');
      expect(window.location.search).toBe('');
    });
  });

  describe('F-C: idempotency truth (observable rotation)', () => {
    it('failure retries reuse the SAME key; accepted success rotates it observably', async () => {
      mockPost
        .mockRejectedValueOnce({ response: { status: 500, data: {} } })
        .mockResolvedValue({
          status: 202,
          data: { success: true, data: { status: 'pending_email_verification' } },
        });

      renderAt('/signup', <BrowserRouter><SignupPage /></BrowserRouter>);
      // 1st submit fails.
      const user = await fillAndSubmit('first@acme.com');
      await waitFor(() => expect(mockPost).toHaveBeenCalledTimes(1));
      const failedKey = mockPost.mock.calls[0][2].headers['Idempotency-Key'];
      expect(failedKey).toMatch(UUID_RE);

      // 2nd submit (retry after failure): SAME key.
      await user.click(screen.getByRole('button', { name: /create account/i }));
      await waitFor(() => expect(mockPost).toHaveBeenCalledTimes(2));
      expect(mockPost.mock.calls[1][2].headers['Idempotency-Key']).toBe(failedKey);
      // This retry is the accepted success.
      expect(await screen.findByText('Check your email')).toBeDefined();

      // Restart via the accepted panel; the next submission must use a
      // DIFFERENT key — the rotation is observable, not implied.
      await user.click(
        screen.getByRole('button', { name: /register another account/i }),
      );
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /create account/i }));
      });
      await fillAndSubmit('second@acme.com');
      await waitFor(() => expect(mockPost).toHaveBeenCalledTimes(3));
      const rotatedKey = mockPost.mock.calls[2][2].headers['Idempotency-Key'];
      expect(rotatedKey).toMatch(UUID_RE);
      expect(rotatedKey).not.toBe(failedKey);
      expect(mockPost.mock.calls[2][1]).toEqual({
        companyName: 'Acme Trading Ltd',
        country: 'KE',
        email: 'second@acme.com',
      });
    });

    it('failure shows neutral copy only: no backend message, code, request_id, or axios text', async () => {
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
      await fillAndSubmit();
      await waitFor(() => expect(mockPost).toHaveBeenCalledTimes(1));

      expect(
        await screen.findByText(/unable to create your account/i),
      ).toBeDefined();
      expect(document.body.textContent).not.toContain('LEAKED INTERNAL DETAIL');
      expect(document.body.textContent).not.toContain('IDEMPOTENCY_CONFLICT');
      expect(document.body.textContent).not.toContain('req-123');
      expect(document.body.textContent).not.toContain('Network Error RAW');
      expect(window.location.pathname).toBe('/signup');
    });

    it('the key never enters URL, storage, or rendered UI', async () => {
      mockPost.mockResolvedValue({
        status: 202,
        data: { success: true, data: { status: 'pending_email_verification' } },
      });
      const storageSetItem = vi.spyOn(Storage.prototype, 'setItem');

      renderAt('/signup', <BrowserRouter><SignupPage /></BrowserRouter>);
      await fillAndSubmit();
      await waitFor(() => expect(mockPost).toHaveBeenCalledTimes(1));
      const key = mockPost.mock.calls[0][2].headers['Idempotency-Key'];

      expect(await screen.findByText('Check your email')).toBeDefined();
      expect(document.body.textContent).not.toContain(key);
      expect(window.location.href).not.toContain(key);
      expect(storageSetItem).not.toHaveBeenCalled();
    });
  });

  describe('validation mirrors the backend schema (passwordless)', () => {
    it.each([
      ['companyName', 'a', /at least 2 characters/i],
      ['country', 'KEN', 'Country must be a 2-letter code (e.g. KE)'],
      ['email', 'not-an-email', /valid email/i],
    ])(
      'rejects invalid %s before any API call',
      async (field, value, message) => {
        renderAt('/signup', <BrowserRouter><SignupPage /></BrowserRouter>);
        const user = userEvent.setup();
        await user.type(screen.getByLabelText(/company name/i), 'Acme Trading Ltd');
        await user.type(screen.getByLabelText(/country/i), 'KE');
        await user.type(screen.getByLabelText(/^email/i), 'owner@acme.com');

        const labelFor: Record<string, RegExp> = {
          companyName: /company name/i,
          country: /country/i,
          email: /^email/i,
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
        /phone/i,
        /business type/i,
      ]) {
        const el = screen.getByLabelText(label);
        expect(el.tagName).toBe('INPUT');
        expect(document.querySelector(`label[for="${el.id}"]`)).not.toBeNull();
      }

      mockPost.mockResolvedValue({
        status: 202,
        data: { success: true, data: { status: 'pending_email_verification' } },
      });
      const user = userEvent.setup();
      await user.type(screen.getByLabelText(/company name/i), 'Acme Trading Ltd');
      await user.type(screen.getByLabelText(/country/i), 'KE');
      await user.type(screen.getByLabelText(/^email/i), 'owner@acme.com');
      await user.keyboard('{Enter}');
      await waitFor(() => {
        expect(mockPost).toHaveBeenCalledWith(
          '/auth/signup',
          expect.not.objectContaining({ password: expect.anything() }),
          expect.objectContaining({
            headers: expect.objectContaining({ 'Idempotency-Key': expect.any(String) }),
          }),
        );
      });
    });
  });

  describe('guards remain correct', () => {
    it('anonymous visitor can reach /signup but a contextual session is redirected away from it', async () => {
      const { unmount } = renderAt('/signup', <AppRouter />);
      expect(
        await screen.findByText('Create your wholesaler account'),
      ).toBeDefined();
      unmount();

      const { useAuthStore } = await import('@/stores/authStore');
      await act(async () => {
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
          ME_RESPONSE.data.data,
          'ACME',
        );
      });
      renderAt('/signup', <AppRouter />);
      await waitFor(() => {
        expect(window.location.pathname).toBe('/');
      });
      await settle();
      act(() => {
        useAuthStore.getState().logout();
      });
    });
  });

  describe('LoginPage regression: existing single/multi-tenant flows untouched (F-OBS1)', () => {
    it('single-tenant login really mounts the dashboard with no render error', async () => {
      mockPost.mockImplementation((path: string) => {
        if (path === '/auth/login') {
          return Promise.resolve(
            identityLoginResponse([{ id: 't1', code: 'ACME', name: 'Acme' }]),
          );
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
        return Promise.reject(new Error('unexpected call'));
      });
      mockGet.mockImplementation((url: string) =>
        Promise.resolve(DASHBOARD_GETS(url)),
      );
      const consoleError = vi
        .spyOn(console, 'error')
        .mockImplementation(() => {});

      const { useAuthStore } = await import('@/stores/authStore');
      renderAt('/login', <AppRouter />);
      const user = userEvent.setup();
      await user.type(screen.getByLabelText(/^email/i), 'owner@acme.com');
      await user.type(screen.getByLabelText(/^password/i), 'owner-pass-123'); // pragma: allowlist secret
      await user.click(screen.getByRole('button', { name: /sign in/i }));

      // The dashboard page truly mounts (real content, not just pathname).
      await waitFor(() => {
        expect(window.location.pathname).toBe('/');
      });
      expect(
        await screen.findByText(/welcome to your dashboard/i),
      ).toBeDefined();
      expect(mockPost).toHaveBeenCalledWith(
        '/auth/select-tenant',
        { tenant_id: 't1' },
        expect.anything(),
      );
      // Flush every pending async update first: the "no render error"
      // assertion must hold in the settled final state (P2-3 closure).
      await settle();
      await settle();
      expect(consoleError).not.toHaveBeenCalled();
      act(() => {
        useAuthStore.getState().logout();
      });
      await settle();
    });
  });
});
