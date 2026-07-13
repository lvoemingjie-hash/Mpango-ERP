import { Link, useLocation } from 'react-router-dom';
import {
  HomeIcon,
  BuildingOfficeIcon,
  ArrowRightOnRectangleIcon,
  ClipboardDocumentListIcon,
  CubeIcon,
  BanknotesIcon,
  CreditCardIcon,
  CurrencyDollarIcon,
  ShieldCheckIcon,
  WrenchScrewdriverIcon,
  ChartBarIcon,
  MagnifyingGlassCircleIcon,
  QueueListIcon,
  CheckBadgeIcon,
  LockClosedIcon,
  BeakerIcon,
  ClipboardDocumentCheckIcon,
  LifebuoyIcon,
} from '@heroicons/react/24/outline';
import { useAuthStore } from '@/stores/authStore';
import { isIdentityPlatformOperator } from '@/router/guards';

interface NavItem {
  label: string;
  path: string;
  icon: React.ComponentType<React.SVGProps<SVGSVGElement>>;
}

const navItems: NavItem[] = [
  { label: 'Home', path: '/', icon: HomeIcon },
  { label: 'Sales', path: '/orders', icon: ClipboardDocumentListIcon },
  { label: 'Products', path: '/skus', icon: CubeIcon },
  { label: 'Stock', path: '/inventory', icon: CubeIcon },
  { label: 'Finance', path: '/finance', icon: BanknotesIcon },
  { label: 'Payments', path: '/payments', icon: CreditCardIcon },
  { label: 'Customers', path: '/retailers', icon: BuildingOfficeIcon },
  { label: 'Pricing', path: '/pricing', icon: CurrencyDollarIcon },
  // Temporarily hidden to avoid 404s until implemented
  // { label: 'Team', path: '/users', icon: UsersIcon },
  // { label: 'Settings', path: '/settings', icon: Cog6ToothIcon },
];

