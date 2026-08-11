/**
 * DC-12R1-S3-S2B-I2C-I2B — Contract D statement print services (read-only).
 *
 * Both methods are GET-only; no financial/state mutation. Money is
 * server-authoritative and rendered verbatim (no client recomputation).
 * Dynamic path/query values are encoded.
 */
import { api } from '@/services/api';
import type { ApiResponse } from '@/types/api';
import type { StatementPrintView } from '@/types/statement';

/**
 * Retailer-side printable relationship account statement.
 * GET /client/statements/print?from=YYYY-MM-DD&to=YYYY-MM-DD
 */
export const getRetailerStatementPrint = async (
  from: string,
  to: string,
  includePending = false,
): Promise<ApiResponse<StatementPrintView>> => {
  const resp = await api.get('/client/statements/print', {
    params: {
      from: encodeURIComponent(from),
      to: encodeURIComponent(to),
      include_pending: includePending,
    },
  });
  return resp.data;
};

/**
 * Supplier-side printable relationship account statement.
 * GET /statements/print?retailer_id=<uuid>&from=YYYY-MM-DD&to=YYYY-MM-DD
 * `retailerId` is only a target selector; the active binding under the token
 * tenant remains the authority.
 */
export const getSupplierStatementPrint = async (
  retailerId: string,
  from: string,
  to: string,
  includePending = false,
): Promise<ApiResponse<StatementPrintView>> => {
  const resp = await api.get('/statements/print', {
    params: {
      retailer_id: encodeURIComponent(retailerId),
      from: encodeURIComponent(from),
      to: encodeURIComponent(to),
      include_pending: includePending,
    },
  });
  return resp.data;
};
