# P11 Frontend Boundary Map

**Phase:** P11-A
**Status:** Boundary document (docs/ledger only -- no UI code yet)
**Date:** 2026-06-08
**Author:** Platform product boundary analysis

---

## Purpose

This document defines the frontend boundary for the first Platform Admin Cockpit UI (P11-B/C/D). It maps:

- Where P11 frontend code may be placed
- What frontend conventions and patterns P11 must follow
- What areas are strictly forbidden
- What the first read-only cockpit route shape should look like
- How the P10 API client will be used
- Loading, error, empty, and unknown state rules
- Test plan for the first read-only UI

This document does NOT contain UI code. It is a planning boundary for P11-B/C/D implementation.

---

## 1. Frontend Technology Stack (Established)

Per `docs/contracts/frontend_contract.md`:

| Layer | Technology | Version |
|-------|-----------|---------|
| Framework | React | 18.2 |
| Build | Vite | 5.0 |
| Language | TypeScript | Strict |
| Styling | TailwindCSS | 3.3 |
| State | Zustand | 4.4 |
| HTTP | Axios (singleton) | -- |
| Router | React Router v6 | 6.20 |
| Forms | React Hook Form + Zod | -- |
| Tests | Vitest + React Testing Library | -- |

**P11 must follow all frontend_contract.md mandatory requirements.**

---

## 2. Allowed Frontend Files/Areas for P11

### New files (P11-B/C/D may create these):

```
frontend/src/
|-- pages/platform/                          # Platform admin pages
|   |-- PlatformOverviewPage.tsx             # P11-B: Dashboard overview
|   |-- PlatformTenantDirectoryPage.tsx      # P11-C: Tenant list
|   |-- PlatformTenantHealthPage.tsx         # P11-D: Tenant health detail
|   |-- PlatformAuditEventsPage.tsx          # P11-C: Audit event list
|-- components/platform/                     # Platform-specific components
|   |-- PlatformHealthCard.tsx               # System health summary card
|   |-- PlatformTenantCard.tsx               # Tenant summary card
|   |-- PlatformAuditEventRow.tsx            # Audit event row
|   |-- PlatformStatusBadge.tsx              # Health/status badge (extends pattern)
|   |-- PlatformMetricCard.tsx               # Metric display card
|   |-- PlatformUnknownState.tsx             # Unknown state display
|-- services/
|   |-- platformApi.ts                       # Platform P10 API client service
|-- stores/
|   |-- platformStore.ts                     # Platform data state (Zustand)
|-- types/
|   |-- platform.ts                          # P10 contract TypeScript types
|-- hooks/
|   |-- usePlatformData.ts                   # Platform data fetching hook
|-- router/
    |-- (modify AppRouter.tsx)               # Add /platform/* routes
```

### Existing files P11 may modify:

| File | Modification | Scope |
|------|-------------|-------|
| `frontend/src/router/AppRouter.tsx` | Add `/platform/*` route group | 1 route block |
| `frontend/src/components/layout/Sidebar.tsx` | Add "Platform" nav item (super_admin only) | 1 nav item |
| `frontend/src/services/api.ts` | No modification -- auth transport must be resolved in P11-B before API wiring | -- |
| `frontend/src/types/auth.ts` | May add platform role type if needed | Minimal |

### Existing files P11 may reuse but NOT modify:

| File | Usage |
|------|-------|
| `components/ui/EmptyState.tsx` | Reuse for empty platform data states |
| `components/ui/StatusBadge.tsx` | Reuse for tenant health badges |
| `components/ui/Skeleton.tsx` | Reuse for loading states |
| `components/ui/Pagination.tsx` | Reuse for paginated lists |
| `components/layout/MainLayout.tsx` | Platform pages use same layout |
| `services/api.ts` | Platform API calls use same Axios instance |
| `stores/authStore.ts` | Read-only: check `user.roles` for platform access |

---

## 3. Forbidden Areas

### Absolute forbidden (P11 must not touch):

| Area | Path pattern | Reason |
|------|-------------|--------|
| Auth/RBAC/session | `stores/authStore.ts` (writes), `services/authService.ts`, `router/guards.tsx` | No auth/RBAC/session rewrite |
| Payment flows | `pages/finance/*`, `services/*payment*` | No payment paths |
| Tenant business data | `pages/orders/*`, `pages/inventory/*`, `pages/skus/*`, `pages/retailers/*` | No product business data edits |
| Client app | `pages/client/*`, `components/layout/ClientLayout.tsx` | No retailer-facing changes |
| Migrations | `*/migrations/*`, `*/alembic/*` | No migrations |
| Backend code | `backend/` | P11-A is frontend boundary only |
| Product dev recovered | `product-dev-recovered/` | Forbidden |
| `.github/` | `.github/` | Forbidden |
| `.claude/` | `.claude/` | Forbidden |

