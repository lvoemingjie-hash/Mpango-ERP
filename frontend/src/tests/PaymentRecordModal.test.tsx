import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PaymentRecordModal } from '@/components/ui/PaymentRecordModal';
import {
  calculatePaymentModalState,
  isOrderListPaymentActionVisible,
} from '@/pages/orders/OrderListPage';
import type { Order } from '@/types/order';
import type { PaymentData } from '@/services/paymentService';


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
    }, expect.stringMatching(/^[A-Za-z0-9._:-]{8,64}$/));
  });

  it('disables duplicate credit sale when collecting a paid credit order', async () => {
    render(
      <PaymentRecordModal
        open={true}
        onClose={vi.fn()}
        onSubmit={vi.fn()}
        orderId="12345678-1234-1234-1234-123456789abc"
        orderTotal={5000}
        remainingAmount={5000}
        allowCreditSale={false}
      />,
    );

    const methodSelect = screen.getByLabelText(/payment method/i) as HTMLSelectElement;
    const creditOption = Array.from(methodSelect.options).find((option) => option.value === 'credit');
    expect(creditOption?.disabled).toBe(true);
    expect(screen.getByText(/credit sale is disabled/i)).toBeInTheDocument();
  });

  it('calculates Finance Collect remaining exposure from credit minus collections', () => {
    const paidCreditOrder: Order = {
      id: '12345678-1234-1234-1234-123456789abc',
      wholesaler_id: '22345678-1234-1234-1234-123456789abc',
      retailer_id: '32345678-1234-1234-1234-123456789abc',
      retailer_name: 'Retailer A',
      status: 'paid',
      total_amount: 5000,
      items: [],
      notes: null,
      created_by: null,
      created_at: '2026-07-22T00:00:00Z',
      updated_at: '2026-07-22T00:00:00Z',
    };
    const payments: PaymentData[] = [
      {
        id: '42345678-1234-1234-1234-123456789abc',
        order_id: paidCreditOrder.id,
        retailer_id: paidCreditOrder.retailer_id,
        transaction_id: null,
        amount: 5000,
        method: 'credit',
        status: 'pending',
        created_at: '2026-07-22T00:00:00Z',
        updated_at: '2026-07-22T00:00:00Z',
      },
      {
        id: '52345678-1234-1234-1234-123456789abc',
        order_id: paidCreditOrder.id,
        retailer_id: paidCreditOrder.retailer_id,
        transaction_id: 'MM-12345',
        amount: 1250,
        method: 'transfer',
        status: 'completed',
        created_at: '2026-07-22T00:00:00Z',
        updated_at: '2026-07-22T00:00:00Z',
      },
    ];

    expect(calculatePaymentModalState(paidCreditOrder, payments)).toEqual({
      remainingAmount: 3750,
      allowCreditSale: false,
    });
  });

  it('does not expose a remaining balance for an ordinary paid order', () => {
    const paidCashOrder = {
      id: '62345678-1234-1234-1234-123456789abc',
      wholesaler_id: '22345678-1234-1234-1234-123456789abc',
      retailer_id: '32345678-1234-1234-1234-123456789abc',
      retailer_name: 'Retailer A',
      status: 'paid',
      total_amount: 5000,
      items: [],
      notes: null,
      created_by: null,
      created_at: '2026-07-22T00:00:00Z',
      updated_at: '2026-07-22T00:00:00Z',
    } satisfies Order;
    const payments = [{
      id: '72345678-1234-1234-1234-123456789abc',
      order_id: paidCashOrder.id,
      retailer_id: paidCashOrder.retailer_id,
      transaction_id: null,
      amount: 5000,
      method: 'cash',
      status: 'completed',
      created_at: '2026-07-22T00:00:00Z',
      updated_at: '2026-07-22T00:00:00Z',
    }] satisfies PaymentData[];

    expect(calculatePaymentModalState(paidCashOrder, payments)).toEqual({
      remainingAmount: 0,
      allowCreditSale: false,
    });
    expect(isOrderListPaymentActionVisible('paid')).toBe(false);
    expect(isOrderListPaymentActionVisible('confirmed')).toBe(true);
    expect(isOrderListPaymentActionVisible('partially_paid')).toBe(true);
  });
});
