# Cycle 3B — Payments Schema-Contract Alignment

**Date:** 2026-05-09
**Author:** CodeBuddy (Product AI)
**Branch:** `ops/integration-rehearsal-clean-2026-05-08`
**Status:** COMPLETE — awaiting CTO review, no commit

---

## 1. Git Status

```
HEAD: 3a124a9 fix(platform): add audit contract columns to sys jobs

Modified (unstaged):
  backend/scripts/bootstrap_tenant_schema.py
  backend/alembic/versions/021_tenant_payments_retailer_id_transaction_id.py (new)
  backend/tests/test_payments_schema_contract.py (new)

Updated (ledger):
  ai-ledger/ops/2026-05-09_cycle_3a_b5_payment_legacy_diagnosis.md
  ai-ledger/ops/2026-05-09_cycle_3b_payments_schema_contract_alignment.md (new)

Untracked:
  resolve_conflict.py  (kept untracked per hard constraint)

No commit. No push.
```

---

## 2. Problem Statement

Cycle 3A diagnosed that `bootstrap_tenant_schema.py` created `t_dev.payments` without `retailer_id` and `transaction_id`, while `payment_repository.py` expected both. This is a **latent production defect**: any real payment against a bootstrapped tenant would fail with `UndefinedColumnError`.

---

## 3. Changes

### 3.1 `backend/scripts/bootstrap_tenant_schema.py`

**Diff (payments CREATE TABLE):**

```diff
 f'CREATE TABLE IF NOT EXISTS "{ts}".payments ('
 "id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
 f'order_id UUID NOT NULL REFERENCES "{ts}".orders(id) ON DELETE CASCADE,'
+"retailer_id UUID NOT NULL,"
+"transaction_id VARCHAR(64),"
 "amount NUMERIC(12,2) NOT NULL,"
 "method VARCHAR(50) NOT NULL DEFAULT 'cash',"
 "status VARCHAR(50) NOT NULL DEFAULT 'completed',"
 "reference_number VARCHAR(100),"
```

**Added after CREATE TABLE loop:**

```python
# Indexes for payments table (idempotent via CREATE INDEX IF NOT EXISTS)
payment_indexes = [
    f'CREATE INDEX IF NOT EXISTS ix_{ts}_payments_order_id ON "{ts}".payments (order_id)',
    f'CREATE UNIQUE INDEX IF NOT EXISTS uq_{ts}_payments_transaction_id '
    f'ON "{ts}".payments (transaction_id) '
    f"WHERE transaction_id IS NOT NULL",
]
```

**Preserved:** `reference_number` column (additive alignment only).

### 3.2 `backend/alembic/versions/021_tenant_payments_retailer_id_transaction_id.py`

**New migration.** Revision chain: `020_sys_jobs_audit_columns` → `021_tenant_payments_retailer_id_transaction_id`.

**Strategy:**
1. Tenant-only (no-op on public schema)
2. If `payments` table exists but lacks `retailer_id`:
   - Add nullable `retailer_id UUID`
   - Backfill from `orders.retailer_id` via JOIN
   - **Fail-fast:** if any NULLs remain after backfill, raise `RuntimeError` exposing the data issue
   - Set `NOT NULL` constraint
3. If `payments` table exists but lacks `transaction_id`:
   - Add nullable `transaction_id VARCHAR(64)`
4. Create `ix_payments_order_id` index if missing
5. Create `uq_payments_transaction_id` partial unique index if missing

**Design decisions:**
- Nullable-first + backfill + NOT NULL pattern avoids data loss
- Explicit `RuntimeError` on orphaned payments prevents silent data corruption
- All operations idempotent (column/index existence checks)
- Downgrade drops all added columns and indexes

---

## 4. Migration Strategy

| Tenant Type | Impact |
|-------------|--------|
| **New tenants** (future bootstrap) | Correct schema from day one — `bootstrap_tenant_schema.py` now includes `retailer_id`/`transaction_id` |
| **Existing bootstrapped tenants** (e.g. `t_dev`) | Run `alembic -x tenant_schema=t_dev upgrade head` — migration 021 adds missing columns |
| **Alembic-migrated tenants** | Migration 021 is no-op (columns already exist from 005) |
| **Public schema** | No-op (migration returns immediately if not tenant search_path) |

---

## 5. Verification Results

### 5.1 Alembic Heads

```
021_tenant_payments_retailer_id_transaction_id (head)
```

Single head confirmed.

