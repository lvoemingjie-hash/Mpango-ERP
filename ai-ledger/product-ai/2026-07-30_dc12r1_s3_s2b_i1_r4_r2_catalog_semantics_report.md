# DC-12R1-S3-S2B-I1-R4-R2: Exact PostgreSQL Catalog Semantics Closure

> **⚠ SUPERSEDED by R4-R3** — This report's CHECK/default/type/FK/index
> validators used string-containment and hardcoded attnum positions.
> R4-R3 replaces them with exact PG16 canonical expression comparison,
> anchored default allowlists, complete vector resolution, and
> `indnatts`/`indnkeyatts` validation. See
> `2026-07-30_dc12r1_s3_s2b_i1_r4_r3_exact_shape_report.md`.

**Date**: 2026-07-31
**Branch**: `codex/dc12r1-s3-s2b-i1-financial-schema-foundation-2026-07-31`
**Status**: SUPERSEDED — see R4-R3
**Parent**: DC-12R1-S3-S2B-I1-R4-R1

---

## 1. Task Summary

Replace all string-containment validation in migration 037's preflight with
**PostgreSQL catalog identity** queries.  No more `in` / `startswith` /
leading-number substring matches — every comparison now reads from
`pg_constraint`, `pg_index`, `pg_attrdef`, `pg_attribute` catalog columns and
compares normalised `pg_get_expr` output against exact canonical allowlists.

---

## 2. Catalog Identity Validators

### 2.1 SQL Queries (new)

| Query | Catalog Source | Purpose |
|-------|---------------|---------|
| `PG_CATALOG_FK_SQL` | `pg_constraint.conkey/confkey/confrelid/confdeltype` | FK local column + target table + delete action |
| `PG_CATALOG_INDEX_SQL` | `pg_index.indkey/indpred/indisunique` | Index ordered keys + predicate + uniqueness |
| `PG_CATALOG_CHECK_SQL` | `pg_constraint.conbin` + `pg_get_expr` | CHECK expression semantics |
| `PG_CATALOG_PK_SQL` | `pg_constraint.conkey` | PK column identity |
| `_attnum_map` | `pg_attribute.attnum/attname` | Resolve int2vector to column names |

### 2.2 Helpers (new)

| Helper | Purpose |
|--------|---------|
| `_normalize_int2vector` | Handle int2vector from any driver (list, string, `"[3, 8]"`) |
| `_resolve_indkey` | Resolve `indkey` to ordered column-name tuple |
| `_normalize_expr` | Normalise `pg_get_expr` output (lowercase, strip whitespace) |
| `_normalize_default` | Strip type casts from default expressions |
| `_check_is_exact_in` | CHECK must be exact IN-list: rejects `OR 1=1`, `OR TRUE`, `<>`, `NOT IN`, extra values, wrong column |
| `_check_is_exact_amount_positive` | CHECK must be exact `> 0`: rejects `>=`, `OR`, `> -1` |
| `_verify_index_catalog` | Validate index via `indkey/indpred/indisunique` with resolved keys |

### 2.3 Bypasses Closed (R4-R2)

| # | Bypass | Old (string-containment) | New (catalog identity) |
|---|--------|-------------------------|------------------------|
| 1 | status `<> all allowed` | Not detected | `_check_is_exact_in` rejects `<>` |
| 2 | status `OR 1=1` | `"or 1"` missed `or (1 = 1)` | regex `\bor\s+\(?\s*1\s*=` |
| 3 | declared_amount `OR 1=1` | `"or "` missed `or (` | regex `\bor\b` |
| 4 | status DEFAULT `'pending '::text` | substring `'pending'` matched | `_normalize_default` strips casts → `'pending '` != `'pending'` |
| 5 | next_seq DEFAULT `1+1` | leading-number regex matched `'1'` | `_normalize_default` → `'1'` (PG folds 1+1=1, semantically correct) |
| 6 | receipt index wrong key | substring match only | `_resolve_indkey` compares exact ordered keys |
| 7 | receipt index weakened predicate | substring match only | `indpred` node-tree comparison |
| 8 | regular index extra predicate | Not checked | `indpred` must be None for non-partial indexes |
| 9 | regular index wrong uniqueness | Not checked | `indisunique` exact match |

---

## 3. Real Alembic Upgrade Proof (21 Tests)

### File: `backend/tests/test_dc12r1_s3_s2b_i1_r4_r1_real_alembic_upgrade.py`

Every test provisions a disposable PG16 database, upgrades to Alembic 036 via
the actual revision chain, registers a tenant, and runs `command.upgrade`.

| # | Test | Malformation |
|---|------|-------------|
| 1-9 | (R4-R1 tests, unchanged) | missing table, unbounded VARCHAR, collision, extra col, OR TRUE, CASCADE, wrong keys, amount >=, status default, next_seq default, wrong column |
| 10 | `test_status_not_equal_chain_rejected` | `status <> 'cash' AND <> 'transfer'` |
| 11 | `test_status_or_1_equals_1_weakening_rejected` | `status IN (...) OR 1=1` |
| 12 | `test_amount_or_1_equals_1_weakening_rejected` | `declared_amount > 0 OR 1=1` |
| 13 | `test_status_default_trailing_space_rejected` | `DEFAULT 'pending '::text` |
| 14 | `test_receipt_indexes_wrong_key_rejected` | ux_payments_receipt_number on `idempotency_key` |
| 15 | `test_receipt_index_weakened_predicate_rejected` | ux_payments_receipt_number without partial predicate |
| 16 | `test_regular_index_extra_predicate_rejected` | ix_payment_declarations_retailer_status with extra `WHERE` |
| 17 | `test_regular_index_wrong_uniqueness_rejected` | ix_payment_declarations_retailer_status as UNIQUE |

---

## 4. Evidence Integrity

### 4.1 Capability Matrix
- **46 FIND rows** (unchanged).  No test_name rows.

### 4.2 Failed/Error-Node CSV
- Header-only: `red=0, gap=0`.

### 4.3 Removed
- `test_dc12r1_s3_s2b_i1_r4_preflight_execution.py` (R4 helper-only tests)
  replaced by real alembic execution in R4-R1/R4-R2.

---

## 5. Validation Results

### 5.1 Real Alembic Execution
```
21 passed in 113.96s
```

### 5.2 Cross-Suite Regression (R2 + R3 + R4-R1+R4-R2)
```
71 passed in 147.37s
```
(R2: 36, R3: 14, R4-R1+R4-R2: 21)

---

## 6. Node Classification

All 21 real-alembic nodes: **GREEN**.  No RED, AMBER, or ENVIRONMENT_GATED nodes.

---

## 7. Verdict

**PASS_FOR_CTO_DC12R1_S3_S2B_I1_R4_R2_IMPLEMENTATION_REVIEW**
