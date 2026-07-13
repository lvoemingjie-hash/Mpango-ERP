import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PaymentRecordModal } from '@/components/ui/PaymentRecordModal';


describe('PaymentRecordModal payment methods', () => {
  it('submits Mobile Money label as canonical transfer method', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);

    render(
      <PaymentRecordModal
        open={true}
        onClose={vi.fn()}
        onSubmit={onSubmit}
        orderId="12345678-1234-1234-1234-123456789abc"
        orderTotal={5000}
        remainingAmount={5000}
      />,
    );

    const methodSelect = screen.getByLabelText(/payment method/i) as HTMLSelectElement;
    const optionValues = Array.from(methodSelect.options).map((option) => option.value);
    expect(optionValues).not.toContain('mobile_money');

    await userEvent.selectOptions(methodSelect, 'transfer');
    await userEvent.type(screen.getByLabelText(/amount/i), '1250');
    await userEvent.type(screen.getByLabelText(/transaction id/i), 'MM-12345');
    await userEvent.click(screen.getByRole('button', { name: /record payment/i }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).toHaveBeenCalledWith({
      method: 'transfer',
      amount: 1250,
      transaction_id: 'MM-12345',
      notes: undefined,
    });
  });
});
