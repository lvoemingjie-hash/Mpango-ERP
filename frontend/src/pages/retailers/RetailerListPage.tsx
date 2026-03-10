import { useEffect, useState, useCallback } from 'react';
import { retailerService, type RetailerBindingItem } from '@/services/retailerService';
import { PageHeader } from '@/components/layout/PageHeader';
import { TableSkeleton } from '@/components/skeletons/TableSkeleton';
import { UsersIcon } from '@heroicons/react/24/outline';
import { EmptyState } from '@/components/ui/EmptyState';

export function RetailerListPage() {
  const [bindings, setBindings] = useState<RetailerBindingItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await retailerService.getBindings();
      setBindings(res.data.data.items);
    } catch {
      setError('Failed to load customers. Please try again.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div>
      <PageHeader
        title="Customers"
        description="View all retailers bound to your business."
        action={
          <button onClick={load} disabled={loading} className="btn-secondary text-sm">
            Refresh
          </button>
        }
      />

      {loading && <TableSkeleton />}

      {error && (
        <div className="mt-6 rounded-md bg-red-50 p-4">
          <div className="text-sm text-red-700">{error}</div>
        </div>
      )}

      {!loading && !error && bindings.length === 0 && (
        <EmptyState
          icon={UsersIcon}
          title="No customers yet"
          description="Retailers will appear here once they register using your invitation link."
        />
      )}

      {!loading && !error && bindings.length > 0 && (
        <div className="mt-6 overflow-hidden rounded-lg border border-gray-200 bg-white">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Name
                </th>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Phone
                </th>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Email
                </th>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Address
                </th>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Joined
                </th>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Status
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 bg-white">
              {bindings.map(({ binding, retailer }) => (
                <tr key={binding.id} className="hover:bg-gray-50">
                  <td className="whitespace-nowrap px-6 py-4 text-sm font-medium text-gray-900">
                    {retailer?.name || '—'}
                  </td>
                  <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-900">
                    {retailer?.phone || '—'}
                  </td>
                  <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-500">
                    {retailer?.email || '—'}
                  </td>
                  <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-500 truncate max-w-xs">
                    {retailer?.address || '—'}
                  </td>
                  <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-500">
                    {new Date(binding.created_at).toLocaleDateString()}
                  </td>
                  <td className="whitespace-nowrap px-6 py-4 text-sm">
                    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
                      binding.status === 'active' ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'
                    }`}>
                      {binding.status.charAt(0).toUpperCase() + binding.status.slice(1)}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
