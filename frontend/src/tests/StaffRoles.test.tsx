import { beforeEach, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { StaffRolesPage } from '@/pages/staff/StaffRolesPage';
import { STAFF_CAPABILITIES } from '@/types/staff';
const mocks=vi.hoisted(()=>({templates:vi.fn(),editTemplate:vi.fn()}));
vi.mock('@/services/staffService',()=>({staffService:mocks}));
const template={key:'warehouse',version:4,affected_count:3,permission_codes:['inventory:read']};
beforeEach(()=>{vi.clearAllMocks();mocks.templates.mockResolvedValue([template]);mocks.editTemplate.mockResolvedValue([template]);});
it('shows affected employees and sends only the closed capability set with the current version',async()=>{
  render(<MemoryRouter><StaffRolesPage/></MemoryRouter>);
  await screen.findByText('Affects 3 employees · version 4');
  expect(screen.getAllByRole('checkbox')).toHaveLength(STAFF_CAPABILITIES.length+3);
  expect(screen.getByLabelText('inventory:adjustments:approve')).not.toBeChecked();
  expect(screen.queryByLabelText('inventory:update')).not.toBeInTheDocument();
  expect(screen.queryByLabelText('users:create')).not.toBeInTheDocument();
  await userEvent.click(screen.getByLabelText('orders:ship'));
  await userEvent.click(screen.getByRole('button',{name:'Save permissions for all 3 employees'}));
  await waitFor(()=>expect(mocks.editTemplate).toHaveBeenCalledWith(template,['inventory:read','orders:ship']));
});
it('does not claim success or silently retry a stale version',async()=>{
  mocks.editTemplate.mockRejectedValue(new Error('stale'));
  render(<MemoryRouter><StaffRolesPage/></MemoryRouter>);
  await userEvent.click(await screen.findByRole('button',{name:'Save permissions for all 3 employees'}));
  expect(await screen.findByRole('status')).toHaveTextContent('Not saved');
  expect(mocks.editTemplate).toHaveBeenCalledOnce();
});
