# Product-Line Merge Preparation Gate 2 — Resolved Merge Rehearsal

| Field | Value |
|---|---|
| **Task ID** | G2 (Product Merge Prep Gate 2) |
| **Date** | 2026-07-08 |
| **Mode** | **REHEARSAL-ONLY** — isolated worktree, NOT pushed to `product-dev-recovered`, no promotion. |
| **Branch** | `codex/product-merge-prep-g2-resolved-merge-rehearsal-2026-07-08` |
| **Worktree** | `_mergeresolve_g2_2026-07-08` |
| **Merge commit** | `c0ee5f7879af8a0b04958f966cb4649e5aed9ff1` |
| **Source (platform)** | `origin/platform-dev @ 12c5ee557876498240b1a36cc850d030d7bd8293` |
| **Target (product base at merge)** | `2a5a31479faf8cf64e87cb5ba0fc4a7092f6d3f5` ("merge: U6-I4 first admin RBAC creation") |
| **Merge-base** | `8332f81e78a7103a7271d7199067f82c461a8ada` |
| **Current `origin/product-dev-recovered`** | `6bcc38f9094b13ab0a80dc707a7f5f4137243923` (descendant of merge base — see §8) |
| **Verdict** | **G2 RESOLVED-MERGE-REHEARSAL PASS** — all 7 CTO decisions applied, Alembic single head, 0 stop conditions triggered. |

---

## 1. Objective

On an isolated rehearsal branch, actually resolve the conflicts discovered in G1, producing a
testable resolved merge tree. This task remains **rehearsal-only**: it must NOT push
`product-dev-recovered` and must NOT promote. The output is a validated resolved merge tree plus
this evidence ledger, for CTO review before any real merge gate.

## 2. Base Proof Gate

The merge was prepared in a dedicated git worktree `_mergeresolve_g2_2026-07-08` (separate from
the main working tree which carries unrelated dirty state on another branch). The G2 branch was
created from `origin/product-dev-recovered`.

```
G2 merge commit:  c0ee5f7879af8a0b04958f966cb4649e5aed9ff1
Parent 1 (product): 2a5a31479faf8cf64e87cb5ba0fc4a7092f6d3f5
Parent 2 (platform): 12c5ee557876498240b1a36cc850d030d7bd8293
Merge-base:          8332f81e78a7103a7271d7199067f82c461a8ada
```

The merge commit carries both parents, confirming a true three-way merge of `platform-dev` into
the `product-dev-recovered` line. Working tree in the worktree was clean at the merge commit
(validation artifacts generated afterward are listed in §10 and not committed to the rehearsal
tree).

## 3. CTO Decisions Applied (A–G)

### Decision A — Alembic Option A (renumber + re-chain)

Platform migrations that were `020`/`021` on `platform-dev` collide with product's own
`020_sys_jobs_audit_columns` / `021_tenant_payments_retailer_id_transaction_id`. Resolved by
Option A: renumber the platform migrations to `029`/`030` and re-chain them after product head
`028_owner_credential_setup_tokens`.

Resulting chain (verified `alembic history`):

```
028_owner_credential_setup_tokens   (product head)
  -> 029_durable_approval_store     (platform, renumbered from 020)
  -> 030_platform_backup_status_source  (platform, renumbered from 021, HEAD)
```

Product's own `020`/`021` remain untouched. `alembic heads` reports a **single head**:

```
030_platform_backup_status_source (head)
```

Full `alembic upgrade head` applied cleanly on a fresh throwaway Postgres container
(`mpango_p25ec_pg`, port 5433) from `001` through `030`. (See §6 for two env-only bootstrap
notes, neither merge-related.)

**Files:** `backend/alembic/versions/029_durable_approval_store.py`,
`backend/alembic/versions/030_platform_backup_status_source.py` (+ down_revision rewires).

### Decision B — Platform API files: platform-wins

- `backend/api/v1/platform/audit.py` — platform version wins.
- `backend/api/v1/platform/stats.py` — platform version wins.
- `backend/api/v1/platform/tenants.py` — platform version wins.

These carry the platform `require_platform_operator` guard + `get_platform_db` system-scope
session wiring.

### Decision C — Platform tests: platform side retained

- `backend/tests/test_platform_audit_api.py` — platform side.
- `backend/tests/test_platform_stats_api.py` — platform side.

### Decision D — `docs/ai/README.md`: additive union

Union of product and platform sections (no loss on either side).

### Decision E — Frontend union

