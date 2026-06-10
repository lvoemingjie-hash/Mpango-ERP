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
 * PlatformRoute — P11-B1 platform admin route guard.
 *
 * Only identity/global super_admin may enter platform cockpit routes.
 * Reads user.roles from auth store (populated from JWT payload).
 * Does NOT modify existing auth flow or guards — additive only.
 *
 * Non-super-admin users are redirected to the main dashboard.
 */
export function PlatformRoute() {
  const user = useAuthStore((s) => s.user);
  const isPlatformOperator = user?.roles?.includes('super_admin');

  if (!isPlatformOperator) {
    return <Navigate to="/" replace />;
  }

  return <Outlet />;
}