export function Sidebar() {
  const location = useLocation();
  const logout = useAuthStore((s) => s.logout);
  const user = useAuthStore((s) => s.user);
  const showPlatformNav = isIdentityPlatformOperator(user);

  const isActive = (path: string) => {
    if (path === '/') return location.pathname === '/';
    return location.pathname.startsWith(path);
  };

  return (
    <aside className="fixed inset-y-0 left-0 z-30 flex w-64 flex-col border-r border-gray-200 bg-white">
      {/* Logo */}
      <div className="flex h-16 shrink-0 items-center gap-2 border-b border-gray-200 px-6">
        <div className="h-8 w-8 rounded-lg bg-primary-600 flex items-center justify-center">
          <span className="text-sm font-bold text-white">M</span>
        </div>
        <span className="text-lg font-semibold text-gray-900">Mpango ERP</span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 px-3 py-4 overflow-y-auto">
        {navItems.map((item) => {
          const active = isActive(item.path);
          return (
            <Link
              key={item.path}
              to={item.path}
              className={`group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${active
                  ? 'bg-primary-50 text-primary-700 ring-1 ring-inset ring-primary-200'
                  : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                }`}
            >
              <item.icon
                className={`h-5 w-5 shrink-0 transition-colors ${active ? 'text-primary-700' : 'text-gray-400 group-hover:text-gray-500'
                  }`}
              />
              {item.label}
              {active && <div className="absolute left-0 h-8 w-1 rounded-r-full bg-primary-600" />}
            </Link>
          );
        })}

        {/* Platform Admin -- identity-only super_admin */}
        {showPlatformNav && (
          <>
            <div className="my-2 border-t border-gray-200" />
            <p className="px-3 pb-1 pt-2 text-xs font-semibold uppercase tracking-wider text-gray-400">
              Platform
            </p>
            <Link
              to="/platform"
              className={`group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${isActive('/platform')
                  ? 'bg-primary-50 text-primary-700 ring-1 ring-inset ring-primary-200'
                  : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                }`}
            >
              <ShieldCheckIcon
                className={`h-5 w-5 shrink-0 transition-colors ${isActive('/platform') ? 'text-primary-700' : 'text-gray-400 group-hover:text-gray-500'
                  }`}
              />
              Platform
              {isActive('/platform') && <div className="absolute left-0 h-8 w-1 rounded-r-full bg-primary-600" />}
            </Link>
            <Link
              to="/platform/support"
              className={`group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${isActive('/platform/support')
                  ? 'bg-primary-50 text-primary-700 ring-1 ring-inset ring-primary-200'
                  : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                }`}
            >
              <WrenchScrewdriverIcon
                className={`h-5 w-5 shrink-0 transition-colors ${isActive('/platform/support') ? 'text-primary-700' : 'text-gray-400 group-hover:text-gray-500'
                  }`}
              />
              Support Console
              {isActive('/platform/support') && <div className="absolute left-0 h-8 w-1 rounded-r-full bg-primary-600" />}
            </Link>
            <Link
              to="/platform/ops/health"
              className={`group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${isActive('/platform/ops')
                  ? 'bg-primary-50 text-primary-700 ring-1 ring-inset ring-primary-200'
                  : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                }`}
            >
              <ChartBarIcon
                className={`h-5 w-5 shrink-0 transition-colors ${isActive('/platform/ops') ? 'text-primary-700' : 'text-gray-400 group-hover:text-gray-500'
                  }`}
              />
              Ops Cockpit
              {isActive('/platform/ops') && <div className="absolute left-0 h-8 w-1 rounded-r-full bg-primary-600" />}
            </Link>
            <Link
              to="/platform/ops/incidents/triage"
              className={`group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${isActive('/platform/ops/incidents/triage')
                  ? 'bg-primary-50 text-primary-700 ring-1 ring-inset ring-primary-200'
                  : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                }`}
            >
              <MagnifyingGlassCircleIcon
                className={`h-5 w-5 shrink-0 transition-colors ${isActive('/platform/ops/incidents/triage') ? 'text-primary-700' : 'text-gray-400 group-hover:text-gray-500'
                  }`}
              />
              Incident Triage
              {isActive('/platform/ops/incidents/triage') && <div className="absolute left-0 h-8 w-1 rounded-r-full bg-primary-600" />}
            </Link>
            <Link
              to="/platform/controlled-actions"
              className={`group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${isActive('/platform/controlled-actions')
                  ? 'bg-primary-50 text-primary-700 ring-1 ring-inset ring-primary-200'
                  : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                }`}
            >
              <QueueListIcon
                className={`h-5 w-5 shrink-0 transition-colors ${isActive('/platform/controlled-actions') ? 'text-primary-700' : 'text-gray-400 group-hover:text-gray-500'
                  }`}
              />
              Controlled Actions
              {isActive('/platform/controlled-actions') && <div className="absolute left-0 h-8 w-1 rounded-r-full bg-primary-600" />}
            </Link>
            <Link
              to="/platform/approvals"
              className={`group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${isActive('/platform/approvals')
                  ? 'bg-primary-50 text-primary-700 ring-1 ring-inset ring-primary-200'
                  : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                }`}
            >
              <CheckBadgeIcon
                className={`h-5 w-5 shrink-0 transition-colors ${isActive('/platform/approvals') ? 'text-primary-700' : 'text-gray-400 group-hover:text-gray-500'
                  }`}
              />
              Approvals
              {isActive('/platform/approvals') && <div className="absolute left-0 h-8 w-1 rounded-r-full bg-primary-600" />}
            </Link>
            <Link
              to="/platform/durable-approvals"
              className={`group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${isActive('/platform/durable-approvals')
                  ? 'bg-primary-50 text-primary-700 ring-1 ring-inset ring-primary-200'
                  : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                }`}
            >
              <LockClosedIcon
                className={`h-5 w-5 shrink-0 transition-colors ${isActive('/platform/durable-approvals') ? 'text-primary-700' : 'text-gray-400 group-hover:text-gray-500'
                  }`}
              />
              Durable Approvals
              {isActive('/platform/durable-approvals') && <div className="absolute left-0 h-8 w-1 rounded-r-full bg-primary-600" />}
            </Link>
            <Link
              to="/platform/controlled-execution"
              className={`group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${isActive('/platform/controlled-execution')
                  ? 'bg-primary-50 text-primary-700 ring-1 ring-inset ring-primary-200'
                  : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                }`}
            >
              <BeakerIcon
                className={`h-5 w-5 shrink-0 transition-colors ${isActive('/platform/controlled-execution') ? 'text-primary-700' : 'text-gray-400 group-hover:text-gray-500'
                  }`}
              />
              Controlled Execution
              {isActive('/platform/controlled-execution') && <div className="absolute left-0 h-8 w-1 rounded-r-full bg-primary-600" />}
            </Link>
            <Link
              to="/platform/operator-tasks"
              className={`group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${isActive('/platform/operator-tasks')
                  ? 'bg-primary-50 text-primary-700 ring-1 ring-inset ring-primary-200'
                  : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                }`}
            >
              <ClipboardDocumentCheckIcon
                className={`h-5 w-5 shrink-0 transition-colors ${isActive('/platform/operator-tasks') ? 'text-primary-700' : 'text-gray-400 group-hover:text-gray-500'
                  }`}
              />
              Operator Tasks
              {isActive('/platform/operator-tasks') && <div className="absolute left-0 h-8 w-1 rounded-r-full bg-primary-600" />}
            </Link>
            <Link
              to="/platform/incident-closeouts"
              className={`group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${isActive('/platform/incident-closeouts')
                  ? 'bg-primary-50 text-primary-700 ring-1 ring-inset ring-primary-200'
                  : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                }`}
            >
              <LifebuoyIcon
                className={`h-5 w-5 shrink-0 transition-colors ${isActive('/platform/incident-closeouts') ? 'text-primary-700' : 'text-gray-400 group-hover:text-gray-500'
                  }`}
              />
              Incident Closeouts
              {isActive('/platform/incident-closeouts') && <div className="absolute left-0 h-8 w-1 rounded-r-full bg-primary-600" />}
            </Link>
          </>
        )}
      </nav>

      {/* Logout */}
      <div className="border-t border-gray-200 p-3">
        <button
          onClick={logout}
          className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-gray-600 hover:bg-red-50 hover:text-red-700 transition-colors"
        >
          <ArrowRightOnRectangleIcon className="h-5 w-5 shrink-0" />
          Logout
        </button>
      </div>
    </aside >
  );
}