### 5.2 t_dev Schema After Migration

```sql
SELECT column_name, data_type, is_nullable FROM information_schema.columns
WHERE table_schema='t_dev' AND table_name='payments' ORDER BY ordinal_position;
```

```
 column_name     | data_type                | is_nullable
-----------------+--------------------------+-------------
 id              | uuid                     | NO
 order_id        | uuid                     | NO
 amount          | numeric                  | NO
 method          | character varying        | NO
 status          | character varying        | NO
 reference_number| character varying        | YES
 idempotency_key | character varying        | YES
 created_at      | timestamp with time zone | YES
 updated_at      | timestamp with time zone | YES
 is_deleted      | boolean                  | YES
 deleted_at      | timestamp with time zone | YES
 created_by      | uuid                     | YES
 updated_by      | uuid                     | YES
 retailer_id     | uuid                     | NO
 transaction_id  | character varying        | YES
```

**Indexes:**

```
 payments_pkey                | CREATE UNIQUE INDEX ... (id)
 payments_idempotency_key_key | CREATE UNIQUE INDEX ... (idempotency_key)
 ix_payments_order_id         | CREATE INDEX ... (order_id)
 uq_payments_transaction_id   | CREATE UNIQUE INDEX ... (transaction_id) WHERE (transaction_id IS NOT NULL)
```

Backfill: 0 rows updated (no existing payments in t_dev). No orphaned data.

### 5.3 Payment Mainline Tests

| Suite | Result |
|-------|--------|
| `test_payments_api.py` + `test_payment_atomicity.py` | **7 passed**, 0 failed (0.98s) |
| `test_phase5_order_payment.py` | **46 passed**, 1 xfailed (2.09s) |
| **Total mainline** | **53 passed**, 0 failed |

### 5.4 B5 Legacy Tests

| Test | Before 3B | After 3B | Classification |
|------|-----------|----------|----------------|
| `test_cash_payment` | `ORDER_NOT_FOUND` (404) | `ORDER_NOT_FOUND` (404) | Cycle 3C — hardcoded ORDER_ID |
| `test_transfer_payment_first` | `UndefinedColumnError` (retailer_id) | `ORDER_NOT_FOUND` (404) | **Schema fix resolved** — remaining is 3C |
| `test_idempotent_replay` | `UndefinedColumnError` (retailer_id) | Event loop cascade (from test_cash_payment) | **Schema fix resolved** — remaining is 3C |
| `test_idempotency_violation` | `UndefinedColumnError` (retailer_id) | Event loop cascade (from test_cash_payment) | **Schema fix resolved** — remaining is 3C |

**Key result:** `UndefinedColumnError` is **completely eliminated**. All 4 B5 tests now fail for the same root cause: hardcoded `ORDER_ID` `550e8400-e29b-41d4-a716-446655440002` not in DB. This is a test-seed issue deferred to Cycle 3C.

---

## 6. Files Changed

| File | Change |
|------|--------|
| `backend/scripts/bootstrap_tenant_schema.py` | Added `retailer_id`, `transaction_id`, order_id index, transaction_id partial unique index to payments DDL |
| `backend/alembic/versions/021_tenant_payments_retailer_id_transaction_id.py` | **New** — tenant migration to add missing columns to existing bootstrapped tenants |
| `backend/tests/test_payments_schema_contract.py` | **New** — schema-contract guard (7 static DDL + 6 live DB checks) |
| `ai-ledger/ops/2026-05-09_cycle_3a_b5_payment_legacy_diagnosis.md` | Status updated to SUPERSEDED |
| `ai-ledger/ops/2026-05-09_cycle_3b_payments_schema_contract_alignment.md` | **New** — this ledger |

---

## 7. Tenant Creation Path Coverage

| Path | Status | Notes |
|------|--------|-------|
| `bootstrap_tenant_schema.py` | **Fixed** | Now creates payments with `retailer_id`, `transaction_id`, and required indexes |
| `alembic migration 021` | **New** | Brings existing bootstrapped tenants into compliance |
| `onboard_tenant.py` | **Not audited this cycle** | Uses Alembic `upgrade head` (which includes 021) or `metadata.create_all` fallback — **requires follow-up audit** to confirm fallback path generates correct schema |
| `seed_demo_data.py` | **No concern** | Seeds data only, does not create/alter tables |
| Other tenant creation paths | **Not audited** | Any custom scripts or manual DDL should be reviewed in a future cycle |

