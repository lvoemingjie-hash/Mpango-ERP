# DC-12R1-S3-S2B-I1-R4-R3-R2: Final Report Accounting Closeout

**Date**: 2026-08-01
**Branch**: `codex/dc12r1-s3-s2b-i1-financial-schema-foundation-2026-07-31`
**Tip**: `5bcb8f60`
**Scope**: Docs-only. No migration, model, test, config, or dependency changes.

---

## 1. Corrected Accounting

| File | Class | Tests |
|------|-------|-------|
| `test_dc12r1_s3_s2b_i1_financial_schema_foundation.py` | (R2) | 36 |
| `test_dc12r1_s3_s2b_i1_r3_migration_preflight.py` | (R3) | 14 |
| `test_dc12r1_s3_s2b_i1_r4_r1_real_alembic_upgrade.py` | `TestRealAlembicUpgradeFailClosed` | 20 |
| | `TestExactCatalogShapeBypass` | 8 |
| | `TestTwoRegisteredTenantsUpgrade` | 1 |
| **Total collected** | | **79** |

Independent collection proof:

```
========================= 79 tests collected in 0.87s =========================
```

---

## 2. R4-R3 Report Corrections

The R4-R3 report (`2026-07-30_dc12r1_s3_s2b_i1_r4_r3_exact_shape_report.md`)
contained two errors:

1. **Stale 78/shared-fixture accounting** — claimed "78 passed" with a
   parenthetical excuse about a shared fixture. Corrected to **79 collected,
   79 passed**. The stale block is preserved under an explicit
   `NON-AUTHORITATIVE` heading.

2. **Obsolete verdict** — `PASS_FOR_CTO_DC12R1_S3_S2B_I1_R4_R3_MERGE_REVIEW`
   is now marked `SUPERSEDED` with a pointer to the current authoritative
   verdict.

3. **Per-class count error** — `TestRealAlembicUpgradeFailClosed` was listed
   as 19 in R4-R3-R1; corrected to **20** (verified by `pytest --co`).

---

## 3. Evidence Chain

| Report | Status |
|--------|--------|
| R4-R2 `r4_r2_catalog_semantics_report.md` | **SUPERSEDED** |
| R4-R3 `r4_r3_exact_shape_report.md` | **CORRECTED** (stale accounting under NON-AUTHORITATIVE block; verdict SUPERSEDED) |
| R4-R3-R1 `r4_r3_r1_final_report.md` | **CORRECTED** (per-class count 19→20) |
| R4-R3-R2 `r4_r3_r2_final_report.md` | **AUTHORITATIVE** (this report) |

Capability matrix: **46 FIND rows**. Failed/error CSV: **header-only** (red=0, gap=0).

---

## 4. Verdict

**PASS_FOR_CTO_DC12R1_S3_S2B_I1_R4_R3_R2_FINAL_MERGE_REVIEW**
