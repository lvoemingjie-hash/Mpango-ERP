/**
 * TypeScript types for the U3-B/C/D SKU import pipeline.
 * Mirrors backend/schemas/import_schemas.py contract.
 */

// ---------------------------------------------------------------------------
// Shared row-level detail types
// ---------------------------------------------------------------------------

export interface ImportErrorDetail {
  row: number;
  field?: string;
  sku_code?: string;
  message: string;
}

export interface ImportWarningDetail {
  row: number;
  field?: string;
  message: string;
}

// ---------------------------------------------------------------------------
// Phase 1: Preview
// ---------------------------------------------------------------------------

export interface ImportSourceInfo {
  filename: string;
  encoding: string;
  row_count: number;
}

export interface ImportPreviewResponse {
  import_id: string;
  source: ImportSourceInfo;
  columns_detected: string[];
  sample_rows: Record<string, unknown>[];
}

// ---------------------------------------------------------------------------
// Phase 2: Validate
// ---------------------------------------------------------------------------

export type ImportValidateStatus = 'validated' | 'needs_review';

export interface ImportValidateResponse {
  import_id: string;
  status: ImportValidateStatus;
  valid_rows: number;
  error_rows: number;
  warning_rows: number;
  errors: ImportErrorDetail[];
  warnings: ImportWarningDetail[];
}

// ---------------------------------------------------------------------------
// Phase 3: Apply
// ---------------------------------------------------------------------------

export type ImportApplyStatus = 'completed' | 'failed';

export interface ImportApplyResponse {
  import_id: string;
  status: ImportApplyStatus;
  created: number;
  skipped: number;
  updated: number;
  errors: ImportErrorDetail[];
  audit_run_id: string | null;
}

// ---------------------------------------------------------------------------
// Field mapping constants
// ---------------------------------------------------------------------------

export const REQUIRED_FIELDS = ['sku_code', 'name'] as const;
export const OPTIONAL_FIELDS = ['description', 'unit', 'category', 'is_active'] as const;
export const ALL_MAPPABLE_FIELDS = [...REQUIRED_FIELDS, ...OPTIONAL_FIELDS] as const;

/** Fields explicitly NOT supported in this import scope. */
export const UNSUPPORTED_FIELDS = [
  'stock',
  'price',
  'image',
  'barcode',
  'custom_attributes',
] as const;

export type MappableField = (typeof ALL_MAPPABLE_FIELDS)[number];
