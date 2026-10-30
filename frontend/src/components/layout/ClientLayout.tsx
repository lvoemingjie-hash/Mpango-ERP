import { Outlet, Link, useLocation, useNavigate } from 'react-router-dom';
import { useEffect, useRef, useState } from 'react';
import {
  ShoppingBagIcon,
  ClipboardDocumentListIcon,
  BanknotesIcon,
  ScaleIcon,
  ArrowRightOnRectangleIcon,
} from '@heroicons/react/24/outline';
import { useAuthStore } from '@/stores/authStore';
import { getClientPortalContext } from '@/services/partyContextService';
import { isClientPortalContext, type ClientPortalContext } from '@/types/partyContext';

const navItems = [
  { path: '/client', icon: ShoppingBagIcon, label: 'Products' },
  { path: '/client/orders', icon: ClipboardDocumentListIcon, label: 'Orders' },
  { path: '/client/payments', icon: BanknotesIcon, label: 'Payments' },
  { path: '/client/finance', icon: ScaleIcon, label: 'Finance' },
];

export function ClientLayout() {
  const auth = useAuthStore();
  const scope = portalScope(auth);
  return <CurrentClientLayout key={scope} scope={scope} />;
}

function portalScope(s: ReturnType<typeof useAuthStore.getState>) {
  return JSON.stringify([s.user?.id, s.user?.tenant_id, s.user?.tenant_schema, s.sessionGeneration,
    s.retailerPortalCode, s.tenantCode, s.user?.roles, s.user?.permissions, s.user?.authz_revision]);
}

function CurrentClientLayout({ scope }: { scope: string }) {
  const location = useLocation();
  const navigate = useNavigate();
  const logout = useAuthStore((s) => s.logout);
  const user = useAuthStore((s) => s.user);
  const portal = useAuthStore(s => s.retailerPortalCode || s.tenantCode);
  const mounted = useRef(false);
  const attempt = useRef(0);
  const [revision, setRevision] = useState(0);
  const [identity, setIdentity] = useState<ClientPortalContext | null>(null);
  const [loading, setLoading] = useState(true);
  const [unavailable, setUnavailable] = useState(false);
  useEffect(() => {
    mounted.current = true;
    const sequence = ++attempt.current;
    const request = new AbortController();
    const current = () => mounted.current && sequence === attempt.current && !request.signal.aborted
      && Boolean(useAuthStore.getState().accessToken) && scope === portalScope(useAuthStore.getState());
    setIdentity(null); setLoading(true); setUnavailable(false);
    if (!useAuthStore.getState().accessToken || !useAuthStore.getState().user) {
      setLoading(false); setUnavailable(true);
      return () => { mounted.current = false; request.abort(); };
    }
    void (async () => {
      try {
        if (!useAuthStore.getState().accessToken || !useAuthStore.getState().user) throw new Error('No current identity');
        const response = await getClientPortalContext(request.signal);
        if (!current()) return;
        if (response.success !== true) throw new Error('Unverified response');
        const data: unknown = response.data;
        const user = useAuthStore.getState().user;
        if (!isClientPortalContext(data) || data.context.user_id !== user?.id || data.context.tenant_id !== user?.tenant_id
          || data.supplier.id !== user?.tenant_id) throw new Error('Portal identity mismatch');
        setIdentity(data);
      } catch {
        if (current()) { setIdentity(null); setUnavailable(true); }
      } finally {
        if (current()) setLoading(false);
      }
    })();
    return () => { mounted.current = false; request.abort(); };
  }, [scope, revision]);

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
              <span className="max-w-40 truncate text-sm text-gray-500" title={user.full_name}>
                {user.full_name}
              </span>
            )}
            <button
              onClick={handleLogout}
              className="rounded-lg p-2 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
              title="Sign out" aria-label="Sign out"
            >
              <ArrowRightOnRectangleIcon className="h-5 w-5" />
            </button>
          </div>
        </div>
        <section aria-label="Current business identity" className="mx-auto max-w-lg px-4 pb-2 text-xs text-gray-600 break-words space-y-1">
          {loading && <p role="status">Checking current business identity…</p>}
          {unavailable && <p role="alert">Business identity not verified. Your saved portal or login name is not verification.</p>}
          {identity && <>
            <p>Supplier: {identity.supplier.name_resolution === 'RESOLVED' ? identity.supplier.name : 'Supplier name not verified'} · {identity.supplier.code}</p>
            <p>Retailer: {identity.retailer.name_resolution === 'RESOLVED' ? identity.retailer.name : 'Retailer name not verified'}</p>
            <p className="break-all">Active binding: {identity.binding.id} · Observed at: {identity.observed_at}</p>
          </>}
          <p>Saved portal hint: {portal || 'not available'} · Signed in as {user?.full_name || user?.email || 'identity unavailable'}</p>
          <button onClick={() => setRevision(v => v + 1)} disabled={loading} className="underline">Refresh business identity</button>
        </section>
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
                aria-current={isActive ? 'page' : undefined}
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
