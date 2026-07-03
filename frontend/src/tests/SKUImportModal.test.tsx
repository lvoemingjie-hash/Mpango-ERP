/**
 * U3-D Frontend tests for SKU Import UX.
 *
 * Covers:
 *   1. Import button renders on SKU list page
 *   2. Preview success
 *   3. Validate success
 *   4. Validate errors block apply
 *   5. Apply success refreshes SKU list
 *   6. 403 permission message
 *   7. Unsupported fields are excluded or visibly blocked
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SKUImportModal } from '@/pages/skus/SKUImportModal';
import { UNSUPPORTED_FIELDS, ALL_MAPPABLE_FIELDS } from '@/types/import';

// ---------------------------------------------------------------------------
// Mock skuImportService
// ---------------------------------------------------------------------------

const mockPreview = vi.fn();
const mockValidate = vi.fn();
const mockApply = vi.fn();

vi.mock('@/services/skuImportService', () => ({
  skuImportService: {
    preview: (...args: unknown[]) => mockPreview(...args),
    validate: (...args: unknown[]) => mockValidate(...args),
    apply: (...args: unknown[]) => mockApply(...args),
  },
}));

// ---------------------------------------------------------------------------
// Mock toast store
// ---------------------------------------------------------------------------

vi.mock('@/stores/toastStore', () => ({
  useToastStore: {
    getState: () => ({ addToast: vi.fn() }),
  },
}));

// ---------------------------------------------------------------------------
// Mock normalizeApiError
// ---------------------------------------------------------------------------

vi.mock('@/utils/errorHandling', () => ({
  normalizeApiError: (err: unknown) => {
    const axErr = err as { response?: { status?: number; data?: { detail?: string } }; message?: string };
    if (axErr.response?.status === 403) return 'Permission denied';
    return axErr.message || 'An error occurred';
  },
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const defaultProps = {
  isOpen: true,
  onClose: vi.fn(),
  onSuccess: vi.fn(),
};

function createFile(content: string, name = 'products.csv') {
  return new File([content], name, { type: 'text/csv' });
}

const PREVIEW_RESPONSE = {
  data: {
    success: true,
    data: {
      import_id: 'imp-001',
      source: { filename: 'products.csv', encoding: 'utf-8', row_count: 5 },
      columns_detected: ['sku_code', 'name', 'description', 'unit', 'price', 'stock'],
      sample_rows: [
        { sku_code: 'SKU-001', name: 'Widget', description: 'A widget', unit: 'unit', price: '10.00', stock: '100' },
      ],
    },
    timestamp: new Date().toISOString(),
  },
};

const VALIDATE_SUCCESS_RESPONSE = {
  data: {
    success: true,
    data: {
      import_id: 'imp-001',
      status: 'validated',
      valid_rows: 5,
      error_rows: 0,
      warning_rows: 0,
      errors: [],
      warnings: [],
    },
    timestamp: new Date().toISOString(),
  },
};

const VALIDATE_ERROR_RESPONSE = {
  data: {
    success: true,
    data: {
      import_id: 'imp-001',
      status: 'needs_review',
      valid_rows: 3,
      error_rows: 2,
      warning_rows: 0,
      errors: [
        { row: 3, field: 'sku_code', sku_code: '', message: 'SKU code is required' },
        { row: 5, field: 'name', sku_code: 'SKU-005', message: 'Name is required' },
      ],
      warnings: [],
    },
    timestamp: new Date().toISOString(),
  },
};

const APPLY_SUCCESS_RESPONSE = {
  data: {
    success: true,
    data: {
      import_id: 'imp-001',
      status: 'completed',
      created: 5,
      skipped: 0,
      updated: 0,
      errors: [],
      audit_run_id: 'audit-001',
    },
    timestamp: new Date().toISOString(),
  },
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('SKUImportModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // -------------------------------------------------------------------------
  // Test 1: Import button renders -- tested at the modal level
  // -------------------------------------------------------------------------

  it('renders the upload step with file input when open', () => {
    render(<SKUImportModal {...defaultProps} />);
    expect(screen.getByText('Import Products')).toBeInTheDocument();
    expect(screen.getByText(/CSV only/i)).toBeInTheDocument();
  });

  it('does not render when closed', () => {
    render(<SKUImportModal {...defaultProps} isOpen={false} />);
    expect(screen.queryByText('Import Products')).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Test 2: Preview success
  // -------------------------------------------------------------------------

  it('advances to mapping step after successful preview', async () => {
    mockPreview.mockResolvedValueOnce(PREVIEW_RESPONSE);
    render(<SKUImportModal {...defaultProps} />);

    const fileInput = screen.getByLabelText(/click to select a csv file/i) as HTMLInputElement;
    const file = createFile('sku_code,name\nSKU-001,Widget');
    await userEvent.upload(fileInput, file);

    await waitFor(() => {
      expect(mockPreview).toHaveBeenCalledTimes(1);
    });

    // Should advance to mapping step
    await waitFor(() => {
      expect(screen.getByText('Map Columns')).toBeInTheDocument();
    });

    // Should show detected columns
    expect(screen.getByText('products.csv')).toBeInTheDocument();
    expect(screen.getByText(/5 rows detected/)).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Test 3: Validate success
  // -------------------------------------------------------------------------

  it('advances to validate step with no errors', async () => {
    mockPreview.mockResolvedValueOnce(PREVIEW_RESPONSE);
    mockValidate.mockResolvedValueOnce(VALIDATE_SUCCESS_RESPONSE);

    render(<SKUImportModal {...defaultProps} />);

    // Upload
    const fileInput = screen.getByLabelText(/click to select a csv file/i) as HTMLInputElement;
    await userEvent.upload(fileInput, createFile('sku_code,name\nSKU-001,Widget'));

    await waitFor(() => {
      expect(screen.getByText('Map Columns')).toBeInTheDocument();
    });

    // Click Validate
    const validateBtn = screen.getByRole('button', { name: /validate/i });
    await userEvent.click(validateBtn);

    await waitFor(() => {
      expect(mockValidate).toHaveBeenCalledWith('imp-001', expect.any(Object));
    });

    await waitFor(() => {
      expect(screen.getByText('Validation Results')).toBeInTheDocument();
    });

    // Should show valid rows
    expect(screen.getByText('5')).toBeInTheDocument(); // valid_rows
  });

  // -------------------------------------------------------------------------
  // Test 4: Validate errors block apply
  // -------------------------------------------------------------------------

  it('shows errors and blocks apply when validation has error_rows > 0', async () => {
    mockPreview.mockResolvedValueOnce(PREVIEW_RESPONSE);
    mockValidate.mockResolvedValueOnce(VALIDATE_ERROR_RESPONSE);

    render(<SKUImportModal {...defaultProps} />);

    // Upload
    const fileInput = screen.getByLabelText(/click to select a csv file/i) as HTMLInputElement;
    await userEvent.upload(fileInput, createFile('sku_code,name\nSKU-001,Widget'));

    await waitFor(() => {
      expect(screen.getByText('Map Columns')).toBeInTheDocument();
    });

    // Click Validate
    const validateBtn = screen.getByRole('button', { name: /validate/i });
    await userEvent.click(validateBtn);

    await waitFor(() => {
      expect(screen.getByText('Validation Results')).toBeInTheDocument();
    });

    // Should show error info
    expect(screen.getByText(/Import blocked/i)).toBeInTheDocument();
    expect(screen.getByText(/2 row\(s\) have errors/i)).toBeInTheDocument();

    // Apply button should NOT be present
    expect(screen.queryByRole('button', { name: /apply import/i })).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Test 5: Apply success refreshes SKU list
  // -------------------------------------------------------------------------

  it('calls onSuccess and shows catalog-only results after successful apply', async () => {
    const onSuccess = vi.fn();
    mockPreview.mockResolvedValueOnce(PREVIEW_RESPONSE);
    mockValidate.mockResolvedValueOnce(VALIDATE_SUCCESS_RESPONSE);
    mockApply.mockResolvedValueOnce(APPLY_SUCCESS_RESPONSE);

    render(<SKUImportModal {...defaultProps} onSuccess={onSuccess} />);

    // Upload
    const fileInput = screen.getByLabelText(/click to select a csv file/i) as HTMLInputElement;
    await userEvent.upload(fileInput, createFile('sku_code,name\nSKU-001,Widget'));

    await waitFor(() => {
      expect(screen.getByText('Map Columns')).toBeInTheDocument();
    });

    // Validate
    await userEvent.click(screen.getByRole('button', { name: /validate/i }));

    await waitFor(() => {
      expect(screen.getByText('Validation Results')).toBeInTheDocument();
    });

    // Apply
    const applyBtn = screen.getByRole('button', { name: /apply import/i });
    await userEvent.click(applyBtn);

    await waitFor(() => {
      expect(mockApply).toHaveBeenCalledWith('imp-001', 'skip');
    });

    await waitFor(() => {
      expect(screen.getByText('Catalog SKU Import Complete')).toBeInTheDocument();
    });

    expect(onSuccess).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/applied staged rows to the product catalog only/i)).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Test 6: 403 permission message
  // -------------------------------------------------------------------------

  it('shows permission error when API returns 403', async () => {
    const error403 = {
      response: { status: 403, data: { detail: 'Forbidden' } },
      message: 'Forbidden',
    };
    mockPreview.mockRejectedValueOnce(error403);

    render(<SKUImportModal {...defaultProps} />);

    const fileInput = screen.getByLabelText(/click to select a csv file/i) as HTMLInputElement;
    await userEvent.upload(fileInput, createFile('sku_code,name\nSKU-001,Widget'));

    await waitFor(() => {
      expect(screen.getByText(/lacks product import permission/i)).toBeInTheDocument();
      expect(screen.getByText(/admin role/i)).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Test 7: Unsupported fields are excluded or visibly blocked
  // -------------------------------------------------------------------------

  it('marks unsupported columns (price, stock) as not supported in mapping', async () => {
    mockPreview.mockResolvedValueOnce(PREVIEW_RESPONSE);
    render(<SKUImportModal {...defaultProps} />);

    const fileInput = screen.getByLabelText(/click to select a csv file/i) as HTMLInputElement;
    await userEvent.upload(fileInput, createFile('sku_code,name,price,stock\nSKU-001,Widget,10,100'));

    await waitFor(() => {
      expect(screen.getByText('Map Columns')).toBeInTheDocument();
    });

    // Unsupported columns should show "Not supported" label
    const unsupportedLabels = screen.getAllByText(/not supported in this import/i);
    expect(unsupportedLabels.length).toBeGreaterThanOrEqual(2); // price + stock
  });

  it('shows catalog-only scope warning on upload step', () => {
    render(<SKUImportModal {...defaultProps} />);

    expect(screen.getByText(/apply creates catalog sku records only/i)).toBeInTheDocument();
    expect(screen.getByText((content) => content.includes('write inventory, pricing, barcode lookup, images, custom attributes, or sellable readiness.'))).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Additional: CSV-only validation
  // -------------------------------------------------------------------------

  it('rejects non-CSV files with clear error', async () => {
    render(<SKUImportModal {...defaultProps} />);

    const fileInput = screen.getByLabelText(/click to select a csv file/i) as HTMLInputElement;
    // Use fireEvent since userEvent may enforce accept attribute
    const xlsxFile = new File(['data'], 'products.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
    // Remove accept restriction so the change handler fires
    fileInput.removeAttribute('accept');
    fireEvent.change(fileInput, { target: { files: [xlsxFile] } });

    await waitFor(() => {
      expect(screen.getByText(/please upload a csv file/i)).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Additional: Mappable fields constant verification
  // -------------------------------------------------------------------------

  it('includes required fields sku_code and name in mappable fields', () => {
    expect(ALL_MAPPABLE_FIELDS).toContain('sku_code');
    expect(ALL_MAPPABLE_FIELDS).toContain('name');
  });

  it('excludes unsupported fields from mappable fields', () => {
    for (const u of UNSUPPORTED_FIELDS) {
      expect(ALL_MAPPABLE_FIELDS).not.toContain(u);
    }
  });

  it('unsupported fields list includes stock, price, image, barcode, custom_attributes', () => {
    expect(UNSUPPORTED_FIELDS).toContain('stock');
    expect(UNSUPPORTED_FIELDS).toContain('price');
    expect(UNSUPPORTED_FIELDS).toContain('image');
    expect(UNSUPPORTED_FIELDS).toContain('barcode');
    expect(UNSUPPORTED_FIELDS).toContain('custom_attributes');
  });
});
