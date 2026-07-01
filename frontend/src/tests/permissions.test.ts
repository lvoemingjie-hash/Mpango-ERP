/**
 * U4-A: Permission helper tests.
 *
 * Verifies can(), canAny(), and isAdmin() behavior:
 * - Admin bypass (admin/super_admin roles return true for any permission)
 * - Non-admin with permission passes
 * - Non-admin without permission is blocked
 * - Unauthenticated (null) user is always blocked
 * - Intake permission constants are correct
 */
import { describe, it, expect } from 'vitest';
import { can, canAny, isAdmin, SKU_PERMISSIONS, INTAKE_PERMISSIONS, ALL_INTAKE_PERMISSIONS } from '@/utils/permissions';
import type { CurrentUserData } from '@/types/auth';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeUser(permissions: string[], roles: string[]): CurrentUserData {
  return {
    id: 'u1',
    email: 'test@test.com',
    full_name: 'Test User',
    tenant_id: 't1',
    tenant_schema: 't1',
    roles,
    permissions,
  };
}

// ---------------------------------------------------------------------------
// isAdmin
// ---------------------------------------------------------------------------

describe('isAdmin', () => {
  it('returns true for admin role', () => {
    expect(isAdmin(makeUser([], ['admin']))).toBe(true);
  });

  it('returns true for super_admin role', () => {
    expect(isAdmin(makeUser([], ['super_admin']))).toBe(true);
  });

  it('returns false for non-admin role', () => {
    expect(isAdmin(makeUser(['skus:read'], ['viewer']))).toBe(false);
  });

  it('returns false for null user', () => {
    expect(isAdmin(null)).toBe(false);
  });

  it('returns false for user with no roles', () => {
    expect(isAdmin(makeUser([], []))).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// can
// ---------------------------------------------------------------------------

describe('can', () => {
  it('returns true when user has the permission', () => {
    expect(can(makeUser(['skus:read'], ['viewer']), 'skus:read')).toBe(true);
  });

  it('returns false when user lacks the permission', () => {
    expect(can(makeUser(['skus:read'], ['viewer']), 'skus:create')).toBe(false);
  });

  it('admin bypass: returns true even without the permission', () => {
    expect(can(makeUser([], ['admin']), 'skus:create')).toBe(true);
  });

  it('super_admin bypass: returns true even without the permission', () => {
    expect(can(makeUser([], ['super_admin']), 'intake:approve')).toBe(true);
  });

  it('returns false for null user', () => {
    expect(can(null, 'skus:read')).toBe(false);
  });

  it('returns false for user with empty permissions', () => {
    expect(can(makeUser([], ['viewer']), 'skus:read')).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// canAny
// ---------------------------------------------------------------------------

describe('canAny', () => {
  it('returns true when user has at least one of the permissions', () => {
    expect(canAny(makeUser(['skus:update'], ['viewer']), ['skus:create', 'skus:update'])).toBe(true);
  });

  it('returns false when user has none of the permissions', () => {
    expect(canAny(makeUser(['skus:read'], ['viewer']), ['skus:create', 'skus:update'])).toBe(false);
  });

  it('admin bypass: returns true even without any matching permission', () => {
    expect(canAny(makeUser([], ['admin']), ['skus:create', 'skus:update'])).toBe(true);
  });

  it('returns false for null user', () => {
    expect(canAny(null, ['skus:read'])).toBe(false);
  });

  it('returns false for empty permissions list', () => {
    expect(canAny(makeUser(['skus:read'], ['viewer']), [])).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Permission constants
// ---------------------------------------------------------------------------

describe('Permission constants', () => {
  it('SKU_PERMISSIONS has the 4 product permission codes', () => {
    expect(SKU_PERMISSIONS.READ).toBe('skus:read');
    expect(SKU_PERMISSIONS.CREATE).toBe('skus:create');
    expect(SKU_PERMISSIONS.UPDATE).toBe('skus:update');
    expect(SKU_PERMISSIONS.IMPORT).toBe('skus:import');
  });

  it('INTAKE_PERMISSIONS has the 6 intake permission codes', () => {
    expect(INTAKE_PERMISSIONS.READ).toBe('intake:read');
    expect(INTAKE_PERMISSIONS.CREATE).toBe('intake:create');
    expect(INTAKE_PERMISSIONS.UPDATE).toBe('intake:update');
    expect(INTAKE_PERMISSIONS.APPROVE).toBe('intake:approve');
    expect(INTAKE_PERMISSIONS.EXPORT).toBe('intake:export');
    expect(INTAKE_PERMISSIONS.IMPORT_TO_ERP).toBe('intake:import_to_erp');
  });

  it('ALL_INTAKE_PERMISSIONS contains all 6 codes', () => {
    expect(ALL_INTAKE_PERMISSIONS).toHaveLength(6);
    expect(ALL_INTAKE_PERMISSIONS).toContain('intake:read');
    expect(ALL_INTAKE_PERMISSIONS).toContain('intake:create');
    expect(ALL_INTAKE_PERMISSIONS).toContain('intake:update');
    expect(ALL_INTAKE_PERMISSIONS).toContain('intake:approve');
    expect(ALL_INTAKE_PERMISSIONS).toContain('intake:export');
    expect(ALL_INTAKE_PERMISSIONS).toContain('intake:import_to_erp');
  });
});
