/**
 * P25-B dimension: copy / leak safety (matrix dim 9; AC 11; C20).
 *
 * Scans every route's rendered text (empty-state AND error-state) against the
 * P23 never-leaked list (secrets, DSNs, host:port, bearer tokens, cookies, auth
 * headers, raw payloads, shell, SQL, tenant business payloads), and asserts no
 * sensitive field NAME is shown as visible on-screen copy.
 *
 * Backend redaction is server-side; this defends the client surface: even if a
 * malformed / drifted response reaches the browser, no platform secret renders.
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
  scanForLeaks,
} from './__helpers__/readiness';

const SAFE_ERROR = new Error('Request failed with status code 500');
const SENSITIVE_LABEL = /(\bpassword\b|\bsecret\b|api[_-]?key|bearer|\bcookie\b|\bdsn\b|private[_-]?key|access[_-]?token|x-platform-operator)/i;

function concretePath(path: string): string {
  return path.replace(':tenantId', 't-demo');
}

beforeEach(() => {
  clearAuth();
  setAuth(IDENTITY_ONLY_SUPER_ADMIN, 'token');
  resetPlatformStore();
  vi.clearAllMocks();
});

describe('P25-B copy safety -- empty render (dim 9; AC 11)', () => {
  it.each(SWEEP_ROUTES)('P25-C1: $name empty render leaks nothing ($path)', async (r) => {
    vi.mocked(api.get).mockResolvedValue({ data: EMPTY_BODY });
    vi.mocked(api.post).mockResolvedValue({ data: {} });
    const { container } = renderPlatformAt(concretePath(r.path));
    await waitFor(() => expect(container.textContent).toBeTruthy());
    // Allow loading to settle, then scan.
    await waitFor(
      () => {
        expect(scanForLeaks(container.textContent ?? '')).toEqual([]);
      },
      { timeout: 2000 },
    );
  });
});

describe('P25-B copy safety -- error render (dim 9; AC 7/11; C20)', () => {
  it.each(SWEEP_ROUTES)('P25-C2: $name error render leaks nothing ($path)', async (r) => {
    vi.mocked(api.get).mockRejectedValue(SAFE_ERROR);
    vi.mocked(api.post).mockRejectedValue(SAFE_ERROR);
    const { container } = renderPlatformAt(concretePath(r.path));
    await waitFor(
      () => {
        const t = container.textContent ?? '';
        expect(scanForLeaks(t)).toEqual([]);
        // No raw stack frame in the DOM.
        expect(t).not.toMatch(/at \w+\.\w+ \(.+\.tsx?:\d+\)/);
      },
      { timeout: 2000 },
    );
  });
});

describe('P25-B copy safety -- no sensitive field label is visible (AC 11)', () => {
  it.each(SWEEP_ROUTES)('P25-C3: $name shows no secret/token/dsn label ($path)', async (r) => {
    vi.mocked(api.get).mockResolvedValue({ data: EMPTY_BODY });
    vi.mocked(api.post).mockResolvedValue({ data: {} });
    const { container } = renderPlatformAt(concretePath(r.path));
    await waitFor(() => expect(container.textContent).toBeTruthy());
    await waitFor(
      () => {
        expect(container.textContent ?? '').not.toMatch(SENSITIVE_LABEL);
      },
      { timeout: 2000 },
    );
  });
});
