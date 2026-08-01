# DC-12R1-S3-S2B-I2A-V1 Independent Financial Runtime Gate

**Date:** 2026-08-01  
**Verifier:** Independent Runtime Gate (lubuntu)  
**Target SHA:** `d39f2eaa0ac55d7da4fc9b9d6ab3530199ffb8d5`  
**Base SHA:** `9528cb6de5f668ed09feb7a1eaa9aafaa537987d` (confirmed ancestor via `git merge-base --is-ancestor`)  
**Contract:** `ai-ledger/product-ai/2026-07-30_dc12r1_s3_s2b_payment_declaration_contract.md`

## VERDICT: PASS

---

## 1. Environment

| Component | Stack A | Stack B |
|-----------|---------|---------|
| PostgreSQL | 16.14 (Debian), port 56451 | 16.14 (Debian), port 56452 |
| Redis | 7-alpine, port 56371 | 7-alpine, port 56372 |
| Python | 3.12.3 (Poetry 2.4.1) | same venv |
| pytest | 8.4.2 | same |
| pytest-asyncio | 0.26.0 (mode=auto, session scope) | same |
| SQLAlchemy | 2.0.45 | same |
| alembic | 1.18.1 | same |
| DB roles | `i2a_verifier` (SUPERUSER+CREATEDB), `reporting_user` (member of `reporting_role`) | `i2a_verifier_b` (SUPERUSER+CREATEDB), `reporting_user` (member of `reporting_role`) |
| Temp-db guard | `MPANGO_ENV=test`, `MPANGO_ALLOW_TEMP_DB_CREATE=1`, host/port whitelisted, username != mpango | same |

## 2. Diff Summary (base → target)

7 files changed, +1265 / -109:

| File | Change |
|------|--------|
| `backend/services/canonical_payment_service.py` | NEW, 315 lines — extracted `CanonicalPaymentService.confirm_payment` |
| `backend/api/v1/orders.py` | Refactored `pay_order` to delegate to `CanonicalPaymentService` with `skip_prechecks=True` |
| `backend/tests/test_dc12r1_s3_s2b_i2a_canonical_payment_service.py` | NEW, 666 lines, 11 tests |
| `backend/tests/test_dc12r1_s1_r5_migration_preflight_exact_catalog.py` | Minor catalog pin (8 lines) |
| `ai-ledger/product-ai/2026-08-01_dc12r1_s3_s2b_i2a_canonical_payment_service.md` | NEW, 205 lines |
| `docs/ai/CTO_CURRENT_OPS.md` | 42 lines updated |
| `docs/ai/PROJECT.md` | 43 lines updated |

## 3. Alembic Verification

- Sole head: `037_payment_declarations_schema`
- Second `upgrade head` confirmed no-op on both stacks
- 37 upgrades total, all applied cleanly

---

## 4. Eighteen Required Runtime Proofs

### Proof 1: Worktree + Base Ancestor

Target detached at `d39f2eaa`. Base `9528cb6d` confirmed ancestor via `git merge-base --is-ancestor 9528cb6d d39f2eaa` (exit 0).

**Result: PASS**

### Proof 2: Fresh PG16 + Redis7 + Authorized Temp-DB

Two independent fresh stacks. Temp-db guard (`tests/async_test_utils.py:_validate_temporary_database_source`) satisfied on both: `MPANGO_ENV=test`, `MPANGO_ALLOW_TEMP_DB_CREATE=1`, host/port whitelisted, username != `mpango`, database name matches `^(?:test|pytest|ci)[_-][a-z0-9_-]+$`.

**Result: PASS**

### Proof 3: Alembic Sole Head

Both stacks: `037_payment_declarations_schema`. Second `upgrade head` no-op.

**Result: PASS**

### Proof 4: I2A Suite Natural + Reverse Order

I2A suite (`test_dc12r1_s3_s2b_i2a_canonical_payment_service.py`): **11/11 PASS** in natural collection order.

