import { useEffect, useState } from 'react';
import { staffService } from '@/services/staffService';

export function StaffSetupCredentialPage(){
  const [token,setToken]=useState(()=>new URLSearchParams(window.location.hash.slice(1)).get('token')||'');
  const [password,setPassword]=useState('');
  const [confirm,setConfirm]=useState('');
  const [busy,setBusy]=useState(false);
  const [done,setDone]=useState(false);
  const [message,setMessage]=useState('');
  useEffect(()=>{window.history.replaceState(window.history.state,'',window.location.pathname+window.location.search);},[]);
  return <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-5 p-5">
    <h1 className="text-2xl font-semibold">Join your team</h1>
    <p className="text-gray-600">This is your personal email invitation. If you already use Mpango, enter your existing password. Your employer cannot set it for you.</p>
    {done?<p role="status">You have joined. Sign in from your own session. Any existing browser session has been left unchanged.</p>:<form className="space-y-4" onSubmit={e=>{e.preventDefault();setMessage('');if(password!==confirm){setMessage('Passwords must match.');return;}setBusy(true);
      void staffService.consume(token,password).then(()=>{setDone(true);setToken('');}).catch(()=>setMessage('Unable to complete joining. Check your invitation and existing password, or use personal password recovery.')).finally(()=>{setBusy(false);setPassword('');setConfirm('');});}}>
      <label className="block">Your password<input required minLength={8} autoComplete="new-password" type="password" className="mt-1 w-full rounded-lg border px-3 py-3 text-base" value={password} onChange={e=>setPassword(e.target.value)}/></label>
      <label className="block">Repeat password<input required minLength={8} autoComplete="new-password" type="password" className="mt-1 w-full rounded-lg border px-3 py-3 text-base" value={confirm} onChange={e=>setConfirm(e.target.value)}/></label>
      <button disabled={busy||!token} className="w-full rounded-lg bg-primary-600 px-4 py-3 text-white disabled:opacity-50">Join with my email proof</button>
    </form>}
    {message&&<p role="alert">{message}</p>}{!token&&!done&&<p role="alert">Open the full personal invitation from your email.</p>}
  </main>;
}
