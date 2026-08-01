# DC-12R1-S3-S2B-I2A-V1-R1 Independent Financial Runtime Gate (Corrected)

**Date:** 2026-08-02  
**Verifier:** Independent Runtime Gate (lubuntu)  
**Target SHA:** `d39f2eaa0ac55d7da4fc9b9d6ab3530199ffb8d5`  
**Base SHA:** `9528cb6de5f668ed09feb7a1eaa9aafaa537987d` (confirmed ancestor via `git merge-base --is-ancestor`)  
**Prior report:** Retracted. This document supersedes `2026-08-01_dc12r1_s3_s2b_i2a_v1_independent_runtime.md` (v1).

## VERDICT: STOP_AND_REPORT_CTO

The exact full-gate command (`poetry run pytest tests/ -q`) produces failures and errors on both fresh stacks and does not exit 0. The prior PASS verdict is retracted.

---

## 1. Corrections to Prior Report

### 1.1 Retraction of PASS

The prior PASS was based on a two-pass split-run strategy (3022 tests + 161 tests in separate processes). That strategy is moved to **DIAGNOSTIC_ONLY_NON_AUTHORITATIVE** (Appendix A). The exact gate requires a single `pytest tests/ -q` process with no exclusions.

### 1.2 receipt_number — Corrected Wording

**Prior (incorrect):** "`receipt_number` is completely absent from all services, models, repositories, API code, and schemas."

**Corrected:** Migration `037_payment_declarations_schema` creates `payments.receipt_number VARCHAR(32)` with a partial unique index (`alembic/versions/037*.py:389-398`). The bootstrap/reconcile step references it (`"ensured DC-12R1-S3-S2B-I1 payment_declarations + receipt_sequences + receipt_number"`). The `receipt_sequences` table is defined in `models/payment_declaration.py:171`.

However, application services, repositories, API endpoints, and schemas (excluding the `payment_declaration` model) do not yet read, allocate, write, or expose `receipt_number`. Specifically: zero occurrences in `services/`, `repositories/`, `api/`, `schemas/`, and `models/payment.py`.

### 1.3 temporary_database_url — Unsupported Claim Removed

**Prior (incorrect):** "`temporary_database_url` internally calls `asyncio.run()`."

**Corrected:** `temporary_database_url` (`tests/async_test_utils.py:124-153`) uses synchronous `psycopg2.connect()` to create and drop disposable databases. It does not call `asyncio.run()`. The related helpers `run_coroutine` (line 40) and `run_alembic_upgrade` (line 58) use `loop.run_until_complete()` and `_run_alembic_preserving_loop` respectively, interacting with the existing event loop policy. No claim about the contamination mechanism is made in this report.

---

## 2. Environment

| Component | Stack A | Stack B |
|-----------|---------|---------|
| PostgreSQL | 16 (Debian), port 56501 | 16 (Debian), port 56502 |
| Redis | 7-alpine, port 56401 | 7-alpine, port 56402 |
| Python | 3.12.3 (Poetry 2.4.1) | same venv |
| pytest | 8.4.2, asyncio 0.26.0 (mode=auto, session scope) | same |
| Alembic head | `037_payment_declarations_schema` | same |
| Second upgrade | no-op | no-op |

---

## 3. Exact Full-Gate Results

### Command (identical on both stacks)

```
poetry run pytest tests/ -q
```

Single pytest process, natural collection, no `--ignore`, `-k`, deselection, split pass, rerun, or exclusions.

### Stack A (port 56501/56401)

- **Collected:** 3183 items
- **EXIT_CODE:** 137 (SIGKILL — process hung at `test_platform_p21dd_runtime_storage_cutover_gate.py`)
- **Progress at termination:** 53%
- **Visible failures:** 60 failed, 16 errors (in the 53% that ran)

### Stack B (port 56502/56402)

- **Collected:** 3183 items
- **EXIT_CODE:** 137 (SIGKILL — hung at same test)
- **Progress at termination:** 53%
- **Visible failures:** identical pattern to Stack A (log files byte-for-byte identical through line 133)

### Identical Totals Check

Both Stack A and Stack B produced byte-for-byte identical `-q` output (10383 bytes, 133 lines) up to the kill point. Both hung at the same test (`test_platform_p21dd_runtime_storage_cutover_gate.py`) at 53%.

**Neither run exited 0. Neither run had failed=0 and errors=0.**

---

## 4. Failed/Error Node Classification

### 4.1 Failure Clusters (from `-q` output, both stacks identical)