### Conditional forbidden (require explicit CTO gate):

| Area | Reason |
|------|--------|
| `frontend/src/types/auth.ts` (modifications) | Adding platform role type is allowed; changing auth flow is forbidden |
| `frontend/src/services/api.ts` (modifications) | Adding platform headers is allowed; changing interceptor logic is forbidden |

---

## 4. Expected Platform Admin Cockpit Route Shape

### Route structure:

```tsx
// In AppRouter.tsx, add under ProtectedRoute:
{
  element: <PlatformRoute />,     // New: checks super_admin role
  children: [
    {
      element: <MainLayout />,     // Reuse existing layout
      children: [
        { path: '/platform', element: <PlatformOverviewPage /> },
        { path: '/platform/tenants', element: <PlatformTenantDirectoryPage /> },
        { path: '/platform/tenants/:tenantId/health', element: <PlatformTenantHealthPage /> },
        { path: '/platform/audit', element: <PlatformAuditEventsPage /> },
        { path: '/platform/system/health', element: <PlatformSystemHealthPage /> },
      ],
    },
  ],
}
```

### Route guard:

```tsx
// frontend/src/router/guards.tsx -- ADD ONLY, do not modify existing guards
export function PlatformRoute() {
  const user = useAuthStore((s) => s.user);
  const isPlatformOperator = user?.roles?.includes('super_admin');

  if (!isPlatformOperator) {
    return <Navigate to="/" replace />;
  }

  return <Outlet />;
}
```

### Sidebar addition:

```tsx
// Add to navItems conditionally:
{ label: 'Platform', path: '/platform', icon: ShieldCheckIcon }
// Only visible when user.roles includes 'super_admin'
```

### Route table:

| Route | Page | P10 API | Phase |
|-------|------|---------|-------|
| `/platform` | PlatformOverviewPage | `GET /platform/p10/tenants` + `GET /platform/p10/system/health` | P11-B |
| `/platform/tenants` | PlatformTenantDirectoryPage | `GET /platform/p10/tenants` | P11-C |
| `/platform/tenants/:id/health` | PlatformTenantHealthPage | `GET /platform/p10/tenants/{id}/health` | P11-D |
| `/platform/audit` | PlatformAuditEventsPage | `GET /platform/p10/audit/events` | P11-C |
| `/platform/system/health` | PlatformSystemHealthPage | `GET /platform/p10/system/health` | P11-D |

---

## 5. Expected P10 API Client Usage

### Service layer pattern:

```typescript
// frontend/src/services/platformApi.ts
import { api } from './api';
import type {
  PlatformTenantSummaryList,
  PlatformTenantHealth,
  PlatformSystemHealth,
  PlatformAuditEventList,
} from '@/types/platform';

// The P10 API base path
const P10_BASE = '/platform/p10';

export const platformService = {
  listTenants: (limit = 50, offset = 0) =>
    api.get<PlatformTenantSummaryList>(`${P10_BASE}/tenants`, { params: { limit, offset } }),

  getTenant: (tenantId: string) =>
    api.get<PlatformTenantSummary>(`${P10_BASE}/tenants/${tenantId}`),

  getTenantHealth: (tenantId: string) =>
    api.get<PlatformTenantHealth>(`${P10_BASE}/tenants/${tenantId}/health`),

  getSystemHealth: () =>
    api.get<PlatformSystemHealth>(`${P10_BASE}/system/health`),

  listAuditEvents: (limit = 50, offset = 0) =>
    api.get<PlatformAuditEventList>(`${P10_BASE}/audit/events`, { params: { limit, offset } }),

  getAuditEvent: (eventId: string) =>
    api.get<PlatformAuditEvent>(`${P10_BASE}/audit/events/${eventId}`),
};
```

### Key rules:

1. **Must use the existing `api` Axios singleton** -- no separate client.
2. **AUTH TRANSPORT RESOLVED (P11-B0):** The backend P10 guard has been extended to accept Bearer-authenticated `super_admin` users. The frontend sends standard Bearer tokens via the existing Axios interceptor. No `X-Platform-Operator` secret material is ever sent to or stored in the browser. The `X-Platform-Operator` header remains available for server/operator contexts. This was resolved in P11-B0 as a separate backend slice before P11-B UI work begins.
3. **All responses are P10 contract shapes** -- TypeScript types must match P10-A contracts exactly.
4. **No caching layer needed initially** -- Zustand store holds fetched data; refetch on mount is acceptable for P11.

