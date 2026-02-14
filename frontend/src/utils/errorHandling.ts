import { AxiosError } from 'axios';

/**
 * Pydantic 422 validation error item shape.
 * FastAPI returns `detail` as an array of these objects.
 */
interface ValidationErrorItem {
  loc: (string | number)[];
  msg: string;
  type: string;
}

/**
 * Structured error object shape (409, 403, 404, etc.).
 * FastAPI returns `detail` as a single object with code + message.
 */
interface StructuredErrorDetail {
  code?: string;
  message?: string;
}

type ApiDetailPayload =
  | ValidationErrorItem[]
  | StructuredErrorDetail
  | string;

/**
 * Normalizes any Axios error into a single user-friendly string.
 *
 * Handles three backend error shapes:
 *   1. 422 — `detail` is an array of Pydantic validation errors
 *   2. 409/403/404 — `detail` is an object with `code` and `message`
 *   3. Plain string — `detail` is a raw string
 *   4. 500 — generic server error
 *   5. Fallback — network / unknown errors
 */
export function normalizeApiError(error: unknown): string {
  const axErr = error as AxiosError<{ detail?: ApiDetailPayload }>;
  const status = axErr.response?.status;
  const detail = axErr.response?.data?.detail;

  // ── 422 Unprocessable Entity (Pydantic validation array) ──────────
  if (status === 422 && Array.isArray(detail)) {
    const first = detail[0] as ValidationErrorItem | undefined;
    if (first) {
      const field = first.loc.filter((s) => s !== 'body').join('.');
      return field ? `${field}: ${first.msg}` : first.msg;
    }
    return 'Validation error. Please check your input.';
  }

  // ── 409 Conflict ──────────────────────────────────────────────────
  if (status === 409) {
    if (isStructuredDetail(detail)) {
      return detail.message ?? 'A record with this identifier already exists.';
    }
    return 'A record with this identifier already exists.';
  }

  // ── 403 Forbidden ─────────────────────────────────────────────────
  if (status === 403) {
    if (isStructuredDetail(detail) && detail.message) {
      return detail.message;
    }
    return 'Permission denied. You do not have access to this action.';
  }

  // ── 404 Not Found ─────────────────────────────────────────────────
  if (status === 404) {
    if (isStructuredDetail(detail) && detail.message) {
      return detail.message;
    }
    return 'The requested resource was not found.';
  }

  // ── 500 Internal Server Error ─────────────────────────────────────
  if (status === 500) {
    return 'Internal server error. Please try again or contact support.';
  }

  // ── Structured detail (other status codes) ────────────────────────
  if (typeof detail === 'string') return detail;
  if (isStructuredDetail(detail) && detail.message) return detail.message;

  // ── Network / unknown ─────────────────────────────────────────────
  if (axErr.message) return axErr.message;
  return 'An unexpected error occurred.';
}

function isStructuredDetail(
  detail: ApiDetailPayload | undefined,
): detail is StructuredErrorDetail {
  return (
    detail !== undefined &&
    typeof detail === 'object' &&
    !Array.isArray(detail)
  );
}
