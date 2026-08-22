/**
 * DC-12R1-MVP-L1-J1-H2-A-R1: public supplier-code self-join services.
 *
 * Entry B of the dual-entry contract. The wholesaler CODE is a public
 * supplier locator, never a credential: the lookup returns a SAFE preview
 * plus a short-lived server-signed join_intent, and the final registration
 * submits that intent (never a client-chosen wholesaler id). Both public
 * calls are sent with an explicitly EMPTY Authorization header and the
 * full interceptor opt-out (no global toast echo, no 401 refresh hijack).
 */
import { api } from '@/services/api';
import type { ApiResponse } from '@/types/api';

/** Safe preview + signed intent returned by POST /wholesalers/lookup-code. */
export interface WholesalerJoinPreview {
  found: boolean;
  name?: string | null;
  region?: string | null;
  contact_masked?: string | null;
  join_intent?: string | null;
  expires_at?: string | null;
}

export const selfJoinService = {
  /** Public supplier-code lookup (rate limited server-side). */
  async lookupByCode(code: string) {
    const res = await api.post<ApiResponse<WholesalerJoinPreview>>(
      '/wholesalers/lookup-code',
      { code },
      { headers: { Authorization: '' }, skipAuthInterceptors: true },
    );
    return res.data;
  },
};
