# DC-12R1-S3-S2B-I2B-M1 — Controlled Merge

**Status:** PASS_DC12R1_S3_S2B_I2B_CONTROLLED_MERGE
**Date:** 2026-08-04
**Executor:** local Zcode

---

## SHAs

| Ref | SHA |
|-----|-----|
| Pre-merge target (product-dev-recovered) | `76fb345c9054530cb0e6abccf35f0cc1863d2bef` |
| Source (R5-R1) | `c65c87cb0b9fd5a46ed55a2554988e00ebff9764` |
| Independent report (Lubuntu) | `34220d0fa8901ccaefecf307288a31b048105cbc` |
| **Merge commit** | `753048f029c4eede86fb11857677db57b865900e` |
| Merge parent 1 (target) | `76fb345c9054530cb0e6abccf35f0cc1863d2bef` |
| Merge parent 2 (source) | `c65c87cb0b9fd5a46ed55a2554988e00ebff9764` |

## Merge integrity

- `git merge --no-ff` — no conflicts
- `git diff --exit-code <source> HEAD` — **empty** (merge tree == source tree byte-for-byte)
- Merge commit first parent == exact target SHA ✅
- Merge commit second parent == exact source SHA ✅

## Scope gate — 31 files, 6025 insertions, 50 deletions

```
A  ai-ledger/product-ai/2026-08-03_dc12r1_s3_s2b_i2b_payment_declaration_runtime.md
A  ai-ledger/product-ai/2026-08-03_dc12r1_s3_s2b_i2b_r2_r3_r1_final_gate.md
A  ai-ledger/product-ai/2026-08-03_dc12r1_s3_s2b_i2b_r2_r3_r2_r1_exact_gate_closure.md
A  ai-ledger/product-ai/2026-08-03_dc12r1_s3_s2b_i2b_r2_r3_runtime_closure.md
A  ai-ledger/product-ai/2026-08-03_dc12r1_s3_s2b_i2b_r3_h5_final_gate.md
A  ai-ledger/product-ai/2026-08-03_dc12r1_s3_s2b_i2b_self_review.md
A  ai-ledger/product-ai/2026-08-04_dc12r1_s3_s2b_i2b_r4_h5_causal_regression.md
A  ai-ledger/product-ai/2026-08-04_dc12r1_s3_s2b_i2b_r5_admin_lifecycle_final_closure.md
A  ai-ledger/product-ai/2026-08-04_dc12r1_s3_s2b_i2b_r5_r1_test_evidence_integrity.md
M  backend/api/app.py
A  backend/api/v1/client/declarations.py
M  backend/api/v1/client/orders.py
A  backend/api/v1/client/statements.py
A  backend/api/v1/declarations.py
M  backend/api/v1/orders.py
A  backend/repositories/payment_declaration_repository.py
M  backend/repositories/payment_repository.py
A  backend/schemas/declaration.py
M  backend/services/canonical_payment_service.py
A  backend/services/payment_declaration_service.py
A  backend/tests/test_dc12r1_h5_prepared_statement_cache_isolation.py
M  backend/tests/test_dc12r1_s3_s1_catalog_order_hardening.py
M  backend/tests/test_dc12r1_s3_s2_read_only_retailer_finance.py
A  backend/tests/test_dc12r1_s3_s2b_i2b_payment_declarations.py
A  frontend/src/pages/client/DeclarationHistoryPage.tsx
A  frontend/src/pages/client/DeclarePaymentPage.tsx
A  frontend/src/pages/finance/DeclarationQueuePage.tsx
M  frontend/src/router/AppRouter.tsx
A  frontend/src/services/declarationService.ts
A  frontend/src/tests/DeclarePaymentPage.test.tsx
A  frontend/src/types/declaration.ts
```

No migration 038, no lockfile, no config, no permission-registry changes.

## Post-merge focused gates

| Gate | Result |
|------|--------|
| I2A → I2B → H5 | 64 passed |
| H5 → I2B → I2A (reverse) | 64 passed |
| Bootstrap/admin/owner lifecycle | 30 passed |
| Frontend focused vitest | 6 passed |
| Full vitest | 160 passed |
| pnpm build | exit 0 |

## Accepted Lubuntu full-gate attribution

Two exact independent full backend runs (from `34220d0f` Lubuntu evidence):
- Stack A: 3180 passed, 48 skipped, 15 xfailed, 0 failed, 0 errors
- Stack B: 3180 passed, 48 skipped, 15 xfailed, 0 failed, 0 errors

## GitNexus

14,548 nodes | 45,235 edges | 946 clusters. Financial blast radius treated as CRITICAL.
Impact: confirm_payment (2), confirm_declaration (0), allocate_receipt_number (3), configure_app (5) — all LOW graph score, 0 processes affected, validated by two independent full gates.

## Protected-ref proof

| Ref | Before | After | Status |
|-----|--------|-------|--------|
| product-dev-recovered | 76fb345c | 753048f0 | ✅ ff updated |
| main | 134ea59e | 134ea59e | ✅ unchanged |
| platform-dev | 12c5ee55 | 12c5ee55 | ✅ unchanged |
| source branch | c65c87cb | c65c87cb | ✅ unchanged |
| report branch | 34220d0f | 34220d0f | ✅ unchanged |
| Tag fingerprint | d9c4d82d... | d9c4d82d... | ✅ unchanged |

## Cleanup proof

- Docker containers (merge-pg, merge-redis): removed
- Temporary integration branch (i2b-merge-temp-2026-08-04): deleted
- Integration worktree: removed and pruned
- No unrelated worktrees affected
