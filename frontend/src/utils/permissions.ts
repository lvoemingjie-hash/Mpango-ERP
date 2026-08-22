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

/**
 * Retailer (client) permission codes — DC-12R1-MVP-R0-R1 (WPR-002).
 *
 * Canonical constants for the six ``client:*`` permissions granted to the
 * ``retailer_operator`` role by the backend seed (migration
 * ``036_retailer_mvp_identity``) with the ``client:payments:create`` →
 * ``client:payments:declare`` rename applied by migration
 * ``037_payment_declarations_schema``. These MUST match the backend
 * ``RequirePermission(...)`` strings byte-for-byte; they are the single
 * source of truth referenced by route guards and tests so no independent
 * permission algorithm or string drift can arise.
 *
 * Route admission (WPR-002) reuses the existing ``can()`` helper:
 *   - order print          -> CLIENT_PERMISSIONS.ORDERS_READ
 *   - declaration print    -> CLIENT_PERMISSIONS.PAYMENTS_READ
 *   - receipt (Contract C) -> CLIENT_PERMISSIONS.PAYMENTS_READ
 *   - statement (Contract D) -> CLIENT_PERMISSIONS.FINANCE_READ
 *   - declaration submit   -> CLIENT_PERMISSIONS.PAYMENTS_DECLARE (WPR-003)
 */
export const CLIENT_PERMISSIONS = {
  CATALOG_READ: 'client:catalog:read',
  ORDERS_READ: 'client:orders:read',
  ORDERS_CREATE: 'client:orders:create',
  PAYMENTS_READ: 'client:payments:read',
  PAYMENTS_DECLARE: 'client:payments:declare',
  FINANCE_READ: 'client:finance:read',
} as const;

/** All six retailer (client) permission codes as an array. */
export const ALL_CLIENT_PERMISSIONS: readonly string[] = Object.values(CLIENT_PERMISSIONS);

/**
 * Wholesaler invitation permission codes — DC-12R1-MVP-L1-J1-H2-A.
 *
 * Must match the backend RequirePermission(...) strings byte-for-byte
 * (api/v1/invitations.py + core/permission_registry.py). The authoring UI
 * (Customers "Invite Retailer" CTA and /retailers/invite) is admitted only
 * with invitations:create; revoke stays a backend/permission concern.
 */
export const INVITATION_PERMISSIONS = {
  CREATE: 'invitations:create',
  REVOKE: 'invitations:revoke',
} as const;

/**
 * Wholesaler retailer-relationship permission codes — DC-12R1-MVP-L1-J1-H2-A-R1.
 * Must match the backend RequirePermission(...) string byte-for-byte
 * (api/v1/retailers.py + core/permission_registry.py). Gates the Customers
 * page deactivate control for dual-entry relationships.
 */
export const RETAILER_PERMISSIONS = {
  DEACTIVATE: 'retailers:deactivate',
} as const;
