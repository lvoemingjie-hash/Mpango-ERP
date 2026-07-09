# DC-1B Release Candidate Evidence Pack

- **Date**: 2026-07-09
- **Pack ID**: DC-1B
- **Scope**: Docs / evidence only. No runtime code, no migrations, no frontend, no package/lockfile changes.
- **Predecessor**: DC-1A exact VPS runtime baseline (PASS).
- **Production commit (verified baseline)**: `9bb2b3090c946d5edb6a4d17958fdebe9c5dd95f` (`9bb2b30`)
- **Branch tip certified**: `origin/product-dev-recovered` == `9bb2b3090c946d5edb6a4d17958fdebe9c5dd95f` (identical)
- **Runtime report commit**: `b6c8eb95795b93b9181a460bf7f5d6b58f2c88a6` (`b6c8eb95`)
- **Runtime report branch**: `ops/s6j-redeploy-smoke-2026-07-05`
- **Pack branch**: `codex/dc1b-release-candidate-evidence-pack-2026-07-09` (docs-only, off `product-dev-recovered @ 9bb2b30`)
- **Prepared by**: Codex agent

## 0. Purpose

This pack consolidates the evidence trail that the **merged platform/product runtime
baseline is healthy and ready to be treated as the release candidate runtime**. It does
NOT certify that all product business features are complete (see Section 5). It certifies
that the platform P10-P25 surface, the U6 onboarding chain, the product core smoke, the
platform smoke, the Alembic single-head state, and the auth/RBAC boundary are all
proven at the production commit `9bb2b30`.

DC-1A already proved the exact VPS runtime baseline at this commit. DC-1B is the
release-candidate evidence aggregation layer on top of DC-1A.

## 1. Evidence Trail (linked and summarized)

### 1.1 G5 Controlled Platform-to-Product Promotion Candidate

- **Ledger**: `ai-ledger/platform/2026-07-09_product_merge_g5_controlled_promotion.md`
- **Commit**: `1de66c6188d3bc7039ded4295fdb5fda41ebb807` (`1de66c61`)
- **Branch**: `codex/product-merge-g5-controlled-promotion-2026-07-09`
- **Summary**: Controlled merge of `platform-dev @ 12c5ee55` into `product-dev-recovered`.
  Aligned the candidate tree to the G4-R1 reviewed evidence tip, then restored the G2-R2
  D-class regression repair on top. The conflict family (9 paths) was resolved by reusing
  the G4-reviewed resolution. Verdict: `PASS_FOR_CTO_PRODUCT_PROMOTION`.
- **Final tip** of the G5 branch is byte-identical to `origin/product-dev-recovered`
  (`9bb2b309...`), confirming the candidate was promoted into the protected branch.

### 1.2 G5-R1 Hygiene Fix

- **Ledger**: `ai-ledger/platform/2026-07-09_product_merge_g4_promotion_candidate.md`
  (trailing-whitespace correction applied in the G5-R1 pass)
- **Commit**: `9bb2b3090c946d5edb6a4d17958fdebe9c5dd95f` (`9bb2b30`) -- `docs(g5-r1): remove promotion ledger trailing whitespace`
- **Summary**: Docs-only hygiene fix. This is the commit that became the production
  baseline tip after G5 promotion. No code, no migration, no frontend, no lockfile delta.

### 1.3 DC-1A Exact VPS Runtime Baseline Report

- **Report**: `ai-ledger/ops/2026-07-09_dc1a_post_promotion_runtime_baseline.md`
- **Commit**: `b6c8eb95795b93b9181a460bf7f5d6b58f2c88a6` (`b6c8eb95`)
- **Branch**: `ops/s6j-redeploy-smoke-2026-07-05`
- **Verdict**: `PASS_EXACT_VPS_RUNTIME_BASELINE_READY_FOR_NEXT_PHASE`
- **Key results**:
  - HEAD matched target `9bb2b30` on VPS `1.14.247.12`.
  - DB backup taken before redeploy (see Section 6).
  - Exact rebuild/redeploy, no code changes: `docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build`.
  - 5/5 containers healthy.
  - `/health/live` 200, `/health/ready` 200, `/openapi.json` 200, frontend `/` 200, frontend `/docs` 200.
  - Alembic current head `030_platform_backup_status_source`, single head, version table matches.
  - U6 onboarding chain passed end-to-end (signup, email verify, provisioning, setup credential, login, select tenant, `/me`).
  - Product runtime smoke all 200.
  - Platform runtime smoke all 200, no 500s.
  - Auth boundary: tenant token correctly blocked from platform endpoints.

