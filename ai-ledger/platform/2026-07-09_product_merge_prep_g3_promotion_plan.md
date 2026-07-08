# Product-Line Merge Preparation Gate 3 -- Promotion Plan (No Merge)

| Field | Value |
|---|---|
| **Task ID** | G3 (Product Merge Prep Gate 3 -- Promotion Plan) |
| **Date** | 2026-07-09 |
| **Mode** | **PLAN-ONLY** -- documentation and evidence closeout. No merge executed, no push to `product-dev-recovered`, no promotion. |
| **Branch** | `codex/product-merge-prep-g2-resolved-merge-rehearsal-2026-07-08` |
| **Worktree** | `_mergeresolve_g2_2026-07-08` |
| **Base (HEAD at start)** | `2dd1d4e6` (G2-R3 validation ledger) |
| **Predecessor** | G2-R3 confirmed D=0, PROCEED_TO_G3_PROMOTION_PLAN |
| **Result** | **GO to G4 conditional on CTO acceptance. No automatic merge.** |

---

## 1. Source / Target State

All SHAs captured from `git fetch origin` on 2026-07-09.

| Ref | SHA | Description |
|---|---|---|
| `origin/platform-dev` | `12c5ee557876498240b1a36cc850d030d7bd8293` | Platform source branch (unchanged since G2) |
| `origin/product-dev-recovered` | `66e8371bf159fff4c2e8ea526a2c842da0783775` | Product target branch (current remote tip) |
| G2 resolved rehearsal tip | `2dd1d4e69f806d126aee1773c1b85d0548d10ee2` | This branch HEAD (G2-R3 ledger commit) |
| merge-base(platform-dev, product-dev-recovered) | `8332f81e78a7103a7271d7199067f82c461a8ada` | Common ancestor for three-way merge |
| G2 merge commit | `c0ee5f7879af8a0b04958f966cb4649e5aed9ff1` | Resolved merge rehearsal (Decisions A-G applied) |
| G2 merge parent 1 (product at merge) | `2a5a31479faf8cf64e87cb5ba0fc4a7092f6d3f5` | Product snapshot base used for G2 rehearsal |
| G2-R2 repair commit | `6ab5b32dda4973c7226d5d071cbdd0d7dc6c3432` | Fixed 10 D-class merge regressions |
| G2-R3 validation ledger commit | `2dd1d4e69f806d126aee1773c1b85d0548d10ee2` | Full validation evidence, D=0 confirmed |
| G2-R1 classification commit | `baf79d33` | Failure classification: A=16, B=6, C=66, D=10 |

### Product-dev-recovered advancement since G2 merge

The G2 rehearsal was based on `2a5a3147` (then `6bcc38f9`). Since then,
`product-dev-recovered` has advanced by 5 commits to `66e8371b` (U6-I6
onboarding e2e closeout):

```
66e8371b merge: U6-I6 onboarding e2e closeout
4e9a0606 docs(U6-I6): record R1 head alignment evidence
6623d561 test(U6-I6): align U6F closeout alembic head
4c4b2aae docs(U6-I6): record closeout gate evidence
aa566b1d test(U6-I6): add onboarding e2e closeout gate
```

**Impact**: G4 promotion must re-merge onto the latest `66e8371b` tip. The
base-advancement artifacts (u6i5 files missing in G2 rehearsal) will be
re-included automatically.

---

## 2. Final Resolution Inventory

The G2 rehearsal applied 7 CTO decisions (A-G). G2-R1 surfaced 10 D-class
regressions; G2-R2 resolved all 10. The final resolution policy for G4:

### 2.1 Alembic Migrations (Decision A + verified in G2-R3)

| Item | Resolution |
|---|---|
| Platform `020`/`021` collision | Renumbered to `029_durable_approval_store` and `030_platform_backup_status_source` |
| Chain | `028_owner_credential_setup_tokens` (product head) -> `029` -> `030` (HEAD) |
| Product `020`/`021` | Untouched, remain in original positions |
| `alembic heads` | Single head `030_platform_backup_status_source` |
| `alembic upgrade head` | `001 -> 030` verified clean on fresh throwaway DB |

