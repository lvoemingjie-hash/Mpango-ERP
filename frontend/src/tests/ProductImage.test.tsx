import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ProductImage } from '@/components/catalog/ProductImage';
import { useAuthStore } from '@/stores/authStore';
import { api } from '@/services/api';
import type { ProductImageMetadata } from '@/services/productImageService';

vi.mock('@/services/api', () => ({ api: { get: vi.fn() } }));
const meta: ProductImageMetadata = {
  version: '22222222-2222-4222-8222-222222222222', revision: 1,
  thumb_path: '/catalog-products/11111111-1111-4111-8111-111111111111/image/22222222-2222-4222-8222-222222222222/thumb',
  detail_path: '/catalog-products/11111111-1111-4111-8111-111111111111/image/22222222-2222-4222-8222-222222222222/detail',
  width: 100, height: 80,
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal('IntersectionObserver', undefined);
  URL.createObjectURL = vi.fn(() => 'blob:local-image');
  URL.revokeObjectURL = vi.fn();
  useAuthStore.setState({ accessToken: 'component-fixture', tenantCode: 'tenant-one', user: null });
  vi.mocked(api.get).mockResolvedValue({ data: new Blob(['webp-fixture'], { type: 'image/webp' }) });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('private product image view', () => {
  it('uses authenticated blob reads, never a direct public src', async () => {
    render(<ProductImage image={meta} name="Rice pack" />);
    await waitFor(() => expect(screen.getByAltText('Rice pack')).toHaveAttribute('src', 'blob:local-image'));
    expect(api.get).toHaveBeenCalledWith(meta.thumb_path, expect.objectContaining({ responseType: 'blob', signal: expect.any(AbortSignal) }));
  });
  it('has a placeholder without requesting absent images', () => {
    render(<ProductImage image={null} name="Rice pack" />);
    expect(screen.getByText('No product image')).toBeInTheDocument();
    expect(api.get).not.toHaveBeenCalled();
  });
  it('deduplicates current-page instances and releases only the last lease', async () => {
    const first = render(<ProductImage image={meta} name="First" />);
    const second = render(<ProductImage image={meta} name="Second" />);
    await waitFor(() => expect(screen.getByAltText('Second')).toBeInTheDocument());
    expect(api.get).toHaveBeenCalledTimes(1);
    first.unmount(); expect(URL.revokeObjectURL).not.toHaveBeenCalled();
    second.unmount(); expect(URL.revokeObjectURL).toHaveBeenCalledTimes(1);
  });
  it('releases cached pixels on logout and rejects a late old-session response', async () => {
    let complete!: (value: unknown) => void;
    vi.mocked(api.get).mockImplementation(() => new Promise(resolve => { complete = resolve; }));
    render(<ProductImage image={meta} name="Rice pack" />);
    await waitFor(() => expect(api.get).toHaveBeenCalledTimes(1));
    act(() => useAuthStore.setState({ accessToken: null, tenantCode: null }));
    await act(async () => { complete({ data: new Blob(['late'], { type: 'image/webp' }) }); });
    expect(screen.queryByAltText('Rice pack')).not.toBeInTheDocument();
    expect(URL.createObjectURL).not.toHaveBeenCalled();
  });
  it('rejects wrong MIME and oversized thumbnails', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: new Blob(['not-webp'], { type: 'image/svg+xml' }) });
    const view = render(<ProductImage image={meta} name="Rice pack" />);
    await waitFor(() => expect(api.get).toHaveBeenCalledTimes(1));
    await act(async () => {});
    expect(screen.queryByAltText('Rice pack')).not.toBeInTheDocument();
    view.unmount();
    vi.mocked(api.get).mockResolvedValue({ data: new Blob([new Uint8Array(80 * 1024 + 1)], { type: 'image/webp' }) });
    render(<ProductImage image={meta} name="Too big" />);
    await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2));
    await act(async () => {});
    expect(screen.queryByAltText('Too big')).not.toBeInTheDocument();
  });
});
