import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DataIntakePage } from '@/pages/skus/DataIntakePage';
import { useAuthStore } from '@/stores/authStore';

const mockCreateWorkspace = vi.fn();
const mockUpload = vi.fn();
const mockUpdateMapping = vi.fn();
const mockValidate = vi.fn();
const mockListRows = vi.fn();
const mockListIssues = vi.fn();
const mockApply = vi.fn();

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((innerResolve) => {
    resolve = innerResolve;
  });
  return { promise, resolve };
}

vi.mock('@/services/intakeService', async () => {
  const actual = await vi.importActual<typeof import('@/services/intakeService')>('@/services/intakeService');
  return {
    ...actual,
    intakeService: {
      createWorkspace: (...args: unknown[]) => mockCreateWorkspace(...args),
      upload: (...args: unknown[]) => mockUpload(...args),
      updateMapping: (...args: unknown[]) => mockUpdateMapping(...args),
      validate: (...args: unknown[]) => mockValidate(...args),
      listRows: (...args: unknown[]) => mockListRows(...args),
      listIssues: (...args: unknown[]) => mockListIssues(...args),
      apply: (...args: unknown[]) => mockApply(...args),
    },
  };
});

const workspaceResponse = {
  data: {
    success: true,
    data: {
      workspace_id: 'workspace-1',
      tenant_id: 'tenant-1',
      name: 'Product intake workspace',
      source_type: 'CUSTOMER_ONBOARDING',
      status: 'OPEN',
      metadata: {},
      created_at: '2026-07-01T00:00:00Z',
      updated_at: '2026-07-01T00:00:00Z',
    },
    timestamp: '2026-07-01T00:00:00Z',
  },
};

const uploadResponse = {
  data: {
    success: true,
    data: {
      upload_id: 'upload-1',
      workspace_id: 'workspace-1',
      filename: 'products.csv',
      file_ext: 'csv',
      status: 'PARSED',
      row_count: 2,
      column_count: 4,
      headers_raw: ['Sku Code', 'Name', 'Price', 'Extra'],
      headers_normalized: {
        'Sku Code': 'sku_code',
        Name: 'name',
        Price: 'price',
        Extra: 'extra',
      },
      parse_summary: { parser: 'csv' },
      created_at: '2026-07-01T00:00:00Z',
    },
    timestamp: '2026-07-01T00:00:00Z',
  },
};

const mappingResponse = {
  data: {
    success: true,
    data: {
      workspace_id: 'workspace-1',
      mapped_rows: 2,
      mapping: { 'Sku Code': 'sku_code', Name: 'name', Price: 'unit_price' },
      status: 'MAPPED',
      unit_default_note: 'Missing unit is documented for review; U4-D does not mutate it to a default value.',
    },
    timestamp: '2026-07-01T00:00:00Z',
  },
};

const validationResponse = {
  data: {
    success: true,
    data: {
      workspace_id: 'workspace-1',
      status: 'NEEDS_REVIEW',
      row_count: 2,
      error_count: 1,
      warning_count: 1,
    },
    timestamp: '2026-07-01T00:00:00Z',
  },
};

const readyValidationResponse = {
  data: {
    success: true,
    data: {
      workspace_id: 'workspace-1',
      status: 'READY_FOR_EXPORT',
      row_count: 2,
      error_count: 0,
      warning_count: 0,
    },
    timestamp: '2026-07-01T00:00:00Z',
  },
};

const rowsResponse = {
  data: {
    success: true,
    data: {
      items: [
        {
          row_id: 'row-1',
          upload_id: 'upload-1',
          source_row_number: 2,
          row_index: 0,
          raw_values: { 'Sku Code': 'SKU-1', Name: 'Widget', Price: 'abc' },
          normalized_values: { sku_code: 'SKU-1', name: 'Widget', unit_price: 'abc' },
          mapping_version: 2,
          sku_code: 'SKU-1',
          name: 'Widget',
          unit: null,
          category: null,
          unit_price: null,
          barcode: null,
          review_status: 'UNREVIEWED',
          created_at: '2026-07-01T00:00:00Z',
          updated_at: '2026-07-01T00:00:00Z',
        },
      ],
      pagination: { page: 1, size: 100, total: 1, pages: 1 },
    },
    timestamp: '2026-07-01T00:00:00Z',
  },
};

