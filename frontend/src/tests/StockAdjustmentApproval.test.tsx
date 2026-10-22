import {beforeEach,expect,it,vi} from 'vitest';
import {render,screen,waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MemoryRouter} from 'react-router-dom';
import {StockAdjustmentPage} from '@/pages/inventory/StockAdjustmentPage';
import {useAuthStore} from '@/stores/authStore';

const mocks=vi.hoisted(()=>({getStocks:vi.fn(),getAdjustmentRequests:vi.fn(),getAdjustmentSnapshot:vi.fn(),submitAdjustment:vi.fn(),decideAdjustment:vi.fn()}));
vi.mock('@/services/inventoryService',()=>({inventoryService:mocks}));
const row={id:'r1',requester_id:'employee',sellable_unit_id:'s1',delta:'-5.00',version:1,status:'pending',result:null,
  payload:{sku_id:'s1',sku_code:'BOX',unit:'box',package_quantity:'12.000',reason:'Damaged stock',reason_kind:'loss'}};
beforeEach(()=>{vi.clearAllMocks();window.history.replaceState({},'','/');
  useAuthStore.setState({user:{id:'owner',email:'owner@example.com',full_name:'Owner',tenant_id:'tenant',tenant_schema:'t_tenant',roles:['admin'],permissions:[],is_owner:true}});
  mocks.getStocks.mockResolvedValue({data:{data:{items:[{sku_id:'s1',sku_code:'BOX',sku_name:'Box product'}]}}});
  mocks.getAdjustmentRequests.mockResolvedValue({items:[row],can_approve:true});
  mocks.getAdjustmentSnapshot.mockResolvedValue({sku_id:'s1',sku_code:'BOX',unit:'box',package_quantity:'12.000',
    quantity_on_hand:'100.00',quantity_reserved:'80.00',stock_revision:8,policy_version:3});
  mocks.submitAdjustment.mockResolvedValue({id:'new',status:'pending'});
  mocks.decideAdjustment.mockResolvedValue({...row,status:'approved_applied'});
});

it('submits an unchanged decimal string and explicit snapshots, never the old endpoint',async()=>{
  render(<MemoryRouter><StockAdjustmentPage/></MemoryRouter>);
  await userEvent.selectOptions(await screen.findByLabelText('Product'),'s1');
  await userEvent.click(screen.getByRole('button',{name:'Load current stock snapshot'}));
  await screen.findByText(/Unit: box/);
  await userEvent.type(screen.getByLabelText('Signed quantity'),'-5.00');
  await userEvent.type(screen.getByLabelText('Reason'),'Damaged stock');
  await userEvent.click(screen.getByRole('button',{name:'Submit for approval'}));
  await waitFor(()=>expect(mocks.submitAdjustment).toHaveBeenCalledOnce());
  expect(mocks.submitAdjustment).toHaveBeenCalledWith({sellable_unit_id:'s1',quantity_delta:'-5.00',reason_kind:'correction',reason:'Damaged stock',
    expected_stock_revision:8,expected_policy_version:3},expect.any(String),false);
  expect(await screen.findByRole('status')).toHaveTextContent('Stock is unchanged until approval');
});

it('never offers self approval, including to Owner',async()=>{
  mocks.getAdjustmentRequests.mockResolvedValue({items:[{...row,requester_id:'owner'}],can_approve:true});
  render(<MemoryRouter><StockAdjustmentPage/></MemoryRouter>);
  await screen.findByText('You cannot approve your own request.');
  expect(screen.queryByRole('button',{name:'Approve'})).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole('button',{name:'Withdraw'}));
  await waitFor(()=>expect(mocks.decideAdjustment).toHaveBeenCalledWith(expect.objectContaining({id:'r1'}),'withdraw',expect.any(String),''));
});

it('does not offer approval merely because a job has the capability',async()=>{
  mocks.getAdjustmentRequests.mockResolvedValue({items:[row],can_approve:false});
  render(<MemoryRouter><StockAdjustmentPage/></MemoryRouter>);
  await screen.findByText('Damaged stock');
  expect(screen.queryByRole('button',{name:'Approve'})).not.toBeInTheDocument();
});

it('retains a stale failure and does not automatically retry or recalculate',async()=>{
  mocks.decideAdjustment.mockRejectedValue(new Error('STOCK_CHANGED'));
  render(<MemoryRouter><StockAdjustmentPage/></MemoryRouter>);
  await userEvent.click(await screen.findByRole('button',{name:'Approve'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('No automatic retry');
  expect(mocks.decideAdjustment).toHaveBeenCalledOnce();
  expect(mocks.getAdjustmentSnapshot).not.toHaveBeenCalled();
});

it('does not expose explicit Owner direct mode to a named employee approver',async()=>{
  useAuthStore.setState({user:{id:'employee2',email:'employee@example.com',full_name:'Employee',tenant_id:'tenant',tenant_schema:'t_tenant',
    roles:['staff_warehouse'],permissions:['inventory:adjustments:read','inventory:adjustments:request','inventory:adjustments:approve'],staff_state:'active',is_owner:false}});
  render(<MemoryRouter><StockAdjustmentPage/></MemoryRouter>);
  await screen.findByText('Damaged stock');
  expect(screen.queryByLabelText(/Explicit Owner direct/)).not.toBeInTheDocument();
});
