# P19-A Controlled Action Approval Workflow Contract -- Ledger

**Date:** 2026-06-24
**Branch:** `codex/platform-p19a-approval-workflow-contract-2026-06-24`
**Base:** `bacec41` (origin/platform-dev -- P18-D real registry source status + P18-E
controlled action request queue). Local platform-dev == origin/platform-dev at base.
**Commit:** the P19-A contract commit on the isolated branch (3 files). The exact short
SHA is recorded in the session report and intentionally kept out of this ledger so the
ledger stays non-self-referential and the detect-secrets scan stays clean.
**Push target:** `origin/codex/platform-p19a-approval-workflow-contract-2026-06-24`
(the isolated branch only). Not merged into platform-dev.
**Report path:** `ai-ledger/platform/2026-06-24_p19a_approval_workflow_contract.md`
(this ledger is the persisted report; the final human-readable report is delivered in
the work session).
**Author:** Codex (Claude worker)
**Statement:** **Docs-only. Contract-only. No runtime code, no backend, no frontend, no
migrations, no alembic changes, no test code, no dependency changes. P19-B is not
started.**

---

## Summary

P19-A introduces the **Controlled Action Approval Workflow Contract**. P18 delivered the
controlled platform actions contract and a request skeleton that can receive, validate,
deny, deduplicate, audit, and queue an action request, but P18 **never executes** any
action -- every P18 response carries `executed == False`. P19-A is the approval boundary
on top of the P18 request layer. It defines, before any approval code is written, that
**approval is not execution**: approve and reject change approval state only, an approved
approval resolves to `execution_blocked`, and `execution_allowed` stays `false`.

P19-A fixes:

- The **approval lifecycle states**: `requested`, `pending_review`, `approved`,
  `rejected`, `expired`, `cancelled`, `execution_blocked`, with the explicit invariants
  that approved does not mean executed, execution_blocked is the default post-approval
  safety state, reject is final, and an expired approval can never be accepted.
- The **actors and the approval permission matrix**: identity-only super_admin is the
  only approver; support_operator and engineering_operator may submit only within their
  P18 request scope; tenant admin, tenant-contextual super_admin, and tenant-scoped token
  are explicitly denied on every approval operation.
- Five **data contracts**: ControlledActionApprovalRequest,
  ControlledActionApprovalDecision, ControlledActionApprovalRecord,
  ControlledActionApprovalQueue, and ControlledActionApprovalAuditEvent -- all
  `extra = forbid`, all redacted via the P10 allowlist.
- The **required fields** for every approval record, including
  `execution_allowed == false` by default and `redaction_applied == true` by default.
- Nine **safety rules** (approval cannot execute, cannot mutate tenant state, cannot
  bypass P18 validation, must not expose raw values, must expire, reject is final,
  duplicate decisions are idempotent, no raw secrets/logs/DSNs/host/port, and the
  approval queue must not become a hidden execution queue) plus derived hard rules.
- The **audit event contract** with seven event types (approval_requested,
  approval_approved, approval_rejected, approval_expired, approval_cancelled,
  approval_read, approval_denied) and the required fields on every event (actor,
  identity_context, tenant_id, action_id, approval_id, decision, redaction_applied,
  timestamp).
- The **UI expectations**: read-only request context, approve/reject only after explicit
  confirmation, no execute button, approved-vs-executed badge distinction, unknown never
  healthy, and approval controls hidden from tenant-contextual users.
- Sixteen **acceptance criteria** and eighteen **counterexamples** (including every
  required counterexample: tenant admin approves, tenant-contextual super_admin approves,
  approved action executes immediately, raw secret in approval reason, expired approval
  accepted, rejected approval later approved with the same approval_id, approval bypasses
  P18 source_status, migration added, frontend shows executed after approval).
- A strict **P19-B entry gate** (backend approval read/write skeleton only; no execution,
  no tenant mutation, no migration unless separately gated and approved, in-memory or
  existing-safe storage only, reuse P18 redaction, reuse the P10 identity-only guard,
  backend tests before UI work, no automation runner).

P19-A composes P10 through P18 and introduces no new auth, RBAC, session, observability,
data-source, or action concepts. An approval request references a recorded P18
`action_id`; approval never changes the P18 `executed` flag and never re-runs P18
validation destructively. The P18 registry source_status is a hard precondition for any
approval decision.

---

## Modified Files (docs + ledger only)

