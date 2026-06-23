/**
 * Platform Admin Cockpit API client service.
 *
 * Uses the existing Axios singleton (api.ts) with Bearer token injection.
 * All calls go to P10/P12/P13 contract-backed endpoints.
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
import type {
  ErrorRateSummary,
  SlowRouteSummary,
  ResourceHealthSummary,
  NoisyNeighborSummary,
} from '@/types/platformOps';
import type { IncidentTriageSnapshot } from '@/types/platformIncident';
import type {
  PlatformTenantRegistry,
  PlatformTenantRegistryList,
} from '@/types/platformRegistry';

const P10_BASE = '/platform/p10';
const P13_BASE = '/platform/p13';
const P15_BASE = '/platform/p15';
const P17_BASE = '/platform/p17';

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

  // -- P13 Operations Cockpit (read-only) --

  /** P13: Get ops system health */
  getOpsHealth: () =>
    api.get<PlatformSystemHealth>(`${P13_BASE}/ops/health`),

  /** P13: Get error rate analysis */
  getOpsErrors: (window = 15) =>
    api.get<ErrorRateSummary>(`${P13_BASE}/ops/errors`, {
      params: { window },
    }),

  /** P13: Get slow route analysis */
  getOpsSlowRoutes: (window = 15, threshold = 1000) =>
    api.get<SlowRouteSummary>(`${P13_BASE}/ops/slow-routes`, {
      params: { window, threshold },
    }),

  /** P13: Get resource health summary */
  getOpsResources: () =>
    api.get<ResourceHealthSummary>(`${P13_BASE}/ops/resources`),

  /** P13: Get noisy-neighbor analysis */
  getOpsNoisyNeighbors: (window = 15) =>
    api.get<NoisyNeighborSummary>(`${P13_BASE}/ops/noisy-neighbors`, {
      params: { window },
    }),

  // -- P15 Incident Triage (read-only snapshot) --

  /** P15: Get incident triage snapshot (read-only) */
  getIncidentTriageSnapshot: () =>
    api.get<IncidentTriageSnapshot>(`${P15_BASE}/incidents/triage/snapshot`),

  // -- P17 Platform Registry (read-only tenant registry) --

  /** P17: List tenant registry (read-only) */
  listTenantRegistry: (limit = 50, offset = 0) =>
    api.get<PlatformTenantRegistryList>(`${P17_BASE}/registry`, {
      params: { limit, offset },
    }),

  /** P17: Get a single tenant registry (read-only) */
  getTenantRegistry: (tenantId: string) =>
    api.get<PlatformTenantRegistry>(`${P17_BASE}/registry/${tenantId}`),
};
