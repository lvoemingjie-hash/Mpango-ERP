# Cycle 3A — B5 Payment Legacy Harness Diagnosis

**Date:** 2026-05-09
**Author:** CodeBuddy (Product AI)
**Branch:** `ops/integration-rehearsal-clean-2026-05-08`
**HEAD:** `3a124a9`
**Status:** SUPERSEDED by Cycle 3B — schema-contract fix applied

---

## 1. Git Status

```
HEAD: 3a124a9 fix(platform): add audit contract columns to sys jobs

Untracked files:
  resolve_conflict.py  (kept untracked per hard constraint)

No staged changes. No modified files. No commits made this cycle.
```

---

## 2. B5 Node IDs

```
tests/test_b5_real_db.py::TestB5RealDB::test_cash_payment
tests/test_b5_real_db.py::TestB5RealDB::test_idempotency_violation
tests/test_b5_real_db.py::TestB5RealDB::test_idempotent_replay
tests/test_b5_real_db.py::TestB5RealDB::test_transfer_payment_first
```

---

## 3. B5 Full File Run

```
4 failed, 0 passed, 39 warnings in 4.15s
```

---

## 4. Per-Test Isolated Run Results

| # | Test | Isolated Result | Error Type | Error Detail |
|---|------|----------------|------------|--------------|
| 1 | `test_cash_payment` | **FAILED** | `AssertionError: 404 != 201` | `ORDER_NOT_FOUND` — order `550e8400-...-440002` does not exist in `t_dev.orders` |
| 2 | `test_transfer_payment_first` | **FAILED** | `UndefinedColumnError` | `column "retailer_id" does not exist` — `t_dev.payments` lacks `retailer_id` column |
| 3 | `test_idempotent_replay` | **FAILED** | `UndefinedColumnError` | `column "retailer_id" does not exist` — same root cause as #2 |
| 4 | `test_idempotency_violation` | **FAILED** | `UndefinedColumnError` | `column "retailer_id" does not exist` — same root cause as #2 |

**Key finding: All 4 tests fail independently.** This is NOT a cascade. Two distinct root causes exist.

---

## 5. Root Cause Evidence

### Root Cause 1: Hardcoded ORDER_ID Not in DB

**Query:**
```sql
SELECT id FROM t_dev.orders WHERE id='550e8400-e29b-41d4-a716-446655440002';
```

**Result:** 0 rows. The order does not exist.

**Impact:** `test_cash_payment` calls `POST /api/v1/payments` with this order ID. `PaymentService.create_payment()` looks up the order and raises 404 `ORDER_NOT_FOUND`.

**Classification:** B5 test depends on historical seed data that is no longer present.

### Root Cause 2: `t_dev.payments` Schema Diverges from Repository Code

**Actual `t_dev.payments` schema (from `\d t_dev.payments`):**

```
 id               | uuid
 order_id         | uuid
 amount           | numeric(12,2)
 method           | varchar(50)
 status           | varchar(50)
 reference_number | varchar(100)
 idempotency_key  | varchar(64)
 created_at       | timestamptz
 updated_at       | timestamptz
 is_deleted       | boolean
 deleted_at       | timestamptz
 created_by       | uuid
 updated_by       | uuid
```

**Missing columns that `payment_repository.py` expects:**
- `retailer_id` (used in SELECT, INSERT, and all list queries)
- `transaction_id` (used in SELECT, INSERT, and idempotency lookup)

**Source of divergence:**

| Source | Schema Version |
|--------|---------------|
| `scripts/bootstrap_tenant_schema.py` (line 147-157) | **No `retailer_id`, no `transaction_id`** — has `reference_number` instead |
| `alembic/versions/005_phase_b5_payments_minimal_loop.py` | **Has `retailer_id` and `transaction_id`** |
| `payment_repository.py` (all queries) | Expects `retailer_id` + `transaction_id` |

The `t_dev` tenant was created via `bootstrap_tenant_schema.py`, not via Alembic migration 005. The bootstrap script has a **simpler payments schema** that diverges from what the repository code expects.

**Impact:** Any code path that calls `PaymentRepository.create()` or any SELECT with `retailer_id`/`transaction_id` against `t_dev` (or any tenant created via bootstrap) will fail with `UndefinedColumnError`.

