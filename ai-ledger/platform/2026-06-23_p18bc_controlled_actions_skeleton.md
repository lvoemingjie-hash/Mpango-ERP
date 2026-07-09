# P18-B/C Controlled Platform Actions Request Skeleton -- Ledger

**Date:** 2026-06-23
**Branch:** `codex/platform-p18bc-controlled-actions-skeleton-2026-06-23`
**Base:** `origin/platform-dev` @ `947052f` (merge: P18-A; P18-A commit `74c70ff`
confirmed merged -- is-ancestor true). Required base gate PASSED before any work.
**Commit chain:** `947052f` (base) -> `e84d586` (R0: skeleton) -> `28d83d5` (R1: reason
redaction) -> the R2 commit at branch tip. The exact R2 short SHA is recorded in the
session report and intentionally kept out of this ledger so it stays non-self-referential
and the detect-secrets scan stays clean.
**Push target:** `origin/codex/platform-p18bc-controlled-actions-skeleton-2026-06-23`
(the isolated branch only; platform-dev is not merged or pushed).
**Report path:** `ai-ledger/platform/2026-06-23_p18bc_controlled_actions_skeleton.md`.
**Author:** Codex (Claude worker)
**Statement:** Safe REQUEST skeleton only. No controlled action is executed. No P17
registry / tenant lifecycle / operational flag / provisioning / backup / tenant
business mutation. No migrations. No auth/RBAC/session/tenancy rewrite.

---

## R2 Revision -- Generalized Sensitive-Input Boundary (current)

A CTO review found that R1 closed only the free-text **reason** leak. The other
client-supplied fields echoed in responses and audit were still returned verbatim:
`action_type` (when unsupported), `idempotency_key`, `requested_state`, and
`correlation_id`. A hostile payload could put a secret in any of these (for example
`idempotency_key="password=abc123"` or `action_type="postgres://u:p@10.0.0.5:5432/db"`)
and have it echoed back in the response and written into the audit metadata. This is a
platform-runtime secret-handling defect, so the change remains classified **HIGH** until
mitigated.

R2 fix (all in `backend/api/v1/platform/p18/services.py`):

- New `_sanitize_text(value)` and `_sanitize_action_type(action_type)` helpers extend the
  R1 wholesale-redaction policy to every echoed field. Any value carrying a sensitive
  pattern (secret keyword, connection scheme, `@`, or host / IP : port) is replaced with
  `[redacted]`; `None` stays `None`; a clean value is returned verbatim. `action_type` is
  returned verbatim when it is a known catalog value (fixed safe enum) or a benign
  unsupported value, and redacted only when it is unsupported AND sensitive.
- `evaluate_request` now computes echo-safe values once (`safe_action_type`, `safe_key`,
  `safe_requested_state`, `safe_correlation_id`, alongside R1 `safe_reason`) and uses
  them in EVERY response (denied / degraded / duplicate / conflict / accepted / validate)
  and in the stored record.
- The RAW values are still used **internally only**: catalog lookup (`action_type`), the
  in-memory store dict key (`raw_key`, for duplicate / conflict detection), and the
  one-way SHA-256 idempotency fingerprint (raw payload). The fingerprint is a hash and is
  never echoed or audited, so duplicate / conflict semantics are unchanged while no raw
  sensitive value reaches a response or the audit.
- Audit inherits the boundary automatically: `_write_request_audit` reads
  `response.action_type` / `response.idempotency_key`, which are now safe.

R2 adds 9 regression tests (`TestGeneralizedSensitiveBoundary`): sensitive
idempotency_key not leaked in response OR audit (audit intercepted via a patched
`append_audit_entry`); unsupported sensitive action_type not leaked (benign unsupported
type still echoed); sensitive requested_state / correlation_id not leaked; duplicate and
conflict paths do not leak the raw key; GET-by-id does not leak any sensitive echo field;
clean echo fields are preserved. R1 reason tests remain green.

**Risk after R2:** HIGH (platform-runtime additive) / **mitigated after R2**. The
echo-leak vector is now closed across all client-supplied fields. Residual classification
is HIGH only because the branch adds platform-runtime code (it is not docs-only).

---

## Prior revisions (history)

- **R1 (`28d83d5`)** -- reason redaction: `_redact_reason` wholesale-redacts any sensitive
  reason to `[redacted]`; `_StoredRequest.reason` stores the redacted reason; raw reason
  never echoed. (R0 `_redact_reason` only substituted keywords and left the value.)
- **R0 (`e84d586`)** -- initial P18-B/C request skeleton + cockpit.

---

## Summary

P18-B/C implements the **controlled-action request skeleton** defined by the P18-A
contract: validate, deduplicate, redact, audit, and RECORD controlled-action requests
without ever executing them.

- **P18-B backend**: `backend/api/v1/platform/p18/` package with schemas, services, and
  routes. Four endpoints, all behind the existing identity-only P10 guard:
  `GET /actions/catalog`, `POST /actions/validate` (dry-run), `POST /actions/request`
  (record, duplicate/conflict idempotency), `GET /actions/requests/{action_id}`. Uniform
  response envelope with `executed == False` always. Reason + idempotency_key required;
  unsupported action_type denied; write / write_request against an unknown registry source
  denied; degraded read only for `provisioning.recheck` / `backup.check`; confirmation
  required for write / write_request; **all client-supplied echo fields redacted (R2)**;
  best-effort audit on every request, validate, lookup, and access denial. Role
  granularity deferred to super_admin-only.
- **P18-C frontend**: read-only / request-only cockpit at `/platform/controlled-actions`
  behind the `PlatformRoute` identity-only guard, reusing `platformService`. No execute /
  pause / resume / trigger control; explicit request-not-executed copy.

