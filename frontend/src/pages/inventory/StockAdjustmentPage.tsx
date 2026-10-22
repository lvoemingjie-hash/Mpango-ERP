import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { inventoryService } from '@/services/inventoryService';
import { useAuthStore } from '@/stores/authStore';
import { can } from '@/utils/permissions';
import { normalizeApiError } from '@/utils/errorHandling';
import type { AdjustmentSnapshot, StockAdjustment, StockView } from '@/types/inventory';

export function StockAdjustmentPage() {
  const user=useAuthStore(s=>s.user);
  const [stocks,setStocks]=useState<StockView[]>([]);
  const [rows,setRows]=useState<StockAdjustment[]>([]);
  const [canApprove,setCanApprove]=useState(false);
  const [sku,setSku]=useState(new URLSearchParams(window.location.search).get('sku')||'');
  const [snapshot,setSnapshot]=useState<AdjustmentSnapshot|null>(null);
  const [delta,setDelta]=useState('');
  const [reason,setReason]=useState('');
  const [kind,setKind]=useState('correction');
  const [direct,setDirect]=useState(false);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [message,setMessage]=useState('');
  const key=useRef(crypto.randomUUID());
  const decisions=useRef<Record<string,string>>({});
  const canRequest=can(user,'inventory:adjustments:request');
  async function load() {
    const [stock,response]=await Promise.all([inventoryService.getStocks(),inventoryService.getAdjustmentRequests()]);
    setStocks(stock.data.data.items);setRows(response.items);setCanApprove(response.can_approve);
  }
  useEffect(()=>{void load().catch(e=>setError(normalizeApiError(e)));},[]);
  async function refreshSnapshot() {
    if(!sku)return;
    setBusy(true);setSnapshot(null);setError('');
    try {setSnapshot(await inventoryService.getAdjustmentSnapshot(sku));key.current=crypto.randomUUID();}
    catch(e){setError(normalizeApiError(e));}finally{setBusy(false);}
  }
  async function decide(row:StockAdjustment,action:'approve'|'reject'|'withdraw') {
    setBusy(true);setError('');setMessage('');
    const lookup=row.id+':'+action;
    decisions.current[lookup]??=crypto.randomUUID();
    try {const result=await inventoryService.decideAdjustment(row,action,decisions.current[lookup],action==='reject'?'Rejected by approver':'');
      setMessage('Request '+result.status.replace(/_/g,' ')+'.');await load();}
    catch(e){setError(normalizeApiError(e));}finally{setBusy(false);}
  }
  return <main className="mx-auto max-w-3xl space-y-5 p-4 sm:p-6">
    <header className="space-y-3"><Link className="text-primary-700 underline" to="/inventory">Back to stock</Link>
      <h1 className="text-2xl font-semibold">Stock adjustment requests</h1>
      <p className="text-gray-600">Requests do not change stock. Another named approver must approve. Changed stock or policy requires withdrawal and a new request.</p>
      {user?.is_owner&&<Link className="inline-block text-primary-700 underline" to="/settings/stock-approval">Stock approval settings</Link>}
    </header>
    {error&&<p role="alert" className="break-words rounded bg-red-50 p-3 text-red-800">{error} No automatic retry was made. Reload current data before deciding what to do.</p>}
    {message&&<p role="status" className="rounded bg-green-50 p-3">{message}</p>}
    {canRequest&&<form className="space-y-4 rounded-xl border bg-white p-4" onSubmit={async e=>{e.preventDefault();if(!snapshot)return;
      setBusy(true);setError('');setMessage('');try {const result=await inventoryService.submitAdjustment({sellable_unit_id:sku,
        quantity_delta:delta,reason_kind:kind,reason,expected_stock_revision:snapshot.stock_revision,
        expected_policy_version:snapshot.policy_version},key.current,direct);
        setMessage(result.status==='applied_direct'?'Owner direct adjustment applied.':'Request submitted. Stock is unchanged until approval.');
        setSnapshot(null);setDelta('');setReason('');key.current=crypto.randomUUID();await load();
      }catch(err){setError(normalizeApiError(err));}finally{setBusy(false);}}}>
      <h2 className="text-lg font-semibold">New adjustment</h2>
      <label className="block">Product<select aria-label="Product" className="mt-1 min-h-12 w-full rounded border p-2" value={sku} disabled={busy}
        onChange={e=>{setSku(e.target.value);setSnapshot(null);}}><option value="">Select a product</option>
        {stocks.map(s=><option key={s.sku_id} value={s.sku_id}>{s.sku_name} · {s.sku_code}</option>)}</select></label>
      <button type="button" disabled={busy||!sku} onClick={()=>void refreshSnapshot()} className="btn-secondary">Load current stock snapshot</button>
      {snapshot&&<p className="rounded bg-gray-50 p-3 text-sm">Unit: {snapshot.unit} · Pack: {snapshot.package_quantity}<br/>
        On hand: {snapshot.quantity_on_hand} · Reserved: {snapshot.quantity_reserved}<br/>Stock revision {snapshot.stock_revision} · Policy {snapshot.policy_version}</p>}
      <label className="block">Reason type<select className="mt-1 min-h-12 w-full rounded border p-2" value={kind} disabled={busy} onChange={e=>setKind(e.target.value)}>
        <option value="correction">Correction (+ or -)</option><option value="loss">Loss (-)</option><option value="shrink">Shrinkage (-)</option><option value="gain">Gain (+)</option></select></label>
      <label className="block">Signed quantity<input className="mt-1 min-h-12 w-full rounded border p-2" inputMode="decimal" type="text" value={delta}
        disabled={busy} onChange={e=>setDelta(e.target.value)} required placeholder="-5.00 or 10.00"/></label>
      <p className="text-sm text-gray-600">Quantity is in the displayed selling unit, at most two decimal places. It is never rounded.</p>
      <label className="block">Reason<textarea className="mt-1 w-full rounded border p-2" value={reason} maxLength={1000} required disabled={busy} onChange={e=>setReason(e.target.value)}/></label>
      {user?.is_owner&&<label className="flex min-h-12 items-center gap-3"><input type="checkbox" checked={direct} disabled={busy} onChange={e=>{setDirect(e.target.checked);key.current=crypto.randomUUID();}}/>
        Explicit Owner direct adjustment (if enabled)</label>}
      <button className="btn-primary w-full sm:w-auto" disabled={busy||!snapshot}>{busy?'Submitting…':direct?'Apply Owner direct adjustment':'Submit for approval'}</button>
    </form>}
    <div className="flex items-center justify-between gap-3"><h2 className="text-lg font-semibold">Requests</h2><button className="btn-secondary" disabled={busy} onClick={()=>{setError('');void load().catch(e=>setError(normalizeApiError(e)));}}>Reload requests</button></div>
    {rows.length===0&&<p>No visible requests yet.</p>}
    <div className="space-y-4">{rows.map(row=><article key={row.id} className="space-y-3 rounded-xl border bg-white p-4">
      <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="font-semibold">{row.payload.sku_code}</h3><span className="rounded bg-gray-100 px-2 py-1 text-sm">{row.status.replace(/_/g,' ')}</span></div>
      <p>{row.delta} {row.payload.unit} · pack {row.payload.package_quantity}</p><p className="break-words">{row.payload.reason}</p>
      {row.result?.quantity_after&&<p>Stock: {row.result.quantity_before} → {row.result.quantity_after}</p>}
      {row.status==='pending'&&<div className="flex flex-wrap gap-3">
        {row.requester_id===user?.id?<><p className="w-full text-sm text-gray-600">You cannot approve your own request.</p><button className="btn-secondary" disabled={busy} onClick={()=>void decide(row,'withdraw')}>Withdraw</button></>:
          canApprove&&<><button className="btn-primary" disabled={busy} onClick={()=>void decide(row,'approve')}>Approve</button><button className="btn-secondary" disabled={busy} onClick={()=>void decide(row,'reject')}>Reject</button></>}
      </div>}
    </article>)}</div>
  </main>;
}