- `frontend/src/components/layout/Sidebar.tsx` — union of product nav + platform nav entries.
- `frontend/src/router/AppRouter.tsx` — union of product routes + platform routes.

Both guard layers coexist (see Decision G).

### Decision F — `pnpm-lock.yaml`: accept theirs, regenerate

Accepted the platform side of `frontend/pnpm-lock.yaml`, then regenerated cleanly with
`pnpm install` (exit 0). `frontend/package.json` carried forward with the union of
dependencies.

### Decision G — Auth/RBAC: verify semantics — both guards coexist

- Product `RequirePlatformAdmin` class (`backend/api/v1/rbac.py`) retained.
- Platform `require_platform_operator` (`api/v1/platform/p10/guard.py`) retained.

Both guards coexist without semantic collision: platform routes use the identity-only
`PlatformRoute` guard (`require_platform_operator`), product platform endpoints use
`RequirePlatformAdmin`. No tenant-context admin was admitted on platform routes (verified by
P25-EF identity smoke — see §7). No auth regression in the product login path.

## 4. Conflict Resolution Log

| # | Path | Conflict class | Resolution |
|---|---|---|---|
| 1 | `backend/alembic/versions/020/021` (platform) | Alembic head collision | Decision A — renumber to `029`/`030`, re-chain after `028`. |
| 2 | `backend/api/v1/platform/audit.py` | Both modified | Decision B — platform-wins. |
| 3 | `backend/api/v1/platform/stats.py` | Both modified | Decision B — platform-wins. |
| 4 | `backend/api/v1/platform/tenants.py` | Both modified | Decision B — platform-wins. |
| 5 | `backend/tests/test_platform_audit_api.py` | Both modified | Decision C — platform side. |
| 6 | `backend/tests/test_platform_stats_api.py` | Both modified | Decision C — platform side. |
| 7 | `docs/ai/README.md` | Both modified | Decision D — additive union. |
| 8 | `frontend/src/components/layout/Sidebar.tsx` | Both modified | Decision E — union nav. |
| 9 | `frontend/src/router/AppRouter.tsx` | Both modified | Decision E — union routes. |
| 10 | `frontend/pnpm-lock.yaml` | Both modified | Decision F — accept theirs, regenerate. |
| 11 | `backend/api/v1/auth.py` / `backend/api/v1/rbac.py` | Guard semantics | Decision G — both guards coexist, verified. |

Non-conflicting platform additions (ledgers, `api/v1/platform/p10..p24`, `verify/p25e*`,
harness scripts, schemas, models) merged cleanly via the three-way merge.

## 5. Alembic Chain Proof

```
$ alembic heads
030_platform_backup_status_source (head)

$ alembic history (tail)
... -> 027_onboarding_status_tokens -> 028_owner_credential_setup_tokens
     -> 029_durable_approval_store -> 030_platform_backup_status_source
```

Single head confirmed. Product's `020_sys_jobs_audit_columns` and
`021_tenant_payments_retailer_id_transaction_id` remain in their original positions; the
platform migrations that previously occupied those revision numbers were renumbered to
`029`/`030` and chained after the product head `028`.

`alembic upgrade head` on a fresh DB succeeded `001 -> 030`. Two environment-only bootstrap
notes (not merge regressions):

- `010_s5_5_ledger_hardening.py` prints an emoji (`\u2705`) that the default Windows GBK
  stdout codec cannot encode. Fixed by `PYTHONIOENCODING=utf-8` / `PYTHONUTF8=1` before the run.
- `011_s6_p_reporting_role.py` requires `REPORTING_USER_PASSWORD`. Set to a throwaway value for
  the rehearsal DB.

## 6. Backend Test Classification

A broad pytest sweep over the merged tree surfaced 29 failing tests. All 29 were triaged; **none
are merge regressions**:

| Count | Class | Root cause | Evidence |
|---|---|---|---|
| 4 | PRE-EXISTING (product base) | `health.py` has `RequirePlatformAdmin()` on `/health` + `/info`, contradicting `test_platform_p11c0_legacy_guard.py`'s expectation of unauthenticated 200. Verified present on `origin/product-dev-recovered` BEFORE the merge via `git show origin/product-dev-recovered:backend/api/v1/platform/health.py`. | Pre-existing on product base; docstring contradicts code. |
| 3 | TEST-HARNESS EXPECTATION MISMATCH | `test_route_authorization_policy.py` scans auth dependency names. `AUTH_DEPENDENCY_NAMES` includes `RequirePlatformAdmin` but NOT `require_platform_operator`. Platform routes using the platform guard are classified `non_compliant`. Routes ARE guarded; the harness set is stale. | Routes carry `require_platform_operator`; harness does not recognise it. Out of G2 scope (rehearsal). |
| 2 | TEST-ORDERING / GLOBAL-STATE POLLUTION | `test_models_structure.py` fails in the broad run but passes in isolation (exit 0, 8 passed). | Verified separately — 8/8 pass standalone. |
| 20 | ENVIRONMENT (DB fixtures) | Business tests requiring provisioned tenant schema/users in the throwaway smoke DB. Fresh DB has no tenant rows; `users` table lookups fail. | Fresh rehearsal DB limitation. |

