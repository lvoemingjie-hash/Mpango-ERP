/**
 * S5-D2-R2 Frontend tests for InventoryAdjustModal SKU binding.
 *
 * Covers the bug found in S5-D2-BROWSER: the Adjust Stock modal opened with
 * an empty, disabled SKU Code field because a `useState` initializer was
 * misused as a side-effect (runs only once on mount).
 *
 * Verifies:
 *   1. SKU field displays the initialSkuCode when modal is open
 *   2. SKU field is disabled when initialSkuCode is provided
 *   3. Submit sends sku_code = initialSkuCode along with quantity/reason
 *   4. Form resets when the modal re-opens with a different SKU
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { InventoryAdjustModal } from '@/pages/inventory/InventoryAdjustModal';

// ---------------------------------------------------------------------------
// Mock normalizeApiError
// ---------------------------------------------------------------------------

vi.mock('@/utils/errorHandling', () => ({
  normalizeApiError: (err: unknown) => {
    const axErr = err as { response?: { status?: number; data?: { detail?: string } }; message?: string };
    return axErr.message || 'An error occurred';
  },
}));

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('InventoryAdjustModal SKU binding (S5-D2-R2)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('displays the initialSkuCode in the disabled SKU field when open', async () => {
    render(
      <InventoryAdjustModal
        isOpen={true}
        onClose={vi.fn()}
        onSubmit={vi.fn()}
        initialSkuCode="S5D2B-CHARGER01"
      />,
    );

    // useEffect runs after mount; wait for the field to be populated
    await waitFor(() => {
      const skuInput = screen.getByLabelText('SKU Code') as HTMLInputElement;
      expect(skuInput.value).toBe('S5D2B-CHARGER01');
    });

    // SKU field must be disabled since a SKU was provided
    expect(screen.getByLabelText('SKU Code')).toBeDisabled();
  });

  it('submits sku_code=initialSkuCode with quantity and reason', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);

    render(
      <InventoryAdjustModal
        isOpen={true}
        onClose={vi.fn()}
        onSubmit={onSubmit}
        initialSkuCode="S5D2B-CHARGER01"
      />,
    );

    // Fill quantity
    const qtyInput = screen.getByLabelText('Adjustment Quantity (+/-)');
    await userEvent.clear(qtyInput);
    await userEvent.type(qtyInput, '-5');

    // Fill reason
    const reasonInput = screen.getByLabelText('Reason');
    await userEvent.type(reasonInput, 'Damaged in transit');

    // Submit
    await userEvent.click(screen.getByRole('button', { name: /confirm adjustment/i }));

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledTimes(1);
    });

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        sku_code: 'S5D2B-CHARGER01',
        quantity: -5,
        reason: 'Damaged in transit',
      }),
    );
  });

  it('resets the SKU field when re-opened with a different initialSkuCode', async () => {
    const onClose = vi.fn();
    const onSubmit = vi.fn().mockResolvedValue(undefined);

    const { rerender } = render(
      <InventoryAdjustModal
        isOpen={true}
        onClose={onClose}
        onSubmit={onSubmit}
        initialSkuCode="SKU-A"
      />,
    );

    await waitFor(() => {
      expect((screen.getByLabelText('SKU Code') as HTMLInputElement).value).toBe('SKU-A');
    });

    // Re-render simulating reopening the modal for a different SKU
    rerender(
      <InventoryAdjustModal
        isOpen={true}
        onClose={onClose}
        onSubmit={onSubmit}
        initialSkuCode="SKU-B"
      />,
    );

    await waitFor(() => {
      expect((screen.getByLabelText('SKU Code') as HTMLInputElement).value).toBe('SKU-B');
    });
  });
});
