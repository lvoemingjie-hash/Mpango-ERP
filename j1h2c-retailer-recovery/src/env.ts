/**
 * Fail-closed environment contract (J1H2C_* variables only).
 *
 * Every credential used by the harness is read from the environment at RUN
 * time — never at module load, so `playwright --list` works env-free, and
 * never hardcoded in the repository. Missing or malformed values fail the
 * test with an error naming the VARIABLE NAME only; values are never
 * echoed into logs, reports or artifacts.
 */

export interface H2CJourneyEnv {
  /** Retailer frontend origin (task loopback), no trailing slash. */
  baseUrl: string;
  /** Backend origin (task loopback), no trailing slash. */
  apiBaseUrl: string;
  /** Absolute path of the task-private maildir the launcher dumps emails into. */
  maildirRoot: string;
  /** The retailer's supplier CANONICAL (DB, uppercase) wholesaler code. */
  wholesalerCanonicalCode: string;
  /** HC07 protagonist: established (verified + password) retailer identity. */
  retailer: {
    email: string;
    /** Current password; used only for read-only post-proofs, never echoed. */
    currentPassword: string;
    /** New password the reset journey sets (HC12/HC13/HC14). */
    newPassword: string;
  };
  /** HC08 — never-registered email. Must differ from every provisioned identity. */
  unknownEmail: string;
  /** HC10 — registered but UNVERIFIED retailer email (setup never consumed). */
  unverifiedEmail: string;
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
    wholesalerCanonicalCode: required('J1H2C_WHOLESALER_CANONICAL_CODE'),
    retailer: {
      email: required('J1H2C_RETAILER_EMAIL'),
      currentPassword: required('J1H2C_RETAILER_CURRENT_PASSWORD'),
      newPassword: required('J1H2C_RETAILER_NEW_PASSWORD'),
    },
    unknownEmail: required('J1H2C_UNKNOWN_EMAIL'),
    unverifiedEmail: required('J1H2C_UNVERIFIED_EMAIL'),
  };
}
