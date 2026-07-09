# P19-C Controlled Action Approval Frontend Console -- Ledger

**Date:** 2026-06-24
**Branch:** `codex/platform-p19c-approval-frontend-console-2026-06-24`
**Base:** `b08b191` (origin/platform-dev -- P19-B approval backend skeleton + R1 security
fix merged; local platform-dev == origin/platform-dev at base).
**Commit:** `0a11de7` (code: 7 files, +1350 lines) plus a P19-C-R1 follow-up commit on this
branch (test-warning + ledger-evidence fix; see the P19-C-R1 section). The R1 short SHA is
recorded in the R1 session report and intentionally kept out of this ledger so the ledger stays
non-self-referential and the detect-secrets scan stays clean.
**Push target:** `origin/codex/platform-p19c-approval-frontend-console-2026-06-24` (the
isolated branch only). Pushed as a new branch; tracks origin. Not merged into platform-dev.
**Report path:** `ai-ledger/platform/2026-06-24_p19c_approval_frontend_console.md`.

**Statement:** Frontend-only controlled-action approval console built on top of the already
merged P19-B backend skeleton. The console records approval requests, lists the ephemeral
approval queue, reads a single approval, and records approve / reject decisions only.
Approval is NOT execution: an approved approval resolves to `execution_blocked`,
`execution_allowed` and `executed` stay `false`, there is no execute / run / apply /
dispatch / trigger control, and no tenant state is ever changed from this surface. **No
backend, no migration, no alembic, no auth / RBAC rewrite, no package / lockfile, no payment,
and no product business UI. P19-D not started.**

## Scope

Frontend only, all on allowed platform paths:

- `frontend/src/types/platformApprovals.ts` (NEW) -- five approval contracts
  (`ControlledActionApprovalRequest`, `ControlledActionApprovalDecision`,
  `ControlledActionApprovalRecord`, `ControlledActionApprovalQueue`) plus the
  `ApprovalState` / `ApprovalDecisionType` / `ApprovalResult` vocabularies, field-for-field
  aligned to docs/ai/PLATFORM_PRODUCT_P19_APPROVAL_WORKFLOW_CONTRACT.md (P19-A) and the
  backend P19 schemas. `RegistrySourceStatus` is imported (reused) from
  `platformControlledActions.ts` so the P18 source-status vocabulary stays the single source
  of truth. Every record / queue item types `execution_allowed` and `executed` as `false`.
- `frontend/src/services/platformApi.ts` (MODIFIED) -- four methods added to the existing
  `platformService` object: `createApprovalRequest`, `listApprovals`, `getApproval`,
  `submitApprovalDecision`, under `P19_BASE = '/platform/p19'` (Axios baseURL `/api/v1`
  prepends -> `/api/v1/platform/p19/approvals{,/{id},/{id}/decision}`). Reuses the existing
  Axios Bearer-token client; no new auth transport, no `X-Platform-Operator` secret.
- `frontend/src/pages/platform/PlatformApprovalsPage.tsx` (NEW) -- the console: create form
  (action_type / tenant_id / reason / idempotency_key / expires_at / confirm), approval queue,
  read-only detail panel, and approve / reject decision controls gated behind explicit
  confirmation. `requested_by` / `reviewed_by` are derived from the authenticated
  identity-only platform operator (`useAuthStore` user id), never typed by the operator.
- `frontend/src/router/AppRouter.tsx` (MODIFIED, additive) -- one import and one route entry
  `{ path: '/platform/approvals', element: <PlatformApprovalsPage /> }`, placed directly after
  the P18 controlled-actions route and inside the existing `PlatformRoute`-guarded block. No
  tenant / product / auth route touched.
- `frontend/src/components/layout/Sidebar.tsx` (MODIFIED, additive) -- one `CheckBadgeIcon`
  import and one "Approvals" nav `<Link to="/platform/approvals">`, rendered inside the
  existing `showPlatformNav` (`isIdentityPlatformOperator`) block, exactly where the other
  platform entries are. No tenant / product nav touched.
- `frontend/src/pages/platform/__tests__/PlatformApprovalsPage.test.tsx` (NEW) -- 14 tests.
- `frontend/src/components/layout/__tests__/SidebarApprovals.test.tsx` (NEW) -- 5 tests.

## Safety (approval is not execution)

- **No execution control.** The only decision controls are Approve and Reject. No button text
  contains execute / run / apply / dispatch / trigger / suspend / destroy; an explicit test
  asserts this over every rendered button. Approve and Reject are disabled until an explicit
  confirmation token (the confirm checkbox), a decision reason, and a decision idempotency key
  are all supplied.
- **approved is shown as execution_blocked, never executed.** The `execution_blocked` state
  uses a RED badge (not green); a test asserts the red tone and that the text reads
  "execution blocked" with `executed=false`. There is no executed / applied / running state
  to badge.
- **Unknown / degraded source is never healthy.** `source_status` unknown / unavailable uses
  a gray / red badge (never green); an approve against a non-available source is disabled and
  shows a safe warning. A test asserts the gray (not green) badge and the disabled approve.