### 1.4 P25 Platform Frontend Customer Readiness

- **P25-A contract**: `ai-ledger/platform/2026-07-06_p25a_platform_frontend_customer_readiness_contract.md`
- **P25-B validation harness**: `ai-ledger/platform/2026-07-06_p25b_platform_frontend_readiness_validation.md`
- **P25-C defect fix**: `ai-ledger/platform/2026-07-06_p25c_customer_readiness_defect_fix.md`
- **P25-D signoff gate**: `ai-ledger/platform/2026-07-07_p25d_platform_frontend_customer_readiness_signoff.md`
- **P25-F final closeout**: `ai-ledger/platform/2026-07-08_p25f_platform_frontend_customer_readiness_closeout.md`
  - Verdict: `P25_PLATFORM_FRONTEND_CUSTOMER_READINESS_READY`
  - Merged on `origin/platform-dev @ 26d6ba55` into the P25-F closeout chain.
- **Summary**: P25 is the customer/operator readiness validation layer over the P10-P24
  platform frontend surface (19 routes behind the identity-only `PlatformRoute` guard).
  Ten merged phases on `platform-dev` are cited from their own ledgers in P25-F.

### 1.5 P25-EA Production Build Unblock

- **Ledger**: `ai-ledger/platform/2026-07-07_p25ea_frontend_production_build_unblock.md`
- **Summary**: Frontend-only TypeScript build error fixes -- 16 shipped `src` errors reduced
  to 0. Unblocked the production frontend build over the P25-D signoff base.

### 1.6 P25-EB Durable Approval Resolver Alignment

- **Ledger**: `ai-ledger/platform/2026-07-07_p25eb_p22_durable_approval_resolver_alignment.md`
- **Summary**: Aligned the P22 default durable-approval resolver to the P20/P21 durable
  READ path with NO in-memory fallback. R1 added 6 durable-read-path unit proofs plus 10
  P25-EB integration proofs covering the durable approval -> dry-run -> request ->
  governed backup.check preflight happy path and the fail-closed matrix.

### 1.7 P25-EC/ED/EE/EF Real-Stack 5xx Closures

- **P25-EC real-stack browser smoke evidence**: `ai-ledger/platform/2026-07-08_p25ec_real_stack_browser_smoke_evidence.md`
  - Originally `STOP_AND_REPORT_CTO` (Part A: 0-backend-5xx blocked by global tenant
    filter; Part B: identity smoke PASS; Part C: artifact cleanup PASS). The blockers it
    surfaced were closed by P25-ED/EE/EF below.
- **P25-ED system DB context / tenant filter boundary fix**: `ai-ledger/platform/2026-07-08_p25ed_platform_system_db_context_tenant_filter_fix.md`
  - Verdict (R1): tenant-filter blocker `PROVEN_CLOSED`.
- **P25-EE tenant health ID boundary fix**: `ai-ledger/platform/2026-07-08_p25ee_tenant_health_id_boundary_fix.md`
  - Verdict: tenant-health UUID/slug boundary blocker `PROVEN_CLOSED`.
- **P25-EF audit result closed-vocab boundary fix**: `ai-ledger/platform/2026-07-08_p25ef_audit_result_recorded_boundary_fix.md`
  - Verdict: audit result `recorded` closed-vocab defect `PROVEN_CLOSED`; P25 customer
    readiness UNBLOCKED -- real-stack smoke 19/19 HTTP 200, 0 backend 5xx.
- **Real-stack smoke artifact** (the closing evidence): `verify/g4r1_smoke/smoke_result.json`
  - `route_smoke`: 19 routes, all HTTP 200, none with `has_5xx`.
  - `identity_smoke`: 6/6 passed (operator admit, test-override reject in production,
    identity super_admin admit, no-credentials deny, wrong-operator deny, tenant-token deny).
  - `log_grep`: `http_500_error_lines = 0`, `traceback_lines = 0`,
    `tenant_context_missing_errors = 0`.

