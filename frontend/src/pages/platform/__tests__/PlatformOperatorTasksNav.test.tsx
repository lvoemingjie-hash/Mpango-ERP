/**
 * P23-D: Operator Task console nav + guard wiring tests.
 *
 * Verifies the additive wiring only:
 *   - the Sidebar shows the "Operator Tasks" link for an identity-only
 *     platform operator and hides it for everyone else
 *   - the PlatformRoute guard (reused unchanged) admits identity-only
 *     super_admin and redirects tenant-contextual / non-platform users
 *
 * The route element is wired under PlatformRoute in AppRouter.tsx (verified by
 * tsc + the source check); these tests cover the guard + nav visibility that
 * gate it at runtime.
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { Sidebar } from '@/components/layout/Sidebar';
import { PlatformRoute } from '@/router/guards';
import { useAuthStore } from '@/stores/authStore';
import type { CurrentUserData } from '@/types/auth';

const identityOnly: CurrentUserData = {
  id: 'u-super',
  email: 'super@mpango.example',
  full_name: 'Super Admin',
  tenant_id: null,
  tenant_schema: null,
  roles: ['super_admin'],
  permissions: [],
};

const tenantContextual: CurrentUserData = {
  id: 'u-tenant',
  email: 'tenant@mpango.example',
  full_name: 'Tenant Admin',
  tenant_id: 't-1',
  tenant_schema: 't1',
  roles: ['super_admin'],
  permissions: [],
};

const regularUser: CurrentUserData = {
  id: 'u-reg',
  email: 'user@mpango.example',
  full_name: 'Regular',
  tenant_id: 't-1',
  tenant_schema: 't1',
  roles: ['user'],
  permissions: [],
};

beforeEach(() => {
  useAuthStore.setState({ user: null, accessToken: null });
});

describe('P23 operator tasks nav + guard', () => {
  it('P23-N01: Sidebar shows the Operator Tasks link for identity-only super_admin', () => {
    useAuthStore.setState({ user: identityOnly, accessToken: 'token' });
    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    );
    const link = screen.getByText('Operator Tasks').closest('a');
    expect(link).not.toBeNull();
    expect(link?.getAttribute('href')).toBe('/platform/operator-tasks');
  });

  it('P23-N02: Sidebar hides the Operator Tasks link for tenant-contextual super_admin', () => {
    useAuthStore.setState({ user: tenantContextual, accessToken: 'token' });
    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    );
    expect(screen.queryByText('Operator Tasks')).not.toBeInTheDocument();
  });

  it('P23-N03: Sidebar hides the Operator Tasks link for non-platform users', () => {
    useAuthStore.setState({ user: regularUser, accessToken: 'token' });
    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    );
    expect(screen.queryByText('Operator Tasks')).not.toBeInTheDocument();
  });

  it('P23-N04: PlatformRoute admits identity-only super_admin to the console', () => {
    useAuthStore.setState({ user: identityOnly, accessToken: 'token' });
    render(
      <MemoryRouter initialEntries={['/platform/operator-tasks']}>
        <Routes>
          <Route path="/" element={<div data-testid="home">home</div>} />
          <Route element={<PlatformRoute />}>
            <Route
              path="/platform/operator-tasks"
              element={<div data-testid="console">console</div>}
            />
          </Route>
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByTestId('console')).toBeInTheDocument();
    expect(screen.queryByTestId('home')).not.toBeInTheDocument();
  });

  it('P23-N05: PlatformRoute redirects tenant-contextual super_admin away from the console', () => {
    useAuthStore.setState({ user: tenantContextual, accessToken: 'token' });
    render(
      <MemoryRouter initialEntries={['/platform/operator-tasks']}>
        <Routes>
          <Route path="/" element={<div data-testid="home">home</div>} />
          <Route element={<PlatformRoute />}>
            <Route
              path="/platform/operator-tasks"
              element={<div data-testid="console">console</div>}
            />
          </Route>
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.queryByTestId('console')).not.toBeInTheDocument();
    expect(screen.getByTestId('home')).toBeInTheDocument();
  });
});
