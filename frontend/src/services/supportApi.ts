/**
 * P12 Support Console API client service.
 *
 * Uses the existing Axios singleton (api.ts) with Bearer token injection.
 * All calls go to P12 contract-backed endpoints.
 *
 * Auth transport: Same as P11 platform cockpit -- identity-only (global)
 * super_admin Bearer tokens. The backend P12 guard wraps P10 guard.
 * No X-Platform-Operator secret is ever sent to or stored in the browser.
 *
 * Frontend enforces reason required (min 10 chars) before API call.
 * Backend reason Optional is an implementation detail for route-layer
 * 400 + audit coverage (P12-B-R3), NOT a contract change.
 */
import { api } from './api';
import type {
  CreateSessionRequest,
  CreateBundleRequest,
  SupportSession,
  SupportDiagnosticItem,
  SupportBundle,
} from '@/types/support';

const P12_BASE = '/platform/p12';

export const supportService = {
  /**
   * Create a new support session.
   * Frontend MUST validate reason (min 10 chars) before calling.
   */
  createSession: (body: CreateSessionRequest) =>
    api.post<SupportSession>(`${P12_BASE}/sessions`, body),

  /** Get redacted diagnostics for an active support session. */
  getDiagnostics: (sessionId: string) =>
    api.get<SupportDiagnosticItem[]>(`${P12_BASE}/sessions/${sessionId}/diagnostics`),

  /** Generate a support bundle from an active session. */
  createBundle: (sessionId: string, body?: CreateBundleRequest) =>
    api.post<SupportBundle>(
      `${P12_BASE}/sessions/${sessionId}/bundles`,
      body ?? { bundle_type: 'full' },
    ),

  /** Close an active support session. */
  closeSession: (sessionId: string) =>
    api.post<SupportSession>(`${P12_BASE}/sessions/${sessionId}/close`),
};
