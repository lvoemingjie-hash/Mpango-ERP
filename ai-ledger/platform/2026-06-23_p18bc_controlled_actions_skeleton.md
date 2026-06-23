# P18-B/C Controlled Platform Actions Request Skeleton -- Ledger

**Date:** 2026-06-23
**Branch:** `codex/platform-p18bc-controlled-actions-skeleton-2026-06-23`
**Base:** `origin/platform-dev` @ `947052f` (merge: P18-A controlled platform actions
contract; P18-A commit `74c70ff` confirmed merged -- is-ancestor true). Required base
gate PASSED before any work began.
**Commit:** the P18-B/C skeleton commit on the isolated branch. The exact short SHA is
recorded in the session report and intentionally kept out of this ledger so it stays
non-self-referential and the detect-secrets scan stays clean.
**Push target:** `origin/codex/platform-p18bc-controlled-actions-skeleton-2026-06-23`
(the isolated branch only; platform-dev is not merged or pushed).
**Report path:** `ai-ledger/platform/2026-06-23_p18bc_controlled_actions_skeleton.md`
(this ledger is the persisted report).
**Author:** Codex (Claude worker)
**Statement:** Safe REQUEST skeleton only. No controlled action is executed. No P17
registry / tenant lifecycle / operational flag / provisioning / backup / tenant
business mutation. No migrations. No auth/RBAC/session/tenancy rewrite.

---

## Summary

P18-B/C implements the **controlled-action request skeleton** defined by the P18-A
contract: validate, deduplicate, redact, audit, and RECORD controlled-action requests
without ever executing them.

- **P18-B backend**: a new `backend/api/v1/platform/p18/` package with schemas,
  services, and routes. Four endpoints, all behind the existing identity-only P10
  platform guard (`require_platform_operator`):
  - `GET  /api/v1/platform/p18/actions/catalog` -- the closed 10-action catalog.
  - `POST /api/v1/platform/p18/actions/validate` -- dry-run validation (no persistence).
  - `POST /api/v1/platform/p18/actions/request` -- record a request (ephemeral in-memory
    store) with duplicate/conflict idempotency.
  - `GET  /api/v1/platform/p18/actions/requests/{action_id}` -- read a recorded request.
  - Responses are a uniform envelope (`action_id, action_type, result, executed,
    dry_run, message, reason, idempotency_key, requested_state, previous_state,
    source_status, degraded_reason, metadata_redacted, correlation_id, created_at`)
    with `executed == False` always and copy that states the action was not executed.
  - Safety: reason + idempotency_key required; unsupported action_type denied; write /
    write_request actions against an unknown registry source denied; degraded read
    allowed only for `provisioning.recheck` / `backup.check`; confirmation required for
    write / write_request; metadata redacted (no secret / DSN / host / port); best-effort
    audit on every validate / request / lookup and on every access denial.
  - Role granularity deferral: the P10 guard enforces identity-only super_admin at
    runtime; `support_operator` / `engineering_operator` are not wired yet. Per the
    P18-A contract and task, the skeleton defaults to conservative super_admin-only and
    documents the deferral.
- **P18-C frontend**: a read-only / request-only cockpit page at
  `/platform/controlled-actions` behind the `PlatformRoute` identity-only guard, reusing
  the existing `platformService` API client. It renders the catalog, a validate/submit
  form (reason + idempotency_key required to enable the buttons), result statuses
  (accepted / denied / duplicate / conflict / degraded), an explicit "request recorded
  -- not executed" notice, and a safe warning on unknown / degraded source. Buttons read
  "Validate request" / "Submit request"; there is no execute / pause / resume / trigger
  control.

---

## Modified Files

Backend (new):
- `backend/api/v1/platform/p18/__init__.py` -- package marker.
- `backend/api/v1/platform/p18/schemas.py` -- Pydantic schemas (extra="forbid").
- `backend/api/v1/platform/p18/services.py` -- catalog, validation, source resolution,
  in-memory store, redaction, duplicate/conflict.
- `backend/api/v1/platform/p18/routes.py` -- 4 guarded endpoints + best-effort audit.
- `backend/tests/test_platform_p18_controlled_actions.py` -- 32 backend tests.

Backend (modified):
- `backend/api/app.py` -- register the P18 router (4 added lines). ASCII-only addition.

Frontend (new):
- `frontend/src/types/platformControlledActions.ts` -- P18 types.
- `frontend/src/pages/platform/PlatformControlledActionsPage.tsx` -- cockpit page.
- `frontend/src/pages/platform/__tests__/PlatformControlledActionsPage.test.tsx` -- 6 tests.

Frontend (modified):
- `frontend/src/services/platformApi.ts` -- P18 API methods (additive).
- `frontend/src/router/AppRouter.tsx` -- P18 route under PlatformRoute (additive).
- `frontend/src/components/layout/Sidebar.tsx` -- P18 nav link (additive).

No `migrations/`, `alembic/`, `.github/`, `.claude/`, or `product-dev-recovered/` paths.
No tenant business tables, no auth/RBAC/session/tenancy, no payment/billing code.

---

## Checks / Validation (all PASS)

- Base gate -- PASS. `origin/platform-dev` tip is `947052f` (P18-A merge); P18-A commit
  `74c70ff` is an ancestor of HEAD.
