import { useCallback, useEffect, useState } from 'react';
import { PlusIcon, PencilIcon, TrashIcon } from '@heroicons/react/24/outline';
import { tenantService } from '@/services/tenantService';
import { useAuthStore } from '@/stores/authStore';
import { normalizeApiError } from '@/utils/errorHandling';
import { Badge } from '@/components/ui/Badge';
import { Pagination } from '@/components/ui/Pagination';
import { TenantFormModal } from '@/pages/tenants/TenantFormModal';
import type { Tenant, CreateTenantRequest, UpdateTenantRequest } from '@/types/tenant';

export function TenantListPage() {
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);

  // Modal state
  const [modalOpen, setModalOpen] = useState(false);
  const [editingTenant, setEditingTenant] = useState<Tenant | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  // Permission-aware UI
  const user = useAuthStore((s) => s.user);
  const canWrite = user?.permissions?.includes('wholesalers:write') ?? false;

  const fetchTenants = useCallback(async (p: number) => {
    setIsLoading(true);
    setLoadError(null);
    try {
      const res = await tenantService.getAll(p, 20);
      const payload = res.data.data;
      setTenants(payload.items);
      setTotalPages(payload.pagination.pages);
    } catch (err) {
      const msg = normalizeApiError(err);
      setLoadError(msg);
      setTenants([]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTenants(page);
  }, [page, fetchTenants]);

  // ── Create / Edit ──────────────────────────────────────────────────
  const openCreate = () => {
    setEditingTenant(null);
    setServerError(null);
    setModalOpen(true);
  };

  const openEdit = (tenant: Tenant) => {
    setEditingTenant(tenant);
    setServerError(null);
    setModalOpen(true);
  };

  const handleFormSubmit = async (
    data: CreateTenantRequest & UpdateTenantRequest
  ) => {
    setServerError(null);
    try {
      if (editingTenant) {
        await tenantService.update(editingTenant.id, {
          name: data.name,
          address: data.address || null,
          contact: data.contact || null,
          plan_type: data.plan_type || null,
        });
      } else {
        await tenantService.create({
          code: data.code,
          name: data.name,
          address: data.address || null,
          contact: data.contact || null,
          plan_type: data.plan_type || null,
        });
      }
      setModalOpen(false);
      fetchTenants(page);
    } catch (err) {
      setServerError(normalizeApiError(err));
    }
  };

  // ── Delete ─────────────────────────────────────────────────────────
  const handleDelete = async (tenant: Tenant) => {
    if (!window.confirm(`Delete tenant "${tenant.name}" (${tenant.code})? This cannot be undone.`)) {
      return;
    }
    setDeletingId(tenant.id);
    try {
      await tenantService.delete(tenant.id);
      fetchTenants(page);
    } catch (err) {
      alert(normalizeApiError(err));
    } finally {
      setDeletingId(null);
    }
  };

  // ── Render ─────────────────────────────────────────────────────────
  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Tenants</h1>
          <p className="mt-1 text-sm text-gray-500">
            Manage wholesaler tenants and their configurations.
          </p>
        </div>
        <button
          onClick={openCreate}
          disabled={!canWrite}
          className="btn-primary inline-flex items-center gap-1.5 disabled:opacity-50 disabled:cursor-not-allowed"
          title={canWrite ? 'Create a new tenant' : 'You need wholesalers:write permission'}
        >
          <PlusIcon className="h-4 w-4" />
          Create Tenant
        </button>
      </div>

      {/* Error Banner */}
      {loadError && (
        <div className="mt-4 rounded-md bg-red-50 p-4 text-sm text-red-700">
          {loadError}
        </div>
      )}

      {/* Table */}
      <div className="mt-6 overflow-hidden rounded-lg border border-gray-200 bg-white">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                Code
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                Name
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                Contact
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                Plan
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                Created
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {isLoading ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-sm text-gray-400">
                  Loading…
                </td>
              </tr>
            ) : tenants.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-sm text-gray-400">
                  {loadError ? 'Failed to load tenants.' : 'No tenants found.'}
                </td>
              </tr>
            ) : (
              tenants.map((t) => (
                <tr key={t.id} className="hover:bg-gray-50">
                  <td className="whitespace-nowrap px-4 py-3 text-sm font-mono font-medium text-gray-900">
                    {t.code}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-900">{t.name}</td>
                  <td className="px-4 py-3 text-sm text-gray-500">
                    {t.contact || '—'}
                  </td>
                  <td className="px-4 py-3 text-sm">
                    {t.plan_type ? (
                      <Badge variant={planBadgeVariant(t.plan_type)}>
                        {t.plan_type}
                      </Badge>
                    ) : (
                      <span className="text-gray-400">—</span>
                    )}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-sm text-gray-500">
                    {new Date(t.created_at).toLocaleDateString()}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-right">
                    <div className="inline-flex gap-1">
                      <button
                        onClick={() => openEdit(t)}
                        disabled={!canWrite}
                        className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600 disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:bg-transparent"
                        title={canWrite ? 'Edit' : 'wholesalers:write required'}
                      >
                        <PencilIcon className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => handleDelete(t)}
                        disabled={!canWrite || deletingId === t.id}
                        className="rounded p-1 text-gray-400 hover:bg-red-50 hover:text-red-600 disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:bg-transparent"
                        title={canWrite ? 'Delete' : 'wholesalers:write required'}
                      >
                        {deletingId === t.id ? (
                          <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-red-300 border-t-red-600" />
                        ) : (
                          <TrashIcon className="h-4 w-4" />
                        )}
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="mt-4">
        <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />
      </div>

      {/* Create / Edit Modal */}
      <TenantFormModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onSubmit={handleFormSubmit}
        tenant={editingTenant}
        serverError={serverError}
      />
    </div>
  );
}

// ── Helpers ────────────────────────────────────────────────────────────

function planBadgeVariant(plan: string): string {
  switch (plan) {
    case 'enterprise':
      return 'blue';
    case 'pro':
      return 'green';
    case 'basic':
      return 'yellow';
    default:
      return 'gray';
  }
}
