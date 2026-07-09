/**
 * P11-B1/R1: PlatformRoute guard tests.
 *
 * Tests:
 *   TG-001: PlatformRoute renders for identity-only super_admin
 *   TG-002: PlatformRoute redirects for regular user
 *   TG-003: PlatformRoute redirects for unauthenticated user
 *   TG-004: PlatformRoute redirects for tenant-contextual super_admin
 *   TG-005: isIdentityPlatformOperator helper
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { PlatformRoute, isIdentityPlatformOperator } from '@/router/guards';
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

const IDENTITY_SUPER_ADMIN = {
  id: '1',
  email: 'admin@test.com',
  full_name: 'Admin',
  tenant_id: null,
  tenant_schema: null,
  roles: ['super_admin'],
  permissions: [],
};

const TENANT_CONTEXTUAL_SUPER_ADMIN = {
  id: '4',
  email: 'tenantadmin@test.com',
  full_name: 'Tenant Admin',
  tenant_id: 'tenant-1',
  tenant_schema: 'tenant_test',
  roles: ['super_admin'],
  permissions: [],
};

describe('PlatformRoute guard', () => {
  it('TG-001: renders for identity-only super_admin (tenant_id=null, tenant_schema=null)', () => {
    useAuthStore.setState({
      accessToken: 'test-token',
      refreshToken: 'test-refresh',
      user: IDENTITY_SUPER_ADMIN,
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

  it('TG-004: redirects tenant-contextual super_admin (tenant_id != null)', () => {
    useAuthStore.setState({
      accessToken: 'tenant-contextual-token',
      refreshToken: 'test-refresh',
      user: TENANT_CONTEXTUAL_SUPER_ADMIN,
      tenantCode: 'TEST',
    });

    renderWithRouter();
    // Tenant-contextual super_admin MUST be redirected — identity-only enforcement
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

  it('redirects super_admin with tenant_schema but null tenant_id', () => {
    useAuthStore.setState({
      accessToken: 'test-token',
      refreshToken: 'test-refresh',
      user: {
        id: '5',
        email: 'edge@test.com',
        full_name: 'Edge Case',
        tenant_id: null,
        tenant_schema: 'tenant_test',
        roles: ['super_admin'],
        permissions: [],
      },
      tenantCode: 'TEST',
    });

    renderWithRouter();
    expect(screen.getByTestId('home-page')).toBeInTheDocument();
    expect(screen.queryByTestId('platform-page')).not.toBeInTheDocument();
  });
});

describe('isIdentityPlatformOperator', () => {
  it('returns true for identity-only super_admin', () => {
    expect(isIdentityPlatformOperator(IDENTITY_SUPER_ADMIN)).toBe(true);
  });

  it('returns false for tenant-contextual super_admin', () => {
    expect(isIdentityPlatformOperator(TENANT_CONTEXTUAL_SUPER_ADMIN)).toBe(false);
  });

  it('returns false for null user', () => {
    expect(isIdentityPlatformOperator(null)).toBe(false);
  });

  it('returns false for regular admin', () => {
    expect(isIdentityPlatformOperator({
      id: '2',
      email: 'user@test.com',
      full_name: 'User',
      tenant_id: 'tenant-1',
      tenant_schema: 'tenant_test',
      roles: ['admin'],
      permissions: [],
    })).toBe(false);
  });
});
