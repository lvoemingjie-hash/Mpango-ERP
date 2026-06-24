# P19-B Controlled Action Approval Workflow Backend Skeleton -- Ledger

**Date:** 2026-06-24
**Branch:** `codex/platform-p19b-approval-backend-skeleton-2026-06-24`
**Base:** `24a4b35` (origin/platform-dev -- P19-A approval workflow contract merged).
Local platform-dev == origin/platform-dev at base.
**Commit:** the P19-B skeleton commit on the isolated branch (7 files). The exact
short SHA is recorded in the session report and intentionally kept out of this
ledger so the ledger stays non-self-referential and the detect-secrets scan
stays clean.
**Push target:** `origin/codex/platform-p19b-approval-backend-skeleton-2026-06-24`
(the isolated branch only). Not merged into platform-dev.
**Report path:** `ai-ledger/platform/2026-06-24_p19b_approval_backend_skeleton.md`.

**Statement:** Backend approval read / write skeleton only. Approval changes
approval state only; it never executes any controlled action, never mutates
tenant lifecycle / operational flags / registry / provisioning / backup / tenant
business data, adds no migrations, and uses in-memory storage only. Approval is
NOT execution: an approved approval resolves to `execution_blocked` and
`execution_allowed` stays false. **P19-C frontend not started.**

**Scope:** `backend/api/v1/platform/p19/` (schemas / services / routes /
__init__), a minimal P19 router include in `backend/api/app.py` (no auth / RBAC
logic change), `backend/tests/test_platform_p19_approval_workflow.py`, and this
ledger.

**Safety:** All P19 routes reuse the P10 identity-only platform guard
(`require_platform_operator`); tenant admin, tenant-contextual super_admin, and
tenant-scoped tokens are denied. Redaction reuses P18 verbatim
(`redact_metadata` / `_redact_reason` / `_sanitize_text`); raw reason /
metadata / idempotency_key / correlation_id are never echoed or audited (a
sensitive value is replaced wholesale with `[redacted]`). The P18 boundary is
honored: an approval wraps a P18 action (action_id lookup in the shared
in-memory P18 store, or action_type resolution via the P18 source-status
resolver); an unknown / unavailable source is stored verbatim -- never
fabricated as available -- and an approve against it is denied. `executed` and
`execution_allowed` are false on every record and queue item.

**Risk:** HIGH / platform-runtime additive / mitigated, contained to P19. No
product business paths, no auth/RBAC rewrite, no migrations, no payment/billing,
no frontend, and no product branch changes. Mitigations: identity-only guard,
no real action execution, no tenant mutation, in-memory-only storage, redacted
responses, reject-is-final / expired-not-approvable / idempotent-and-conflict
decision semantics, and full P19 test coverage plus P18 / P18-D / P10
regression.

**Modified files:**
- `backend/api/v1/platform/p19/__init__.py` -- package docstring (safe skeleton statement).
- `backend/api/v1/platform/p19/schemas.py` -- five data contracts
  (ControlledActionApprovalRequest / Decision / Record / Queue / AuditEvent)
  aligned to P19-A; `extra="forbid"`; `execution_allowed=False`,
  `redaction_applied=True`, `executed=False`, `storage="memory"` defaults.
- `backend/api/v1/platform/p19/services.py` -- in-memory approval store; the
  seven-state lifecycle (pending_review -> approved resolves to
  execution_blocked; rejected final; expired / cancelled terminal); create /
  decision idempotency (duplicate vs conflict); the P18 boundary adapter
  (`_resolve_p18_context`, never fabricates available); P18 redaction reuse;
  `_build_approval_audit_event` / `_emit` audit helpers; read / list / cancel /
  `sweep_expired`. `execution_allowed` and `executed` always false.
- `backend/api/v1/platform/p19/routes.py` -- four endpoints under
  `/api/v1/platform/p19/approvals` (POST create, GET list, GET {id} read, POST
  {id}/decision), all behind the reused P10 guard with a best-effort
  access-denied + outcome audit; `execution_allowed` / `executed` false.
- `backend/api/app.py` -- minimal P19 router include only (4 lines, directly
  after the P18 include); no auth / RBAC logic changed.
- `backend/tests/test_platform_p19_approval_workflow.py` -- 37 tests covering
  create / list / read; approve -> execution_blocked; reject -> rejected;
  approved does not execute; execution_allowed false always; tenant-contextual
  / tenant admin / non-super / unauthenticated denied; all endpoints guarded;
  expired cannot approve; rejected cannot re-approve; duplicate idempotent and
  conflicting decision fails; raw secret in reason / metadata redacted (value
  leakage); idempotency / correlation not echoed raw; audit never carries raw
  secrets; unknown P18 source cannot approve; action_id not found denied;
  available never fabricated; in-memory storage; no migration files; route
  registration.
- `ai-ledger/platform/2026-06-24_p19b_approval_backend_skeleton.md` -- this ledger.

**Tests:** Backend P19: 37 passed. Regression P18 + P18-D + P10: 201 passed.
Total 238 passed, 0 failed. (Shared venv, `PYTHONPATH=backend`, `PYTHONUTF8=1`,
`MPANGO_ENV=test`.)

**Checks:** `git diff --check origin/platform-dev..HEAD` PASS (rc 0). Non-ASCII
added-line scan on the five new P19 backend files + the test file: 0 hits (the
3 non-ASCII chars in `backend/api/app.py` are pre-existing em-dashes in
unrelated comments, not in the P19 include lines, and are intentionally left
untouched to avoid expanding the diff). detect-secrets (pre-commit
`detect-secrets` hook with `--baseline .secrets.baseline`) on all changed
files: clean (rc 0); test fixtures carry `# pragma: allowlist secret`. Short
SHAs only; no 40-char SHAs in any new file. Pre-commit hooks at commit: all
passed (trailing-whitespace, end-of-file-fixer, check-added-large-files,
detect-secrets). Forbidden path audit: no `frontend/`, `migrations/`,
`alembic/`, `product-dev-recovered/`, auth/RBAC rewrite, payment/billing, or
product branch paths; the only file outside `backend/api/v1/platform/p19/` is
the minimal `backend/api/app.py` router include.

**GitNexus:** `npx gitnexus analyze` PASS (7,372 nodes / 22,547 edges / 484
clusters / 300 flows; additive vs base: +127 nodes / +501 edges from the new
P19 module; execution-flow count unchanged at 300). `detect_changes` is
MCP-only (no CLI; no MCP tools connected this session); the equivalent
`git diff --name-only origin/platform-dev..HEAD` shows backend platform-only
files (no frontend, no migrations, no product, no deployment/infra). Risk by
full-branch graph classification is HIGH / platform-runtime additive, which is
acceptable here because every change is P19 platform-only, there is no
execution, no tenant mutation, no migration, no product business path, and all
tests pass.

**Explicit statements:**
- No execution: approval changes approval state only; approved resolves to
  execution_blocked; no controlled action is ever run.
- No tenant mutation: no P17 registry / lifecycle / flag / provisioning / backup
  / tenant business data is touched.
- No migration: no migrations / alembic changes; no persistent store introduced.
- In-memory only: approvals live in process-local memory (`storage="memory"`);
  `reset_store()` is test-only.
- P19-C frontend not started: no frontend files touched.

**Blockers:** None. P19-B is a complete, tested, non-executing backend
approval skeleton. P19-C (frontend approval surface) may begin only after this
skeleton is reviewed, and must follow the P19-A UI expectations (read-only
context, approve/reject only after explicit confirmation, no execute button,
approved-vs-executed badge distinction, controls hidden from tenant-contextual
users). **P19-C frontend not started.**
