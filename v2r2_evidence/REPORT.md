# DC-12R1-MVP-L1-J1-H2-B-R2-R1-V2-R2: Failed-Schema Lifecycle Causality Audit

## Classification: TEST_FIXTURE_RESIDUE_DEFECT

The 5 DC3B failures are caused by test fixture residue from a preceding test node,
not by candidate code defects.

## Phase 1 — Proof: PASS

| Check | Result |
|-------|--------|
| Candidate SHA | 34ccec116204b6a61b2e37c874b0c65953acfb43 |
| Parent | 87e5cbf52a169be17a20ca865631c7f667f5b59f |
| Protected baseline | 6e9470a1daa5d6eece29724316fdd8aef6b737c1 (ancestor OK) |
| Kilo E2 | 3e796996382872f10d5bd5312cdbbfe311d9cc7c |
| Delta | 7 files |
| Clean tree | Yes |

## Phase 2 — Fresh Correct Stack: PASS

- User: h2btester (not mpango)
- Database: test_h2b_diag_a
- PG port: 15441, Redis port: 16384
- Pre-conditions: zero wholesalers, clean tree, Alembic 037

## Phase 3 — Clean Control: PASS

DC3B alone on empty migrated database: **16/16 PASSED**

This proves DC3B has NO inherent defect.

## Phase 4 — Contamination Causality: IDENTIFIED

### Bisection Result

| Round | Modules/Nodes Tested | DC3B Result |
|-------|---------------------|-------------|
| 1 | Last 10 modules before DC3B | 5 failed |
| 2A | First 5 of those 10 | 5 failed |
| 3 | First 2 of those 5 | 16 passed (clean) |
| 4 | Modules 3-5 | 5 failed |
| 5 | Module 3 alone (real_alembic_upgrade) | 16 passed (clean) |
| 6 | Module 4 alone (canonical_payment_service) | 5 failed |
| 7 | First 9 nodes of module 4 | 16 passed (clean) |
| 8 | Last 9 nodes of module 4 | 5 failed |
| 9 | Nodes 10-14 | 5 failed |
| 10 | **Node 10 alone** | **5 failed** |

### Exact Contaminating Node

```
tests/test_dc12r1_s3_s2b_i2a_canonical_payment_service.py
  ::test_service_cross_tenant_same_key_isolated
```

### Contamination Mechanism

1. The contaminating test calls `_seed_confirmed_order` with a hardcoded tenant UUID
   `33333333-3333-3333-3333-333333333333`, which INSERTs a wholesaler row into
   `public.wholesalers` via `ON CONFLICT ... DO UPDATE`.

2. It bootstraps the derived schema `t_33333333333333333333333333333333` with
   `_bootstrap_minimal_tenant_schema`, which creates order/payment tables but
   does NOT create a `users` table.

3. The test commits and disposes the engine, but the wholesaler row persists in
   `public.wholesalers` with `is_deleted = false` and `status = 'active'`.

4. When DC3B's password reset scan (`_enumerate_active_tenant_users`) runs, it
   visits all non-deleted wholesalers. For the hardcoded UUID wholesaler, it
   attempts `SELECT ... FROM "t_333...".users`. This query fails (table does not
   exist), increments `failed_schema_count`, and the scan result has
   `failed_schema_count > 0`.

5. DC3B's `consume_reset` method checks `if scan.failed_schema_count` and raises
   `PasswordResetScanIncompleteError`, which the API maps to a neutral 401.

### Post-Contamination Database State

- public.wholesalers with DC11D prefix: 2 rows (active, not deleted)
- Schema `t_33333333333333333333333333333333`: exists, has NO `users` table
- Wholesaler `33333333-3333-3333-3333-333333333333`: active, not deleted
- Schema missing users table: 1 (the hardcoded UUID schema)
- Failed-schema aggregate: 1 (from this schema)

### Originating Test Module and Node

- Module: `tests/test_dc12r1_s3_s2b_i2a_canonical_payment_service.py`
- Node: `test_service_cross_tenant_same_key_isolated`
- Helper: `_seed_confirmed_order` from `tests/test_dc11d_payment_replay_concurrency_integrity.py`
- Bootstrap: `_bootstrap_minimal_tenant_schema` creates schema without `users` table

## Phase 5 — Interaction Proof: CONFIRMED

| Scenario | Result |
|----------|--------|
| DC3B alone (Phase 3) | 16/16 PASSED |
| Contaminator + DC3B (Phase 4 round 6/10) | 5 failed, 11 passed |

The contamination is deterministic and reproducible.

## Phase 6 — Classification

**Classification: TEST_FIXTURE_RESIDUE_DEFECT**

The contaminating test (`test_service_cross_tenant_same_key_isolated`) creates a
wholesaler with a hardcoded UUID and bootstraps a schema without a `users` table,
but does not clean up the wholesaler row after the test completes. This residue
persists in the shared test database and causes DC3B's password reset scan to fail
on the orphaned schema.

Cleanup owner: `test_dc12r1_s3_s2b_i2a_canonical_payment_service.py` — the
`test_service_cross_tenant_same_key_isolated` node should delete the hardcoded
wholesaler row (or mark it `is_deleted = true`) in its teardown.

Candidate code is NOT responsible. The candidate's password reset code correctly
fails closed when the scan encounters an unscannable schema (PASSWORD_RESET_SCAN_INCOMPLETE).

## Phase 7 — Evidence Truth

### Superseded V2-R1 Statements

- "active wholesaler-derived schemas" → SUPERSeded: the failing schema is an
  orphaned test fixture residue, not an active lifecycle schema
- "candidate_defects: []" → PRESERVED (correct — no candidate defects)
- unconditional "not a candidate code defect" → SUPERSeded: now supported by
  exact bisection proof showing test fixture residue as root cause

### Preserved Statements

- V2 environment was INVALID (mpango/mpango)
- V2 focused 109/109 remains valid
- V2-R1 Stack A accounting is 3682/5/48/15/0
- Candidate fail-closed behavior is verified (PASSWORD_RESET_SCAN_INCOMPLETE)

### V2-R1 Correction

V2-R1's classification of "not a candidate code defect" was correct but
insufficiently justified. V2-R2 provides the exact bisection proof.
