# Product-Line Merge Preparation Gate 3-R1 -- Promotion Plan Refresh Against Latest Product Target

| Field | Value |
|---|---|
| **Task ID** | G3-R1 (G3 Promotion Plan, Round 1 -- Latest Target Refresh) |
| **Date** | 2026-07-09 |
| **Mode** | **DOCS/LEDGER-ONLY** -- refresh G3 plan against latest `origin/product-dev-recovered`. No merge, no promotion. |
| **Branch** | `codex/product-merge-prep-g2-resolved-merge-rehearsal-2026-07-08` |
| **Worktree** | `_mergeresolve_g2_2026-07-08` |
| **Base (HEAD at start)** | `7a5e41c5` (G3 promotion plan) |
| **Predecessor** | G3 promotion plan documented resolution policy, GO to G4 conditional on CTO |
| **Result** | **PROCEED_TO_G4** -- latest target drift does not change G3 resolution plan |

---

## 1. Base Proof Gate

| Check | Result |
|---|---|
| `git fetch --all --prune` | Executed 2026-07-09 |
| Working tree | Pre-existing artifacts only (no source code modifications) |
| HEAD | `7a5e41c5` (G3 promotion plan tip) |

---

## 2. Source / Target SHA Capture

All SHAs captured from `git fetch --all --prune` on 2026-07-09.

| Ref | SHA | Status |
|---|---|---|
| `origin/platform-dev` | `12c5ee557876498240b1a36cc850d030d7bd8293` | **UNCHANGED** since G2 |
| `origin/product-dev-recovered` | `19f6afde9c351de0d8d29b30fbf1ce8ba0462961` | **ADVANCED** from `66e8371b` |
| G3 plan recorded target | `66e8371bf159fff4c2e8ea526a2c842da0783775` | (now superseded) |
| merge-base(platform-dev, product-dev-recovered) | `8332f81e78a7103a7271d7199067f82c461a8ada` | **UNCHANGED** |

### Delta since G3 recorded target

```
19f6afde..origin/product-dev-recovered:
66e8371b..origin/product-dev-recovered = +3 commits
```

---

## 3. New Product Commits (+3, U6-K SMTP Email Delivery)

| SHA | Message |
|---|---|
| `19f6afde` | Merge remote-tracking branch 'origin/opencode/u6k-production-smoke-email-delivery-2026-07-09' into codex/merge-u6k-2026-07-09 |
| `48599670` | docs(U6-K): record SMTP delivery validation evidence |
| `6987eff7` | feat(U6-K): add production SMTP email delivery |

**Note**: G3 plan recorded +5 commits from `2a5a3147` to `66e8371b` (U6-I6 closeout).
This R1 refresh captures an additional +3 commits from `66e8371b` to `19f6afde` (U6-K).
Total advancement since G2 merge base: +8 commits.

---

## 4. Drift Scan -- Changed Files (66e8371b..19f6afde)

| Status | File | Category |
|---|---|---|
| M | `.env.example` | Environment config |
| M | `backend/.env.example` | Environment config |
| M | `backend/core/config.py` | Product config (+17 lines SMTP settings) |
| M | `backend/services/email_delivery.py` | Product service |
| M | `backend/services/onboarding_service.py` | Product service |
| A | `backend/tests/test_u6k_production_smtp_email_delivery.py` | Product test |
| A | `ai-ledger/product-ai/2026-07-09_u6k_production_smtp_email_delivery.md` | Ledger |

**Total: 7 files (5 modified, 2 added)**

---

## 5. Drift Impact Assessment

### 5.1 Critical Category Scan

| Category | Files Changed | Impact |
|---|---|---|
| **Alembic migrations** (`backend/alembic/versions/*.py`) | 0 | NONE -- no new migration revisions |
| **Auth/RBAC/Session** (`auth.py`, `rbac.py`, `security.py`, `session.py`) | 0 | NONE -- no auth changes |
| **Lockfile/Package** (`pnpm-lock.yaml`, `package.json`) | 0 | NONE -- no frontend dependency changes |
| **G1/G2 conflict files** (audit, stats, tenants, health, Sidebar, AppRouter, README) | 0 | NONE -- no overlap with previously conflicted files |
| **Frontend tests** (`src/tests/`, `__tests__/`) | 0 | NONE -- no test expectation changes |

### 5.2 File-Level Conflict Risk Analysis

| File | Platform-dev modifies it? | U6-K modifies it? | Conflict risk |
|---|---|---|---|
| `backend/core/config.py` | NO (0 diff vs merge-base) | YES (+17 lines, additive SMTP config) | **NONE** -- platform side untouched, U6-K is pure additive |
| `backend/services/email_delivery.py` | NO (file does not exist on platform-dev) | YES (modified) | **NONE** -- product-only file |
| `backend/services/onboarding_service.py` | NO (file does not exist on platform-dev) | YES (modified) | **NONE** -- product-only file |
| `.env.example`, `backend/.env.example` | NO | YES (additive) | **NONE** -- config-only |
| `test_u6k_*.py`, ledger | NO | YES (new) | **NONE** -- new additive files |

