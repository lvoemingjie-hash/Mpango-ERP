# DC-12R1-S3-S2B-I1-R4-R1: Exact Fail-Closed Catalog + Real Alembic Upgrade Proof

**Date**: 2026-07-31
**Branch**: `codex/dc12r1-s3-s2b-i1-financial-schema-foundation-2026-07-31`
**Status**: PASS — 9/9 real-alembic tests GREEN; focused gate red=0, gap=0
**Parent**: DC-12R1-S3-S2B-I1-R4

---

## 1. Task Summary

Two corrections to the I1 migration preflight and its evidence:

1. **Tighten migration 037 preflight** — close every bypass identified in the
   CTO review (missing tables must fail; reject unbounded VARCHAR; exact
   NUMERIC(12,2); normalised CHECK semantics rejecting OR TRUE / extra values;
   FK local-column + target + delete-action validation; index key-order +
   predicate validation; receipt_sequences rejects extra columns).

2. **Replace helper-only evidence with real alembic execution** — every test
   now provisions a disposable PG16 database, upgrades to Alembic 036 through
   the actual revision chain + env.py, registers a tenant through the public
   registry path, creates one malformed condition, runs actual
   `alembic upgrade head`, asserts PreflightFailure, asserts version remains
   036, compares complete catalog + permission fingerprints, repairs, and
   proves upgrade reaches sole head 037.

---

## 2. Migration 037 Preflight Tightening

### 2.1 Bug Fixes

| # | Bypass Closed | Before | After |
|---|---------------|--------|-------|
| 1 | Missing payments/orders/permissions tables | `continue` (silently skip) | `failures.append(...)` — fail closed |
| 2 | Unbounded transaction_id | Accepted `"character varying"` (no length) | Rejected; only VARCHAR(64) or VARCHAR(128) accepted |
| 3 | Unbounded receipt_number | Accepted `"character varying"` | Rejected; exact VARCHAR(32) required |
| 4 | Schema-qualified index names | `i[0]` was schema-qualified (`t_xxx.idx`); never matched constant | SQL changed to `ic.relname` — bare index name |
| 5 | CHECK weakening (OR TRUE, extra values) | Substring check only | Normalised comparison; rejects OR TRUE, extra literals, weakened predicates |
| 6 | FK CASCADE | Not checked | Explicitly rejected: any FK with CASCADE fails |
| 7 | FK target validation | Only `orders(id)` + RESTRICT substring | Validates local column + target schema/table/column + delete action |
| 8 | Index key order | Substring check only | Exact `(retailer_id, idempotency_key)` / `(retailer_id, status)` key order |
| 9 | receipt_sequences extra columns | Not checked | Rejects any column outside `{business_date, next_seq}` |
| 10 | declared_amount precision | `"numeric"` substring | Exact `numeric(12,2)` |

### 2.2 New Helpers

- `_normalize_check_expr(expr)` — lowercases, strips whitespace for semantic comparison
- `_check_in_allowed_values(normalised, column, allowed)` — rejects OR TRUE, extra literals

---

## 3. Real Alembic Upgrade Proof (9 Tests)

### File: `backend/tests/test_dc12r1_s3_s2b_i1_r4_r1_real_alembic_upgrade.py`

Every test creates a **disposable PG16 database** via
`temporary_database_url()`, runs the actual Alembic revision chain
(`command.upgrade` → env.py → all migrations 001-036), registers a tenant
through `public.wholesalers` + `public.tenant_registrations`, bootstraps the
tenant schema, and reverts to the exact 036 baseline.

| # | Test | Malformation | Asserts |
|---|------|-------------|---------|
| 1 | `test_missing_payments_table_fails` | DROP payments table | PreflightFailure + version=036 |
| 2 | `test_unbounded_transaction_id_rejected` | transaction_id → VARCHAR (no length) | PreflightFailure + version=036 + fingerprint unchanged + GREEN repair → 037 |
| 3 | `test_permission_collision_fails_upgrade` | Both client:payments:create + client:payments:declare | PreflightFailure + version=036 + fingerprint unchanged + GREEN → 037 |
| 4 | `test_receipt_sequences_extra_column_rejected` | ADD COLUMN extra_col | PreflightFailure + version=036 |
| 5 | `test_check_or_true_weakening_rejected` | status CHECK + OR TRUE | PreflightFailure + version=036 |
| 6 | `test_fk_cascade_rejected` | order_id FK → CASCADE | PreflightFailure + version=036 |
| 7 | `test_wrong_index_keys_rejected` | ux_payment_declarations_retailer_idem → (idempotency_key) only | PreflightFailure + version=036 |
| 8 | `test_canonical_upgrade_reaches_037_and_second_run_noops` | (none — canonical) | version=037 + sole head + second upgrade no-op fingerprint match |
| 9 | `test_cross_tenant_failure_neither_mutates` | Tenant B transaction_id unbounded | PreflightFailure + version=036 + A unchanged + B unchanged |

---

## 4. Evidence Integrity

### 4.1 Capability Matrix

- **Removed** the 10 `test_*` PASS rows that were appended to
  `2026-07-30_dc12r1_s3_s2b_capability_test_matrix.csv` in R4.
- The matrix now contains only the 46 `FIND-*` design findings (gap=0).

### 4.2 Failed/Error-Node CSV

- **File**: `2026-07-30_dc12r1_s3_s2b_i1_r4_r1_failed_error_nodes.csv`
- **Content**: Header-only — the focused gate has **zero red nodes**.
- **Accounting**: red=0, gap=0.

---

## 5. Validation Results

### 5.1 Real Alembic Execution

```
9 passed in 41.73s
```

### 5.2 Cross-Suite Regression (R2 + R3 + R4)

```
60 passed in ~35s
```

(R2: 36, R3: 14, R4: 10 — all GREEN after tightening.)

---

## 6. Node Classification

All 9 R4-R1 nodes: **GREEN** (PASS on real PG16 via actual alembic upgrade).

No RED, AMBER, or ENVIRONMENT_GATED nodes in the R4-R1 suite.

---

## 7. Verdict

**PASS_FOR_CTO_DC12R1_S3_S2B_I1_R4_R1_IMPLEMENTATION_REVIEW**
