import { useEffect, useState } from 'react';
import { useFieldArray, useForm } from 'react-hook-form';
import { Dialog } from '@headlessui/react';
import { XMarkIcon } from '@heroicons/react/24/outline';
import { catalogProductService } from '@/services/catalogProductService';
import type { CatalogProduct } from '@/services/catalogProductService';
import { useToastStore } from '@/stores/toastStore';

interface SKUFormModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
  product: CatalogProduct | null;
}

export function SKUFormModal({ isOpen, onClose, onSuccess, product }: SKUFormModalProps) {
  const [loading, setLoading] = useState(false);
  type FormValues = {
    name: string;
    description?: string;
    category?: string;
    is_active: boolean;
    sellable_units: Array<{ sku_code: string; unit: string; package_quantity: number; is_active: boolean }>;
  };
  const { register, control, handleSubmit, reset, formState: { errors } } = useForm<FormValues>({
    defaultValues: {
      is_active: true,
      sellable_units: [{ sku_code: '', unit: 'unit', package_quantity: 1, is_active: true }]
    }
  });
  const { fields, append, remove } = useFieldArray({ control, name: 'sellable_units' });

  useEffect(() => {
    if (product) {
      reset({
        name: product.name,
        description: product.description || '',
        category: product.category || '',
        is_active: product.is_active,
        sellable_units: [],
      });
    } else {
      reset({
        name: '',
        description: '',
        category: '',
        is_active: true,
        sellable_units: [{ sku_code: '', unit: 'unit', package_quantity: 1, is_active: true }],
      });
    }
  }, [product, reset, isOpen]);

  const onSubmit = async (data: FormValues) => {
    setLoading(true);
    try {
      if (product) {
        await catalogProductService.update(product.id, {
          name: data.name,
          description: data.description,
          category: data.category,
          is_active: data.is_active,
        });
        useToastStore.getState().addToast({
          type: 'success',
          title: 'Product Updated',
          message: `${data.name} has been updated successfully.`,
        });
      } else {
        await catalogProductService.create({
          name: data.name,
          description: data.description,
          category: data.category,
          is_active: data.is_active,
          sellable_units: data.sellable_units.map((unit) => ({
            ...unit,
            package_quantity: Number(unit.package_quantity),
          })),
        });
        useToastStore.getState().addToast({
          type: 'success',
          title: 'Product Created',
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
              {product ? 'Edit Product' : 'Add New Product'}
            </Dialog.Title>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-500">
              <XMarkIcon className="h-5 w-5" />
            </button>
          </div>

          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div>
              <label htmlFor="catalog-product-name" className="block text-sm font-medium text-gray-700">Product Name</label>
              <input
                id="catalog-product-name"
                type="text"
                {...register('name', { required: 'Product Name is required' })}
                className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
              />
              {errors.name && <p className="mt-1 text-sm text-red-600">{errors.name.message}</p>}
            </div>

            <div>
              <label htmlFor="catalog-product-category" className="block text-sm font-medium text-gray-700">Category</label>
              <input
                id="catalog-product-category"
                type="text"
                {...register('category')}
                className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
              />
            </div>

            {!product && <div className="space-y-3 rounded-lg border border-gray-200 p-3">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-gray-900">Packaging options</h3>
                <button
                  type="button"
                  className="text-sm font-medium text-primary-700"
                  onClick={() => append({ sku_code: '', unit: 'unit', package_quantity: 1, is_active: true })}
                >
                  Add packaging
                </button>
              </div>
              {fields.map((field, index) => (
                <div key={field.id} className="grid gap-3 rounded-md bg-gray-50 p-3 sm:grid-cols-3">
                  <div>
                    <label htmlFor={`sellable-unit-${index}-code`} className="block text-xs font-medium text-gray-700">SKU Code</label>
                    <input
                      id={`sellable-unit-${index}-code`}
                      {...register(`sellable_units.${index}.sku_code`, { required: 'SKU Code is required' })}
                      className="mt-1 block w-full rounded-md border-gray-300 sm:text-sm"
                    />
                  </div>
                  <div>
                    <label htmlFor={`sellable-unit-${index}-quantity`} className="block text-xs font-medium text-gray-700">Pack quantity</label>
                    <input
                      id={`sellable-unit-${index}-quantity`}
                      type="number"
                      min="0.001"
                      step="0.001"
                      {...register(`sellable_units.${index}.package_quantity`, {
                        valueAsNumber: true,
                        required: 'Pack quantity is required',
                        min: { value: 0.001, message: 'Pack quantity must be positive' },
                        validate: (value) => Number.isFinite(value) || 'Pack quantity is required',
                      })}
                      className="mt-1 block w-full rounded-md border-gray-300 sm:text-sm"
                    />
                  </div>
                  <div>
                    <label htmlFor={`sellable-unit-${index}-unit`} className="block text-xs font-medium text-gray-700">Unit</label>
                    <input
                      id={`sellable-unit-${index}-unit`}
                      {...register(`sellable_units.${index}.unit`, { required: 'Unit is required' })}
                      className="mt-1 block w-full rounded-md border-gray-300 sm:text-sm"
                    />
                  </div>
                  {fields.length > 1 && (
                    <button type="button" className="text-left text-xs text-red-700" onClick={() => remove(index)}>
                      Remove packaging
                    </button>
                  )}
                </div>
              ))}
              {errors.sellable_units && <p className="text-sm text-red-600">Check each packaging option.</p>}
            </div>}

            <div>
              <label htmlFor="catalog-product-description" className="block text-sm font-medium text-gray-700">Description</label>
              <textarea
                id="catalog-product-description"
                {...register('description')}
                rows={3}
                className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
              />
            </div>

            <div className="flex items-center">
              <input
                id="catalog-product-active"
                type="checkbox"
                {...register('is_active')}
                className="h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
              />
              <label htmlFor="catalog-product-active" className="ml-2 block text-sm text-gray-900">Active</label>
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
