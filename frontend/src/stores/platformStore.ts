/**
 * Platform Admin Cockpit Zustand store.
 *
 * Holds platform data fetched from P10 API endpoints.
 * No caching layer — refetch on mount is acceptable for P11.
 * All data is read-only from the perspective of the frontend.
 */
import { create } from 'zustand';
import type {
  PlatformTenantSummary,
  PlatformTenantHealth,
  PlatformSystemHealth,
  PlatformAuditEvent,
} from '@/types/platform';

interface PlatformState {
  // Data
  tenants: PlatformTenantSummary[];
  tenantsTotal: number;
  systemHealth: PlatformSystemHealth | null;
  auditEvents: PlatformAuditEvent[];
  auditTotal: number;
  selectedTenantHealth: PlatformTenantHealth | null;

  // Loading states
  tenantsLoading: boolean;
  systemHealthLoading: boolean;
  auditLoading: boolean;
  tenantHealthLoading: boolean;

  // Error states
  tenantsError: string | null;
  systemHealthError: string | null;
  auditError: string | null;
  tenantHealthError: string | null;
}

interface PlatformActions {
  // Setters (called by pages/hooks after API responses)
  setTenants: (tenants: PlatformTenantSummary[], total: number) => void;
  setTenantsLoading: (loading: boolean) => void;
  setTenantsError: (error: string | null) => void;

  setSystemHealth: (health: PlatformSystemHealth) => void;
  setSystemHealthLoading: (loading: boolean) => void;
  setSystemHealthError: (error: string | null) => void;

  setAuditEvents: (events: PlatformAuditEvent[], total: number) => void;
  setAuditLoading: (loading: boolean) => void;
  setAuditError: (error: string | null) => void;

  setTenantHealth: (health: PlatformTenantHealth | null) => void;
  setTenantHealthLoading: (loading: boolean) => void;
  setTenantHealthError: (error: string | null) => void;

  // Reset
  reset: () => void;
}

const initialState: PlatformState = {
  tenants: [],
  tenantsTotal: 0,
  systemHealth: null,
  auditEvents: [],
  auditTotal: 0,
  selectedTenantHealth: null,
  tenantsLoading: false,
  systemHealthLoading: false,
  auditLoading: false,
  tenantHealthLoading: false,
  tenantsError: null,
  systemHealthError: null,
  auditError: null,
  tenantHealthError: null,
};

export type PlatformStore = PlatformState & PlatformActions;

export const usePlatformStore = create<PlatformStore>()((set) => ({
  ...initialState,

  setTenants: (tenants, total) => set({ tenants, tenantsTotal: total, tenantsLoading: false, tenantsError: null }),
  setTenantsLoading: (loading) => set({ tenantsLoading: loading }),
  setTenantsError: (error) => set({ tenantsError: error, tenantsLoading: false }),

  setSystemHealth: (health) => set({ systemHealth: health, systemHealthLoading: false, systemHealthError: null }),
  setSystemHealthLoading: (loading) => set({ systemHealthLoading: loading }),
  setSystemHealthError: (error) => set({ systemHealthError: error, systemHealthLoading: false }),

  setAuditEvents: (events, total) => set({ auditEvents: events, auditTotal: total, auditLoading: false, auditError: null }),
  setAuditLoading: (loading) => set({ auditLoading: loading }),
  setAuditError: (error) => set({ auditError: error, auditLoading: false }),

  setTenantHealth: (health) => set({ selectedTenantHealth: health, tenantHealthLoading: false, tenantHealthError: null }),
  setTenantHealthLoading: (loading) => set({ tenantHealthLoading: loading }),
  setTenantHealthError: (error) => set({ tenantHealthError: error, tenantHealthLoading: false }),

  reset: () => set({ ...initialState }),
}));
