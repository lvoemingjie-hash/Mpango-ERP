# DC-12R1-S3-S2B-I2B-R5-R1-V1 Independent Final Runtime Verification

**Date**: 2026-08-04  
**Executor**: Lubuntu Codex (Python 3.12.3, Poetry 2.4.1, PG 16.14 port 57501, Redis 7.4.9 port 57901)  
**Verdict**: PASS_DC12R1_S3_S2B_I2B_R5_R1_V1_INDEPENDENT_FINAL

---

## 1. Exact SHAs and Lineage

| Ref | Expected SHA | Verified SHA | Match |
|-----|-------------|-------------|-------|
| Candidate | `c65c87cb0b9fd5a46ed55a2554988e00ebff9764` | `c65c87cb0b9fd5a46ed55a2554988e00ebff9764` | YES |
| Candidate parent | `fb9b82a12a29b156dd5f20fae20393e7caae8cdd` | `fb9b82a12a29b156dd5f20fae20393e7caae8cdd` | YES |
| Baseline | `76fb345c9054530cb0e6abccf35f0cc1863d2bef` | `76fb345c9054530cb0e6abccf35f0cc1863d2bef` | YES |
| Ancestry | baseline is ancestor of candidate | YES | YES |

Worktree: detached HEAD at `c65c87c`, clean working tree.

## 2. Complete Changed-File Scope

### R5-R1 delta from parent (fb9b82a1..c65c87cb) -- exactly 4 files:

| File | Lines |
|------|-------|
| `backend/tests/test_dc12r1_h5_prepared_statement_cache_isolation.py` | 169 changed |
| `frontend/src/tests/DeclarePaymentPage.test.tsx` | 103 changed |
| `ai-ledger/product-ai/2026-08-04_dc12r1_s3_s2b_i2b_r5_admin_lifecycle_final_closure.md` | 7 changed |
| `ai-ledger/product-ai/2026-08-04_dc12r1_s3_s2b_i2b_r5_r1_test_evidence_integrity.md` | 104 added |

**No product code, migration, config, dependency, or lockfile changes.**  
**No migration 038.**  
**No deployment changes.**

### Full candidate delta vs baseline (76fb345..c65c87cb) -- 31 files:

All changes are backend services/repositories/schemas/routes, frontend pages/services/types/tests, and ai-ledger reports. No lockfile, Dockerfile, or alembic migration version files changed.

## 3. Frontend Evidence Authenticity

### Source verification
- `DeclarePaymentPage.tsx` line 62: `<label htmlFor="amount" ...>` -- associated
- `DeclarePaymentPage.tsx` line 63: `<input id="amount" type="number" ...>` -- associated
- Test line 86: `screen.getByLabelText(/amount/i)` -- correct query
- UUID mock: 20 distinct valid UUIDs (lines 35-56), sequential, not fixed-value
- Mount creates exactly one key (useRef init, line 20)
- Failed retries reuse the original key (lines 93-120, `keys[0] === keys[1]`)
- Successful submission rotates exactly once (lines 122-140, `totalCalls() > callsAfterMount`)
- Double-submit prevention (lines 142-152)
- Single navigation (lines 154-163)
- No browser storage (lines 165-179)

### Mutation proof
- **Mutation**: added `idempotencyKeyRef.current = crypto.randomUUID()` in catch block (failure path)
- **Result**: `reuses same key when first request fails` test turned RED
  - `AssertionError: expected '...001' to be '...004'` -- keys[0] != keys[1]
- **Restore**: byte-for-byte from backup
- **Result**: all 6 tests GREEN
- Mutation artifacts: NOT committed

### Full frontend suite
- `pnpm vitest run`: **18 files, 160 tests passed**
- `pnpm build`: successful (1286 modules, 11.32s)

## 4. H5 Causal and Cleanup Proof

### Source audit
- No cleanup uses `except Exception: pass` -- all cleanup errors are captured and re-raised
- Every temporary schema protected by try/finally (Test 1: lines 97/156, Test 2: lines 184/229)
- Engine disposal runs even if cleanup fails (Test 1: finally at 167 disposes engines)
- `pg_catalog.pg_namespace` checked for exact zero residue after each cleanup
- RED test: `assert stale_error is not None` (line 147) -- fail-closed when no error
- RED test: walks exception chain for `InvalidCachedStatement` (lines 139-154)
- GREEN test: imports `from database.session import async_engine` (line 180)
- Event-loop identity assertion: `assert loop_before is loop_after` (line 335)
- Backend PID change assertion: `assert pid_before != pid_after` (line 271)
- `pg_stat_activity` exact count assertion: `assert count_after == 0` (line 328)

### Execution on real PostgreSQL 16
- H5 file 3 consecutive runs: **4 passed each, zero `h5_*` schemas after each run**
- I2A -> I2B -> H5: **64 passed, zero residue**
- H5 -> I2B -> I2A: **64 passed, zero residue**

