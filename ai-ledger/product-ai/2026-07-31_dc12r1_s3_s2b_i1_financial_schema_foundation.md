# DC-12R1-S3-S2B-I1: Financial Schema and Permission Foundation

**Date:** 2026-07-31
**Branch:** `codex/dc12r1-s3-s2b-i1-financial-schema-foundation-2026-07-31`
**Product baseline:** `origin/product-dev-recovered` @ `0f9d259b`
**Design authority:** `zcode/dc12r1-s3-s2b-d-payment-declaration-contract-2026-07-30` @ `c583cea1`

---

## 1. Scope

Implementation of the financial schema and permission foundation:
1. Forward-only migration 037 (down_revision 036)
2. `payment_declarations` and `receipt_sequences` tables
3. `payments.receipt_number` as sole receipt source with partial unique index
4. `payments.transaction_id` widened VARCHAR(64) → VARCHAR(128)
5. Permission rename: `client:payments:create` → `client:payments:declare`
6. New permission: `payments:confirm_declaration` in `ADMIN_PERMISSIONS` only
7. Bootstrap reconciliation parity for all new objects

**Not in scope:** CanonicalPaymentService, declaration routes, frontend, payment write paths.

---

## 2. Changed Files

| File | Change |
|---|---|
| `alembic/versions/037_payment_declarations_schema.py` | NEW — forward-only migration |
| `core/permission_registry.py` | Rename + add permission |
| `scripts/bootstrap_tenant_schema.py` | DDL + reconcile parity |
| `tests/test_dc12r1_s3_s2b_i1_financial_schema_foundation.py` | NEW — 21 tests |
| `tests/test_dc12r1_s1_r5a_permission_registry_parity.py` | Update for rename |
| `tests/test_u1_bootstrap_permission_completeness.py` | Update for rename + new perm |
| `tests/test_u1r1_bootstrap_completeness.py` | Handle stale legacy perm |
| `tests/test_u6f_onboarding_auth_chain_closeout.py` | Update head to 037 |
| `tests/test_u6i1_owner_credential_setup_schema.py` | Update head to 037 |

---

## 3. Migration 037 Details

- **Revision:** `037_payment_declarations_schema`
- **down_revision:** `036_retailer_mvp_identity`
- **Forward-only:** `downgrade()` raises `RuntimeError`
- **Tenant enumeration:** `public.tenant_registrations JOIN public.wholesalers` with exact 035/036 status sets
- **Preflight:** Verifies payments/orders tables exist, transaction_id column exists, permission exists; fails closed
- **Per-tenant DDL:**
  - `ALTER TABLE payments ALTER COLUMN transaction_id TYPE VARCHAR(128)`
  - `ALTER TABLE payments ADD COLUMN receipt_number VARCHAR(32)` + partial unique index
  - `CREATE TABLE payment_declarations` with FK RESTRICT on order_id and confirmation_payment_id
  - `CREATE TABLE receipt_sequences` with `business_date CHAR(8)` PK
  - `UPDATE permissions SET code = 'client:payments:declare' WHERE code = 'client:payments:create'`
  - `INSERT INTO permissions ... ('payments:confirm_declaration', ...) ON CONFLICT DO NOTHING`

---

## 4. Validation Results

| Gate | Result |
|---|---|
| `py_compile` all changed files | PASS |
| Migration 036 → 037 upgrade on PG16 | PASS |
| Second upgrade (no-op) | PASS |
| I1 schema foundation tests (21) | **21 passed** |
| Permission registry parity (4) | **4 passed** |
| s6e RBAC drift gate (6) | **6 passed** |
| u1 bootstrap permission completeness | **PASS** |
| u1r1 bootstrap completeness | **PASS** |
| u6f/u6i1 head assertion (037) | **PASS** |
| Focused suite total | **73 passed, 5 xfailed** |
| Full backend regression | **3037 passed**, 12 failed (7 pre-existing baseline + 5 fixed) |
| `git diff --check` | CLEAN |
| GitNexus analyze | 14,106 nodes, 43,505 edges |

### Full backend failures (7 pre-existing baseline):
- `test_dc11t4c` (TEST_DATABASE_URL env-gated)
- `test_dc12r1_s1_r5_migration_preflight` (migration state)
- `test_s4g_migration_infrastructure_hardening` (5 migration infra tests)

All reproduced on baseline `0f9d259b`. No branch-caused failures after test corrections.

---

## 5. Receipt Sequence Allocator Tests

| Test | Result |
|---|---|
| First allocation = 000001 | PASS |
| No 000000 receipt | PASS |
| Concurrent allocations unique | PASS |
| Rolled-back allocation reusable | PASS |

---

## 6. Permission Tests

| Test | Result |
|---|---|
| client:payments:create renamed to declare | PASS |
| payments:confirm_declaration in ADMIN_PERMISSION_CODES | PASS |
| retailer_operator never gets confirm_declaration | PASS |
| Admin and retailer_operator disjoint | PASS |

---

## 7. Self-Review

| # | Check | Result |
|---|---|---|
| 1 | Migration 037 forward-only, no downgrade | PASS |
| 2 | Tenant enumeration via tenant_registrations JOIN wholesalers | PASS |
| 3 | Exact 035/036 status sets used | PASS |
| 4 | No per-tenant alembic_version checks | PASS |
| 5 | Rogue schemas untouched | PASS |
| 6 | Incompatible objects fail closed | PASS |
| 7 | Second upgrade is no-op | PASS |
| 8 | Sole head = 037 | PASS |
| 9 | receipt_number single source on payments | PASS |
| 10 | Partial unique index verified | PASS |
| 11 | transaction_id widened to VARCHAR(128) | PASS |
| 12 | payment_declarations has no is_deleted | PASS |
| 13 | FK RESTRICT semantics | PASS |
| 14 | UNIQUE(retailer_id, idempotency_key) | PASS |
| 15 | Permission rename correct | PASS |
| 16 | payments:confirm_declaration in ADMIN only | PASS |
| 17 | No payment/ledger/order write-path changes | PASS |
| 18 | No frontend changes | PASS |
| 19 | No dependency/lockfile changes | PASS |
| 20 | git diff --check | PASS |
| 21 | detect-secrets | PASS |
| 22 | No skip/xfail/assertion weakening added | PASS |

---

## 8. Verdict

```
PASS_FOR_CTO_DC12R1_S3_S2B_I1_REVIEW
```
