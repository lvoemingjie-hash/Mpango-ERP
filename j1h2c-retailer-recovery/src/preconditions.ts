/**
 * Formal provisioning preconditions — B1-R2 (Kilo D closure).
 *
 * STRICT STATUS CONTRACT (Kilo D #1/#2):
 *   register accepts ONLY the contract 2xx statuses (200/201). ANY 409,
 *   any other 4xx, any 5xx, and any transport failure FAIL CLOSED with a
 *   step+field-only error. The "any 409 = success" logic is removed.
 *   An authoritative fresh runtime uses FRESH, UNCONSUMED invitations —
 *   a 409 (conflict) is never an acceptable precondition.
 *
 * FULL OFFICIAL LIFECYCLE (Kilo D #3/#4/#5): for the established W1
 * retailer the harness performs register -> read the SETUP email from the
 * task maildir (memory only) -> consume setup-credential -> login proof.
 * Tokens are read ONLY from the task-private maildir into memory; there
 * is no SQL, no ORM, no debug endpoint, no hand-rolled hashing anywhere.
 *
 * UNVERIFIED RETAILER (Kilo D #5): formal register then an explicit STOP
 * before verification/setup; a login proof MUST fail (not established).
 *
 * W2 (Kilo D #6): provisioned by the formal wholesaler lifecycle through
 * the LAUNCHER CONTRACT (below); the harness proves at precondition time
 * that the W2 canonical code is valid-shaped and different from W1, and
 * that the target retailer is NOT bound to W2 (login proof with the W2
 * portal code must fail).
 *
 * UNKNOWN EMAIL (Kilo D #7): normalized (trim+lowercase) different from
 * every provisioned identity.
 *
 * All precondition proofs run BEFORE any browser node and NEVER count as
 * a browser PASS (Kilo D #8).
 *
 * LAUNCHER CONTRACT (Kilo D #9, executable + machine-verifiable):
 *   The launcher (external pre-gate) must provide, via J1H2C_* env:
 *   - W1/W2 wholesaler creation through the official wholesaler lifecycle
 *     with canonical codes (J1H2C_W1/W2_CANONICAL_CODE);
 *   - fresh, unconsumed invitations:
 *     J1H2C_W1_VERIFIED_INVITATION_{CODE,PHONE},
 *     J1H2C_W1_UNVERIFIED_INVITATION_{CODE,PHONE};
 *   - J1H2C_FORGED_RESET_TOKEN: a unique per-run value for HC15 + the
 *     scanner (missing/short/equal-to-any-mail-token fails closed);
 *   - the task maildir (J1H2C_MAILDIR_ROOT) receiving every credential
 *     email for the exact provisioned addresses.
 *   This contract is enforced EXECUTABLY by runPreconditions() below and
 *   statically by tools/validate-static.mjs step [11]; the README prose
 *   alone is never the contract.
 */

import { request as playwrightRequest, type APIRequestContext } from '@playwright/test';
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import type { H2CJourneyEnv } from './env.js';
import { fieldOnly } from './assertions.js';
import { snapshotDeliveries, pollForExactlyOneNewDelivery } from './maildir.js';

const REGISTER_URL = '/api/v1/retailers/register';
const SETUP_CONSUME_URL = '/api/v1/retailers/setup-credential';
const LOGIN_URL = '/api/v1/client/auth/login';

export interface PreconditionProofs {
  establishedLifecycleComplete: boolean;
  unverifiedStoppedBeforeVerification: boolean;
  w2DiffersFromW1: boolean;
  retailerNotBoundToW2: boolean;
  unknownEmailDistinct: boolean;
  maildirSnapshotPersisted: boolean;
}

function normalizeEmail(email: string): string {
  return email.trim().toLowerCase();
}

async function strictRegister(
  context: APIRequestContext,
  input: { invitationCode: string; phone: string; email: string; step: string },
): Promise<void> {
  const response = await context.post(REGISTER_URL, {
    data: {
      invitation_code: input.invitationCode,
      phone: input.phone,
      email: input.email,
    },
  });
  const status = response.status();
  // Kilo D #1/#2: ONLY 200/201 pass; any 409/4xx/5xx fails closed.
  if (status !== 200 && status !== 201) {
    throw fieldOnly('http', `precondition:${input.step}`, `strict_register_rejected:${status}`);
  }
}

async function loginProofSucceeds(
  context: APIRequestContext,
  input: { email: string; password: string; wholesalerCode: string; step: string },
): Promise<void> {
  const response = await context.post(LOGIN_URL, {
    data: {
      email: input.email,
      password: input.password,
      wholesaler_code: input.wholesalerCode,
    },
  });
  if (response.status() !== 200) {
    throw fieldOnly('http', `precondition:${input.step}`, `login_proof_failed:${response.status()}`);
  }
}

async function loginProofMustFail(
  context: APIRequestContext,
  input: { email: string; password: string; wholesalerCode: string; step: string },
): Promise<void> {
  const response = await context.post(LOGIN_URL, {
    data: {
      email: input.email,
      password: input.password,
      wholesaler_code: input.wholesalerCode,
    },
  });
  if (response.status() === 200) {
    throw fieldOnly('http', `precondition:${input.step}`, 'login_unexpectedly_succeeded');
  }
}

