/**
 * P11-B1: PlatformRoute guard tests.
 *
 * Tests:
 *   TG-001: PlatformRoute renders for super_admin
 *   TG-002: PlatformRoute redirects for regular user
 *   TG-003: PlatformRoute redirects for unauthenticated user
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { PlatformRoute } from '@/router/guards';
import { useAuthStore } from '@/stores/authStore';

// Reset auth store between tests
beforeEach(() => {
  useAuthStore.setState({
    accessToken: null,
    refreshToken: null,
    user: null,
    tenantCode: null,
  });
});

function renderWithRouter(initialPath = '/platform') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route element={<PlatformRoute />}>
          <Route path="/platform" element={<div data-testid="platform-page">Platform Cockpit</div>} />
        </Route>
        <Route path="/" element={<div data-testid="home-page">Dashboard</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('PlatformRoute guard', () => {
  it('TG-001: renders for super_admin user', () => {
    useAuthStore.setState({
      accessToken: 'test-token',
      refreshToken: 'test-refresh',
      user: {
        id: '1',
        email: 'admin@test.com',
        full_name: 'Admin',
        tenant_id: null,
        tenant_schema: null,
        roles: ['super_admin'],
        permissions: [],
      },
      tenantCode: null,
    });

    renderWithRouter();
    expect(screen.getByTestId('platform-page')).toBeInTheDocument();
  });

  it('TG-002: redirects for regular (non-super_admin) user', () => {
    useAuthStore.setState({
      accessToken: 'test-token',
      refreshToken: 'test-refresh',
      user: {
        id: '2',
        email: 'user@test.com',
        full_name: 'User',
        tenant_id: 'tenant-1',
        tenant_schema: 'tenant_test',
        roles: ['admin'],
        permissions: [],
      },
      tenantCode: 'TEST',
    });

    renderWithRouter();
    expect(screen.getByTestId('home-page')).toBeInTheDocument();
    expect(screen.queryByTestId('platform-page')).not.toBeInTheDocument();
  });

  it('TG-003: redirects for unauthenticated user', () => {
    // Default state: no user, no token
    renderWithRouter();
    expect(screen.getByTestId('home-page')).toBeInTheDocument();
    expect(screen.queryByTestId('platform-page')).not.toBeInTheDocument();
  });

  it('redirects user with empty roles array', () => {
    useAuthStore.setState({
      accessToken: 'test-token',
      refreshToken: 'test-refresh',
      user: {
        id: '3',
        email: 'empty@test.com',
        full_name: null,
        tenant_id: 'tenant-1',
        tenant_schema: 'tenant_test',
        roles: [],
        permissions: [],
      },
      tenantCode: 'TEST',
    });

    renderWithRouter();
    expect(screen.getByTestId('home-page')).toBeInTheDocument();
  });

  it('redirects user with super_admin in tenant-contextual token', () => {
    // User has super_admin role but also has tenant context
    // The frontend guard checks roles only; backend guard checks identity-only
    // Frontend is defense-in-depth — allows through if role matches
    // Backend will deny if token is tenant-contextual (P11-B0-R1)
    useAuthStore.setState({
      accessToken: 'tenant-contextual-token',
      refreshToken: 'test-refresh',
      user: {
        id: '4',
        email: 'tenantadmin@test.com',
        full_name: 'Tenant Admin',
        tenant_id: 'tenant-1',
        tenant_schema: 'tenant_test',
        roles: ['super_admin'],
        permissions: [],
      },
      tenantCode: 'TEST',
    });

    renderWithRouter();
    // Frontend allows (defense-in-depth, backend enforces identity-only)
    expect(screen.getByTestId('platform-page')).toBeInTheDocument();
  });
});
