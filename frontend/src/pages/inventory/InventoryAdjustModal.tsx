import { useState, useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import { Dialog } from '@headlessui/react';
import { XMarkIcon } from '@heroicons/react/24/outline';
import { normalizeApiError } from '@/utils/errorHandling';

const schema = z.object({
  sku_code: z.string().min(1, 'SKU code is required'),
  quantity: z.number().refine(val => val !== 0, 'Quantity cannot be zero'),
  reason: z.string().min(1, 'Reason is required').max(500, 'Reason is too long'),
});

export type AdjustFormData = z.infer<typeof schema>;

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: AdjustFormData) => Promise<void>;
  initialSkuCode?: string;
}

export function InventoryAdjustModal({ isOpen, onClose, onSubmit, initialSkuCode = '' }: Props) {
  const [error, setError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<AdjustFormData>({
    resolver: zodResolver(schema),
    defaultValues: {
      sku_code: initialSkuCode,
      quantity: 0,
      reason: '',
    },
  });

  // Reset form when modal opens or when initialSkuCode changes.
  // useEffect ensures the reset runs on every relevant render (not just initial
  // mount), so the disabled SKU field reflects the selected SKU code.
  useEffect(() => {
    if (isOpen) {
      reset({ sku_code: initialSkuCode, quantity: 0, reason: '' });
      setError(null);
    }
  }, [isOpen, initialSkuCode, reset, setError]);

  const handleFormSubmit = async (data: AdjustFormData) => {
    try {
      setError(null);
      await onSubmit(data);
      onClose();
    } catch (err: unknown) {
      const message = normalizeApiError(err);
      setError(message);
    }
  };

  return (
    <Dialog open={isOpen} onClose={onClose} className="relative z-50">
      <div className="fixed inset-0 bg-black/30" aria-hidden="true" />
      <div className="fixed inset-0 flex items-center justify-center p-4">
        <Dialog.Panel className="mx-auto w-full max-w-md rounded-xl bg-white shadow-xl">
          <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
            <Dialog.Title className="text-lg font-semibold text-gray-900">
              Adjust Inventory
            </Dialog.Title>
            <button
              onClick={onClose}
              className="rounded-lg p-1 text-gray-400 hover:bg-gray-50 hover:text-gray-500"
            >
              <XMarkIcon className="h-5 w-5" />
            </button>
          </div>

          <form onSubmit={handleSubmit(handleFormSubmit)} className="p-6">
            {error && (
              <div className="mb-4 rounded-md bg-red-50 p-3 text-sm text-red-700">
                {error}
              </div>
            )}

            <div className="space-y-4">
              <div>
                <label htmlFor="adjust-sku-code" className="block text-sm font-medium text-gray-700">
                  SKU Code
                </label>
                <input
                  id="adjust-sku-code"
                  type="text"
                  {...register('sku_code')}
                  disabled={!!initialSkuCode}
                  className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500 disabled:bg-gray-100 sm:text-sm"
                />
                {errors.sku_code && (
                  <p className="mt-1 text-sm text-red-600">{errors.sku_code.message}</p>
                )}
              </div>

              <div>
                <label htmlFor="adjust-quantity" className="block text-sm font-medium text-gray-700">
                  Adjustment Quantity (+/-)
                </label>
                <div className="mt-1 relative rounded-md shadow-sm">
                  <input
                    id="adjust-quantity"
                    type="number"
                    step="1"
                    {...register('quantity', { valueAsNumber: true })}
                    className="block w-full rounded-md border border-gray-300 px-3 py-2 focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500 sm:text-sm"
                    placeholder="-5 or 10"
                  />
                </div>
                {errors.quantity && (
                  <p className="mt-1 text-sm text-red-600">{errors.quantity.message}</p>
                )}
              </div>

              <div>
                <label htmlFor="adjust-reason" className="block text-sm font-medium text-gray-700">
                  Reason
                </label>
                <input
                  id="adjust-reason"
                  type="text"
                  {...register('reason')}
                  className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500 sm:text-sm"
                  placeholder="e.g., Stocktake correction, Damaged goods"
                />
                {errors.reason && (
                  <p className="mt-1 text-sm text-red-600">{errors.reason.message}</p>
                )}
              </div>
            </div>

            <div className="mt-6 flex justify-end gap-3 border-t border-gray-200 pt-4">
              <button
                type="button"
                onClick={onClose}
                className="btn-secondary"
                disabled={isSubmitting}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="btn-primary"
                disabled={isSubmitting}
              >
                {isSubmitting ? 'Adjusting...' : 'Confirm Adjustment'}
              </button>
            </div>
          </form>
        </Dialog.Panel>
      </div>
    </Dialog>
  );
}
