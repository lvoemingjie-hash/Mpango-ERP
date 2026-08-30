import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { SKUFormModal } from '@/pages/skus/SKUFormModal';
import { AddSellableUnitModal } from '@/pages/skus/AddSellableUnitModal';
import { catalogProductService } from '@/services/catalogProductService';

vi.mock('@/services/catalogProductService', () => ({
  catalogProductService: {
    create: vi.fn(),
    update: vi.fn(),
    addSellableUnit: vi.fn(),
    updateSellableUnit: vi.fn(),
  },
}));

vi.mock('@/stores/toastStore', () => ({
  useToastStore: {
    getState: () => ({ addToast: vi.fn() }),
  },
}));

describe('SKU catalog identity vertical slice', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('creates one product with multiple independently identified packaging options', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    const onSuccess = vi.fn();
    vi.mocked(catalogProductService.create).mockResolvedValue({} as never);

    render(
      <SKUFormModal
        isOpen
        onClose={onClose}
        onSuccess={onSuccess}
        product={null}
      />
    );

    await user.type(screen.getByLabelText('Product Name'), 'Premium Rice');
    await user.type(screen.getByLabelText('SKU Code'), 'RICE-EACH-1');
    await user.clear(screen.getByLabelText('Unit'));
    await user.type(screen.getByLabelText('Unit'), 'bag');
    await user.click(screen.getByRole('button', { name: 'Add packaging' }));

    const codes = screen.getAllByLabelText('SKU Code');
    const quantities = screen.getAllByLabelText('Pack quantity');
    const units = screen.getAllByLabelText('Unit');
    await user.type(codes[1], 'RICE-CASE-12');
    await user.clear(quantities[1]);
    await user.type(quantities[1], '12');
    await user.clear(units[1]);
    await user.type(units[1], 'case');
    await user.click(screen.getByRole('button', { name: 'Save Product' }));

    await waitFor(() => {
      expect(catalogProductService.create).toHaveBeenCalledWith({
        name: 'Premium Rice',
        description: '',
        category: '',
        is_active: true,
        sellable_units: [
          { sku_code: 'RICE-EACH-1', unit: 'bag', package_quantity: 1, is_active: true },
          { sku_code: 'RICE-CASE-12', unit: 'case', package_quantity: 12, is_active: true },
        ],
      });
    });
    expect(onSuccess).toHaveBeenCalledOnce();
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('rejects an empty package quantity before calling the API', async () => {
    const user = userEvent.setup();
    render(
      <SKUFormModal
        isOpen
        onClose={vi.fn()}
        onSuccess={vi.fn()}
        product={null}
      />
    );

    await user.type(screen.getByLabelText('Product Name'), 'Premium Rice');
    await user.type(screen.getByLabelText('SKU Code'), 'RICE-EACH-1');
    await user.clear(screen.getByLabelText('Pack quantity'));
    await user.click(screen.getByRole('button', { name: 'Save Product' }));

    expect(catalogProductService.create).not.toHaveBeenCalled();
    expect(await screen.findByText('Check each packaging option.')).toBeInTheDocument();
  });

  it('updates packaging activity without attempting to change its permanent code', async () => {
    const user = userEvent.setup();
    vi.mocked(catalogProductService.updateSellableUnit).mockResolvedValue({} as never);
    const product = {
      id: 'product-1',
      name: 'Premium Rice',
      description: null,
      category: null,
      is_active: true,
      created_at: '2026-08-30T00:00:00Z',
      updated_at: '2026-08-30T00:00:00Z',
      sellable_units: [],
    };
    const sellableUnit = {
      id: 'unit-1',
      catalog_product_id: product.id,
      sku_code: 'RICE-EACH-1',
      unit: 'bag',
      package_quantity: 1,
      is_active: true,
      created_at: '2026-08-30T00:00:00Z',
      updated_at: '2026-08-30T00:00:00Z',
    };

    render(
      <AddSellableUnitModal
        isOpen
        product={product}
        sellableUnit={sellableUnit}
        onClose={vi.fn()}
        onSuccess={vi.fn()}
      />
    );
    await user.click(screen.getByLabelText('Active packaging'));
    await user.click(screen.getByRole('button', { name: 'Save packaging' }));

    await waitFor(() => {
      expect(catalogProductService.updateSellableUnit).toHaveBeenCalledWith(
        product.id,
        sellableUnit.id,
        { unit: 'bag', package_quantity: 1, is_active: false },
      );
    });
  });
});
