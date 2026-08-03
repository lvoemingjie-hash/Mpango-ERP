/** DC-12R1-S3-S2B-I2B: Declaration API service (retailer + cashier). */
import { api } from './api';
import type {
  PaymentDeclaration,
  StatementLine,
  DeclarationConfirmResponse,
  DeclarationStatus,
} from '@/types/declaration';
import type { ApiResponse, PaginatedData } from '@/types/api';

/** Retailer: submit a payment declaration. */
export const submitDeclaration = async (
  orderId: string,
  payload: { declared_amount: string; method: string; transfer_reference?: string | null },
  idempotencyKey: string
): Promise<ApiResponse<PaymentDeclaration>> => {
  const resp = await api.post(`/client/orders/${orderId}/declare`, payload, {
    headers: { 'X-Declaration-Idempotency-Key': idempotencyKey },
  });
  return resp.data;
};

/** Retailer: list own declarations. */
export const listClientDeclarations = async (
  page = 1,
  size = 20,
  status?: DeclarationStatus
): Promise<ApiResponse<PaginatedData<PaymentDeclaration>>> => {
  const params: Record<string, unknown> = { page, size };
  if (status) params.status = status;
  const resp = await api.get('/client/declarations', { params });
  return resp.data;
};

/** Retailer: get a single declaration. */
export const getClientDeclaration = async (
  id: string
): Promise<ApiResponse<PaymentDeclaration>> => {
  const resp = await api.get(`/client/declarations/${id}`);
  return resp.data;
};

/** Retailer: get statement line items. */
export const getClientStatement = async (
  page = 1,
  size = 20
): Promise<ApiResponse<PaginatedData<StatementLine>>> => {
  const resp = await api.get('/client/statements', { params: { page, size } });
  return resp.data;
};

/** Cashier: list all declarations. */
export const listDeclarations = async (
  page = 1,
  size = 20,
  status?: DeclarationStatus
): Promise<ApiResponse<PaginatedData<PaymentDeclaration>>> => {
  const params: Record<string, unknown> = { page, size };
  if (status) params.status = status;
  const resp = await api.get('/declarations', { params });
  return resp.data;
};

/** Cashier: confirm a declaration. */
export const confirmDeclaration = async (
  id: string
): Promise<ApiResponse<DeclarationConfirmResponse>> => {
  const resp = await api.post(`/declarations/${id}/confirm`);
  return resp.data;
};

/** Cashier: reject a declaration. */
export const rejectDeclaration = async (
  id: string,
  reason: string
): Promise<ApiResponse<PaymentDeclaration>> => {
  const resp = await api.post(`/declarations/${id}/reject`, { reason });
  return resp.data;
};
