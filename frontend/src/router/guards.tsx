import { Navigate, Outlet } from 'react-router-dom';
import { useAuthStore } from '@/stores/authStore';
import { can } from '@/utils/permissions';

/**
 * ProtectedRoute — redirects to /login if not authenticated.
 * Wraps child routes via <Outlet />.
 *
 * DC-12R1-S2: if a stale/expired retailer session is detected (portal code
 * preserved but no access token), redirect back to the same supplier portal
 * instead of the owner login page.
 */
export function ProtectedRoute() {
  const accessToken = useAuthStore((s) => s.accessToken);
  const retailerPortalCode = useAuthStore((s) => s.retailerPortalCode);

  if (!accessToken) {
    if (retailerPortalCode) {
      return <Navigate to={`/retail/login?w=${retailerPortalCode}`} replace />;
    }
    return <Navigate to="/login" replace />;
  }

  return <Outlet />;
}

/**
 * PublicRoute — redirects to / (dashboard) if already authenticated.
 * Used for login page to prevent logged-in users from seeing it.
 */
export function PublicRoute() {
  const accessToken = useAuthStore((s) => s.accessToken);

  if (accessToken) {
    return <Navigate to="/" replace />;
  }

  return <Outlet />;
}

/**
 * PlatformRoute — P11-B1/R1 platform admin route guard.
 *
 * Only identity-only (global) super_admin may enter platform cockpit routes.
 * Identity-only means: user.roles includes super_admin AND user.tenant_id is null
 * AND user.tenant_schema is null.
 *
 * Tenant-contextual super_admin (tenant_id != null) is explicitly denied —
 * the platform cockpit is for identity-level operators only.
 *
 * Does NOT modify existing auth flow or guards — additive only.
 */
export function PlatformRoute() {
  const user = useAuthStore((s) => s.user);

  const isIdentityOnlySuperAdmin =
    !!user &&
    user.roles?.includes('super_admin') === true &&
    user.tenant_id == null &&
    user.tenant_schema == null;

  if (!isIdentityOnlySuperAdmin) {
    return <Navigate to="/" replace />;
  }

  return <Outlet />;
}

/**
 * RetailerRoute — DC-12R1-S2 guard for /client/** routes.
 *
 * Only users carrying the retailer_operator role may enter retailer-facing
 * client routes. On rejection the retailer is redirected back to its portal
 * login (preserving the portal code); owner/platform sessions go to /login.
 */
export function RetailerRoute() {
  const user = useAuthStore((s) => s.user);
  const retailerPortalCode = useAuthStore((s) => s.retailerPortalCode);

  const isRetailerOperator =
    !!user && user.roles?.includes('retailer_operator') === true;

  if (!isRetailerOperator) {
    if (retailerPortalCode) {
      return <Navigate to={`/retail/login?w=${retailerPortalCode}`} replace />;
    }
    return <Navigate to="/login" replace />;
  }

  return <Outlet />;
}

/**
 * RetailerPermissionRoute — DC-12R1-MVP-R0-R1 (WPR-002/WPR-003) permission guard.
 *
 * A reusable nested route guard that admits a route only if the current user
 * holds ``permission``. It reuses the centralized ``can()`` helper (no
 * independent permission algorithm): admins bypass, otherwise the exact
 * permission string must be present in ``user.permissions``.
 *
 * This guard is ALWAYS nested under ``RetailerRoute``, so on entry the user is
 * already an authenticated ``retailer_operator``. When the permission is
 * missing it fails closed BEFORE the child page renders and BEFORE any
 * protected API request can be issued: the user is redirected (replace) to
 * ``/client`` — their legitimate retailer home — mirroring how
 * ``WholesalerRoute`` redirects an authenticated retailer who crosses a
 * boundary. The protected page component never mounts, so its data-fetch
 * effects (and any submit) never run.
 *
 * ``RetailerRoute`` stays role/boundary-only; this guard adds the per-route
 * permission check on top of it. It does NOT weaken or replace any backend
 * ``RequirePermission`` — it is a defense-in-depth client admission check.
 */
export function RetailerPermissionRoute({ permission }: { permission: string }) {
  const user = useAuthStore((s) => s.user);

  if (!can(user, permission)) {
    // Fail closed before render: the guarded page never mounts.
    return <Navigate to="/client" replace />;
  }

  return <Outlet />;
}

/**
 * WholesalerRoute — DC-12R1-S2 guard for wholesaler ERP routes.
 *
 * retailer_operator must NOT enter wholesaler ERP routes. The redirect target
 * depends on session state:
 *   - Authenticated retailer  → /client (their own home; they are signed in,
 *     just on the wrong side of the boundary — we do NOT log them out).
 *   - Stale/unauthenticated    → supplier portal login (preserving the code).
 * All other non-retailer sessions pass through to the existing
 * ProtectedRoute/auth checks.
 */
export function WholesalerRoute() {
  const user = useAuthStore((s) => s.user);
  const accessToken = useAuthStore((s) => s.accessToken);
  const retailerPortalCode = useAuthStore((s) => s.retailerPortalCode);

  const isRetailerOperator =
    !!user && user.roles?.includes('retailer_operator') === true;

  if (isRetailerOperator) {
    if (accessToken) {
      // Authenticated retailer on a wholesaler route → send to retailer home.
      return <Navigate to="/client" replace />;
    }
    // Stale retailer session → back to its supplier portal.
    if (retailerPortalCode) {
      return <Navigate to={`/retail/login?w=${retailerPortalCode}`} replace />;
    }
    return <Navigate to="/retail/login" replace />;
  }

  return <Outlet />;
}

/**
 * Check if user qualifies for platform admin cockpit (identity-only super_admin).
 * Shared between PlatformRoute guard and Sidebar nav visibility.
 */
export function isIdentityPlatformOperator(user: {
  roles?: string[];
  tenant_id: string | null;
  tenant_schema: string | null;
} | null): boolean {
  return (
    !!user &&
    user.roles?.includes('super_admin') === true &&
    user.tenant_id == null &&
    user.tenant_schema == null
  );
}
