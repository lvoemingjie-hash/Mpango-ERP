import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { staffService } from '@/services/staffService';

export function StaffRecoverCredentialPage(){
  const [token,setToken]=useState(()=>window.location.search ? '' : new URLSearchParams(window.location.hash.slice(1)).get('token')||'');
  const [password,setPassword]=useState('');
  const [confirm,setConfirm]=useState('');
  const [busy,setBusy]=useState(false);
  const [done,setDone]=useState(false);
  const [message,setMessage]=useState('');
  useEffect(()=>{window.history.replaceState(window.history.state,'',window.location.pathname);},[]);
  return <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-5 p-5">
    <h1 className="text-2xl font-semibold">Recover your password</h1>
    <p>Only you can choose your password. This changes your shared password for current active accounts; employment, roles and customer access stay unchanged.</p>
    {done?<section role="status"><p>Password changed. Sign in again with your new password. Other existing browser sessions have not been replaced.</p><p>If this browser is already signed in, sign out of that session or open a private window to sign in as yourself.</p><Link className="underline" to="/login">Go to sign in</Link></section>:
      <form className="space-y-4" onSubmit={e=>{e.preventDefault();if(busy)return;setMessage('');
        if(password!==confirm){setMessage('Passwords must match.');return;}
        setBusy(true);void staffService.recover(token,password).then(()=>{setDone(true);setToken('');})
          .catch(()=>setMessage('Recovery not completed or could not be confirmed. The link may be expired, replaced or no longer eligible. Try signing in with your new password before asking your Owner for a new link.'))
          .finally(()=>{setBusy(false);setPassword('');setConfirm('');});}}>
        <label className="block">New password<input required minLength={8} maxLength={72} autoComplete="new-password" type="password" className="mt-1 w-full rounded-lg border px-3 py-3 text-base" value={password} onChange={e=>setPassword(e.target.value)}/></label>
        <label className="block">Repeat new password<input required minLength={8} maxLength={72} autoComplete="new-password" type="password" className="mt-1 w-full rounded-lg border px-3 py-3 text-base" value={confirm} onChange={e=>setConfirm(e.target.value)}/></label>
        <button disabled={busy||!token} className="w-full rounded-lg bg-primary-600 px-4 py-3 text-white disabled:opacity-50">Set my new password</button>
      </form>}
    {message&&<p role="alert">{message}</p>}
    {!token&&!done&&<p role="alert">Open the complete recovery link from your email. Query or stored tokens are not accepted.</p>}
  </main>;
}