**IMPORTANT:** This cycle **only fixes the `bootstrap_tenant_schema.py` path**. The claim must not be made that all tenant creation paths are now safe. Specifically, `onboard_tenant.py`'s `_fallback_create_tables()` method uses `BaseModel.metadata.create_all` which depends on SQLAlchemy model definitions — those should be audited separately.

---

## 8. Schema-Contract Guard

### File: `backend/tests/test_payments_schema_contract.py`

**Run command:**
```bash
poetry run pytest tests/test_payments_schema_contract.py -q --tb=short
```

### Static DDL Checks (TestBootstrapDDLContract) — always runs, no DB needed

| Test | What it checks |
|------|----------------|
| `test_payments_has_retailer_id` | `retailer_id` column present in payments DDL |
| `test_payments_has_transaction_id` | `transaction_id` column present in payments DDL |
| `test_payments_retailer_id_is_not_null` | `retailer_id` declared `NOT NULL` |
| `test_payments_transaction_id_is_nullable` | `transaction_id` is nullable (no `NOT NULL`) |
| `test_payments_preserves_reference_number` | `reference_number` column not accidentally removed |
| `test_payments_has_order_id_index` | `ix_payments_order_id` index DDL present |
| `test_payments_has_transaction_id_partial_unique_index` | `uq_payments_transaction_id` partial unique index DDL + `IS NOT NULL` condition |

### Live Schema Checks (TestLiveSchemaContract) — runs against t_dev if DB reachable

| Test | What it checks |
|------|----------------|
| `test_live_has_retailer_id` | `t_dev.payments` actually has `retailer_id` column |
| `test_live_retailer_id_not_null` | `retailer_id` is `NOT NULL` in live schema |
| `test_live_has_transaction_id` | `t_dev.payments` actually has `transaction_id` column |
| `test_live_transaction_id_nullable` | `transaction_id` is nullable in live schema |
| `test_live_has_order_id_index` | `ix_payments_order_id` index exists |
| `test_live_has_transaction_id_partial_unique` | `uq_payments_transaction_id` partial unique index exists |

### Results

```
13 passed, 0 failed, 0 skipped in 0.92s
```

All 7 static + 6 live checks green.

---

## 9. Full Test Suite Re-verification (Polish Run — Pre-Final-Polish)

```
$ poetry run alembic heads
021_tenant_payments_retailer_id_transaction_id (head)

$ poetry run pytest ... -q --tb=short
66 passed, 1 xfailed, 47 warnings in 3.79s
```

### 9.1 Final Polish Verification Run (2026-05-11)

```
$ poetry run alembic heads
021_tenant_payments_retailer_id_transaction_id (head)

$ poetry run pytest tests/test_payments_api.py tests/test_payment_atomicity.py tests/test_phase5_order_payment.py tests/test_payments_schema_contract.py -q --tb=short
67 passed, 1 xfailed, 41 warnings in 2.91s
```

- +1 test vs. Polish Run: `test_index_names_match_migration_021` (new cross-check)
- -6 warnings vs. Polish Run: asyncio cleanup eliminated pytest-asyncio event loop warnings
- All remaining warnings are pre-existing (datetime.utcnow deprecation, declarative_base moved, unawaited coroutine in ledger_service)
- **0 new warnings from Cycle 3B changes**

---

## 10. Final Polish (2026-05-11)

CTO directed three final refinements before commit approval.

### 10.1 Bootstrap Index Name Alignment

**Problem:** Bootstrap used schema-prefixed index names (`ix_{ts}_payments_order_id`, `uq_{ts}_payments_transaction_id`) while migration 021 uses bare names (`ix_payments_order_id`, `uq_payments_transaction_id`). Inconsistent naming would cause duplicate indexes if both paths ran on the same tenant.

**Fix:** Removed `{ts}_` prefix from bootstrap index names to match migration 021 exactly:

```python
# Before (Final Polish)
f'CREATE INDEX IF NOT EXISTS ix_{ts}_payments_order_id ON "{ts}".payments (order_id)'
f'CREATE UNIQUE INDEX IF NOT EXISTS uq_{ts}_payments_transaction_id ...'

# After (Final Polish)
f'CREATE INDEX IF NOT EXISTS ix_payments_order_id ON "{ts}".payments (order_id)'
f'CREATE UNIQUE INDEX IF NOT EXISTS uq_payments_transaction_id ...'
```

### 10.2 Strengthened Static Index Name Checks

**Problem:** Static tests checked for substring `"payments_order_id"` which could match either naming convention.

