/**
 * P13-D: Sidebar ops cockpit link tests.
 *
 * Verifies the Ops Cockpit link appears when platform admin
 * conditions are met, and does not appear otherwise.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { Sidebar } from '@/components/layout/Sidebar';
import { useAuthStore } from '@/stores/authStore';

// Mock platformService to prevent import errors
vi.mock('@/services/platformApi', () => ({
  platformService: {},
}));

beforeEach(() => {
  useAuthStore.setState({
    user: null,
    accessToken: null,
  });
});

function renderSidebar() {
  return render(
    <MemoryRouter>
      <Sidebar />
    </MemoryRouter>,
  );
}

describe('Sidebar P13 ops link', () => {
  it('shows Ops Cockpit link for identity-only super_admin', () => {
    useAuthStore.setState({
      user: {
        id: 'test-user',
        email: 'admin@mpango.com',
        name: 'Admin',
        roles: ['super_admin'],
        tenant_id: null,
        tenant_schema: null,
      },
      accessToken: 'valid-token',
    });

    renderSidebar();
    expect(screen.getByText('Ops Cockpit')).toBeInTheDocument();
  });

  it('does not show Ops Cockpit link for non-platform users', () => {
    useAuthStore.setState({
      user: {
        id: 'regular-user',
        email: 'user@mpango.com',
        name: 'User',
        roles: ['user'],
        tenant_id: 'some-tenant-id',
        tenant_schema: 't_test',
      },
      accessToken: 'valid-token',
    });

    renderSidebar();
    expect(screen.queryByText('Ops Cockpit')).not.toBeInTheDocument();
  });

  it('does not show Ops Cockpit link when not logged in', () => {
    renderSidebar();
    expect(screen.queryByText('Ops Cockpit')).not.toBeInTheDocument();
  });

  it('does not show Ops Cockpit for tenant-contextual super_admin', () => {
    useAuthStore.setState({
      user: {
        id: 'ctx-admin',
        email: 'admin@mpango.com',
        name: 'Admin',
        roles: ['super_admin'],
        tenant_id: 'tenant-123',
        tenant_schema: 't_test',
      },
      accessToken: 'valid-token',
    });

    renderSidebar();
    expect(screen.queryByText('Ops Cockpit')).not.toBeInTheDocument();
  });

  it('Ops Cockpit link points to /platform/ops/health', () => {
    useAuthStore.setState({
      user: {
        id: 'test-user',
        email: 'admin@mpango.com',
        name: 'Admin',
        roles: ['super_admin'],
        tenant_id: null,
        tenant_schema: null,
      },
      accessToken: 'valid-token',
    });

    renderSidebar();
    const link = screen.getByText('Ops Cockpit').closest('a');
    expect(link).toHaveAttribute('href', '/platform/ops/health');
  });
});
