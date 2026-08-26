/**
 * Fail-closed environment contract (task directive #6).
 *
 * Every successful-auth credential used by the harness is read from the
 * environment at RUN time — never at module load, so `playwright --list`
 * works env-free, and never hardcoded in the repository.
 *
 * Missing or malformed values fail the test with an error that names the
 * VARIABLE NAME only; values are never echoed into logs, reports or
 * artifacts.
 */

export interface JourneyEnv {
  /** Wholesaler frontend origin (e.g. the task loopback vite origin), no trailing slash. */
  baseUrl: string;
  /** Backend origin (e.g. the task loopback uvicorn origin), no trailing slash. */
  apiBaseUrl: string;
  /** Absolute path of the task-private maildir the launcher dumps emails into. */
  maildirRoot: string;
  /** Two-letter signup country code (SignupRequest.country). */
  signupCountry: string;
  /** A1 — single-copy journey protagonist (wholesaler owner, official lifecycle). */
  a1: {
    email: string;
    initialPassword: string;
    newPassword: string;
    replayPassword: string;
    companyName: string;
  };
  /** U — never-registered email (F4). Must differ from every provisioned identity. */
  unknownEmail: string;
  /** X — ineligible email (exists only as a soft-deleted user, provisioned via official API). */
  ineligible: {
    email: string;
    /** Transient password for the pre-deletion create; never used to authenticate. */
    tempPassword: string;
  };
  /** M1 — shared identity across W1/W2 (official API provisioning precondition). */
  m1: {
    w1: { ownerEmail: string; ownerPassword: string; companyName: string };
    w2: { ownerEmail: string; ownerPassword: string; companyName: string };
    m: { email: string; fullName: string; initialPassword: string; newPassword: string };
  };
}

const COMMON_VARS = [
  'J1H2B_BASE_URL',
  'J1H2B_API_BASE_URL',
  'J1H2B_MAILDIR_ROOT',
  'J1H2B_SIGNUP_COUNTRY',
] as const;

const A1_VARS = [
  'J1H2B_A1_EMAIL',
  'J1H2B_A1_INITIAL_PASSWORD',
  'J1H2B_A1_NEW_PASSWORD',
  'J1H2B_A1_REPLAY_PASSWORD',
  'J1H2B_A1_COMPANY_NAME',
] as const;

const UNKNOWN_VARS = ['J1H2B_UNKNOWN_EMAIL'] as const;

const INELIGIBLE_VARS = [
  'J1H2B_INELIGIBLE_EMAIL',
  'J1H2B_INELIGIBLE_TEMP_PASSWORD',
] as const;

const M1_VARS = [
  'J1H2B_W1_OWNER_EMAIL',
  'J1H2B_W1_OWNER_PASSWORD',
  'J1H2B_W1_COMPANY_NAME',
  'J1H2B_W2_OWNER_EMAIL',
  'J1H2B_W2_OWNER_PASSWORD',
  'J1H2B_W2_COMPANY_NAME',
  'J1H2B_M_EMAIL',
  'J1H2B_M_FULL_NAME',
  'J1H2B_M_INITIAL_PASSWORD',
  'J1H2B_M_NEW_PASSWORD',
] as const;

export type EnvGroup = 'common' | 'a1' | 'unknown' | 'ineligible' | 'm1';

const GROUP_VARS: Record<EnvGroup, readonly string[]> = {
  common: COMMON_VARS,
  a1: [...COMMON_VARS, ...A1_VARS],
  unknown: [...COMMON_VARS, ...UNKNOWN_VARS],
  ineligible: [...COMMON_VARS, ...INELIGIBLE_VARS],
  m1: [...COMMON_VARS, ...M1_VARS],
};

function readVar(name: string): string | undefined {
  const raw = process.env[name];
  if (raw === undefined) return undefined;
  const trimmed = raw.trim();
  return trimmed.length > 0 ? trimmed : undefined;
}

/** Require a single env var; the error names the variable, never a value. */
export function requireEnvVar(name: string): string {
  const value = readVar(name);
  if (value === undefined) {
    throw new Error(`fail-closed: environment variable ${name} is missing or empty`);
  }
  return value;
}

function requireAll(names: readonly string[]): Record<string, string> {
  const missing: string[] = [];
  const values: Record<string, string> = {};
  for (const name of names) {
    const value = readVar(name);
    if (value === undefined) {
      missing.push(name);
    } else {
      values[name] = value;
    }
  }
  if (missing.length > 0) {
    throw new Error(
      `fail-closed: missing environment variables: ${missing.join(', ')} (values are never echoed)`,
    );
  }
  return values;
}

function normalizeOrigin(raw: string, varName: string): string {
  let parsed: URL;
  try {
    parsed = new URL(raw);
  } catch {
    throw new Error(`fail-closed: ${varName} is not a parseable absolute http(s) URL`);
  }
  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    throw new Error(`fail-closed: ${varName} must use http or https`);
  }
  return parsed.origin;
}

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function requireEmail(raw: string, varName: string): string {
  const email = raw.trim().toLowerCase();
  if (!EMAIL_PATTERN.test(email)) {
    throw new Error(`fail-closed: ${varName} is not a syntactically valid email`);
  }
  return email;
}

function requirePassword(raw: string, varName: string): string {
  if (raw.length < 8) {
    throw new Error(`fail-closed: ${varName} must be at least 8 characters (length withheld)`);
  }
  return raw;
}

function assertDistinct(
  pairs: Array<[string, string, string]>,
): void {
  for (const [left, right, label] of pairs) {
    if (left === right) {
      throw new Error(`fail-closed: ${label} must be two different values`);
    }
  }
}

