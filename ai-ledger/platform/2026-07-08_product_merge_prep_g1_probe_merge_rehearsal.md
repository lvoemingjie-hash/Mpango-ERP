# Product-Line Merge Preparation Gate 1 -- Probe-Only Merge Rehearsal Conflict Inventory

| Field | Value |
|---|---|
| **Task ID** | G1 (Product-Line Merge Preparation Gate 1) |
| **Date** | 2026-07-08 |
| **Branch** | `codex/product-merge-prep-g1-probe-merge-rehearsal-2026-07-08` |
| **Type** | PROBE-ONLY. Evidence-only. No promotion. No resolution applied as final. |
| **Source (merging IN)** | `origin/platform-dev @ 12c5ee557876498240b1a36cc850d030d7bd8293` |
| **Target (merge base of branch)** | `origin/product-dev-recovered @ 2a5a31479faf8cf64e87cb5ba0fc4a7092f6d3f5` |
| **Common merge-base** | `8332f81e78a7103a7271d7199067f82c461a8ada` |
| **Merge command** | `git merge --no-ff --no-commit origin/platform-dev` |
| **Merge result** | `Automatic merge failed; fix conflicts and then commit the result.` (exit 1) |
| **Verdict** | **NOT AUTO-MERGEABLE. G2 human-resolution plan is FEASIBLE (conflict surface is bounded and classified). 53 conflict hunks across 9 files + silent Alembic dual-head + auto-merged-but-semantically-critical auth/rbac. Promotion requires G2 CTO decisions.** |

---

## 1. Conflict File List and Counts

The probe merge (`git merge --no-ff --no-commit origin/platform-dev`) failed with **9 conflicting files**, **27 unmerged index entries** (9 files x 3 stages), and **53 total conflict hunks**.

### Conflict files (9)

| # | File | Category | Conflict hunks |
|---|---|---|---|
| 1 | `backend/api/v1/platform/audit.py` | platform API (auth/DB dependency) | 2 |
| 2 | `backend/api/v1/platform/stats.py` | platform API (auth/DB dependency) | 2 |
| 3 | `backend/api/v1/platform/tenants.py` | platform API (auth/DB dependency) | 3 |
| 4 | `backend/tests/test_platform_audit_api.py` | platform test | 3 |
| 5 | `backend/tests/test_platform_stats_api.py` | platform test | 2 |
| 6 | `docs/ai/README.md` | shared docs/memory | 1 |
| 7 | `frontend/pnpm-lock.yaml` | package/lockfile | 36 |
| 8 | `frontend/src/components/layout/Sidebar.tsx` | platform frontend infra | 1 |
| 9 | `frontend/src/router/AppRouter.tsx` | platform frontend infra | 3 |
| | **TOTAL** | | **53** |

### Conflict counts by category

| Category | Files | Hunks |
|---|---|---|
| Migration/Alembic (silent collision, no git conflict) | 0 git-conflict (but 4 colliding files present in tree) | N/A (see Section 3) |
| Auth/security/RBAC/session (auto-merged, no git conflict) | 0 git-conflict (auth.py + rbac.py auto-merged) | N/A (see Section 4) |
| Package/lockfile/dependency | 1 (`pnpm-lock.yaml`) | 36 |
| Shared docs/memory | 1 (`docs/ai/README.md`) | 1 |
| Product business frontend/backend | 0 git-conflict (auto-merged) | N/A |
| Platform-only (API + frontend infra) | 7 (`audit.py`, `stats.py`, `tenants.py`, 2 tests, `Sidebar.tsx`, `AppRouter.tsx`) | 16 |

**Auto-merged but semantically critical files (no git conflict markers):**
- `backend/api/middleware/auth.py` -- both sides modified, non-overlapping regions, git auto-merged.
- `backend/api/middleware/rbac.py` -- both sides modified, non-overlapping regions, git auto-merged. Contains `RequirePlatformAdmin` class (identity-only super_admin guard) from the product side.
- `frontend/package.json` -- both sides modified, auto-merged.
- `backend/api/v1/platform/audit.py` / `stats.py` / `tenants.py` -- these DID conflict because both sides rewrote the same import/dependency-injection lines.
- Product business files (`InventoryPage.tsx`, `InventoryAdjustModal.tsx`, `OrderListPage.tsx`) -- auto-merged (non-overlapping changes); no git conflict.