### 5.3 merge-base stability

The merge-base between `platform-dev` and `product-dev-recovered` remains
`8332f81e` -- unchanged since G2. The +3 U6-K commits are all descendants of
`66e8371b` which is a descendant of the merge-base. The three-way merge
geometry is stable.

### 5.4 Impact on G4 Promotion Plan

| G3 Plan Element | Affected by U6-K drift? |
|---|---|
| Alembic Decision A (029/030 renumber) | NO -- no new migrations |
| Platform API Decisions B/C (audit/stats/tenants/health) | NO -- U6-K does not touch these |
| Frontend union Decision E | NO -- U6-K has no frontend changes |
| Lockfile Decision F | NO -- U6-K has no lockfile changes |
| Auth/RBAC Decision G | NO -- U6-K does not touch auth |
| G2-R2 D-class fixes | NO -- U6-K does not touch test harness/health/scanner |
| Promotion procedure (Section 6) | MINOR -- target SHA must be updated from `66e8371b` to `19f6afde` |
| Promotion preconditions (Section 5) | NO -- all 10 preconditions remain valid |

**Conclusion**: The U6-K drift does NOT change the G3 resolution plan. Only the
target SHA reference needs updating.

---

## 6. Updated Promotion Target

| Field | G3 (stale) | G3-R1 (current) |
|---|---|---|
| `origin/product-dev-recovered` SHA | `66e8371b` | `19f6afde` |
| Total commits since G2 merge base | +5 (U6-I6) | +8 (U6-I6 + U6-K) |
| Resolution policy affected | -- | NO |

**G4 must merge onto `19f6afde`**, not `66e8371b`. The U6-K files will be
included automatically (they are product-side additions with no platform overlap).

---

## 7. tenant_context_admin_deny 500 -- CTO Decision Required

**Issue**: `require_platform_operator` guard crashes with HTTP 500 (not 401/403)
when presented with a tenant-context super_admin JWT and the tenant schema is
missing from the DB.

**Status**: Pre-existing, fail-closed. The tenant-context admin is **NOT admitted**
(returned 500, not 200). The access is correctly denied -- just via an unhandled
exception rather than a clean policy rejection.

**CTO must choose before G4:**

### Option A: Fix before G4 (recommended for production readiness)
- **Scope**: Small platform/product auth robustness task
- **Fix**: Add try/except in `require_platform_operator` around asyncpg tenant-schema
  resolution; return clean 401/403 on schema-not-found
- **Effort**: ~30 min code + test
- **Benefit**: Clean identity smoke 6/6, no 500 in production logs, no customer confusion

### Option B: Allow G4 with known issue
- **Rationale**: The endpoint fails-closed (denies access), does not admit tenant-context admin
- **Risk**: 500 in production logs, monitoring noise, poor error UX
- **Acceptance**: CTO must explicitly sign off on the known issue
- **Tracking**: Must be tracked for customer release hardening

**This task (G3-R1) does not fix it.** The decision is deferred to CTO.

---

## 8. CTO Recommendation

**PROCEED_TO_G4**

The latest target drift (+3 commits, U6-K SMTP email delivery) is entirely
product-side additive with zero overlap on migration, auth/RBAC/session,
lockfile, frontend, or previously-conflicted files. The merge-base is stable.
The G3 resolution plan (Decisions A-G + G2-R2 fixes) remains valid unchanged.

The only update required is the target SHA: G4 must merge onto `19f6afde`
instead of the G3-recorded `66e8371b`.

---

## 9. Stop Condition Check

| Stop Condition | Triggered? |
|---|---|
| New Alembic revisions introduced | NO |
| Auth/RBAC/session files touched | NO |
| Previously-conflicted files touched | NO |
| Lockfile/package touched | NO |
| Product smoke/test expectations changed | NO |
| merge-base shifted | NO |

**No stop conditions triggered.**

---

## 10. Validation Gates

| Gate | Result |
|---|---|
| `git diff --check` | PASS |
| ASCII scan | CLEAN |
| `detect-secrets-hook --baseline .secrets.baseline` | PASS (pre-commit) |
| `.secrets.baseline` | Unchanged |
| Forbidden file audit | Docs/ledger only |
| Worktree clean | No staged source files |

---

## 11. Scope Diff (G3-R1)

```
ai-ledger/platform/2026-07-09_product_merge_prep_g3_r1_latest_target_refresh.md  (new)
```

1 file added, 0 deletions, 0 source code, 0 migrations, 0 lockfiles.
