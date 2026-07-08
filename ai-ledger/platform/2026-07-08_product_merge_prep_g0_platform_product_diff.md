# Product-Line Merge Preparation Gate 0 -- Platform/Product Diff & Risk Proposal

| Field | Value |
|---|---|
| **Task ID** | G0 (Product-Line Merge Preparation Gate 0) |
| **Date** | 2026-07-08 |
| **Branch** | `codex/product-merge-prep-g0-platform-product-diff-2026-07-08` |
| **Type** | PROPOSAL / REVIEW-ONLY. No merge. No runtime change. Docs/ledger-only. |
| **Base (worktree)** | `origin/platform-dev @ 12c5ee557876498240b1a36cc850d030d7bd8293` |
| **Target of evaluation** | Merge direction: `platform-dev` -> `product-dev-recovered` |
| **Verdict** | **CONDITIONAL: G1 isolated merge rehearsal ALLOWED as PROBE-ONLY (throwaway, no promotion). 4 blockers must be resolved with a CTO-approved resolution plan before any real promotion.** |

---

## 1. Branch SHAs (recorded after `git fetch --all --prune`)

| Branch | SHA |
|---|---|
| `origin/platform-dev` | `12c5ee557876498240b1a36cc850d030d7bd8293` |
| `origin/product-dev-recovered` | `2a5a31479faf8cf64e87cb5ba0fc4a7092f6d3f5` |
| Common merge-base | `8332f81e78a7103a7271d7199067f82c461a8ada` |
| Commits platform-dev is ahead of product-dev-recovered | **419** |
| Commits product-dev-recovered is ahead of platform-dev | **293** |

The two branches have diverged hard from `8332f81e` (712 combined divergent commits). This is NOT a fast-forward scenario; any merge is a true 3-way merge with high conflict surface.

---

## 2. Diff Summary (origin/product-dev-recovered..origin/platform-dev)

```
873 files changed, 127944 insertions(+), 69560 deletions(-)
Status counts:  A (added on platform) = 524
                 D (present on product, absent on platform) = 258
                 M (modified on one or both sides) = 91
```

**Diff direction convention:** `git diff A..B` where A = product-dev-recovered, B = platform-dev.
- `A` = absent on product-dev-recovered, present on platform-dev (platform-only additions).
- `D` = present on product-dev-recovered, absent on platform-dev (product-only files that platform lacks).
- `M` = differs between the two (potentially modified on both sides -- real conflict candidates).

### Category counts

| Category | Count | Merge risk |
|---|---|---|
| platform-only (P10-P25 backend API + frontend pages/components + platform contracts) | 82 | LOW (additive) |
| shared docs/memory (docs/ai, ai-ledger, README, etc.) | 462 | LOW-MEDIUM (additive mostly; README double-edit needs pick-one) |
| shared backend/frontend infra (tests, platform pages/components, src) | 243 | LOW-MEDIUM (additive mostly; see infra conflicts) |
| product-business touched (orders/inventory/receivables) | 5 | **MEDIUM-HIGH** (3 modified on both sides) |
| migration/DB | 17 | **CRITICAL** (numeric collision + deletes) |
| package/lockfile | 4 | **MEDIUM** (all 4 modified on both sides) |
| risk/unknown (platform agent/harness scripts under `scripts/`) | 60 | LOW (additive platform tooling) |
| **TOTAL** | **873** | |

---

## 3. CRITICAL Blockers (must resolve before promotion; surface in G1)

### 3.1 BLOCKER-1 -- Alembic migration numeric collision (CRITICAL)

Both branches independently claim revision numbers `020` and `021` for DIFFERENT migrations:

| Rev | product-dev-recovered (present) | platform-dev (present) |
|---|---|---|
| `020` | `020_sys_jobs_audit_columns.py` | `020_durable_approval_store.py` |
| `021` | `021_tenant_payments_retailer_id_transaction_id.py` | `021_platform_backup_status_source.py` |

Additionally, product-dev-recovered has migrations `022` through `028` that platform-dev does NOT have (they appear as `D` in the diff):
- `022_import_runs.py`, `023_inventory_reservations.py`, `024_intake_skeleton.py`,
  `025_intake_apply_audit.py`, `026_tenant_onboarding_auth_contract.py`,
  `027_onboarding_status_tokens.py`, `028_owner_credential_setup_tokens.py`

