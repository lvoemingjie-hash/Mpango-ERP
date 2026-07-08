/**
 * P25-C RESOLVED-DEFECT GUARDS (was P25-B recorded defects; contract 6.8 / 9).
 *
 * P25-B recorded two customer-readiness defects and deliberately turned a blind
 * eye -- its tests were GREEN while the defects existed. P25-C is the approved
 * fix slice:
 *   D2 -- PlatformAuditEventsPage / PlatformTenantDirectoryPage now pass the
 *         REQUIRED `icon` prop to <EmptyState>, so the empty branch renders.
 *   D1 -- hub links were added so every platform route is reachable by a
 *         Sidebar link or an in-app <Link> (no route is URL-only).
 *
 * These tests now GUARD the fix: GREEN while it holds, RED the moment a defect
 * regresses (icon removed -> render throws; hub link removed -> route goes
 * URL-only). The two formerly-D2 routes are back in the SWEEP_ROUTES sweeps in
 * P25_StateMatrix / P25_CopySafety / P25_ForbiddenControls, where the full
 * matrix coverage lives; this file is the focused regression guard.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { waitFor } from '@testing-library/react';

vi.mock('@/services/api', () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

import { api } from '@/services/api';
import {
  EMPTY_BODY,
  PLATFORM_ROUTES,
  URL_ONLY_ROUTES,
  routeIsReachable,
  IDENTITY_ONLY_SUPER_ADMIN,
  setAuth,
  clearAuth,
  resetPlatformStore,
  renderPlatformAt,
} from './__helpers__/readiness';

beforeEach(() => {
  clearAuth();
  setAuth(IDENTITY_ONLY_SUPER_ADMIN, 'token');
  resetPlatformStore();
  vi.clearAllMocks();
  vi.mocked(api.get).mockResolvedValue({ data: EMPTY_BODY });
  vi.mocked(api.post).mockResolvedValue({ data: {} });
});

describe('P25-C D2 resolved -- empty-state renders safely (AC 5)', () => {
  // EmptyState now carries its required `icon` prop, so reaching the empty
  // branch no longer throws "Element type is invalid". We render the page, let
  // the backing read settle onto the EMPTY branch (the store clears the loading
  // flag on a successful empty read), and assert the empty copy is present. If
  // the icon prop regresses, render throws and these turn RED.
  it('D2-a: PlatformAuditEventsPage empty branch renders "No audit events" (no throw)', async () => {
    const { container } = renderPlatformAt('/platform/audit');
    await waitFor(
      () => {
        expect(container.textContent ?? '').toContain('No audit events');
      },
      { timeout: 2000 },
    );
  });

  it('D2-b: PlatformTenantDirectoryPage empty branch renders "No tenants found" (no throw)', async () => {
    const { container } = renderPlatformAt('/platform/tenants');
    await waitFor(
      () => {
        expect(container.textContent ?? '').toContain('No tenants found');
      },
      { timeout: 2000 },
    );
  });
});

describe('P25-C D1 resolved -- every platform route is reachable (AC 9)', () => {
  // Reachability is REAL: every route has a Sidebar link OR an in-app <Link>
  // from a platform page/component. The helper scans the shipped platform
  // source to compute URL_ONLY_ROUTES, so that list is EMPTY now and turns
  // non-empty the moment a hub/sidebar link is removed -- these go RED if
  // reachability regresses.
  it('D1-a: no platform route is URL-only (URL_ONLY_ROUTES is empty)', () => {
    expect(URL_ONLY_ROUTES).toHaveLength(0);
  });

  it('D1-b: every route is reachable by Sidebar link or in-app Link', () => {
    const unreachable = PLATFORM_ROUTES.filter((r) => !routeIsReachable(r)).map((r) => r.path);
    expect(unreachable, 'every platform route must be reachable').toEqual([]);
  });
});