- `git diff --check origin/platform-dev..HEAD` -- PASS (rc 0, no whitespace errors).
- Forbidden path audit -- PASS. All changed paths are platform p18 backend/frontend +
  the three additive shared-wiring files; no forbidden paths.
- Non-ASCII scan on phase-authored files -- 0 hits. (`backend/api/app.py` carries 3
  pre-existing em-dash comment characters on lines unrelated to this phase; per
  established platform practice these are left untouched. The P18 router-registration
  lines added to app.py are ASCII-only, and every other new/changed file is ASCII-clean.)
- detect-secrets scan (--baseline .secrets.baseline) on all changed files -- clean.
- Pre-commit hooks at commit -- all Passed (trailing-whitespace, end-of-file-fixer,
  check-yaml, check-added-large-files, detect-secrets).
- `npx gitnexus analyze` -- PASS (7,159 nodes / 21,751 edges / 471 clusters / 300 flows).
- `npx gitnexus status` -- up-to-date at the P18-B/C commit.
- GitNexus `detect_changes` (MCP-only; equivalent via `git diff`): only platform p18
  files + the three additive shared-wiring files; additive, platform-only; no change to
  existing route handlers' behavior. Risk LOW (platform-only, guarded, non-executing).
- GitNexus api_impact (new/modified API route handlers): four NEW guarded endpoints
  under `/api/v1/platform/p18/*`; they call only the new p18 services and the existing
  P10 guard + audit appender. No existing route handler is altered; `app.py` only
  registers the new router.

---

## Tests

- **Backend P18** (`tests/test_platform_p18_controlled_actions.py`): **32 passed**.
  Covers catalog GET; valid request accepted but not executed; missing reason / empty
  reason / missing idempotency_key / unsupported action_type / missing confirmation
  denied; tenant-contextual admin denied; unauthenticated denied; non-super_admin
  denied; operator-secret and test-override accepted; identity-only super_admin
  accepted; duplicate same payload -> duplicate; duplicate different payload -> conflict;
  write and write_request against unknown source denied; degraded read allowed only for
  provisioning.recheck / backup.check; read accepted when source available; no mutation
  route to P17/tenant state (route set is exactly the 4 endpoints, GET/POST only); no
  tenant business data in responses; metadata redaction (no raw secret/host/port);
  validate is a dry run (no persistence, not executed).
- **Backend regression** (P10 contracts + P17 registry + P15 incident triage):
  **208 passed**, no breakage from the new module or the `app.py` registration.
- **Frontend P18** (`PlatformControlledActionsPage.test.tsx`): **6 passed**. Covers
  catalog render; form requires reason + idempotency key (buttons disabled until
  present); submit shows request-not-executed status; denied/conflict/duplicate statuses
  render; no direct-execution button wording with request-vs-execution copy; unknown /
  degraded source shows a safe warning.
- **Frontend regression** (full suite, 26 files): **229 passed**, no breakage from the
  shared-file edits (platformApi, AppRouter, Sidebar).
- TypeScript: `tsc --noEmit` reports 0 errors in any P18-authored or P18-edited file
  (39 pre-existing errors live in unrelated, untouched platform pages/tests).

---

## GitNexus

- `npx gitnexus analyze` -- 7,159 nodes / 21,751 edges / 471 clusters / 300 flows.
- `npx gitnexus status` -- up-to-date at the P18-B/C commit.
- Impact: additive platform-only. New nodes/edges are the p18 package + the 4 guarded
  route handlers; no existing symbol, caller, or execution flow is changed.
- Risk classification: **LOW** (platform-only, additive, identity-only guarded,
  non-executing, audited, redacted, in-memory only).

---

## Forbidden Path Audit

- Touched only: `backend/api/v1/platform/p18/*`, `backend/tests/test_platform_p18*`,
  `backend/api/app.py`, `frontend/src/types/platformControlledActions.ts`,
  `frontend/src/pages/platform/PlatformControlledActionsPage.tsx` (+ test),
  `frontend/src/services/platformApi.ts`, `frontend/src/router/AppRouter.tsx`,
  `frontend/src/components/layout/Sidebar.tsx`, and this ledger.
- No `migrations/`, `alembic/`, `.github/`, `.claude/`, `product-dev-recovered/`,
  auth/RBAC/session, payment/billing, or tenancy paths. No tenant business tables.
- No actual destructive execution; no lifecycle / flag / provisioning / backup mutation.

---

## Risk

**LOW.** The change is additive and platform-only. Every endpoint is behind the
existing identity-only P10 guard (tenant-contextual and unauthenticated denied) and
emits best-effort audit. The skeleton never executes any controlled action, never
mutates the P17 registry or tenant state, writes only to an ephemeral in-memory store
(no DB table, no migration), and redacts all metadata. The frontend is request-only
with explicit not-executed copy and no execution controls. Role granularity is
conservatively deferred to super_admin-only until runtime support exists.

---

## Blockers

None. P18-B/C is complete and pushed on the isolated branch. The skeleton is ready for
CTO review. A future, separately approved phase may begin to wire real source status
and (only with separate approval) execute non-destructive rechecks; destructive
execution remains blocked unless separately approved.