- **Invariants are always visible.** A persistent console banner states storage = memory,
  execution_allowed = false, executed = false, and "approved is blocked from execution".
- **Tenant-contextual identities see no controls.** The create form, queue, and decision
  controls are gated behind `isIdentityPlatformOperator(user)`; a tenant-contextual identity
  sees a hidden-surface notice and the queue is not even fetched (no `api.get` call). This is
  defense-in-depth on top of the existing `PlatformRoute` guard that already redirects
  non-identity-only users away from `/platform/approvals`.
- **No backend / tenant mutation.** Every call is a frontend read / write to the P19 approval
  endpoints; the backend resolves an approve to `execution_blocked` and never executes. The
  frontend sends no operator secret and no raw credential.

## Risk

**MEDIUM -- frontend platform surface, additive, contained.** Rationale: the change is purely
frontend and additive; it adds one guarded route, one guarded nav entry, four service methods
on the existing client, and one new page; it touches no backend, migration, auth/RBAC, tenant
business, payment, package, or lockfile path. The elevated surface is the platform approval
console, which is why the contract's approval-is-not-execution rules are enforced in the UI
and asserted by tests. Mitigations: identity-only `PlatformRoute` guard reused unchanged;
no execute / run / apply control (asserted); execution_blocked rendered red and never as
executed (asserted); unknown source never healthy (asserted); controls hidden for
tenant-contextual identities (asserted); requested_by / reviewed_by derived from the
authenticated operator, no operator secret sent; full frontend suite green (251 tests).

## Modified files

8 files total against `origin/platform-dev` (7 frontend code files below + this ledger):

- `frontend/src/types/platformApprovals.ts` -- approval contracts (NEW).
- `frontend/src/services/platformApi.ts` -- four P19 service methods (MODIFIED, additive).
- `frontend/src/pages/platform/PlatformApprovalsPage.tsx` -- approval console (NEW).
- `frontend/src/router/AppRouter.tsx` -- `/platform/approvals` route (MODIFIED, additive).
- `frontend/src/components/layout/Sidebar.tsx` -- Approvals nav entry (MODIFIED, additive).
- `frontend/src/pages/platform/__tests__/PlatformApprovalsPage.test.tsx` -- 14 tests (NEW).
- `frontend/src/components/layout/__tests__/SidebarApprovals.test.tsx` -- 5 tests (NEW).

## Tests

- New P19-C tests: **19 passed** (14 page + 5 sidebar).
  - page: title / not-executed subtitle / invariants; queue render; empty / loading / error
    states; create submits to `POST /platform/p19/approvals` with operator-derived
    `requested_by` and `confirm:true`; create disabled until reason + idempotency + expiry +
    confirm; approve submits to `POST /platform/p19/approvals/{id}/decision` with
    `decision:approve`, `confirm:true`, operator-derived `reviewed_by`, only after
    confirmation; reject submits with `decision:reject`; no execute / run / apply / dispatch /
    trigger control; execution_blocked shown as "execution blocked" with red tone, never
    executed; executed=false and execution_allowed=false displayed; unknown source_status not
    styled healthy and approve disabled; service methods call the correct P19 endpoints
    (list / read-by-id / create / decision); tenant-contextual identity hides all controls and
    does not fetch the queue.
  - sidebar: Approvals link present for identity-only super_admin, points at
    `/platform/approvals`, absent for tenant-contextual super_admin / non-platform user /
    logged-out.
- Regression: `src/pages/platform/**` + layout + router/guards + platform service/type tests
  -> **142 passed** (includes the `PlatformControlledActionsPage` gate).
- Targeted P19/P18 frontend tests (`PlatformApprovalsPage` + `SidebarApprovals` +
  `PlatformControlledActionsPage`): **28 passed** (14 + 5 + 9), 0 `act(...)` warnings.