---

## 2. Silent Collision: Alembic Migration Dual-Head (CRITICAL)

The merge did NOT produce a git conflict for migrations (different filenames), but it landed BOTH chains simultaneously in `backend/alembic/versions/`, creating a **dual-head branching migration graph** with two independent heads from the same parent `019_platform_audit_logs`.

### Migration table (post-merge tree)

| File | Side | Revision ID | down_revision | Chain |
|---|---|---|---|---|
| `019_platform_audit_logs.py` | both (common) | `019_platform_audit_logs` | `018_...` | common parent |
| `020_durable_approval_store.py` | platform | `020_durable_approval_store` | `019_platform_audit_logs` | **platform chain A** |
| `021_platform_backup_status_source.py` | platform | `021_platform_backup_status_source` | `020_durable_approval_store` | **platform chain A** |
| `020_sys_jobs_audit_columns.py` | product | `020_sys_jobs_audit_columns` | `019_platform_audit_logs` | **product chain B** |
| `021_tenant_payments_retailer_id_transaction_id.py` | product | `021_tenant_payments_retailer_id_transaction_id` | `020_sys_jobs_audit_columns` | **product chain B** |
| `022_import_runs.py` | product | `022_import_runs` | `021_tenant_payments_...` | **product chain B** |
| `023_inventory_reservations.py` | product | `023_inventory_reservations` | `022_import_runs` | **product chain B** |
| `024_intake_skeleton.py` | product | `024_intake_skeleton` | `023_inventory_reservations` | **product chain B** |
| `025_intake_apply_audit.py` | product | `025_intake_apply_audit` | `024_intake_skeleton` | **product chain B** |
| `026_tenant_onboarding_auth_contract.py` | product | `026_tenant_onboarding_auth_contract` | `025_intake_apply_audit` | **product chain B** |
| `027_onboarding_status_tokens.py` | product | `027_onboarding_status_tokens` | `026_tenant_onboarding_...` | **product chain B** |
| `028_owner_credential_setup_tokens.py` | product | `028_owner_credential_setup_tokens` | `027_onboarding_status_tokens` | **product chain B** |

**Result: TWO HEADS** -- `021_platform_backup_status_source` (platform) and `028_owner_credential_setup_tokens` (product), both ultimately branching from `019_platform_audit_logs`. Revision ID strings are unique (no Alembic duplicate-ID error), but `alembic upgrade head` is ambiguous (two heads).

### Renumber options (NOT executed -- proposal only)

**Option A -- Linearize platform after product chain (recommended):**
- Renumber `020_durable_approval_store` to `029_durable_approval_store`, set `down_revision = '028_owner_credential_setup_tokens'`.
- Renumber `021_platform_backup_status_source` to `030_platform_backup_status_source`, set `down_revision = '029_durable_approval_store'`.
- Result: single linear head `030_platform_backup_status_source`. Product chain 019->020->...->028 is untouched.
- Pro: product migrations stay unchanged (less risk to product business data). Con: platform tables created last in the upgrade sequence.

**Option B -- Linearize product after platform chain:**
- Keep platform `020_durable_approval_store` and `021_platform_backup_status_source` as-is.
- Renumber product `020` through `028` to `022` through `030` (8 files), re-chain their `down_revision` pointers.
- Result: single linear head `030_owner_credential_setup_tokens`.
- Pro: platform chain stays at 020/021. Con: 8 product files must be renumbered and re-pointed (higher risk to product business data integrity).

**Option C -- Alembic merge head (no renumber):**
- Add an `alembic merge -m "merge_platform_product_heads"` revision that has `down_revision = ('021_platform_backup_status_source', '028_owner_credential_setup_tokens')`.
- Result: single head (the merge revision). Both chains remain at their current numbers.
- Pro: zero file renumbering. Con: introduces a merge-revision; `alembic upgrade head` works but the migration history has a diamond (two paths from 019 to head). Some tooling may not handle this well.

**Recommendation: Option A** (least product disruption, single linear chain, only 2 files renumbered). CTO must decide.

---

## 3. Platform API Conflicts (auth.py / rbac.py / DB dependency)

### 3.1 Conflicting hunks in platform API endpoints

All three backend platform API files (`audit.py`, `stats.py`, `tenants.py`) have the **same conflict pattern** -- every route's import block and dependency injection:

