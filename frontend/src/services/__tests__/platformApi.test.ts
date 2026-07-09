/**
 * P11-B1: Platform API service tests.
 *
 * Verifies that platformService calls correct endpoints with correct params.
 * Uses MSW-style mocking via vi.fn() on the api module.
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

describe('platformService', () => {
  it('TS-001: listTenants calls GET /platform/p10/tenants with limit/offset', async () => {
    mockGet.mockResolvedValueOnce({
      data: { items: [], total: 0, limit: 50, offset: 0 },
    });
    await platformService.listTenants(25, 10);
    expect(mockGet).toHaveBeenCalledWith('/platform/p10/tenants', {
      params: { limit: 25, offset: 10 },
    });
  });

  it('TS-002: listTenants uses default limit=50 offset=0', async () => {
    mockGet.mockResolvedValueOnce({
      data: { items: [], total: 0, limit: 50, offset: 0 },
    });
    await platformService.listTenants();
    expect(mockGet).toHaveBeenCalledWith('/platform/p10/tenants', {
      params: { limit: 50, offset: 0 },
    });
  });

  it('TS-003: getTenant calls GET /platform/p10/tenants/:id', async () => {
    mockGet.mockResolvedValueOnce({ data: {} });
    await platformService.getTenant('abc-123');
    expect(mockGet).toHaveBeenCalledWith('/platform/p10/tenants/abc-123');
  });

  it('TS-004: getTenantHealth calls GET /platform/p10/tenants/:id/health', async () => {
    mockGet.mockResolvedValueOnce({ data: {} });
    await platformService.getTenantHealth('abc-123');
    expect(mockGet).toHaveBeenCalledWith('/platform/p10/tenants/abc-123/health');
  });

  it('TS-005: getSystemHealth calls GET /platform/p10/system/health', async () => {
    mockGet.mockResolvedValueOnce({ data: {} });
    await platformService.getSystemHealth();
    expect(mockGet).toHaveBeenCalledWith('/platform/p10/system/health');
  });

  it('TS-006: listAuditEvents calls GET /platform/p10/audit/events with limit/offset', async () => {
    mockGet.mockResolvedValueOnce({
      data: { items: [], total: 0, limit: 50, offset: 0 },
    });
    await platformService.listAuditEvents(20, 5);
    expect(mockGet).toHaveBeenCalledWith('/platform/p10/audit/events', {
      params: { limit: 20, offset: 5 },
    });
  });

  it('TS-007: getAuditEvent calls GET /platform/p10/audit/events/:id', async () => {
    mockGet.mockResolvedValueOnce({ data: {} });
    await platformService.getAuditEvent('evt-456');
    expect(mockGet).toHaveBeenCalledWith('/platform/p10/audit/events/evt-456');
  });
});
