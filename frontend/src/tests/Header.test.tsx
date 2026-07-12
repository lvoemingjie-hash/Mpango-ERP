import { beforeEach, describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { Header } from '@/components/layout/Header';
import { useAuthStore } from '@/stores/authStore';
import type { CurrentUserData } from '@/types/auth';

function renderHeader() {
  return render(
    <MemoryRouter>
      <Header />
    </MemoryRouter>,
  );
}

describe('Header', () => {
  beforeEach(() => {
    useAuthStore.setState({
      accessToken: null,
      refreshToken: null,
      user: null,
      tenantCode: null,
    });
  });

  it('falls back when persisted user data has no roles array', () => {
    useAuthStore.setState({
      accessToken: 'redacted-test-access-token',
      refreshToken: 'redacted-test-refresh-token',
      tenantCode: 'TST',
      user: ({
        id: 'test-user',
        email: 'person@example.invalid',
        full_name: 'Example User',
        tenant_id: 'tenant-1',
        tenant_schema: 'tenant_test',
        permissions: [],
      } as unknown) as CurrentUserData,
    });

    renderHeader();

    expect(screen.getByText('Example User')).toBeInTheDocument();
    expect(screen.getByText('User')).toBeInTheDocument();
  });
});