**Classification:** Schema-code mismatch. The repository was updated (presumably during Phase 5/6 development) to use `retailer_id` and `transaction_id`, but the bootstrap script was not updated to match.

---

## 6. Event Loop Cascade Assessment

| Test | Isolated Error | In Full File |
|------|---------------|--------------|
| `test_cash_payment` | `ORDER_NOT_FOUND` (404) | Same — runs first |
| `test_transfer_payment_first` | `UndefinedColumnError` | `RuntimeError: Event loop is closed` |
| `test_idempotent_replay` | `UndefinedColumnError` | `RuntimeError: Event loop is closed` |
| `test_idempotency_violation` | `UndefinedColumnError` | `RuntimeError: Event loop is closed` |

**Verdict:** The "Event loop is closed" errors in the full-file run are a **cascade side effect** of the first two tests' real failures. Tests 2-4 all fail independently with `UndefinedColumnError` when run alone. The event loop corruption is a secondary symptom, not a root cause.

---

## 7. Current Payment Mainline Test Results

### `test_payments_api.py` + `test_payment_atomicity.py`

```
7 passed, 0 failed, 1 warning in 0.90s
```

### `test_phase5_order_payment.py`

```
46 passed, 0 failed, 1 xfailed, 41 warnings in 2.11s
```

**Total payment mainline: 53 passed, 0 failed.**

All Phase 5/6 payment tests pass because they use **mocked DB** — they never execute SQL against the real `t_dev.payments` table. The `retailer_id`/`transaction_id` schema gap only manifests in tests that hit the real database through TestClient.

---

## 8. Production Risk Assessment

| Question | Answer |
|----------|--------|
| Does the payment API work in production? | **Depends on tenant schema version.** Tenants created via bootstrap have the diverged schema. |
| Are new tenants affected? | **Yes** — `bootstrap_tenant_schema.py` creates payments without `retailer_id`/`transaction_id` |
| Are existing tenants affected? | **Depends** — tenants migrated through Alembic 005 have the correct schema |
| Is this a real product defect? | **YES** — `payment_repository.py` will fail against any bootstrapped tenant |
| Can payments be created at all? | **NO** against bootstrapped tenants — `PaymentRepository.create()` INSERT includes `retailer_id`/`transaction_id` which don't exist |
| Is the Phase 5/6 payment flow affected? | **Yes in production** — `pay_order()` in `orders.py` calls `payment_repo.create()` which uses these columns |

**This is a latent production defect masked by mocked tests.** The Phase 5/6 tests all pass because they mock `PaymentRepository`, but any real-DB call through `pay_order()` or `POST /payments` will fail against a bootstrapped tenant.

---

## 9. CTO Decision Required

### Recommended: **Option B — Schema Alignment (product fix, not test fix)**

This is NOT just a B5 legacy harness issue. The `bootstrap_tenant_schema.py` script is out of sync with the payment repository. **Any real payment attempt against a bootstrapped tenant will fail.**

### Three Options

| Option | Description | Scope | Risk |
|--------|-------------|-------|------|
| **A** | Update `bootstrap_tenant_schema.py` to add `retailer_id` and `transaction_id` to payments table | 1 script file | Low — brings bootstrap in line with repository |
| **B** | Same as A + add Alembic migration to ALTER existing bootstrapped tenants | 1 script + 1 migration | Medium — requires migration against live tenants |
| **C** | Mark B5 as `@pytest.mark.skip("legacy harness — bootstrap schema diverged")` and defer | 1 test file | Defers production defect |

### CTO Guidance Requested

1. **Is `t_dev` the only bootstrapped tenant?** If so, Option A (update bootstrap + re-create `t_dev`) is sufficient.
2. **Are there production tenants created via bootstrap?** If yes, Option B (migration) is required.
3. **Should B5 tests be rewritten or deprecated regardless?** The hardcoded UUIDs make them fragile.

---

## 10. Confirmations

- No production code modified
- No test code modified
- No migrations added
- No commit made
- No push made
- No staging performed
- `resolve_conflict.py` remains untracked
- Only output: this diagnosis ledger