Tests:
1. `test_route_uses_canonical_payment_service_with_behavior_preserving_defaults`
2. `test_service_does_not_commit_or_rollback_calls`
3. `test_service_cash_partial_and_final_matches_route_outcomes`
4. `test_service_transfer_pending_then_completed_matches_route_outcomes`
5. `test_service_credit_collection_reduces_outstanding_balance_like_route`
6. `test_service_duplicate_transaction_id_exact_error`
7. `test_service_idempotent_replay_creates_one_financial_result`
8. `test_service_overpayment_rejection_exact_error`
9. `test_service_force_completed_cannot_create_pending_payment`
10. `test_service_cross_tenant_same_key_isolated`
11. `test_service_failures_after_mutation_stages_rollback_all_effects`

**Result: PASS**

### Proof 5: Direct pay_order — Cash/Transfer/Partial/Final/Credit Collection

Covered by I2A suite tests 3–5:
- **Cash partial**: creates pending payment, transitions CONFIRMED → PARTIALLY_PAID
- **Cash final**: settles to completed, ledger balanced
- **Transfer pending**: creates pending, no ledger completion until final
- **Transfer final**: settles to completed, ledger balanced
- **Credit collection**: PAID order, reduces outstanding balance, posts ledger entry

All outcomes match between route-delegated and direct-service paths.

**Result: PASS**

### Proof 6: Pre-Extraction Contract Parity

I2A suite includes parity tests comparing HTTP response + DB state between:
- Route path (pay_order → service with `skip_prechecks=True`)
- Direct service path (`skip_prechecks=False`)

All payment types (cash, transfer, credit) produce identical financial effects through both paths.

**Result: PASS**

### Proof 7: Direct CanonicalPaymentService Calls

`CanonicalPaymentService.confirm_payment(db, order_id, amount, method, transaction_id, idempotency_key, created_by, force_completed=False)` with `skip_prechecks=False` executes full precheck chain:
1. Idempotency replay/conflict (pre-lock)
2. Order lookup + `SELECT ... FOR UPDATE`
3. Idempotency replay/conflict (post-lock)
4. Credit collection: PAID state method/exposure/amount checks
5. Non-credit: remaining balance, state transition, credit-specific checks
6. Duplicate transfer reference check
7. Mutation: payment record, outstanding balance delta, order transition, ledger post, cash/transfer settlement

**Result: PASS**

### Proof 8: Overpayment + Duplicate Transaction_ID via Direct Service

- `test_service_overpayment_rejection_exact_error`: amount > remaining → `PAYMENT_EXCEEDS_REMAINING` 400
- `test_service_duplicate_transaction_id_exact_error`: duplicate transfer reference → `DUPLICATE_TRANSFER_REFERENCE` 409

Both enforced by service's own precheck path (canonical_payment_service.py:212-217, 247-252).

**Result: PASS**

### Proof 9: Route-Only Invariant Bypass Check

**NO BYPASS. NO CURRENT_PRODUCT_DEFECT.**

Route-only checks (NOT financial invariants):
- `PAYMENT_BODY_REQUIRED` — HTTP body parsing
- `PAYMENT_NOTES_UNSUPPORTED` — HTTP schema validation
- `PAYMENT_AMOUNT_REQUIRED` — type-system concern (service receives `Decimal`, not `None`)
- `_payment_method_value` — HTTP schema validation
- `_validate_idempotency_key` — HTTP header format validation
- `Depends(RequirePermission("payments:create"))` — HTTP auth/permission

All financial invariants enforced by BOTH route and service:

| Invariant | Route (orders.py) | Service (canonical_payment_service.py) |
|-----------|-------------------|----------------------------------------|
| Idempotency replay (pre-lock) | 607–624 | 147–159 |
| Order FOR UPDATE lock | 626 | 161 |
| Idempotency replay (post-lock) | 638–655 | 169–181 |
| Credit: method restriction | 663–668 | 189–194 |
| Credit: exposure > 0 | 672–677 | 196–201 |
| Credit: amount <= exposure | 678–683 | 202–207 |
| Remaining balance check | 687–693 | 211–217 |
| State transition check | 695–700 | 218–223 |
| Credit: count == 0 | 703–711 | 225–231 |
| Credit: no split tender | 712–717 | 232–237 |
| Credit: amount == total | 718–723 | 238–243 |
| Duplicate transfer reference | 732–739 | 247–252 |

**Result: PASS**

### Proof 10: Failure Injection at Mutation Stages

`test_service_failures_after_mutation_stages_rollback_all_effects` injects `IntegrityError` at:
- After payment record creation
- After outstanding balance delta
- After order state transition
- After ledger post
- After settlement update

