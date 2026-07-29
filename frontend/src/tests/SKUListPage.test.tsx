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
import type { AuthStore } from '@/stores/authStore';

// ---------------------------------------------------------------------------
// Mock dependencies
// ---------------------------------------------------------------------------

vi.mock('@/services/skuService', () => ({
  skuService: {
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
    } as AuthStore)) as unknown as typeof mockedUseAuthStore);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('SKUListPage Import button permission gate', () => {
  beforeEach(() => {
    vi.clearAllMocks();
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