/**
 * Load and validate the environment for the requested groups.
 * Call from beforeAll/test bodies only — never at module top level.
 */
export function loadJourneyEnv(
  ...groups: EnvGroup[]
): JourneyEnv {
  const merged = new Set<EnvGroup>(['common', ...groups]);
  const names = [...merged].flatMap((group) => GROUP_VARS[group]);
  const v = requireAll(names);

  const signupCountry = v.J1H2B_SIGNUP_COUNTRY.trim().toUpperCase();
  if (!/^[A-Z]{2}$/.test(signupCountry)) {
    throw new Error('fail-closed: J1H2B_SIGNUP_COUNTRY must be a 2-letter country code');
  }

  const a1 = {
    email: requireEmail(v.J1H2B_A1_EMAIL, 'J1H2B_A1_EMAIL'),
    initialPassword: requirePassword(v.J1H2B_A1_INITIAL_PASSWORD, 'J1H2B_A1_INITIAL_PASSWORD'),
    newPassword: requirePassword(v.J1H2B_A1_NEW_PASSWORD, 'J1H2B_A1_NEW_PASSWORD'),
    replayPassword: requirePassword(v.J1H2B_A1_REPLAY_PASSWORD, 'J1H2B_A1_REPLAY_PASSWORD'),
    companyName: v.J1H2B_A1_COMPANY_NAME,
  };

  const unknownEmail = merged.has('unknown')
    ? requireEmail(v.J1H2B_UNKNOWN_EMAIL, 'J1H2B_UNKNOWN_EMAIL')
    : '';

  const ineligible = merged.has('ineligible')
    ? {
        email: requireEmail(v.J1H2B_INELIGIBLE_EMAIL, 'J1H2B_INELIGIBLE_EMAIL'),
        tempPassword: requirePassword(v.J1H2B_INELIGIBLE_TEMP_PASSWORD, 'J1H2B_INELIGIBLE_TEMP_PASSWORD'),
      }
    : { email: '', tempPassword: '' };

  const m1 = merged.has('m1')
    ? {
        w1: {
          ownerEmail: requireEmail(v.J1H2B_W1_OWNER_EMAIL, 'J1H2B_W1_OWNER_EMAIL'),
          ownerPassword: requirePassword(v.J1H2B_W1_OWNER_PASSWORD, 'J1H2B_W1_OWNER_PASSWORD'),
          companyName: v.J1H2B_W1_COMPANY_NAME,
        },
        w2: {
          ownerEmail: requireEmail(v.J1H2B_W2_OWNER_EMAIL, 'J1H2B_W2_OWNER_EMAIL'),
          ownerPassword: requirePassword(v.J1H2B_W2_OWNER_PASSWORD, 'J1H2B_W2_OWNER_PASSWORD'),
          companyName: v.J1H2B_W2_COMPANY_NAME,
        },
        m: {
          email: requireEmail(v.J1H2B_M_EMAIL, 'J1H2B_M_EMAIL'),
          fullName: v.J1H2B_M_FULL_NAME,
          initialPassword: requirePassword(v.J1H2B_M_INITIAL_PASSWORD, 'J1H2B_M_INITIAL_PASSWORD'),
          newPassword: requirePassword(v.J1H2B_M_NEW_PASSWORD, 'J1H2B_M_NEW_PASSWORD'),
        },
      }
    : {
        w1: { ownerEmail: '', ownerPassword: '', companyName: '' },
        w2: { ownerEmail: '', ownerPassword: '', companyName: '' },
        m: { email: '', fullName: '', initialPassword: '', newPassword: '' },
      };

  // Distinctness rules — each violation fails closed with a names-only error.
  const distinctness: Array<[string, string, string]> = [
    [a1.initialPassword, a1.newPassword, 'J1H2B_A1_INITIAL_PASSWORD vs J1H2B_A1_NEW_PASSWORD'],
    [a1.newPassword, a1.replayPassword, 'J1H2B_A1_NEW_PASSWORD vs J1H2B_A1_REPLAY_PASSWORD'],
  ];
  if (merged.has('m1')) {
    distinctness.push(
      [m1.w1.ownerEmail, m1.w2.ownerEmail, 'J1H2B_W1_OWNER_EMAIL vs J1H2B_W2_OWNER_EMAIL'],
      [m1.m.initialPassword, m1.m.newPassword, 'J1H2B_M_INITIAL_PASSWORD vs J1H2B_M_NEW_PASSWORD'],
      [m1.m.email, m1.w1.ownerEmail, 'J1H2B_M_EMAIL vs J1H2B_W1_OWNER_EMAIL'],
      [m1.m.email, m1.w2.ownerEmail, 'J1H2B_M_EMAIL vs J1H2B_W2_OWNER_EMAIL'],
    );
  }
  assertDistinct(distinctness);

  const provisionedEmails = [a1.email, m1.w1.ownerEmail, m1.w2.ownerEmail, m1.m.email, ineligible.email];
  if (unknownEmail !== '' && provisionedEmails.includes(unknownEmail)) {
    throw new Error(
      'fail-closed: J1H2B_UNKNOWN_EMAIL must differ from every provisioned identity email',
    );
  }

  return {
    baseUrl: normalizeOrigin(v.J1H2B_BASE_URL, 'J1H2B_BASE_URL'),
    apiBaseUrl: normalizeOrigin(v.J1H2B_API_BASE_URL, 'J1H2B_API_BASE_URL'),
    maildirRoot: v.J1H2B_MAILDIR_ROOT,
    signupCountry,
    a1,
    unknownEmail,
    ineligible,
    m1,
  };
}
