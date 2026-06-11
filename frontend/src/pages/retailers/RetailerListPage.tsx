import { useEffect, useState, useCallback } from 'react';
import { retailerService, type RetailerWithBinding } from '@/services/retailerService';
import { PageHeader } from '@/components/layout/PageHeader';
import { TableSkeleton } from '@/components/skeletons/TableSkeleton';
import { UsersIcon } from '@heroicons/react/24/outline';
import { EmptyState } from '@/components/ui/EmptyState';
import { Pagination } from '@/components/ui/Pagination';

export function RetailerListPage() {
  const [retailers, setRetailers] = useState<RetailerWithBinding[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Pagination state
  const [page, setPage] = useState(1);
  const [size] = useState(20);
  const [total, setTotal] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await retailerService.getAll(page, size);
      setRetailers(res.data.data.items);
      setTotal(res.data.data.pagination.total);
    } catch {
      setError('Could not load customers. Check your connection and try again. If the problem persists, contact support.');
    } finally {
      setLoading(false);
    }
  }, [page, size]);

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
        <div className="mt-6 flex items-center gap-3 rounded-md bg-red-50 px-4 py-3 text-sm text-red-700">
          <span>{error}</span>
          <button
            onClick={load}
            className="inline-flex items-center gap-1 rounded-md bg-red-100 px-2 py-1 text-xs font-medium text-red-800 hover:bg-red-200"
          >
            Retry
          </button>
        </div>
      )}

      {!loading && !error && retailers.length === 0 && (
        <EmptyState
          icon={UsersIcon}
          title="No customers yet"
          description="Customers will appear here once they register using your invitation link. Share your business link to start building your customer base."
        />
      )}

      {!loading && !error && retailers.length > 0 && (
        <div className="mt-6 flex flex-col gap-4">
          <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
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
                {retailers.map(({ retailer, binding_status, bound_at }) => (
                  <tr key={retailer.id} className="hover:bg-gray-50">
                    <td className="whitespace-nowrap px-6 py-4 text-sm font-medium text-gray-900">
                      {retailer.name || '—'}
                    </td>
                    <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-900">
                      {retailer.phone || '—'}
                    </td>
                    <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-500">
                      {retailer.email || '—'}
                    </td>
                    <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-500 truncate max-w-xs">
                      {retailer.address || '—'}
                    </td>
                    <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-500">
                      {new Date(bound_at).toLocaleDateString()}
                    </td>
                    <td className="whitespace-nowrap px-6 py-4 text-sm">
                      <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
                        binding_status === 'active' ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'
                      }`}>
                        {binding_status.charAt(0).toUpperCase() + binding_status.slice(1)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <Pagination
            page={page}
            totalPages={Math.ceil(total / size)}
            onPageChange={setPage}
          />
        </div>
      )}
    </div>
  );
}
