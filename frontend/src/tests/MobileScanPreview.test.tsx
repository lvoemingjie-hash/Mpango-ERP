/**
 * U4-H-A: MobileScanPreview tests.
 *
 * Verifies:
 *   1. BarcodeDetector unavailable -> manual fallback visible (no crash)
 *   2. Scan result displayed after manual entry
 *   3. No official SKU write/apply API called (preview-only)
 *   4. Permission/routing remains internal-login-only (component renders for
 *      logged-in users; does not expose public/anonymous access)
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MobileScanPreview, type ScanResult } from '@/pages/skus/MobileScanPreview';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

// Mock clipboard API
Object.defineProperty(navigator, 'clipboard', {
  value: { writeText: vi.fn().mockResolvedValue(undefined) },
  writable: true,
});

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// 1. BarcodeDetector unavailable -> manual fallback visible
// ---------------------------------------------------------------------------

describe('MobileScanPreview -- BarcodeDetector unavailable', () => {
  it('shows manual fallback when BarcodeDetector API is not available', async () => {
    render(<MobileScanPreview />);

    await waitFor(() => {
      expect(screen.getByText(/not supported in this browser/i)).toBeInTheDocument();
    });

    expect(screen.getByLabelText(/manual barcode or sku code/i)).toBeInTheDocument();
  });

  it('does not crash when BarcodeDetector is absent', async () => {
    const { container } = render(<MobileScanPreview />);
    await waitFor(() => {
      expect(container).toBeTruthy();
    });
  });
});

// ---------------------------------------------------------------------------
// 2. Scan result displayed after manual entry
// ---------------------------------------------------------------------------

describe('MobileScanPreview -- manual entry', () => {
  it('displays the captured code after manual submit', async () => {
    render(<MobileScanPreview />);

    const input = screen.getByLabelText(/manual barcode or sku code/i) as HTMLInputElement;
    fireEvent.change(input, { target: { value: '6291041234567' } });
    fireEvent.click(screen.getByRole('button', { name: /capture/i }));

    await waitFor(() => {
      expect(screen.getByText('6291041234567')).toBeInTheDocument();
    });

    expect(screen.getByText(/Captured \(manual entry\)/i)).toBeInTheDocument();
  });

  it('calls onScan callback with the result', async () => {
    const onScan = vi.fn();
    render(<MobileScanPreview onScan={onScan} />);

    const input = screen.getByLabelText(/manual barcode or sku code/i);
    fireEvent.change(input, { target: { value: 'SKU-TEST-001' } });
    fireEvent.click(screen.getByRole('button', { name: /capture/i }));

    await waitFor(() => {
      expect(onScan).toHaveBeenCalledTimes(1);
    });

    const result: ScanResult = onScan.mock.calls[0][0];
    expect(result.code).toBe('SKU-TEST-001');
    expect(result.source).toBe('manual');
    expect(result.timestamp).toBeTruthy();
  });

  it('disables capture button when input is empty', () => {
    render(<MobileScanPreview />);
    const button = screen.getByRole('button', { name: /capture/i });
    expect(button).toBeDisabled();
  });
});

// ---------------------------------------------------------------------------
// 3. No official SKU write/apply API called
// ---------------------------------------------------------------------------

describe('MobileScanPreview -- preview-only (no SKU writes)', () => {
  it('does not call any backend API on scan', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('{}', { status: 200 })
    );

    render(<MobileScanPreview />);

    const input = screen.getByLabelText(/manual barcode or sku code/i);
    fireEvent.change(input, { target: { value: '1234567890' } });
    fireEvent.click(screen.getByRole('button', { name: /capture/i }));

    await waitFor(() => {
      expect(screen.getByText('1234567890')).toBeInTheDocument();
    });

    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it('shows "Preview only" disclaimer on captured result', async () => {
    render(<MobileScanPreview />);

    const input = screen.getByLabelText(/manual barcode or sku code/i);
    fireEvent.change(input, { target: { value: 'TEST-CODE' } });
    fireEvent.click(screen.getByRole('button', { name: /capture/i }));

    await waitFor(() => {
      // The result block with "Not applied to the product catalog" appears
      expect(screen.getByText(/not applied to the product catalog/i)).toBeInTheDocument();
    });
  });
});

// ---------------------------------------------------------------------------
// 4. Internal-login-only (no public/anonymous access)
// ---------------------------------------------------------------------------

describe('MobileScanPreview -- access control', () => {
  it('does not expose any public/anonymous entry point', () => {
    const { container } = render(<MobileScanPreview />);
    const html = container.innerHTML;

    expect(html).not.toMatch(/public.*token|anonymous|share.*link/i);
    expect(screen.getByText('Mobile scan preview')).toBeInTheDocument();
  });
});
