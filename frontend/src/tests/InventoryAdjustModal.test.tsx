/** M2 supersedes the retired form, while preserving selected-product visibility. */
import {describe,it,expect,vi} from 'vitest';
import {render,screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MemoryRouter} from 'react-router-dom';
import {InventoryAdjustModal} from '@/pages/inventory/InventoryAdjustModal';

describe('InventoryAdjustModal retired writer boundary',()=>{
  it('offers only the new adjustment entry, never an old quantity form',()=>{
    render(<MemoryRouter><InventoryAdjustModal isOpen onClose={vi.fn()} onSubmit={vi.fn()} initialSkuCode="SKU-A"/></MemoryRouter>);
    expect(screen.getByText('Selected product: SKU-A')).toBeInTheDocument();
    expect(screen.queryByLabelText('Adjustment Quantity (+/-)')).not.toBeInTheDocument();
    expect(screen.getByRole('link',{name:'Open adjustment requests'})).toHaveAttribute('href','/inventory/adjustments');
  });
  it('cannot invoke the retired writer even when the compatibility entry is used',async()=>{
    const submit=vi.fn();
    render(<MemoryRouter><InventoryAdjustModal isOpen onClose={vi.fn()} onSubmit={submit}/></MemoryRouter>);
    await userEvent.click(screen.getByRole('link',{name:'Open adjustment requests'}));
    expect(submit).not.toHaveBeenCalled();
  });
  it('updates the selected product when reopened without retaining an editable payload',()=>{
    const props={isOpen:true,onClose:vi.fn(),onSubmit:vi.fn()};
    const view=render(<MemoryRouter><InventoryAdjustModal {...props} initialSkuCode="SKU-A"/></MemoryRouter>);
    view.rerender(<MemoryRouter><InventoryAdjustModal {...props} initialSkuCode="SKU-B"/></MemoryRouter>);
    expect(screen.queryByText('Selected product: SKU-A')).not.toBeInTheDocument();
    expect(screen.getByText('Selected product: SKU-B')).toBeInTheDocument();
  });
  it('closes without submitting',async()=>{
    const close=vi.fn(),submit=vi.fn();
    render(<MemoryRouter><InventoryAdjustModal isOpen onClose={close} onSubmit={submit}/></MemoryRouter>);
    await userEvent.click(screen.getByRole('button',{name:'Close'}));
    expect(close).toHaveBeenCalledOnce();expect(submit).not.toHaveBeenCalled();
  });
  it('does not mount while closed',()=>{
    render(<MemoryRouter><InventoryAdjustModal isOpen={false} onClose={vi.fn()} onSubmit={vi.fn()}/></MemoryRouter>);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});