async function readSetupTokenFromMaildir(
  env: H2CJourneyEnv,
  snapshot: Set<string>,
): Promise<string> {
  const fresh = await pollForExactlyOneNewDelivery(
    env.maildirRoot,
    env.retailer.email,
    snapshot,
    { timeoutMs: 30_000 },
  );
  // Setup emails carry the same fragment contract; extract setupToken.
  const hashIndex = fresh.link.indexOf('#');
  if (hashIndex < 0) {
    throw fieldOnly('mail', 'setup_link', 'missing_fragment');
  }
  const fragment = new URLSearchParams(fresh.link.slice(hashIndex + 1));
  const setupToken = fragment.get('setupToken');
  if (!setupToken) {
    throw fieldOnly('mail', 'setup_link.fragment', 'missing_setupToken');
  }
  return setupToken; // memory only
}

/**
 * The executable precondition gate. Runs in the spec beforeAll BEFORE any
 * browser node; never recorded as a browser PASS. Also persists the
 * run-start maildir snapshot (filenames only, no values) so the scanner
 * can scope itself to THIS run's deliveries.
 */
export async function runPreconditions(env: H2CJourneyEnv): Promise<PreconditionProofs> {
  // Static identity proofs first (fail-closed, value-free errors).
  const w1 = env.w1CanonicalCode;
  const w2 = env.w2CanonicalCode;
  if (w1 === w2) {
    throw fieldOnly('precondition', 'w2_canonical_code', 'must_differ_from_w1');
  }
  if (!/^[A-Z0-9]+$/.test(w2)) {
    throw fieldOnly('precondition', 'w2_canonical_code', 'code_class_violation');
  }
  const provisioned = [
    normalizeEmail(env.retailer.email),
    normalizeEmail(env.unverifiedEmail),
  ];
  if (provisioned.includes(normalizeEmail(env.unknownEmail))) {
    throw fieldOnly('precondition', 'unknown_email', 'collides_with_provisioned_identity');
  }
  const forged = process.env.J1H2C_FORGED_RESET_TOKEN ?? '';
  if (forged.trim().length < 8) {
    throw fieldOnly('precondition', 'forged_reset_token', 'missing_or_too_short');
  }

  // Persist the run-start maildir snapshot (filenames only) for scanner
  // scoping — no secret values ever hit disk here.
  const mailSnapshot = await snapshotDeliveries(env.maildirRoot, env.retailer.email);
  mkdirSync('artifacts', { recursive: true });
  writeFileSync(
    join('artifacts', 'maildir-snapshot.json'),
    `${JSON.stringify({
      schema: 'j1h2c-maildir-snapshot/1',
      emailKey: normalizeEmail(env.retailer.email),
      files: [...mailSnapshot].sort(),
      note: 'filenames only; no secret values',
    })}\n`,
    'utf8',
  );

  const context = await playwrightRequest.newContext({ baseURL: env.apiBaseUrl });
  try {
    // W1 verified retailer: FULL official lifecycle (Kilo D #3).
    await strictRegister(context, {
      invitationCode: env.provisioning.w1VerifiedInvitationCode,
      phone: env.provisioning.w1VerifiedInvitationPhone,
      email: env.retailer.email,
      step: 'w1_verified_register',
    });
    const setupToken = await readSetupTokenFromMaildir(env, mailSnapshot);
    const consume = await context.post(SETUP_CONSUME_URL, {
      data: { setup_token: setupToken, new_password: env.retailer.currentPassword },
    });
    if (consume.status() !== 200 && consume.status() !== 201) {
      throw fieldOnly('http', 'precondition:w1_setup_consume', `rejected:${consume.status()}`);
    }
    await loginProofSucceeds(context, {
      email: env.retailer.email,
      password: env.retailer.currentPassword,
      wholesalerCode: w1,
      step: 'w1_established_login_proof',
    });

    // W1 unverified retailer: register then STOP before verification
    // (Kilo D #5); prove it is NOT an established verified identity.
    await strictRegister(context, {
      invitationCode: env.provisioning.w1UnverifiedInvitationCode,
      phone: env.provisioning.w1UnverifiedInvitationPhone,
      email: env.unverifiedEmail,
      step: 'w1_unverified_register',
    });
    await loginProofMustFail(context, {
      email: env.unverifiedEmail,
      password: env.retailer.currentPassword,
      wholesalerCode: w1,
      step: 'w1_unverified_not_established_proof',
    });

    // Kilo D #6: the target retailer must NOT be bound to W2.
    await loginProofMustFail(context, {
      email: env.retailer.email,
      password: env.retailer.currentPassword,
      wholesalerCode: w2,
      step: 'retailer_not_bound_to_w2_proof',
    });

    return {
      establishedLifecycleComplete: true,
      unverifiedStoppedBeforeVerification: true,
      w2DiffersFromW1: true,
      retailerNotBoundToW2: true,
      unknownEmailDistinct: true,
      maildirSnapshotPersisted: true,
    };
  } finally {
    await context.dispose();
  }
}
