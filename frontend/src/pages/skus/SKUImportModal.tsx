import { useState, useCallback, useRef } from 'react';
import { Dialog } from '@headlessui/react';
import { XMarkIcon, ArrowUpTrayIcon } from '@heroicons/react/24/outline';
import { skuImportService } from '@/services/skuImportService';
import { useToastStore } from '@/stores/toastStore';
import { normalizeApiError } from '@/utils/errorHandling';
import type {
  ImportPreviewResponse,
  ImportValidateResponse,
  ImportApplyResponse,
  MappableField,
} from '@/types/import';
import {
  ALL_MAPPABLE_FIELDS,
  REQUIRED_FIELDS,
  UNSUPPORTED_FIELDS,
} from '@/types/import';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface SKUImportModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

// ---------------------------------------------------------------------------
// Wizard step enum
// ---------------------------------------------------------------------------

type Step = 'upload' | 'mapping' | 'validate' | 'apply';

// ---------------------------------------------------------------------------
// Auto-mapping heuristic
// ---------------------------------------------------------------------------

const CANONICAL_LABELS: Record<MappableField, string[]> = {
  sku_code: ['sku_code', 'skucode', 'sku code', 'sku', 'code', 'product_code', 'item_code'],
  name: ['name', 'product_name', 'product name', 'product', 'title', 'item_name', 'description'],
  description: ['description', 'desc', 'product_description', 'details'],
  unit: ['unit', 'uom', 'unit_of_measure', 'measure'],
  category: ['category', 'cat', 'product_category', 'group'],
  is_active: ['is_active', 'active', 'status', 'enabled'],
};

