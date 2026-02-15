import { Link, useLocation } from 'react-router-dom';
import {
  HomeIcon,
  BuildingOfficeIcon,
  UsersIcon,
  Cog6ToothIcon,
  ArrowRightOnRectangleIcon,
  ClipboardDocumentListIcon,
  CubeIcon,
} from '@heroicons/react/24/outline';
import { useAuthStore } from '@/stores/authStore';

interface NavItem {
  label: string;
  path: string;
  icon: React.ComponentType<React.SVGProps<SVGSVGElement>>;
}

const navItems: NavItem[] = [
  { label: 'Dashboard', path: '/', icon: HomeIcon },
  { label: 'Orders', path: '/orders', icon: ClipboardDocumentListIcon },
  { label: 'Inventory', path: '/inventory', icon: CubeIcon },
  { label: 'Tenants', path: '/tenants', icon: BuildingOfficeIcon },
  { label: 'Users', path: '/users', icon: UsersIcon },
  { label: 'Settings', path: '/settings', icon: Cog6ToothIcon },
];

export function Sidebar() {
  const location = useLocation();
  const logout = useAuthStore((s) => s.logout);

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
      <nav className="flex-1 space-y-1 px-3 py-4">
        {navItems.map((item) => {
          const active = isActive(item.path);
          return (
            <Link
              key={item.path}
              to={item.path}
              className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                active
                  ? 'bg-primary-50 text-primary-700'
                  : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
              }`}
            >
              <item.icon className="h-5 w-5 shrink-0" />
              {item.label}
            </Link>
          );
        })}
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
    </aside>
  );
}