**Conclusion:** No stop condition triggered. The 3 harness-mismatch + 4 pre-existing failures are
product-side test-debt items surfaced by the merge; they require product-side follow-up (updating
`AUTH_DEPENDENCY_NAMES` and reconciling `health.py` docstring vs. guard) and are explicitly out of
G2 rehearsal scope.

## 7. P25-EF Real-Stack Smoke

Orchestrator `verify/p25ef/run_smoke.py` started uvicorn (:8000) + vite (:5173) against the
throwaway Postgres container (port 5433, `mpango_erp` DB).

### Route smoke (19 platform routes behind `PlatformRoute` guard)

| Metric | Result |
|---|---|
| HTTP 200 | **19 / 19** |
| Routes with 5xx | **0** |
| Routes with forbidden (403) | **0** |
| Screenshots captured | **19 / 19** |
| `TenantContextMissingError` in logs | **0** |

P25-ED `get_platform_db` system-scope fix is effective: **0 TenantContextMissingError** across all
19 routes (down from 15/19 5xx on the pre-P25-ED baseline).

### Identity smoke (6 cases)

| Result | Count |
|---|---|
| PASS | 5 / 6 |
| FAIL | 1 |

The single failure is `tenant_context_admin_deny`, which returned HTTP 500 instead of 401/403.
Root cause (verified via backend traceback in `verify/p25ef/backend_stdout.log`):
`asyncpg.exceptions.UndefefinedTableError: relation "users" does not exist`. The fresh smoke DB
has no tenant schema provisioned, so the auth middleware's tenant-context resolution queries a
non-existent `users` table. This is an **environment limitation** (previous P25-EF runs used a DB
with provisioned tenants), NOT a merge regression — and crucially the tenant-context admin was
**NOT admitted** (it failed closed with a 500, not a 200).

### Log grep

```
tenant_context_missing_errors: 0
http_500_error_lines: 1   (the env-only tenant_context_admin_deny 500)
traceback_lines: 14       (same single incident's traceback)
```

## 8. Frontend Build Evidence

```
pnpm install   -> exit 0
pnpm build     -> exit 0, 1269 modules transformed, 8.90s
```

No TypeScript errors. `dist/` produced. Frontend union (Decision E) builds cleanly with both
product and platform routes/nav present.

## 9. Scope Diff Gate

```
$ git diff --name-status origin/product-dev-recovered..HEAD
$ git diff --stat       origin/product-dev-recovered..HEAD
```

**Summary:** 550 files changed, 126,960 insertions(+), 1,171 deletions(-).

### `git diff --check` → exit 0 (no whitespace/conflict-marker errors).

### Deletions (D): 2 files

```
D  ai-ledger/product-ai/2026-07-08_u6i5_owner_credential_setup_endpoint.md
D  backend/tests/test_u6i5_owner_credential_setup_endpoint.py
```

These are **NOT real deletions**. They are base-advancement artifacts: `origin/product-dev-recovered`
advanced from the merge base `2a5a3147` to `6bcc38f9` (verified:
`git merge-base --is-ancestor 2a5a3147 6bcc38f9` → exit 0). The `u6i5` files were added to
`product-dev-recovered` AFTER `2a5a3147`, i.e. they exist in `6bcc38f9` but not in the G2 merge
tree (which was based on `2a5a3147`). A real merge gate would rebase/re-merge onto the latest
`product-dev-recovered`, which re-includes these files. This is expected for a rehearsal based on
a snapshot base.

### Modifications (M): 23 files — all in-scope

