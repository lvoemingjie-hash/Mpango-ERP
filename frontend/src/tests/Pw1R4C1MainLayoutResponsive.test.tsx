/**
 * DC-12R1-MVP-L1-PW1-R4-C1 — Responsive MainLayout + Mobile Navigation tests (T1–T9).
 *
 * Renders the REAL MainLayout + Header + Sidebar with MemoryRouter/Routes.
 * No fake guards, no fake layout. Tests are order-independent (each renders
 * from scratch) so they pass in natural, shuffled and reverse order.
 */
import { beforeEach, describe, expect, it } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { MainLayout } from '@/components/layout/MainLayout';
import { useAuthStore } from '@/stores/authStore';
import type { CurrentUserData } from '@/types/auth';

function renderApp(initialEntry = '/') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route element={<MainLayout />}>
          <Route path="/" element={<div data-testid="page-home">Home Page</div>} />
          <Route path="/orders" element={<div data-testid="page-orders">Orders Page</div>} />
          <Route
            path="/very/deep/long-breadcrumb-path-segment"
            element={<div data-testid="page-deep">Deep Page</div>}
          />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

function getHamburger() {
  return screen.getByRole('button', { name: 'Toggle navigation menu' });
}

function getDrawer() {
  return document.getElementById('mobile-navigation-drawer');
}

function getBackdrop() {
  return screen.queryByTestId('mobile-backdrop');
}

function openDrawer() {
  fireEvent.click(getHamburger());
  expect(getDrawer()).not.toBeNull();
}

const testUser = ({
  full_name = 'Example User',
  email = 'person@example.invalid',
} = {}) =>
  ({
    id: 'test-user',
    email,
    full_name,
    tenant_id: 'tenant-1',
    tenant_schema: 'tenant_test',
    permissions: [],
  } as unknown) as CurrentUserData;

