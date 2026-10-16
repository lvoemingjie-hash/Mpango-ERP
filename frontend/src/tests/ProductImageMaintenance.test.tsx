import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ProductImageMaintenance } from '@/components/catalog/ProductImage';
import { productImageService } from '@/services/productImageService';

vi.mock('@/services/productImageService', () => ({
  productImageService: { upload: vi.fn(), remove: vi.fn(), readState: vi.fn() },
  leaseProductImage: vi.fn(() => { throw new Error('not rendering file bytes in maintenance tests'); }),
}));
beforeEach(() => { vi.clearAllMocks(); });
afterEach(cleanup);
describe('explicit image revision maintenance', () => {
  it('uses the tombstone revision for re-upload, not zero', async () => {
    vi.mocked(productImageService.upload).mockResolvedValue({ image_revision: 5, image: null });
    render(<ProductImageMaintenance productId="product" initial={{ image_revision: 4, image: null }} onChanged={vi.fn()} />);
    const file = new File(['fixture'], 'photo.png', { type: 'image/png' });
    fireEvent.change(screen.getByLabelText('Upload product image'), { target: { files: [file] } });
    await waitFor(() => expect(productImageService.upload).toHaveBeenCalledWith('product', 4, file));
    expect(await screen.findByText('Image saved.')).toBeInTheDocument();
  });
  it('does not retry an unknown write; explicit status refresh restores the tombstone', async () => {
    vi.mocked(productImageService.upload).mockRejectedValue(new Error('connection ended'));
    vi.mocked(productImageService.readState).mockResolvedValue({ image_revision: 7, image: null });
    render(<ProductImageMaintenance productId="product" initial={{ image_revision: 4, image: null }} onChanged={vi.fn()} />);
    const file = new File(['fixture'], 'photo.png', { type: 'image/png' });
    fireEvent.change(screen.getByLabelText('Upload product image'), { target: { files: [file] } });
    await screen.findByText(/result is unknown/);
    expect(screen.getByLabelText('Upload product image')).toBeDisabled();
    expect(productImageService.upload).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByText('Refresh image status'));
    await waitFor(() => expect(screen.getByLabelText('Upload product image')).not.toBeDisabled());
    vi.mocked(productImageService.upload).mockResolvedValue({ image_revision: 8, image: null });
    fireEvent.change(screen.getByLabelText('Upload product image'), { target: { files: [file] } });
    await waitFor(() => expect(productImageService.upload).toHaveBeenLastCalledWith('product', 7, file));
  });
  it('rejects unsupported or oversized input before sending bytes', () => {
    render(<ProductImageMaintenance productId="product" initial={{ image_revision: 0, image: null }} onChanged={vi.fn()} />);
    fireEvent.change(screen.getByLabelText('Upload product image'), { target: { files: [new File(['<svg/>'], 'bad.svg', { type: 'image/svg+xml' })] } });
    expect(productImageService.upload).not.toHaveBeenCalled();
    expect(screen.getByText(/no larger than 5 MiB/)).toBeInTheDocument();
  });
});
