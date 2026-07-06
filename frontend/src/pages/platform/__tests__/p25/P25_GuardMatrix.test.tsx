/**
 * P25-B dimension: identity-only guard matrix (matrix dim 2; section 3.6; C13).
 *
 * The P10/P11 PlatformRoute guard is shared by all 19 routes, so it is exercised
 * once at the guard level. Asserts the admit path AND both deny paths:
 *   - identity-only (global) super_admin  -> admitted (Outlet renders)
 *   - tenant-contextual super_admin        -> denied (Navigate to "/")
 *   - non-super_admin regular user         -> denied (Navigate to "/")
 *   - unauthenticated (no user)            -> denied (Navigate to "/")
 *
 * A denied operator is redirected to "/", never leaked into the cockpit.
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { PlatformRoute, isIdentityPlatformOperator } from '@/router/guards';
import {
  IDENTITY_ONLY_SUPER_ADMIN,
  TENANT_CONTEXTUAL_SUPER_ADMIN,
  REGULAR_USER,
  setAuth,
  clearAuth,
} from './__helpers__/readiness';

function renderGuarded() {
  return render(
    <MemoryRouter initialEntries={['/platform/operator-tasks']}>
      <Routes>
        <Route path="/" element={<div data-testid="home">home</div>} />
        <Route element={<PlatformRoute />}>
          <Route path="/platform/operator-tasks" element={<div data-testid="console">console</div>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(clearAuth);

describe('P25-B identity-only guard admit/deny matrix', () => {
  it('P25-G01: identity-only global super_admin is ADMITTED', () => {
    setAuth(IDENTITY_ONLY_SUPER_ADMIN, 'token');
    renderGuarded();
    expect(screen.getByTestId('console')).toBeInTheDocument();
    expect(screen.queryByTestId('home')).not.toBeInTheDocument();
  });

  it('P25-G02: tenant-contextual super_admin is DENIED (no leak)', () => {
    setAuth(TENANT_CONTEXTUAL_SUPER_ADMIN, 'token');
    renderGuarded();
    expect(screen.queryByTestId('console')).not.toBeInTheDocument();
    expect(screen.getByTestId('home')).toBeInTheDocument();
  });

  it('P25-G03: non-super_admin regular user is DENIED (no leak)', () => {
    setAuth(REGULAR_USER, 'token');
    renderGuarded();
    expect(screen.queryByTestId('console')).not.toBeInTheDocument();
    expect(screen.getByTestId('home')).toBeInTheDocument();
  });

  it('P25-G04: unauthenticated (no user / no token) is DENIED (no leak)', () => {
    clearAuth();
    renderGuarded();
    expect(screen.queryByTestId('console')).not.toBeInTheDocument();
    expect(screen.getByTestId('home')).toBeInTheDocument();
  });

  it('P25-G05: isIdentityPlatformOperator matches the guard exactly (no drift)', () => {
    // The Sidebar reuses the same predicate; assert it agrees with the guard on
    // every identity class so nav visibility and route admission cannot drift.
    expect(isIdentityPlatformOperator(IDENTITY_ONLY_SUPER_ADMIN)).toBe(true);
    expect(isIdentityPlatformOperator(TENANT_CONTEXTUAL_SUPER_ADMIN)).toBe(false);
    expect(isIdentityPlatformOperator(REGULAR_USER)).toBe(false);
    expect(isIdentityPlatformOperator(null)).toBe(false);
  });
});
