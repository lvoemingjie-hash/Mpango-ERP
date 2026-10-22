import { StrictMode } from 'react';
import { beforeEach, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { StaffSetupCredentialPage } from '@/pages/staff/StaffSetupCredentialPage';
import { useAuthStore } from '@/stores/authStore';
const consume=vi.hoisted(()=>vi.fn());
vi.mock('@/services/staffService',()=>({staffService:{consume}}));
beforeEach(()=>{vi.clearAllMocks();consume.mockResolvedValue({action:'joined'});
  window.history.replaceState(null,'','/staff/setup-credential#token=synthetic-mailbox-proof');
  useAuthStore.setState({accessToken:'unrelated-owner-session',user:null});
});
it('scrubs fragment even in StrictMode and consumes only a JSON-body service call without taking over the session',async()=>{
  render(<StrictMode><StaffSetupCredentialPage/></StrictMode>);
  expect(window.location.hash).toBe('');
  await userEvent.type(screen.getByLabelText('Your password'),'ExistingPassword!9');
  await userEvent.type(screen.getByLabelText('Repeat password'),'ExistingPassword!9');
  await userEvent.click(screen.getByRole('button',{name:'Join with my email proof'}));
  await waitFor(()=>expect(consume).toHaveBeenCalledWith('synthetic-mailbox-proof','ExistingPassword!9'));
  expect(await screen.findByRole('status')).toHaveTextContent('existing browser session has been left unchanged');
  expect(useAuthStore.getState().accessToken).toBe('unrelated-owner-session');
  expect(localStorage.getItem('mpango-auth')).not.toContain('synthetic-mailbox-proof');
});
it('shows fixed neutral failure text and never persists the proof or password',async()=>{
  consume.mockRejectedValue(new Error('must-not-echo-internal-details'));
  render(<StaffSetupCredentialPage/>);
  await userEvent.type(screen.getByLabelText('Your password'),'ExistingPassword!9');
  await userEvent.type(screen.getByLabelText('Repeat password'),'ExistingPassword!9');
  await userEvent.click(screen.getByRole('button',{name:'Join with my email proof'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('Unable to complete joining');
  expect(screen.queryByText('must-not-echo-internal-details')).not.toBeInTheDocument();
  expect(screen.getByLabelText('Your password')).toHaveValue('');
});
it('refuses missing proof rather than finding it in query parameters or storage',()=>{
  window.history.replaceState(null,'','/staff/setup-credential?token=wrong-channel');
  render(<StaffSetupCredentialPage/>);
  expect(screen.getByRole('button',{name:'Join with my email proof'})).toBeDisabled();
  expect(consume).not.toHaveBeenCalled();
});