| File | Line | Pattern | Approx. Failed | Approx. Errors |
|------|------|---------|----------------|----------------|
| `test_dc10e_export_worker_tenant_context.py` | 31 | `F.FF.F..` | 4 | 0 |
| `test_dc12r1_s3_s2b_i2a_canonical_payment_service.py` | 69-70 | `..FEEFEEFEEFEEFE` | 5 | 9 |
| `test_dc1g_retailer_registration_binding_balance.py` | 72 | `EFE` | 1 | 2 |
| `test_dc3b_credential_recovery_backend.py` | 76 | `EFFFFFFFFFFFFFFF` | 15 | 1 |
| `test_order_creation.py` | 84 | `FE` | 1 | 1 |
| `test_phase3_pricing.py` | 92 | `EFFFFFFFFF.F...EE` | 10 | 3 |
| `test_platform_p21_durable_approval_adapter_implementation.py` | 123-124 | `..FFFFFFFFFFFFFFFFF...` | 17 | 0 |
| `test_platform_p21dd_runtime_storage_cutover_gate.py` | 132-133 | `.....F...FFFFFFFFFFFFFFFFFFFFF.F.........` | 16 | 0 |

**Note:** Process killed before completion; tests after 53% did not run.

### 4.2 Failure Root Causes

**Cluster 1: dc10e (4 failed)**