### TypeScript types (from P10-A contracts):

```typescript
// frontend/src/types/platform.ts
// Must match PLATFORM_PRODUCT_CONTRACTS.md P10-A-R1 exactly

export type TenantStatus = 'draft' | 'active' | 'paused' | 'suspended' | 'archived' | 'unknown';
export type HealthStatus = 'healthy' | 'degraded' | 'unhealthy' | 'unknown';
export type AuditScope = 'global' | 'tenant' | 'system' | 'support';
export type AuditResult = 'allowed' | 'denied' | 'failed' | 'completed';

export interface PlatformTenantSummary { /* 11 fields from P10-A */ }
export interface PlatformTenantSummaryList { items: PlatformTenantSummary[]; total: number; limit: number; offset: number; }
export interface PlatformTenantHealth { /* 10 fields from P10-A */ }
export interface PlatformSystemHealth { /* 11 fields from P10-A */ }
export interface PlatformAuditEvent { /* 11 fields from P10-A */ }
export interface PlatformAuditEventList { items: PlatformAuditEvent[]; total: number; limit: number; offset: number; }
```

---

## 6. Loading/Error/Empty/Unknown State Rules

### Acceptance criteria (from PLATFORM_PRODUCT_ACCEPTANCE_CRITERIA.md):

> P11 must show `unknown` distinctly from `healthy`.

### State matrix:

| State | When | Visual | Component |
|-------|------|--------|-----------|
| **Loading** | API request in flight | Skeleton placeholder | Reuse `Skeleton.tsx` |
| **Error** | API returns 4xx/5xx or network failure | Error card with message + retry button | New `PlatformErrorState.tsx` |
| **Empty** | API returns `{ items: [], total: 0 }` | Empty state with icon + description | Reuse `EmptyState.tsx` |
| **Unknown** | Field value is `null` or `"unknown"` | Gray badge/icon with tooltip "Data unavailable" | New `PlatformUnknownState.tsx` |
| **Healthy** | Status is `"healthy"` | Green badge | Reuse `StatusBadge.tsx` |
| **Degraded** | Status is `"degraded"` | Yellow/amber badge | Reuse `StatusBadge.tsx` |
| **Unhealthy** | Status is `"unhealthy"` | Red badge | Reuse `StatusBadge.tsx` |

### Critical rules:

1. **Unknown != healthy.** Never render unknown status as green or "OK".
2. **Null != zero.** `user_count: null` means "unavailable", not "0 users". Display as "--" or "N/A" with tooltip.
3. **Degraded gracefully.** If one API call fails, show what succeeded. Don't block the entire page.
4. **No raw data display.** Never show raw `metadata_redacted` payloads to the user. Only display structured fields.
5. **No write/destructive buttons in P11.** All pages are read-only. No "edit", "delete", "create", "pause" buttons.

---

## 7. Test Plan for First Read-Only UI

### Test framework:

- **Vitest** + **React Testing Library** (per frontend_contract.md)
- Test files colocated or in `__tests__/` subdirectories

### Test categories:

| Category | Count (est.) | Description |
|----------|-------------|-------------|
| Route guard | 3 | PlatformRoute denies non-super-admin, allows super_admin, redirects to / |
| Type conformance | 6 | TypeScript types match P10-A contracts (compile-time) |
| Service layer | 6 | platformApi calls correct endpoints with correct params |
| Component render | 8 | Each page/component renders with loading, error, empty, unknown states |
| State display | 4 | Unknown shown distinctly from healthy; null shown as N/A |
| Integration | 3 | Full page render with mocked API showing real contract fixture data |
| Forbidden | 3 | No write buttons present; no raw metadata display; no business data fields |
| **Total estimate** | **~33** | |

### Key test cases:

