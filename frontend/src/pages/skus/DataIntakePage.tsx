import { FormEvent, useMemo, useRef, useState } from 'react';
import { ArrowLeftIcon, ArrowUpTrayIcon, ExclamationTriangleIcon } from '@heroicons/react/24/outline';
import { PageHeader } from '@/components/layout/PageHeader';
import { useAuthStore } from '@/stores/authStore';
import { can, INTAKE_PERMISSIONS, SKU_PERMISSIONS } from '@/utils/permissions';
import { normalizeApiError } from '@/utils/errorHandling';
import {
  INTAKE_TARGET_FIELDS,
  intakeService,
  type IntakeApplyResult,
  type IntakeMappingResult,
  type IntakeProductRow,
  type IntakeSourceType,
  type IntakeTargetField,
  type IntakeUploadResult,
  type IntakeValidationIssue,
  type IntakeValidationResult,
  type IntakeWorkspace,
} from '@/services/intakeService';

const FIELD_LABELS: Record<IntakeTargetField, string> = {
  sku_code: 'SKU code',
  name: 'Product name',
  unit: 'Unit',
  category: 'Category',
  unit_price: 'Unit price',
  barcode: 'Barcode',
};

const ISSUE_COPY: Record<string, string> = {
  INVALID_UNIT_PRICE: 'Unit price must be a valid decimal number.',
  MISSING_SKU_CODE: 'SKU code is required for this staged row.',
  MISSING_NAME: 'Product name is required for this staged row.',
  DUPLICATE_STAGED_SKU_CODE: 'This SKU code appears more than once in the staged workspace.',
  UNMAPPED_EXTRA_COLUMN: 'This source column is not mapped and will remain in staging only.',
  FIELD_TOO_LONG: 'A mapped field is longer than the allowed limit.',
  UNIT_DEFAULT_AVAILABLE: 'Unit is missing. U4-E does not write a default during staging preview.',
};

const AUTO_MAP_ALIASES: Record<IntakeTargetField, string[]> = {
  sku_code: ['sku_code', 'sku code', 'sku', 'code', 'product_code', 'item_code'],
  name: ['name', 'product name', 'product_name', 'item_name', 'title'],
  unit: ['unit', 'uom', 'unit_of_measure'],
  category: ['category', 'cat', 'product_category'],
  unit_price: ['unit_price', 'unit price', 'price', 'selling_price'],
  barcode: ['barcode', 'bar_code', 'ean', 'upc'],
};

function friendlyError(error: unknown): string {
  const axErr = error as { response?: { status?: number; data?: { code?: string; message?: string; sku_codes?: string[]; detail?: { code?: string; message?: string; sku_codes?: string[] } } } };
  if (axErr.response?.status === 403) {
    return 'You do not have permission to manage intake workspaces. Ask an admin for intake access.';
  }

  const detail = axErr.response?.data?.detail ?? axErr.response?.data;
  const code = detail?.code;
  const skuCodes = detail?.sku_codes || [];
  if (code === 'ALREADY_APPLIED') return 'This intake workspace has already been applied';
  if (code === 'DUPLICATE_STAGED_SKU_CODE') return `Duplicate staged SKU codes: ${skuCodes.join(', ') || 'review staged rows'}`;
  if (code === 'SKU_CODE_EXISTS') return `Existing SKU codes already in Products: ${skuCodes.join(', ') || 'review staged rows'}`;
  if (code === 'BLOCKING_ISSUES') return 'Revalidate and fix blocking issues before applying this workspace.';
  if (code === 'ROW_LIMIT_EXCEEDED') return 'Upload rejected: the file has more than 5,000 staged rows.';
  if (code === 'COLUMN_LIMIT_EXCEEDED') return 'Upload rejected: the file has more than 100 columns.';
  if (code === 'CELL_TOO_LARGE') return 'Upload rejected: one cell is longer than 2,000 characters.';
  if (code === 'HEADER_TOO_LARGE') return 'Upload rejected: one header is longer than 255 characters.';
  if (code === 'XLSX_PARSE_ERROR') return 'Upload rejected: the XLSX file is unreadable or protected.';

  return normalizeApiError(error);
}

function applyFriendlyError(error: unknown): string {
  const axErr = error as { response?: { status?: number } };
  if (axErr.response?.status === 403) {
    return 'You need both intake:update and skus:import to apply staged rows to Products.';
  }

  return friendlyError(error);
}