function autoMap(columns: string[]): Record<string, string> {
  const mapping: Record<string, string> = {};

  for (const col of columns) {
    const lower = col.toLowerCase().trim();
    let matched = false;
    for (const [field, aliases] of Object.entries(CANONICAL_LABELS)) {
      if (aliases.includes(lower) && !Object.values(mapping).includes(field)) {
        mapping[col] = field;
        matched = true;
        break;
      }
    }
    if (!matched) {
      // Leave unmapped -- user can manually assign or ignore
    }
  }
  return mapping;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function SKUImportModal({ isOpen, onClose, onSuccess }: SKUImportModalProps) {
  const [step, setStep] = useState<Step>('upload');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [permissionError, setPermissionError] = useState(false);

  // Phase data
  const [preview, setPreview] = useState<ImportPreviewResponse | null>(null);
  const [validation, setValidation] = useState<ImportValidateResponse | null>(null);
  const [applyResult, setApplyResult] = useState<ImportApplyResponse | null>(null);

  // User choices
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [onConflict, setOnConflict] = useState<'skip' | 'fail'>('skip');
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ---------------------------------------------------------------------------
  // Reset state on close
  // ---------------------------------------------------------------------------
  const resetAndClose = useCallback(() => {
    setStep('upload');
    setLoading(false);
    setError(null);
    setPermissionError(false);
    setPreview(null);
    setValidation(null);
    setApplyResult(null);
    setMapping({});
    setOnConflict('skip');
    onClose();
  }, [onClose]);

  // ---------------------------------------------------------------------------
  // Error handler
  // ---------------------------------------------------------------------------
  const handleError = useCallback((err: unknown) => {
    const msg = normalizeApiError(err);
    // Check for 403
    const axErr = err as { response?: { status?: number } };
    if (axErr.response?.status === 403) {
      setPermissionError(true);
      setError('Your account lacks product import permission.');
    } else {
      setError(msg);
    }
  }, []);

  // ---------------------------------------------------------------------------
  // Step 1: Upload
  // ---------------------------------------------------------------------------
  const handleFileSelect = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!file.name.toLowerCase().endsWith('.csv')) {
      setError('Please upload a CSV file (.csv). Excel files are not supported.');
      return;
    }

    setLoading(true);
    setError(null);
    setPermissionError(false);

    try {
      const res = await skuImportService.preview(file);
      const data = res.data.data;
      setPreview(data);
      const autoMapping = autoMap(data.columns_detected);
      setMapping(autoMapping);
      setStep('mapping');
    } catch (err) {
      handleError(err);
    } finally {
      setLoading(false);
      // Reset file input so the same file can be re-selected
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }, [handleError]);

  // ---------------------------------------------------------------------------
  // Step 2: Mapping -> Validate
  // ---------------------------------------------------------------------------
  const handleValidate = useCallback(async () => {
    if (!preview) return;

    // Check that required fields are mapped
    const mappedFields = new Set(Object.values(mapping));
    for (const req of REQUIRED_FIELDS) {
      if (!mappedFields.has(req)) {
        setError(`Required field "${req}" must be mapped to a column.`);
        return;
      }
    }

    setLoading(true);
    setError(null);

    try {
      const res = await skuImportService.validate(preview.import_id, mapping);
      setValidation(res.data.data);
      setStep('validate');
    } catch (err) {
      handleError(err);
    } finally {
      setLoading(false);
    }
  }, [preview, mapping, handleError]);

  // ---------------------------------------------------------------------------
  // Step 3: Validate results -> Apply
  // ---------------------------------------------------------------------------
  const handleApply = useCallback(async () => {
    if (!preview) return;

    setLoading(true);
    setError(null);

    try {
      const res = await skuImportService.apply(preview.import_id, onConflict);
      setApplyResult(res.data.data);
      setStep('apply');
      if (res.data.data.status === 'completed') {
        useToastStore.getState().addToast({
          type: 'success',
          title: 'Import Complete',
          message: `Created ${res.data.data.created} product(s), skipped ${res.data.data.skipped}.`,
        });
        onSuccess();
      }
    } catch (err) {
      handleError(err);
    } finally {
      setLoading(false);
    }
  }, [preview, onConflict, handleError, onSuccess]);

  // ---------------------------------------------------------------------------
  // Mapping helpers
  // ---------------------------------------------------------------------------
  const updateMapping = (column: string, field: string) => {
    setMapping((prev) => {
      const next = { ...prev };
      if (field === '') {
        delete next[column];
      } else {
        next[column] = field;
      }
      return next;
    });
  };

  // ---------------------------------------------------------------------------
  // Render helpers
  // ---------------------------------------------------------------------------

  const renderUploadStep = () => (
    <div className="space-y-4">
      <p className="text-sm text-gray-500">
        Upload a CSV file with your product data. Supported fields:{' '}
        <span className="font-medium text-gray-700">
          {ALL_MAPPABLE_FIELDS.join(', ')}
        </span>.
      </p>
      <div className="rounded-lg border-2 border-dashed border-gray-300 p-8 text-center hover:border-primary-400 transition-colors">
        <ArrowUpTrayIcon className="mx-auto h-10 w-10 text-gray-400" />
        <p className="mt-2 text-sm text-gray-600">
          Click to select a CSV file, or drag and drop
        </p>
        <p className="mt-1 text-xs text-gray-400">Max 10 MB -- CSV only</p>
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv,text/csv"
          onChange={handleFileSelect}
          aria-label="Click to select a CSV file"
          className="mt-4 mx-auto block text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-medium file:bg-primary-50 file:text-primary-700 hover:file:bg-primary-100"
        />
      </div>
      {/* Unsupported fields notice */}
      <div className="rounded-md bg-amber-50 p-3">
        <p className="text-xs text-amber-800">
          <strong>Note:</strong> This import only creates basic SKU records. It does{' '}
          <u>not</u> import inventory, pricing, images, barcodes, or custom attributes.
        </p>
      </div>
    </div>
  );

  const renderMappingStep = () => {
    if (!preview) return null;
    return (
      <div className="space-y-4">
        <div className="rounded-md bg-blue-50 p-3">
          <p className="text-sm text-blue-700">
            <strong>{preview.source.filename}</strong> -- {preview.source.row_count} rows detected,{' '}
            {preview.columns_detected.length} columns.
          </p>
        </div>

        {/* Column mapping table */}
        <div className="max-h-64 overflow-y-auto">
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-3 py-2 text-left font-medium text-gray-500">CSV Column</th>
                <th className="px-3 py-2 text-left font-medium text-gray-500">Mpango Field</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {preview.columns_detected.map((col) => {
                const lower = col.toLowerCase().trim();
                const isUnsupported = UNSUPPORTED_FIELDS.some(
                  (u) => lower === u || lower.startsWith(u + '.') || lower.startsWith(u + '_'),
                );
                return (
                  <tr key={col} className={isUnsupported ? 'bg-red-50' : ''}>
                    <td className="px-3 py-2 font-medium text-gray-900">{col}</td>
                    <td className="px-3 py-2">
                      {isUnsupported ? (
                        <span className="text-xs text-red-600 font-medium">
                          Not supported in this import
                        </span>
                      ) : (
                        <select
                          value={mapping[col] || ''}
                          onChange={(e) => updateMapping(col, e.target.value)}
                          className="input-field text-sm py-1"
                        >
                          <option value="">-- Skip --</option>
                          {ALL_MAPPABLE_FIELDS.map((f) => (
                            <option key={f} value={f}>
                              {f}
                              {REQUIRED_FIELDS.includes(f as typeof REQUIRED_FIELDS[number]) ? ' *' : ''}
                            </option>
                          ))}
                        </select>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Sample rows */}
        {preview.sample_rows.length > 0 && (
          <details className="text-sm">
            <summary className="cursor-pointer text-gray-600 hover:text-gray-900">
              Preview first {preview.sample_rows.length} rows
            </summary>
            <div className="mt-2 overflow-x-auto rounded border border-gray-200">
              <table className="min-w-full divide-y divide-gray-200 text-xs">
                <thead className="bg-gray-50">
                  <tr>
                    {preview.columns_detected.map((col) => (
                      <th key={col} className="px-2 py-1 text-left font-medium text-gray-500 whitespace-nowrap">
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {preview.sample_rows.map((row, i) => (
                    <tr key={i}>
                      {preview.columns_detected.map((col) => (
                        <td key={col} className="px-2 py-1 text-gray-700 whitespace-nowrap">
                          {String((row as Record<string, unknown>)[col] ?? '')}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        )}

        {/* Required fields legend */}
        <p className="text-xs text-gray-500">
          * Required fields -- both <strong>sku_code</strong> and <strong>name</strong> must be mapped.
        </p>
      </div>
    );
  };

  const renderValidateStep = () => {
    if (!validation) return null;
    const hasErrors = validation.error_rows > 0;
    return (
      <div className="space-y-4">
        {/* Summary */}
        <div className="grid grid-cols-3 gap-3">
          <div className="rounded-lg bg-green-50 p-3 text-center">
            <p className="text-2xl font-bold text-green-700">{validation.valid_rows}</p>
            <p className="text-xs text-green-600">Valid rows</p>
          </div>
          <div className={`rounded-lg p-3 text-center ${hasErrors ? 'bg-red-50' : 'bg-gray-50'}`}>
            <p className={`text-2xl font-bold ${hasErrors ? 'text-red-700' : 'text-gray-400'}`}>
              {validation.error_rows}
            </p>
            <p className={`text-xs ${hasErrors ? 'text-red-600' : 'text-gray-400'}`}>Error rows</p>
          </div>
          <div className="rounded-lg bg-amber-50 p-3 text-center">
            <p className="text-2xl font-bold text-amber-700">{validation.warning_rows}</p>
            <p className="text-xs text-amber-600">Warning rows</p>
          </div>
        </div>

        {/* Errors list */}
        {validation.errors.length > 0 && (
          <div className="max-h-40 overflow-y-auto rounded-md bg-red-50 p-3">
            <p className="text-sm font-medium text-red-800 mb-2">Errors:</p>
            <ul className="space-y-1">
              {validation.errors.slice(0, 20).map((err, i) => (
                <li key={i} className="text-xs text-red-700">
                  Row {err.row}
                  {err.field && <span className="font-medium"> ({err.field})</span>}: {err.message}
                  {err.sku_code && <span className="text-red-500"> [{err.sku_code}]</span>}
                </li>
              ))}
              {validation.errors.length > 20 && (
                <li className="text-xs text-red-500 italic">
                  ...and {validation.errors.length - 20} more errors
                </li>
              )}
            </ul>
          </div>
        )}

        {/* Warnings list */}
        {validation.warnings.length > 0 && (
          <details className="rounded-md bg-amber-50 p-3">
            <summary className="cursor-pointer text-sm font-medium text-amber-800">
              {validation.warnings.length} warning(s)
            </summary>
            <ul className="mt-2 space-y-1">
              {validation.warnings.slice(0, 10).map((w, i) => (
                <li key={i} className="text-xs text-amber-700">
                  Row {w.row}{w.field && ` (${w.field})`}: {w.message}
                </li>
              ))}
            </ul>
          </details>
        )}

        {/* Block apply if errors */}
        {hasErrors && (
          <div className="rounded-md bg-red-100 p-3">
            <p className="text-sm font-medium text-red-800">
              Import blocked: {validation.error_rows} row(s) have errors. Fix your CSV and re-upload.
            </p>
          </div>
        )}

        {/* Conflict strategy */}
        {!hasErrors && (
          <div className="rounded-md border border-gray-200 p-4 space-y-3">
            <p className="text-sm font-medium text-gray-700">Conflict strategy</p>
            <p className="text-xs text-gray-500">
              What happens when a SKU code already exists in your catalog?
            </p>
            <div className="space-y-2">
              <label className="flex items-start gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="on_conflict"
                  value="skip"
                  checked={onConflict === 'skip'}
                  onChange={() => setOnConflict('skip')}
                  className="mt-0.5"
                />
                <div>
                  <span className="text-sm font-medium text-gray-900">Skip duplicates</span>
                  <p className="text-xs text-gray-500">
                    Skip rows with existing SKU codes. New products are still created.
                  </p>
                </div>
              </label>
              <label className="flex items-start gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="on_conflict"
                  value="fail"
                  checked={onConflict === 'fail'}
                  onChange={() => setOnConflict('fail')}
                  className="mt-0.5"
                />
                <div>
                  <span className="text-sm font-medium text-gray-900">Fail on duplicate</span>
                  <p className="text-xs text-gray-500">
                    Abort the entire import if any SKU code already exists. No products are created.
                  </p>
                </div>
              </label>
            </div>
          </div>
        )}
      </div>
    );
  };

  const renderApplyStep = () => {
    if (!applyResult) return null;
    const isCompleted = applyResult.status === 'completed';
    return (
      <div className="space-y-4">
        {isCompleted ? (
          <>
            <div className="rounded-md bg-green-50 p-4 text-center">
              <p className="text-lg font-bold text-green-700">Import Complete</p>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div className="rounded-lg bg-green-50 p-3 text-center">
                <p className="text-2xl font-bold text-green-700">{applyResult.created}</p>
                <p className="text-xs text-green-600">Created</p>
              </div>
              <div className="rounded-lg bg-gray-50 p-3 text-center">
                <p className="text-2xl font-bold text-gray-700">{applyResult.skipped}</p>
                <p className="text-xs text-gray-600">Skipped</p>
              </div>
              <div className="rounded-lg bg-blue-50 p-3 text-center">
                <p className="text-2xl font-bold text-blue-700">{applyResult.updated}</p>
                <p className="text-xs text-blue-600">Updated</p>
              </div>
            </div>
            {applyResult.audit_run_id && (
              <p className="text-xs text-gray-500 text-center">
                Audit run: {applyResult.audit_run_id}
              </p>
            )}
          </>
        ) : (
          <div className="rounded-md bg-red-50 p-4 text-center">
            <p className="text-lg font-bold text-red-700">Import Failed</p>
            <p className="text-sm text-red-600 mt-1">
              No products were created. Please fix your data and try again.
            </p>
            {applyResult.errors.length > 0 && (
              <ul className="mt-3 space-y-1 text-left">
                {applyResult.errors.slice(0, 10).map((err, i) => (
                  <li key={i} className="text-xs text-red-700">
                    Row {err.row}: {err.message}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    );
  };

  // ---------------------------------------------------------------------------
  // Step titles and navigation
  // ---------------------------------------------------------------------------

  const stepTitles: Record<Step, string> = {
    upload: 'Import Products',
    mapping: 'Map Columns',
    validate: 'Validation Results',
    apply: 'Import Results',
  };

  const canProceed: Record<Step, boolean> = {
    upload: !!preview,
    mapping: !!preview,
    validate: !!validation && validation.error_rows === 0,
    apply: false,
  };

  return (
    <Dialog open={isOpen} onClose={resetAndClose} className="relative z-50">
      <div className="fixed inset-0 bg-black/30" aria-hidden="true" />
      <div className="fixed inset-0 flex items-center justify-center p-4">
        <Dialog.Panel className="mx-auto w-full max-w-2xl rounded-xl bg-white p-6 shadow-xl max-h-[90vh] overflow-y-auto">
          {/* Header */}
          <div className="flex items-center justify-between mb-4">
            <Dialog.Title className="text-lg font-semibold text-gray-900">
              {stepTitles[step]}
            </Dialog.Title>
            <button onClick={resetAndClose} className="text-gray-400 hover:text-gray-500">
              <XMarkIcon className="h-5 w-5" />
            </button>
          </div>

          {/* Step indicator */}
          <div className="mb-6">
            <div className="flex items-center gap-1">
              {(['upload', 'mapping', 'validate', 'apply'] as Step[]).map((s, i) => (
                <div key={s} className="flex items-center">
                  <div
                    className={`h-2 flex-1 rounded-full ${
                      step === s
                        ? 'bg-primary-600'
                        : (['upload', 'mapping', 'validate', 'apply'] as Step[]).indexOf(step) > i
                          ? 'bg-primary-300'
                          : 'bg-gray-200'
                    }`}
                  />
                </div>
              ))}
            </div>
            <div className="flex justify-between mt-1">
              {(['Upload', 'Map', 'Validate', 'Apply'] as const).map((label, i) => (
                <span
                  key={label}
                  className={`text-xs ${
                    (['upload', 'mapping', 'validate', 'apply'] as Step[]).indexOf(step) >= i
                      ? 'text-primary-600 font-medium'
                      : 'text-gray-400'
                  }`}
                >
                  {label}
                </span>
              ))}
            </div>
          </div>

          {/* Permission error */}
          {permissionError && (
            <div className="rounded-md bg-red-50 p-4 mb-4">
              <p className="text-sm font-medium text-red-800">
                Your account lacks product import permission.
              </p>
              <p className="text-xs text-red-600 mt-1">
                Contact your administrator to get the &quot;skus:import&quot; permission or an admin role.
              </p>
            </div>
          )}

          {/* Generic error */}
          {error && !permissionError && (
            <div className="rounded-md bg-red-50 p-4 mb-4">
              <p className="text-sm text-red-700">{error}</p>
            </div>
          )}

          {/* Step content */}
          {step === 'upload' && renderUploadStep()}
          {step === 'mapping' && renderMappingStep()}
          {step === 'validate' && renderValidateStep()}
          {step === 'apply' && renderApplyStep()}

          {/* Footer actions */}
          <div className="mt-6 flex justify-between">
            <div>
              {step !== 'upload' && step !== 'apply' && (
                <button
                  type="button"
                  onClick={() => {
                    setError(null);
                    if (step === 'validate') setStep('mapping');
                    else if (step === 'mapping') setStep('upload');
                  }}
                  className="btn-secondary"
                  disabled={loading}
                >
                  Back
                </button>
              )}
            </div>
            <div className="flex gap-3">
              <button
                type="button"
                onClick={resetAndClose}
                className="btn-secondary"
                disabled={loading}
              >
                {step === 'apply' ? 'Close' : 'Cancel'}
              </button>

              {step === 'mapping' && (
                <button
                  type="button"
                  onClick={handleValidate}
                  className="btn-primary"
                  disabled={loading || !canProceed.mapping}
                >
                  {loading ? 'Validating...' : 'Validate'}
                </button>
              )}

              {step === 'validate' && validation && validation.error_rows === 0 && (
                <button
                  type="button"
                  onClick={handleApply}
                  className="btn-primary"
                  disabled={loading}
                >
                  {loading ? 'Applying...' : `Apply Import (${onConflict} duplicates)`}
                </button>
              )}
            </div>
          </div>
        </Dialog.Panel>
      </div>
    </Dialog>
  );
}
