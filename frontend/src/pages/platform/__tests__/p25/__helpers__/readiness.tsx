/**
 * P25-B shared readiness harness helpers.
 *
 * Grounded in the as-built P10-P24 surface:
 *   - frontend/src/router/AppRouter.tsx (PlatformRoute subtree)
 *   - frontend/src/router/guards.tsx (PlatformRoute, isIdentityPlatformOperator)
 *   - frontend/src/components/layout/Sidebar.tsx (platform nav section)
 *
 * P25-B is a NON-SHIPPING, NON-MERGING readiness/validation harness only.
 * It adds no capability, no route, no backend, no migration. It records
 * results (pass / skip-with-reason / fail) and records defects for a later,
 * separately approved fix slice; it never fixes a defect inline.
 */
import { readFileSync, readdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { type ReactNode } from 'react';
import { render } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { useAuthStore } from '@/stores/authStore';
import { usePlatformStore } from '@/stores/platformStore';
import { PlatformRoute } from '@/router/guards';
import type { CurrentUserData } from '@/types/auth';

// -- Page components (the closed P10-P24 platform surface) ----------------
import { PlatformOverviewPage } from '@/pages/platform/PlatformOverviewPage';
import { PlatformTenantDirectoryPage } from '@/pages/platform/PlatformTenantDirectoryPage';
import { PlatformAuditEventsPage } from '@/pages/platform/PlatformAuditEventsPage';
import { PlatformTenantHealthPage } from '@/pages/platform/PlatformTenantHealthPage';
import { PlatformSystemHealthPage } from '@/pages/platform/PlatformSystemHealthPage';
import { SupportConsolePage } from '@/pages/platform/SupportConsolePage';
import { PlatformRegistryPage } from '@/pages/platform/PlatformRegistryPage';
import { PlatformControlledActionsPage } from '@/pages/platform/PlatformControlledActionsPage';
import { PlatformApprovalsPage } from '@/pages/platform/PlatformApprovalsPage';
import { PlatformDurableApprovalsPage } from '@/pages/platform/PlatformDurableApprovalsPage';
import { PlatformControlledExecutionConsolePage } from '@/pages/platform/PlatformControlledExecutionConsolePage';
import { PlatformOperatorTasksPage } from '@/pages/platform/PlatformOperatorTasksPage';
import { PlatformIncidentCloseoutsPage } from '@/pages/platform/PlatformIncidentCloseoutsPage';
import { OpsHealthPage } from '@/pages/platform/ops/OpsHealthPage';
import { OpsErrorsPage } from '@/pages/platform/ops/OpsErrorsPage';
import { OpsSlowRoutesPage } from '@/pages/platform/ops/OpsSlowRoutesPage';
import { OpsResourcesPage } from '@/pages/platform/ops/OpsResourcesPage';
import { OpsNoisyNeighborsPage } from '@/pages/platform/ops/OpsNoisyNeighborsPage';
import { IncidentTriagePage } from '@/pages/platform/ops/IncidentTriagePage';

/**
 * P25-A section 3 route inventory (19 routes). This is the CLOSED set; it is
 * grounded in AppRouter.tsx and Sidebar.tsx, not invented. A route's
 * `sidebar` field is the Sidebar.tsx nav entry that reaches it, or null when
 * the route is reached only via a parent page or by direct URL.
 *
 * `group`  -> capability family (matches the P25-A section 3 grouping).
 * `empty`  -> minimal empty backend body for the empty-state matrix cell.
 */
export interface PlatformRouteEntry {
  path: string;
  name: string;
  component: () => ReactNode;
  group: string;
  sidebarLabel: string | null;
  sidebarPath: string | null;
  empty: unknown;
}

export const PLATFORM_ROUTES: PlatformRouteEntry[] = [
  { path: '/platform', name: 'Platform Overview', component: () => <PlatformOverviewPage />, group: 'overview', sidebarLabel: 'Platform', sidebarPath: '/platform', empty: { items: [], total: 0 } },
  { path: '/platform/system/health', name: 'System Health', component: () => <PlatformSystemHealthPage />, group: 'health', sidebarLabel: null, sidebarPath: null, empty: {} },
  { path: '/platform/tenants', name: 'Tenant Directory', component: () => <PlatformTenantDirectoryPage />, group: 'registry', sidebarLabel: null, sidebarPath: null, empty: { items: [], total: 0 } },
  { path: '/platform/tenants/:tenantId/health', name: 'Tenant Health', component: () => <PlatformTenantHealthPage />, group: 'health', sidebarLabel: null, sidebarPath: null, empty: {} },
  { path: '/platform/audit', name: 'Audit Events', component: () => <PlatformAuditEventsPage />, group: 'overview', sidebarLabel: null, sidebarPath: null, empty: { items: [], total: 0 } },
  { path: '/platform/registry', name: 'Registry', component: () => <PlatformRegistryPage />, group: 'registry', sidebarLabel: null, sidebarPath: null, empty: { tenants: [], total: 0 } },
  { path: '/platform/support', name: 'Support Console', component: () => <SupportConsolePage />, group: 'support', sidebarLabel: 'Support Console', sidebarPath: '/platform/support', empty: { items: [], total: 0 } },
  { path: '/platform/ops/health', name: 'Ops Health', component: () => <OpsHealthPage />, group: 'ops', sidebarLabel: 'Ops Cockpit', sidebarPath: '/platform/ops/health', empty: {} },
  { path: '/platform/ops/errors', name: 'Ops Errors', component: () => <OpsErrorsPage />, group: 'ops', sidebarLabel: null, sidebarPath: null, empty: { items: [], total: 0 } },
  { path: '/platform/ops/slow-routes', name: 'Ops Slow Routes', component: () => <OpsSlowRoutesPage />, group: 'ops', sidebarLabel: null, sidebarPath: null, empty: { items: [], total: 0 } },
  { path: '/platform/ops/resources', name: 'Ops Resources', component: () => <OpsResourcesPage />, group: 'ops', sidebarLabel: null, sidebarPath: null, empty: {} },
  { path: '/platform/ops/noisy-neighbors', name: 'Ops Noisy Neighbors', component: () => <OpsNoisyNeighborsPage />, group: 'ops', sidebarLabel: null, sidebarPath: null, empty: { items: [], total: 0 } },
  { path: '/platform/ops/incidents/triage', name: 'Incident Triage', component: () => <IncidentTriagePage />, group: 'ops', sidebarLabel: 'Incident Triage', sidebarPath: '/platform/ops/incidents/triage', empty: {} },
  { path: '/platform/controlled-actions', name: 'Controlled Actions', component: () => <PlatformControlledActionsPage />, group: 'actions', sidebarLabel: 'Controlled Actions', sidebarPath: '/platform/controlled-actions', empty: { items: [], total: 0 } },
  { path: '/platform/approvals', name: 'Approvals', component: () => <PlatformApprovalsPage />, group: 'approvals', sidebarLabel: 'Approvals', sidebarPath: '/platform/approvals', empty: { items: [], total: 0 } },
  { path: '/platform/durable-approvals', name: 'Durable Approvals', component: () => <PlatformDurableApprovalsPage />, group: 'approvals', sidebarLabel: 'Durable Approvals', sidebarPath: '/platform/durable-approvals', empty: { items: [], total: 0 } },
  { path: '/platform/controlled-execution', name: 'Controlled Execution', component: () => <PlatformControlledExecutionConsolePage />, group: 'execution', sidebarLabel: 'Controlled Execution', sidebarPath: '/platform/controlled-execution', empty: {} },
  { path: '/platform/operator-tasks', name: 'Operator Tasks', component: () => <PlatformOperatorTasksPage />, group: 'tasks', sidebarLabel: 'Operator Tasks', sidebarPath: '/platform/operator-tasks', empty: { items: [], total: 0 } },
  { path: '/platform/incident-closeouts', name: 'Incident Closeouts', component: () => <PlatformIncidentCloseoutsPage />, group: 'closeouts', sidebarLabel: 'Incident Closeouts', sidebarPath: '/platform/incident-closeouts', empty: { items: [], total: 0 } },
];

/** Direct sidebar-linked routes (10), reachable from the Sidebar platform section. */
export const SIDEBAR_ROUTES = PLATFORM_ROUTES.filter((r) => r.sidebarPath !== null);

/**
 * Routes used by the state / copy / forbidden sweeps.
 *
 * P25-C resolved defect D2 (EmptyState now carries its required `icon` prop on
 * PlatformAuditEventsPage and PlatformTenantDirectoryPage), so the empty-state
 * render no longer crashes and EVERY route is swept (19/19).
 */
export const SWEEP_ROUTES = PLATFORM_ROUTES;

// -- Reachability scan (D1) ------------------------------------------------
//
// A route is REACHABLE when it has a Sidebar link OR an in-app <Link> from a
// platform page/component. This reads the same closed source set the as-built
// surface ships (pages + components, no tests), so the URL_ONLY_ROUTES list is
// EMPTY once every route is genuinely navigable and turns non-empty the moment
// a reachability link is removed -- the D1 test in P25_RecordedDefects goes
// RED if reachability regresses.

const PLATFORM_SRC_ROOT = resolve(process.cwd(), 'src/pages/platform');
const PLATFORM_COMPONENT_ROOT = resolve(process.cwd(), 'src/components/platform');

/** Concatenate every shipped platform page + component source (.tsx, no tests). */
function readAllPlatformSource(): string {
  const dirs = [PLATFORM_SRC_ROOT, resolve(PLATFORM_SRC_ROOT, 'ops'), PLATFORM_COMPONENT_ROOT];
  let acc = '';
  for (const d of dirs) {
    let entries: string[] = [];
    try {
      entries = readdirSync(d);
    } catch {
      continue;
    }
    for (const f of entries) {
      if (f.endsWith('.tsx') && !f.includes('.test.')) {
        try {
          acc += readFileSync(resolve(d, f), 'utf-8');
        } catch {
          /* ignore an unreadable entry */
        }
      }
    }
  }
  return acc;
}

const PLATFORM_SOURCE = readAllPlatformSource();

/**
 * Reachable = Sidebar link (sidebarPath !== null) OR an in-app <Link>. A static
 * path appears as a link target in either idiom -- the JSX attribute
 * `to="<path>"` or an object-key `to: '<path>'` fed into `<Link to={item.to}>`
 * -- but NOT as an AppRouter `path:` declaration. The parameterized
 * tenant-health route appears as a template literal in PlatformTenantCard.
 */
function linkTargetRe(path: string): RegExp {
  const escaped = path.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return new RegExp(`to[:=]\\s*['"]${escaped}['"]`);
}

export function routeIsReachable(r: PlatformRouteEntry): boolean {
  if (r.sidebarPath !== null) return true;
  if (r.path.includes(':')) {
    return PLATFORM_SOURCE.includes('`/platform/tenants/${');
  }
  return linkTargetRe(r.path).test(PLATFORM_SOURCE);
}

/**
 * Routes with NO Sidebar link and NO in-app <Link> -- reachable only by direct
 * URL. EMPTY once P25-C hub links make every route navigable; non-empty the
 * moment a reachability link is removed.
 */
export const URL_ONLY_ROUTES = PLATFORM_ROUTES.filter((r) => !routeIsReachable(r));

// -- Identity fixtures -----------------------------------------------------

export const IDENTITY_ONLY_SUPER_ADMIN: CurrentUserData = {
  id: 'u-super',
  email: 'super@mpango.example',
  full_name: 'Super Admin',
  tenant_id: null,
  tenant_schema: null,
  roles: ['super_admin'],
  permissions: [],
};

export const TENANT_CONTEXTUAL_SUPER_ADMIN: CurrentUserData = {
  id: 'u-tenant',
  email: 'tenant@mpango.example',
  full_name: 'Tenant Admin',
  tenant_id: 't-1',
  tenant_schema: 't1',
  roles: ['super_admin'],
  permissions: [],
};

export const REGULAR_USER: CurrentUserData = {
  id: 'u-reg',
  email: 'user@mpango.example',
  full_name: 'Regular',
  tenant_id: 't-1',
  tenant_schema: 't1',
  roles: ['user'],
  permissions: [],
};

export function setAuth(user: CurrentUserData | null, token: string | null = null) {
  useAuthStore.setState({ user, accessToken: token });
}

export function clearAuth() {
  useAuthStore.setState({ user: null, accessToken: null });
}

/** Reset the shared platform Zustand store between tests (it is a singleton). */
export function resetPlatformStore() {
  usePlatformStore.getState().reset();
}

/**
 * Comprehensive flat empty backend body for the empty-state matrix cell.
 *
 * Pages read a variety of `data.X` fields, some WITHOUT optional chaining
 * (e.g. `data.signals.length`, `catalog.items.map`, `data.error_classes`). A
 * flat body (no `data` envelope key) is used so the `res.data?.data ?? res.data`
 * unwrap resolves to the body itself, and every key a page reads directly is
 * present with a safe empty value (lists `[]`, sub-objects `{}`, scalars 0 /
 * null / 'unknown'). This exercises the true empty path per route without
 * per-page fixture brittleness.
 */
export const EMPTY_BODY = {
  items: [] as unknown[],
  total: 0,
  events: [] as unknown[],
  audit_events: [] as unknown[],
  tenants: [] as unknown[],
  actions: [] as unknown[],
  approvals: [] as unknown[],
  durable_approvals: [] as unknown[],
  tasks: [] as unknown[],
  closeouts: [] as unknown[],
  steps: [] as unknown[],
  sessions: [] as unknown[],
  slow_routes: [] as unknown[],
  slowRoutes: [] as unknown[],
  errors: [] as unknown[],
  error_classes: [] as unknown[],
  top_routes: [] as unknown[],
  routes: [] as unknown[],
  noisy_neighbors: [] as unknown[],
  noisyNeighbors: [] as unknown[],
  components: [] as unknown[],
  signals: [] as unknown[],
  results: [] as unknown[],
  exclusions: [] as unknown[],
  examples: [] as unknown[],
  recent_errors: null,
  activity_counters: null,
  failed_jobs: null,
  resources: {} as Record<string, unknown>,
  database: {} as Record<string, unknown>,
  queue: {} as Record<string, unknown>,
  database_probe: {} as Record<string, unknown>,
  lifecycle_state: {} as Record<string, unknown>,
  operational_flags: {} as Record<string, unknown>,
  total_errors: 0,
  total_slow_requests: 0,
  tenant_health_sample_count: 0,
  tenant_health_unhealthy_count: 0,
  window_minutes: null,
  threshold_ms: null,
  generated_at: null,
  unavailable_reason: null,
  source_status: 'unknown',
  degraded_reason: null,
  overall_status: 'unknown',
  graceful_degraded: null,
  registry_source_status: 'unknown',
};

// -- Render harness --------------------------------------------------------

/**
 * Render the full as-built platform subtree exactly as AppRouter wires it:
 * every section-3 route under <PlatformRoute />. A "/" home route is included
 * so deny-path redirects (Navigate to "/") are observable.
 */
export function renderPlatformAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/" element={<div data-testid="home">home</div>} />
        <Route element={<PlatformRoute />}>
          {PLATFORM_ROUTES.map((r) => (
            <Route key={r.path} path={r.path} element={r.component()} />
          ))}
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

// -- Copy / leak safety (P23 never-leaked list, applied platform-wide) ------

/**
 * Patterns a readiness sweep must never find in rendered platform text:
 * secrets, DSNs, host:port, bearer tokens, cookies, auth headers, raw
 * payloads, shell, SQL, or tenant business payloads. Fixture values used in
 * tests are intentionally benign (example.test / .example / fake ids).
 */
export const LEAK_PATTERNS: Array<{ name: string; re: RegExp }> = [
  { name: 'postgres-dsn', re: /postgres(?:ql)?:\/\/[^\s"']+/i },
  { name: 'mysql-dsn', re: /mysql:\/\//i },
  { name: 'redis-dsn', re: /redis:\/\//i },
  { name: 'mongodb-dsn', re: /mongodb(?:\+srv)?:\/\//i },
  { name: 'amazonaws', re: /https?:\/\/[a-z0-9.-]*\.amazonaws\.com/i },
  { name: 'bearer-token', re: /bearer\s+[A-Za-z0-9._-]{8,}/i },
  { name: 'basic-auth-header', re: /authorization:\s*basic\s+/i },
  { name: 'api-key', re: /(?:x-api-key|api[_-]?key)\s*[:=]\s*[A-Za-z0-9_\-]{12,}/i },
  { name: 'aws-access-key', re: /AKIA[0-9A-Z]{12,}/ },
  { name: 'jwt', re: /eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}/ },
  { name: 'set-cookie', re: /set-cookie\s*:/i },
  { name: 'private-key', re: /-----BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY-----/ },
  { name: 'password-assignment', re: /password\s*[:=]\s*\S{6,}/i },
  { name: 'shell-injection', re: /(?:rm\s+-rf|curl\s+.*\|\s*sh|wget\s+.*\|\s*bash)/i },
  { name: 'raw-sql-dml', re: /\b(?:DROP\s+TABLE|DELETE\s+FROM|TRUNCATE\s+TABLE)\b/i },
];

/** Scan a blob of rendered text for any leak pattern; returns the hits. */
export function scanForLeaks(text: string): Array<{ name: string; match: string }> {
  const hits: Array<{ name: string; match: string }> = [];
  for (const { name, re } of LEAK_PATTERNS) {
    const m = text.match(re);
    if (m) hits.push({ name, match: m[0] });
  }
  return hits;
}
