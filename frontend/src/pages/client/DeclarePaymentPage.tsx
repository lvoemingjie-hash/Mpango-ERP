/** Retailer payment declaration submission (DC-12R1-S3-S2B-I2B). */
import { useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { submitDeclaration } from '@/services/declarationService';

export default function DeclarePaymentPage() {
  const { orderId } = useParams<{ orderId: string }>();
  const navigate = useNavigate();
  const [amount, setAmount] = useState('');
  const [method, setMethod] = useState<'cash' | 'transfer'>('cash');
  const [transferRef, setTransferRef] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Stable idempotency key: generated ONCE per mounted form, reused across
  // retries (timeout / network failure / controlled API error) so the backend
  // can deduplicate. Kept in a ref (not state) because it must not trigger
  // re-renders. Rotated only after a confirmed successful submission so the
  // next fresh declaration gets a new key.
  const idempotencyKeyRef = useRef<string>(crypto.randomUUID());
  // Mutex to prevent duplicate clicks while a request is in flight.
  const submittingRef = useRef(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!orderId || !amount) return;
    // Prevent duplicate clicks while a submission is already in flight.
    if (submittingRef.current) return;
    submittingRef.current = true;
    setLoading(true);
    setError('');
    try {
      const body: { declared_amount: string; method: string; transfer_reference?: string | null } = {
        declared_amount: amount,
        method,
      };
      if (method === 'transfer' && transferRef) {
        body.transfer_reference = transferRef.trim();
      }
      await submitDeclaration(orderId, body, idempotencyKeyRef.current);
      // Success: rotate the key so a completely new declaration gets a fresh one.
      idempotencyKeyRef.current = crypto.randomUUID();
      navigate(`/client/orders/${orderId}`);
    } catch (err: unknown) {
      // Error: keep the SAME key so a retry hits the same idempotency slot.
      const msg = (err as { response?: { data?: { message?: string; code?: string } } })?.response?.data?.message
        || (err as Error).message || 'Submission failed';
      setError(msg);
    } finally {
      setLoading(false);
      submittingRef.current = false;
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 p-4">
      <h1 className="text-lg font-semibold text-gray-900 mb-4">Declare Payment</h1>
      <p className="text-sm text-gray-500 mb-4">Order: {orderId}</p>
      <form onSubmit={handleSubmit} className="bg-white rounded-xl shadow p-6 space-y-4">
        {error && <div className="bg-red-50 text-red-700 text-sm p-3 rounded">{error}</div>}
        <div>
          <label htmlFor="amount" className="block text-sm font-medium text-gray-700 mb-1">Amount (KES)</label>
          <input id="amount" type="number" step="0.01" min="0.01" required value={amount} onChange={e => setAmount(e.target.value)}
            className="w-full rounded-lg border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500" />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Method</label>
          <select value={method} onChange={e => setMethod(e.target.value as 'cash' | 'transfer')}
            className="w-full rounded-lg border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500">
            <option value="cash">Cash</option>
            <option value="transfer">Transfer</option>
          </select>
        </div>
        {method === 'transfer' && (
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Transfer Reference</label>
            <input type="text" maxLength={128} value={transferRef} onChange={e => setTransferRef(e.target.value)}
              className="w-full rounded-lg border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500" />
          </div>
        )}
        <button type="submit" disabled={loading}
          className="w-full bg-indigo-600 text-white py-2 px-4 rounded-lg hover:bg-indigo-700 disabled:opacity-50">
          {loading ? 'Submitting...' : 'Submit Declaration'}
        </button>
      </form>
    </div>
  );
}