**Why CRITICAL:** Alembic enforces unique revision identifiers per chain. Duplicate `020`/`021` revisions produce an ambiguous history (`down_revision`/`depends_on` graph breaks), `alembic upgrade head` becomes non-deterministic, and the migration head the two branches point at is different. A naive `git merge` will land BOTH `020_*` files in the tree with no git-level conflict (different filenames), silently producing a broken migration set.

**Resolution requirement (pre-promotion):** Renumber one side's `020`/`021` to non-colliding revisions (recommended: renumber platform's `020_durable_approval_store` -> `029` and `021_platform_backup_status_source` -> `030`, keeping the product 020-028 chain intact), fix the `down_revision` pointers, then re-run `alembic upgrade head` + `alembic downgrade` round-trip on a clean DB to prove a single linear head. **CTO must approve the renumbering direction.**

### 3.2 BLOCKER-2 -- Auth/RBAC middleware double-modify (HIGH)

Both `backend/api/middleware/auth.py` and `backend/api/middleware/rbac.py` are `M` (differ on both sides):
- **product-dev-recovered side:** U6-I4 first tenant admin RBAC creation + tenant-context / onboarding auth contract (migrations 026-028) work.
- **platform-dev side:** identity-only `PlatformRoute` global `super_admin` guard + P25-ED `get_platform_db` system-scope session (`mark_session_as_system`).

**Why HIGH:** These are security boundary files. A conflict resolution that picks product's version would silently DROP the P25-ED system-scope session fix -> the `TenantContextMissingError` 5xx that P25-ED/P25-EE/P25-EF just closed on all 19 platform routes would regress. A resolution that picks platform's version would silently DROP the product RBAC/onboarding-auth work.

**Resolution requirement (pre-promotion):** Manual 3-way merge by a reviewer who understands BOTH the platform identity boundary AND the product RBAC/onboarding model. Both behaviors must coexist. Security sign-off required.

### 3.3 BLOCKER-3 -- Product business files modified on both sides (MEDIUM)

| File | Status | Notes |
|---|---|---|
| `frontend/src/pages/inventory/InventoryAdjustModal.tsx` | M | product UI changed on both sides |
| `frontend/src/pages/inventory/InventoryPage.tsx` | M | product UI changed on both sides |
| `frontend/src/pages/orders/OrderListPage.tsx` | M | product UI changed on both sides |
| `backend/services/receivables_service.py` | D | present on product, absent on platform (merge keeps it) |
| `frontend/src/pages/orders/CreateOrderPage.tsx` | D | present on product, absent on platform (merge keeps it) |

**Resolution requirement:** The 3 `M` files need conflict resolution with PRODUCT business logic winning (these are product-domain files; platform should not have touched them -- if platform did, that itself is a scope question for CTO). The 2 `D` files are safe (a merge of platform->product never deletes product-only files).

### 3.4 BLOCKER-4 -- Package/lockfile double-modify (MEDIUM)

All 4 dependency manifests modified on both sides:
- `backend/poetry.lock` (M), `backend/pyproject.toml` (M)
- `frontend/package.json` (M), `frontend/pnpm-lock.yaml` (M)

**Resolution requirement:** Reconcile dependencies after merge (re-run `poetry lock` + `pnpm install` on the merged tree). Verify no platform-only dependency gets dropped and no product dependency regresses.

---

## 4. Shared Docs/Memory Drift

### 4.1 docs/ai/ (33 files differ)

- **32 PLATFORM_PRODUCT_* contracts** (P10-P25, PRD, ROADMAP, SECURITY_BOUNDARY, PERMISSION_MATRIX, etc.) -- these are ADDITIVE on platform-dev (product-dev-recovered does not have them or has older versions). Merge risk LOW (platform wins; product adopts platform contracts).
- **docs/ai/README.md** -- BOTH branches modified this file (platform added the P25 closeout status line in P25-F; product has its own state). **CTO-choice: pick canonical version.** Recommended: take platform-dev's README.md (it is the more recent cumulative AI context entry) and re-merge any product-specific pointers.