### 2.2 Platform API Files (Decision B)

| File | Resolution |
|---|---|
| `backend/api/v1/platform/audit.py` | Platform-wins (carries `require_platform_operator` + `get_platform_db`) |
| `backend/api/v1/platform/stats.py` | Platform-wins |
| `backend/api/v1/platform/tenants.py` | Platform-wins |
| `backend/api/v1/platform/health.py` | `/health` and `/info` remain **public** (G2-R2: removed `RequirePlatformAdmin` that merged from product side) |
| `get_platform_db` | System-scope session wiring (platform version wins) |
| `require_platform_operator` | Identity-only guard retained (platform version) |
| `redact_metadata` | Platform version wins |

### 2.3 Platform Tests (Decision C)

| File | Resolution |
|---|---|
| `backend/tests/test_platform_audit_api.py` | Platform side |
| `backend/tests/test_platform_stats_api.py` | Platform side |

### 2.4 Documentation (Decision D)

| File | Resolution |
|---|---|
| `docs/ai/README.md` | Additive union (product + platform sections) |

### 2.5 Frontend Union (Decision E)

| File | Resolution |
|---|---|
| `frontend/src/components/layout/Sidebar.tsx` | Union of product nav + platform nav entries |
| `frontend/src/router/AppRouter.tsx` | Union of product routes + platform routes |
| Guard layers | Both coexist (product `RequirePlatformAdmin` + platform `require_platform_operator`) |

### 2.6 Lockfile (Decision F)

| File | Resolution |
|---|---|
| `frontend/pnpm-lock.yaml` | Accept platform side, regenerate with `pnpm install` (exit 0) |
| `frontend/package.json` | Union of dependencies |

### 2.7 Auth / RBAC (Decision G + G2-R2 fixes)

| Item | Resolution |
|---|---|
| Product `RequirePlatformAdmin` (`backend/api/v1/rbac.py`) | Retained (product platform-admin dependency) |
| Platform `require_platform_operator` (`backend/api/v1/platform/p10/guard.py`) | Retained (identity-only guard) |
| Product U6 auth/RBAC | Both retained alongside platform P10/P25 |
| `AUTH_DEPENDENCY_NAMES` | G2-R2: added `require_platform_operator` for compliance counting |
| `classify_route` if-elif ordering | G2-R2: platform guard check FIRST, before `AUTH_DEPENDENCY_NAMES` membership |
| `PLATFORM_PUBLIC_ALLOWLIST` | G2-R2: `/health`, `/info` exempted from auth-dep requirement |

### 2.8 RBAC Permission Registry Drift Gate (G2-R2 fix)

| Item | Resolution |
|---|---|
| False-positive token filtering | G2-R2: exclude `__tests__` files, add prefix denylist (`node:`, `denied:`) |
| Permission weakening | **None** -- scan filters only, no permissions removed or weakened |

---

## 3. Validation Summary (from G2-R3)

All results from `ai-ledger/platform/2026-07-09_product_merge_prep_g2_r3_full_rehearsal_validation.md`.

| Validation Item | Result | Source |
|---|---|---|
| D-class regression suite | **62/62 PASS** | G2-R3 Section 3 |
| Broader auth/RBAC/platform | 108 passed, 3 failed (all Category C: `getaddrinfo`) | G2-R3 Section 4 |
| Alembic heads | **Single head** `030_platform_backup_status_source` | G2-R3 Section 5.1 |
| Alembic migration tests | 4 passed, 5 failed (all Category C: `KeyError POSTGRES_DB`) | G2-R3 Section 5.2 |
| Frontend build | **SUCCESS** (1269 modules, 8.74s) | G2-R3 Section 6.1 |
| Frontend product tests (`src/tests/`) | **9 files, 81/81 PASS** | G2-R3 Section 6.2 |
| Frontend platform tests (`__tests__/`) | **21 files, 333/333 PASS** | G2-R3 Section 6.3 |
| P25 route smoke | **19/19 HTTP 200**, 0 forbidden controls | G2-R3 Section 7.1 |
| P25 identity smoke | **5/6** (1 pre-existing: tenant_context 500) | G2-R3 Section 7.2 |
| TenantContextMissingError | **0** | G2-R3 Section 7.3 |
| **D-class count** | **0** | G2-R3 Section 9 |

