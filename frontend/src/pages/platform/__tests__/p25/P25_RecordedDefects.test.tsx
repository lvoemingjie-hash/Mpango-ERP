/**
 * P25-B RECORDED DEFECTS (contract section 6.8 / section 9).
 *
 * P25-B is a readiness HARNESS: it records defects for a later, separately
 * approved fix slice; it never fixes them inline. The tests below assert the
 * AS-BUILT defective behavior, so they are GREEN while the defect exists and
 * turn RED the moment a fix lands -- a built-in reminder to move the route back
 * into the passing sweeps in P25_StateMatrix / P25_CopySafety /
 * P25_ForbiddenControls.
 *
 * Defects recorded by this harness (see matrix README + ledger for detail):
 *   D1 -- navigation reachability gap: 8 of the 9 non-sidebar routes have no
 *         sidebar link AND no in-app parent-page link (URL-only today).
 *   D2 -- empty-state render crash: PlatformAuditEventsPage and
 *         PlatformTenantDirectoryPage call <EmptyState> WITHOUT the required
 *         `icon` prop, so the page throws on any render that reaches the empty
 *         branch (incl. the initial mount before data lands). AC 5 violation.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { readFileSync, readdirSync } from 'node:fs';
import { resolve } from 'node:path';

vi.mock('@/services/api', () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

import { api } from '@/services/api';
import {
  EMPTY_BODY,
  URL_ONLY_ROUTES,
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

describe('P25-B recorded defect D2 -- empty-state render crash (AC 5)', () => {
  // These assertions PASS while the defect exists (render throws). When a fix
  // lands (EmptyState given an icon, or the pages stop using EmptyState), the
  // render stops throwing and these turn RED -- move the route back into the
  // SWEEP_ROUTES sweeps and delete the matching entry here.
  it('D2-a: PlatformAuditEventsPage THROWS on empty-state render (EmptyState missing icon)', () => {
    expect(() => renderPlatformAt('/platform/audit')).toThrow();
  });

  it('D2-b: PlatformTenantDirectoryPage THROWS on empty-state render (EmptyState missing icon)', () => {
    expect(() => renderPlatformAt('/platform/tenants')).toThrow();
  });
});

describe('P25-B recorded defect D1 -- navigation reachability gap (AC 9)', () => {
  // The Sidebar reaches 10 routes directly + 1 via a parent page (tenant health
  // from the tenant directory card). The routes below have NO sidebar link and
  // NO in-app <Link> from any platform page (verified against the platform page
  // + component source). They are reachable only by direct URL today. Recorded
  // for a separately approved fix slice; NOT fixed inline by P25-B.
  // Vitest runs with cwd at the frontend root (where vite.config.ts lives).
  const PLATFORM_SRC = resolve(process.cwd(), 'src/pages/platform');
  const COMPONENT_SRC = resolve(process.cwd(), 'src/components/platform');

  function readAllPlatformSource(): string {
    const dirs = [PLATFORM_SRC, resolve(PLATFORM_SRC, 'ops')];
    let acc = '';
    for (const d of dirs) {
      for (const f of readdirSync(d) as string[]) {
        if (f.endsWith('.tsx') && !f.includes('.test.')) {
          acc += readFileSync(resolve(d, f), 'utf-8');
        }
      }
    }
    for (const f of readdirSync(COMPONENT_SRC) as string[]) {
      if (f.endsWith('.tsx') && !f.includes('.test.')) {
        acc += readFileSync(resolve(COMPONENT_SRC, f), 'utf-8');
      }
    }
    return acc;
  }

  it('D1: documents the 7 strictly URL-only routes (no sidebar link, no in-app Link)', () => {
    const source = readAllPlatformSource();
    // Of the 9 non-sidebar routes: tenant-health is linked from the tenant
    // directory card (PlatformTenantCard), and /platform/tenants has a back-link
    // from tenant-health -- the remaining 7 have neither a sidebar link nor any
    // in-app <Link>. (Functionally 9 of 19 routes are not sidebar-reachable;
    // see matrix README for the cluster nuance.)
    expect(URL_ONLY_ROUTES.length).toBe(7);
    for (const r of URL_ONLY_ROUTES) {
      // No platform page/component source contains a router Link to this path.
      // (Template-literal links like `/platform/tenants/${id}/health` are the
      // only inter-page links that exist; the 8 URL-only paths appear only in
      // AppRouter.tsx route declarations, never as a Link target.)
      const literal = `to="/platform/${r.path.replace('/platform/', '')}"`;
      expect(source, `${r.path} should be URL-only (no in-app Link)`).not.toContain(literal);
    }
  });
});
