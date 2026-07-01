/**
 * Centralized frontend permission helpers.
 *
 * U4-A: Single source of truth for RBAC checks in the UI. Replaces the ad-hoc
 * `user?.permissions.includes('X') || user?.roles.includes('admin')` pattern
 * scattered across pages with a consistent, tested helper.
 *
 * Contract:
 *   - Admin users bypass all permission checks (return true for any permission).
 *   - Non-admin users must hold the exact permission string in their list.
 *   - A null user (unauthenticated) never has any permission.
 */

import type { CurrentUserData } from '@/types/auth';

/** Admin role strings that bypass all permission checks. */
const ADMIN_ROLES = new Set(['admin', 'super_admin']);

/**
 * Return true if the user is an admin (holds an admin role).
 * Admins bypass all permission checks.
 */
export function isAdmin(user: CurrentUserData | null): boolean {
  if (!user || !user.roles) return false;
  return user.roles.some((role) => ADMIN_ROLES.has(role));
}

/**
 * Return true if the user has a specific permission.
 * Admins always return true. Unauthenticated (null) users always return false.
 *
 * @param user - the current user (or null if unauthenticated)
 * @param permission - the permission code to check (e.g. 'skus:read')
 */
export function can(user: CurrentUserData | null, permission: string): boolean {
  if (!user || !user.permissions) return false;
  if (isAdmin(user)) return true;
  return user.permissions.includes(permission);
}

/**
 * Return true if the user has ANY of the given permissions.
 * Admins always return true. Unauthenticated (null) users always return false.
 *
 * @param user - the current user (or null if unauthenticated)
 * @param permissions - permission codes to check (any-match OR semantics)
 */
export function canAny(user: CurrentUserData | null, permissions: string[]): boolean {
  if (!user) return false;
  if (isAdmin(user)) return true;
  if (!user.permissions) return false;
  return permissions.some((p) => user.permissions.includes(p));
}

// ===========================================================================
// Permission code constants
// ===========================================================================

/**
 * Product / SKU permission codes.
 * These are enforced by the backend and must match the seed scripts exactly.
 */
export const SKU_PERMISSIONS = {
  READ: 'skus:read',
  CREATE: 'skus:create',
  UPDATE: 'skus:update',
  IMPORT: 'skus:import',
} as const;

/**
 * U4 Data Intake permission codes.
 *
 * These constants define the permission vocabulary for the upcoming Data Intake
 * module. They are declared here so that frontend gate code, route guards, and
 * tests can reference them by name. The backend seeds include these codes so
 * admin users automatically have them once a tenant is bootstrapped.
 *
 * U4-E wires the first frontend staging-preview entry point for these permissions.
 * Public-link, export, and import-to-ERP flows remain out of scope.
 */
export const INTAKE_PERMISSIONS = {
  READ: 'intake:read',
  CREATE: 'intake:create',
  UPDATE: 'intake:update',
  APPROVE: 'intake:approve',
  EXPORT: 'intake:export',
  IMPORT_TO_ERP: 'intake:import_to_erp',
} as const;

/** All Data Intake permission codes as an array (useful for bulk seeding/checks). */
export const ALL_INTAKE_PERMISSIONS: readonly string[] = Object.values(INTAKE_PERMISSIONS);