const issuesResponse = {
  data: {
    success: true,
    data: {
      items: [
        {
          issue_id: 'issue-1',
          upload_id: 'upload-1',
          row_id: 'row-1',
          source_row_number: 2,
          severity: 'ERROR',
          code: 'INVALID_UNIT_PRICE',
          field: 'unit_price',
          source_header: null,
          message: 'unit_price must be a valid decimal value',
          is_blocking: true,
          created_at: '2026-07-01T00:00:00Z',
        },
        {
          issue_id: 'issue-2',
          upload_id: 'upload-1',
          row_id: null,
          source_row_number: null,
          severity: 'WARNING',
          code: 'UNMAPPED_EXTRA_COLUMN',
          field: null,
          source_header: 'Extra',
          message: 'Column Extra is not mapped',
          is_blocking: false,
          created_at: '2026-07-01T00:00:00Z',
        },
      ],
      pagination: { page: 1, size: 100, total: 2, pages: 1 },
    },
    timestamp: '2026-07-01T00:00:00Z',
  },
};

const noIssuesResponse = {
  data: {
    success: true,
    data: {
      items: [],
      pagination: { page: 1, size: 100, total: 0, pages: 0 },
    },
    timestamp: '2026-07-01T00:00:00Z',
  },
};

const applyResponse = {
  data: {
    success: true,
    data: {
      workspace_id: 'workspace-1',
      apply_status: 'applied',
      created_count: 2,
      row_count: 2,
      created_sku_ids: ['sku-1', 'sku-2'],
    },
    timestamp: '2026-07-01T00:00:00Z',
  },
};

function mockHappyPath() {
  mockCreateWorkspace.mockResolvedValue(workspaceResponse);
  mockUpload.mockResolvedValue(uploadResponse);
  mockUpdateMapping.mockResolvedValue(mappingResponse);
  mockValidate.mockResolvedValue(validationResponse);
  mockListRows.mockResolvedValue(rowsResponse);
  mockListIssues.mockResolvedValue(issuesResponse);
  mockApply.mockResolvedValue(applyResponse);
}

function setUser(permissions: string[]) {
  useAuthStore.setState({
    accessToken: 'test-token',
    refreshToken: 'test-refresh',
    tenantCode: 'tenant-one',
    user: {
      id: 'user-1',
      email: 'user@example.com',
      full_name: 'Test User',
      tenant_id: 'tenant-1',
      tenant_schema: 't_test',
      roles: ['operator'],
      permissions,
    },
  });
}

async function reachValidatedPreview() {
  await createWorkspace();
  await uploadFile();
  await userEvent.selectOptions(screen.getByLabelText('Map Price'), 'unit_price');
  await userEvent.click(screen.getByRole('button', { name: /save mapping/i }));
  await screen.findByText(/mapped 2 staged row/i);
  await userEvent.click(screen.getByRole('button', { name: /validate staging rows/i }));
}

async function reachReadyForExport() {
  mockCreateWorkspace.mockResolvedValue(workspaceResponse);
  mockUpload.mockResolvedValue(uploadResponse);
  mockUpdateMapping.mockResolvedValue(mappingResponse);
  mockValidate.mockResolvedValue(readyValidationResponse);
  mockListRows.mockResolvedValue(rowsResponse);
  mockListIssues.mockResolvedValue(noIssuesResponse);
  mockApply.mockResolvedValue(applyResponse);

  render(<DataIntakePage />);
  await reachValidatedPreview();
  await screen.findByText('READY_FOR_EXPORT');
}

async function createWorkspace() {
  await userEvent.click(screen.getByRole('button', { name: /create workspace/i }));
  await screen.findByText(/workspace created/i);
}

async function uploadFile() {
  const input = screen.getByLabelText(/upload csv or xlsx file/i);
  await userEvent.upload(input, new File(['Sku Code,Name,Price\nSKU-1,Widget,abc'], 'products.csv', { type: 'text/csv' }));
  await screen.findByText('Parser result');
}

