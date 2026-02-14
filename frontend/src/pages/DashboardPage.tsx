import { useAuthStore } from '@/stores/authStore';

/**
 * Placeholder dashboard — proves login + layout work.
 * Content will be built in later phases.
 */
export function DashboardPage() {
  const user = useAuthStore((s) => s.user);

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
      <p className="mt-1 text-sm text-gray-500">
        Welcome back{user?.full_name ? `, ${user.full_name}` : ''}.
      </p>

      {user && (
        <div className="mt-6 grid max-w-md gap-4">
          <div className="rounded-lg border border-gray-200 bg-white p-4">
            <p className="text-xs font-medium uppercase tracking-wider text-gray-400">
              Session Info
            </p>
            <dl className="mt-3 space-y-2 text-sm">
              <div className="flex justify-between">
                <dt className="text-gray-500">Email</dt>
                <dd className="font-medium text-gray-900">{user.email}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-500">Roles</dt>
                <dd className="font-medium text-gray-900">
                  {user.roles.join(', ') || '—'}
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-500">Tenant</dt>
                <dd className="font-mono text-xs text-gray-700">
                  {user.tenant_schema}
                </dd>
              </div>
            </dl>
          </div>
        </div>
      )}
    </div>
  );
}
