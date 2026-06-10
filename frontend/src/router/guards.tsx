import { Navigate, Outlet } from 'react-router-dom';
import { useAuthStore } from '@/stores/authStore';

/**
 * ProtectedRoute — redirects to /login if not authenticated.
 * Wraps child routes via <Outlet />.
 */
export function ProtectedRoute() {
  const accessToken = useAuthStore((s) => s.accessToken);

  if (!accessToken) {
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
