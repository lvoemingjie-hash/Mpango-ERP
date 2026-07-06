/**
 * P25-B dimension: no forbidden control (matrix dim 12; AC 17; C19).
 *
 * The platform cockpit is non-executing / non-sending / non-mutating. No route
 * may surface a control that performs a forbidden action. Per C19 the forbidden
 * controls are the bare execution / dispatch verbs, notification DELIVERY
 * verbs, and P17 flag-MUTATION verbs:
 *
 *   execute | dispatch | deliver | send | push  (execution / delivery)
 *   clear flag | set flag                        (P17 flag mutation as a control)
 *   delete tenant | purge | truncate             (destructive product mutation)
 *
 * Permitted and NOT forbidden here: Acknowledge / Self-assign / Complete /
 * Dismiss / Materialize / Close / Record-* / Dry-run / Approve / Reject /
 * Retry / Submit -- these are pure RECORD or state-machine transitions
 * (a task is a view, a step is a pointer, a follow-up is a record, an approval
 * is not execution). Row-level forbidden-control coverage additionally inherits
 * from the per-page P22 / P23-D / P24-C suites.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { waitFor } from '@testing-library/react';

vi.mock('@/services/api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

import { api } from '@/services/api';
import {
  SWEEP_ROUTES,
  EMPTY_BODY,
  IDENTITY_ONLY_SUPER_ADMIN,
  setAuth,
  clearAuth,
  resetPlatformStore,
  renderPlatformAt,
} from './__helpers__/readiness';

// "Dry-run" is permitted; bare "run" is intentionally NOT forbidden to avoid a
// Dry-run false positive. "execution" (the noun) does not match \bexecute\b.
const FORBIDDEN_CONTROL =
  /\b(execute|dispatch|deliver|send|push)\b|\bclear\s+flag\b|\bset\s+flag\b|\bdelete\s+tenant\b|\bpurge\b|\btruncate\b/i;

function concretePath(path: string): string {
  return path.replace(':tenantId', 't-demo');
}

function forbiddenButtons(container: HTMLElement): string[] {
  const els = Array.from(container.querySelectorAll('button, [role="button"]'));
  const hits: string[] = [];
  for (const el of els) {
    const name = (el.textContent ?? el.getAttribute('aria-label') ?? '').trim();
    if (name && FORBIDDEN_CONTROL.test(name)) hits.push(name);
  }
  return hits;
}

beforeEach(() => {
  clearAuth();
  setAuth(IDENTITY_ONLY_SUPER_ADMIN, 'token');
  resetPlatformStore();
  vi.clearAllMocks();
  vi.mocked(api.get).mockResolvedValue({ data: EMPTY_BODY });
  vi.mocked(api.post).mockResolvedValue({ data: {} });
});

describe('P25-B forbidden-control sweep (dim 12; AC 17; C19)', () => {
  it.each(SWEEP_ROUTES)('P25-F: $name surfaces no forbidden control ($path)', async (r) => {
    const { container } = renderPlatformAt(concretePath(r.path));
    await waitFor(() => expect(container.textContent).toBeTruthy());
    await waitFor(
      () => {
        expect(forbiddenButtons(container)).toEqual([]);
      },
      { timeout: 2000 },
    );
  });

  it('P25-F-INV: the forbidden-control regex is calibrated (dry-run permitted, bare execute forbidden)', () => {
    expect(FORBIDDEN_CONTROL.test('Dry-run')).toBe(false);
    expect(FORBIDDEN_CONTROL.test('Dry run')).toBe(false);
    expect(FORBIDDEN_CONTROL.test('Record request')).toBe(false);
    expect(FORBIDDEN_CONTROL.test('Record approval')).toBe(false);
    expect(FORBIDDEN_CONTROL.test('Acknowledge')).toBe(false);
    expect(FORBIDDEN_CONTROL.test('Self-assign')).toBe(false);
    expect(FORBIDDEN_CONTROL.test('Complete')).toBe(false);
    expect(FORBIDDEN_CONTROL.test('Materialize')).toBe(false);
    expect(FORBIDDEN_CONTROL.test('Approve')).toBe(false);
    expect(FORBIDDEN_CONTROL.test('Retry')).toBe(false);
    expect(FORBIDDEN_CONTROL.test('execution')).toBe(false);
    // Adversarial: these MUST be forbidden.
    expect(FORBIDDEN_CONTROL.test('Execute')).toBe(true);
    expect(FORBIDDEN_CONTROL.test('Execute backup')).toBe(true);
    expect(FORBIDDEN_CONTROL.test('Deliver notification')).toBe(true);
    expect(FORBIDDEN_CONTROL.test('Send notification')).toBe(true);
    expect(FORBIDDEN_CONTROL.test('Clear flag')).toBe(true);
    expect(FORBIDDEN_CONTROL.test('Dispatch worker')).toBe(true);
    expect(FORBIDDEN_CONTROL.test('Delete tenant')).toBe(true);
  });
});