### 4.2 ai-ledger/ (312 files differ)

Predominantly ADDITIVE platform/backend/frontend/ops ledgers from platform-dev (P1-P25 platform work, platform agent harness ledgers). A small subset of older phase4/phase5 ledgers appears because the branches diverged before those were written. **Merge risk LOW** (ledgers are append-only history; both sides' ledgers should coexist). **CTO-choice:** any ledger edited on BOTH sides (not just added on one) needs pick-one -- G1 rehearsal must enumerate these.

### 4.3 decision-register/

`decision-register/` shows **0 drift** in this diff -- no conflict in the decision register. (LOW risk.)

### 4.4 Other shared memory (README/PROJECT/CTO_CURRENT_OPS/AI_TEAM_OPERATING_RULES)

No standalone `PROJECT.md` / `CTO_CURRENT_OPS.md` / `AI_TEAM_OPERATING_RULES.md` deltas appeared outside `docs/ai/`. The `docs/ai/README.md` double-edit (4.1) is the only human-facing memory pointer needing a CTO pick.

---

## 5. Risk/Unknown category (60 files)

All 60 are `scripts/platform_*.py` and `scripts/test_platform_*.py` -- platform agent/harness tooling (agent preflight, mission gate, worktree executor, diff auditor, runner gate, etc.). These are ADDITIVE platform tooling. **Merge risk LOW** (product adopts platform tooling scripts; no product file is touched). Reclassified as platform-tooling for clarity.

---

## 6. Conclusion: Is G1 isolated merge rehearsal allowed?

**CONDITIONAL YES -- G1 may proceed as a PROBE-ONLY, throwaway rehearsal** to enumerate the exact conflict hunks, BUT:

1. **G1 must be on a throwaway branch** (`NOT` on `product-dev-recovered`, `NOT` on `platform-dev`). Create e.g. `codex/product-merge-rehearsal-g1-<date>` from `product-dev-recovered` and merge `platform-dev` into it.
2. **G1 output is evidence-only**: capture the conflict file list, the conflict hunk count per file, and the migration-head state. **No promotion.**
3. **Promotion is BLOCKED** until the 4 blockers in Section 3 each have a CTO-approved resolution plan (migration renumbering direction; auth/rbac 3-way merge reviewer; product-business conflict winner; lockfile reconciliation).
4. **G1 must explicitly test** that the P25-ED/P25-EE/P25-EF platform fixes survive the merge (run the P25-EF real-stack smoke on the rehearsal tree and confirm 19/19 HTTP 200, 0 backend 5xx).

### Blockers that must be resolved before promotion

1. **BLOCKER-1 (CRITICAL):** Alembic `020`/`021` numeric collision + product migrations 022-028 absent on platform. Requires renumbering + full migration round-trip proof. CTO picks renumber direction.
2. **BLOCKER-2 (HIGH):** `auth.py` + `rbac.py` double-modify. Requires manual 3-way merge preserving BOTH the platform system-scope session AND the product RBAC/onboarding work. Security sign-off.
3. **BLOCKER-3 (MEDIUM):** 3 product-business frontend files modified on both sides. Product business logic must win.
4. **BLOCKER-4 (MEDIUM):** 4 package/lockfile manifests modified on both sides. Dependency reconciliation + rebuild/relock.

### Does product-dev-recovered risk overwriting platform results?

**YES -- MATERIAL RISK.** Because the merge target is `product-dev-recovered`, any conflict resolved in favor of product on `auth.py` / `rbac.py` / the colliding migrations would silently drop the platform P25-ED system-scope session fix, the P25-EF audit-result vocab fix, and the platform durable-approval tables -- reintroducing the exact 5xx regressions P25-EA through P25-EF just closed. This is the single highest-impact risk of the merge and MUST be guarded by the G1 post-merge smoke (Section 6 item 4).

### CTO-choice items (conflicts/drift requiring human decision)

| # | Item | Decision needed |
|---|---|---|
| 1 | Alembic `020`/`021` renumbering direction | Which side renumbers; confirm single linear head |
| 2 | `backend/api/middleware/auth.py` conflict | 3-way merge direction (must keep BOTH behaviors) |
| 3 | `backend/api/middleware/rbac.py` conflict | 3-way merge direction (must keep BOTH behaviors) |
| 4 | `docs/ai/README.md` double-edit | Pick canonical (recommended: platform-dev's) |
| 5 | `frontend/src/pages/inventory/InventoryAdjustModal.tsx` | Conflict winner (product business) |
| 6 | `frontend/src/pages/inventory/InventoryPage.tsx` | Conflict winner (product business) |
| 7 | `frontend/src/pages/orders/OrderListPage.tsx` | Conflict winner (product business) |
| 8 | Any ai-ledger edited on BOTH sides | G1 must enumerate; pick-one per file |
| 9 | `backend/poetry.lock` / `pyproject.toml` | Dependency reconciliation after merge |
| 10 | `frontend/package.json` / `pnpm-lock.yaml` | Dependency reconciliation after merge |

---

## 7. Recommendation

**Do NOT auto-merge. Proceed to G1 rehearsal ONLY to surface exact conflicts, then STOP for CTO resolution of the 4 blockers.** The migration collision (BLOCKER-1) and the auth/rbac double-modify (BLOCKER-2) are hard gates: until each has an approved resolution plan, no real merge may run. The G1 rehearsal is valuable precisely because it will produce the concrete conflict hunks that make the CTO choices in Section 6 actionable, but its output is evidence, not a mergeable tree.

**Risk level for this G0 proposal itself: LOW** (docs/ledger-only; no runtime change; no merge performed; both protected branches untouched).

---

## 8. Scope Diff Gate (this G0 task)

### Changed files (G0)

- `ai-ledger/platform/2026-07-08_product_merge_prep_g0_platform_product_diff.md` (this proposal ledger -- the ONLY added file)

No `docs/ai/README.md` pointer line added (per task rule: optional, must be explained first; not added by default).

### Scope audit

- No `backend/` runtime file modified.
- No `frontend/` runtime file modified.
- No migration modified.
- No merge performed.
- No package/lockfile modified.
- No auth/RBAC file modified.
- No `product-dev-recovered` push.
- No `platform-dev` push.

**Scope Diff Gate: PASS**

---

## 9. Gate Checklist

| Gate | Status | Notes |
|---|---|---|
| `git fetch --all --prune` | PASS | |
| `origin/platform-dev == 12c5ee55` confirmed | PASS | `12c5ee557876498240b1a36cc850d030d7bd8293` |
| `origin/product-dev-recovered == 2a5a3147` recorded | PASS | `2a5a31479faf8cf64e87cb5ba0fc4a7092f6d3f5` |
| Base Proof Gate (HEAD == base, clean tree) | PASS | worktree created from `origin/platform-dev` |
| `git diff --check` | PASS | No whitespace errors (1 ledger file) |
| Added-line ASCII scan | PASS | No non-ASCII |
| `detect-secrets-hook --baseline .secrets.baseline` | PASS | SECRETS_EXIT=0 |
| `.secrets.baseline` unchanged | PASS | |
| Forbidden audit (only ai-ledger/platform proposal doc) | PASS | No backend/frontend/migration/product/auth |
| `npx gitnexus analyze` | PASS | Index built |
| `npx gitnexus status` | PASS | up-to-date at branch tip |
| Worktree clean after commit | PASS | |
| Push feature branch with explicit `branch:branch` refspec | PASS | |
| `platform-dev` NOT pushed / unchanged | PASS | |
| `product-dev-recovered` NOT pushed / unchanged | PASS | |

---

## 10. Verdict

**G0 PROPOSAL COMPLETE. G1 isolated merge rehearsal is ALLOWED as PROBE-ONLY (throwaway, evidence-only, no promotion). 4 blockers (migration collision, auth/rbac double-modify, product-business conflicts, lockfile reconciliation) must each have a CTO-approved resolution plan before any real promotion. Material risk exists that product-dev-recovered-side conflict resolution silently drops the P25-ED/P25-EF platform fixes; G1 must re-prove 19/19 HTTP 200 / 0 backend 5xx on the rehearsal tree before promotion is even considered.**
