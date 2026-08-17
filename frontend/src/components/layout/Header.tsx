import { useLocation } from 'react-router-dom';
import { ChevronRightIcon, Bars3Icon } from '@heroicons/react/20/solid';
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

export interface HeaderProps {
  /** PW1-R4-C1: whether the mobile navigation drawer is open. */
  drawerOpen?: boolean;
  /** Ref to the hamburger button for focus restoration after drawer close. */
  hamburgerRef?: React.RefObject<HTMLButtonElement>;
  /** Toggle callback for the mobile navigation drawer. */
  onToggleDrawer?: () => void;
}

export function Header({ drawerOpen = false, hamburgerRef, onToggleDrawer }: HeaderProps) {
  const user = useAuthStore((s) => s.user);
  const tenantCode = useAuthStore((s) => s.tenantCode);
  const breadcrumbs = useBreadcrumbs();
  const roleLabel = Array.isArray(user?.roles) ? user.roles[0] : undefined;

  return (
    <header className="sticky top-0 z-20 flex h-16 shrink-0 items-center gap-3 border-b border-gray-200 bg-white px-4 lg:px-6">
      {/* Mobile hamburger (PW1-R4-C1 contract 6/7): <lg only, accessible. */}
      <button
        type="button"
        ref={hamburgerRef}
        onClick={onToggleDrawer}
        aria-label="Toggle navigation menu"
        aria-expanded={drawerOpen}
        aria-controls="mobile-navigation-drawer"
        className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-md text-gray-600 hover:bg-gray-100 hover:text-gray-900 lg:hidden"
      >
        <Bars3Icon className="h-6 w-6" aria-hidden="true" />
      </button>

      {/* Breadcrumbs — min-w-0 + truncate contract (no page clipping). */}
      <nav aria-label="Breadcrumb" className="flex min-w-0 flex-1 items-center gap-1 text-sm">
        {breadcrumbs.map((crumb, i) => (
          <span key={crumb.path} className="flex min-w-0 items-center gap-1">
            {i > 0 && (
              <ChevronRightIcon className="h-4 w-4 shrink-0 text-gray-400" />
            )}
            <span
              className={
                i === breadcrumbs.length - 1
                  ? 'truncate font-medium text-gray-900'
                  : 'truncate text-gray-500'
              }
            >
              {crumb.label}
            </span>
          </span>
        ))}
      </nav>

      {/* Tenant + User Info — min-w-0 + truncate contract (no page clipping). */}
      <div className="flex min-w-0 shrink-0 items-center gap-4">
        {tenantCode && (
          <div className="flex min-w-0 items-center gap-1.5 rounded-md bg-primary-50 px-2.5 py-1">
            <BuildingOffice2Icon className="h-4 w-4 shrink-0 text-primary-600" />
            <span className="max-w-[10rem] truncate text-xs font-semibold text-primary-700" title={tenantCode}>
              {tenantCode}
            </span>
          </div>
        )}
        {user && (
          <div className="flex min-w-0 items-center gap-2">
            <UserCircleIcon className="h-8 w-8 shrink-0 text-gray-400" />
            <div className="min-w-0 text-right">
              <p className="truncate text-sm font-medium text-gray-900" title={user.full_name || user.email || undefined}>
                {user.full_name || user.email}
              </p>
              <p className="truncate text-xs text-gray-500">
                {roleLabel || 'User'}
              </p>
            </div>
          </div>
        )}
      </div>
    </header>
  );
}
