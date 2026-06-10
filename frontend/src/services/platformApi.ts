/**
 * Platform Admin Cockpit API client service.
 *
 * Uses the existing Axios singleton (api.ts) with Bearer token injection.
 * All calls go to P10 contract-backed endpoints.
 *
 * Auth transport (P11-B0-R1 resolved): The backend P10 guard accepts
 * identity-only (global) super_admin Bearer tokens only. The frontend
 * uses the standard Axios Bearer token from an identity/global super_admin
 * session (before tenant selection).
 *
 * No X-Platform-Operator secret is ever sent to or stored in the browser.
 */
import { api } from './api';
import type {
  PlatformTenantSummaryList,
  PlatformTenantSummary,
  PlatformTenantHealth,
  PlatformSystemHealth,
  PlatformAuditEventList,
  PlatformAuditEvent,
} from '@/types/platform';

const P10_BASE = '/platform/p10';

export const platformService = {
  /** List tenants with optional pagination */
  listTenants: (limit = 50, offset = 0) =>
    api.get<PlatformTenantSummaryList>(`${P10_BASE}/tenants`, {
      params: { limit, offset },
    }),

  /** Get a single tenant summary */
  getTenant: (tenantId: string) =>
    api.get<PlatformTenantSummary>(`${P10_BASE}/tenants/${tenantId}`),

  /** Get tenant health detail */
  getTenantHealth: (tenantId: string) =>
    api.get<PlatformTenantHealth>(`${P10_BASE}/tenants/${tenantId}/health`),

  /** Get system health */
  getSystemHealth: () =>
    api.get<PlatformSystemHealth>(`${P10_BASE}/system/health`),

  /** List audit events with optional pagination */
  listAuditEvents: (limit = 50, offset = 0) =>
    api.get<PlatformAuditEventList>(`${P10_BASE}/audit/events`, {
      params: { limit, offset },
    }),

  /** Get a single audit event */
  getAuditEvent: (eventId: string) =>
    api.get<PlatformAuditEvent>(`${P10_BASE}/audit/events/${eventId}`),
};
