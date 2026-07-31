# DC-12R1-S3-S2B-I1-R4: Real Preflight Execution + Evidence Integrity

**Date**: 2026-07-31
**Status**: PASS — All 10 R4 tests GREEN; 60 total across R2/R3/R4 all GREEN
**Parent**: DC-12R1-S3-S2B-I1-R3 (Exact Migration Preflight and Zero-Red Gate)

---

## 1. Task Summary

Replace mock malformed-object tests from R3 with **real preflight execution** tests that:

1. Create a **deliberately malformed PG16 catalog** (wrong CHECK, FK CASCADE, VARCHAR length, nullability, extra columns, missing indexes, wrong types, permission collision)
2. Execute the **actual migration-037 preflight functions** (`_verify_declaration_catalog_pg`, `_verify_receipt_sequences_pg`, `_preflight_semantic`)
3. Assert exact **PreflightFailure** detection
4. Prove **no catalog mutation** via before/after fingerprint comparison
5. **GREEN** — fix the malformation and prove preflight passes clean

---

## 2. Files Changed

### 2.1 Test File: `backend/tests/test_dc12r1_s3_s2b_i1_r4_preflight_execution.py`

**Created**. Contains:

| Class | Tests | Description |
|-------|-------|-------------|
| `TestRealPreflightExecution` | 9 | RED-before/GREEN-after for each malformation type |
| `TestTwoRegisteredTenants` | 1 | Cross-tenant failure isolation + fingerprint preservation |

**RED → GREEN pattern** (every test):
```python
# RED: malform catalog
ALTER TABLE ... ADD CONSTRAINT wrong_ck ...

# Before fingerprint
fp_before = _fingerprint(schema)

# Execute real preflight → must fail
failures = []
m037._verify_declaration_catalog_pg(conn, schema, failures)
assert failures  # detected

# After fingerprint = before → no catalog mutation
fp_after = _fingerprint(schema)
assert fp_before == fp_after

# GREEN: fix malformation → preflight passes clean
ALTER TABLE ... DROP CONSTRAINT wrong_ck ...
ALTER TABLE ... ADD CONSTRAINT correct_ck ...
m037._verify_declaration_catalog_pg(conn, schema, [])  # no raise
```

### 2.2 Migration Fix: `backend/alembic/versions/037_payment_declarations_schema.py`

Three bugs found and fixed during R4:

| # | Bug | Location | Fix |
|---|-----|----------|-----|
| 1 | `_pg_catalog_indexes` returned `(r[0], r[1], r[2])` — column 2 is `indisprimary` (bool), not `index_def` (string at column 3) | Line ~232 | Changed to `(r[0], r[1], r[3])` — skips `indisprimary`, includes `index_def` |
| 2 | VARCHAR length check too lenient: `c[1].startswith(exp_type.split("(")[0])` matched ANY varchar regardless of length | Line ~353 | For types with `(length)`: require exact match via `exp_type in c[1]`; for types without: keep starts-with |
| 3 | Missing `ux_payments_receipt_number` index undetected when column exists but index doesn't | Line ~273 | Added `else: failures.append(...)` when `rn_idxs` is empty |

---

## 3. Test Coverage (10 tests)

### Test Class: `TestRealPreflightExecution`

| # | Test | Malformation | Preflight Function | RED Detection | GREEN |
|---|------|-------------|-------------------|---------------|-------|
| 1 | `test_wrong_check_constraint_fails_preflight` | `status IN ('pending','confirmed')` — missing 'rejected' | `_verify_declaration_catalog_pg` | CHECK status constraint missing/wrong | Drop + re-add correct CHECK |
| 2 | `test_wrong_fk_cascade_fails_preflight` | `order_id FK ON DELETE CASCADE` instead of RESTRICT | `_verify_declaration_catalog_pg` | order_id FK RESTRICT missing/wrong | Drop + re-add RESTRICT |
| 3 | `test_wrong_varchar_length_fails_preflight` | `transfer_reference VARCHAR(50)` instead of VARCHAR(128) | `_verify_declaration_catalog_pg` | type character varying(50) expected character varying(128) | ALTER TYPE back to VARCHAR(128) |
| 4 | `test_wrong_nullability_fails_preflight` | `reason SET NOT NULL` (should be nullable) | `_verify_declaration_catalog_pg` | reason: not_null=True expected False | DROP NOT NULL |
| 5 | `test_extra_is_deleted_fails_preflight` | `ADD COLUMN is_deleted BOOLEAN` | `_verify_declaration_catalog_pg` | is_deleted must not exist | DROP COLUMN |
| 6 | `test_missing_index_fails_preflight` | Drop `ix_payment_declarations_retailer_status` | `_verify_declaration_catalog_pg` | index missing | CREATE INDEX |
| 7 | `test_wrong_receipt_sequences_type_fails_preflight` | `business_date VARCHAR(10)` instead of CHAR(8) | `_verify_receipt_sequences_pg` | expected CHAR(8) | Recreate with CHAR(8) |
| 8 | `test_permission_collision_fails_preflight` | Both `client:payments:create` + `client:payments:declare` coexist | `_preflight_semantic` | collision — both exist | (none — test validates detection only) |
| 9 | `test_missing_receipt_index_fails_preflight` | Drop `ux_payments_receipt_number` but column exists | `_preflight_semantic` | ux_payments_receipt_number index missing | (none — test validates detection only) |

### Test Class: `TestTwoRegisteredTenants`

| # | Test | Description |
|---|------|-------------|
| 10 | `test_cross_tenant_failure_fingerprint_preserved` | Tenant A canonical, Tenant B malformed (wrong CHECK). Preflight fails only on B. Both fingerprints preserved. |

---

## 4. Fingerprint Contract

The `_fingerprint(schema)` function captures:
- Table existence (`payment_declarations`, `receipt_sequences`)
- Column definitions (`{name: (type, nullable)}`)
- Constraint count
- Index count

Every test asserts `fp_before == fp_after` — proving the preflight is **read-only** and never mutates the catalog.

---

## 5. Cross-Suite Regression

| Suite | Tests | Result |
|-------|-------|--------|
| R2: `test_dc12r1_s3_s2b_i1_financial_schema_foundation.py` | 36 | All GREEN |
| R3: `test_dc12r1_s3_s2b_i1_r3_migration_preflight.py` | 14 | All GREEN |
| R4: `test_dc12r1_s3_s2b_i1_r4_preflight_execution.py` | 10 | All GREEN |
| **Total** | **60** | **All GREEN** |

---

## 6. Node Classification

All 10 R4 nodes are classified **GREEN** (all pass on PG16 real catalog):

| # | Node | Classification |
|---|------|----------------|
| 1-9 | All `TestRealPreflightExecution` tests | GREEN (PASS) |
| 10 | `test_cross_tenant_failure_fingerprint_preserved` | GREEN (PASS) |

No RED, AMBER, or ENVIRONMENT_GATED nodes in the R4 suite.

---

## 7. Verdict

**PASS_FOR_CTO_DC12R1_S3_S2B_I1_R4_REAL_PREFLIGHT_EXECUTION**

All 10 real preflight execution tests pass. Three migration bugs identified and fixed during R4. Full regression across R2/R3/R4 confirms no regressions (60/60 GREEN).