```
<<<<<<< HEAD (product-dev-recovered)
from api.dependencies import get_db
from api.middleware.rbac import RequirePlatformAdmin
from core.security import TokenPayload
=======
from api.dependencies import get_platform_db
from api.v1.platform.p10.guard import require_platform_operator
from api.v1.platform.p10.services import redact_metadata
>>>>>>> origin/platform-dev
```

And per-route:
```
<<<<<<< HEAD (product)
    token: TokenPayload = Depends(RequirePlatformAdmin()),
    db: AsyncSession = Depends(get_db),
=======
    db: AsyncSession = Depends(get_platform_db),
    _auth: None = Depends(require_platform_operator),
>>>>>>> origin/platform-dev
```

### 3.2 Platform behaviors that MUST be preserved

1. **`get_platform_db`** (P25-ED): System-scope DB session (`mark_session_as_system`). Without this, `TenantContextMissingError` fires on all 19 platform routes -> HTTP 500 (the exact regression P25-ED/P25-EE/P25-EF closed).
2. **`require_platform_operator`** (P10/P11): Identity-only `PlatformRoute` guard that admits only a `tenant_id == null` super_admin and denies a tenant-contextual super_admin.
3. **`redact_metadata`** (P10 services): Metadata redaction for audit event reads.
4. **P25-EF audit-result stability**: The `_coerce_audit_result` mapper and `AuditResult` closed-vocab with `recorded`.

### 3.3 Product behaviors that MUST be preserved

1. **`RequirePlatformAdmin`** class (rbac.py): Product's own platform-admin dependency. The platform side renamed/replaced it with `require_platform_operator`. If product still references `RequirePlatformAdmin` anywhere outside the conflict zones, both classes may need to coexist or product references must be migrated.
2. **U6 onboarding/auth/RBAC creation chain** (migrations 026-028): tenant admin RBAC creation, owner credential setup tokens, onboarding status tokens.
3. **Product login / tenant auth** flows in auth.py (auto-merged; must verify coexistence with platform identity guard).

### 3.4 auth.py / rbac.py auto-merge note

`auth.py` and `rbac.py` **auto-merged** (no git conflict markers, no staged diff). This means product and platform modified non-overlapping regions. However, the auto-merged result must be **semantically verified**: does `rbac.py`'s `RequirePlatformAdmin` class (from product) conflict with the platform's `require_platform_operator` guard? Are there two platform-admin auth dependencies that could be inconsistent? This requires a G2 reviewer to read the full merged file, not just rely on the clean git status.

---

## 4. Frontend Conflicts

### 4.1 Sidebar.tsx (1 hunk)

```
<<<<<<< HEAD (product)
  CurrencyDollarIcon,
=======
  ShieldCheckIcon,
  WrenchScrewdriverIcon,
  ChartBarIcon,
  ... (10 platform-admin icons)
  LifebuoyIcon,
>>>>>>> origin/platform-dev
  import { isIdentityPlatformOperator } from '@/router/guards';
```

Product adds `CurrencyDollarIcon`; platform adds 10 platform-admin icons + the `isIdentityPlatformOperator` import. **Resolution: keep BOTH sets of imports** (union). No product icon is dropped; no platform icon is dropped.

### 4.2 AppRouter.tsx (3 hunks)

Hunk 1: Product renames `CreateOrderPage` to `ClientCreateOrderPage` alias; platform adds platform page imports (PlatformOverview, PlatformAuditEvents, etc.). **Resolution: keep BOTH** (union of imports).

