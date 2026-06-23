# P18-B/C Controlled Platform Actions Request Skeleton -- Ledger

**Date:** 2026-06-23
**Branch:** `codex/platform-p18bc-controlled-actions-skeleton-2026-06-23`
**Base:** `origin/platform-dev` @ `947052f` (merge: P18-A controlled platform actions
contract; P18-A commit `74c70ff` confirmed merged -- is-ancestor true). Required base
gate PASSED before any work began.
**Commit chain:** `947052f` (base) -> `e84d586` (R0: P18-B/C skeleton) -> the R1
commit at branch tip. The exact R1 short SHA is recorded in the session report and
intentionally kept out of this ledger so it stays non-self-referential and the
detect-secrets scan stays clean.
**Push target:** `origin/codex/platform-p18bc-controlled-actions-skeleton-2026-06-23`
(the isolated branch only; platform-dev is not merged or pushed).
**Report path:** `ai-ledger/platform/2026-06-23_p18bc_controlled_actions_skeleton.md`
(this ledger is the persisted report).
**Author:** Codex (Claude worker)
**Statement:** Safe REQUEST skeleton only. No controlled action is executed. No P17
registry / tenant lifecycle / operational flag / provisioning / backup / tenant
business mutation. No migrations. No auth/RBAC/session/tenancy rewrite.

---

## R1 Revision -- Redaction + Evidence Fix (current)

A CTO review of the R0 skeleton (commit `e84d586`) found a redaction weakness in the
free-text reason path: `_redact_reason` only substituted the matched secret KEYWORD and
left the secret VALUE behind. For example a reason of `password=abc123` was transformed
to `[redacted]=abc123`, so the value `abc123` survived in the response, in the recorded
(in-memory) request, and in the duplicate echo. This is a platform-runtime secret
handling defect, so the change is classified **HIGH** until mitigated.

R1 fix (this revision), all in `backend/api/v1/platform/p18/services.py`:

