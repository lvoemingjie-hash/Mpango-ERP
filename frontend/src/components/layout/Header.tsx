import { useLocation } from 'react-router-dom';
import { ChevronRightIcon } from '@heroicons/react/20/solid';
import { UserCircleIcon } from '@heroicons/react/24/solid';
import { BuildingOffice2Icon } from '@heroicons/react/24/outline';
import { useAuthStore } from '@/stores/authStore';

/**
 * Generates breadcrumb segments from the current pathname.
 * e.g. "/users/123" -> [{ label: "Users", path: "/users" }, { label: "123", path: "/users/123" }]
 */
function useBreadcrumbs() {
  const { pathname } = useLocation();

  if (pathname === '/') {
    return [{ label: 'Dashboard', path: '/' }];
  }

  const segments = pathname.split('/').filter(Boolean);
  return segments.map((seg, i) => ({
    label: seg.charAt(0).toUpperCase() + seg.slice(1),
    path: '/' + segments.slice(0, i + 1).join('/'),
  }));
}

export function Header() {
  const user = useAuthStore((s) => s.user);
  const tenantCode = useAuthStore((s) => s.tenantCode);
  const breadcrumbs = useBreadcrumbs();
  const roleLabel = Array.isArray(user?.roles) ? user.roles[0] : undefined;

  return (
    <header className="sticky top-0 z-20 flex h-16 shrink-0 items-center justify-between border-b border-gray-200 bg-white px-6">
      {/* Breadcrumbs */}
      <nav className="flex items-center gap-1 text-sm">
        {breadcrumbs.map((crumb, i) => (
          <span key={crumb.path} className="flex items-center gap-1">
            {i > 0 && (
              <ChevronRightIcon className="h-4 w-4 text-gray-400" />
            )}
            <span
              className={
                i === breadcrumbs.length - 1
                  ? 'font-medium text-gray-900'
                  : 'text-gray-500'
              }
            >
              {crumb.label}
            </span>
          </span>
        ))}
      </nav>

      {/* Tenant + User Info */}
      <div className="flex items-center gap-4">
        {tenantCode && (
          <div className="flex items-center gap-1.5 rounded-md bg-primary-50 px-2.5 py-1">
            <BuildingOffice2Icon className="h-4 w-4 text-primary-600" />
            <span className="text-xs font-semibold text-primary-700">{tenantCode}</span>
          </div>
        )}
        {user && (
          <div className="flex items-center gap-2">
            <UserCircleIcon className="h-8 w-8 text-gray-400" />
            <div className="text-right">
              <p className="text-sm font-medium text-gray-900">
                {user.full_name || user.email}
              </p>
              <p className="text-xs text-gray-500">
                {roleLabel || 'User'}
              </p>
            </div>
          </div>
        )}
      </div>
    </header>
  );
}