- Full frontend suite: **28 files, 251 tests, 0 failed.** (Pre-existing `act(...)` warnings in
  other platform pages -- e.g. Ops / Registry -- are unrelated to P19-C, are not introduced by
  it, and are out of P19-C scope; R1 clears only the P19-C-owned test's warning.)
- Run config: vitest 1.6.1, jsdom, `include: ['src/**/*.{test,spec}.{ts,tsx}']`. The worktree
  has no tracked `node_modules`; the shared main-repo `frontend/node_modules` was junction'd
  in for the run only (untracked, gitignored, not committed).

## Checks

- `git diff --check origin/platform-dev..HEAD` -> PASS (rc 0; no whitespace / conflict issues).
- Non-ASCII scan: 0 non-ASCII bytes in each of the 4 new files; 0 non-ASCII added lines in
  each of the 3 modified files. (ASCII-only throughout, no section-sign / em-dash / box-dash /
  middot mojibake.)
- detect-secrets: the pre-commit detect-secrets hook (with the repo's configured baseline) on
  all 8 changed files (7 frontend code + this ledger) -> PASS (rc 0). Full pre-commit
  (`trailing-whitespace`, `end-of-file-fixer`, `check-yaml`, `check-added-large-files`,
  `detect-secrets`) on the 8 files -> all Passed; and all Passed again at commit time. Short
  SHAs only; no 40-char SHA in any new file.
- Forbidden-path audit: `git diff --name-only origin/platform-dev..HEAD` lists 8 files (7
  frontend + this ledger), all on allowed paths. No `backend/`, `migrations/`, `alembic/`,
  `product-dev-recovered`, `payment`, `billing`, `frontend/package.json`,
  `frontend/pnpm-lock.yaml`, auth/RBAC, or product-business path is touched. The only
  non-`pages/platform` edits are the additive route line in `AppRouter.tsx`, the additive nav
  link in `Sidebar.tsx`, the additive methods in `services/platformApi.ts`, and this ledger --
  all explicitly allowed.

## GitNexus

- `gitnexus analyze` PASS at commit `0a11de7`: **7,398 nodes / 22,622 edges / 485 clusters /
  300 flows** (indexed in ~17s). Additive vs the P19-B base (7,364 nodes / 22,549 edges / 474
  clusters / 300 flows): +34 nodes, +73 edges, +11 clusters from the new approval console
  types / service / page; **execution-flow count unchanged at 300** (no new execution path,
  consistent with approval-is-not-execution).
- GitNexus MCP `detect_changes compare origin/platform-dev..HEAD` = **MEDIUM**:
  changed_files = **8**, changed_symbols = **34**, affected_processes = **1**; the single
  affected execution flow is **PlatformApprovalsPage -> Unwrap** (the page's response-unwrapping
  helper; all four approval service calls unwrap through it). `detect_changes` is MCP-only (no
  CLI subcommand -- the CLI exposes `analyze` / `index` / `query` / `context` / `impact` /
  `cypher` / `wiki` / `serve` / `mcp` but not `detect_changes`; this worker session and a
  delegated subagent cannot invoke the MCP tool). These figures are the GitNexus MCP result
  obtained during review; changed_files = 8 is independently corroborated by
  `git diff --name-only origin/platform-dev..HEAD` (7 frontend code files + this ledger; no
  backend, no migration, no product, no deployment/infra). MEDIUM, not HIGH/CRITICAL: there is
  no execution, no tenant mutation, no migration, no auth/RBAC change, no product business
  path, and all 251 frontend tests pass.

## P19-C-R1 (test warning + evidence accuracy fix, 2026-06-24)

Review of P19-C found one cosmetic test warning and asked for the real GitNexus `detect_changes`
evidence. R1 fixes both. No scope expansion, no P19-D, no platform-dev merge.

- React `act(...)` warning: the single P19-C-owned warning was in
  `frontend/src/pages/platform/__tests__/PlatformApprovalsPage.test.tsx`, in the
  "renders title, not-executed subtitle, and the console invariants" test, which asserted
  synchronously before the mount-time `useEffect` queue load settled. Fixed by awaiting
  `screen.findByTestId('ap-queue-summary')` so the `setQueue` / `setQueueLoading(false)`
  update lands within `act(...)`. The P19-C page test now reports 0 `act(...)` warnings
  (14 tests pass). Only the P19-C-owned test was changed; pre-existing `act(...)` warnings in
  other platform pages (Ops / Registry, etc.) are untouched and remain pre-existing /
  non-blocking / out of P19-C scope.
- Ledger evidence accuracy: the GitNexus section now records the actual MCP `detect_changes`
  result (MEDIUM; changed_files 8; changed_symbols 34; affected_processes 1;
  PlatformApprovalsPage -> Unwrap), and the modified-files total is stated as 8 (7 code files
  + this ledger).
- Modified in R1: `frontend/src/pages/platform/__tests__/PlatformApprovalsPage.test.tsx` and
  this ledger. No production code, no backend, no migration, no auth/RBAC, no
  package/lockfile, no product path changed. `gitnexus analyze` re-run: index already up to
  date (a test-only edit adds no production symbols); execution flows still 300.

## Explicit statements

- **No execution:** the console records and decides approvals only; an approve resolves to
  execution_blocked; no controlled action is ever run. There is no execute / run / apply
  control in the UI.
- **No backend changes:** no backend file is touched; the console consumes the already-merged
  P19-B endpoints.
- **No tenant mutation:** no P17 registry / lifecycle / flag / provisioning / backup / tenant
  business data is read or written from this surface.
- **No migration:** no migrations / alembic changes; no persistent store introduced.
- **No auth / RBAC rewrite:** the existing `PlatformRoute` guard and `isIdentityPlatformOperator`
  helper are reused unchanged; no new auth transport, no `X-Platform-Operator` secret.
- **P19-D not started.**

## Blockers

None. P19-C is a complete, tested, non-executing frontend approval console on an isolated
branch, pushed to origin and not merged into platform-dev. It honors the P19-A UI
expectations: read-only request context, approve / reject only after explicit confirmation,
no execute button, approved-vs-executed badge distinction (red execution_blocked), unknown
source never healthy, and controls hidden from tenant-contextual identities.
