# DC-10L Independent Cross-Environment DB Validation

**Date:** 2026-07-14
**Validator:** Leo (Lubuntu independent)
**Target branch:** `origin/codex/dc10l-order-status-enum-reconciliation-2026-07-14`
**Target SHA:** `b88ec3aa2a4aa138b4e8d9079a930e297999cf92`
**Base branch:** `origin/product-dev-recovered`
**Base SHA:** `280c5629ee46efbcb9b890c105320bfdac8bc694`
**PostgreSQL version:** 16 (disposable Docker container)

---

## Preflight

| Check | Result |
|-------|--------|
| V1: HEAD == `b88ec3a` | PASS |
| V2: Merge-base == `280c562` (expected base) | PASS |
| V3: Clean worktree, 4 changed files | PASS |
| V4: Historical migrations 001-032 unmodified | PASS |

### Changed files (verified)

1. `backend/alembic/versions/033_order_status_enum_reconciliation.py`
2. `backend/scripts/bootstrap_tenant_schema.py`
3. `backend/tests/test_dc10l_order_status_enum_reconciliation.py`
4. `ai-ledger/product-ai/2026-07-14_dc10l_order_status_enum_reconciliation.md`

No unexpected files. No files outside intended scope.

---

## V1: Target DB-Backed Gate (8 tests)

```
poetry run pytest tests/test_dc10l_order_status_enum_reconciliation.py -q
```

**Result: 8 passed in 4.34s**

Evidence of legacy failure-before and success-after:
- `test_migration_closes_real_finance_enum_coercion_failure_and_is_idempotent` — reproduces `invalid input value for enum order_status: "paid"`, migration 033 adds canonical statuses, ReceivablesService succeeds after, second run is idempotent.
- `test_preflight_failure_prevents_partial_enum_mutation_across_tenants` — one bad tenant blocks all mutation.
- `test_unregistered_and_inactive_tenant_schemas_are_not_mutated` — unregistered/inactive schemas untouched.
- `test_wrong_order_status_column_type_fails_closed` — wrong column type rejected.
- `test_fresh_bootstrap_creates_complete_order_status_enum` — fresh bootstrap creates full canonical enum.
- `test_bootstrap_reconciles_existing_legacy_order_status_enum` — legacy enum reconciled to canonical.
- `test_bootstrap_rejects_wrong_order_status_type_without_creating_enum` — VARCHAR column correctly rejected.

**Note:** Initial run of bootstrap tests (2 failures) was due to missing `reporting_role` in test DB. After running full `alembic upgrade head` (which creates the role via migration 011), all 8 tests passed. This is a test-environment prerequisite ordering issue, not a code defect.

---

## V2: Finance Regression (40 tests)

```
poetry run pytest tests/test_dc10k_finance_receivables_runtime.py tests/test_finance_receivables_api.py tests/test_receivables_service.py -q
```

**Result: 40 passed in 3.66s**

All DC-10K finance receivables tests remain stable after DC-10L migration.

---

## V3: Order/Payment Regression (73 tests)

```
poetry run pytest tests/test_phase5_order_payment.py tests/test_s5d4b_settled_cash_payment.py tests/test_s5d5_payment_ledger_runtime_invariant.py tests/test_s5d6_multi_partial_payment_state_machine.py -q
```

**Result: 72 passed, 1 xfailed in 9.55s**

XFail is pre-existing (route-level monkeypatch brittleness), not caused by DC-10L.

---

## V4: Migration/Bootstrap Regression (46 tests)

```
poetry run pytest tests/test_dc2m2_legacy_tenant_reconciliation_forward_migration.py tests/test_dc10f_r1_payment_method_migration.py tests/test_u1_bootstrap_permission_completeness.py tests/test_s4g_migration_infrastructure_hardening.py -q
```

**Result: 46 passed in 8.15s**

**Note:** s4g tests initially failed due to default `POSTGRES_PORT=5432` vs our test container on port 5438. After setting `POSTGRES_PORT=5438`, all 5 s4g tests passed. This is test-environment configuration, not a code defect.

---

## Alembic

| Check | Result |
|-------|--------|
| `alembic heads` | `033_order_status_enum_reconciliation` (exactly one) |
| `alembic upgrade head` on fresh DB | All 33 migrations applied successfully |
| `alembic current` | `033_order_status_enum_reconciliation` |

Migration 033 imports no runtime models — confirmed by code inspection.

---

## Static/Security Checks

| Check | Result |
|-------|--------|
| `git diff --check` (whitespace) | PASS — no issues |
| Migration 033 runtime model imports | PASS — none found |
| UTF-8 / mojibake scan | PASS — all 4 files are valid UTF-8 |
| Secret scan (password/token/key patterns) | PASS — no hardcoded secrets |
| Email exposure scan | PASS — no real emails |
| DB URL exposure | PASS — only code template placeholder (`postgresql://...`) in bootstrap script docstring |
| Full Alembic migration chain (001-033) | PASS — clean upgrade on fresh DB |

---

## Hard Stops — All Clear

- No DB-backed assertion failures.
- No multiple Alembic heads.
- Migration does not modify unregistered/inactive schemas.
- No partial mutation when any live tenant fails preflight.
- Finance service no longer raises enum coercion error after migration.
- No unexpected changed files.
- No secret exposure.

---

## P0 Findings

None.

## P1 Findings

None.

## P2 Findings

1. **Bootstrap test environment fragility:** The 2 bootstrap tests (`test_fresh_bootstrap_creates_complete_order_status_enum`, `test_bootstrap_reconciles_existing_legacy_order_status_enum`) require the `reporting_role` to exist (created by migration 011). When tests run without a full migration chain pre-applied, they fail with `RuntimeError: reporting_role does not exist`. The tests call `_ensure_public_prerequisites()` which only creates `pgcrypto` + public tables, not the full migration chain. **Recommendation:** Either add `reporting_role` creation to the test's `_ensure_public_prerequisites`, or document that full migration chain must be applied before bootstrap tests.

---

## Cleanup Confirmation

| Resource | Status |
|----------|--------|
| Docker container `dc10l-postgres` | Removed |
| Worktree `/tmp/dc10l-worktree` | Removed |
| Disposable DB data | Destroyed with container |

---

## Summary

| Suite | Expected | Actual | Status |
|-------|----------|--------|--------|
| V1: DC-10L target gate | 8 passed | **8 passed** | PASS |
| V2: Finance regression | 40 passed | **40 passed** | PASS |
| V3: Order/payment regression | 72 passed, 1 xfailed | **72 passed, 1 xfailed** | PASS |
| V4: Migration/bootstrap regression | 46 passed | **46 passed** | PASS |
| Alembic head/current | 033 | **033** | PASS |
| Static/security | All clear | **All clear** | PASS |
| **Total** | 166 passed, 1 xfailed | **166 passed, 1 xfailed** | **PASS** |

---

## Verdict

**PASS_FOR_CTO_DC10L_MERGE_REVIEW**

The DC-10L migration correctly reconciles legacy `order_status` enums across all registered tenant schemas, closes the Finance enum coercion failure, and maintains full backward compatibility with the existing test suite. The P2 finding on bootstrap test environment fragility is advisory and does not block merge.