```
TG-001: PlatformRoute renders for super_admin
TG-002: PlatformRoute redirects for regular user
TG-003: PlatformRoute redirects for unauthenticated user
TS-001: platformApi.listTenants calls GET /platform/p10/tenants with limit/offset
TS-002: platformApi.getSystemHealth calls GET /platform/p10/system/health
TS-003: platformApi returns typed PlatformTenantSummaryList
TC-001: PlatformOverviewPage renders with loading skeletons
TC-002: PlatformOverviewPage renders with healthy data
TC-003: PlatformOverviewPage renders with unknown states (shows unknown badges)
TC-004: PlatformOverviewPage renders with error state + retry
TC-005: PlatformTenantDirectoryPage renders empty state when total=0
TC-006: PlatformTenantHealthPage shows null fields as "N/A" not "0"
TC-007: PlatformAuditEventsPage renders event list with pagination
TC-008: PlatformStatusBadge shows unknown as gray, distinct from green healthy
TF-001: No edit/delete/create buttons on any P11 page
TF-002: metadata_redacted is never rendered as raw text
TF-003: No tenant business data (orders, inventory, payments) on platform pages
```

---

## 8. Risks and Open Questions

### Risks:

| Risk | Severity | Mitigation |
|------|----------|------------|
| ~~P11-B cannot wire APIs until auth transport is resolved~~ | ~~HIGH~~ | **RESOLVED in P11-B0**: Backend guard now accepts Bearer-authenticated super_admin users. Frontend uses existing Axios Bearer token. No secret material in browser. |
| Platform API surface exposed without proper auth | HIGH | Mitigated by P10-R2 hardened guard + P11-B0 Bearer super_admin check; frontend adds PlatformRoute guard as defense-in-depth |
| Unknown state confused with healthy | MEDIUM | Explicit test cases (TC-003, TC-006, TC-008); design tokens for unknown vs healthy |
| Frontend platform code mixed with tenant business code | LOW | Strict file boundary: all new code in pages/platform/ and components/platform/ |
| P10 telemetry fields all return null | LOW | Expected -- UI must handle gracefully with unknown/empty states |

### Open questions:

1. ~~**Platform auth transport (BLOCKING for P11-B):**~~ **RESOLVED in P11-B0.** Backend guard extended to accept Bearer-authenticated super_admin. Frontend uses standard Bearer tokens. X-Platform-Operator remains for server/operator contexts. Browser never receives PLATFORM_OPERATOR_SECRET.

2. **Platform route guard**: Should the frontend check `user.roles` from JWT payload, or call a separate platform identity endpoint? Current plan: check `user.roles.includes('super_admin')` from auth store.

3. **Sidebar visibility**: Should the "Platform" nav item be hidden for non-platform users, or always visible but grayed out? Current plan: hidden for non-super-admin.

4. **Real-time updates**: Should the cockpit auto-refresh? Current plan: manual refresh only for P11. Auto-refresh deferred to P13.

5. **Error boundary**: Should platform pages have a dedicated error boundary separate from the main app? Current plan: reuse existing error handling patterns.

6. **Mobile responsiveness**: Should the platform cockpit be mobile-friendly? Current plan: desktop-first for P11. Mobile support deferred.

---

## 9. Implementation Phasing

| Phase | Scope | Deliverables |
|-------|-------|-------------|
| **P11-B** | Foundation | types/platform.ts, services/platformApi.ts, stores/platformStore.ts, PlatformRoute guard, sidebar integration, PlatformOverviewPage |
| **P11-C** | Directory | PlatformTenantDirectoryPage, PlatformAuditEventsPage, pagination, search/filter |
| **P11-D** | Detail | PlatformTenantHealthPage, PlatformSystemHealthPage, unknown state handling, health badges |

---

## 10. Boundary Checklist

Before any P11 frontend code is merged:

- [ ] **P11-B auth transport gate resolved (P11-B0):** Backend P10 guard now accepts Bearer-authenticated super_admin users (P11-B0). Frontend uses standard Bearer tokens. No secret material in browser.
- [ ] All new files are in `pages/platform/`, `components/platform/`, `services/platformApi.ts`, `stores/platformStore.ts`, `types/platform.ts`
- [ ] No modifications to auth flow (`guards.tsx` additions only, no changes to existing `ProtectedRoute`/`PublicRoute`)
- [ ] No modifications to `services/api.ts` interceptor logic
- [ ] No payment, order, inventory, SKU, or retailer pages touched
- [ ] No backend code changes (unless in a separately approved backend/security slice for auth transport)
- [ ] No migrations
- [ ] All TypeScript types match P10-A contracts exactly
- [ ] Unknown state displayed distinctly from healthy in all components
- [ ] No write/destructive buttons on any P11 page
- [ ] No raw metadata_redacted payloads rendered
- [ ] Tests pass with Vitest
- [ ] Forbidden path audit clean
- [ ] GitNexus risk LOW/docs-only for P11-A; may be LOW/additive for P11-B/C/D