function headerLabel(header: string, normalized?: string) {
  return normalized && normalized !== header ? `${header} (${normalized})` : header;
}

function autoMap(headers: string[], normalized: Record<string, string>): Record<string, string> {
  const usedTargets = new Set<string>();
  const mapping: Record<string, string> = {};

  for (const header of headers) {
    const candidates = [header, normalized[header]].filter(Boolean).map((value) => value.toLowerCase().trim());
    for (const field of INTAKE_TARGET_FIELDS) {
      if (usedTargets.has(field)) continue;
      if (candidates.some((candidate) => AUTO_MAP_ALIASES[field].includes(candidate))) {
        mapping[header] = field;
        usedTargets.add(field);
        break;
      }
    }
  }

  return mapping;
}

function issueText(issue: IntakeValidationIssue) {
  return ISSUE_COPY[issue.code] ?? issue.message;
}

function valueText(value: unknown) {
  if (value === null || value === undefined || value === '') return '--';
  return String(value);
}

export function DataIntakePage() {
  const user = useAuthStore((state) => state.user);
  const [workspaceName, setWorkspaceName] = useState('Product intake workspace');
  const [sourceType, setSourceType] = useState<IntakeSourceType>('CUSTOMER_ONBOARDING');
  const [workspace, setWorkspace] = useState<IntakeWorkspace | null>(null);
  const [upload, setUpload] = useState<IntakeUploadResult | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [mappingResult, setMappingResult] = useState<IntakeMappingResult | null>(null);
  const [validation, setValidation] = useState<IntakeValidationResult | null>(null);
  const [rows, setRows] = useState<IntakeProductRow[]>([]);
  const [issues, setIssues] = useState<IntakeValidationIssue[]>([]);
  const [applyResult, setApplyResult] = useState<IntakeApplyResult | null>(null);
  const [showApplyConfirm, setShowApplyConfirm] = useState(false);
  const [applying, setApplying] = useState(false);
  const applyingRef = useRef(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const headerKeys = useMemo(() => {
    if (!upload) return [];
    const normalizedKeys = Object.keys(upload.headers_normalized || {});
    return normalizedKeys.length > 0 ? normalizedKeys : upload.headers_raw;
  }, [upload]);

  const hasApplyPermission = can(user, INTAKE_PERMISSIONS.UPDATE) && can(user, SKU_PERMISSIONS.IMPORT);
  const blockingIssues = issues.filter((issue) => issue.is_blocking);
  const isReadyForApply = validation?.status === 'READY_FOR_EXPORT' && validation.error_count === 0 && blockingIssues.length === 0;
  const isApplied = applyResult?.apply_status === 'applied';

  const applyUnavailableReason = useMemo(() => {
    if (isApplied) return 'Already applied. This workspace cannot be applied again.';
    if (!hasApplyPermission) return 'Missing permission: intake:update and skus:import are required.';
    if (!validation) return 'Validate first before applying staged rows to Products.';
    if (blockingIssues.length > 0 || validation.error_count > 0) return 'Fix blocking issues and revalidate before applying.';
    if (validation.status !== 'READY_FOR_EXPORT') return 'Validate first until the workspace is READY_FOR_EXPORT.';
    return null;
  }, [blockingIssues.length, hasApplyPermission, isApplied, validation]);

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const response = await intakeService.createWorkspace({
        name: workspaceName.trim(),
        source_type: sourceType,
        description: 'Frontend MVP staging preview workspace',
      });
      setWorkspace(response.data.data);
    } catch (err) {
      setError(friendlyError(err));
    } finally {
      setLoading(false);
    }
  }

  async function handleUpload(file: File | undefined) {
    if (!workspace || !file) return;
    const lowerName = file.name.toLowerCase();
    if (!lowerName.endsWith('.csv') && !lowerName.endsWith('.xlsx')) {
      setError('Upload a .csv or .xlsx file for staging preview.');
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const response = await intakeService.upload(workspace.workspace_id, file);
      const uploadResult = response.data.data;
      const headers = Object.keys(uploadResult.headers_normalized || {});
      setUpload(uploadResult);
      setMapping(autoMap(headers.length > 0 ? headers : uploadResult.headers_raw, uploadResult.headers_normalized || {}));
      setMappingResult(null);
      setValidation(null);
      setApplyResult(null);
      setRows([]);
      setIssues([]);
    } catch (err) {
      setError(friendlyError(err));
    } finally {
      setLoading(false);
    }
  }

  async function handleSaveMapping() {
    if (!workspace) return;
    setLoading(true);
    setError(null);
    try {
      const response = await intakeService.updateMapping(workspace.workspace_id, mapping);
      setMappingResult(response.data.data);
    } catch (err) {
      setError(friendlyError(err));
    } finally {
      setLoading(false);
    }
  }

  async function handleValidate() {
    if (!workspace) return;
    setLoading(true);
    setError(null);
    try {
      const validationResponse = await intakeService.validate(workspace.workspace_id);
      const [rowsResponse, issuesResponse] = await Promise.all([
        intakeService.listRows(workspace.workspace_id),
        intakeService.listIssues(workspace.workspace_id),
      ]);
      setValidation(validationResponse.data.data);
      setApplyResult(null);
      setRows(rowsResponse.data.data.items);
      setIssues(issuesResponse.data.data.items);
    } catch (err) {
      setError(friendlyError(err));
    } finally {
      setLoading(false);
    }
  }

  async function handleConfirmApply() {
    if (!workspace || applyingRef.current || !isReadyForApply || !hasApplyPermission || isApplied) return;
    applyingRef.current = true;
    setApplying(true);
    setError(null);
    try {
      const response = await intakeService.apply(workspace.workspace_id);
      setApplyResult(response.data.data);
      setShowApplyConfirm(false);
    } catch (err) {
      setError(applyFriendlyError(err));
    } finally {
      applyingRef.current = false;
      setApplying(false);
    }
  }

  return (
    <div>
      <PageHeader
        title="Data Intake Workspace"
        description="Stage catalog files, map fields, validate rows, and review issues before any catalog SKU apply is considered."
        action={
          <a href="/skus" className="btn-secondary flex items-center gap-2">
            <ArrowLeftIcon className="h-4 w-4" />
            Back to Products
          </a>
        }
      />

      <div className="mb-6 rounded-md border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900" role="status">
        <strong>Controlled intake flow:</strong> validate staged rows first. Apply is available only after confirmation and duplicate checks, and it creates catalog SKU records only.
      </div>

      {error && (
        <div className="mb-6 rounded-md bg-red-50 p-4 text-sm text-red-800" role="alert">
          {error}
        </div>
      )}

      <section className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
        <h2 className="text-lg font-semibold text-gray-900">1. Create workspace</h2>
        <form onSubmit={handleCreate} className="mt-4 grid gap-4 md:grid-cols-[1fr_220px_auto] md:items-end">
          <label className="block text-sm font-medium text-gray-700">
            Workspace name
            <input
              value={workspaceName}
              onChange={(event) => setWorkspaceName(event.target.value)}
              className="input-field mt-1"
              required
            />
          </label>
          <label className="block text-sm font-medium text-gray-700">
            Source type
            <select
              value={sourceType}
              onChange={(event) => setSourceType(event.target.value as IntakeSourceType)}
              className="input-field mt-1"
            >
              <option value="CUSTOMER_ONBOARDING">Customer onboarding</option>
              <option value="CATALOG_REFRESH">Catalog refresh</option>
              <option value="STOCK_INTAKE">Stock intake</option>
            </select>
          </label>
          <button type="submit" className="btn-primary" disabled={loading || workspaceName.trim().length === 0}>
            Create workspace
          </button>
        </form>
        {workspace && (
          <p className="mt-3 text-sm text-green-700">
            Workspace created: <span className="font-medium">{workspace.name}</span> ({workspace.status})
          </p>
        )}
      </section>

      <section className="mt-6 rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
        <h2 className="text-lg font-semibold text-gray-900">2. Upload CSV/XLSX</h2>
        <div className="mt-4 rounded-lg border-2 border-dashed border-gray-300 p-6 text-center">
          <ArrowUpTrayIcon className="mx-auto h-9 w-9 text-gray-400" />
          <p className="mt-2 text-sm text-gray-600">Choose a .csv or .xlsx file for parser preview.</p>
          <input
            type="file"
            accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            aria-label="Upload CSV or XLSX file"
            disabled={!workspace || loading}
            onChange={(event) => handleUpload(event.target.files?.[0])}
            className="mx-auto mt-4 block text-sm text-gray-500 file:mr-4 file:rounded-md file:border-0 file:bg-primary-50 file:px-4 file:py-2 file:text-sm file:font-medium file:text-primary-700 hover:file:bg-primary-100"
          />
        </div>

        {upload && (
          <div className="mt-4 rounded-md bg-blue-50 p-4 text-sm text-blue-900">
            <div className="font-medium">Parser result</div>
            <dl className="mt-2 grid gap-2 sm:grid-cols-3">
              <div><dt className="text-blue-700">Filename</dt><dd>{upload.filename}</dd></div>
              <div><dt className="text-blue-700">Rows</dt><dd>{upload.row_count}</dd></div>
              <div><dt className="text-blue-700">Columns</dt><dd>{upload.column_count}</dd></div>
            </dl>
            <div className="mt-3">
              <span className="text-blue-700">Headers:</span> {headerKeys.join(', ')}
            </div>
          </div>
        )}
      </section>

      {upload && (
        <section className="mt-6 rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
          <h2 className="text-lg font-semibold text-gray-900">3. Map fields</h2>
          <div className="mt-4 overflow-hidden rounded-md border border-gray-200">
            <table className="min-w-full divide-y divide-gray-200 text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-2 text-left font-medium text-gray-500">Source header</th>
                  <th className="px-4 py-2 text-left font-medium text-gray-500">Intake field</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 bg-white">
                {headerKeys.map((header) => (
                  <tr key={header}>
                    <td className="px-4 py-2 font-medium text-gray-900">
                      {headerLabel(header, upload.headers_normalized[header])}
                    </td>
                    <td className="px-4 py-2">
                      <select
                        value={mapping[header] || ''}
                        onChange={(event) => setMapping((current) => ({ ...current, [header]: event.target.value }))}
                        className="input-field py-1 text-sm"
                        aria-label={`Map ${header}`}
                      >
                        <option value="">Skip</option>
                        {INTAKE_TARGET_FIELDS.map((field) => (
                          <option key={field} value={field}>{FIELD_LABELS[field]}</option>
                        ))}
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <button type="button" className="btn-primary" onClick={handleSaveMapping} disabled={loading}>
              Save mapping
            </button>
            {mappingResult && (
              <span className="text-sm text-green-700">
                Mapped {mappingResult.mapped_rows} staged row(s). {mappingResult.unit_default_note}
              </span>
            )}
          </div>
        </section>
      )}

      {mappingResult && (
        <section className="mt-6 rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
          <h2 className="text-lg font-semibold text-gray-900">4. Validate staging preview</h2>
          <button type="button" className="btn-primary mt-4" onClick={handleValidate} disabled={loading}>
            Validate staging rows
          </button>

          {validation && (
            <div className="mt-4 grid gap-3 sm:grid-cols-4">
              <SummaryCard label="Rows" value={validation.row_count} />
              <SummaryCard label="Errors" value={validation.error_count} tone={validation.error_count ? 'error' : 'neutral'} />
              <SummaryCard label="Warnings" value={validation.warning_count} tone={validation.warning_count ? 'warning' : 'neutral'} />
              <SummaryCard label="Status" value={validation.status} />
            </div>
          )}
        </section>
      )}

      {validation && (
        <div className="mt-6 grid gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
          <section className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
            <h2 className="text-lg font-semibold text-gray-900">Rows preview</h2>
            <div className="mt-4 overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200 text-sm">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium text-gray-500">Source row</th>
                    <th className="px-3 py-2 text-left font-medium text-gray-500">SKU</th>
                    <th className="px-3 py-2 text-left font-medium text-gray-500">Name</th>
                    <th className="px-3 py-2 text-left font-medium text-gray-500">Unit price</th>
                    <th className="px-3 py-2 text-left font-medium text-gray-500">Raw values</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 bg-white">
                  {rows.map((row) => (
                    <tr key={row.row_id}>
                      <td className="px-3 py-2">{row.source_row_number}</td>
                      <td className="px-3 py-2">{valueText(row.normalized_values.sku_code ?? row.sku_code)}</td>
                      <td className="px-3 py-2">{valueText(row.normalized_values.name ?? row.name)}</td>
                      <td className="px-3 py-2">{valueText(row.normalized_values.unit_price ?? row.unit_price)}</td>
                      <td className="px-3 py-2 text-gray-500">{Object.keys(row.raw_values).join(', ') || '--'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
            <h2 className="text-lg font-semibold text-gray-900">Issues</h2>
            {issues.length === 0 ? (
              <p className="mt-4 text-sm text-green-700">No validation issues returned.</p>
            ) : (
              <ul className="mt-4 space-y-3">
                {issues.map((issue) => (
                  <li key={issue.issue_id} className="rounded-md border border-gray-200 p-3">
                    <div className="flex items-start gap-2">
                      <ExclamationTriangleIcon className={issue.severity === 'ERROR' ? 'mt-0.5 h-5 w-5 text-red-500' : 'mt-0.5 h-5 w-5 text-amber-500'} />
                      <div>
                        <div className="text-sm font-medium text-gray-900">
                          {issue.severity}: {issueText(issue)}
                        </div>
                        <div className="mt-1 text-xs text-gray-500">
                          {issue.source_row_number ? `Source row ${issue.source_row_number}` : 'File-level issue'}
                          {issue.field ? ` - ${issue.field}` : ''}
                          {issue.source_header ? ` - ${issue.source_header}` : ''}
                        </div>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      )}

      {mappingResult && (
        <section className="mt-6 rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
          <h2 className="text-lg font-semibold text-gray-900">5. Apply to Products</h2>
          <p className="mt-2 text-sm text-gray-600">
            Apply only after validation says READY_FOR_EXPORT. Existing SKU codes are blocked; this flow does not overwrite, upsert, or merge Products, and it does not write stock, pricing, barcode lookup, images, or sellable readiness.
          </p>

          {applyUnavailableReason ? (
            <div className={isApplied ? 'mt-4 rounded-md bg-green-50 p-4 text-sm text-green-800' : 'mt-4 rounded-md bg-gray-50 p-4 text-sm text-gray-700'} role="status">
              {applyUnavailableReason}
            </div>
          ) : (
            <button
              type="button"
              className="btn-primary mt-4"
              onClick={() => setShowApplyConfirm(true)}
              disabled={loading || applying}
            >
              Apply to Products
            </button>
          )}

          {applyResult && (
            <div className="mt-4 rounded-md bg-green-50 p-4 text-sm text-green-800" role="status">
              <div className="font-medium">Created {applyResult.created_count} official catalog Product/SKU record(s) only.</div>
              {applyResult.created_sku_ids.length > 0 && (
                <div className="mt-1">Created SKU IDs: {applyResult.created_sku_ids.join(', ')}</div>
              )}
            </div>
          )}
        </section>
      )}

      {showApplyConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-gray-900/50 p-4">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="apply-confirm-title"
            className="w-full max-w-lg rounded-lg bg-white p-6 shadow-xl"
          >
            <h2 id="apply-confirm-title" className="text-lg font-semibold text-gray-900">Apply staged rows to Products</h2>
            <div className="mt-3 space-y-2 text-sm text-gray-700">
              <p>This writes to official catalog Products/SKUs only.</p>
              <p>It does not write stock, pricing, barcode lookup, images, or sellable readiness.</p>
              <p>Duplicate existing SKU codes will be blocked.</p>
              <p>There is no silent overwrite, upsert, or merge.</p>
            </div>
            <div className="mt-6 flex justify-end gap-3">
              <button type="button" className="btn-secondary" onClick={() => setShowApplyConfirm(false)} disabled={applying}>
                Cancel
              </button>
              <button type="button" className="btn-primary" onClick={handleConfirmApply} disabled={applying}>
                {applying ? 'Applying...' : 'Confirm apply'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function SummaryCard({ label, value, tone = 'neutral' }: { label: string; value: number | string; tone?: 'neutral' | 'error' | 'warning' }) {
  const toneClass = tone === 'error' ? 'text-red-700' : tone === 'warning' ? 'text-amber-700' : 'text-gray-900';
  return (
    <div className="rounded-md border border-gray-200 bg-gray-50 p-4">
      <div className="text-xs font-medium uppercase tracking-wide text-gray-500">{label}</div>
      <div className={`mt-1 text-lg font-semibold ${toneClass}`}>{value}</div>
    </div>
  );
}
