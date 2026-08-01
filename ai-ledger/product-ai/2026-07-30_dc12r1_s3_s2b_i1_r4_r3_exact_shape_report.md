# DC-12R1-S3-S2B-I1-R4-R3: Exact Catalog Shape + Uniform Alembic Evidence

> **⚠ CORRECTED by R4-R3-R1** — This report's test count (78/78) was
> inaccurate due to a merged class and a false "1+1 folded to 1" claim.
> R4-R3-R1 restores `TestTwoRegisteredTenantsUpgrade`, adds the
> `next_seq DEFAULT (1+0)` test, replaces all `pytest.skip` with fail-closed
> assertions, and adds exception-chain proof. Corrected count: **79 collected,
> 79 passed, 0 failed, 0 errors, 0 skipped, 0 xfailed**.
> See `2026-07-30_dc12r1_s3_s2b_i1_r4_r3_r1_final_report.md`.

**Date**: 2026-08-01
**Branch**: `codex/dc12r1-s3-s2b-i1-financial-schema-foundation-2026-07-31`
**Status**: CORRECTED — see R4-R3-R1
**Parent**: DC-12R1-S3-S2B-I1-R4-R2 (SUPERSEDED)

---

## 1. Summary

R4-R2 left residual shape-matching weaknesses: CHECK validation approved
expressions whose column/literal sets matched but whose boolean structure
differed (extra AND/OR, non-equivalent operators). Types used `in`/`startswith`
matching. Defaults used broad cast-stripping regex. FK/PK checked only `conkey[0]`
and hardcoded attnum positions. Index validation filtered out expression keys
(attnum 0) silently.

R4-R3 closes every residual by building the **exact PG16 canonical expression**
and comparing normalised form byte-for-byte.

---

## 2. Corrections

### 2.1 CHECK — Exact Canonical Expression Shape

| Check | Method |
|-------|--------|
| method IN ('cash','transfer') | `_build_canonical_any_expr` builds the exact PG16 `= ANY(ARRAY[...])` string; `_normalize_expr` normalises; compared by `==` |
| status IN ('pending','confirmed','rejected') | Same canonical builder |
| declared_amount > 0 | Exact `(declared_amount > (0)::numeric)` comparison |

**Rejects**: extra AND condition, OR 1=1, amount range (AND < 10), `<>` chains,
`NOT IN`, alternate operators, non-equivalent shapes.

### 2.2 Types — `format_type` Exact Equality

Removed all `in`/`startswith` matching. Every column type compared by `==`
against the expected `format_type` output.

### 2.3 Defaults — Anchored Canonical Allowlist

`_normalize_default` no longer strips type casts. Instead, anchored allowlists
of exact PG16 expressions:
- `_STATUS_DEFAULT_CANONICAL = {"'pending'::character varying"}`
- `_NEXT_SEQ_DEFAULT_CANONICAL = {"1"}`

Rejects computed defaults (`concat('pending','')`), trailing-space variants,
type-cast variants.

### 2.4 FK — Complete Vector Resolution, No Hardcoded Attnums

- `conkey`/`confkey` resolved to column **names** via `_attnum_map`
- Require `len(conkey) == 1` and `len(confkey) == 1` (rejects composite FK)
- `confdeltype` handled as both `str` and `bytes` (`b'r'` vs `'r'`)
- Referenced column name verified from target table's attnum map

### 2.5 PK — Exactly One Column

- `conkey` must be exactly `[business_date]` (rejects composite PK)

### 2.6 Index — `indnatts`/`indnkeyatts`/Expression Keys

- `indkey` entries with attnum 0 (expression columns) flagged as `<expr>` and rejected
- `indnatts != indnkeyatts` → INCLUDE columns rejected
- Every `indkey` entry validated against expected ordered column names
- `indpred` compared by exact normalised `pg_get_expr` (including outer parens)

---

## 3. Tests (8 Mandatory Bypass Cases)

All in `TestExactCatalogShapeBypass` with full RED→GREEN→no-op protocol:

| # | Test | Bypass |
|---|------|--------|
| 1 | `test_check_extra_and_condition_rejected` | status IN (...) AND status IS NOT NULL |
| 2 | `test_amount_range_constraint_rejected` | amount > 0 AND amount < 10 |
| 3 | `test_index_expression_key_rejected` | Index with (retailer_id, status, (id::text)) |
| 4 | `test_composite_fk_rejected` | Composite FK (order_id, wholesaler_id) → orders(id, wholesaler_id) |
| 5 | `test_composite_pk_rejected` | Composite PK (business_date, next_seq) |
| 6 | `test_prefix_compatible_wrong_type_rejected` | reason VARCHAR(160) (prefix-compatible, wrong length) |
| 7 | `test_computed_status_default_rejected` | DEFAULT concat('pending', '') |
| 8 | `test_next_seq_computed_default_rejected` (added in R4-R3-R1) | DEFAULT (1 + 0) — PG stores as `(1 + 0)`, not folded to `1`; correctly rejected by anchored allowlist |

Every test: 036 start → malform → fingerprint → upgrade fails (PreflightFailure) →
version=036 → fingerprint unchanged → repair → upgrade to 037 → second no-op.

---

## 4. Evidence Integrity

- Capability matrix: **46 FIND rows** (unchanged)
- Failed/error CSV: **header-only** (red=0, gap=0)
- R4-R2 report marked **SUPERSEDED**

---

## 5. Validation Results (NON-AUTHORITATIVE — corrected by R4-R3-R1/R4-R3-R2)

> The accounting below was produced before R4-R3-R1 added the
> `next_seq DEFAULT (1+0)` test, restored `TestTwoRegisteredTenantsUpgrade`
> as a separate class, and added exception-chain proof.
> It is preserved here as a historical record only.
> **Authoritative accounting**: see R4-R3-R2 final report.

### Historical (stale) run

```
78 passed in 139.63s
```

### Corrected per-class breakdown (authoritative)

| Class | Tests |
|-------|-------|
| R2 `financial_schema_foundation` | 36 |
| R3 `r3_migration_preflight` | 14 |
| `TestRealAlembicUpgradeFailClosed` | 20 |
| `TestExactCatalogShapeBypass` | 8 |
| `TestTwoRegisteredTenantsUpgrade` | 1 |
| **Total collected** | **79** |
| **Passed** | **79** |
| **Failed / Errors / Skipped / Xfailed** | **0 / 0 / 0 / 0** |

---

## 6. Verdict (SUPERSEDED)

> **PASS_FOR_CTO_DC12R1_S3_S2B_I1_R4_R3_MERGE_REVIEW** — issued at commit
> `f4d8fce0`. Superseded by R4-R3-R1 (`5bcb8f60`) and R4-R3-R2 which corrected
> the accounting from 78 to 79 and added exception-chain proof.
>
> **Current authoritative verdict**:
> `PASS_FOR_CTO_DC12R1_S3_S2B_I1_R4_R3_R2_FINAL_MERGE_REVIEW`
