import { api } from '@/services/api';
import type { ApiResponse } from '@/types/api';
import type {
  ImportPreviewResponse,
  ImportValidateResponse,
  ImportApplyResponse,
} from '@/types/import';

/**
 * API client for the U3-B/C/D SKU import pipeline.
 * All endpoints live under /api/v1/skus/import (proxied via Vite dev server).
 */
export const skuImportService = {
  /**
   * Phase 1: Upload CSV and get a preview of detected columns + sample rows.
   * Returns an import_id used for subsequent validate/apply calls.
   */
  preview: (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post<ApiResponse<ImportPreviewResponse>>(
      '/skus/import/preview',
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    );
  },

  /**
   * Phase 2: Submit field mapping and validate rows.
   * Returns row-level errors/warnings. No SKU writes.
   */
  validate: (importId: string, mapping: Record<string, string>) =>
    api.post<ApiResponse<ImportValidateResponse>>(
      `/skus/import/${importId}/validate`,
      { mapping },
    ),

  /**
   * Phase 3: Apply validated import -- writes SKU rows to the database.
   * Only allowed when validate returned status='validated' (error_rows === 0).
   */
  apply: (importId: string, onConflict: 'skip' | 'fail') =>
    api.post<ApiResponse<ImportApplyResponse>>(
      `/skus/import/${importId}/apply`,
      { on_conflict: onConflict },
    ),
};
