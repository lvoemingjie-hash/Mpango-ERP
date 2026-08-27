/**
 * Formal-API-lifecycle provisioning — B1-R1 (Kilo D closure).
 *
 * This module is NO LONGER dead code: the spec's global PRECONDITION step
 * (tests/recovery.spec.ts beforeAll) calls provisionPreconditions before
 * any browser node runs. Provisioning uses ONLY the real public HTTP
 * endpoints of the official retailer lifecycle (invitation -> register);
 * the verified retailer's setup-credential consume happens through the
 * emailed setup link by the launcher's pre-gate. There is no SQL, no ORM,
 * no debug endpoint, no hand-rolled password hashing anywhere.
 *
 * Provisioning is a PRECONDITION: its success never counts as a browser
 * node PASS and is never recorded in the reconciliation as one.
 *
 * All failures are fail-closed and name the STEP/field only.
 */

import { request as playwrightRequest, type APIRequestContext } from '@playwright/test';
import type { H2CJourneyEnv } from './env.js';
import { fieldOnly } from './assertions.js';

export interface ProvisionOutcome {
  w1VerifiedRegistered: boolean;
  w1UnverifiedRegistered: boolean;
}

export async function provisionPreconditions(
  env: H2CJourneyEnv,
): Promise<ProvisionOutcome> {
  const context = await playwrightRequest.newContext({ baseURL: env.apiBaseUrl });
  try {
    const w1VerifiedRegistered = await registerRetailer(context, {
      invitationCode: env.provisioning.w1VerifiedInvitationCode,
      phone: env.provisioning.w1VerifiedInvitationPhone,
      email: env.retailer.email,
      step: 'w1_verified_register',
    });
    const w1UnverifiedRegistered = await registerRetailer(context, {
      invitationCode: env.provisioning.w1UnverifiedInvitationCode,
      phone: env.provisioning.w1UnverifiedInvitationPhone,
      email: env.unverifiedEmail,
      step: 'w1_unverified_register',
    });
    return { w1VerifiedRegistered, w1UnverifiedRegistered };
  } finally {
    await context.dispose();
  }
}

/**
 * Register one retailer through the real public endpoint. Idempotent
 * re-registration (already-registered email) is accepted as success —
 * the invitation lifecycle guarantees identity.
 */
async function registerRetailer(
  context: APIRequestContext,
  input: {
    invitationCode: string;
    phone: string;
    email: string;
    step: string;
  },
): Promise<boolean> {
  const response = await context.post('/api/v1/retailers/register', {
    data: {
      invitation_code: input.invitationCode,
      phone: input.phone,
      email: input.email,
    },
  });
  if (response.status() === 200 || response.status() === 201) {
    return true;
  }
  // Accept "already registered" shapes (409) as precondition-satisfied;
  // anything else fails closed with step + field only.
  if (response.status() === 409) {
    return true;
  }
  throw fieldOnly('http', `precondition:${input.step}`, 'unexpected_status');
}