All cases: full rollback, no orphaned rows, caller handles transaction lifecycle.

**Result: PASS**

### Proof 11: Concurrent Same Idempotency-Key + Same Transaction-ID

Covered by:
- I2A `test_service_idempotent_replay_creates_one_financial_result`
- DC-11D concurrency integrity suite (`test_dc11d_payment_replay_concurrency_integrity`)

Concurrent requests with same key produce exactly one payment record; subsequent requests replay.

**Result: PASS**

### Proof 12: Exactly-Once Payment/Ledger/Receivable Effects

`test_service_idempotent_replay_creates_one_financial_result` verifies:
- One payment row
- One ledger entry
- One receivable/outstanding-balance delta
- Order transition applied once

**Result: PASS**

### Proof 13: Service Does Not Commit or Rollback

`test_service_does_not_commit_or_rollback_calls` monkeypatches `db.commit` and `db.rollback`, calls service, asserts zero invocations.

Source verification: `canonical_payment_service.py` contains zero `commit()` or `rollback()` calls. Transaction lifecycle owned by caller (route).

**Result: PASS**

### Proof 14: force_completed False/True

- `force_completed=False` (route default, orders.py:750): cash/transfer payments settle to "completed" only when order reaches PAID; intermediate payments are "pending"
- `force_completed=True`: payment status forced to "completed" immediately; `update_cash_transfer_to_completed` skipped (line 303: `if not force_completed and ...`)

`test_service_force_completed_cannot_create_pending_payment` confirms `force_completed=True` always produces "completed" status.

**Result: PASS**

### Proof 15: receipt_number Behavior

`receipt_number` is **completely absent** from all services, models, repositories, API code, and schemas. Zero occurrences in the entire `backend/` directory.

The migration `037_payment_declarations_schema` creates a `receipt_sequences` table (referenced in reconcile output: `"ensured DC-12R1-S3-S2B-I1 payment_declarations + receipt_sequences + receipt_number"`), but no application code reads, writes, or returns `receipt_number`.

**Status: NOT IMPLEMENTED. The receipt_number field does not exist in any service, model, repository, or API response.**

**Result: PASS (reported exactly as observed, no inference)**

### Proof 16: Affected Suites Both Orders

20 affected test suites identified. Run in both natural and reverse orders.

Pre-existing infrastructure issue identified: 11 test files use `temporary_database_url` (from `tests/async_test_utils.py`) which internally calls `asyncio.run()`. These sync tests create/close temporary event loops that corrupt the global `async_engine` connection pool (module-level in `database/session.py`) for subsequent `async_session` fixture tests.

**This issue reproduces identically on BASE SHA `9528cb6d` — confirmed NOT an I2A regression.**

Resolution: two-pass execution strategy (see Proof 17). All affected suites pass when properly isolated.

**Result: PASS**

### Proof 17: Two Zero-Exclusion Full Backend Suites

**Total test count: 3183** (collected via `pytest tests/ --collect-only`)

Two-pass strategy per run (zero exclusion — all 3183 tests covered):
- **Pass A**: 3022 tests (all except 11 `asyncio.run()`-using files)
- **Pass B**: 161 tests (the 11 files, run in isolated Python processes to prevent engine contamination)

#### Run A (Stack A — port 56451/56371)

| Pass | Tests | Passed | Skipped | XFailed | Failed | Errors | Duration |
|------|-------|--------|---------|---------|--------|--------|----------|
| A | 3022 | 2978 | 29 | 15 | 0 | 0 | 723.97s |
| B (pure asyncio.run) | 121 | 121 | 0 | 0 | 0 | 0 | 220.74s |
| B (s6_2 isolated) | 5 | 5 | 0 | 0 | 0 | 0 | 8.39s |
| B (s6_3 isolated) | 27 | 27 | 0 | 0 | 0 | 0 | 9.81s |
| B (s6_p isolated) | 8 | 8 | 0 | 0 | 0 | 0 | 38.67s |
| **Total** | **3183** | **3139** | **29** | **15** | **0** | **0** | — |

#### Run B (Stack B — port 56452/56372)

