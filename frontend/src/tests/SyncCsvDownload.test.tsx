import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { CsvExportButton } from '@/components/ui/CsvExportButton';
import { OrderListPage } from '@/pages/orders/OrderListPage';
import { InventoryPage } from '@/pages/inventory/InventoryPage';
import * as csvService from '@/services/csvExportService';
import { api } from '@/services/api';
import { useAuthStore } from '@/stores/authStore';
import type { CurrentUserData } from '@/types/auth';

vi.mock('@/services/orderService', () => ({
  orderService: { getAll: vi.fn().mockResolvedValue({ data: { data: { items: [] } } }) },
}));
vi.mock('@/services/inventoryService', () => ({
  inventoryService: { getStocks: vi.fn().mockResolvedValue({ data: { data: { items: [] } } }) },
}));

const nativeURL = URL;
const profile = (permissions = ['exports:create']): CurrentUserData => ({
  id: 'csv-user-a', email: null, full_name: 'CSV user', tenant_id: 'csv-tenant-a',
  tenant_schema: 't_csv_a', roles: ['user'], permissions,
});
const blob = () => new Blob(['\ufeffOrder ID,Notes\r\n1,safe\r\n'], { type: 'text/csv' });
const saved: Array<{ href: string; filename: string }> = [];
const createURL = vi.fn(() => 'blob:csv-download');
const revokeURL = vi.fn();

beforeEach(() => {
  saved.length = 0;
  createURL.mockClear();
  revokeURL.mockClear();
  vi.stubGlobal('URL', Object.assign(class extends nativeURL {}, {
    createObjectURL: createURL, revokeObjectURL: revokeURL,
  }));
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
    saved.push({ href: this.href, filename: this.download });
  });
  useAuthStore.setState({ user: profile(), sessionGeneration: 100 });
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function pending<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

describe('authenticated synchronous CSV service', () => {
  it.each(['orders', 'inventory'] as const)('uses the existing API client and fixed %s endpoint', async (kind) => {
    const data = blob();
    const get = vi.spyOn(api, 'get').mockResolvedValue({ status: 200, headers: { 'content-type': 'text/csv; charset=utf-8' }, data });
    const controller = new AbortController();
    expect(await csvService.fetchCsvExport(kind, controller.signal)).toBe(data);
    expect(get).toHaveBeenCalledOnce();
    expect(get).toHaveBeenCalledWith(`/${kind}/export`, {
      params: { format: 'csv' }, responseType: 'blob', signal: controller.signal, timeout: 60_000,
    });
  });

  it.each(['json', 'html', 'empty', 'not-blob', 'non-200'])('rejects a %s response instead of downloading it', async (mode) => {
    const response = { status: mode === 'non-200' ? 403 : 200,
      headers: { 'content-type': mode === 'json' ? 'application/json' : mode === 'html' ? 'text/html' : 'text/csv' },
      data: mode === 'empty' ? new Blob([]) : mode === 'not-blob' ? 'not a blob' : blob() };
    vi.spyOn(api, 'get').mockResolvedValue(response);
    await expect(csvService.fetchCsvExport('orders', new AbortController().signal)).rejects.toThrow('INVALID_CSV_RESPONSE');
    expect(createURL).not.toHaveBeenCalled();
  });

  it('does not create an arbitrary path from an invalid kind', async () => {
    const get = vi.spyOn(api, 'get');
    await expect(csvService.fetchCsvExport('../foreign' as csvService.CsvExportKind, new AbortController().signal))
      .rejects.toThrow('INVALID_CSV_EXPORT');
    expect(get).not.toHaveBeenCalled();
  });
});

