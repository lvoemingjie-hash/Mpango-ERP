/**
 * Fail-closed environment contract (J1H2C_* variables only) — B1-R1.
 *
 * Every credential used by the harness is read from the environment at RUN
 * time — never at module load, so `playwright --list` works env-free, and
 * never hardcoded in the repository. Missing or malformed values fail the
 * test with an error naming the VARIABLE NAME only; values are never
 * echoed into logs, reports or artifacts.
 *
 * B1-R1 (Kilo C): a SECOND genuine supplier (W2) is a required identity.
 * W1 is the target retailer's supplier; W2 is a formally provisioned,
 * valid, but WRONG supplier for the HC09 state — never a fabricated code.
 *
 * B1-R1 (Kilo D): the provisioning launcher contract variables are
 * declared here and consumed by the global PRECONDITION setup (see
 * tests/recovery.spec.ts beforeAll -> provisionPreconditions). They are
 * PRECONDITION inputs; provisioning success never counts as a browser
 * node PASS.
 */

export interface ProvisioningEnv {
  /** Invitation code + phone for the W1 verified retailer (official lifecycle). */
  w1VerifiedInvitationCode: string;
  w1VerifiedInvitationPhone: string;
  /** Invitation code + phone for the W1 UNVERIFIED retailer (setup never consumed). */
  w1UnverifiedInvitationCode: string;
  w1UnverifiedInvitationPhone: string;
}

export interface H2CJourneyEnv {
  /** Retailer frontend origin (task loopback), no trailing slash. */
  baseUrl: string;
  /** Backend origin (task loopback), no trailing slash. */
  apiBaseUrl: string;
  /** Absolute path of the task-private maildir the launcher dumps emails into. */
  maildirRoot: string;
  /** W1: the target retailer's supplier CANONICAL (DB, uppercase) code. */
  w1CanonicalCode: string;
  /** W2: a formally provisioned SECOND valid supplier's canonical code (Kilo C). */
  w2CanonicalCode: string;
  /** HC07 protagonist: established (verified + password) W1 retailer identity. */
  retailer: {
    email: string;
    /** Current password; used only for read-only post-proofs, never echoed. */
    currentPassword: string;
    /** New password the reset journey sets (HC12/HC13/HC14). */
    newPassword: string;
  };
  /** HC08 — never-registered email. Must differ from every provisioned identity. */
  unknownEmail: string;
  /** HC10 — registered but UNVERIFIED W1 retailer email (setup never consumed). */
  unverifiedEmail: string;
  /** HC15 + scanner: unique per-run forged reset token (launcher-provided). */
  forgedResetToken: string;
  /**
   * Official-lifecycle provisioning inputs (Kilo D). The invitations are
   * created by the wholesaler through the official API by the launcher's
   * pre-gate; the harness's PRECONDITION step consumes them through the
   * PUBLIC retailer lifecycle endpoints only.
   */
  provisioning: ProvisioningEnv;
}

function required(name: string): string {
  const value = process.env[name];
  if (!value || !value.trim()) {
    throw new Error(
      `J1H2C environment variable missing or empty: ${name} (fail-closed; values are never echoed)`,
    );
  }
  return value.trim();
}

export function loadJourneyEnv(): H2CJourneyEnv {
  return {
    baseUrl: required('J1H2C_BASE_URL'),
    apiBaseUrl: required('J1H2C_API_BASE_URL'),
    maildirRoot: required('J1H2C_MAILDIR_ROOT'),
    w1CanonicalCode: required('J1H2C_W1_CANONICAL_CODE'),
    w2CanonicalCode: required('J1H2C_W2_CANONICAL_CODE'),
    retailer: {
      email: required('J1H2C_RETAILER_EMAIL'),
      currentPassword: required('J1H2C_RETAILER_CURRENT_PASSWORD'),
      newPassword: required('J1H2C_RETAILER_NEW_PASSWORD'),
    },
    unknownEmail: required('J1H2C_UNKNOWN_EMAIL'),
    unverifiedEmail: required('J1H2C_UNVERIFIED_EMAIL'),
    forgedResetToken: required('J1H2C_FORGED_RESET_TOKEN'),
    provisioning: {
      w1VerifiedInvitationCode: required('J1H2C_W1_VERIFIED_INVITATION_CODE'),
      w1VerifiedInvitationPhone: required('J1H2C_W1_VERIFIED_INVITATION_PHONE'),
      w1UnverifiedInvitationCode: required('J1H2C_W1_UNVERIFIED_INVITATION_CODE'),
      w1UnverifiedInvitationPhone: required('J1H2C_W1_UNVERIFIED_INVITATION_PHONE'),
    },
  };
}