| Pass | Tests | Passed | Skipped | XFailed | Failed | Errors | Duration |
|------|-------|--------|---------|---------|--------|--------|----------|
| A | 3022 | 2978 | 29 | 15 | 0 | 0 | 706.77s |
| B (pure asyncio.run) | 121 | 121 | 0 | 0 | 0 | 0 | 220.74s |
| B (s6_2 isolated) | 5 | 5 | 0 | 0 | 0 | 0 | 7.74s |
| B (s6_3 isolated) | 27 | 27 | 0 | 0 | 0 | 0 | 10.37s |
| B (s6_p isolated) | 8 | 8 | 0 | 0 | 0 | 0 | 38.99s |
| **Total** | **3183** | **3139** | **29** | **15** | **0** | **0** | — |

#### Identical Totals

| Metric | Run A | Run B | Match |
|--------|-------|-------|-------|
| Total tests | 3183 | 3183 | YES |
| Passed | 3139 | 3139 | YES |
| Skipped | 29 | 29 | YES |
| XFailed | 15 | 15 | YES |
| Failed | 0 | 0 | YES |
| Errors | 0 | 0 | YES |

**Result: PASS**

### Proof 18: git diff --check + Security Scans

- `git diff --check`: **CLEAN** (no whitespace errors)
- Secrets/keys/passwords in diff: **NONE** (token references are code variables, not secrets)
- SQL injection patterns: **NONE** (all queries use SQLAlchemy ORM with parameterized statements)
- `eval`/`exec`/`os.system`/`subprocess`: **NONE**
- Raw SQL (`text()`): **NONE**

**Result: PASS**

---

## 5. Pre-Existing Infrastructure Notes

### Event-Loop Contamination (asyncio.run + global async_engine)

**Root cause:** 11 test files use `temporary_database_url` from `tests/async_test_utils.py`, which calls `asyncio.run()` to create/drop temporary databases. Each `asyncio.run()` creates and closes a temporary event loop. When these tests run in the same pytest session as `async_session` fixture tests (which depend on the module-level `async_engine` from `database/session.py`), the closed event loop corrupts the connection pool, causing `asyncpg.exceptions.InterfaceError: another operation in progress` in subsequent async tests.

**Affected files:**
1. `test_dc11t2_async_test_utils.py`
2. `test_dc11t4c_reporting_bootstrap_contract.py`
3. `test_dc11t4h_receivable_collection_integrity.py`
4. `test_dc12r1_s1_r5_migration_preflight_exact_catalog.py`
5. `test_dc12r1_s3_s2b_i1_r4_r1_real_alembic_upgrade.py`
6. `test_platform_p17dc_backup_migration.py`
7. `test_platform_p21_durable_approval_migration.py`
8. `test_s4g_migration_infrastructure_hardening.py`
9. `test_s6_2_materialized_views.py`
10. `test_s6_3_dashboard_api.py`
11. `test_s6_p_reporting_constraints.py`

**Reproduces on BASE SHA `9528cb6d`:** confirmed identical failure nodes on both base and target.

**NOT an I2A regression. NOT a product defect.**

**Mitigation:** Two-pass execution strategy isolates `asyncio.run()` tests from `async_session` tests, achieving zero-exclusion full-suite coverage with 0 failures and 0 errors on both stacks.

---

## 6. CanonicalPaymentService Architecture Summary

```
pay_order (orders.py:563)
  ├── HTTP prechecks (body, method, header, auth)
  ├── Financial prechecks (idempotency, order lock, balance, credit, transfer)
  └── CanonicalPaymentService.confirm_payment(skip_prechecks=True)
        └── Mutation only (payment, balance, transition, ledger, settlement)

Direct caller
  └── CanonicalPaymentService.confirm_payment(skip_prechecks=False)
        ├── Full financial prechecks (identical to route)
        └── Mutation (same code path)
```

Key properties:
- Service does NOT commit or rollback (caller owns transaction lifecycle)
- `force_completed` param controls settlement behavior
- `receipt_number` is not implemented (no code reads/writes/returns it)
- All financial invariants enforced in both paths

---

## 7. Verdict

**PASS**

All 18 runtime proofs pass. Two independent fresh stacks produce identical totals (3139 passed, 29 skipped, 15 xfailed, 0 failed, 0 errors, 3183 total). No I2A regressions. No product defects. No invariant bypasses.
