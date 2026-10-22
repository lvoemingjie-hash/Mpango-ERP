import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { staffService } from '@/services/staffService';
import type { StaffMember, StaffTemplateKey } from '@/types/staff';

const field='w-full rounded-lg border border-gray-300 px-3 py-2 text-base';
const button='rounded-lg bg-primary-600 px-4 py-3 font-medium text-white disabled:opacity-50';

export function StaffPage() {
  const [members,setMembers]=useState<StaffMember[]>([]);
  const [email,setEmail]=useState('');
  const [name,setName]=useState('');
  const [job,setJob]=useState<StaffTemplateKey>('sales');
  const [adopt,setAdopt]=useState(false);
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState('');
  const [invite,setInvite]=useState<StaffMember|null>(null);
  const [password,setPassword]=useState('');
  const key=useRef(crypto.randomUUID());
  async function load(){ setMembers((await staffService.list()).items); }
  useEffect(()=>{let active=true; void staffService.list().then(data=>{if(active)setMembers(data.items);}).catch(()=>{if(active)setMessage('Unable to load employees. Refresh your session.');});return()=>{active=false;};},[]);
  async function act(action:()=>Promise<unknown>,success:string){
    setBusy(true);setMessage('');
    try{await action();await load();setMessage(success);}catch{setMessage('Action not completed. Reload current permissions and versions before retrying.');}
    finally{setBusy(false);setPassword('');}
  }
  return <main className="mx-auto max-w-4xl space-y-6 p-4 sm:p-6">
    <header><p className="text-sm text-gray-500">Team access</p><h1 className="text-2xl font-semibold">Employees</h1>
      <p className="mt-2 text-gray-600">You manage employment and roles. Employees prove their own identity and keep their own passwords.</p>
      <Link className="mt-3 inline-block text-primary-700 underline" to="/users/roles">Edit job permissions</Link></header>
    {message&&<p role="status" className="rounded-lg bg-gray-100 p-3">{message}</p>}
    <form className="space-y-4 rounded-xl border border-gray-200 bg-white p-4" onSubmit={e=>{e.preventDefault();void act(async()=>{
      await staffService.create({email,full_name:name,template_key:job,adopt_existing:adopt},key.current);
      key.current=crypto.randomUUID();setEmail('');setName('');setAdopt(false);
    },'Employee created as pending. Send an invitation to their own email below.');}}>
      <h2 className="text-lg font-semibold">Add employee</h2>
      <label className="block">Full name<input required maxLength={255} className={field} value={name} onChange={e=>setName(e.target.value)}/></label>
      <label className="block">Employee email<input required type="email" autoComplete="off" className={field} value={email} onChange={e=>setEmail(e.target.value)}/></label>
      <label className="block">Job<select className={field} value={job} onChange={e=>setJob(e.target.value as StaffTemplateKey)}><option value="warehouse">Warehouse</option><option value="sales">Sales</option><option value="finance">Finance</option></select></label>
      <label className="flex items-start gap-3"><input type="checkbox" className="mt-1" checked={adopt} onChange={e=>setAdopt(e.target.checked)}/><span>I explicitly approve converting an existing local non-customer account to this managed job.</span></label>
      <button className={button} disabled={busy}>Create pending employee</button>
    </form>
    <section className="space-y-3" aria-label="Employees">
      {members.length===0&&<p className="text-gray-500">No managed employees yet. Your Owner identity is protected separately.</p>}
      {members.map(member=><article key={member.id} className="min-w-0 space-y-3 rounded-xl border border-gray-200 bg-white p-4">
        <div><h2 className="font-semibold">{member.full_name||member.email}</h2><p className="break-all text-sm text-gray-600">{member.email}</p></div>
        <p className="text-sm">{member.employment_state} · {member.credential_state==='ready'?'Identity verified':'Waiting for employee proof'} · version {member.version}</p>
        <label className="block">Current job<select className={field} value={member.template_key} disabled={busy} onChange={e=>void act(()=>staffService.edit(member,{template_key:e.target.value as StaffTemplateKey}),'Role updated. Current permissions apply to new requests.')}><option value="warehouse">Warehouse</option><option value="sales">Sales</option><option value="finance">Finance</option></select></label>
        <div className="flex flex-wrap gap-3">
          {member.employment_state!=='disabled'&&<button className={button} disabled={busy} onClick={()=>{setInvite(member);setPassword('');}}>Send invitation</button>}
          <button disabled={busy} className="rounded-lg border px-4 py-3" onClick={()=>void act(()=>staffService.edit(member,{is_active:member.employment_state==='disabled'}),member.employment_state==='disabled'?'Employment restored. A fresh invitation and employee proof are still required.':'Employment disabled. Unused invitations revoked.')}>
            {member.employment_state==='disabled'?'Restore employment':'Disable employment'}</button>
        </div>
        {invite?.id===member.id&&<form className="space-y-3 border-t pt-3" onSubmit={e=>{e.preventDefault();void act(async()=>{await staffService.invite(member,password);setInvite(null);},'Invitation sent to the employee email. No credential link is available to you.');}}>
          <label className="block">Your current Owner password<input required type="password" autoComplete="current-password" className={field} value={password} onChange={e=>setPassword(e.target.value)}/></label>
          <button className={button} disabled={busy}>Confirm email invitation</button>
          <button type="button" className="ml-3 underline" onClick={()=>{setInvite(null);setPassword('');}}>Cancel</button>
        </form>}
      </article>)}
    </section>
  </main>;
}
