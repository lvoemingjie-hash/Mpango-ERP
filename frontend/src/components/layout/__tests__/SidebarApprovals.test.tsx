/**
 * P19-C: Sidebar approvals link visibility tests.
 *
 * Verifies the Approvals nav entry appears only for an identity-only
 * super_admin (exactly where the existing platform entries appear), is absent
 * for tenant-contextual / non-platform users and when logged out, and points at
 * /platform/approvals. No tenant or product route is touched.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { Sidebar } from '@/components/layout/Sidebar';
import { useAuthStore } from '@/stores/authStore';

// Mirror the existing SidebarOps test: mock platformService to prevent import errors.
vi.mock('@/services/platformApi', () => ({
  platformService: {},
}));

beforeEach(() => {
  useAuthStore.setState({ user: null, accessToken: null });
});

function renderSidebar() {
  return render(
    <MemoryRouter>
      <Sidebar />
    </MemoryRouter>,
  );
}

function identityOperator() {
  useAuthStore.setState({
    user: {
      id: 'test-user',
      email: 'admin@mpango.com',
      full_name: 'Admin',
      roles: ['super_admin'],
      tenant_id: null,
      tenant_schema: null,
      permissions: [],
    },
    accessToken: 'valid-token',
  });
}

describe('Sidebar P19 approvals link', () => {
  it('shows the Approvals link for identity-only super_admin', () => {
    identityOperator();
    renderSidebar();
    expect(screen.getByText('Approvals')).toBeInTheDocument();
  });

  it('Approvals link points to /platform/approvals', () => {
    identityOperator();
    renderSidebar();
    const link = screen.getByText('Approvals').closest('a');
    expect(link).toHaveAttribute('href', '/platform/approvals');
  });

  it('does not show the Approvals link for a tenant-contextual super_admin', () => {
    useAuthStore.setState({
      user: {
        id: 'ctx-admin',
        email: 'admin@mpango.com',
        full_name: 'Admin',
        roles: ['super_admin'],
        tenant_id: 'tenant-123',
        tenant_schema: 't_test',
        permissions: [],
      },
      accessToken: 'valid-token',
    });
    renderSidebar();
    expect(screen.queryByText('Approvals')).not.toBeInTheDocument();
  });

  it('does not show the Approvals link for non-platform users', () => {
    useAuthStore.setState({
      user: {
        id: 'regular-user',
        email: 'user@mpango.com',
        full_name: 'User',
        roles: ['user'],
        tenant_id: 'some-tenant-id',
        tenant_schema: 't_test',
        permissions: [],
      },
      accessToken: 'valid-token',
    });
    renderSidebar();
    expect(screen.queryByText('Approvals')).not.toBeInTheDocument();
  });

  it('does not show the Approvals link when not logged in', () => {
    renderSidebar();
    expect(screen.queryByText('Approvals')).not.toBeInTheDocument();
  });
});
