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
import { PlatformRoute, RetailerPermissionRoute, isIdentityPlatformOperator } from '@/router/guards';
import { CLIENT_PERMISSIONS } from '@/utils/permissions';
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

// ===========================================================================
// DC-12R1-MVP-R0-R1 (WPR-002/WPR-003): RetailerPermissionRoute guard.
//
// Reuses can() (no independent permission algorithm). A route is admitted only
// when the user holds the required client:* permission; otherwise it fails
// closed (redirect) BEFORE the child page renders. Admins bypass via can().
// ===========================================================================

function renderRetailerPermissionRoute(initialPath = '/guarded', permission: string = CLIENT_PERMISSIONS.PAYMENTS_DECLARE) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route element={<RetailerPermissionRoute permission={permission} />}>
          <Route path="/guarded" element={<div data-testid="guarded-page">Guarded</div>} />
        </Route>
        {/* Fail-closed redirect target used by the guard. */}
        <Route path="/client" element={<div data-testid="client-home">Client Home</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('RetailerPermissionRoute guard', () => {
  beforeEach(() => {
    useAuthStore.setState({
      accessToken: null,
      refreshToken: null,
      user: null,
      tenantCode: null,
    });
  });

  it('admits a retailer_operator holding the required permission', () => {
    useAuthStore.setState({
      accessToken: 'tok',
      refreshToken: 'ref',
      user: {
        id: 'r1',
        email: 'r@e.com',
        full_name: 'R',
        tenant_id: 't1',
        tenant_schema: 't_1',
        roles: ['retailer_operator'],
        permissions: ['client:payments:declare'],
      },
      tenantCode: null,
    });
    renderRetailerPermissionRoute('/guarded', CLIENT_PERMISSIONS.PAYMENTS_DECLARE);
    expect(screen.getByTestId('guarded-page')).toBeInTheDocument();
    expect(screen.queryByTestId('client-home')).not.toBeInTheDocument();
  });

  it('fails closed (redirects to /client) when the permission is missing', () => {
    // RED/GREEN: before WPR-002 the client print/declare routes admitted any
    // retailer_operator regardless of permissions; this permission-empty user
    // must now be denied.
    useAuthStore.setState({
      accessToken: 'tok',
      refreshToken: 'ref',
      user: {
        id: 'r2',
        email: 'r2@e.com',
        full_name: 'R2',
        tenant_id: 't1',
        tenant_schema: 't_1',
        roles: ['retailer_operator'],
        permissions: [],
      },
      tenantCode: null,
    });
    renderRetailerPermissionRoute('/guarded', CLIENT_PERMISSIONS.PAYMENTS_DECLARE);
    // The guarded page NEVER renders.
    expect(screen.queryByTestId('guarded-page')).not.toBeInTheDocument();
    expect(screen.getByTestId('client-home')).toBeInTheDocument();
  });

  it('denies a retailer holding a DIFFERENT client permission (precision)', () => {
    useAuthStore.setState({
      accessToken: 'tok',
      refreshToken: 'ref',
      user: {
        id: 'r3',
        email: 'r3@e.com',
        full_name: 'R3',
        tenant_id: 't1',
        tenant_schema: 't_1',
        roles: ['retailer_operator'],
        // Holds payments:read but NOT payments:declare.
        permissions: ['client:payments:read'],
      },
      tenantCode: null,
    });
    renderRetailerPermissionRoute('/guarded', CLIENT_PERMISSIONS.PAYMENTS_DECLARE);
    expect(screen.queryByTestId('guarded-page')).not.toBeInTheDocument();
    expect(screen.getByTestId('client-home')).toBeInTheDocument();
  });

  it('admin bypass: admits an admin even without the permission in the list', () => {
    useAuthStore.setState({
      accessToken: 'tok',
      refreshToken: 'ref',
      user: {
        id: 'a1',
        email: 'a@e.com',
        full_name: 'A',
        tenant_id: 't1',
        tenant_schema: 't_1',
        roles: ['admin'],
        permissions: [],
      },
      tenantCode: null,
    });
    renderRetailerPermissionRoute('/guarded', CLIENT_PERMISSIONS.FINANCE_READ);
    expect(screen.getByTestId('guarded-page')).toBeInTheDocument();
  });

  it('denies an unauthenticated (null) user', () => {
    renderRetailerPermissionRoute('/guarded', CLIENT_PERMISSIONS.ORDERS_READ);
    expect(screen.queryByTestId('guarded-page')).not.toBeInTheDocument();
    expect(screen.getByTestId('client-home')).toBeInTheDocument();
  });
});
