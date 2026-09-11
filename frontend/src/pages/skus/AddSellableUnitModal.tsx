import { useEffect, useState } from 'react';
import { Dialog } from '@headlessui/react';
import { XMarkIcon } from '@heroicons/react/24/outline';
import { catalogProductService } from '@/services/catalogProductService';
import type { CatalogProduct, SellableUnit } from '@/services/catalogProductService';
import { useToastStore } from '@/stores/toastStore';

interface AddSellableUnitModalProps {
  isOpen: boolean;
  product: CatalogProduct | null;
  sellableUnit?: SellableUnit | null;
  onClose: () => void;
  onSuccess: () => void;
}

export function AddSellableUnitModal({
  isOpen,
  product,
  sellableUnit = null,
  onClose,
  onSuccess,
}: AddSellableUnitModalProps) {
  const [skuCode, setSkuCode] = useState('');
  const [unit, setUnit] = useState('unit');
  const [packageQuantity, setPackageQuantity] = useState(1);
  const [isActive, setIsActive] = useState(true);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (isOpen) {
      setSkuCode(sellableUnit?.sku_code || '');
      setUnit(sellableUnit?.unit || 'unit');
      setPackageQuantity(sellableUnit?.package_quantity ?? 1);
      setIsActive(sellableUnit?.is_active ?? true);
    }
  }, [isOpen, sellableUnit]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!product || !skuCode.trim() || !unit.trim()
      || !Number.isFinite(packageQuantity) || packageQuantity <= 0) return;
    setLoading(true);
    try {
      if (sellableUnit) {
        await catalogProductService.updateSellableUnit(product.id, sellableUnit.id, {
          unit: unit.trim(),
          package_quantity: packageQuantity,
          is_active: isActive,
        });
      } else {
        await catalogProductService.addSellableUnit(product.id, {
          sku_code: skuCode.trim(),
          unit: unit.trim(),
          package_quantity: packageQuantity,
          is_active: isActive,
        });
      }
      useToastStore.getState().addToast({
        type: 'success',
        title: sellableUnit ? 'Packaging Updated' : 'Packaging Added',
        message: `${skuCode.trim()} ${sellableUnit ? 'was updated' : 'is now available'} for ${product.name}.`,
      });
      onSuccess();
      onClose();
    } catch {
      // The global interceptor presents the server error.
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={isOpen} onClose={onClose} className="relative z-50">
      <div className="fixed inset-0 bg-black/30" aria-hidden="true" />
      <div className="fixed inset-0 flex items-center justify-center p-4">
        <Dialog.Panel className="mx-auto w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
          <div className="mb-6 flex items-center justify-between">
            <div>
              <Dialog.Title className="text-lg font-medium text-gray-900">
                {sellableUnit ? 'Edit packaging' : 'Add packaging'}
              </Dialog.Title>
              <p className="mt-1 text-sm text-gray-500">{product?.name}</p>
            </div>
            <button type="button" onClick={onClose} className="text-gray-400 hover:text-gray-500">
              <XMarkIcon className="h-5 w-5" />
            </button>
          </div>
          <form onSubmit={submit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700" htmlFor="package-sku-code">SKU code</label>
              <input id="package-sku-code" required disabled={!!sellableUnit} value={skuCode} onChange={(event) => setSkuCode(event.target.value)} className="mt-1 block w-full rounded-md border-gray-300 disabled:bg-gray-100 sm:text-sm" />
              <p className="mt-1 text-xs text-gray-500">Permanent after creation and never reusable.</p>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium text-gray-700" htmlFor="package-quantity">Pack quantity</label>
                <input id="package-quantity" required type="number" min="0.001" step="0.001" value={packageQuantity} onChange={(event) => setPackageQuantity(Number(event.target.value))} className="mt-1 block w-full rounded-md border-gray-300 sm:text-sm" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700" htmlFor="package-unit">Unit</label>
                <input id="package-unit" required value={unit} onChange={(event) => setUnit(event.target.value)} className="mt-1 block w-full rounded-md border-gray-300 sm:text-sm" />
              </div>
            </div>
            <div className="flex items-center">
              <input
                id="package-active"
                type="checkbox"
                checked={isActive}
                onChange={(event) => setIsActive(event.target.checked)}
                className="h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
              />
              <label htmlFor="package-active" className="ml-2 block text-sm text-gray-900">
                Active packaging
              </label>
            </div>
            <div className="flex justify-end gap-3 pt-2">
              <button type="button" onClick={onClose} className="btn-secondary" disabled={loading}>Cancel</button>
              <button type="submit" className="btn-primary" disabled={loading || !product}>{loading ? 'Saving...' : sellableUnit ? 'Save packaging' : 'Add packaging'}</button>
            </div>
          </form>
        </Dialog.Panel>
      </div>
    </Dialog>
  );
}