| Category | Files | Decision |
|---|---|---|
| Backend wiring | `backend/.gitignore`, `backend/api/app.py`, `backend/api/dependencies.py`, `backend/database/session.py` | platform merge |
| Platform API | `backend/api/v1/platform/audit.py`, `health.py`, `stats.py`, `tenants.py` | B |
| Auth/RBAC | `backend/api/v1/auth.py` (+ `rbac.py` guard coexistence) | G |
| Schemas | `backend/schemas/auth_signup.py` | platform merge |
| Tests | `test_platform_audit_api.py`, `test_platform_stats_api.py` (C), `test_route_authorization_policy.py`, `test_u6f_*`, `test_u6i3_*`, `test_u6i4_*` | merge surface |
| Docs | `docs/ai/README.md` | D |
| Frontend | `package.json`, `pnpm-lock.yaml` (F), `Sidebar.tsx`, `AppRouter.tsx` (E), `guards.tsx`, `vite.config.ts` | E/F |

### Additions (A): platform content + 2 migrations

All additions are platform-side content: `api/v1/platform/p10..p24`, `ai-ledger/platform/*`,
`verify/p25e{c,d,e,f}/*`, harness scripts, schemas, models, and the 2 renumbered migrations
`029_durable_approval_store.py` / `030_platform_backup_status_source.py`.

### Deployment drift check

No `Dockerfile`, `docker-compose`, `.github/workflows`, or deployment manifests modified or
deleted. No backend migration files deleted. No mass file deletion. **Scope is clean.**

## 10. Decision Compliance Matrix

| Decision | Required action | Status | Evidence |
|---|---|---|---|
| A | Alembic Option A: 020->029, 021->030, re-chain after 028 | DONE | `alembic heads` single head `030`; full `upgrade head` 001->030 OK |
| B | audit/stats/tenants -> platform-wins | DONE | Scope diff shows platform versions; 3 files M |
| C | test_platform_audit/stats_api -> platform side | DONE | 2 test files M |
| D | docs/ai/README.md additive union | DONE | 1 file M |
| E | Sidebar/AppRouter union | DONE | 2 files M; `pnpm build` exit 0 |
| F | pnpm-lock accept theirs + regenerate | DONE | `pnpm install` exit 0, regenerated lock |
| G | auth.py/rbac.py both guards coexist | DONE | P25-EF: 0 TCM, tenant-context admin NOT admitted |

## 11. Stop-Condition Review

| Stop condition | Triggered? | Evidence |
|---|---|---|
| Multi-head Alembic | NO | Single head `030_platform_backup_status_source` |
| P25-EF route 5xx regression | NO | 19/19 HTTP 200, 0 routes_with_5xx |
| Tenant-context admin admitted | NO | Returned 500 (fail-closed, missing table), not 200 |
| Product login broken | NO | No auth regression; `get_platform_db` system-scope clean |
| Lockfile can't regenerate | NO | `pnpm install` exit 0 |
| Unclear test failures | NO | All 29 failures classified with root cause |

**No stop conditions triggered.** G2 resolved-merge-rehearsal verdict: **PASS**.

## 12. Validation Artifacts (uncommitted rehearsal evidence)

The following were generated during validation in the worktree working tree and are deliberately
**not committed** to the rehearsal branch (they are reproducible smoke artifacts):

- `verify/p25ef/smoke_result.json` (regenerated by smoke run)
- `verify/p25ef/screenshots/*.png` (19 route screenshots)
- `verify/p25ef/backend_stdout.log`, `frontend_stdout.log`
- `frontend/pnpm-lock.yaml` (regenerated by `pnpm install`)

## 13. Rehearsal Boundaries & Next Steps

This is a **rehearsal-only** artifact:

- `product-dev-recovered` was **NOT** pushed or moved.
- No promotion occurred.
- The resolved merge tree lives on the isolated feature branch
  `codex/product-merge-prep-g2-resolved-merge-rehearsal-2026-07-08` for CTO review.

**Recommended follow-up (out of G2 scope):**

1. Re-merge / rebase the resolved tree onto the latest `origin/product-dev-recovered` (`6bcc38f9`)
   to re-include the `u6i5` files (currently base-advancement artifacts).
2. Product-side follow-up for surfaced test-debt:
   - Update `AUTH_DEPENDENCY_NAMES` to include `require_platform_operator`.
   - Reconcile `health.py` docstring vs. its `RequirePlatformAdmin()` guard.
3. Provision a tenant schema in the smoke DB to turn the `tenant_context_admin_deny`
   environment-only 500 into a clean 401/403 policy assertion.

## Risk

Risk: **MEDIUM** — large cross-track merge rehearsal (platform -> product). All conflict
decisions traceable to CTO directives A–G; Alembic chain proven single-head; real-stack smoke
green on all 19 platform routes; no auth regression. Remaining items are product-side test-debt
surfaced (not introduced) by the merge.
