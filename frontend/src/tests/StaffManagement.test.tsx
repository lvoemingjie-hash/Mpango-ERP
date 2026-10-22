import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { StaffPage } from '@/pages/staff/StaffPage';
import { OwnerRoute } from '@/router/guards';
import { useAuthStore } from '@/stores/authStore';
import { can, canAny } from '@/utils/permissions';
import { api, refreshCurrentAuthority } from '@/services/api';
import { AxiosError } from 'axios';
import type { AxiosAdapter } from 'axios';

const mocks=vi.hoisted(()=>({ list:vi.fn(),create:vi.fn(),edit:vi.fn(),invite:vi.fn() }));
vi.mock('@/services/staffService',()=>({staffService:mocks}));
const member={id:'staff-1',email:'staff@example.com',full_name:'Worker',template_key:'sales',
  employment_state:'invited',credential_state:'pending',version:2,is_active:false};
const owner={id:'owner',email:'owner@example.com',full_name:'Owner',tenant_id:'tenant',
  tenant_schema:'t_tenant',roles:['admin'],permissions:[],is_owner:true};
const originalAdapter=api.defaults.adapter;
afterEach(()=>{api.defaults.adapter=originalAdapter;});

beforeEach(()=>{
  vi.clearAllMocks();
  mocks.list.mockResolvedValue({items:[member],owner_id:'owner',authz_revision:1});
  mocks.create.mockResolvedValue(member);
  mocks.invite.mockResolvedValue({action:'invitation_sent',member});
  mocks.edit.mockResolvedValue(member);
  useAuthStore.setState({accessToken:'session',user:owner});
});
describe('M1 employee management',()=>{
  it('uses pending email proof without an Owner-visible token',async()=>{
    render(<MemoryRouter><StaffPage/></MemoryRouter>);
    await screen.findByText('Worker');
    expect(screen.queryByText(/credential link:/i)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button',{name:'Send invitation'}));
    await userEvent.type(screen.getByLabelText('Your current Owner password'),'synthetic-owner-proof');
    await userEvent.click(screen.getByRole('button',{name:'Confirm email invitation'}));
    await waitFor(()=>expect(mocks.invite).toHaveBeenCalledWith(member,'synthetic-owner-proof'));
    expect(await screen.findByRole('status')).toHaveTextContent('No credential link is available');
  });
  it('creates with a persistent key and no employee password field',async()=>{
    render(<MemoryRouter><StaffPage/></MemoryRouter>);
    await userEvent.type(screen.getByLabelText('Full name'),'New worker');
    await userEvent.type(screen.getByLabelText('Employee email'),'new@example.com');
    await userEvent.click(screen.getByRole('button',{name:'Create pending employee'}));
    await waitFor(()=>expect(mocks.create).toHaveBeenCalledOnce());
    expect(mocks.create.mock.calls[0][0]).toEqual({email:'new@example.com',full_name:'New worker',template_key:'sales',adopt_existing:false});
    expect(mocks.create.mock.calls[0][1]).toMatch(/^[0-9a-f-]{36}$/);
    expect(screen.queryByLabelText('Employee password')).not.toBeInTheDocument();
  });
  it('requires actual Owner proof, not admin aliases, in the route',async()=>{
    useAuthStore.setState({user:{...owner,is_owner:false}});
    render(<MemoryRouter initialEntries={['/users']}><Routes><Route path="/" element={<p>Denied</p>}/>
      <Route element={<OwnerRoute/>}><Route path="/users" element={<StaffPage/>}/></Route></Routes></MemoryRouter>);
    expect(await screen.findByText('Denied')).toBeInTheDocument();
    expect(mocks.list).not.toHaveBeenCalled();
  });
  it('never grants protected authority through canAny or stale staff aliases',()=>{
    expect(canAny({...owner,is_owner:false},['inventory:update'])).toBe(false);
    expect(can({...owner,is_owner:false,staff_state:'active',permissions:[]},'orders:ship')).toBe(false);
    expect(can({...owner,is_owner:false,staff_state:'disabled',permissions:['orders:ship']},'orders:ship')).toBe(false);
  });
  it('discards a late authority response from the previous tenant/session',async()=>{
    let release!:()=>void;
    api.defaults.adapter=(async config=>{
      if(config.headers.get('Authorization')==='Bearer session') await new Promise<void>(resolve=>{release=resolve;});
      const next=config.headers.get('Authorization')==='Bearer switched'
        ? {...owner,id:'other',tenant_id:'other-tenant',tenant_schema:'t_other',is_owner:false}
        : owner;
      return {data:{success:true,data:next},status:200,statusText:'OK',headers:{},config};
    }) as AxiosAdapter;
    const previous=refreshCurrentAuthority();
    await waitFor(()=>expect(release).toBeTypeOf('function'));
    useAuthStore.setState({accessToken:'switched',user:{...owner,id:'other',tenant_id:'other-tenant',tenant_schema:'t_other',is_owner:false}});
    await refreshCurrentAuthority();
    release();
    await previous;
    expect(useAuthStore.getState().user?.id).toBe('other');
    expect(useAuthStore.getState().user?.is_owner).toBe(false);
  });
  it('refreshes after 403 but never resends the refused write',async()=>{
    let writes=0;
    api.defaults.adapter=(async config=>{
      if(config.method==='post'){
        writes++;
        throw new AxiosError('refused','ERR_BAD_REQUEST',config,undefined,{data:{},status:403,statusText:'Forbidden',headers:{},config});
      }
      return {data:{success:true,data:{...owner,is_owner:false,permissions:[]}},status:200,statusText:'OK',headers:{},config};
    }) as AxiosAdapter;
    await expect(api.post('/staff',{untrusted:true})).rejects.toBeInstanceOf(AxiosError);
    await waitFor(()=>expect(useAuthStore.getState().user?.is_owner).toBe(false));
    expect(writes).toBe(1);
  });
});
