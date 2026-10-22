import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { inventoryService } from '@/services/inventoryService';
import { staffService } from '@/services/staffService';
import type { AdjustmentPolicy } from '@/types/inventory';
import { normalizeApiError } from '@/utils/errorHandling';

export function StockApprovalSettingsPage() {
  const [policy,setPolicy]=useState<AdjustmentPolicy|null>(null);
  const [people,setPeople]=useState<{id:string;name:string}[]>([]);
  const [error,setError]=useState('');
  const [message,setMessage]=useState('');
  const [busy,setBusy]=useState(false);
  async function load() {
    const [p,staff,templates]=await Promise.all([inventoryService.getAdjustmentPolicy(),staffService.list(),staffService.templates()]);
    setPolicy(p);
    setPeople([{id:staff.owner_id,name:'Owner'},...staff.items.filter(m=>p.approver_ids.includes(m.id)||(m.is_active&&m.credential_state==='ready'
      &&m.employment_state==='active'&&templates.find(t=>t.key===m.template_key)?.permission_codes.includes('inventory:adjustments:approve')))
      .map(m=>({id:m.id,name:(m.full_name||m.email)+(!m.is_active||m.credential_state!=='ready'?' (not eligible; remove from list)':'')}))]);
  }
  useEffect(()=>{void load().catch(e=>setError(normalizeApiError(e)));},[]);
  return <main className="mx-auto max-w-2xl space-y-5 p-4 sm:p-6">
    <Link className="text-primary-700 underline" to="/inventory/adjustments">Back to stock requests</Link>
    <h1 className="text-2xl font-semibold">Stock approval settings</h1>
    <p className="text-gray-600">Choose named approvers. A job permission alone never grants approval. Nobody, including Owner, can approve their own request.</p>
    {error&&<p role="alert" className="rounded bg-red-50 p-3 text-red-800">{error} Reload the current policy before retrying.</p>}
    {message&&<p role="status">{message}</p>}
    {policy&&<form className="space-y-5 rounded-xl border bg-white p-4" onSubmit={async e=>{e.preventDefault();setBusy(true);setError('');setMessage('');
      try {const next=await inventoryService.saveAdjustmentPolicy({approver_ids:policy.approver_ids,
        owner_direct_enabled:policy.owner_direct_enabled,expected_policy_version:policy.policy_version});setPolicy(next);setMessage('Stock approval policy saved. Existing pending requests now require resubmission.');}
      catch(err){setError(normalizeApiError(err));}finally{setBusy(false);}}}>
      <p className="text-sm">Policy version {policy.policy_version}</p>
      <fieldset disabled={busy} className="space-y-3"><legend className="mb-3 font-medium">Named approvers</legend>
        {people.map(person=><label key={person.id} className="flex min-h-12 items-center gap-3 rounded border p-3">
          <input type="checkbox" checked={policy.approver_ids.includes(person.id)} onChange={e=>setPolicy({...policy,
            approver_ids:e.target.checked?[...policy.approver_ids,person.id]:policy.approver_ids.filter(id=>id!==person.id)})}/>
          <span className="break-all">{person.name}</span></label>)}
      </fieldset>
      <label className="flex min-h-12 items-start gap-3 rounded border p-3"><input type="checkbox" disabled={busy}
        checked={policy.owner_direct_enabled} onChange={e=>setPolicy({...policy,owner_direct_enabled:e.target.checked})}/>
        <span>Allow explicit Owner direct adjustment. This is audited as direct, not as an approval.</span></label>
      <div className="flex flex-wrap gap-3"><button className="btn-primary" disabled={busy||policy.approver_ids.length===0}>Save policy</button>
        <button type="button" className="btn-secondary" disabled={busy} onClick={()=>{setError('');void load().catch(e=>setError(normalizeApiError(e)));}}>Reload policy</button></div>
    </form>}
  </main>;
}