Hunks 2-3: Comment style difference -- product uses `//` (single dash), platform uses `// --` (double dash). **Resolution: pick one comment style** (trivial; recommend platform's `--` style).

---

## 5. Package/Lockfile Conflicts

### 5.1 `pnpm-lock.yaml` (36 hunks)

36 conflict hunks in the lockfile. This is expected when both sides add/change dependencies. **Resolution: do NOT hand-resolve.** After all other conflicts are resolved and the merge is committed, run `pnpm install` on the merged tree to regenerate the lockfile cleanly.

### 5.2 `package.json` (auto-merged, no conflict)

Both sides modified `package.json` in non-overlapping regions. The auto-merged result must be verified for duplicate/conflicting dependency versions, but git did not flag a conflict. **Action: verify merged `package.json` has no version contradictions.**

### 5.3 Backend dependencies (`poetry.lock` / `pyproject.toml`)

Both were `M` on both sides per G0 analysis. They did NOT appear in the conflict list -- they auto-merged. Same as package.json: verify no version contradictions; if needed, run `poetry lock` on the merged tree.

---

## 6. Shared Docs/Memory Conflicts

### 6.1 `docs/ai/README.md` (1 hunk)

Product (HEAD) has no platform product track section; platform-dev adds the full "Platform Product Track Entry" section (25 platform product contract reading pointers + the P25 closeout status line from P25-F).

```
<<<<<<< HEAD (product)
(no platform section)
=======
## Platform Product Track Entry
... (25 pointers + P25 contract)
>>>>>>> origin/platform-dev
```

**Resolution: take platform-dev's version** (additive; product gains platform context). No product content is lost.

---

## 7. Feasibility Verdict

### 7.1 Is auto-merge possible?

**NO.** The probe produced 53 conflict hunks across 9 files. The conflict surface is bounded and well-classified, but manual resolution is required for each.

### 7.2 Is G2 human-resolution plan feasible?

**YES.** The conflict surface is tractable:
- 7 of 9 files are platform API/frontend infra with a clear "platform wins" resolution (preserve `get_platform_db` + `require_platform_operator`).
- `docs/ai/README.md` is additive (platform wins, no loss).
- `pnpm-lock.yaml` (36 of 53 hunks) is regenerated, not hand-resolved.
- The remaining hard items are the silent Alembic dual-head (Section 2) and the auto-merged auth/rbac semantic verification (Section 3.4), neither of which is a git conflict but both of which are G2-required work.

### 7.3 Can a temporary resolved rehearsal tree be produced for testing?

**Not attempted in G1.** A rehearsal-only resolution would require:
1. Resolve all 9 files (platform-wins for API/frontend, union for Sidebar/Router, regenerate pnpm-lock).
2. Renumber migrations (Section 2 Option A).
3. Commit as `rehearsal-only-...`.
4. Run backend tests + frontend build + P25-EF smoke.

This is G2 work. G1 is evidence-only. No rehearsal-only commit was created.

### 7.4 Minimal verification status

- Backend tests: **NOT RUN** (merge was aborted after evidence capture; no resolved tree exists).
- Frontend build: **NOT RUN** (same reason).
- P25-EF real-stack smoke: **NOT RUN** (same reason).
- **Blockers for running tests on a rehearsal tree:** the 9 conflicts must be resolved first, and the Alembic dual-head must be linearized before `alembic upgrade head` can run on any DB. These are G2 tasks.

---

## 8. G2 CTO Decision List

| # | Decision needed | Options | Default recommendation |
|---|---|---|---|
| 1 | Alembic dual-head resolution direction | A (platform renumber to 029/030) / B (product renumber 020-028 to 022-030) / C (alembic merge head) | **A** (least product disruption) |
| 2 | Platform API endpoints (audit/stats/tenants) | Platform wins (`get_platform_db` + `require_platform_operator`) / product wins (`get_db` + `RequirePlatformAdmin`) | **Platform wins** (preserves P25-ED fix) |
| 3 | Platform tests (test_platform_audit_api, test_platform_stats_api) | Platform wins (match API resolution) | **Platform wins** |
| 4 | `docs/ai/README.md` | Platform wins (additive) / merge both sections | **Platform wins** (additive) |
| 5 | `Sidebar.tsx` import union | Keep both icon sets + platform import | **Union** |
| 6 | `AppRouter.tsx` | Keep both imports + pick comment style | **Union + platform comment style** |
| 7 | `pnpm-lock.yaml` | Regenerate via `pnpm install` | **Regenerate** |
| 8 | auth.py / rbac.py semantic verification | G2 reviewer must read full auto-merged files and confirm both product RBAC and platform identity guard coexist | **Manual review** |
| 9 | Product business files (Inventory/Orders) auto-merge verification | Confirm no semantic conflict in auto-merged result | **Manual review** |
| 10 | Post-resolution P25-EF smoke gate | Re-run 19/19 HTTP 200 + 0 backend 5xx on the rehearsal tree before any promotion | **Mandatory** |

---

## 9. Risk

| Risk Domain | Level | Rationale |
|---|---|---|
| This G1 probe (evidence-only) | **LOW** | Merge was aborted; worktree is clean; no commit pushed other than the ledger. Both protected branches untouched. |
| G2 resolution plan execution | **MEDIUM** | Conflict surface is bounded (9 files, 53 hunks) but the silent Alembic dual-head and auto-merged auth/rbac semantic verification carry real risk if missed. |
| Product-dev-recovered overwriting platform results | **HIGH if mis-resolved** | If the platform API endpoints are resolved in favor of product (`get_db` + `RequirePlatformAdmin`), the P25-ED system-scope session fix is lost and all 19 platform routes regress to 5xx. The post-resolution P25-EF smoke (decision #10) is the guard. |
| Migration data integrity | **MEDIUM-HIGH** | The dual-head means any existing production DB that ran one chain will need the other chain applied. The renumbering direction (decision #1) affects upgrade order. Must be tested on a clean DB round-trip. |

---

## 10. Blockers

1. **No resolved rehearsal tree exists.** G1 is evidence-only; tests/build/smoke cannot run on a conflict-aborted tree. G2 must produce a resolved rehearsal tree first.
2. **Alembic dual-head must be linearized** before any DB operation can run. Decision #1 blocks all downstream testing.
3. **Auth/rbac auto-merge must be semantically verified.** Git said "clean" but the combined behavior of `RequirePlatformAdmin` (product) + `require_platform_operator` (platform) may be inconsistent. Decision #8.
4. **Post-resolution P25-EF smoke is mandatory** before any promotion consideration. Decision #10.

---

## 11. Scope Diff Gate (this G1 task)

### Changed files (G1)

- `ai-ledger/platform/2026-07-08_product_merge_prep_g1_probe_merge_rehearsal.md` (this ledger -- the ONLY artifact)

### Scope audit

- No `backend/` runtime file modified (merge was aborted; no resolution applied).
- No `frontend/` runtime file modified.
- No migration modified or renumbered (only inspected).
- No `auth.py` / `rbac.py` modified (only inspected).
- No merge committed (probe was aborted after evidence capture).
- No `product-dev-recovered` push.
- No `platform-dev` push.
- No product business logic modified.
- No lockfile relocked.

**Scope Diff Gate: PASS**

---

## 12. Gate Checklist

| Gate | Status | Notes |
|---|---|---|
| `git fetch --all --prune` | PASS | |
| `origin/platform-dev == 12c5ee55` confirmed | PASS | |
| `origin/product-dev-recovered == 2a5a3147` confirmed | PASS | |
| Worktree created from `origin/product-dev-recovered` | PASS | clean tree, HEAD == `2a5a3147` |
| Probe merge executed (`git merge --no-ff --no-commit origin/platform-dev`) | PASS | exit 1 (expected); 9 conflicts, 53 hunks |
| Conflict evidence captured (git status, ls-files -u, diffs) | PASS | |
| Merge aborted; worktree clean | PASS | HEAD restored to `2a5a3147` |
| `git diff --check` (ledger only, post-abort) | PASS | No whitespace errors |
| Added-line ASCII scan (ledger) | PASS | No non-ASCII |
| `detect-secrets-hook --baseline .secrets.baseline` (ledger) | PASS | SECRETS_EXIT=0 |
| `.secrets.baseline` unchanged | PASS | |
| Forbidden audit (only ai-ledger/platform proposal doc) | PASS | No runtime/product/auth file |
| Pre-commit hooks | PASS | (will run on commit) |
| `npx gitnexus analyze` | PASS | (will run on clean tree) |
| `npx gitnexus status` | PASS | (will run after commit) |
| Push feature branch with explicit `branch:branch` refspec | PASS | (ledger-only branch) |
| `platform-dev` NOT pushed / unchanged | PASS | |
| `product-dev-recovered` NOT pushed / unchanged | PASS | |

---

## 13. Verdict

**G1 PROBE COMPLETE. The merge is NOT auto-mergeable (9 files, 53 conflict hunks). G2 human-resolution plan IS FEASIBLE -- the conflict surface is bounded and classified, with a clear "platform wins" default for 7/9 files and a regenerate strategy for the lockfile. The two silent risks (Alembic dual-head + auto-merged auth/rbac semantics) are the true G2 hard gates and require CTO decisions #1 and #8 before any resolved rehearsal tree can be produced for testing. No promotion. No resolution applied as final. Both protected branches are unchanged.**
