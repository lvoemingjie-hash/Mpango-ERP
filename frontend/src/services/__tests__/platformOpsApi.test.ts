/**
 * P13-D: Platform ops API service tests.
 *
 * Verifies P13 endpoint paths and parameters.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock the api module
vi.mock('@/services/api', () => ({
  api: {
    get: vi.fn(),
  },
}));

import { platformService } from '@/services/platformApi';
import { api } from '@/services/api';

const mockGet = vi.mocked(api.get);

beforeEach(() => {
  vi.clearAllMocks();
});

describe('platformService P13 ops endpoints', () => {
  it('P13-001: getOpsHealth calls GET /platform/p13/ops/health', async () => {
    mockGet.mockResolvedValueOnce({ data: {} });
    await platformService.getOpsHealth();
    expect(mockGet).toHaveBeenCalledWith('/platform/p13/ops/health');
  });

  it('P13-002: getOpsErrors calls GET /platform/p13/ops/errors with default window=15', async () => {
    mockGet.mockResolvedValueOnce({ data: {} });
    await platformService.getOpsErrors();
    expect(mockGet).toHaveBeenCalledWith('/platform/p13/ops/errors', {
      params: { window: 15 },
    });
  });

  it('P13-003: getOpsErrors passes custom window', async () => {
    mockGet.mockResolvedValueOnce({ data: {} });
    await platformService.getOpsErrors(60);
    expect(mockGet).toHaveBeenCalledWith('/platform/p13/ops/errors', {
      params: { window: 60 },
    });
  });

  it('P13-004: getOpsSlowRoutes calls GET /platform/p13/ops/slow-routes with defaults', async () => {
    mockGet.mockResolvedValueOnce({ data: {} });
    await platformService.getOpsSlowRoutes();
    expect(mockGet).toHaveBeenCalledWith('/platform/p13/ops/slow-routes', {
      params: { window: 15, threshold: 1000 },
    });
  });

  it('P13-005: getOpsSlowRoutes passes custom window and threshold', async () => {
    mockGet.mockResolvedValueOnce({ data: {} });
    await platformService.getOpsSlowRoutes(30, 2000);
    expect(mockGet).toHaveBeenCalledWith('/platform/p13/ops/slow-routes', {
      params: { window: 30, threshold: 2000 },
    });
  });

  it('P13-006: getOpsResources calls GET /platform/p13/ops/resources', async () => {
    mockGet.mockResolvedValueOnce({ data: {} });
    await platformService.getOpsResources();
    expect(mockGet).toHaveBeenCalledWith('/platform/p13/ops/resources');
  });

  it('P13-007: getOpsNoisyNeighbors calls GET /platform/p13/ops/noisy-neighbors with default window', async () => {
    mockGet.mockResolvedValueOnce({ data: {} });
    await platformService.getOpsNoisyNeighbors();
    expect(mockGet).toHaveBeenCalledWith('/platform/p13/ops/noisy-neighbors', {
      params: { window: 15 },
    });
  });

  it('P13-008: getOpsNoisyNeighbors passes custom window', async () => {
    mockGet.mockResolvedValueOnce({ data: {} });
    await platformService.getOpsNoisyNeighbors(60);
    expect(mockGet).toHaveBeenCalledWith('/platform/p13/ops/noisy-neighbors', {
      params: { window: 60 },
    });
  });
});
