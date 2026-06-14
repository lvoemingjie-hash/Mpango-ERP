# P15-A Incident Triage Contract -- Ledger

**Date:** 2026-06-14
**Branch:** `codex/platform-p15a-incident-triage-contract-2026-06-14`
**Base:** `6b9efa8` (origin/platform-dev -- P14 real-signals merge)
**HEAD:** Final pushed branch HEAD is externally verified by CTO/reviewer after push.
**Author:** Codex (Claude worker)
**Statement:** **Docs-only. No runtime code, no backend, no frontend, no migrations,
no test code, no dependency changes.**

---

## Summary

P15-A introduces the **Incident Triage Workflow** product/technical contract for
the Platform Operations Cockpit. It defines a read-only triage path (detect ->
classify -> inspect -> explain -> handoff -> close) and the data contracts
(`IncidentSignal`, `IncidentClassification`, `IncidentRunbookHint`,
`IncidentTriageSnapshot`, `IncidentHandoffSummary`) that P15-B will implement as
read-only adapters.

Every field is pinned to an existing P10/P12/P13/P14 read-only source, or marked
`unavailable`/`unknown` with a reason. No new sources, no fabrication.

---

## Modified Files (docs + ledger only)

- `docs/ai/PLATFORM_PRODUCT_P15_INCIDENT_TRIAGE_CONTRACT.md` -- new contract
  (goals, personas, workflow, 5 data contracts, source map, security boundary,
  P15-B entry gate, 14 acceptance criteria, 14 counterexamples, test plan).
- `docs/ai/README.md` -- added P15 contract to the Platform Product Track read
  order (item 14) plus a P15 entry paragraph.
- `ai-ledger/platform/2026-06-14_p15a_incident_triage_contract.md` -- this ledger.

No backend/, frontend/, migrations/, alembic/, .github/, .claude/, or product
business files touched.

---

## Checks / Validation

- `git diff --check` -- no whitespace errors.
- Non-ASCII scan on the new/changed markdown files -- **0 hits** (ASCII-only).
- Forbidden path audit -- only `docs/ai/` and `ai-ledger/platform/` files changed;
  no runtime/forbidden paths.
- `npx gitnexus analyze` -- index current (docs-only change; no symbol/flow
  impact).
- GitNexus `detect_changes` (compare vs pre-merge platform-dev) -- expected
  **LOW / docs-only** (no runtime symbols changed).
- Pre-commit hooks (trim trailing whitespace, end-of-file, detect-secrets, large
  files) -- run at commit.

No runtime tests apply (no runtime code in P15-A).

---

## GitNexus

- `npx gitnexus analyze` -- index current. Exact node/edge/cluster/flow counts are
  captured in the merge readiness gate output (per the P13-D-R6 count-deferral
  policy).
- Impact: none. P15-A changes documentation only; no symbols, callers, or
  execution flows are affected.
- Risk classification: **LOW / docs-only**.

---

## Forbidden Path Audit

- Touched only `docs/ai/PLATFORM_PRODUCT_P15_INCIDENT_TRIAGE_CONTRACT.md`,
  `docs/ai/README.md`, and `ai-ledger/platform/2026-06-14_p15a_incident_triage_contract.md`.
- No `backend/`, `frontend/`, `migrations/`, `alembic/`, `.github/`, `.claude/`,
  `product-dev-recovered/`, auth/RBAC/session, payment/billing, or tenancy paths.
- No runtime code.

---

## Risk

**NONE / docs-only.** This phase introduces a contract and a ledger only. It
changes no runtime behavior, no security posture, no data, and no dependencies.
The contract explicitly constrains P15-B to a read-only snapshot adapter and
enumerates prohibited actions (repair, impersonation, business queries, mutations,
migrations, auth rewrite).

---

## Blockers

None. P15-A is docs-only and complete. P15-B may begin only after this contract
is accepted by the CTO.
