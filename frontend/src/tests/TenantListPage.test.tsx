import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { TenantListPage } from '@/pages/tenants/TenantListPage';
import { useAuthStore } from '@/stores/authStore';

const mockGetAll = vi.fn();
const mockCreate = vi.fn();
const mockUpdate = vi.fn();
const mockDelete = vi.fn();

vi.mock('@/services/tenantService', () => ({
  tenantService: {
    getAll: (...args: unknown[]) => mockGetAll(...args),
    create: (...args: unknown[]) => mockCreate(...args),
    update: (...args: unknown[]) => mockUpdate(...args),
    delete: (...args: unknown[]) => mockDelete(...args),
  },
}));

const emptyTenantListResponse = {
  data: {
    success: true,
    data: {
      items: [],
      pagination: { page: 1, size: 20, total: 0, pages: 0 },
    },
    timestamp: '2026-07-03T00:00:00Z',
  },
};

const createRegistryResponse = {
  data: {
    success: true,
    data: {
      id: 'tenant-1',
      code: 'ACME01',
      name: 'Acme Wholesale',
      address: null,
      contact: null,
      plan_type: null,
      schema_name: 't_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      created_at: '2026-07-03T00:00:00Z',
      updated_at: '2026-07-03T00:00:00Z',
    },
    message: 'Registry record created only; tenant schema, login, admin user, RBAC, inventory, orders, and finance workspace were not provisioned.',
    timestamp: '2026-07-03T00:00:00Z',
  },
};

function setWritableUser() {
  useAuthStore.setState({
    user: {
      id: 'user-1',
      email: 'user@example.com',
      full_name: 'Tenant Admin',
      tenant_id: 'tenant-1',
      tenant_schema: 't_test',
      roles: ['super_admin'],
      permissions: ['wholesalers:read', 'wholesalers:write'],
    },
  });
}

describe('TenantListPage truth gate', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setWritableUser();
    mockGetAll.mockResolvedValue(emptyTenantListResponse);
    mockCreate.mockResolvedValue(createRegistryResponse);
  });

  it('labels creation as registry-only instead of complete customer provisioning', async () => {
    render(<TenantListPage />);

    expect(await screen.findByText('System Tenant Registry')).toBeInTheDocument();
    expect(screen.getByText(/registry records/i)).toBeInTheDocument();
    expect(screen.getByText(/This creates a registry record only/i)).toBeInTheDocument();
    expect(screen.getByText(/does not provision login, tenant schema, admin user, RBAC, inventory, orders, or finance workspace/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /create registry record/i })).toBeInTheDocument();

    expect(screen.queryByRole('button', { name: /create customer/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/customer ready/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/ready to log in/i)).not.toBeInTheDocument();
  });

  it('shows registry-only warning in the create form and success notice', async () => {
    render(<TenantListPage />);

    await userEvent.click(await screen.findByRole('button', { name: /create registry record/i }));

    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText('Create customer registry record')).toBeInTheDocument();
    expect(within(dialog).getByText(/This creates a registry record only/i)).toBeInTheDocument();
    expect(within(dialog).getByText(/does not provision login, tenant schema, admin user, RBAC, inventory, orders, or finance workspace/i)).toBeInTheDocument();

    await userEvent.type(within(dialog).getByLabelText(/tenant code/i), 'ACME01');
    await userEvent.type(within(dialog).getByLabelText(/^name$/i), 'Acme Wholesale');
    await userEvent.click(within(dialog).getByRole('button', { name: /create registry record/i }));

    await waitFor(() => {
      expect(mockCreate).toHaveBeenCalledWith({
        code: 'ACME01',
        name: 'Acme Wholesale',
        address: null,
        contact: null,
        plan_type: null,
      });
    });

    expect(await screen.findByText(/Registry record created only/i)).toBeInTheDocument();
    expect(screen.getByText(/were not provisioned/i)).toBeInTheDocument();
    expect(screen.queryByText(/customer ready/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/tenant ready/i)).not.toBeInTheDocument();
  });
});
