import { api } from '@/services/api';
import type { ApiResponse, PaginatedData } from '@/types/api';

export type IntakeSourceType = 'CUSTOMER_ONBOARDING' | 'CATALOG_REFRESH' | 'STOCK_INTAKE' | 'MOBILE_SCAN';

export type IntakeWorkspaceStatus =
  | 'DRAFT'
  | 'OPEN'
  | 'UPLOADED'
  | 'MAPPED'
  | 'VALIDATING'
  | 'NEEDS_REVIEW'
  | 'READY_FOR_EXPORT'
  | 'EXPORTED'
  | 'PUSHED_TO_ERP_PREVIEW'
  | 'CLOSED'
  | 'CANCELLED';

export interface IntakeWorkspace {
  workspace_id: string;
  tenant_id: string;
  name: string;
  description?: string | null;
  source_type: IntakeSourceType;
  status: IntakeWorkspaceStatus;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface IntakeUploadResult {
  upload_id: string;
  workspace_id: string;
  filename: string;
  file_ext: string;
  status: string;
  row_count: number;
  column_count: number;
  headers_raw: string[];
  headers_normalized: Record<string, string>;
  parse_summary: Record<string, unknown>;
  created_at: string;
}

export interface IntakeMappingResult {
  workspace_id: string;
  mapped_rows: number;
  mapping: Record<string, string>;
  status: IntakeWorkspaceStatus;
  unit_default_note: string;
}

export interface IntakeValidationResult {
  workspace_id: string;
  status: IntakeWorkspaceStatus;
  row_count: number;
  error_count: number;
  warning_count: number;
}

export interface IntakeProductRow {
  row_id: string;
  upload_id: string;
  source_row_number: number;
  row_index: number;
  raw_values: Record<string, unknown>;
  normalized_values: Record<string, unknown>;
  mapping_version: number;
  sku_code?: string | null;
  name?: string | null;
  unit?: string | null;
  category?: string | null;
  unit_price?: string | null;
  barcode?: string | null;
  review_status: string;
  created_at: string;
  updated_at: string;
}

export interface IntakeValidationIssue {
  issue_id: string;
  upload_id?: string | null;
  row_id?: string | null;
  source_row_number?: number | null;
  severity: 'ERROR' | 'WARNING';
  code: string;
  field?: string | null;
  source_header?: string | null;
  message: string;
  is_blocking: boolean;
  created_at: string;
}

export const INTAKE_TARGET_FIELDS = [
  'sku_code',
  'name',
  'unit',
  'category',
  'unit_price',
  'barcode',
] as const;

export type IntakeTargetField = typeof INTAKE_TARGET_FIELDS[number];

export const intakeService = {
  createWorkspace: (body: { name: string; description?: string; source_type: IntakeSourceType }) =>
    api.post<ApiResponse<IntakeWorkspace>>('/intake/workspaces', body),

  upload: (workspaceId: string, file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post<ApiResponse<IntakeUploadResult>>(
      `/intake/workspaces/${workspaceId}/uploads`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    );
  },

  updateMapping: (workspaceId: string, mapping: Record<string, string>) =>
    api.put<ApiResponse<IntakeMappingResult>>(
      `/intake/workspaces/${workspaceId}/mapping`,
      { mapping },
    ),

  validate: (workspaceId: string) =>
    api.post<ApiResponse<IntakeValidationResult>>(`/intake/workspaces/${workspaceId}/validate`),

  listRows: (workspaceId: string) =>
    api.get<ApiResponse<PaginatedData<IntakeProductRow>>>(`/intake/workspaces/${workspaceId}/rows`),

  listIssues: (workspaceId: string) =>
    api.get<ApiResponse<PaginatedData<IntakeValidationIssue>>>(`/intake/workspaces/${workspaceId}/issues`),
};