### Failure classification (final, from G2-R3)

| Class | Count | Description |
|---|---|---|
| A (merge-introduced, blocking) | 0 | None |
| B (pre-existing code bug) | 1 | `tenant_context_admin_deny` returns 500 |
| C (environmental / infrastructure) | 9 | DNS, Postgres env vars, UUIDv1 seed data |
| D (merge-introduced regression) | 0 | All 10 resolved by G2-R2 |

---

## 4. Remaining Non-Merge Blockers / Caveats

These items do NOT block the G2 rehearsal verdict (D=0) but must be tracked
before production deployment or customer release.

### 4.1 tenant_context_admin_deny 500 (Category B -- pre-existing)

**Issue**: When a tenant-context super_admin JWT is presented to a
`require_platform_operator`-guarded endpoint, the guard attempts to resolve the
tenant schema via asyncpg. On the smoke DB (no tenant schema provisioned), this
fails with an unhandled 500 instead of a clean 401/403 denial.

**Classification**: Pre-existing robustness gap, NOT introduced by the G2 merge.
Observed in P25-EF (before G2-R1) and persists identically after G2-R2.

**Risk**: The endpoint fails-closed (500, not 200 -- the tenant-context admin is
NOT admitted). However, a 500 is not a clean denial and should be a 401/403.

**Action required before customer release**: Add try/except around the
asyncpg tenant-schema resolution in the `require_platform_operator` guard to
catch schema-not-found and return a clean 401/403.

### 4.2 Alembic env var KeyError POSTGRES_DB (Category C -- environmental)

**Issue**: 5 migration infrastructure hardening tests fail with
`KeyError: 'POSTGRES_DB'` because the local test environment does not set
Postgres environment variables.

**Classification**: Environment configuration gap. NOT a merge regression.

**Risk**: Promotion gate validation cannot rely on these tests unless run with
the correct environment (`POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`,
etc.).

**Action required before promotion**: Ensure the G4 promotion worktree has all
required environment variables configured. Do not interpret unconfigured
test-suite failures as green.

### 4.3 Fresh DB version_num width issue (Lubuntu independent verification)

**Issue**: On a fresh database, Alembic 1.18 creates the
`alembic_version.version_num` column as `VARCHAR(32)`. Some migration revision
IDs exceed 32 characters, causing a value-too-long error during
`alembic upgrade head`.

**Mitigation in repo**: `backend/alembic/env.py` includes an auto-widen
mechanism (`ALEMBIC_VERSION_NUM_LENGTH = 128`) that runs before migration to
ensure the column is `VARCHAR(128)`.

**Risk**: If the auto-widen hook is not invoked (e.g., bare `alembic stamp`
without the custom env runner), the `VARCHAR(32)` default persists.

**Action required before fresh deploy**: Verify `alembic upgrade head` is run
through the repo's custom `env.py` entrypoint, not a bare Alembic CLI invocation.
Alternatively, explicitly accept the risk with CTO sign-off if the deploy uses a
pre-provisioned DB schema with `VARCHAR(128)`.

### 4.4 Full backend suite has env-dependent failures

**Issue**: The full backend test suite has failures that depend on environment
configuration (live DB DNS, Postgres env vars, provisioned tenant schemas). These
cannot be relied upon as green in an unconfigured environment.

**Classification**: Environmental, NOT merge regressions.

