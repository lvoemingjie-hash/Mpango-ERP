/**
 * PlatformAuditEventsPage — read-only audit event list view.
 *
 * Displays platform audit events with pagination.
 * Metadata is never displayed as raw text.
 * No write actions.
 */
import { useEffect, useState } from 'react';
import { usePlatformStore } from '@/stores/platformStore';
import { platformService } from '@/services/platformApi';
import { PlatformAuditEventRow } from '@/components/platform/PlatformAuditEventRow';
import { PlatformErrorState } from '@/components/platform/PlatformErrorState';
import { EmptyState } from '@/components/ui/EmptyState';
import { Skeleton } from '@/components/ui/Skeleton';

const PAGE_SIZE = 20;

export function PlatformAuditEventsPage() {
  const {
    auditEvents,
    auditTotal,
    auditLoading,
    auditError,
    setAuditEvents,
    setAuditLoading,
    setAuditError,
  } = usePlatformStore();

  const [offset, setOffset] = useState(0);

  const fetchEvents = (newOffset = 0) => {
    setAuditLoading(true);
    setAuditError(null);
    platformService
      .listAuditEvents(PAGE_SIZE, newOffset)
      .then((res) => {
        const data = res.data?.data ?? res.data;
        setAuditEvents(data.items ?? [], data.total ?? 0);
        setOffset(newOffset);
      })
      .catch((err) => setAuditError(err.message ?? 'Failed to load audit events'));
  };

  useEffect(() => {
    fetchEvents(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const hasPrev = offset > 0;
  const hasNext = offset + PAGE_SIZE < auditTotal;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Audit Events</h1>
        <p className="mt-1 text-sm text-gray-500">
          Read-only platform audit trail. Redacted metadata is not displayed.
        </p>
      </div>

      {auditError ? (
        <PlatformErrorState message={auditError} onRetry={() => fetchEvents(offset)} />
      ) : auditLoading ? (
        <div className="space-y-2">
          {[1, 2, 3, 4, 5].map((i) => (
            <Skeleton key={i} className="h-12 w-full rounded" />
          ))}
        </div>
      ) : auditEvents.length === 0 ? (
        <EmptyState
          title="No audit events"
          description="No platform audit events have been recorded yet."
        />
      ) : (
        <>
          <p className="text-sm text-gray-500">
            Showing {offset + 1}–{Math.min(offset + PAGE_SIZE, auditTotal)} of {auditTotal} events
          </p>
          <div className="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                    Action
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                    Actor
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                    Scope
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                    Result
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                    Time
                  </th>
                </tr>
              </thead>
              <tbody>
                {auditEvents.map((event) => (
                  <PlatformAuditEventRow key={event.event_id} event={event} />
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="flex items-center justify-between">
            <button
              onClick={() => fetchEvents(offset - PAGE_SIZE)}
              disabled={!hasPrev}
              className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              ← Previous
            </button>
            <span className="text-sm text-gray-500">
              Page {Math.floor(offset / PAGE_SIZE) + 1} of {Math.ceil(auditTotal / PAGE_SIZE)}
            </span>
            <button
              onClick={() => fetchEvents(offset + PAGE_SIZE)}
              disabled={!hasNext}
              className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Next →
            </button>
          </div>
        </>
      )}
    </div>
  );
}