**Fix:** Changed to exact match on `"ix_payments_order_id"` and `"uq_payments_transaction_id"`. Added new cross-check test `test_index_names_match_migration_021` that explicitly verifies bootstrap names match migration 021 naming.

### 10.3 Asyncio Warning Cleanup

**Problem:** `@pytest.mark.asyncio(loop_scope="session")` on `TestLiveSchemaContract` caused warnings when pytest-asyncio event loop management conflicted with async fixtures.

**Fix:** Removed class-level `@pytest.mark.asyncio` decorator (async fixtures handle their own loop). Extracted `_get_db_urls()` and `_to_async_url()` helpers for cleaner connection management. Removed unused `re` import.

### 10.4 Schema-Contract Guard (Post-Polish)

Static checks: **8 tests** (7 original + 1 new cross-check `test_index_names_match_migration_021`)
Live checks: **6 tests** (unchanged)
Total: **14 tests** in guard suite.

---

## 11. Confirmations

- No production payment logic modified (`payment_repository.py` untouched)
- No public schema changes
- No push
- No commit (awaiting CTO review)
- `resolve_conflict.py` remains untracked
- All payment mainline tests green (67 passed including schema-contract guard)
- `UndefinedColumnError` eliminated from B5
- B5 remaining failures classified as Cycle 3C (hardcoded ORDER_ID seed data)
- Schema-contract guard covers both static DDL analysis and live DB verification
- **Only `bootstrap_tenant_schema.py` path is confirmed fixed. `onboard_tenant.py` and other paths require follow-up audit.**

---

## 12. Micro-Polish: Schema-Contract Guard Precision (2026-05-11)

CTO directed precision fix for static check accuracy. **No production code changed.**

### 12.1 Problem: `_extract_payments_block()` Over-Extraction

**Root cause:** The closing-line check `line.rstrip().endswith(")")` never matched the actual payments DDL closing line. In the bootstrap Python source, the closing line is:
```python
            "created_by UUID, updated_by UUID)",
```
This ends with `)",` (closing paren → Python string close → list comma), NOT with `)`.

The `endswith(")")` check failed on every line of the payments block, so the extractor kept scanning past `ledger_entries` DDL, `payment_indexes` DDL, and the trigger function — returning a massive over-extracted block that included code from other tables and indexes.

**Fix:** Detect closing line by pattern: SQL `)` immediately followed by Python string close quote (`"` or `'`), optionally followed by list comma. This distinguishes `gen_random_uuid(),"` (ends with `,"` — comma between `)` and quote) from `UUID)",` (ends with `)",` — quote immediately after `)`).

### 12.2 Problem: Partial Unique Index False-Pass

**Root cause:** `test_payments_has_transaction_id_partial_unique_index` checked `"IS NOT NULL" in bootstrap_source` on the full file. Combined with the over-extraction from `_extract_payments_block()`, this could match any `IS NOT NULL` anywhere in the file (comments, other DDL, trigger code).

**Fix:** Added `_extract_uq_transaction_id_block()` helper that extracts only the 3 lines of the `uq_payments_transaction_id` index DDL. The test now verifies all three components within the extracted block:
1. `CREATE UNIQUE INDEX IF NOT EXISTS uq_payments_transaction_id`
2. `ON "{ts}".payments (transaction_id)`
3. `WHERE transaction_id IS NOT NULL`

### 12.3 Strengthened `test_index_names_match_migration_021`

Added structural verification: `uq_payments_transaction_id` must appear in the index DDL block, NOT in the CREATE TABLE block. This catches a hypothetical regression where the index name leaks into column definitions.

### 12.4 Files Changed

| File | Change |
|------|--------|
| `backend/tests/test_payments_schema_contract.py` | Precision fixes only — no production code |
| `ai-ledger/ops/2026-05-09_cycle_3b_payments_schema_contract_alignment.md` | This section |

### 12.5 Verification

```
$ poetry run alembic heads
021_tenant_payments_retailer_id_transaction_id (head)

$ poetry run pytest tests/test_payments_schema_contract.py -q --tb=short
14 passed, 1 warning in 0.90s

$ poetry run pytest tests/test_payments_api.py tests/test_payment_atomicity.py tests/test_phase5_order_payment.py tests/test_payments_schema_contract.py -q --tb=short
67 passed, 1 xfailed, 41 warnings in 2.89s
```

- 0 new warnings
- No production code modified
- All pre-existing warnings unchanged
