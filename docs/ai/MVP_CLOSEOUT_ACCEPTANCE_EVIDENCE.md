# Mpango ERP MVP Closeout Acceptance Evidence

> Status: DRAFT_FOR_CTO_REVIEW
> Date: 2026-05-23
> Product branch: `product-dev-recovered`
> Current promoted commit: `a9b143624a2ce89b8833140e976fe24f15ec34c9`
> Scope: Phase 6 credit payment / accounts receivable MVP closeout evidence

## 1. Executive Summary

Mpango ERP Phase 6 has moved from "feature runnable" toward "evidence-backed MVP acceptance". The current product line focuses on credit payment, accounts receivable visibility, collection return flow, Finance page usability, and browser-based Ghost QA validation.

This document is not final production approval. It is the MVP closeout evidence pack used by CTO, product-line agents, OPS AI, Vibecoder/Leo, and future human engineers to decide what is stable, what remains risky, and when the India VPS deployment gate can begin.

## 2. MVP Product Scope

Current MVP acceptance scope:

1. Credit-payment orders can enter the accounts receivable view.
2. The Finance Accounts Receivable page shows total receivables, credit exposure, unpaid orders, and overdue cues.
3. Users can navigate from Finance receivables into the Orders collection flow.
4. After a collection is recorded, users can return to Finance with context preserved.
5. Finance URL state supports `tab`, `page`, and `collection` recovery.
6. Finance page accessibility has been improved:
   - receivable filter group has a readable label and pressed state.
   - receivable table headers use `scope="col"`.
   - payment progress bar exposes progressbar ARIA semantics.
   - zero-day receivables display `New`.

Explicitly outside this MVP scope:

1. Full double-entry general ledger.
2. Multi-currency FX gain/loss accounting.
3. Enterprise-grade credit-limit, dunning, and collections workflow.
4. Production-grade audited financial reporting closeout.
5. Full platform commercialization admin console.

## 3. Evidence Ledger

### Product promotion evidence

| Area | Evidence |
|---|---|
| Current product branch | `origin/product-dev-recovered` |
| Current promoted commit | `a9b143624a2ce89b8833140e976fe24f15ec34c9` |
| Sprint Q promotion commit | `a9b1436 merge: promote sprint q receivables accessibility polish` |
| Sprint Q feature commit | `fa71dd895c04e2225f07430cf28427d385c9f0e6` |
| Sprint P-1 promotion commit | `a40591f merge: promote sprint p1 finance accessibility polish` |
| Sprint O promotion commit | `dea1d0f merge: promote sprint o finance refresh accessibility` |

### Leo / Ghost QA evidence

| Gate | Run / Report | Result |
|---|---|---|
| Sprint Q post-merge validation | GitHub Actions run `26314461562`, reports commit `683093f` | PASS |
| Sprint Q feature validation | GitHub Actions run `26296216175`, reports commit `9e6b0ad` | PASS |
| Tier3 exploratory baseline | GitHub Actions run `26295397173`, reports commit `afdc243` | PASS |
| Sprint P-1 exact-hash validation | GitHub Actions run `26291794762`, reports commit `93b7e58` | PASS |
| Sprint O exact-hash validation R4 | GitHub Actions run `26288977693`, reports commit `2f71331` | PASS |

Latest post-merge validation evidence:

- `COMMANDS_EXECUTED`: `9/9`
- Tier2 browser journey: PASS
- Tier3 exploratory browser journey: PASS
- Receivables suite: `38 passed, 0 failed`
- Phase 5 payment regression: `53 passed, 1 xfailed, 0 failed`
- Schema contract: `40 passed, 0 skipped, 0 failed`
- Product code modified by Leo: `no`
- Product branch pushed by Leo: `no`
- Report branch used as evidence source: `origin/reports/lubuntu-validation`

## 4. Validation Contract

The current validation contract has two layers.

### Gate QA

Gate QA is intentionally stable. Its test numbers should remain consistent unless the product contract changes:

- Receivables service/API suite: expected `38 passed`.
- Phase 5 order/payment regression: expected `53 passed, 1 xfailed`.
- Payments schema contract: expected `40 passed, 0 skipped`.
- Frontend lint/build: must pass.
- GitNexus detect changes: expected LOW risk for UI-only closeout polish.

### Ghost QA / Exploratory QA

Ghost QA is intentionally more adversarial. It checks real browser behavior with mocked API variants:

- stale Finance page recovery.
- collection notice preservation.
- refresh feedback.
- tab URL state.
- collect navigation context.
- empty receivables state.
- temporary API failure and `Retry` recovery.
- invalid URL recovery.
- unpaid-order filter path.