### Causal mutation
- **Mutation**: removed `await async_engine.dispose()` from `_h5_flush_stmt_cache` fixture
- **RED**: I2A -> I2B (no flush) produced 1 failure each run, 3/3 runs:
  - Run 1: `test_confirm_full_creates_receipt_and_paid_order` FAILED
  - Run 2: `test_confirm_overpayment_leaves_declaration_pending_and_zero_writes` FAILED
  - Run 3: `test_confirm_full_creates_receipt_and_paid_order` FAILED
- **Restore**: byte-for-byte from backup
- **GREEN**: 3/3 runs of I2A -> I2B (with flush): **60 passed each**
- Mutation artifacts: NOT committed

## 5. Runtime and Isolation Gates

| Gate | Result |
|------|--------|
| I2B natural order | 42 passed |
| I2B reverse order | 42 passed |
| I2A -> I2B -> H5 | 64 passed, zero residue |
| H5 -> I2B -> I2A | 64 passed, zero residue |
| Bootstrap/admin lifecycle (u6h2, u6h3, s3s1, u6d, u6f, s5a) | 83 passed |
| Owner credential lifecycle (u6i0-u6i6) | 64 passed |
| Redis cleanup: exact task-owned keys only | Confirmed |
| SCAN wildcard / FLUSHDB in I2B | NONE |
| Redis residue after focused gates | Zero (TTL-expired) |

### Admin lifecycle contract verified
- Bare bootstrap does NOT create the first admin: `_grant(ADMIN_ROLE, ...)` returns early if role does not exist
- `OwnerCredentialSetupService.create_first_admin_rbac()` creates admin RBAC: verified by u6i4 tests

## 6. Two Exact Full Backend Gates

| Metric | Gate 1 | Gate 2 |
|--------|--------|--------|
| Database | test_r5r1_gate1 (fresh) | test_r5r1_gate2 (fresh) |
| Redis | FLUSHALL before run | FLUSHALL before run |
| Alembic | upgrade head (037) | upgrade head (037) |
| **Exit code** | **0** | **0** |
| Collected | 3243 | 3243 |
| Passed | 3180 | 3180 |
| Failed | 0 | 0 |
| Errors | 0 | 0 |
| Skipped | 48 | 48 |
| XFailed | 15 | 15 |
| XPassed | 0 | 0 |
| Deselected | 0 | 0 |
| Duration | 1252.32s | 1267.85s |

**Totals are identical.** Accounting gap = 0.

## 7. Quality Gates

| Gate | Result |
|------|--------|
| `py_compile` on R5-R1 Python files | OK |
| `git diff --check` | OK (no whitespace errors) |
| `pre-commit` (scoped to changed files) | All passed |
| `detect-secrets` scan | Zero secrets found |
| Mojibake scan | 3 files have em-dashes/arrows (valid UTF-8, not corruption); DeclarePaymentPage.test.tsx pure ASCII |
| GitNexus | NOT AVAILABLE in this environment (noted as limitation) |

### Impact review: bootstrap reconciliation
- `bootstrap_tenant_schema.py` NOT modified in R5-R1 delta
- `_reconcile_rbac_s1`: INSERTs only `RETAILER_OPERATOR_ROLE` (ON CONFLICT DO NOTHING)
- `_grant(ADMIN_ROLE, ...)`: checks role existence first, returns if not found -- does NOT create admin role
- Admin role creation deferred to `OwnerCredentialSetupService` -- verified by 83 lifecycle tests passing

### Impact review: DeclarePaymentPage
- Source `DeclarePaymentPage.tsx` NOT modified in R5-R1 delta (only test file changed)
- `htmlFor="amount"` / `id="amount"` association confirmed in source
- `getByLabelText` used in test, no `querySelector` workaround

## 8. Limitations

1. **GitNexus**: Not installed in this environment. Impact review performed manually.
2. **Independent stacks**: Used two separate databases on same PG 16 instance. Redis flushed between runs. No process overlap.
3. **Non-ASCII in source**: 3 of 4 R5-R1 changed files contain em-dashes (U+2014) and right arrows (U+2192) in docstrings/markdown. These are valid UTF-8, not mojibake.

## 9. Residue Accounting

| Artifact | Status |
|----------|--------|
| PG databases (test_r5r1_gate1, test_r5r1_gate2) | To be dropped |
| Redis keys | Zero (all TTL-expired) |
| h5_* schemas | Zero (verified after each run) |
| Temporary databases | Created and dropped by test runner |
| Mutation artifacts | Restored byte-for-byte, NOT committed |
| Worktree modifications | Clean (git diff --stat empty) |

## 10. Final Verdict

**PASS_DC12R1_S3_S2B_I2B_R5_R1_V1_INDEPENDENT_FINAL**

All gates passed:
- Base/scope: exact 4-file delta, no product/migration/config changes
- Frontend: htmlFor/id association, sequential UUIDs, mutation RED->GREEN
- H5 causal: fail-closed RED, global engine GREEN, 3x consecutive, both orderings, causal mutation
- Runtime/isolation: I2B both orders, bundle both orders, lifecycle tests, Redis exact keys
- Full backend: two independent gates, 3180 passed each, 0 failed, 0 errors, identical totals
- Quality: py_compile, pre-commit, detect-secrets all clean
- Accounting gap: 0
