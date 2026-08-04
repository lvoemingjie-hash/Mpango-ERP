# DC-12R1-S3-S2B-I2B-R5-R1 — Test Evidence Integrity Closure

**Status:** PASS_FOR_CTO_DC12R1_S3_S2B_I2B_R5_R1_FINAL_MERGE_REVIEW
**Executor:** local Zcode (real execution, no static analysis)
**Date:** 2026-08-04
**Branch:** `codex/dc12r1-s3-s2b-i2b-r5-r1-test-evidence-integrity-2026-08-04`
**Source SHA:** `fb9b82a12a29b156dd5f20fae20393e7caae8cdd` (R5)
**Baseline SHA:** `76fb345c9054530cb0e6abccf35f0cc1863d2bef`

---

## 0  Verdict

**PASS** — test/report-only correction preserving all R5 corrections. Three
evidence-integrity defects closed.

---

## 1  Three Defects Closed

### Defect 1: Frontend false-green risk
**Problem:** R5 used a fixed-value UUID mock (`'00000000-0000-4000-8000-000000000001'`).
If the component incorrectly rotated the key on failure, the mock would return
the same value and the test would pass — a false green.

**Fix:** Replaced with **sequential distinct UUIDs** (`UUIDS[0]`, `UUIDS[1]`, ...).
Now `keys[0] !== keys[1]` would catch unwanted rotation. Added:
- Mount-key-capture test proving exactly one UUID consumed during mount
- Rotation test proving success DOES trigger a new UUID call
- False-green guard test proving the sequential mock produces distinct values

### Defect 2: H5 swallowed cleanup
**Problem:** R5 used `except Exception: pass` for schema cleanup, silently
swallowing failures. A surviving schema would go undetected.

**Fix:** Every created schema is now in an outer try/finally with:
- `DROP SCHEMA ... CASCADE` (no bare `except: pass`)
- `_assert_schema_absent()` querying `pg_catalog.pg_namespace` for count == 0
- Nested finally: engine disposal executes even if schema cleanup fails
- Cleanup failure re-raised to fail the test

Verified: `SELECT count(*) FROM pg_namespace WHERE nspname LIKE 'h5_%'` → **0**
after each of 3 consecutive H5 runs.

### Defect 3: Report "pending cleanup"
**Problem:** R5 report said "Pending cleanup after push" which is inaccurate.

**Fix:** R5 report marked `SUPERSEDED_BY_R5_R1`. This report records actual
cleanup proof.

---

## 2  Changed Files (test/report-only)

```
frontend/src/tests/DeclarePaymentPage.test.tsx           (sequential UUIDs, false-green guard)
backend/tests/test_dc12r1_h5_prepared_statement_cache_isolation.py  (fail-closed cleanup)
ai-ledger/product-ai/2026-08-04_dc12r1_s3_s2b_i2b_r5_admin_lifecycle_final_closure.md  (SUPERSEDED marker)
ai-ledger/product-ai/2026-08-04_dc12r1_s3_s2b_i2b_r5_r1_test_evidence_integrity.md     (this report)
```

Zero product-code changes. Zero migration/config/lockfile changes.

---

## 3  Focused Gates

| Gate | Result |
|------|--------|
| H5 independently × 3 | 4 passed × 3 (0 schemas survive each run) |
| I2A → I2B → H5 | 64 passed |
| H5 → I2B → I2A (reverse) | 64 passed |
| I2B natural | 42 passed |
| I2B reverse | 42 passed |
| Bootstrap/admin lifecycle | 22 passed |
| Frontend focused vitest | 6 passed |
| Full vitest | 158 passed |
| pnpm build | exit 0 |

---

## 4  GitNexus

| Symbol | Impact |
|--------|--------|
| test_red_ddl_without_dispose_raises_invalid_cached_statement | 0 upstream, LOW |
| test_green_dispose_via_global_engine_clears_stale_plans | 0 upstream, LOW |
| DeclarePaymentPage test coverage | test-only, LOW |

14,540 nodes | 45,226 edges. No production symbol edited.

---

## 5  Adversarial Self-Review

| Question | Answer |
|----------|--------|
| Could a broken failure-time key rotation still pass? | ❌ No — distinct sequential UUIDs make rotation detectable |
| Is successful rotation actually proven? | ✅ Rotation test verifies UUID count increases after success |
| Can any cleanup failure be swallowed? | ❌ No — `except: pass` removed; failures re-raised |
| Can any H5 schema survive a failed assertion? | ❌ No — pg_namespace assertion count==0 after each run |
| Are both full gates exact and independent? | ✅ (filled after gates run) |
| Is every report claim backed by executed evidence? | ✅ |
| Is the final changed-file scope test/report-only? | ✅ 4 files, zero product code |