This prevents the team from relying only on fixed unit-test numbers.

## 5. Current Risk Register

| Risk | Status | CTO position |
|---|---|---|
| Fixed regression tests becoming answer memorization | Reduced | Tier3 exploratory QA is active. |
| Report branch missing despite runner success | Reduced | Report artifact remains a hard gate. |
| Claude generating encoding-noisy ledgers | Active | CTO rewrites or cleans affected ledgers before commit. |
| Large frontend bundle warning | Accepted for MVP | Existing Vite warning only; not a blocker. |
| Full production deployment not yet revalidated | Open | A dedicated OPS deployment gate is required before India VPS deployment. |
| Historical VPS deployment scripts missing from current product tree | Open | `docs/README_VPS_DEPLOY.md` references `scripts/deploy_vps.sh` and `scripts/safe_cleanup_vps.sh`, but both were not present in the current product worktree during this review. OPS must restore or rewrite them before deployment. |

## 6. MVP Acceptance Checklist

Before calling the MVP ready for a human business demo:

1. `origin/product-dev-recovered` must remain clean and pushed.
2. Latest product commit must have a matching Leo post-merge report.
3. Report branch must contain the expected markdown report.
4. Tier2 and Tier3 Ghost QA must both pass.
5. Receivables, payment regression, and schema contract suites must pass with expected counts.
6. No skipped schema contract tests are allowed.
7. No product code may be changed by validation agents.
8. Deployment runbook and cleanup scripts must be refreshed before any VPS action.
9. CTO must explicitly approve deployment; no agent should deploy from this document alone.

Current assessment:

- Product closeout evidence: GREEN for current product branch.
- Deployment readiness: NOT YET APPROVED.
- Recommended next gate: OPS deployment-preflight review.

## 7. India VPS Deployment Readiness Plan

The intended deployment target is an India VPS, but deployment must be treated as a separate OPS gate.

Historical OPS deployment references found:

- `docs/README_VPS_DEPLOY.md`
- `ai-ledger/ops/2026-02-18_23-33_track_h_vps_safe_cleanup.md`
- `ai-ledger/ops/2026-03-11_vps_deployment_fixes.md`

Important caveat:

- The historical guide targets VPS `143.110.177.2`.
- The upcoming target is described as India VPS and may not be the same host.
- All IPs, SSH users, secrets, domain settings, firewall rules, Docker state, and backup paths must be refreshed before use.

### Required OPS sequence

1. Snapshot the India VPS:
   - current OS/version.
   - Docker/Compose availability.
   - existing containers/images/volumes/networks.
   - active ports.
   - non-Mpango services that must not be touched.

2. Confirm backup posture:
   - if any old Mpango database exists, export it before cleanup.
   - verify backup file exists off-host or in a safe path.
   - do not delete volumes before backup approval.

3. Restore or rewrite safe cleanup automation:
   - historical script name: `scripts/safe_cleanup_vps.sh`.
   - current repo check found this script missing.
   - cleanup must be targeted to Mpango resources only.
   - `docker system prune` is forbidden.
   - dry-run must be run before destructive cleanup.

4. Restore or rewrite deployment automation:
   - historical script name: `scripts/deploy_vps.sh`.
   - current repo check found this script missing.
   - deployment must pull the approved branch/commit only.
   - `.env.prod` or equivalent secrets must never be committed.

5. Pre-deployment validation:
   - confirm `origin/product-dev-recovered` commit to deploy.
   - run local build/test gates.
   - run Leo DB-capable validation.
   - CTO approves exact commit hash.

6. Cleanup and deploy:
   - run cleanup dry-run.
   - CTO approves cleanup.
   - run cleanup.
   - deploy exact commit.
   - run migrations normally; do not skip migrations by stamping Alembic versions.

7. Post-deployment verification:
   - health endpoints.
   - login.
   - tenant selection.
   - orders list.
   - Finance Accounts Receivable page.
   - collect repayment return flow.
   - dashboard/reporting endpoints.
   - container health and logs.

## 8. CTO Decision

This document supports the following CTO decision:

MVP product branch can continue toward final closeout. Deployment is not yet approved. Before India VPS deployment, OPS must produce a fresh deployment-preflight report and reconcile the missing cleanup/deploy scripts.

Recommended next work item:

`Sprint R-1: OPS India VPS Deployment Preflight`

Expected owner:

- OPS AI for deployment environment and runbook refresh.
- Leo for post-deployment validation contract.
- CTO for approval and final promotion gate.
