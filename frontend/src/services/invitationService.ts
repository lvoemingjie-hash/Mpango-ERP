/**
 * DC-12R1-MVP-L1-J1-H2-A: retailer invitation API adapter.
 *
 * Thin, contract-faithful wrappers over the existing backend invitation
 * endpoints (api/v1/invitations.py). No schema drift is introduced:
 *  - POST /invitations body is the backend InvitationCreateRequest verbatim
 *    (snake_case, both fields optional);
 *  - POST /invitations/lookup carries the code ONLY in the JSON body — the
 *    code never travels in a URL path or query string.
 *
 * The deprecated GET /invitations/{code} (path token) is intentionally NOT
 * wrapped: new UI must not generate or consume path-token requests.
 */
import { api } from '@/services/api';
import type { ApiResponse } from '@/types/api';

/** Backend InvitationCreateRequest (snake_case; both fields optional). */
export interface InvitationCreatePayload {
  retailer_phone?: string;
  expires_at?: string;
}

/** Backend InvitationData response (serialized snake_case). */
export interface InvitationData {
  code: string;
  status: string;
  wholesaler_id: string;
  retailer_phone: string | null;
  expires_at: string | null;
  created_at: string;
}

/** Backend InvitationLookupData response (serialized snake_case). */
export interface InvitationLookupData {
  code: string;
  usable: boolean;
  reason: string | null;
  status?: string;
  wholesaler_id?: string;
  wholesaler_name?: string | null;
  expires_at?: string | null;
}

export const invitationService = {
  /** Create an invitation (wholesaler side; requires invitations:create). */
  async create(payload: InvitationCreatePayload) {
    const res = await api.post<ApiResponse<InvitationData>>('/invitations', payload);
    return res.data;
  },

  /** Public preflight: the code travels ONLY in the JSON body. */
  async lookup(code: string) {
    const res = await api.post<ApiResponse<InvitationLookupData>>('/invitations/lookup', {
      code,
    });
    return res.data;
  },
};
