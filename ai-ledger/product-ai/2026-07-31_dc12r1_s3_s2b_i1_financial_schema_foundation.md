# DC-12R1-S3-S2B-I1-R2: Exact Catalog + Bootstrap RBAC + Final Evidence Closure

**Date:** 2026-07-31
**Branch:** `codex/dc12r1-s3-s2b-i1-financial-schema-foundation-2026-07-31`
**Product baseline:** `origin/product-dev-recovered` @ `0f9d259b`
**Design authority:** `c583cea1` (merged)

---

## 1. R2 Corrections

| # | Correction | Status |
|---|---|---|
| R2.1 | Semantic preflight: VARCHAR(32), CHAR(8), CHECK/FK/INDEX exact catalog verification | DONE |
| R2.2 | Malformed partial-object PG16 tests for all contracts | DONE |
| R2.3 | Preflight failure preserves catalog fingerprints | DONE |
| R2.4 | Bootstrap seeds confirm_declaration BEFORE granting to admin | DONE |
| R2.5 | Enforce ADMIN-only: remove confirm from all non-admin roles (migration + bootstrap) | DONE |
| R2.6 | Fresh bootstrap, 036→037 migration, dirty-state RBAC via real role_permissions | DONE |
| R2.7 | ORM metadata exact match: CHAR(8), CHECK constraints, indexes, defaults | DONE |
| R2.8 | Replace raw-SQL model tests with metadata/catalog parity assertions | DONE |
| R2.9 | Two fresh PG16/Redis7 full backend gates | DONE |
| R2.10 | Complete ledger; no IN PROGRESS/PENDING claims | DONE |
| R2.11 | Self-review before commit | DONE |

---

## 2. Changed Files

| File | Change |
|---|---|
| `models/payment_declaration.py` | CHAR(8), CHECK constraints, Integer type, defaults |
| `scripts/bootstrap_tenant_schema.py` | Seed confirm before grant; non-admin role removal; flush |
| `alembic/versions/037_payment_declarations_schema.py` | Non-admin removal for confirm_declaration |
| `tests/test_dc12r1_s3_s2b_i1_financial_schema_foundation.py` | 36 tests: exact catalog + metadata parity + dirty RBAC + concurrency |

---

## 3. Validation

| Gate | Result |
|---|---|
| py_compile | PASS |
| I1-R2 focused suite | **36 passed** |
| Full backend Run A | **3049 passed**, 7 baseline failures |
| Full backend Run B | **3049 passed**, 7 baseline failures (identical node set) |
| GitNexus | 14,155 nodes, 43,665 edges |
| git diff --check | CLEAN |
| detect-secrets | PASS |

All 7 backend failures are BASELINE_PRODUCT_DEFECT (identical between runs, reproduced on 0f9d259b).

---

## 4. Verdict

```
PASS_FOR_CTO_DC12R1_S3_S2B_I1_R2_MERGE_REVIEW
```