- Error: `asyncpg.exceptions.UndefinedTableError: relation "mv_sales_daily" does not exist`
- Phase: query execution during test body
- Classification: fresh-database state issue (materialized view not created on a clean alembic-init'd database). Not I2A-related.

**Cluster 2: I2A suite (5 failed, 9 errors)**

- Error: `asyncpg.exceptions._base.InterfaceError: cannot perform operation: another operation in progress`
- Location: `asyncpg/protocol/protocol.pyx:735`
- Phase: `async_session` fixture setup/teardown
- See Section 5 for contamination evidence
- Classification: infrastructure contamination. I2A suite passes 11/11 in isolation.

**Clusters 3-8: dc1g, dc3b, order_creation, phase3_pricing, p21_adapter, p21dd**

- Same `InterfaceError` pattern (for post-r4r1 clusters)
- Classification: infrastructure contamination and/or fresh-database state issues

---

## 5. Event-Loop Contamination Evidence

### 5.1 Exact Reproduction

Contamination reproduces with a minimal 3-file subset:

```
pytest tests/test_dc11t4c_reporting_bootstrap_contract.py \
       tests/test_dc12r1_s3_s2b_i1_r4_r1_real_alembic_upgrade.py \
       tests/test_dc12r1_s3_s2b_i2a_canonical_payment_service.py
```

Result: **5 failed, 35 passed, 9 errors** (I2A suite corrupted).

### 5.2 Isolation Tests (all pass)

| Combination | Result |
|------------|--------|
| I2A alone | 11/11 PASS |
| dc11t2 + I2A | 25/25 PASS |
| dc11t4c + I2A | 15/15 PASS |
| dc11t4h + I2A | 24/24 PASS |
| r4r1 + I2A | 40/40 PASS |
| dc11t2 + r4r1 + I2A | 54/54 PASS |
| dc11t2 + dc11t4c + dc11t4h + I2A (no r4r1) | 42/42 PASS |
| **dc11t4c + r4r1 + I2A** | **5 failed, 9 errors** |

### 5.3 First Contaminating Predecessor

The contamination requires `test_dc11t4c_reporting_bootstrap_contract.py` to run before `test_dc12r1_s3_s2b_i1_r4_r1_real_alembic_upgrade.py`. Neither file alone contaminates; the combination does.

### 5.4 Exact Exception

```
asyncpg.exceptions._base.InterfaceError: cannot perform operation: another operation in progress
```

- Raised at: `asyncpg/protocol/protocol.pyx:735`
- Observed during: `async_session` fixture setup for I2A tests
- Call chain (from traceback): `sqlalchemy/dialects/postgresql/asyncpg.py:797` → `asyncpg _handle_exception` → `InterfaceError`

### 5.5 Causality Statement

No causal mechanism is inferred. The observed facts are:
1. `dc11t4c` then `r4r1` then `async_session`-dependent tests → `InterfaceError`
2. Any other ordering or subset → all pass
3. The exception occurs in asyncpg's protocol layer

---

## 6. Base SHA Attribution

### Command on base SHA `9528cb6`

```
poetry run pytest tests/ -q
```

(single process, same stack after drop/recreate/alembic)

### Result

- **Collected:** 3172 items (11 fewer than target — the I2A test file does not exist on base)
- **EXIT_CODE:** process killed (hung at same `test_platform_p21dd_runtime_storage_cutover_gate.py`)
- **Progress at termination:** 53%

### Diff: target vs base failure patterns

The failure clusters are nearly identical between target and base:
- dc10e: identical 4F pattern
- dc1g: `EFE` (target) vs `FEE` (base) — same 3 tests, different first outcome
- dc3b: `EFFFFFFFFFFFFFFF` (target) vs `FFFFFFFFFFFFFFFF` (base) — same 16 tests
- order_creation: `FE` both
- phase3_pricing: identical
- p21_adapter: identical
- p21dd: identical

**Target-only:** I2A suite (11 tests: 2 pass, 5 fail, 9 error) — does not exist on base.  
**Base-only:** 1 extra failure in `test_dc12r1_s1_r5_migration_preflight_exact_catalog.py` (line 56: trailing `F`).

The contamination pattern reproduces on base SHA. Per task instructions: **STOP_AND_REPORT_CTO is issued even though failures reproduce on base.**

---

## 7. Preserved Evidence

### 7.1 Alembic Sole Head 037 + Second-Upgrade No-Op

Both stacks: `037_payment_declarations_schema`. Second `alembic upgrade head` produces only `INFO [alembic.runtime.migration] Context impl PostgresqlImpl.` with no migration steps.

### 7.2 I2A Suite in Isolation

`pytest tests/test_dc12r1_s3_s2b_i2a_canonical_payment_service.py -q` → **11 passed**. All 11 tests pass when the suite runs in its own pytest process.

Test list:
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

### 7.3 Direct Service Invocation Fingerprints

Verified in isolation via I2A suite:
- Service does not call `commit()` or `rollback()` (test 2)
- `force_completed=True` forces "completed" status (test 9)
- Overpayment rejected with `PAYMENT_EXCEEDS_REMAINING` (test 8)
- Duplicate `transaction_id` rejected with `DUPLICATE_TRANSFER_REFERENCE` (test 6)
- Idempotent replay creates exactly one financial result (test 7)
- Failure injection at mutation stages rolls back all effects (test 11)

### 7.4 receipt_number Status

- Migration 037: creates `payments.receipt_number VARCHAR(32)` + partial unique index
- Bootstrap/reconcile: references `receipt_sequences` and `receipt_number`
- `models/payment_declaration.py:171`: defines `receipt_sequences` table model
- `services/`, `repositories/`, `api/`, `schemas/`, `models/payment.py`: **zero occurrences** — not yet read, allocated, written, or exposed

### 7.5 Security Scan

- `git diff --check`: CLEAN
- Secrets/keys in diff: NONE
- SQL injection patterns: NONE (all SQLAlchemy ORM)
- `eval`/`exec`/`os.system`: NONE

---

## 8. Verdict

### STOP_AND_REPORT_CTO

The exact full-gate command `poetry run pytest tests/ -q` fails on two independent fresh PostgreSQL 16 / Redis 7 stacks:
- EXIT_CODE=137 (process killed after hanging)
- 60+ failures and 16+ errors visible in the 53% that ran before termination
- Both stacks produce byte-for-byte identical failure patterns
- Same failures reproduce on base SHA `9528cb6` (not I2A-specific)
- Process hangs at `test_platform_p21dd_runtime_storage_cutover_gate.py` (53%)

The I2A extraction itself is not implicated: the I2A suite passes 11/11 in isolation, and the contamination pattern reproduces identically on the base SHA where the I2A code does not exist.

---

## Appendix A: DIAGNOSTIC_ONLY_NON_AUTHORITATIVE

The following evidence was gathered in the prior report using a two-pass split-run strategy. It is **not authoritative** for the exact gate and is retained only as diagnostic context.

### A.1 Prior Split-Run Results (Target SHA)

A two-pass approach was used:
- Pass A: 3022 tests (excluding 11 files that interact with the event loop)
- Pass B: 161 tests (the 11 files, run in isolated Python processes)

Both passes reported 0 failures. However, this strategy violates the exact gate requirement of a single `pytest tests/ -q` process with no exclusions.

### A.2 Prior Affected Bundle Results

20-file affected financial bundle run in both natural and reverse orders. All passed when migration-test files were separated from async-session files. This evidence is diagnostic only.

### A.3 Prior Base Comparison

The contamination pattern was confirmed on base SHA in the prior report using the same split-run strategy. This is consistent with the exact-gate base comparison in Section 6.