describe('CSV entry and resource ownership', () => {
  it.each(['orders', 'inventory'] as const)('downloads %s once with a controlled filename and releases its URL', async (kind) => {
    const request = vi.spyOn(csvService, 'fetchCsvExport').mockResolvedValue(blob());
    const view = render(<CsvExportButton kind={kind} />);
    fireEvent.click(screen.getByRole('button', { name: 'Export CSV' }));
    await waitFor(() => expect(saved).toHaveLength(1));
    expect(request).toHaveBeenCalledOnce();
    expect(saved[0]).toEqual({ href: 'blob:csv-download', filename: `${kind}.csv` });
    expect(document.querySelector('a[download]')).toBeNull();
    view.unmount();
    expect(revokeURL).toHaveBeenCalledOnce();
    expect(revokeURL).toHaveBeenCalledWith('blob:csv-download');
  });

  it('revokes a completed Blob after the browser has consumed the click', async () => {
    vi.useFakeTimers();
    vi.spyOn(csvService, 'fetchCsvExport').mockResolvedValue(blob());
    render(<CsvExportButton kind="orders" />);
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Export CSV' })); });
    expect(saved).toHaveLength(1);
    expect(revokeURL).not.toHaveBeenCalled();
    act(() => { vi.advanceTimersByTime(1000); });
    expect(revokeURL).toHaveBeenCalledOnce();
    expect(revokeURL).toHaveBeenCalledWith('blob:csv-download');
  });

  it.each(['none', 'read-only', 'revoked', 'no-tenant'])('does not expose export to %s authority', (mode) => {
    const user = mode === 'none' ? null : profile(mode === 'read-only' ? ['orders:read', 'inventory:read'] : ['exports:create']);
    if (user && mode === 'revoked') user.staff_state = 'revoked';
    if (user && mode === 'no-tenant') user.tenant_id = null;
    useAuthStore.setState({ user });
    const request = vi.spyOn(csvService, 'fetchCsvExport');
    render(<CsvExportButton kind="orders" />);
    expect(screen.queryByRole('button', { name: 'Export CSV' })).not.toBeInTheDocument();
    expect(request).not.toHaveBeenCalled();
  });

  it('blocks duplicate clicks and cancels without a late download', async () => {
    const result = pending<Blob>();
    const request = vi.spyOn(csvService, 'fetchCsvExport').mockReturnValue(result.promise);
    render(<CsvExportButton kind="orders" />);
    const button = screen.getByRole('button', { name: 'Export CSV' });
    fireEvent.click(button);
    fireEvent.click(button);
    expect(request).toHaveBeenCalledOnce();
    expect(screen.getByRole('button', { name: 'Preparing CSV...' })).toBeDisabled();
    const signal = request.mock.calls[0][1];
    fireEvent.click(screen.getByRole('button', { name: 'Cancel export' }));
    expect(signal.aborted).toBe(true);
    await act(async () => { result.resolve(blob()); });
    expect(createURL).not.toHaveBeenCalled();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it.each(['session', 'tenant', 'permission', 'kind', 'unmount'])('suppresses an old download after %s changes', async (change) => {
    const result = pending<Blob>();
    const request = vi.spyOn(csvService, 'fetchCsvExport').mockReturnValue(result.promise);
    const view = render(<CsvExportButton kind="orders" />);
    fireEvent.click(screen.getByRole('button', { name: 'Export CSV' }));
    const signal = request.mock.calls[0][1];
    act(() => {
      if (change === 'session') useAuthStore.setState({ sessionGeneration: 101 });
      else if (change === 'tenant') useAuthStore.setState({ user: { ...profile(), tenant_id: 'tenant-b', tenant_schema: 't_b' } });
      else if (change === 'permission') useAuthStore.setState({ user: profile([]) });
      else if (change === 'kind') view.rerender(<CsvExportButton kind="inventory" />);
      else view.unmount();
    });
    expect(signal.aborted).toBe(true);
    await act(async () => { result.resolve(blob()); });
    expect(createURL).not.toHaveBeenCalled();
  });

  it.each([401, 403, 500])('keeps a %s failure out of downloads and offers a neutral retryable error', async (status) => {
    vi.spyOn(csvService, 'fetchCsvExport').mockRejectedValue(new Error(`HTTP ${status}`));
    render(<CsvExportButton kind="orders" />);
    fireEvent.click(screen.getByRole('button', { name: 'Export CSV' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not download CSV');
    expect(createURL).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Export CSV' })).toBeEnabled();
  });
});

describe('Sales and Stock entry integration', () => {
  it.each([['Sales', OrderListPage, 'orders'], ['Stock', InventoryPage, 'inventory']] as const)
    ('wires %s to its own synchronous export', async (_label, Page, kind) => {
      const request = vi.spyOn(csvService, 'fetchCsvExport').mockResolvedValue(blob());
      render(<MemoryRouter><Page /></MemoryRouter>);
      fireEvent.click(screen.getByRole('button', { name: 'Export CSV' }));
      await waitFor(() => expect(saved).toHaveLength(1));
      expect(request.mock.calls[0][0]).toBe(kind);
      expect(screen.getByRole('button', { name: 'Refresh' })).toBeInTheDocument();
    });

  it.each([['Sales', OrderListPage], ['Stock', InventoryPage]] as const)('keeps %s usable without the export permission', async (_label, Page) => {
    useAuthStore.setState({ user: profile(['orders:read', 'inventory:read']) });
    render(<MemoryRouter><Page /></MemoryRouter>);
    expect(screen.queryByRole('button', { name: 'Export CSV' })).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Refresh' })).toBeEnabled());
  });
});
