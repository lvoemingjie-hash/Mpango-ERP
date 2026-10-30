import { api } from './api';
import type { ApiResponse } from '@/types/api';
import type { CashierReviewContext, ClientPortalContext } from '@/types/partyContext';

/** Cancellation also prevents superseded same-session errors reaching toasts. */
export async function getCashierReviewContext(id: string, signal?: AbortSignal): Promise<ApiResponse<CashierReviewContext>> {
  const response = await api.get(`/declarations/${encodeURIComponent(id)}/review-context`, { signal });
  return response.data;
}
export async function getClientPortalContext(signal?: AbortSignal): Promise<ApiResponse<ClientPortalContext>> {
  const response = await api.get('/client/auth/context', { signal });
  return response.data;
}
