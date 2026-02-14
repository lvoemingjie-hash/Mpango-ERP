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
