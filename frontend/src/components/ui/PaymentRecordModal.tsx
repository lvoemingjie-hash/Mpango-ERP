import { useState } from 'react';
import { Modal } from '@/components/ui/Modal';
import type { PayOrderData, PaymentMethod } from '@/services/orderService';

interface PaymentRecordModalProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (data: PayOrderData, idempotencyKey: string) => Promise<void>;
  orderId: string;
  orderTotal: number;
  /** Remaining unpaid amount (orderTotal minus previous payments) */
  remainingAmount: number;
  loading?: boolean;
}

const METHODS = [
  { value: 'cash', label: 'Cash' },
  { value: 'transfer', label: 'Bank Transfer / Mobile Money' },
  { value: 'credit', label: 'Credit Sale' },
] as const satisfies readonly { value: PaymentMethod; label: string }[];

function createPaymentIdempotencyKey() {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID();
  }
  return `pay-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

export function PaymentRecordModal({
  open,
  onClose,
  onSubmit,
  orderId,
  orderTotal,
  remainingAmount,
  loading = false,
}: PaymentRecordModalProps) {
  const [method, setMethod] = useState<PaymentMethod | ''>('');
  const [amount, setAmount] = useState('');
  const [transactionId, setTransactionId] = useState('');
  const [notes, setNotes] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [idempotencyKey, setIdempotencyKey] = useState(createPaymentIdempotencyKey);

  const resetIdempotencyKey = () => setIdempotencyKey(createPaymentIdempotencyKey());

  const creditUnavailable = remainingAmount !== orderTotal;
  const isValid = method && amount && Number(amount) > 0
    && (method === 'credit' ? Number(amount) === orderTotal && remainingAmount === orderTotal : Number(amount) <= remainingAmount);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    const numAmount = Number(amount);
    if (numAmount <= 0) {
      setError('Amount must be greater than 0');
      return;
    }
    if (!method) {
      setError('Select a payment method');
      return;
    }
    if (method === 'credit') {
      if (remainingAmount !== orderTotal) {
        setError('Credit is only allowed on orders with no prior payments (no split tender).');
        return;
      }
      if (numAmount !== orderTotal) {
        setError(`Credit amount must equal the full order total of KES ${orderTotal.toLocaleString()}. Partial credit is not supported.`);
        return;
      }
    } else if (numAmount > remainingAmount) {
      setError(`Amount cannot exceed remaining balance of KES ${remainingAmount.toLocaleString()}`);
      return;
    }

    try {
      await onSubmit({
        method,
        amount: numAmount,
        transaction_id: transactionId || undefined,
        notes: notes.trim() || undefined,
      }, idempotencyKey);
      // Reset form on success
      setMethod('');
      setAmount('');
      setTransactionId('');
      setNotes('');
      resetIdempotencyKey();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Payment failed';
      setError(msg);
    }
  };

  const handleClose = () => {
    if (loading) return;
    setMethod('');
    setAmount('');
    setTransactionId('');
    setNotes('');
    setError(null);
    resetIdempotencyKey();
    onClose();
  };

  const willFullyPay = amount && Number(amount) >= remainingAmount;

  return (
    <Modal open={open} onClose={handleClose} title="Record Payment">
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="text-sm text-gray-600">
          <p>
            Order: <span className="font-medium text-gray-900">#{orderId.slice(0, 8)}</span>
          </p>
          <p>
            Order Total: <span className="font-medium">KES {orderTotal.toLocaleString()}</span>
          </p>
          <p>
            Remaining:{' '}
            <span className="font-medium text-amber-600">
              KES {remainingAmount.toLocaleString()}
            </span>
          </p>
        </div>

        <div>
          <label htmlFor="pay-method" className="block text-sm font-medium text-gray-700">
            Payment Method *
          </label>
          <select
            id="pay-method"
            value={method}
            onChange={(e) => {
              const next = e.target.value as PaymentMethod | '';
              setError(null);
              resetIdempotencyKey();
              if (next === 'credit' && creditUnavailable) {
                setMethod('');
                setAmount('');
                setError('Credit Sale is only available before any payment has been recorded. Use a repayment method for partially paid orders.');
                return;
              }
              setMethod(next);
              if (next === 'credit') {
                setAmount(String(orderTotal));
              } else {
                setAmount('');
              }
            }}
            className="mt-1 block w-full rounded-md border border-gray-300 py-2 pl-3 pr-10 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          >
            <option value="">Select method</option>
            {METHODS.map((m) => (
              <option key={m.value} value={m.value} disabled={m.value === 'credit' && creditUnavailable}>
                {m.value === 'credit' && creditUnavailable
                  ? `${m.label} (full unpaid orders only)`
                  : m.label}
              </option>
            ))}
          </select>
          {creditUnavailable && (
            <p className="mt-1 text-xs text-gray-500">
              Credit Sale is disabled because this order already has a recorded payment. Use Cash, Bank Transfer, or Mobile Money to collect the remaining balance.
            </p>
          )}
        </div>

        <div>
          <label htmlFor="pay-amount" className="block text-sm font-medium text-gray-700">
            Amount (KES) *
          </label>
          <input
            id="pay-amount"
            type="number"
            min="0.01"
            max={remainingAmount}
            step="0.01"
            value={amount}
            onChange={(e) => {
              setAmount(e.target.value);
              resetIdempotencyKey();
            }}
            readOnly={method === 'credit'}
            placeholder={method === 'credit' ? 'Full order total (auto-filled)' : `Max: KES ${remainingAmount.toLocaleString()}`}
            className={`mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500${method === 'credit' ? ' bg-gray-100 cursor-not-allowed' : ''}`}
          />
        </div>

        {method === 'transfer' && (
          <div>
            <label htmlFor="pay-txn-id" className="block text-sm font-medium text-gray-700">
              Transaction ID
            </label>
            <input
              id="pay-txn-id"
              type="text"
              value={transactionId}
              onChange={(e) => {
                setTransactionId(e.target.value);
                resetIdempotencyKey();
              }}
              placeholder="e.g. QWE12345"
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>
        )}

        <div>
          <label htmlFor="pay-notes" className="block text-sm font-medium text-gray-700">
            Collection note
          </label>
          <textarea
            id="pay-notes"
            value={notes}
            onChange={(e) => {
              setNotes(e.target.value);
              resetIdempotencyKey();
            }}
            maxLength={1000}
            rows={2}
            placeholder="Optional note for this repayment"
            className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
          <p className="mt-1 text-xs text-gray-500">
            Add context such as collector, receipt reference, or repayment promise.
          </p>
        </div>

        {method === 'credit' && (
          <div className="rounded-md bg-blue-50 p-3 text-sm text-blue-700">
            <strong>Credit Sale:</strong> No cash is received now. The full order balance (KES {orderTotal.toLocaleString()}) will be recorded as an account receivable. Repayment is tracked separately under Accounts Receivable.
          </div>
        )}

        {willFullyPay && method !== 'credit' && (
          <div className="rounded-md bg-green-50 p-3 text-sm text-green-700">
            [OK] Full payment -- order will be marked as <strong>Paid</strong>
          </div>
        )}

        {amount && !willFullyPay && Number(amount) > 0 && (
          <div className="rounded-md bg-amber-50 p-3 text-sm text-amber-700">
            [!] Partial payment -- order will be marked as <strong>Partially Paid</strong>
          </div>
        )}

        {error && (
          <div className="rounded-md bg-red-50 p-3 text-sm text-red-700">{error}</div>
        )}

        <div className="flex justify-end gap-3 pt-2">
          <button
            type="button"
            onClick={handleClose}
            disabled={loading}
            className="btn-secondary text-sm"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={!isValid || loading}
            className="btn-primary text-sm disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? 'Recording...' : 'Record Payment'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
