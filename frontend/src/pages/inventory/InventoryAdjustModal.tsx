import { Dialog } from '@headlessui/react';
import { Link } from 'react-router-dom';

export interface AdjustFormData { sku_code:string; quantity:number; reason:string }
interface Props {
  isOpen:boolean; onClose:()=>void; onSubmit:(data:AdjustFormData)=>Promise<void>; initialSkuCode?:string;
}

/** Compatibility entry only; this component never invokes the retired writer. */
export function InventoryAdjustModal({isOpen,onClose,initialSkuCode}:Props) {
  return <Dialog open={isOpen} onClose={onClose} className="relative z-50">
    <div className="fixed inset-0 bg-black/30" aria-hidden="true"/>
    <div className="fixed inset-0 flex items-center justify-center p-4">
      <Dialog.Panel className="w-full max-w-md space-y-4 rounded-xl bg-white p-5 shadow-xl">
        <Dialog.Title className="text-lg font-semibold">Use stock adjustment requests</Dialog.Title>
        <p>Manual changes now use named approval or the explicit Owner direct command. The old adjustment form is retired.</p>
        {initialSkuCode&&<p>Selected product: {initialSkuCode}</p>}
        <Link className="btn-primary inline-block" to="/inventory/adjustments" onClick={onClose}>Open adjustment requests</Link>
        <button type="button" className="btn-secondary" onClick={onClose}>Close</button>
      </Dialog.Panel>
    </div>
  </Dialog>;
}
