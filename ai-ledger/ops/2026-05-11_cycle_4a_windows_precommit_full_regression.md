---
title: Cycle 4A Windows Pre-Commit Full Regression
date: 2026-05-11
validator: Claude (Windows / GLM-5.1)
branch: ops/integration-rehearsal-clean-2026-05-08
head: 14ccc29
verdict: PRECOMMIT_BLOCKED_BY_KNOWN_ENV_OR_HARNESS
---

# Cycle 4A Windows Pre-Commit Full Regression

## 1. Git State

| Item              | Value                                                            |
|-------------------|------------------------------------------------------------------|
| Branch            | `ops/integration-rehearsal-clean-2026-05-08`                     |
| HEAD              | `14ccc29`                                                        |
| Staged            | `A  ai-ledger/ops/2026-05-11_claude_windows_full_regression_validation.md` |
| Unstaged (dirty)  | ` M backend/scripts/bootstrap_tenant_schema.py`                  |
| Untracked         | `?? resolve_conflict.py`, `?? ai-ledger/ops/2026-05-11_cycle_4a_tenant_schema_lifecycle_triage.md` |

## 2. Alembic Head

```
021_tenant_payments_retailer_id_transaction_id (head)
```

Single head. No multiple-heads issue.

## 3. py_compile

```
poetry run python -m py_compile scripts/bootstrap_tenant_schema.py
PY_COMPILE_OK
```

## 4. Schema Contract

```
poetry run pytest tests/test_payments_schema_contract.py -q --tb=short
14 passed, 0 failed, 1 warning (0.80s)
```

## 5. Payment Targeted

```
poetry run pytest tests/test_payments_api.py tests/test_payment_atomicity.py
    tests/test_phase5_order_payment.py -q --tb=short
53 passed, 1 xfailed, 0 failed, 41 warnings (1.99s)
```

## 6. Full Pytest

```
poetry run pytest -q --tb=short
```

| Metric   | Count |
|----------|-------|
| collected| 828   |
| passed   | 798   |
| failed   | 11    |
| errors   | 1     |
| skipped  | 8     |
| xfailed  | 10    |
| warnings | 1239  |
| time     | 132.32s |

## 7. Failure Classification

| #  | Test                                                                                  | Classification          | Root Cause                                         |
|----|---------------------------------------------------------------------------------------|-------------------------|----------------------------------------------------|
| 1  | `test_b5_real_db::test_cash_payment`                                                  | legacy B5 seed          | No PG seed data on Windows                         |
| 2  | `test_b5_real_db::test_idempotency_violation`                                         | legacy B5 seed          | No PG seed data + event loop                       |
| 3  | `test_b5_real_db::test_idempotent_replay`                                             | legacy B5 seed          | No PG seed data on Windows                         |
| 4  | `test_b5_real_db::test_transfer_payment_first`                                        | legacy B5 seed          | No PG seed data + event loop                       |
| 5  | `test_b6_payment_atomicity::test_b6_create_payment_rollback_on_balance_update_failure`| test harness            | Async mock recorder not firing                     |
| 6  | `test_request_validation::test_login_rejects_missing_email`                           | test harness            | Passes in isolation; event loop pollution          |
| 7  | `test_request_validation::test_login_rejects_invalid_email`                           | test harness            | Passes in isolation; event loop pollution          |
| 8  | `test_request_validation::test_login_rejects_short_password`                          | test harness            | Passes in isolation; event loop pollution          |
| 9  | `test_s4_jobs_local::test_enqueue_job`                                                | test harness            | Passes in isolation; event loop pollution          |
| 10 | `test_s6_2_materialized_views::test_mv_sales_daily_accessible_by_reporting_user`      | environment dependency  | socket.gaierror: no PostgreSQL on Windows          |
| 11 | `test_s6_3_dashboard_api::test_query_builder_reporting_user_access`                   | environment dependency  | socket.gaierror: no PostgreSQL on Windows          |
| E1 | `test_order_creation::test_create_order_in_t_test`                                    | test harness            | Passes in isolation; event loop pollution          |

## 8. Risk Signal Scan

| Signal                      | Count | Detail                                     |
|-----------------------------|-------|--------------------------------------------|
| `UndefinedColumnError`      | 0     | None detected                              |
| `socket.gaierror`           | 2     | s6 tests (expected -- no PG on Windows)    |
| `search_path`               | 1     | Mention only, no error or leak             |
| `reporting_user`            | 2     | s6 test names (same failures as gaierror)  |
| `Event loop is closed`      | 8     | B5 + harness tests (known)                 |
| `retailer_id`               | 0     | None in test output                        |
| `transaction_id`            | 0     | None in test output                        |
| `mv_sales_daily`            | 1     | Test name only                             |
| `rpt_receivables_summary`   | 0     | None detected                              |

## 9. Diff Attribution

The unstaged `bootstrap_tenant_schema.py` diff:

1. **Standalone script** (`scripts/`) -- not imported by app or test code.
2. Adds `_reconcile_payments` + `_reconcile_reporting` async functions that only execute against a live PG connection.
3. Replaces inline payment index DDL with reconciled version.

**None of the 11 failures + 1 error are introduced by this diff.** The failure set is identical to the pre-diff baseline verified across 3 consecutive runs (Claude full regression, Cycle 4A initial, and this run).

## 10. Conclusion

```
PRECOMMIT_BLOCKED_BY_KNOWN_ENV_OR_HARNESS
```

The diff itself is clean -- py_compile passes, zero test regressions, zero new risk signals. All failures are pre-existing environment/harness issues unrelated to `bootstrap_tenant_schema.py`. The diff is safe to commit, but formal promotion clearance should follow Lubuntu/DB-capable cross-validation.