- `docs/ai/PLATFORM_PRODUCT_P19_APPROVAL_WORKFLOW_CONTRACT.md` -- new contract (goal and
  non-goals, relationship to P10 through P18, the seven approval lifecycle states with
  state machine, actors and the approval permission matrix, five data contracts, required
  fields table, nine safety rules, audit event contract, UI expectations, sixteen
  acceptance criteria, eighteen counterexamples, P19-B entry gate, docs-only statement).
- `docs/ai/README.md` -- added the P19 contract to the Platform Product Track read order
  (item 17) plus a P19 entry paragraph.
- `ai-ledger/platform/2026-06-24_p19a_approval_workflow_contract.md` -- this ledger.

No `backend/`, `frontend/`, `migrations/`, `alembic/`, `.github/`, `.claude/`, or
`product-dev-recovered/` files touched.

---

## Checks / Validation (all PASS)

- `git fetch --all --prune` -- ran. Local platform-dev == origin/platform-dev at
  `bacec41`.
- `git diff --check origin/platform-dev..HEAD` -- **PASS** (rc 0, no whitespace errors);
  also rc 0 on the working tree.
- Forbidden path audit -- **PASS**. Changed files vs origin/platform-dev:
  `A ai-ledger/platform/2026-06-24_p19a_approval_workflow_contract.md`,
  `A docs/ai/PLATFORM_PRODUCT_P19_APPROVAL_WORKFLOW_CONTRACT.md`,
  `M docs/ai/README.md`. Non-markdown changed files: none. No
  `backend/`, `frontend/`, `migrations/`, `alembic/`, `.github/`, `.claude/`,
  `product-dev-recovered/`, or auth/RBAC/session/payment/tenancy paths.
- Non-ASCII scan on the three new/changed files -- **0 hits** (ASCII-only).
- detect-secrets on the three files (pre-commit `detect-secrets` hook with
  `--baseline .secrets.baseline`) -- **clean**. Short SHAs only (7-char short SHA for the
  base, for example `bacec41`); no long hex object ids (full 40-char SHAs are
  intentionally omitted to keep the detect-secrets scan clean).
- Pre-commit hooks at commit -- **all Passed**: trailing-whitespace, end-of-file-fixer,
  check-yaml (skipped, no yaml in the change), check-added-large-files, detect-secrets
  (with `--baseline .secrets.baseline`).
- `npx gitnexus analyze` -- **PASS** (indexed successfully: 7,238 nodes / 22,037 edges /
  466 clusters / 300 flows).
- `npx gitnexus status` -- up-to-date at the P19-A contract HEAD after the commit.
- GitNexus `detect_changes` -- not exposed as a CLI command in this gitnexus build
  (MCP-only; no gitnexus MCP tools are connected in this session). Equivalent scope
  verified via `git diff`: exactly three files, all markdown, zero source files,
  therefore zero symbol/flow impact. Risk LOW / docs-only / 0 runtime impact.

No runtime tests apply (no runtime code in P19-A).

---

## GitNexus

- `npx gitnexus analyze` -- index current (7,238 nodes / 22,037 edges / 466 clusters /
  300 flows).
- `npx gitnexus status` -- up-to-date at the P19-A contract HEAD.
- Impact: none (docs-only change; no symbols, callers, or execution flows changed).
- Risk classification: **LOW / docs-only / 0 runtime impact**.

---

## Forbidden Path Audit

- Touched only `docs/ai/PLATFORM_PRODUCT_P19_APPROVAL_WORKFLOW_CONTRACT.md`,
  `docs/ai/README.md`, and
  `ai-ledger/platform/2026-06-24_p19a_approval_workflow_contract.md`.
- No `backend/`, `frontend/`, `migrations/`, `alembic/`, `.github/`, `.claude/`,
  `product-dev-recovered/`, auth/RBAC/session, payment/billing, or tenancy paths.
- No runtime code, no migrations, no automation runner, no product impact.
- No merge into platform-dev; isolated branch only. P19-B not started.

---

## Risk

**NONE / docs-only.** This phase introduces a contract and a ledger only. It changes no
runtime behavior, no security posture, no data, and no dependencies. The contract
explicitly constrains future phases to a backend approval read/write skeleton and
enumerates prohibited actions (execution of any action, tenant business mutation,
bypass of P18 validation, raw secrets/logs/DSNs, hidden execution queue, migrations,
auth rewrite, automation runner, cockpit execute controls).

---

## Blockers

None. P19-A is docs-only and complete. P19-B (a backend approval read/write skeleton)
may begin only after this contract is accepted by the CTO, and even P19-B must not
execute any action, must not mutate tenant state, must not add persistent storage unless
separately gated and approved, and must not implement an automation runner. **P19-B is
not started.**
