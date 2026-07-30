import { Outlet, Link, useLocation, useNavigate } from 'react-router-dom';
import {
  ShoppingBagIcon,
  ClipboardDocumentListIcon,
  BanknotesIcon,
  ScaleIcon,
  ArrowRightOnRectangleIcon,
} from '@heroicons/react/24/outline';
import { useAuthStore } from '@/stores/authStore';

const navItems = [
  { path: '/client', icon: ShoppingBagIcon, label: 'Products' },
  { path: '/client/orders', icon: ClipboardDocumentListIcon, label: 'Orders' },
  { path: '/client/payments', icon: BanknotesIcon, label: 'Payments' },
  { path: '/client/finance', icon: ScaleIcon, label: 'Finance' },
];

export function ClientLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const logout = useAuthStore((s) => s.logout);
  const user = useAuthStore((s) => s.user);

  const handleLogout = () => {
    logout();
    navigate('/client/login', { replace: true });
  };

  return (
    <div className="flex min-h-screen flex-col bg-gray-50">
      {/* Top Header */}
      <header className="sticky top-0 z-30 border-b border-gray-200 bg-white">
        <div className="mx-auto flex h-14 max-w-lg items-center justify-between px-4">
          <Link to="/client" className="text-lg font-bold text-primary-600">
            Mpango
          </Link>
          <div className="flex items-center gap-3">
            {user?.full_name && (
              <span className="text-sm text-gray-500 hidden sm:inline">
                {user.full_name}
              </span>
            )}
            <button
              onClick={handleLogout}
              className="rounded-lg p-2 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
              title="Sign out"
            >
              <ArrowRightOnRectangleIcon className="h-5 w-5" />
            </button>
          </div>
        </div>
      </header>

      {/* Content */}
      <main className="mx-auto w-full max-w-lg flex-1 px-4 py-4">
        <Outlet />
      </main>

      {/* Bottom Navigation — mobile-friendly */}
      <nav className="sticky bottom-0 z-30 border-t border-gray-200 bg-white">
        <div className="mx-auto flex max-w-lg">
          {navItems.map((item) => {
            const isActive =
              item.path === '/client'
                ? location.pathname === '/client'
                : location.pathname.startsWith(item.path);

            return (
              <Link
                key={item.path}
                to={item.path}
                className={`flex flex-1 flex-col items-center gap-0.5 py-2 text-xs font-medium transition-colors ${
                  isActive
                    ? 'text-primary-600'
                    : 'text-gray-400 hover:text-gray-600'
                }`}
              >
                <item.icon className="h-6 w-6" />
                {item.label}
              </Link>
            );
          })}
        </div>
      </nav>
    </div>
  );
}
