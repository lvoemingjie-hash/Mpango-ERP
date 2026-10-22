import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { staffService } from '@/services/staffService';
import { STAFF_CAPABILITIES, type StaffTemplate } from '@/types/staff';

function TemplateCard({template,onSaved}:{template:StaffTemplate;onSaved:()=>Promise<void>}){
  const [codes,setCodes]=useState(template.permission_codes);
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState('');
  useEffect(()=>setCodes(template.permission_codes),[template]);
  return <form className="space-y-4 rounded-xl border border-gray-200 bg-white p-4" onSubmit={e=>{e.preventDefault();setBusy(true);void staffService.editTemplate(template,codes).then(onSaved).then(()=>setMessage('Job permissions updated.')).catch(()=>setMessage('Not saved. Reload the current version before retrying.')).finally(()=>setBusy(false));}}>
    <h2 className="text-lg font-semibold capitalize">{template.key}</h2>
    <p className="text-sm text-gray-600">Affects {template.affected_count} employees · version {template.version}</p>
    <div className="grid gap-3 sm:grid-cols-2">{STAFF_CAPABILITIES.map(code=><label className="flex min-w-0 items-center gap-3 rounded border p-3" key={code}>
      <input type="checkbox" checked={codes.includes(code)} disabled={busy} onChange={e=>setCodes(e.target.checked?[...codes,code]:codes.filter(c=>c!==code))}/><span className="break-all text-sm">{code}</span>
    </label>)}</div>
    <p className="text-sm text-gray-600">Payments create is the existing full payment capability, not cash-only. Owner and direct inventory authority cannot be delegated.</p>
    {message&&<p role="status">{message}</p>}<button disabled={busy} className="rounded-lg bg-primary-600 px-4 py-3 text-white disabled:opacity-50">Save permissions for all {template.affected_count} employees</button>
  </form>;
}

export function StaffRolesPage(){
  const [templates,setTemplates]=useState<StaffTemplate[]>([]);
  const [error,setError]=useState('');
  async function load(){setTemplates(await staffService.templates());}
  useEffect(()=>{void load().catch(()=>setError('Unable to load current job permissions.'));},[]);
  return <main className="mx-auto max-w-4xl space-y-6 p-4 sm:p-6"><header><Link className="text-primary-700 underline" to="/users">Back to employees</Link><h1 className="mt-3 text-2xl font-semibold">Job permissions</h1><p className="mt-2 text-gray-600">Edit the three managed templates. Protected administration is never included.</p></header>
    {error&&<p role="alert">{error}</p>}{templates.map(t=><TemplateCard key={t.key} template={t} onSaved={load}/>)}</main>;
}
