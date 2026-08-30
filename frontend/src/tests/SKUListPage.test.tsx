/**
 * U3-D / U4-A Permission gate tests for SKUListPage.
 *
 * Verifies:
 *   Import gate:
 *   1. Import button visible when user has skus:import permission
 *   2. Import button visible when user has admin role (no skus:import perm)
 *   3. Import button hidden when user lacks skus:import and is not admin
 *   4. Import button hidden for unauthenticated (no user)
 *
 *   U4-A Product create/update gate (fixed: was inventory:write):
 *   5. Add Product visible when user has skus:create
 *   6. Add Product hidden when user has inventory:write but NOT skus:create
 *   7. Add Product visible for admin (bypass)
 *   8. Edit button hidden without skus:update
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { SKUListPage } from '@/pages/skus/SKUListPage';
import { catalogProductService } from '@/services/catalogProductService';
import type { AuthStore } from '@/stores/authStore';

// ---------------------------------------------------------------------------
// Mock dependencies
// ---------------------------------------------------------------------------

vi.mock('@/services/catalogProductService', () => ({
  catalogProductService: {
    getAll: vi.fn().mockResolvedValue({
      data: { data: { items: [] } },
    }),
  },
}));

vi.mock('@/stores/authStore', () => ({
  useAuthStore: vi.fn(),
}));

vi.mock('@/pages/skus/SKUFormModal', () => ({
  SKUFormModal: () => null,
}));

vi.mock('@/pages/skus/SKUImportModal', () => ({
  SKUImportModal: () => null,
}));

vi.mock('@/pages/skus/AddSellableUnitModal', () => ({
  AddSellableUnitModal: () => null,
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

import { useAuthStore } from '@/stores/authStore';
const mockedUseAuthStore = vi.mocked(useAuthStore);

function setUser(permissions: string[], roles: string[]) {
  mockedUseAuthStore.mockImplementation(((selector: (state: AuthStore) => unknown) =>
    selector({
      accessToken: 'test-token',
      refreshToken: 'test-refresh',
      user: { id: 'u1', email: 'test@test.com', full_name: 'Test', tenant_id: 't1', tenant_schema: 'ts1', permissions, roles },
      tenantCode: 'TC',
      retailerPortalCode: null,
      login: vi.fn(),
      retailerLogin: vi.fn(),
      logout: vi.fn(),
      updateTokens: vi.fn(),
      setUser: vi.fn(),
      beginWorkspaceSelection: vi.fn(),
    } as AuthStore)) as unknown as typeof mockedUseAuthStore);
}

function setNoUser() {
  mockedUseAuthStore.mockImplementation(((selector: (state: AuthStore) => unknown) =>
    selector({
      accessToken: null,
      refreshToken: null,
      user: null,
      tenantCode: null,
      retailerPortalCode: null,
      login: vi.fn(),
      retailerLogin: vi.fn(),
      logout: vi.fn(),
      updateTokens: vi.fn(),
      setUser: vi.fn(),
      beginWorkspaceSelection: vi.fn(),
    } as AuthStore)) as unknown as typeof mockedUseAuthStore);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('SKUListPage Import button permission gate', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(catalogProductService.getAll).mockResolvedValue({
      data: { data: { items: [] } },
    } as never);
  });

  it('shows Import button when user has skus:import permission', async () => {
    setUser(['skus:create', 'skus:import'], ['viewer']);

    render(<SKUListPage />);

    await waitFor(() => {
      expect(screen.getByText('Import Catalog SKUs')).toBeInTheDocument();
    });
  });

  it('shows Import button when user has admin role without skus:import', async () => {
    setUser([], ['admin']);

    render(<SKUListPage />);

    await waitFor(() => {
      expect(screen.getByText('Import Catalog SKUs')).toBeInTheDocument();
    });
  });

  it('hides Import button when user lacks skus:import and is not admin', async () => {
    setUser(['skus:create'], ['viewer']);

    render(<SKUListPage />);

    await waitFor(() => {
      expect(screen.queryByText('Import Catalog SKUs')).not.toBeInTheDocument();
    });
  });

  it('hides Import button for unauthenticated user', async () => {
    setNoUser();

    render(<SKUListPage />);

    await waitFor(() => {
      expect(screen.queryByText('Import Catalog SKUs')).not.toBeInTheDocument();
    });
  });
});

// ---------------------------------------------------------------------------
// U4-A: Product create/update gate tests (fixed: inventory:write -> skus:*)
// ---------------------------------------------------------------------------

describe('SKUListPage Add Product gate (U4-A)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(catalogProductService.getAll).mockResolvedValue({
      data: { data: { items: [] } },
    } as never);
  });

  it('shows Add Product when user has skus:create', async () => {
    setUser(['skus:create'], ['viewer']);

    render(<SKUListPage />);

    await waitFor(() => {
      expect(screen.getByText('Add Product')).toBeInTheDocument();
    });
  });

  it('hides Add Product when user has inventory:write but NOT skus:create (proves fix)', async () => {
    // U4-A: Previously this user could see Add Product because the gate
    // checked 'inventory:write'. Now it checks 'skus:create' correctly.
    setUser(['inventory:write'], ['viewer']);

    render(<SKUListPage />);

    await waitFor(() => {
      expect(screen.queryByText('Add Product')).not.toBeInTheDocument();
    });
  });

  it('shows Add Product for admin (bypass)', async () => {
    setUser([], ['admin']);

    render(<SKUListPage />);

    await waitFor(() => {
      expect(screen.getByText('Add Product')).toBeInTheDocument();
    });
  });

  it('hides Add Product for unauthenticated user', async () => {
    setNoUser();

    render(<SKUListPage />);

    await waitFor(() => {
      expect(screen.queryByText('Add Product')).not.toBeInTheDocument();
    });
  });
});

describe('SKUListPage product-centered catalog and action permissions', () => {
  const product = {
    id: 'product-1',
    name: 'Premium Rice',
    description: 'Customer-facing product',
    category: 'Staples',
    is_active: true,
    created_at: '2026-08-30T00:00:00Z',
    updated_at: '2026-08-30T00:00:00Z',
    sellable_units: [
      {
        id: 'unit-each',
        catalog_product_id: 'product-1',
        sku_code: 'RICE-EACH-1',
        unit: 'bag',
        package_quantity: 1,
        is_active: true,
        created_at: '2026-08-30T00:00:00Z',
        updated_at: '2026-08-30T00:00:00Z',
      },
      {
        id: 'unit-case',
        catalog_product_id: 'product-1',
        sku_code: 'RICE-CASE-12',
        unit: 'case',
        package_quantity: 12,
        is_active: true,
        created_at: '2026-08-30T00:00:00Z',
        updated_at: '2026-08-30T00:00:00Z',
      },
    ],
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(catalogProductService.getAll).mockResolvedValue({
      data: { data: { items: [product] } },
    } as never);
  });

  it('loads CatalogProduct data and renders multiple packaging options under one product', async () => {
    setUser(['skus:read'], ['viewer']);
    render(<SKUListPage />);

    expect(await screen.findByRole('heading', { name: 'Premium Rice' })).toBeInTheDocument();
    expect(screen.getByText('RICE-EACH-1')).toBeInTheDocument();
    expect(screen.getByText('RICE-CASE-12')).toBeInTheDocument();
    expect(catalogProductService.getAll).toHaveBeenCalledWith(1, 100);
  });

  it('renders a safe empty-packaging state instead of crashing on legacy data', async () => {
    vi.mocked(catalogProductService.getAll).mockResolvedValue({
      data: { data: { items: [{ ...product, sellable_units: undefined }] } },
    } as never);
    setUser(['skus:read'], ['viewer']);
    render(<SKUListPage />);

    expect(await screen.findByText('No packaging options are available for this product.')).toBeInTheDocument();
  });

  it('allows add packaging with skus:create but hides update actions', async () => {
    setUser(['skus:read', 'skus:create'], ['viewer']);
    render(<SKUListPage />);

    await screen.findByRole('heading', { name: 'Premium Rice' });
    expect(screen.getByRole('button', { name: 'Add packaging' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Edit product' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Edit packaging' })).not.toBeInTheDocument();
  });

  it('allows product and packaging edits with skus:update but hides create actions', async () => {
    setUser(['skus:read', 'skus:update'], ['viewer']);
    render(<SKUListPage />);

    await screen.findByRole('heading', { name: 'Premium Rice' });
    expect(screen.getByRole('button', { name: 'Edit product' })).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Edit packaging' })).toHaveLength(2);
    expect(screen.queryByRole('button', { name: 'Add packaging' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Add Product' })).not.toBeInTheDocument();
  });
});
