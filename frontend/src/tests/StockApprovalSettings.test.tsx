import {beforeEach,expect,it,vi} from 'vitest';
import {render,screen,waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MemoryRouter} from 'react-router-dom';
import {StockApprovalSettingsPage} from '@/pages/inventory/StockApprovalSettingsPage';
const mocks=vi.hoisted(()=>({getAdjustmentPolicy:vi.fn(),saveAdjustmentPolicy:vi.fn(),list:vi.fn(),templates:vi.fn()}));
vi.mock('@/services/inventoryService',()=>({inventoryService:mocks}));
vi.mock('@/services/staffService',()=>({staffService:mocks}));
beforeEach(()=>{vi.clearAllMocks();mocks.getAdjustmentPolicy.mockResolvedValue({approver_ids:['owner'],policy_version:4,owner_direct_enabled:true});
  mocks.list.mockResolvedValue({owner_id:'owner',items:[{id:'employee',full_name:'Ready warehouse',is_active:true,credential_state:'ready',employment_state:'active',template_key:'warehouse'},
    {id:'pending',full_name:'Pending employee',is_active:false,credential_state:'pending',employment_state:'invited',template_key:'warehouse'}]});
  mocks.templates.mockResolvedValue([{key:'warehouse',permission_codes:['inventory:adjustments:approve']}]);
  mocks.saveAdjustmentPolicy.mockResolvedValue({approver_ids:['owner','employee'],policy_version:5,owner_direct_enabled:false});});
it('selects named ready staff and sends the exact expected policy version',async()=>{
  render(<MemoryRouter><StockApprovalSettingsPage/></MemoryRouter>);
  await userEvent.click(await screen.findByLabelText('Ready warehouse'));
  expect(screen.queryByLabelText('Pending employee')).not.toBeInTheDocument();
  await userEvent.click(screen.getByLabelText(/Allow explicit Owner/));
  await userEvent.click(screen.getByRole('button',{name:'Save policy'}));
  await waitFor(()=>expect(mocks.saveAdjustmentPolicy).toHaveBeenCalledWith({approver_ids:['owner','employee'],owner_direct_enabled:false,expected_policy_version:4}));
  expect(await screen.findByRole('status')).toHaveTextContent('saved');
});
it('does not retry a stale policy save',async()=>{
  mocks.saveAdjustmentPolicy.mockRejectedValue(new Error('POLICY_CHANGED'));
  render(<MemoryRouter><StockApprovalSettingsPage/></MemoryRouter>);
  await userEvent.click(await screen.findByRole('button',{name:'Save policy'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('Reload the current policy');
  expect(mocks.saveAdjustmentPolicy).toHaveBeenCalledOnce();
});
