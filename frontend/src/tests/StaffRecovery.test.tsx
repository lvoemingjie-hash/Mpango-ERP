import { StrictMode } from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { StaffRecoverCredentialPage } from '@/pages/staff/StaffRecoverCredentialPage';
import { StaffPage } from '@/pages/staff/StaffPage';
import { useAuthStore } from '@/stores/authStore';
import { AxiosError } from 'axios';

const mocks=vi.hoisted(()=>({recover:vi.fn(),requestRecovery:vi.fn(),list:vi.fn()}));
vi.mock('@/services/staffService',()=>({staffService:mocks}));
const member={id:'synthetic-staff',email:'staff@example.com',full_name:'Recovery employee',template_key:'sales',
  employment_state:'active',credential_state:'ready',version:4,is_active:true};
beforeEach(()=>{
  vi.clearAllMocks();mocks.recover.mockResolvedValue({data:{action:'password_recovered',login_required:true}});
  mocks.requestRecovery.mockResolvedValue({data:{action:'recovery_requested',delivery:'accepted_not_confirmed'}});
  mocks.list.mockResolvedValue({items:[member]});
  window.history.replaceState(null,'','/staff/recover-credential#token=synthetic-mailbox-proof');
  useAuthStore.setState({accessToken:'unrelated-owner-session',user:null});
});
afterEach(()=>window.history.replaceState(null,'','/'));
it('scrubs fragment, submits once, clears passwords and leaves unrelated session unchanged',async()=>{
  render(<MemoryRouter><StrictMode><StaffRecoverCredentialPage/></StrictMode></MemoryRouter>);
  expect(window.location.hash).toBe('');
  await userEvent.type(screen.getByLabelText('New password'),'NewEmployeePassword!9');
  await userEvent.type(screen.getByLabelText('Repeat new password'),'NewEmployeePassword!9');
  await userEvent.click(screen.getByRole('button',{name:'Set my new password'}));
  await waitFor(()=>expect(mocks.recover).toHaveBeenCalledTimes(1));
  expect(mocks.recover).toHaveBeenCalledWith('synthetic-mailbox-proof','NewEmployeePassword!9');
  expect(await screen.findByRole('status')).toHaveTextContent('Sign in again');
  expect(screen.getByRole('link',{name:'Go to sign in'})).toHaveAttribute('href','/login');
  expect(useAuthStore.getState().accessToken).toBe('unrelated-owner-session');
  expect(JSON.stringify(localStorage)).not.toContain('synthetic-mailbox-proof');
  expect(JSON.stringify(sessionStorage)).not.toContain('NewEmployeePassword!9');
});
it('rejects query and stored tokens without a service call',()=>{
  window.history.replaceState(null,'','/staff/recover-credential?token=wrong-channel#token=synthetic-mailbox-proof');
  render(<MemoryRouter><StaffRecoverCredentialPage/></MemoryRouter>);
  expect(screen.getByRole('button',{name:'Set my new password'})).toBeDisabled();
  expect(window.location.search).toBe('');expect(window.location.hash).toBe('');
  expect(mocks.recover).not.toHaveBeenCalled();
});
it('keeps failures neutral and clears entered passwords',async()=>{
  mocks.recover.mockRejectedValue(new Error('must-not-echo-runtime-internals'));
  render(<MemoryRouter><StaffRecoverCredentialPage/></MemoryRouter>);
  await userEvent.type(screen.getByLabelText('New password'),'NewEmployeePassword!9');
  await userEvent.type(screen.getByLabelText('Repeat new password'),'NewEmployeePassword!9');
  await userEvent.click(screen.getByRole('button',{name:'Set my new password'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('Recovery not completed');
  expect(screen.queryByText('must-not-echo-runtime-internals')).not.toBeInTheDocument();
  expect(screen.getByLabelText('New password')).toHaveValue('');
});
it('requires matching confirmation before any request',async()=>{
  render(<MemoryRouter><StaffRecoverCredentialPage/></MemoryRouter>);
  await userEvent.type(screen.getByLabelText('New password'),'NewEmployeePassword!9');
  await userEvent.type(screen.getByLabelText('Repeat new password'),'DifferentPassword!9');
  await userEvent.click(screen.getByRole('button',{name:'Set my new password'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('Passwords must match');expect(mocks.recover).not.toHaveBeenCalled();
});
it('Owner sends only own reauthentication and current member version; feedback does not claim inbox delivery',async()=>{
  render(<MemoryRouter><StaffPage/></MemoryRouter>);
  await userEvent.click(await screen.findByRole('button',{name:'Send password recovery'}));
  await userEvent.type(screen.getByLabelText('Your current Owner password'),'SyntheticOwnerPassword!9');
  await userEvent.click(screen.getByRole('button',{name:'Confirm password recovery request'}));
  await waitFor(()=>expect(mocks.requestRecovery).toHaveBeenCalledWith(member,'SyntheticOwnerPassword!9'));
  expect(await screen.findByRole('status')).toHaveTextContent('Delivery to their inbox is not confirmed');
  expect(screen.queryByLabelText('New password')).not.toBeInTheDocument();
});
it('does not offer recovery to disabled or unverified members',async()=>{
  mocks.list.mockResolvedValue({items:[{...member,is_active:false,employment_state:'disabled',credential_state:'pending'}]});
  render(<MemoryRouter><StaffPage/></MemoryRouter>);
  await screen.findByText('Recovery employee');
  expect(screen.queryByRole('button',{name:'Send password recovery'})).not.toBeInTheDocument();
});
it('reports cooldown using fixed copy without echoing server internals or retaining Owner password',async()=>{
  mocks.requestRecovery.mockRejectedValue(new AxiosError('must-not-echo','ERR_BAD_REQUEST',undefined,undefined,
    {data:{code:'STAFF_RECOVERY_RESEND_TOO_SOON'},status:429,statusText:'Too Many Requests',headers:{},config:{} as never}));
  render(<MemoryRouter><StaffPage/></MemoryRouter>);
  await userEvent.click(await screen.findByRole('button',{name:'Send password recovery'}));
  await userEvent.type(screen.getByLabelText('Your current Owner password'),'SyntheticOwnerPassword!9');
  await userEvent.click(screen.getByRole('button',{name:'Confirm password recovery request'}));
  expect(await screen.findByRole('status')).toHaveTextContent('Wait at least 60 seconds');
  expect(screen.getByLabelText('Your current Owner password')).toHaveValue('');
  expect(screen.queryByText('must-not-echo')).not.toBeInTheDocument();
});