- `_redact_reason` now uses a conservative wholesale policy: if the reason contains ANY
  sensitive pattern -- a secret keyword (password / token / api_key / dsn / credential /
  ...), a connection scheme (postgres://, mysql://, redis://, `://`), an `@` credential
  separator, or a host / IP : port pair (new `_HOST_PORT` pattern) -- the ENTIRE reason
  is replaced with `[redacted]`, so no secret value can remain. A clean reason is
  returned verbatim.
- The accepted request no longer stores the raw reason: `_StoredRequest.reason` now
  stores the redacted (safe) reason. `get_stored_request()` and the duplicate echo
  therefore never return a raw reason.
- The idempotency fingerprint still uses the raw payload (for duplicate/conflict
  detection only); it is a one-way SHA-256 hash and is never returned in any response.

R1 adds 8 regression tests (`TestReasonRedaction`) proving: `password=abc123` and
`token abc123` do not leak `abc123`; a DSN / connection-string reason leaks no
user/pass/host/port; a host:port reason leaks no host/port; an accepted request
fetched by action_id leaks no raw reason; a duplicate response leaks no raw reason; a
clean reason is preserved; and structured metadata redaction is unchanged.

**Risk after R1:** HIGH (platform-runtime additive) / **mitigated after R1** -- the
value-leak vector is closed and covered by tests. The skeleton still executes nothing
and mutates no state; the residual classification is HIGH only because the change set
touches platform-runtime code (it is not docs-only).

---

## Summary

P18-B/C implements the **controlled-action request skeleton** defined by the P18-A
contract: validate, deduplicate, redact, audit, and RECORD controlled-action requests
without ever executing them.

- **P18-B backend**: `backend/api/v1/platform/p18/` package with schemas, services, and
  routes. Four endpoints, all behind the existing identity-only P10 guard
  (`require_platform_operator`): `GET /actions/catalog`, `POST /actions/validate`
  (dry-run), `POST /actions/request` (record, with duplicate/conflict idempotency),
  `GET /actions/requests/{action_id}`. Uniform response envelope with `executed == False`
  always and copy that states the action was not executed. Reason + idempotency_key
  required; unsupported action_type denied; write / write_request against an unknown
  registry source denied; degraded read allowed only for `provisioning.recheck` /
  `backup.check`; confirmation required for write / write_request; metadata AND reason
  redacted (R1: reason is wholesale-redacted); best-effort audit on every request,
  validate, lookup, and access denial. Role granularity deferred to super_admin-only.
- **P18-C frontend**: read-only / request-only cockpit at `/platform/controlled-actions`
  behind the `PlatformRoute` identity-only guard, reusing `platformService`. Renders the
  catalog, a validate/submit form (reason + idempotency_key required to enable buttons),
  result statuses, an explicit "request recorded -- not executed" notice, and a safe
  warning on unknown / degraded source. No execute / pause / resume / trigger control.

---

## Modified Files

R1 (this revision) revises 3 files:
- `backend/api/v1/platform/p18/services.py` -- wholesale `_redact_reason`, `_HOST_PORT`,
  `_reason_is_sensitive`; `_StoredRequest.reason` now stores the redacted reason.
- `backend/tests/test_platform_p18_controlled_actions.py` -- +8 `TestReasonRedaction`
  tests (sensitive fixtures annotated `# pragma: allowlist secret`).
- `ai-ledger/platform/2026-06-23_p18bc_controlled_actions_skeleton.md` -- this ledger.

Full branch scope vs `origin/platform-dev` (13 files): the 5 new backend p18 files +
`backend/api/app.py`, the 3 new frontend files, the 3 additive shared-wiring files
(`platformApi.ts`, `AppRouter.tsx`, `Sidebar.tsx`), and this ledger.

No `migrations/`, `alembic/`, `.github/`, `.claude/`, or `product-dev-recovered/` paths.
No tenant business tables, no auth/RBAC/session/tenancy, no payment/billing code.

---

## Checks / Validation (R1 re-run, all PASS)

- Base gate -- PASS. `origin/platform-dev` tip is `947052f`; P18-A `74c70ff` is an
  ancestor of HEAD.
- `git diff --check origin/platform-dev..HEAD` -- PASS (rc 0, no whitespace errors).
- Forbidden path audit -- PASS. Only platform p18 backend/frontend + the three additive
  shared-wiring files + this ledger; no forbidden paths.
- Non-ASCII scan on phase-authored files -- 0 hits in all added lines. (`app.py` carries
  3 pre-existing em-dash comment characters on untouched lines; per established platform
  practice these are left alone. All P18-authored content is ASCII-only.)
- detect-secrets -- clean. `detect-secrets-hook --baseline .secrets.baseline` passes on
  every changed file; sensitive test fixtures are annotated `# pragma: allowlist secret`.
- Pre-commit hooks at commit -- all Passed (trailing-whitespace, end-of-file-fixer,
  check-yaml, check-added-large-files, detect-secrets).
- `npx gitnexus analyze` -- PASS (graph intact; up-to-date at the R1 commit).
- GitNexus `detect_changes` (compare vs `origin/platform-dev`) -- **HIGH**: 13 files,
  93 symbols, 12 affected flows. This is expected and accurate: the branch is a
  platform-runtime additive change (new p18 module, new guarded route handlers, shared
  wiring), not docs-only. It is platform-only, non-executing, identity-only guarded,
  and the only HIGH-severity item (the R0 reason value-leak) is mitigated in R1.
- GitNexus `api_impact` for `backend/api/v1/platform/p18/routes.py` -- the four NEW
  route handlers (`get_catalog`, `validate_action`, `submit_action`,
  `get_recorded_request`) are additive with LOW upstream impact; they call only the new
  p18 services and the existing P10 guard + audit appender. No existing route handler is
  altered.

---

## Tests

- **Backend P18** (`tests/test_platform_p18_controlled_actions.py`): **40 passed** (R0:
  32; R1: +8 reason-redaction). Covers catalog; accepted-not-executed; missing reason /
  empty reason / missing idempotency_key / unsupported action_type / missing
  confirmation denied; tenant-contextual denied; unauthenticated denied; non-super_admin
  denied; operator/test-override/identity-only-super_admin accepted; duplicate same ->
  duplicate / different -> conflict; write & write_request unknown-source denied;
  degraded read only for provisioning.recheck / backup.check; read accepted when source
  available; no mutation route set (exactly 4 endpoints, GET/POST only); no tenant
  business data; metadata redaction; validate dry-run; **R1 reason redaction (password /
  token / DSN / host:port values never leak; GET-by-id and duplicate never echo raw
  reason; clean reason preserved)**.
- **Frontend P18** (`PlatformControlledActionsPage.test.tsx`): **6 passed** (unchanged
  by R1; re-run green).
- **Backend regression** (P10 contracts + P17 registry + P15 incident triage):
  **208 passed**.
- **Frontend regression** (full suite, 26 files): **229 passed**.
- TypeScript: `tsc --noEmit` reports 0 errors in any P18-authored/edited file (39
  pre-existing errors in unrelated, untouched files).

---

## GitNexus

- `npx gitnexus analyze` -- PASS; index up-to-date at the R1 commit.
- `detect_changes` vs `origin/platform-dev` -- **HIGH: 13 files, 93 symbols, 12 affected
  flows.** Platform-runtime additive (not docs-only); expected for this change set.
- `api_impact` for `routes.py` -- four new guarded handlers, additive, LOW upstream
  impact; no existing handler altered.

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

**HIGH (platform-runtime additive) / mitigated after R1.** The branch adds new
platform-runtime code (the p18 package, four guarded route handlers, and shared
wiring), so `detect_changes` is HIGH (13 files / 93 symbols / 12 flows) -- this is not a
docs-only change. The one HIGH-severity defect found in review -- the R0 reason
value-leak -- is closed in R1 (wholesale reason redaction; raw reason never stored or
echoed; covered by 8 regression tests). Residual mitigations: every endpoint is behind
the existing identity-only P10 guard (tenant-contextual and unauthenticated denied) with
best-effort audit; the skeleton never executes any action; it writes only to an
ephemeral in-memory store (no DB table, no migration); metadata and reason are redacted;
the frontend is request-only with explicit not-executed copy and no execution controls.

---

## Blockers

None for the skeleton itself. The R0 reason value-leak is mitigated in R1. Recommended
next step (separately approved): wire real registry source status, and (only with
separate approval) execute non-destructive rechecks; destructive execution remains
blocked unless separately approved.
