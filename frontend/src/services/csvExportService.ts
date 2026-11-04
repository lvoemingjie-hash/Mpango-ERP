import { api } from '@/services/api';

const EXPORT_PATHS = {
  orders: '/orders/export',
  inventory: '/inventory/export',
} as const;

export type CsvExportKind = keyof typeof EXPORT_PATHS;

export async function fetchCsvExport(kind: CsvExportKind, signal: AbortSignal): Promise<Blob> {
  if (!Object.prototype.hasOwnProperty.call(EXPORT_PATHS, kind)) {
    throw new Error('INVALID_CSV_EXPORT');
  }
  const response = await api.get<Blob>(EXPORT_PATHS[kind], {
    params: { format: 'csv' },
    responseType: 'blob',
    signal,
    timeout: 60_000,
  });
  const contentType = String(response.headers['content-type'] ?? '').split(';')[0].trim().toLowerCase();
  if (response.status !== 200 || contentType !== 'text/csv'
      || !(response.data instanceof Blob) || response.data.size === 0) {
    throw new Error('INVALID_CSV_RESPONSE');
  }
  return response.data;
}
