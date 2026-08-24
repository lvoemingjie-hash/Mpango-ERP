/**
 * In-memory journey state (task directive #9).
 *
 * workers=1 keeps every spec file in the same worker process, so this module
 * state carries the journey token chain across files. Everything here lives
 * in process memory ONLY: it is never written to disk, never logged, never
 * included in a report, and failure messages must never interpolate these
 * values. The store holds the maildir-derived reset link/token for the
 * A1 single-copy journey, the M1 shared-identity journey, neutrality
 * fingerprints, and in-memory provisioning handles.
 */

import type { ResponseFingerprint } from './neutrality.js';

export interface ProvisioningHandle {
  /** Contextual (tenant-scoped) access token for official-API provisioning calls. */
  ctxToken: string;
  tenantId: string;
  tenantName: string;
}

interface A1State {
  provisioned?: ProvisioningHandle;
  ineligibleProvisioned?: boolean;
  /** Wall-clock ms just before the F3 forgot-password submit (maildir `since` anchor). */
  f3SubmittedAt?: number;
  fingerprints: Partial<Record<'F3' | 'F4' | 'F5', ResponseFingerprint>>;
  /** Visible neutral copy shown after the F3 submit (compared by F4/F5). */
  neutralVisibleText?: string;
  /** F6-derived reset link (in-memory only). */
  resetLink?: string;
  /** Reset link consumed by R8 — kept for R11 replay. */
  usedResetLink?: string;
}

interface M1State {
  provisionGatePassed?: boolean;
  w1?: ProvisioningHandle;
  w2?: ProvisioningHandle;
  forgotSubmittedAt?: number;
  resetLink?: string;
}

interface JourneyState {
  a1: A1State;
  m1: M1State;
}

const state: JourneyState = { a1: { fingerprints: {} }, m1: {} };

export function a1State(): A1State {
  return state.a1;
}

export function m1State(): M1State {
  return state.m1;
}

/** Extract the raw token from a reset link's fragment (never log the result). */
export function resetTokenFromLink(link: string): string {
  const fragment = link.split('#')[1] ?? '';
  const params = new URLSearchParams(fragment);
  const token = params.get('resetToken');
  if (!token) {
    throw new Error('link did not carry a resetToken fragment parameter (value withheld)');
  }
  return token;
}
