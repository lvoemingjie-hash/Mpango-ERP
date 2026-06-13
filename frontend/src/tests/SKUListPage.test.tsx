/**
 * U3-D Permission gate tests for SKUListPage Import entry point.
 *
 * Verifies:
 *   1. Import button visible when user has skus:import permission
 *   2. Import button visible when user has admin role (no skus:import perm)
 *   3. Import button hidden when user has neither skus:import nor admin
 *   4. Import button hidden for unauthenticated (no user)
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
      login: vi.fn(),
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
      login: vi.fn(),
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
    setUser(['inventory:write', 'skus:import'], ['viewer']);

    render(<SKUListPage />);

    await waitFor(() => {
      expect(screen.getByText('Import Products')).toBeInTheDocument();
    });
  });

  it('shows Import button when user has admin role without skus:import', async () => {
    setUser(['inventory:write'], ['admin']);

    render(<SKUListPage />);

    await waitFor(() => {
      expect(screen.getByText('Import Products')).toBeInTheDocument();
    });
  });

  it('hides Import button when user lacks skus:import and is not admin', async () => {
    setUser(['inventory:write'], ['viewer']);

    render(<SKUListPage />);

    await waitFor(() => {
      expect(screen.queryByText('Import Products')).not.toBeInTheDocument();
    });
  });

  it('hides Import button for unauthenticated user', async () => {
    setNoUser();

    render(<SKUListPage />);

    await waitFor(() => {
      expect(screen.queryByText('Import Products')).not.toBeInTheDocument();
    });
  });
});
