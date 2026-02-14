/**
 * Generic API response types.
 * Mirrors backend schemas/common.py envelope format.
 */

export interface ApiResponse<T> {
  success: boolean;
  data: T;
  timestamp: string;
}

export interface ApiErrorDetail {
  field?: string;
  message?: string;
  meta?: Record<string, unknown>;
}

export interface ApiErrorResponse {
  success: false;
  error: {
    code: string;
    message: string;
    details?: ApiErrorDetail[];
  };
  timestamp: string;
}

export interface PaginatedData<T> {
  items: T[];
  pagination: {
    page: number;
    size: number;
    total: number;
    pages: number;
  };
}

export interface MessageResponse {
  success: boolean;
  message: string;
  timestamp: string;
}