---

## Modified Files

R2 (this revision) revises 3 files:
- `backend/api/v1/platform/p18/services.py` -- `_sanitize_text`, `_sanitize_action_type`;
  `evaluate_request` echo-safe values across all responses, the stored record, and the
  duplicate / conflict paths.
- `backend/tests/test_platform_p18_controlled_actions.py` -- +9
  `TestGeneralizedSensitiveBoundary` tests (sensitive fixtures annotated
  `# pragma: allowlist secret`).
- `ai-ledger/platform/2026-06-23_p18bc_controlled_actions_skeleton.md` -- this ledger.

Full branch scope vs `origin/platform-dev` (13 files): the 5 new backend p18 files +
`backend/api/app.py`, the 3 new frontend files, the 3 additive shared-wiring files
(`platformApi.ts`, `AppRouter.tsx`, `Sidebar.tsx`), and this ledger.

No `migrations/`, `alembic/`, `.github/`, `.claude/`, or `product-dev-recovered/` paths.
No tenant business tables, no auth/RBAC/session/tenancy, no payment/billing code.

---

## Checks / Validation (R2 re-run, all PASS)

- Base gate -- PASS. `origin/platform-dev` tip is `947052f`; P18-A `74c70ff` is an
  ancestor of HEAD.
- `git diff --check origin/platform-dev..HEAD` -- PASS (rc 0, no whitespace errors).
- Forbidden path audit -- PASS. Only platform p18 backend/frontend + the three additive
  shared-wiring files + this ledger; no forbidden paths.
- Non-ASCII added-line scan -- 0 hits in all added lines. (`app.py` carries 3 pre-existing
  em-dash comment characters on untouched lines; per established platform practice these
  are left alone. All P18-authored content is ASCII-only.)
- detect-secrets -- clean. `detect-secrets-hook --baseline .secrets.baseline` passes on
  every changed file; sensitive test fixtures are annotated `# pragma: allowlist secret`.
- Pre-commit hooks at commit -- all Passed.
- `npx gitnexus analyze` -- PASS (graph intact; up-to-date at the R2 commit).
- GitNexus `detect_changes` (compare vs `origin/platform-dev`) -- **HIGH**: 13 files,
  93 symbols, **13 affected processes** (per the re-run). Platform-runtime additive, not
  docs-only; expected for this change set. The HIGH-severity echo-leak findings (R0
  reason; R1 non-reason fields) are mitigated in R1 + R2.
- GitNexus `api_impact` for `backend/api/v1/platform/p18/routes.py` -- the four route
  handlers remain additive with LOW upstream impact; R2 changes only the service-layer
  redaction they call. No existing route handler is altered.

---

## Tests

- **Backend P18** (`tests/test_platform_p18_controlled_actions.py`): **49 passed** (R0:
  32; R1: +8 reason; R2: +9 generalized boundary). Covers catalog; accepted-not-executed;
  missing reason / empty reason / missing idempotency_key / unsupported action_type /
  missing confirmation denied; tenant-contextual denied; unauthenticated denied;
  non-super_admin denied; operator/test-override/identity-only-super_admin accepted;
  duplicate same -> duplicate / different -> conflict; write & write_request
  unknown-source denied; degraded read only for provisioning.recheck / backup.check; read
  accepted when source available; no mutation route set (exactly 4 endpoints, GET/POST
  only); no tenant business data; metadata redaction; validate dry-run; **R1 reason
  redaction; R2 generalized echo-field redaction (action_type / idempotency_key /
  requested_state / correlation_id) across response + audit + stored + duplicate +
  conflict + GET-by-id, with clean values preserved**.
- **Frontend P18** (`PlatformControlledActionsPage.test.tsx`): **6 passed** (unchanged
  by R2; re-run green).
- **Backend regression** (P10 contracts + P17 registry + P15 incident triage):
  **208 passed**.
- **Frontend regression** (full suite, 26 files): **229 passed**.
- TypeScript: `tsc --noEmit` reports 0 errors in any P18-authored/edited file.

---

## GitNexus

- `npx gitnexus analyze` -- PASS; index up-to-date at the R2 commit.
- `detect_changes` vs `origin/platform-dev` -- **HIGH: 13 files, 93 symbols, 13 affected
  processes.** Platform-runtime additive (not docs-only); expected for this change set.
- `api_impact` for `routes.py` -- four new guarded handlers, additive, LOW upstream
  impact; R2 changes only service-layer redaction; no existing handler altered.

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

**HIGH (platform-runtime additive) / mitigated after R2.** The branch adds platform-
runtime code, so `detect_changes` is HIGH (13 files / 93 symbols / 13 processes) -- this
is not a docs-only change. Both HIGH-severity echo-leak defects found in review (R0
reason value-leak; R1 non-reason field echo-leak) are closed: every client-supplied echo
field is wholesale-redacted, raw values are confined to internal catalog lookup / store
key / one-way fingerprint, and 17 redaction regression tests (R1 + R2) cover the
boundary. Residual mitigations: identity-only guard (tenant-contextual and unauthenticated
denied) with best-effort audit; the skeleton never executes any action; writes only to an
ephemeral in-memory store (no DB table, no migration); the frontend is request-only with
explicit not-executed copy and no execution controls.

---

## Blockers

None for the skeleton itself. The R0/R1 echo-leak defects are mitigated in R1 + R2.
Recommended next step (separately approved): wire real registry source status, and (only
with separate approval) execute non-destructive rechecks; destructive execution remains
blocked unless separately approved.