### 1.8 P25-EG/EH/EJ Legacy UUID / Registry / Transaction Poisoning Hardening

- **P25-EG tenant list legacy UUID robustness**: `ai-ledger/platform/2026-07-09_p25eg_tenant_list_legacy_uuid_robustness.md`
  - Verdict: `FIXED` -- legacy/non-v4-v7 UUIDs no longer cause HTTP 500 on tenant list/health.
- **P25-EH P17 registry legacy UUID robustness**: `ai-ledger/platform/2026-07-09_p25eh_p17_registry_legacy_uuid_robustness.md`
  - Verdict: `STOP_AND_REPORT_CTO` in its own scope (the Pydantic UUID fix was correct and
    kept, but the registry 500 persisted for a root cause outside P25-EH scope). The
    remaining 500 was then closed by P25-EJ.
- **P25-EJ P17 registry optional source read transaction poisoning fix**: `ai-ledger/platform/2026-07-09_p25ej_p17_registry_optional_source_transaction_fix.md`
  - Verdict: `P25-EJ_PROVEN_CLOSED` -- real-stack smoke confirmed 0 backend 5xx.
  - Root cause fixed: optional source-read exceptions (`_load_backup_status_map`,
    `_load_provisioning_map` in `p17/services.py`) poisoned the AsyncSession transaction;
    fixed with `db.begin_nested()` (SAVEPOINT) so a missing optional table no longer
    aborts the whole transaction.
- **Net effect on the candidate**: all legacy-UUID / registry / transaction-poisoning 5xx
  paths that surfaced during G3-R3 real-stack smoke are closed (P25-EJ proven 0 backend 5xx).

### 1.9 U6 Onboarding Runtime Proof

- **U6 chain ledgers** (`ai-ledger/product-ai/`): `u6a` (email/auth contract) -> `u6b`
  (schema contract) -> `u6c` (signup/email-verification skeleton) -> `u6d` (verify-email
  endpoint) -> `u6e0`/`u6e` (onboarding status token + endpoint) -> `u6f` (auth chain
  closeout) -> `u6g` (tenant provisioning contract) -> `u6h0`-`u6h3` (provisioning service
  + schema + reconcile) -> `u6i0`-`u6i6` (owner credential setup + first admin RBAC) ->
  `u6k` (production SMTP email delivery) -> `u6l` (email-verified onboarding
  orchestration) -> `u6m` (onboarding runtime closeout).
- **Runtime smoke proofs** (`ai-ledger/ops/`):
  - `2026-07-09_u6j_exact_vps_onboarding_runtime_smoke.md`
  - `2026-07-09_u6j_r2_smtp_onboarding_runtime_smoke.md`
  - `2026-07-09_u6j_r3_full_onboarding_runtime_smoke.md`
  - `2026-07-09_u6j_r3_full_onboarding_e2e_pass.md` -- verdict
    `PASS_U6J_R3_FULL_ONBOARDING_E2E` (7/7 onboarding steps with real SMTP via 126.com).
- **U6-M runtime closeout**: `ai-ledger/product-ai/2026-07-09_u6m_onboarding_runtime_closeout.md`
  - Confirms no manual tenant/admin DB creation was used during runtime validation.

### 1.10 Product Core Smoke Proof

- **Source**: DC-1A report, Section 7 (product runtime smoke).
- **Result** (all HTTP 200): SKUs, wholesalers, retailers, orders, inventory stocks,
  inventory logs, roles, users, payments, intake workspaces, dashboard KPI.
- **No 500s** across the product surface at `9bb2b30`.

### 1.11 Platform Smoke Proof

- **Source**: DC-1A report, Section 8 (platform runtime smoke) + G4-R1 real-stack artifact.
- **Result**: platform health 200, platform info 200, no 500 errors across all endpoints.
  Real-stack browser smoke (G4-R1) confirmed 19/19 platform frontend routes HTTP 200 with
  0 backend 5xx and 0 tracebacks in logs.

### 1.12 Alembic Single-Head Proof

- **Source**: DC-1A report, Section 5.
- **Current head**: `030_platform_backup_status_source`.
- **Single head**: confirmed; version table matches.
- **Mechanism**: G2 Option A merge migrations
  (`c724b9fb` -- `G2 Option A: alembic merge migrations 029/030 (single head 030_platform_backup_status_source)`).
  Product chain 020-028 preserved; platform 020/021 represented as 029/030; single head is
  `030_platform_backup_status_source`.

