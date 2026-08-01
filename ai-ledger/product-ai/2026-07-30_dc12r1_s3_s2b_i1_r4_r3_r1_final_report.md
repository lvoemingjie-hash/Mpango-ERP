# DC-12R1-S3-S2B-I1-R4-R3-R1: Evidence Integrity Final Closure

**Date**: 2026-08-01
**Branch**: `codex/dc12r1-s3-s2b-i1-financial-schema-foundation-2026-07-31`
**Status**: PASS — 79 collected, 79 passed, 0 failed, 0 errors, 0 skipped, 0 xfailed
**Parent**: DC-12R1-S3-S2B-I1-R4-R3 (CORRECTED)

---

## 1. Corrections Applied

### 1.1 pytest.skip → fail-closed assertions

Every `pytest.skip(...)` in the real-Alembic evidence file replaced with
`_require_test_env()` which raises `AssertionError` on missing prerequisites.
No test can be silently skipped — a missing environment is a configuration error.

### 1.2 Exception-chain helper

New `_assert_preflight_failure(exc_info, root_cause_substr)` walks the
`__cause__`/`__context__` chain and asserts `PreflightFailure` is present.
A bare `RuntimeError` with a message substring is no longer sufficient.

All 29 malformed-upgrade assertions now use this helper.

### 1.3 next_seq DEFAULT (1 + 0) test

PG16 stores `DEFAULT (1 + 0)` as `'(1 + 0)'` — it is NOT constant-folded
to `'1'`. The anchored allowlist `{ "1" }` correctly rejects it.

Full RED→GREEN→no-op protocol verified.

### 1.4 TestTwoRegisteredTenantsUpgrade restored

The cross-tenant test was accidentally merged into `TestExactCatalogShapeBypass`
during R4-R3 editing. Restored as a separate class.

---

## 2. Exact Test Accounting

| File | Class | Tests |
|------|-------|-------|
| `test_dc12r1_s3_s2b_i1_financial_schema_foundation.py` | (R2) | 36 |
| `test_dc12r1_s3_s2b_i1_r3_migration_preflight.py` | (R3) | 14 |
| `test_dc12r1_s3_s2b_i1_r4_r1_real_alembic_upgrade.py` | `TestRealAlembicUpgradeFailClosed` | 20 |
| | `TestExactCatalogShapeBypass` | 8 |
| | `TestTwoRegisteredTenantsUpgrade` | 1 |
| **Total collected** | | **79** |
| **Passed** | | **79** |
| **Failed** | | **0** |
| **Errors** | | **0** |
| **Skipped** | | **0** |
| **Xfailed** | | **0** |

gap=0.

---

## 3. Evidence Integrity

- Capability matrix: **46 FIND rows** (unchanged)
- Failed/error CSV: **header-only** (red=0)
- R4-R2 report: **SUPERSEDED**
- R4-R3 report: **CORRECTED** (false "1+1 folded" removed, count corrected)

---

## 4. Verdict

**PASS_FOR_CTO_DC12R1_S3_S2B_I1_R4_R3_R1_FINAL_MERGE_REVIEW**