**Action required before promotion**: The G4 promotion gate must run the
targeted suites (D-class, auth/RBAC, platform, Alembic heads) in a properly
configured environment. Do not use the unconfigured full-suite failure count as
evidence of either pass or fail.

---

## 5. Promotion Preconditions

Before any real `product-dev-recovered` promotion, the CTO must require all of
the following. These are **gating conditions for G4**, not suggestions.

| # | Precondition | Verification |
|---|---|---|
| 1 | Protected target branch tip unchanged from G3 plan (or plan refreshed) | `git rev-parse origin/product-dev-recovered` == `66e8371b` or G3 plan updated |
| 2 | Clean promotion worktree from `origin/product-dev-recovered` | New worktree, no pre-existing dirty state |
| 3 | Apply same resolution policy as G2 (Decisions A-G + G2-R2 fixes) | Re-resolve conflicts using the documented policy |
| 4 | `alembic upgrade head` on throwaway DB with correct env | All env vars set; `PYTHONIOENCODING=utf-8` for emoji migrations |
| 5 | Frontend build succeeds | `pnpm build` exit 0, 0 TypeScript errors |
| 6 | Product smoke/tests pass | `src/tests/` suite: all PASS |
| 7 | Platform P25 smoke: 19/19 HTTP 200, 0 forbidden controls | `verify/p25ef/run_smoke.py` |
| 8 | Identity smoke: 6/6 or explicit accepted known issue | tenant_context 500 tracked or fixed |
| 9 | No backend 5xx in platform smoke (page loads) | 0 page-load 5xx; API 5xx only from environmental seed data |
| 10 | D count remains 0 | D-class suite: all PASS |

---

## 6. Promotion Procedure Draft (for future G4)

This is the high-level procedure for G4 execution. **Do NOT execute these steps
now.** They are documented here for CTO review and future execution.

```
Step 1:  git fetch origin
         Record SHA of origin/product-dev-recovered (must match G3 plan or refresh plan)

Step 2:  Create fresh promotion worktree
         git worktree add _promo_g4_YYYY-MM-DD origin/product-dev-recovered
         cd _promo_g4_YYYY-MM-DD
         git checkout -b codex/product-merge-prep-g4-promotion-YYYY-MM-DD

Step 3:  Merge platform-dev into the promotion branch
         git merge origin/platform-dev
         (Conflicts will arise in the same files as G2 -- apply Decisions A-G)

Step 4:  Apply resolution policy (same as G2)
         - Decision A: Renumber platform migrations to 029/030
         - Decision B: Platform-wins for audit/stats/tenants
         - Decision C: Platform tests for audit/stats
         - Decision D: Additive union for docs/ai/README.md
         - Decision E: Union for Sidebar.tsx + AppRouter.tsx
         - Decision F: Accept platform pnpm-lock, regenerate
         - Decision G: Both auth guards coexist
         - G2-R2 fixes: health.py public, AUTH_DEPENDENCY_NAMES updated,
           classify_route if-elif ordering, RBAC drift scan filters

Step 5:  Run validation gates
         - alembic heads (single head 030)
         - alembic upgrade head (throwaway DB, correct env)
         - D-class regression suite (62/62 PASS)
         - Frontend build (SUCCESS)
         - Frontend tests: src/tests/ + platform __tests__ (414/414)
         - P25 route smoke (19/19 HTTP 200, 0 forbidden)
         - P25 identity smoke (6/6 or accepted known issue)
         - detect-secrets-hook --baseline .secrets.baseline
         - git diff --check

Step 6:  Commit resolved merge + evidence ledger

Step 7:  Request CTO approval to push to product-dev-recovered
         (ONLY after CTO signs off -- no automatic merge)

Step 8:  Upon CTO approval:
         git push origin <promotion-branch>:product-dev-recovered
         (With explicit branch:branch refspec)
```

### Key differences from G2 rehearsal