describe('DataIntakePage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setUser(['intake:create', 'intake:update', 'intake:read', 'skus:import']);
  });

  it('runs the mock API happy path from create through validation preview', async () => {
    mockHappyPath();
    render(<DataIntakePage />);

    await createWorkspace();
    await uploadFile();

    expect(screen.getByText('products.csv')).toBeInTheDocument();
    expect(screen.getByText('Rows')).toBeInTheDocument();
    expect(screen.getByText('Columns')).toBeInTheDocument();
    expect(screen.getByText(/Sku Code, Name, Price, Extra/)).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText('Map Price'), 'unit_price');
    await userEvent.click(screen.getByRole('button', { name: /save mapping/i }));

    await waitFor(() => {
      expect(mockUpdateMapping).toHaveBeenCalledWith('workspace-1', expect.objectContaining({
        'Sku Code': 'sku_code',
        Name: 'name',
        Price: 'unit_price',
      }));
    });

    await userEvent.click(screen.getByRole('button', { name: /validate staging rows/i }));

    await waitFor(() => {
      expect(mockValidate).toHaveBeenCalledWith('workspace-1');
      expect(mockListRows).toHaveBeenCalledWith('workspace-1');
      expect(mockListIssues).toHaveBeenCalledWith('workspace-1');
    });

    expect(screen.getByText('NEEDS_REVIEW')).toBeInTheDocument();
    expect(screen.getByText('SKU-1')).toBeInTheDocument();
    expect(screen.getByText('Widget')).toBeInTheDocument();
  });

  it('waits for validate to resolve before fetching rows and issues', async () => {
    const validateDeferred = deferred<typeof validationResponse>();
    mockCreateWorkspace.mockResolvedValue(workspaceResponse);
    mockUpload.mockResolvedValue(uploadResponse);
    mockUpdateMapping.mockResolvedValue(mappingResponse);
    mockValidate.mockReturnValue(validateDeferred.promise);
    mockListRows.mockResolvedValue(rowsResponse);
    mockListIssues.mockResolvedValue(issuesResponse);

    render(<DataIntakePage />);

    await createWorkspace();
    await uploadFile();
    await userEvent.selectOptions(screen.getByLabelText('Map Price'), 'unit_price');
    await userEvent.click(screen.getByRole('button', { name: /save mapping/i }));
    await screen.findByText(/mapped 2 staged row/i);
    await userEvent.click(screen.getByRole('button', { name: /validate staging rows/i }));

    expect(mockValidate).toHaveBeenCalledWith('workspace-1');
    expect(mockListRows).not.toHaveBeenCalled();
    expect(mockListIssues).not.toHaveBeenCalled();

    validateDeferred.resolve(validationResponse);

    await waitFor(() => {
      expect(mockListRows).toHaveBeenCalledWith('workspace-1');
      expect(mockListIssues).toHaveBeenCalledWith('workspace-1');
    });
  });

  it('shows a friendly permission message for 403 responses', async () => {
    mockCreateWorkspace.mockRejectedValue({ response: { status: 403 } });
    render(<DataIntakePage />);

    await userEvent.click(screen.getByRole('button', { name: /create workspace/i }));

    expect(await screen.findByText(/ask an admin for intake access/i)).toBeInTheDocument();
  });

  it('shows a friendly upload parse error message', async () => {
    mockCreateWorkspace.mockResolvedValue(workspaceResponse);
    mockUpload.mockRejectedValue({
      response: { status: 400, data: { detail: { code: 'XLSX_PARSE_ERROR', message: 'Unreadable' } } },
    });
    render(<DataIntakePage />);

    await createWorkspace();
    const input = screen.getByLabelText(/upload csv or xlsx file/i);
    await userEvent.upload(input, new File(['bad'], 'products.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }));

    expect(await screen.findByText(/xlsx file is unreadable or protected/i)).toBeInTheDocument();
  });

  it('displays invalid unit price and unmapped column issues in readable language', async () => {
    mockHappyPath();
    render(<DataIntakePage />);

    await createWorkspace();
    await uploadFile();
    await userEvent.selectOptions(screen.getByLabelText('Map Price'), 'unit_price');
    await userEvent.click(screen.getByRole('button', { name: /save mapping/i }));
    await screen.findByText(/mapped 2 staged row/i);
    await userEvent.click(screen.getByRole('button', { name: /validate staging rows/i }));

    expect(await screen.findByText(/unit price must be a valid decimal number/i)).toBeInTheDocument();
    expect(screen.getByText(/source column is not mapped/i)).toBeInTheDocument();
  });

  it('does not render an apply button before READY_FOR_EXPORT', async () => {
    mockHappyPath();
    render(<DataIntakePage />);

    await createWorkspace();
    await uploadFile();

    expect(screen.queryByRole('button', { name: /apply to catalog/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /import.*sku/i })).not.toBeInTheDocument();
  });

  it('keeps apply unavailable with blocking issues after validation', async () => {
    mockHappyPath();
    render(<DataIntakePage />);

    await reachValidatedPreview();

    expect(await screen.findByText('NEEDS_REVIEW')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /apply to catalog/i })).not.toBeInTheDocument();
    expect(screen.getByText(/fix blocking issues/i)).toBeInTheDocument();
  });

  it('requires both intake:update and skus:import to apply', async () => {
    setUser(['intake:create', 'intake:update', 'intake:read']);

    await reachReadyForExport();

    expect(screen.queryByRole('button', { name: /apply to catalog/i })).not.toBeInTheDocument();
    expect(screen.getByText(/missing permission/i)).toBeInTheDocument();
  });

  it('shows catalog-only warnings in the apply section and confirmation modal before calling apply', async () => {
    await reachReadyForExport();

    expect(screen.getByRole('heading', { name: '5. Create Catalog SKUs' })).toBeInTheDocument();
    expect(screen.getByText(/this flow creates catalog sku records only/i)).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /apply to catalog/i }));

    expect(mockApply).not.toHaveBeenCalled();
    expect(screen.getByRole('dialog', { name: /apply staged rows to catalog/i })).toBeInTheDocument();
    expect(screen.getByText('This creates catalog SKUs only.')).toBeInTheDocument();
    expect(screen.getByText('It does not create stock, retailer prices, barcode lookup, images, custom attributes, or sellable order readiness.')).toBeInTheDocument();
    expect(screen.getByText('Configure stock and retailer pricing before creating orders.')).toBeInTheDocument();
    expect(screen.getByText(/duplicate existing sku codes will be blocked/i)).toBeInTheDocument();
    expect(screen.getByText(/no silent overwrite/i)).toBeInTheDocument();
  });

  it('confirms apply exactly once and prevents duplicate submits', async () => {
    const applyDeferred = deferred<typeof applyResponse>();
    await reachReadyForExport();
    mockApply.mockReturnValue(applyDeferred.promise);

    await userEvent.click(screen.getByRole('button', { name: /apply to catalog/i }));
    const confirmButton = screen.getByRole('button', { name: /confirm apply/i });
    await userEvent.dblClick(confirmButton);

    expect(mockApply).toHaveBeenCalledTimes(1);
    expect(mockApply).toHaveBeenCalledWith('workspace-1');
    expect(confirmButton).toBeDisabled();

    applyDeferred.resolve(applyResponse);
    expect(await screen.findByText(/created 2 catalog sku record\(s\) only/i)).toBeInTheDocument();
  });

  it('shows success created count, next steps, and disables apply after success', async () => {
    await reachReadyForExport();

    await userEvent.click(screen.getByRole('button', { name: /apply to catalog/i }));
    await userEvent.click(screen.getByRole('button', { name: /confirm apply/i }));

    expect(await screen.findByText(/created 2 catalog sku record\(s\) only/i)).toBeInTheDocument();
    expect(screen.getByText(/next steps: adjust stock, set retailer prices, then create orders/i)).toBeInTheDocument();
    expect(screen.getByText(/sku-1, sku-2/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /apply to catalog/i })).not.toBeInTheDocument();
    expect(screen.getByText(/already applied/i)).toBeInTheDocument();
    expect(screen.queryByText(/official product\/sku record/i)).not.toBeInTheDocument();
  });

  it.each([
    ['ALREADY_APPLIED', 'This intake workspace has already been applied'],
    ['DUPLICATE_STAGED_SKU_CODE', 'Duplicate staged SKU codes: SKU-1, SKU-2'],
    ['SKU_CODE_EXISTS', 'Existing SKU codes already in Products: SKU-1, SKU-2'],
  ])('shows friendly apply error for %s', async (code, message) => {
    await reachReadyForExport();
    mockApply.mockRejectedValue({
      response: {
        status: code === 'ALREADY_APPLIED' ? 409 : 400,
        data: { detail: { code, sku_codes: ['SKU-1', 'SKU-2'] } },
      },
    });

    await userEvent.click(screen.getByRole('button', { name: /apply to catalog/i }));
    await userEvent.click(screen.getByRole('button', { name: /confirm apply/i }));

    expect(await screen.findByText(message)).toBeInTheDocument();
  });

  it('shows friendly apply error for BLOCKING_ISSUES', async () => {
    await reachReadyForExport();
    mockApply.mockRejectedValue({
      response: {
        status: 400,
        data: { detail: { code: 'BLOCKING_ISSUES' } },
      },
    });

    await userEvent.click(screen.getByRole('button', { name: /apply to catalog/i }));
    await userEvent.click(screen.getByRole('button', { name: /confirm apply/i }));

    expect(await screen.findByText('Revalidate and fix blocking issues before applying this workspace.')).toBeInTheDocument();
  });

  it('shows apply-specific permission guidance for 403 apply failures', async () => {
    await reachReadyForExport();
    mockApply.mockRejectedValue({ response: { status: 403 } });

    await userEvent.click(screen.getByRole('button', { name: /apply to catalog/i }));
    await userEvent.click(screen.getByRole('button', { name: /confirm apply/i }));

    expect(await screen.findByText('You need both intake:update and skus:import to create catalog SKUs from staged rows.')).toBeInTheDocument();
  });
});
