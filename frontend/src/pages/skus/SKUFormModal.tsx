import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { Dialog } from '@headlessui/react';
import { XMarkIcon } from '@heroicons/react/24/outline';
import { skuService } from '@/services/skuService';
import type { SKU, SKUCreateRequest, SKUUpdateRequest } from '@/services/skuService';
import { useToastStore } from '@/stores/toastStore';

interface SKUFormModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
  sku: SKU | null;
}

export function SKUFormModal({ isOpen, onClose, onSuccess, sku }: SKUFormModalProps) {
  const [loading, setLoading] = useState(false);
  const { register, handleSubmit, reset, formState: { errors } } = useForm<SKUCreateRequest>({
    defaultValues: {
      is_active: true,
      unit: 'unit'
    }
  });

  useEffect(() => {
    if (sku) {
      reset({
        sku_code: sku.sku_code,
        name: sku.name,
        description: sku.description || '',
        unit: sku.unit,
        category: sku.category || '',
        is_active: sku.is_active,
      });
    } else {
      reset({
        sku_code: '',
        name: '',
        description: '',
        unit: 'unit',
        category: '',
        is_active: true,
      });
    }
  }, [sku, reset, isOpen]);

  const onSubmit = async (data: SKUCreateRequest) => {
    setLoading(true);
    try {
      if (sku) {
        // Update
        const updateData: SKUUpdateRequest = {
          name: data.name,
          description: data.description,
          unit: data.unit,
          category: data.category,
          is_active: data.is_active,
        };
        await skuService.update(sku.sku_code, updateData);
        useToastStore.getState().addToast({
          type: 'success',
          title: 'SKU Updated',
          message: `${data.name} has been updated successfully.`,
        });
      } else {
        // Create
        await skuService.create(data);
        useToastStore.getState().addToast({
          type: 'success',
          title: 'SKU Created',
          message: `${data.name} has been created successfully.`,
        });
      }
      onSuccess();
      onClose();
    } catch {
      // Error is handled by global interceptor
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={isOpen} onClose={onClose} className="relative z-50">
      <div className="fixed inset-0 bg-black/30" aria-hidden="true" />
      <div className="fixed inset-0 flex items-center justify-center p-4">
        <Dialog.Panel className="mx-auto w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
          <div className="flex items-center justify-between mb-6">
            <Dialog.Title className="text-lg font-medium text-gray-900">
              {sku ? 'Edit Product' : 'Add New Product'}
            </Dialog.Title>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-500">
              <XMarkIcon className="h-5 w-5" />
            </button>
          </div>

          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700">SKU Code</label>
              <input
                type="text"
                {...register('sku_code', { required: 'SKU Code is required' })}
                disabled={!!sku}
                className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 disabled:bg-gray-100 sm:text-sm"
              />
              {errors.sku_code && <p className="mt-1 text-sm text-red-600">{errors.sku_code.message}</p>}
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700">Product Name</label>
              <input
                type="text"
                {...register('name', { required: 'Product Name is required' })}
                className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
              />
              {errors.name && <p className="mt-1 text-sm text-red-600">{errors.name.message}</p>}
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700">Category</label>
              <input
                type="text"
                {...register('category')}
                className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700">Unit</label>
              <input
                type="text"
                {...register('unit', { required: 'Unit is required' })}
                className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
                placeholder="e.g. unit, kg, box"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700">Description</label>
              <textarea
                {...register('description')}
                rows={3}
                className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
              />
            </div>

            <div className="flex items-center">
              <input
                type="checkbox"
                {...register('is_active')}
                className="h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
              />
              <label className="ml-2 block text-sm text-gray-900">Active</label>
            </div>

            <div className="mt-6 flex justify-end gap-3">
              <button
                type="button"
                onClick={onClose}
                className="btn-secondary"
                disabled={loading}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="btn-primary"
                disabled={loading}
              >
                {loading ? 'Saving...' : 'Save Product'}
              </button>
            </div>
          </form>
        </Dialog.Panel>
      </div>
    </Dialog>
  );
}
