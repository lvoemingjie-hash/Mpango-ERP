/**
 * P18-C: Platform controlled-actions page component tests.
 *
 * Verifies the read-only / request-only skeleton contract:
 *   - catalog renders (closed action set)
 *   - form requires a reason and an idempotency key (buttons disabled until present)
 *   - submit shows a request-not-executed status
 *   - accepted / denied / duplicate / conflict / degraded statuses render correctly
 *   - no direct-execution button wording; request-vs-execution copy is present
 *   - an unknown / degraded source displays a safe warning
 */
import { beforeEach, describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

// Mock api to prevent real network calls.
vi.mock('@/services/api', () => ({
  api: {
    get: vi.fn().mockResolvedValue({ data: {} }),
    post: vi.fn().mockResolvedValue({ data: {} }),
  },
}));

import { api } from '@/services/api';
import { PlatformControlledActionsPage } from '@/pages/platform/PlatformControlledActionsPage';

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/platform/controlled-actions']}>
      <Routes>
        <Route
          path="/platform/controlled-actions"
          element={<PlatformControlledActionsPage />}
        />
      </Routes>
    </MemoryRouter>,
  );
}

const CATALOG = {
  items: [
    {
      action_type: 'tenant.pause',
      classification: 'write',
      allowed_actors: ['super_admin'],
      confirmation_required: true,
      degraded_allowed: false,
      description: 'Request to pause a tenant. Recorded only; not executed.',
    },
    {
      action_type: 'provisioning.recheck',
      classification: 'read',
      allowed_actors: ['super_admin', 'engineering_operator'],
      confirmation_required: false,
      degraded_allowed: true,
      description: 'Request to recompute provisioning status. Degraded allowed; not executed.',
    },
  ],
  total: 2,
  contract: 'P18-A',
  executed: false,
};

function response(over: Record<string, unknown> = {}) {
  return {
    data: {
      action_id: 'aid-1',
      action_type: 'tenant.pause',
      result: 'accepted',
      executed: false,
      dry_run: false,
      message: 'Accepted: the request was recorded and audited, NOT executed.',
      reason: 'routine review',
      idempotency_key: 'key-1',
      requested_state: null,
      previous_state: null,
      source_status: 'available',
      degraded_reason: null,
      metadata_redacted: null,
      correlation_id: null,
      created_at: '2026-06-23T00:00:00Z',
      ...over,
    },
  };
}

function fillForm() {
  fireEvent.change(screen.getByTestId('ca-reason-input'), { target: { value: 'routine review' } });
  fireEvent.change(screen.getByTestId('ca-idempotency-input'), { target: { value: 'key-1' } });
}

describe('PlatformControlledActionsPage', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockResolvedValue({ data: CATALOG });
    vi.mocked(api.post).mockResolvedValue({ data: {} });
  });

  it('renders title, not-executed subtitle, and the catalog', async () => {
    renderPage();
    expect(screen.getByTestId('ca-title')).toHaveTextContent('Controlled Action Requests');
    expect(screen.getByTestId('ca-subtitle').textContent?.toLowerCase()).toContain('not executed');
    const items = await screen.findAllByTestId('ca-catalog-item');
    expect(items.length).toBe(2);
    // The action types render (in the catalog and again as select options).
    expect(screen.getAllByText('tenant.pause').length).toBeGreaterThan(0);
    expect(screen.getAllByText('provisioning.recheck').length).toBeGreaterThan(0);
  });

  it('form requires a reason and an idempotency key (buttons disabled until present)', async () => {
    renderPage();
    await screen.findAllByTestId('ca-catalog-item');
    // Disabled while reason / idempotency key are empty.
    expect(screen.getByTestId('ca-submit-btn')).toBeDisabled();
    expect(screen.getByTestId('ca-validate-btn')).toBeDisabled();
    // Enabled once both are provided.
    fillForm();
    expect(screen.getByTestId('ca-submit-btn')).not.toBeDisabled();
    expect(screen.getByTestId('ca-validate-btn')).not.toBeDisabled();
  });

  it('submit shows a request-not-executed status (accepted)', async () => {
    renderPage();
    await screen.findAllByTestId('ca-catalog-item');
    fillForm();
    vi.mocked(api.post).mockResolvedValueOnce(response({ result: 'accepted' }));
    fireEvent.click(screen.getByTestId('ca-submit-btn'));
    expect(await screen.findByTestId('ca-not-executed')).toBeInTheDocument();
    expect(screen.getByTestId('ca-result-badge')).toHaveTextContent('accepted');
    // The recorded request is not executed.
    expect(screen.queryByTestId('ca-source-warning')).not.toBeInTheDocument();
  });

  it('denied / conflict / duplicate statuses render correctly', async () => {
    for (const result of ['denied', 'conflict', 'duplicate'] as const) {
      const { unmount } = renderPage();
      await screen.findAllByTestId('ca-catalog-item');
      fillForm();
      vi.mocked(api.post).mockResolvedValueOnce(response({ result }));
      fireEvent.click(screen.getByTestId('ca-submit-btn'));
      expect(await screen.findByTestId('ca-result-badge')).toHaveTextContent(result);
      // Every outcome still states not-executed.
      expect(screen.getByTestId('ca-not-executed')).toBeInTheDocument();
      unmount();
    }
  });

  it('no direct-execution button wording; request-vs-execution copy present', async () => {
    renderPage();
    await screen.findAllByTestId('ca-catalog-item');
    // No button implies immediate execution.
    const verbs = /execute|pause|resume|trigger|suspend|destroy/i;
    for (const btn of screen.queryAllByRole('button')) {
      expect(verbs.test(btn.textContent ?? '')).toBe(false);
    }
    // The only action buttons are the request skeleton buttons.
    const labels = screen.queryAllByRole('button').map((b) => b.textContent ?? '');
    expect(labels).toEqual(expect.arrayContaining(['Validate request', 'Submit request']));
    // Request-vs-execution copy is present.
    expect(screen.getByTestId('ca-subtitle').textContent?.toLowerCase()).toContain('not executed');
  });

  it('unknown / degraded source displays a safe warning', async () => {
    renderPage();
    await screen.findAllByTestId('ca-catalog-item');
    fillForm();
    vi.mocked(api.post).mockResolvedValueOnce(
      response({ result: 'degraded', source_status: 'unknown', dry_run: false }),
    );
    fireEvent.click(screen.getByTestId('ca-submit-btn'));
    const warning = await screen.findByTestId('ca-source-warning');
    expect(warning.textContent?.toLowerCase()).toContain('unknown');
    // Still not executed.
    expect(screen.getByTestId('ca-not-executed')).toBeInTheDocument();
    expect(screen.getByTestId('ca-result-badge')).toHaveTextContent('degraded');
  });
});