- G4 must merge onto the **latest** `origin/product-dev-recovered` (`66e8371b`),
  not the snapshot `2a5a3147` used for G2. The base-advancement artifacts
  (u6i5/u6i6 files) will be included automatically.
- G4 must verify that the U6-I6 closeout commits (alembic head alignment, test
  gates) do not conflict with the platform migration chain.
- G4 should provision a tenant schema in the smoke DB to verify
  `tenant_context_admin_deny` behavior (or explicitly accept the known 500).

---

## 7. Go / No-Go Recommendation

### Recommendation: **GO to G4 -- conditional on CTO acceptance**

**Rationale**:
- D=0: all 10 merge-introduced regressions resolved and confirmed by full
  re-validation (G2-R3).
- Alembic: single head, clean chain, `upgrade head` verified.
- Frontend: 414/414 tests pass, production build succeeds.
- P25 smoke: 19/19 routes HTTP 200, 0 forbidden controls, 0 TCM errors.
- All failures are pre-existing (B=1) or environmental (C=9), none are merge
  regressions.
- All stop conditions from G2-R3 pass.

### Conditions for GO

1. CTO accepts this G3 plan and the G2-R3 validation evidence.
2. Product line confirms readiness (no concurrent changes to
   `product-dev-recovered`).
3. G4 promotion worktree is created fresh from the latest
   `origin/product-dev-recovered`.
4. G4 re-applies the G2 resolution policy (Decisions A-G + G2-R2 fixes).
5. All preconditions in Section 5 are met before any push.

### What does NOT happen now

- **No automatic merge.** This plan is documentation only.
- **No push to `product-dev-recovered`.** The protected branch remains unchanged.
- **No promotion.** G4 execution requires explicit CTO approval.

---

## 8. Validation Gates for G3 Itself

| Gate | Command | Result |
|---|---|---|
| `git diff --check` | whitespace/conflict markers | PASS |
| ASCII scan | no non-ASCII in added lines | PASS |
| `detect-secrets-hook --baseline .secrets.baseline` | secret scan | PASS |
| `.secrets.baseline` unchanged | hash comparison | PASS |
| Forbidden file audit | docs/ledger only (no runtime/migration/lockfile) | PASS |
| GitNexus analyze/status | `npx gitnexus status` | See Section 9 |
| Worktree clean | no staged source files | PASS (ledger-only) |

---

## 9. GitNexus Result

GitNexus analyze/status was run against the G2 rehearsal branch. The indexed
repository reflects the G2-R3 tip (`2dd1d4e6`). No new code was introduced in
G3 (documentation-only), so the knowledge graph is unchanged from G2-R3.

---

## 10. Risk Assessment

| Risk | Level | Mitigation |
|---|---|---|
| Large cross-track merge (platform -> product) | MEDIUM | All conflict decisions traceable to CTO directives A-G; Alembic single-head proven; real-stack smoke green |
| Base advancement (product-dev-recovered +5 commits since G2) | LOW-MEDIUM | G4 must re-merge onto latest tip; U6-I6 closeout commits need compatibility check |
| tenant_context_admin_deny 500 (pre-existing) | LOW | Fails-closed (not admitted); fix tracked for customer release |
| Fresh DB version_num width | LOW | Auto-widen hook in `env.py`; verify through custom entrypoint |
| Env-dependent test failures misread as green | LOW | Explicitly document required env vars; never use unconfigured failures as evidence |

---

## 11. Confirmation: Protected Branches Unchanged

| Branch | SHA at G3 start | SHA at G3 end | Changed? |
|---|---|---|---|
| `origin/platform-dev` | `12c5ee55` | `12c5ee55` | NO |
| `origin/product-dev-recovered` | `66e8371b` | `66e8371b` | NO |

Both protected branches remain unchanged. Only the feature branch
`codex/product-merge-prep-g2-resolved-merge-rehearsal-2026-07-08` was advanced
with the G3 plan ledger.
