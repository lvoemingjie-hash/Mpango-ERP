import { useEffect, useRef, useState } from 'react';
import { fetchCsvExport } from '@/services/csvExportService';
import type { CsvExportKind } from '@/services/csvExportService';
import { useAuthStore } from '@/stores/authStore';
import { can } from '@/utils/permissions';

export function CsvExportButton({ kind }: { kind: CsvExportKind }) {
  const user = useAuthStore((state) => state.user);
  const generation = useAuthStore((state) => state.sessionGeneration);
  const allowed = Boolean(user?.tenant_id && user?.tenant_schema) && can(user, 'exports:create');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const active = useRef<AbortController | null>(null);
  const urls = useRef(new Map<string, number>());

  useEffect(() => {
    setBusy(false);
    setError(null);
    return () => {
      active.current?.abort();
      active.current = null;
      urls.current.forEach((timer, url) => {
        window.clearTimeout(timer);
        URL.revokeObjectURL(url);
      });
      urls.current.clear();
    };
  }, [generation, user?.id, user?.tenant_id, user?.tenant_schema, allowed, kind]);

  if (!allowed) return null;

  const cancel = () => {
    active.current?.abort();
    active.current = null;
    setBusy(false);
  };

  const download = async () => {
    if (active.current) return;
    const owner = useAuthStore.getState();
    const identity = owner.user;
    if (!identity?.tenant_id || !identity.tenant_schema || !can(identity, 'exports:create')) return;
    const controller = new AbortController();
    active.current = controller;
    setBusy(true);
    setError(null);
    const owns = () => {
      const current = useAuthStore.getState();
      return active.current === controller && !controller.signal.aborted
        && current.sessionGeneration === owner.sessionGeneration
        && current.user?.id === identity.id
        && current.user?.tenant_id === identity.tenant_id
        && current.user?.tenant_schema === identity.tenant_schema
        && can(current.user, 'exports:create');
    };
    try {
      const blob = await fetchCsvExport(kind, controller.signal);
      if (!owns()) return;
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      try {
        anchor.href = url;
        anchor.download = kind === 'orders' ? 'orders.csv' : 'inventory.csv';
        document.body.appendChild(anchor);
        anchor.click();
      } finally {
        anchor.remove();
        // Let the browser consume the completed Blob before releasing it.
        const timer = window.setTimeout(() => {
          URL.revokeObjectURL(url);
          urls.current.delete(url);
        }, 1000);
        urls.current.set(url, timer);
      }
    } catch {
      if (owns()) setError('Could not download CSV. Check your access and connection, then try again.');
    } finally {
      if (active.current === controller) {
        active.current = null;
        setBusy(false);
      }
    }
  };

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-2">
        <button type="button" className="btn-secondary text-sm" onClick={download}
          disabled={busy} aria-busy={busy} title={`Download all ${kind}, not just this page`}>
          {busy ? 'Preparing CSV...' : 'Export CSV'}
        </button>
        {busy && <button type="button" onClick={cancel} className="text-sm text-gray-600 underline">Cancel export</button>}
      </div>
      {error && <p role="alert" className="max-w-xs text-xs text-red-700">{error}</p>}
    </div>
  );
}
