# P18-A Controlled Platform Actions Contract -- Ledger

**Date:** 2026-06-23
**Branch:** `codex/platform-p18a-controlled-actions-contract-2026-06-23`
**Base:** `40fed88` (origin/platform-dev -- P17-B/C registry adapter cockpit)
**Commit:** the P18-A contract commit on the isolated branch (3 files). The exact
short SHA is recorded in the session report and intentionally kept out of this ledger
so the ledger stays non-self-referential and the detect-secrets scan stays clean.
**Push target:** `origin/codex/platform-p18a-controlled-actions-contract-2026-06-23`
(the isolated branch only).
**Report path:** `ai-ledger/platform/2026-06-23_p18a_controlled_actions_contract.md`
(this ledger is the persisted report; the final human-readable report is delivered in
the work session).
**Author:** Codex (Claude worker)
**Statement:** **Docs-only. Contract-only. No runtime code, no backend, no frontend, no
migrations, no test code, no dependency changes.**

---

## Summary

P18-A introduces the **Controlled Platform Actions Contract** for SaaS platform
operations. P17 delivered the platform registry and tenant lifecycle as a read and
contract only layer and explicitly deferred every registry mutation to a future,
separately approved controlled-action phase. P18-A is the contract for that phase
boundary. It defines, before any execution code is written:

- A closed **action catalog** of ten actions (support_mode.on/off, tenant.pause/resume,
  incident.flag_set/clear, provisioning.recheck, backup.check,
  backup.restore_test_request, lifecycle.transition), each with ten fields: action name,
  read/write classification, allowed actor role, required reason, required confirmation,
  idempotency key requirement, preconditions, denied states, audit event requirement,
  and expected degraded behavior.
- A **permission matrix** across four roles: identity-only super_admin,
  support_operator, engineering_operator, and the denied tenant-contextual admin.
- Seven **safety rules** (no impersonation, no tenant business mutation, no raw
  secrets/logs/DSNs/host/port, no action without reason, no action without audit, no
  action without an idempotency key, and no action when the registry source is unknown
  unless the contract explicitly allows a degraded request) plus derived hard rules.
- A **ControlledActionAuditEvent** contract with thirteen fields (action_id, actor_id,
  actor_role, tenant_id, action_type, requested_state, previous_state, reason,
  idempotency_key, correlation_id, result, metadata_redacted, created_at) and the
  action_type and result enums.
- **Degraded behavior** for every action: writes are denied against an unknown source;
  only the two read actions (provisioning.recheck, backup.check) explicitly allow a
  degraded request.
- Seventeen **acceptance criteria** and sixteen **counterexamples**.
- A strict **P18-B entry gate** (read-model and action-request skeleton only; no
  execution of destructive actions, no migrations, no auth/RBAC/session rewrite, no
  product business code).

P18-A is the controlled-action layer that P17 deferred. Every P18 action targets a P17
PlatformTenantRegistry field or lifecycle transition, and ControlledActionAuditEvent
specializes the P17 TenantRegistryAuditEvent. P18-A defines the contract only and
executes nothing.

---

## Modified Files (docs + ledger only)

- `docs/ai/PLATFORM_PRODUCT_P18_CONTROLLED_ACTIONS_CONTRACT.md` -- new contract (goal
  and non-goals, relationship to P10 through P17, action catalog with master summary
  and ten per-action blocks, permission matrix, safety rules, audit event contract with
  field table and enums, seventeen acceptance criteria, sixteen counterexamples, P18-B
  entry gate, docs-only statement).
- `docs/ai/README.md` -- added the P18 contract to the Platform Product Track read
  order (item 16) plus a P18 entry paragraph.
- `ai-ledger/platform/2026-06-23_p18a_controlled_actions_contract.md` -- this ledger.

No `backend/`, `frontend/`, `migrations/`, `alembic/`, `.github/`, `.claude/`, or
`product-dev-recovered/` files touched.

---

## Checks / Validation (all PASS)

- `git diff --check origin/platform-dev..HEAD` -- **PASS** (rc 0, no whitespace
  errors).
- Forbidden path audit -- **PASS**. Changed files vs origin/platform-dev:
  `A ai-ledger/platform/2026-06-23_p18a_controlled_actions_contract.md`,
  `A docs/ai/PLATFORM_PRODUCT_P18_CONTROLLED_ACTIONS_CONTRACT.md`,
  `M docs/ai/README.md`. Non-markdown changed files: none. No
  `backend/`, `frontend/`, `migrations/`, `alembic/`, `.github/`, `.claude/`,
  `product-dev-recovered/`, or auth/RBAC/session/payment/tenancy paths.
- Non-ASCII scan on the three new/changed files -- **0 hits** (ASCII-only).
- detect-secrets scan on the three files -- **clean (results empty)**. Short SHAs only
  (7-char short SHA for the base, for example `40fed88`); no long hex object ids (full
  40-char SHAs are intentionally omitted to keep the detect-secrets scan clean).
- Pre-commit hooks at commit -- **all Passed**: trailing-whitespace, end-of-file-fixer,
  check-yaml (skipped, no yaml in the change), check-added-large-files, detect-secrets
  (with `--baseline .secrets.baseline`).
- `npx gitnexus analyze` -- **PASS** (indexed successfully: 7,051 nodes / 21,387 edges
  / 464 clusters / 300 flows).
- `npx gitnexus status` -- **up-to-date** (indexed commit == current HEAD after the
  P18-A contract commit).
- GitNexus `detect_changes` -- not exposed as a CLI command in this gitnexus build
  (MCP-only; no gitnexus MCP tools are connected in this session). Equivalent scope
  verified via `git diff`: exactly three files, all markdown, zero source files,
  therefore zero symbol/flow impact. Risk LOW / docs-only.

No runtime tests apply (no runtime code in P18-A).

---

## GitNexus

- `npx gitnexus analyze` -- index current (7,051 nodes / 21,387 edges / 464 clusters /
  300 flows).
- `npx gitnexus status` -- up-to-date at the P18-A contract commit.
- Impact: none (docs-only change; no symbols, callers, or execution flows changed).
- Risk classification: **LOW / docs-only**.

---

## Forbidden Path Audit

- Touched only `docs/ai/PLATFORM_PRODUCT_P18_CONTROLLED_ACTIONS_CONTRACT.md`,
  `docs/ai/README.md`, and
  `ai-ledger/platform/2026-06-23_p18a_controlled_actions_contract.md`.
- No `backend/`, `frontend/`, `migrations/`, `alembic/`, `.github/`, `.claude/`,
  `product-dev-recovered/`, auth/RBAC/session, payment/billing, or tenancy paths.
- No runtime code, no migrations, no product impact.

---

## Risk

**NONE / docs-only.** This phase introduces a contract and a ledger only. It changes no
runtime behavior, no security posture, no data, and no dependencies. The contract
explicitly constrains future phases to a read-model and action-request skeleton and
enumerates prohibited actions (execution of destructive actions, impersonation, tenant
business mutation, raw secrets/logs/DSNs, migrations, auth rewrite, cockpit mutation
controls).

---

## Blockers

None. P18-A is docs-only and complete. P18-B (a read-model and action-request
skeleton) may begin only after this contract is accepted by the CTO, and even P18-B
must not execute destructive actions unless separately approved.