describe('PW1-R4-C1 MainLayout responsive + mobile navigation (T1–T9)', () => {
  beforeEach(() => {
    cleanup();
    useAuthStore.setState({
      accessToken: 'redacted-test-access-token',
      refreshToken: 'redacted-test-refresh-token',
      user: testUser(),
      tenantCode: 'TST',
    });
  });

  it('T1: hamburger exists with complete aria attributes', () => {
    renderApp();
    const hamburger = getHamburger();
    expect(hamburger).toBeInTheDocument();
    expect(hamburger).toHaveAttribute('aria-label', 'Toggle navigation menu');
    expect(hamburger).toHaveAttribute('aria-expanded', 'false');
    expect(hamburger).toHaveAttribute('aria-controls', 'mobile-navigation-drawer');
  });

  it('T2: drawer is closed by default and its links are not focusable / not in the accessibility tree', () => {
    renderApp();
    expect(getDrawer()).toBeNull();
    expect(getBackdrop()).toBeNull();
    // No drawer links anywhere in the a11y tree while closed.
    expect(screen.queryByRole('dialog', { name: 'Navigation menu' })).toBeNull();
    // Desktop nav exists, but the closed mobile drawer contributes no
    // duplicate focusable navigation links (exactly one "Sales" link).
    expect(screen.getAllByRole('link', { name: /sales/i })).toHaveLength(1);
  });

  it('T3: hamburger opens the drawer and the backdrop appears', () => {
    renderApp();
    fireEvent.click(getHamburger());
    const drawer = getDrawer();
    expect(drawer).not.toBeNull();
    expect(drawer).toHaveAttribute('role', 'dialog');
    expect(drawer).toHaveAttribute('aria-modal', 'true');
    expect(getBackdrop()).not.toBeNull();
    expect(getHamburger()).toHaveAttribute('aria-expanded', 'true');
    // Drawer navigation links are present and focusable while open.
    expect(screen.getAllByRole('link', { name: /sales/i })).toHaveLength(2);
  });

  it('T4: hamburger, backdrop and Escape each close the drawer', () => {
    renderApp();
    // Backdrop close
    openDrawer();
    fireEvent.click(getBackdrop()!);
    expect(getDrawer()).toBeNull();
    expect(getHamburger()).toHaveAttribute('aria-expanded', 'false');

    // Escape close
    openDrawer();
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(getDrawer()).toBeNull();

    // Hamburger toggle close
    openDrawer();
    fireEvent.click(getHamburger());
    expect(getDrawer()).toBeNull();
  });

  it('T5: focus returns to the hamburger after Escape/backdrop close', () => {
    renderApp();
    // Backdrop close
    openDrawer();
    fireEvent.click(getBackdrop()!);
    expect(getDrawer()).toBeNull();
    expect(getHamburger()).toHaveFocus();

    // Escape close
    openDrawer();
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(getDrawer()).toBeNull();
    expect(getHamburger()).toHaveFocus();
  });

  it('T6: navigating a route closes the drawer', () => {
    renderApp();
    openDrawer();
    fireEvent.click(screen.getAllByRole('link', { name: /sales/i })[1]);
    expect(screen.getByTestId('page-orders')).toBeInTheDocument();
    expect(getDrawer()).toBeNull();
    expect(getBackdrop()).toBeNull();
  });

  it('T7: lg+ keeps the desktop sidebar visible and hides the hamburger', () => {
    renderApp();
    const desktopSidebar = document.querySelector('aside');
    expect(desktopSidebar).not.toBeNull();
    // Desktop sidebar is hidden below lg and flex from lg up.
    expect(desktopSidebar!.className).toContain('hidden');
    expect(desktopSidebar!.className).toContain('lg:flex');
    expect(desktopSidebar!.className).toContain('w-64');
    // Hamburger is hidden from lg up.
    expect(getHamburger().className).toContain('lg:hidden');
  });

  it('T8: content uses conditional lg:ml-64 (not unconditional ml-64) with min-w-0', () => {
    const { container } = renderApp();
    const contentWrapper = container.querySelector('main')!.parentElement!;
    expect(contentWrapper.className).toContain('lg:ml-64');
    expect(contentWrapper.className).not.toMatch(/(^|\s)ml-64(?!\S)/);
    expect(contentWrapper.className).toContain('min-w-0');
    expect(container.querySelector('main')!.className).toContain('min-w-0');
    // No overflow masking anywhere in the shell.
    expect(container.innerHTML).not.toContain('overflow-x-hidden');
    expect(container.innerHTML).not.toContain('overflow-hidden');
  });

  it('T9: long tenant code, username and breadcrumb adapt via shrink/truncate without deleting information', () => {
    useAuthStore.setState({
      user: testUser({ full_name: 'A Very Long Wholesaler Operator Full Name' }),
      tenantCode: 'TENANT-CODE-VERY-LONG-1234567890',
    });
    renderApp('/very/deep/long-breadcrumb-path-segment');

    // Long tenant code: full value preserved via title, visually truncated.
    const tenantBadge = screen.getByText('TENANT-CODE-VERY-LONG-1234567890');
    expect(tenantBadge.className).toContain('truncate');
    expect(tenantBadge).toHaveAttribute('title', 'TENANT-CODE-VERY-LONG-1234567890');

    // Long username: full value preserved via title, visually truncated.
    const userName = screen.getByText('A Very Long Wholesaler Operator Full Name');
    expect(userName.className).toContain('truncate');
    expect(userName).toHaveAttribute(
      'title',
      'A Very Long Wholesaler Operator Full Name',
    );

    // Breadcrumbs: every crumb still rendered (no deletion), with truncate.
    expect(screen.getByText('Very')).toBeInTheDocument();
    expect(screen.getByText('Deep')).toBeInTheDocument();
    expect(screen.getByText('Long-breadcrumb-path-segment')).toBeInTheDocument();
    const crumbs = screen.getAllByText(/Long-breadcrumb-path-segment/i);
    expect(crumbs[0].className).toContain('truncate');

    // Breadcrumb nav participates in the shrink contract.
    const breadcrumbNav = screen.getByLabelText('Breadcrumb');
    expect(breadcrumbNav.className).toContain('min-w-0');
  });
});
