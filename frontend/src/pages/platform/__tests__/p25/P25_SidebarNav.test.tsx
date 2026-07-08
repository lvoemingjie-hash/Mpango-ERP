/**
 * P25-B dimension: sidebar navigation (matrix dims 3 + 8; section 3.6; AC 9; C13).
 *
 * Asserts the Sidebar platform section:
 *   - shows all 10 direct platform links to an identity-only super_admin
 *   - hides the ENTIRE platform section from a tenant-contextual super_admin
 *   - hides the ENTIRE platform section from a non-super_admin / unauthenticated
 *   - highlights the correct link as active on its own route
 *
 * Queries are by href (unambiguous); the "Platform" overview label collides
 * with the section header text, so text-based queries are avoided.
 *
 * Parent-group reachability for the 9 non-sidebar routes is recorded in the
 * matrix README (defect D1): 1 is linked from a parent page (tenant health),
 * 8 are reachable only by direct URL today.
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { Sidebar } from '@/components/layout/Sidebar';
import {
  SIDEBAR_ROUTES,
  IDENTITY_ONLY_SUPER_ADMIN,
  TENANT_CONTEXTUAL_SUPER_ADMIN,
  REGULAR_USER,
  setAuth,
  clearAuth,
} from './__helpers__/readiness';

function renderSidebarAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Sidebar />
    </MemoryRouter>,
  );
}

function linkFor(container: HTMLElement, href: string): HTMLAnchorElement | null {
  return container.querySelector<HTMLAnchorElement>(`a[href="${href}"]`);
}

beforeEach(clearAuth);

describe('P25-B sidebar platform nav -- visibility by identity', () => {
  it('P25-S01: identity-only super_admin sees all 10 direct platform links', () => {
    setAuth(IDENTITY_ONLY_SUPER_ADMIN, 'token');
    const { container } = renderSidebarAt('/platform');
    for (const r of SIDEBAR_ROUTES) {
      // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
      const link = linkFor(container, r.sidebarPath!);
      expect(link, `sidebar link ${r.sidebarPath} for ${r.name}`).not.toBeNull();
    }
    expect(SIDEBAR_ROUTES.length).toBe(10);
  });

  it('P25-S02: tenant-contextual super_admin sees NO platform link', () => {
    setAuth(TENANT_CONTEXTUAL_SUPER_ADMIN, 'token');
    const { container } = renderSidebarAt('/platform');
    for (const r of SIDEBAR_ROUTES) {
      // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
      expect(linkFor(container, r.sidebarPath!), `${r.sidebarPath} should be hidden`).toBeNull();
    }
  });

  it('P25-S03: non-super_admin regular user sees NO platform link', () => {
    setAuth(REGULAR_USER, 'token');
    const { container } = renderSidebarAt('/platform');
    for (const r of SIDEBAR_ROUTES) {
      // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
      expect(linkFor(container, r.sidebarPath!), `${r.sidebarPath} should be hidden`).toBeNull();
    }
  });

  it('P25-S04: unauthenticated sees NO platform link', () => {
    clearAuth();
    const { container } = renderSidebarAt('/platform');
    for (const r of SIDEBAR_ROUTES) {
      // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
      expect(linkFor(container, r.sidebarPath!), `${r.sidebarPath} should be hidden`).toBeNull();
    }
  });
});

describe('P25-B sidebar active-link highlight (AC 9)', () => {
  it.each(SIDEBAR_ROUTES)(
    'P25-SH: "$name" link is highlighted active on its own route ($sidebarPath)',
    (r) => {
      setAuth(IDENTITY_ONLY_SUPER_ADMIN, 'token');
      // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
      const { container } = renderSidebarAt(r.sidebarPath!);
      // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
      const link = linkFor(container, r.sidebarPath!);
      expect(link).not.toBeNull();
      // The active link carries the primary-50 background tone class.
      expect(link?.getAttribute('class') ?? '').toMatch(/bg-primary-50/);
    },
  );
});
