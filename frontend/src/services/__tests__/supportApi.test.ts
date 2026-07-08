/**
 * P12-C0: Support Console API service tests.
 *
 * Verifies that supportService calls correct P12 endpoints with correct params.
 * Uses vi.fn() mocking on the api module (same pattern as platformApi.test.ts).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock the api module
vi.mock('@/services/api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

import { supportService } from '@/services/supportApi';
import { api } from '@/services/api';

const mockPost = vi.mocked(api.post);
const mockGet = vi.mocked(api.get);

beforeEach(() => {
  vi.clearAllMocks();
});

describe('supportService', () => {
  it('SA-001: createSession calls POST /platform/p12/sessions with body', async () => {
    mockPost.mockResolvedValueOnce({
      data: { session_id: 'test-id', status: 'active', reason: 'Test reason', category: 'general', started_at: '2026-06-11T10:00:00Z', bundle_count: 0 },
    });
    await supportService.createSession({
      reason: 'Tenant login failure triage',
      category: 'login_issue',
      tenant_id: 'a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d',
    });
    expect(mockPost).toHaveBeenCalledWith('/platform/p12/sessions', {
      reason: 'Tenant login failure triage',
      category: 'login_issue',
      tenant_id: 'a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d',
    });
  });

  it('SA-002: getDiagnostics calls GET /platform/p12/sessions/:id/diagnostics', async () => {
    mockGet.mockResolvedValueOnce({ data: [] });
    await supportService.getDiagnostics('session-123');
    expect(mockGet).toHaveBeenCalledWith('/platform/p12/sessions/session-123/diagnostics');
  });

  it('SA-003: createBundle calls POST /platform/p12/sessions/:id/bundles', async () => {
    mockPost.mockResolvedValueOnce({
      data: { bundle_id: 'bundle-456', diagnostics: [], redaction_applied: true, bundle_type: 'full' },
    });
    await supportService.createBundle('session-123', { bundle_type: 'technical' });
    expect(mockPost).toHaveBeenCalledWith('/platform/p12/sessions/session-123/bundles', {
      bundle_type: 'technical',
    });
  });

  it('SA-004: closeSession calls POST /platform/p12/sessions/:id/close', async () => {
    mockPost.mockResolvedValueOnce({
      data: { session_id: 'session-123', status: 'closed' },
    });
    await supportService.closeSession('session-123');
    expect(mockPost).toHaveBeenCalledWith('/platform/p12/sessions/session-123/close');
  });

  it('SA-005: createBundle defaults to bundle_type full', async () => {
    mockPost.mockResolvedValueOnce({
      data: { bundle_id: 'bundle-789', diagnostics: [], redaction_applied: true, bundle_type: 'full' },
    });
    await supportService.createBundle('session-123');
    expect(mockPost).toHaveBeenCalledWith('/platform/p12/sessions/session-123/bundles', {
      bundle_type: 'full',
    });
  });

  it('SA-006: createSession sends reason/category/tenant_id in body', async () => {
    mockPost.mockResolvedValueOnce({
      data: { session_id: 'test-id', status: 'active' },
    });
    await supportService.createSession({
      reason: 'Performance degradation reported by tenant',
      category: 'performance',
    });
    const callArgs = mockPost.mock.calls[0];
    expect(callArgs[1]).toEqual({
      reason: 'Performance degradation reported by tenant',
      category: 'performance',
    });
  });
});
