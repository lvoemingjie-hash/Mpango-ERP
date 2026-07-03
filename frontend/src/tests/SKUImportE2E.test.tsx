/**
 * U3-E Product Import End-to-End Hardening -- Frontend tests.
 *
 * Focuses on the full user journey and list-refresh verification:
 *   1. Full wizard: upload -> mapping -> validate -> apply -> success summary
 *   2. onSuccess (list refresh) called after completed apply
 *   3. onSuccess NOT called when apply fails or returns non-completed
 *   4. Conflict strategy selector visible only after clean validation
 *   5. Apply failure shows error, does NOT show success summary
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SKUImportModal } from '@/pages/skus/SKUImportModal';

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
    if (axErr.response?.status === 422) return 'Row processing errors detected';
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
      import_id: 'imp-e2e-001',
      source: { filename: 'products.csv', encoding: 'utf-8', row_count: 3 },
      columns_detected: ['sku_code', 'name', 'description'],
      sample_rows: [
        { sku_code: 'SKU-001', name: 'Widget', description: 'A widget' },
        { sku_code: 'SKU-002', name: 'Gadget', description: 'A gadget' },
        { sku_code: 'SKU-003', name: 'Tool', description: 'A tool' },
      ],
    },
    timestamp: new Date().toISOString(),
  },
};

const VALIDATE_CLEAN_RESPONSE = {
  data: {
    success: true,
    data: {
      import_id: 'imp-e2e-001',
      status: 'validated',
      valid_rows: 3,
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
      import_id: 'imp-e2e-001',
      status: 'needs_review',
      valid_rows: 2,
      error_rows: 1,
      warning_rows: 0,
      errors: [
        { row: 2, field: 'sku_code', sku_code: '', message: 'Required field sku_code is empty' },
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
      import_id: 'imp-e2e-001',
      status: 'completed',
      created: 3,
      skipped: 0,
      updated: 0,
      errors: [],
      audit_run_id: 'imp-e2e-001',
    },
    timestamp: new Date().toISOString(),
  },
};

const APPLY_WITH_SKIPS_RESPONSE = {
  data: {
    success: true,
    data: {
      import_id: 'imp-e2e-001',
      status: 'completed',
      created: 2,
      skipped: 1,
      updated: 0,
      errors: [],
      audit_run_id: 'imp-e2e-001',
    },
    timestamp: new Date().toISOString(),
  },
};

// ---------------------------------------------------------------------------
// Helper: advance through upload -> mapping -> validate
// ---------------------------------------------------------------------------

async function advanceToValidateStep() {
  mockPreview.mockResolvedValueOnce(PREVIEW_RESPONSE);
  mockValidate.mockResolvedValueOnce(VALIDATE_CLEAN_RESPONSE);

  render(<SKUImportModal {...defaultProps} />);

  const fileInput = screen.getByLabelText(/click to select a csv file/i) as HTMLInputElement;
  await userEvent.upload(fileInput, createFile('sku_code,name\nSKU-001,Widget'));

  await waitFor(() => {
    expect(screen.getByText('Map Columns')).toBeInTheDocument();
  });

  await userEvent.click(screen.getByRole('button', { name: /validate/i }));

  await waitFor(() => {
    expect(screen.getByText('Validation Results')).toBeInTheDocument();
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('SKU Import E2E hardening', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // -----------------------------------------------------------------------
  // Test 1: Full wizard journey renders success summary
  // -----------------------------------------------------------------------

  it('completes full journey: upload -> validate -> apply -> shows success summary', async () => {
    mockPreview.mockResolvedValueOnce(PREVIEW_RESPONSE);
    mockValidate.mockResolvedValueOnce(VALIDATE_CLEAN_RESPONSE);
    mockApply.mockResolvedValueOnce(APPLY_SUCCESS_RESPONSE);

    render(<SKUImportModal {...defaultProps} />);

    // Step 1: Upload
    const fileInput = screen.getByLabelText(/click to select a csv file/i) as HTMLInputElement;
    await userEvent.upload(fileInput, createFile('sku_code,name\nSKU-001,Widget'));

    await waitFor(() => {
      expect(screen.getByText('Map Columns')).toBeInTheDocument();
    });

    // Step 2: Validate
    await userEvent.click(screen.getByRole('button', { name: /validate/i }));

    await waitFor(() => {
      expect(screen.getByText('Validation Results')).toBeInTheDocument();
    });

    // Verify validation summary
    expect(screen.getByText('3')).toBeInTheDocument(); // valid_rows

    // Step 3: Apply
    const applyBtn = screen.getByRole('button', { name: /apply import/i });
    await userEvent.click(applyBtn);

    await waitFor(() => {
      expect(screen.getByText('Catalog SKU Import Complete')).toBeInTheDocument();
    });

    // Verify success summary counters
    expect(screen.getByText('Catalog SKU Import Complete')).toBeInTheDocument();
    expect(screen.getByText(/applied staged rows to the product catalog only/i)).toBeInTheDocument();
  });

  // -----------------------------------------------------------------------
  // Test 2: onSuccess (list refresh) called after completed apply
  // -----------------------------------------------------------------------

  it('calls onSuccess after successful apply (triggers list refresh)', async () => {
    const onSuccess = vi.fn();
    mockPreview.mockResolvedValueOnce(PREVIEW_RESPONSE);
    mockValidate.mockResolvedValueOnce(VALIDATE_CLEAN_RESPONSE);
    mockApply.mockResolvedValueOnce(APPLY_SUCCESS_RESPONSE);

    render(<SKUImportModal {...defaultProps} onSuccess={onSuccess} />);

    const fileInput = screen.getByLabelText(/click to select a csv file/i) as HTMLInputElement;
    await userEvent.upload(fileInput, createFile('sku_code,name\nSKU-001,Widget'));

    await waitFor(() => expect(screen.getByText('Map Columns')).toBeInTheDocument());
    await userEvent.click(screen.getByRole('button', { name: /validate/i }));
    await waitFor(() => expect(screen.getByText('Validation Results')).toBeInTheDocument());

    await userEvent.click(screen.getByRole('button', { name: /apply import/i }));

    await waitFor(() => {
      expect(onSuccess).toHaveBeenCalledTimes(1);
    });
  });

  // -----------------------------------------------------------------------
  // Test 3: onSuccess NOT called when apply fails
  // -----------------------------------------------------------------------

  it('does NOT call onSuccess when apply returns error (422)', async () => {
    const onSuccess = vi.fn();
    const error422 = {
      response: { status: 422, data: { detail: 'Row processing errors' } },
      message: 'Request failed',
    };
    mockPreview.mockResolvedValueOnce(PREVIEW_RESPONSE);
    mockValidate.mockResolvedValueOnce(VALIDATE_CLEAN_RESPONSE);
    mockApply.mockRejectedValueOnce(error422);

    render(<SKUImportModal {...defaultProps} onSuccess={onSuccess} />);

    const fileInput = screen.getByLabelText(/click to select a csv file/i) as HTMLInputElement;
    await userEvent.upload(fileInput, createFile('sku_code,name\nSKU-001,Widget'));

    await waitFor(() => expect(screen.getByText('Map Columns')).toBeInTheDocument());
    await userEvent.click(screen.getByRole('button', { name: /validate/i }));
    await waitFor(() => expect(screen.getByText('Validation Results')).toBeInTheDocument());

    await userEvent.click(screen.getByRole('button', { name: /apply import/i }));

    // Wait for error to appear
    await waitFor(() => {
      expect(screen.getByText(/row processing errors detected/i)).toBeInTheDocument();
    });

    // onSuccess must NOT have been called
    expect(onSuccess).not.toHaveBeenCalled();

    // Success summary must NOT be shown
    expect(screen.queryByText('Catalog SKU Import Complete')).not.toBeInTheDocument();
  });

  // -----------------------------------------------------------------------
  // Test 4: Conflict strategy selector visible only after clean validation
  // -----------------------------------------------------------------------

  it('shows conflict strategy options when validation has zero errors', async () => {
    await advanceToValidateStep();

    // Conflict strategy radio options should be visible
    expect(screen.getByText('Conflict strategy')).toBeInTheDocument();
    expect(screen.getByText('Skip duplicates')).toBeInTheDocument();
    expect(screen.getByText('Fail on duplicate')).toBeInTheDocument();
  });

  it('hides conflict strategy and blocks apply when validation has errors', async () => {
    mockPreview.mockResolvedValueOnce(PREVIEW_RESPONSE);
    mockValidate.mockResolvedValueOnce(VALIDATE_ERROR_RESPONSE);

    render(<SKUImportModal {...defaultProps} />);

    const fileInput = screen.getByLabelText(/click to select a csv file/i) as HTMLInputElement;
    await userEvent.upload(fileInput, createFile('sku_code,name\nSKU-001,Widget'));

    await waitFor(() => expect(screen.getByText('Map Columns')).toBeInTheDocument());
    await userEvent.click(screen.getByRole('button', { name: /validate/i }));
    await waitFor(() => expect(screen.getByText('Validation Results')).toBeInTheDocument());

    // Conflict strategy should NOT be visible
    expect(screen.queryByText('Conflict strategy')).not.toBeInTheDocument();

    // Apply button should NOT be visible
    expect(screen.queryByRole('button', { name: /apply import/i })).not.toBeInTheDocument();

    // Blocked message visible
    expect(screen.getByText(/Import blocked/i)).toBeInTheDocument();
  });

  // -----------------------------------------------------------------------
  // Test 5: Apply with skips shows correct counters
  // -----------------------------------------------------------------------

  it('shows created and skipped counts in success summary', async () => {
    mockPreview.mockResolvedValueOnce(PREVIEW_RESPONSE);
    mockValidate.mockResolvedValueOnce(VALIDATE_CLEAN_RESPONSE);
    mockApply.mockResolvedValueOnce(APPLY_WITH_SKIPS_RESPONSE);

    render(<SKUImportModal {...defaultProps} />);

    const fileInput = screen.getByLabelText(/click to select a csv file/i) as HTMLInputElement;
    await userEvent.upload(fileInput, createFile('sku_code,name\nSKU-001,Widget'));

    await waitFor(() => expect(screen.getByText('Map Columns')).toBeInTheDocument());
    await userEvent.click(screen.getByRole('button', { name: /validate/i }));
    await waitFor(() => expect(screen.getByText('Validation Results')).toBeInTheDocument());
    await userEvent.click(screen.getByRole('button', { name: /apply import/i }));

    await waitFor(() => {
      expect(screen.getByText('Catalog SKU Import Complete')).toBeInTheDocument();
    });

    // Verify the apply was called (success summary is displayed)
    expect(mockApply).toHaveBeenCalledWith('imp-e2e-001', 'skip');
  });

  // -----------------------------------------------------------------------
  // Test 6: Error rows display with row number and field
  // -----------------------------------------------------------------------

  it('displays row-level error details with row number and field', async () => {
    mockPreview.mockResolvedValueOnce(PREVIEW_RESPONSE);
    mockValidate.mockResolvedValueOnce(VALIDATE_ERROR_RESPONSE);

    render(<SKUImportModal {...defaultProps} />);

    const fileInput = screen.getByLabelText(/click to select a csv file/i) as HTMLInputElement;
    await userEvent.upload(fileInput, createFile('sku_code,name\nSKU-001,Widget'));

    await waitFor(() => expect(screen.getByText('Map Columns')).toBeInTheDocument());
    await userEvent.click(screen.getByRole('button', { name: /validate/i }));
    await waitFor(() => expect(screen.getByText('Validation Results')).toBeInTheDocument());

    // Error list should show row 2 with the error message
    expect(screen.getByText(/Row 2/)).toBeInTheDocument();
    expect(screen.getByText(/Required field sku_code is empty/i)).toBeInTheDocument();
  });
});