### 1.13 Auth / RBAC Boundary Proof

- **Source**: DC-1A report, Section 8 (auth boundary) + G4-R1 identity smoke artifact.
- **Result**: tenant token correctly blocked from platform endpoints. Identity smoke 6/6:
  valid operator secret admitted; `X-Platform-Test-Override` rejected in production (403);
  identity-only super_admin JWT admitted; no credentials denied (401); wrong operator
  denied (403); tenant-token denied.
- **Supporting ledgers**:
  - `ai-ledger/product-ai/2026-07-04_s6e_rbac_permission_registry_drift_gate.md`
  - `ai-ledger/platform/2026-06-09_p11b0_r1_auth_boundary_tightening.md`
  - `ai-ledger/product-ai/2026-06-21_s2r1_platform_super_admin_boundary_fix.md`

## 2. Release-Readiness Matrix

| Area | Evidence source | Commit / branch | Status | Remaining risk | Next owner |
|---|---|---|---|---|---|
| Platform P10-P25 | P25-F closeout + G4-R1 real-stack smoke (19/19, 0 5xx) | `platform-dev @ 26d6ba55` (merged into `product-dev-recovered @ 9bb2b30`); smoke artifact `verify/g4r1_smoke/smoke_result.json` | READY | Local pnpm rebuild blocked by supply-chain `minimumReleaseAge` (env only; no frontend delta in G5) | CTO / ops |
| Product U6 onboarding | U6J-R3 full onboarding E2E pass + U6-M closeout | `ops/s6j-redeploy-smoke-2026-07-05` report; `product-ai/2026-07-09_u6m_*` | READY | Gmail outbound blocker (use 126.com); no `+` alias with 126.com | Product |
| Product core smoke | DC-1A Section 7 (all 200, no 500) | `9bb2b30` / DC-1A report `b6c8eb95` | READY | Not all product business features certified (see Section 5) | Product (DC-2) |
| Platform smoke | DC-1A Section 8 + G4-R1 artifact | `9bb2b30` / DC-1A report `b6c8eb95` | READY | None at this commit | Platform |
| Migrations / Alembic | DC-1A Section 5; G2 Option A merge `c724b9fb` | head `030_platform_backup_status_source`, single head | READY | None (single head verified on VPS) | Platform |
| Auth / RBAC boundary | DC-1A Section 8 + G4-R1 identity smoke 6/6 | `9bb2b30` / DC-1A report | READY | None at this commit | Platform |
| Frontend production build | P25-EA (16 -> 0 TS errors); G4-R1 build passed | `platform-dev` P25-EA merged into `9bb2b30` | READY | Local rebuild env-blocked by supply-chain age policy (not a code failure) | Frontend / ops |
| Runtime deployment | DC-1A exact rebuild, 5/5 containers healthy | `9bb2b30` on VPS `1.14.247.12` | READY | None at this commit | Ops |
| Secrets / env | `.env.prod` (not in ledger); secrets baseline exists | VPS `.env.prod` | READY | Rotate any pre-deploy secrets if policy requires; do not commit secrets | Ops |
| Observability / logs | G4-R1 `log_grep`: 0 500-lines, 0 tracebacks | `verify/g4r1_smoke/smoke_result.json` | READY | Long-term log retention / alerting not part of this pack | Ops |
| Rollback / backup | DC-1A pre-redeploy backup (see Section 6) | `9bb2b30` deploy + backup artifact | READY | Rollback runbook command needs ops confirmation (Section 6) | Ops |

## 3. Acceptance Criteria Check

- [x] G5 controlled platform-to-product promotion candidate documented and promoted.
- [x] G5-R1 hygiene fix documented (the production tip itself).
- [x] DC-1A exact VPS runtime baseline report referenced and summarized.
- [x] P25 platform frontend customer readiness referenced (A/B/C/D/F).
- [x] P25-EA production build unblock referenced.
- [x] P25-EB durable approval resolver alignment referenced.
- [x] P25-EC/ED/EE/EF real-stack 5xx closures referenced (net 0 backend 5xx).
- [x] P25-EG/EH/EJ legacy UUID / registry / transaction poisoning hardening referenced
      (P25-EJ proven closed).
- [x] U6 onboarding runtime proof referenced (U6J-R3 full E2E pass).
- [x] Product smoke proof referenced (DC-1A Section 7).
- [x] Platform smoke proof referenced (DC-1A Section 8 + G4-R1 artifact).
- [x] Alembic single-head proof referenced (`030_platform_backup_status_source`).
- [x] Auth boundary proof referenced (DC-1A Section 8 + identity smoke 6/6).

## 4. Validation Run for This Pack

- `git diff --check`: clean (docs-only change).
- ASCII scan: this file is ASCII-only (no non-ASCII bytes introduced).
- `detect-secrets-hook --baseline .secrets.baseline`: no new findings (docs-only, no
  secrets recorded; the DC-1A report SHA256 value is a file hash, not a secret).
- Forbidden path audit: this pack writes to `ai-ledger/release/` only. No runtime code,
  migration, frontend, package, or lockfile paths touched.
- GitNexus analyze/status: docs-only change. If GitNexus is available, re-analyze after
  this commit; if unavailable, fallback is documented here (docs-only delta does not
  affect the indexed code graph).
- `git status`: clean after commit on the feature branch.
- Push: feature branch `codex/dc1b-release-candidate-evidence-pack-2026-07-09` only.

## 5. Not Yet Final Delivery

This pack does **NOT** certify that all product business features are complete.

- This pack certifies that the **platform/product merged runtime baseline is healthy** at
  `9bb2b30`: containers healthy, migrations single-head, onboarding chain proven, product
  core smoke green, platform smoke green, auth boundary enforced, 0 backend 5xx.
- It does **not** certify full product business-feature coverage, full business-rule
  correctness, performance under load, or end-to-end acceptance of every product module.
- Remaining product feature gaps and broader business acceptance must be tracked
  **separately in DC-2**, not in this pack.

## 6. Rollback

- **Current deployed commit**: `9bb2b3090c946d5edb6a4d17958fdebe9c5dd95f` (`9bb2b30`)
  on VPS `1.14.247.12`, branch `product-dev-recovered`.
- **DC-1A pre-redeploy backup artifact** (taken before the exact rebuild):
  - Path (VPS): `/home/ubuntu/.secure-backups/mpango_erp_dc1a_20260709-210407.sql`
  - Size: 309,157 bytes (~301.9 KB / reported as ~309 KB)
  - SHA256 prefix: `b512815d80cc...` (full value in the DC-1A report)
- **Last known pre-promotion commit** (product tip before the G5 promotion chain landed):
  the `product-dev-recovered` tip immediately before the G5 promotion merge chain is the
  pre-promotion point. Exact SHA to be confirmed from the promotion ledger history on
  request; the G4/G5 ledgers cite the product base as
  `origin/product-dev-recovered @ 0879314c` (G5) and the G4 no-overlap check found the two
  new product tip commits (U6-M, U6-L closeout) to be docs-only.
- **Rollback command / process**: needs ops confirmation. The deploy pattern is
  `docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build` against a
  chosen commit, with a DB restore from the backup artifact above. The exact rollback
  runbook step sequence (commit checkout, DB restore command, container recreate, health
  re-check) is not yet committed as a single script -- mark as **needs ops confirmation**
  before relying on it for a production rollback.

## 7. Acceptance Verdict

**RC_BASELINE_EVIDENCE_PACK_READY**

The merged platform/product runtime baseline at `9bb2b30` is healthy and proven across
platform P10-P25, U6 onboarding, product core smoke, platform smoke, Alembic single-head,
and the auth/RBAC boundary. DC-1A exact VPS runtime baseline PASSED. Remaining product
business-feature completeness is explicitly out of scope for this pack and is tracked in
DC-2.

## 8. Branch and Push Confirmation

- Pack branch: `codex/dc1b-release-candidate-evidence-pack-2026-07-09` (docs-only).
- `product-dev-recovered` was **not** pushed by this task.
- `platform-dev` was **not** pushed by this task.
- The pack was built in a dedicated worktree off `product-dev-recovered @ 9bb2b30` to
  avoid disturbing any other in-flight work in the main worktree.
