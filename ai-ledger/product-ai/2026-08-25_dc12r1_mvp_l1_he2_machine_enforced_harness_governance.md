# DC-12R1-MVP-L1-HE2 Machine-Enforced Harness Governance

## Status

`READY_FOR_CTO_HE2_GOVERNANCE_TOOLING_REVIEW`

## Objective

Make the HE1 harness engineering governance standard machine-enforced:
machine-parseable inventory and coverage-debt schemas, a critical-interaction
registry, a dependency-free validator, and a mandatory CI gate on
`product-dev-recovered` that blocks silent inventory drift and unsynced
product/test/harness changes.

## Baseline

`666af8a62f29d5e7b31dcf5d618336510b328420` (HE1 governance freeze), branch
`codex/dc12r1-mvp-l1-he2-machine-enforced-harness-governance-2026-08-25`.

## Deliverables and directive traceability

| # | Directive requirement | Delivered |
|---|---|---|
| 1 | Machine-parseable inventory schema: HE1 node fields, five oracles, status, risk, mutation, owner, evidence SHA | `harness-governance/schemas/inventory.schema.json` (HE1 §9, 18 fields + lifecycle fields; five oracle fields with explicit `NOT_APPLICABLE` sentinel; status enum; risk enum; `mutation_id`, `owner`, `evidence_sha` required) |
| 2 | coverage-debt schema; BLOCKED/NOT_COVERED need owner, reason, closure condition, target milestone | `schemas/coverage-debt.schema.json` + `DEBT-INCOMPLETE` rule; `INV-BLOCKED-DEBT` ties BLOCKED nodes to an open debt entry |
| 3 | critical-interaction registry: auth interceptor, tenant, rate limit, idempotency, token replay, transaction rollback, mobile navigation | `inventory/critical-interactions.json`: all seven categories with real source anchors and HE1 §5.3 mandatory tuples; `REG-CATEGORY-MISSING` blocks removal |
| 4 | validator with no new third-party dependencies | `validator/harness_governance_validator.py`, Python 3.11+ stdlib only (verified: no third-party imports under `harness-governance/`) |
| 5 | CI mandatory for PRs and pushes to product-dev-recovered | `.github/workflows/harness-governance-gate.yml`: `on.push.branches` and `on.pull_request.branches` = `[product-dev-recovered]` |
| 6 | product/test/harness path changes require inventory co-change or an owned, risk-stated, dated waiver; expired waivers RED | `SYNC-INVENTORY-MISSING` + `WVR-EXPIRED`; governed prefixes data-driven in `governed-paths.json`; waiver-file changes do not satisfy the sync rule; active on expiry day, RED after |
| 7 | block duplicate IDs, silent deletion/reorder, empty oracle, unknown status, P0/P1 without mutation, BLOCKED without owner | `INV-DUP-ID`, `DRIFT-SILENT-DELETE`, `DRIFT-REORDER`, `INV-ORACLE-EMPTY` (+`INV-ORACLE-INVALID`), `SCHEMA-ENUM` on status, `INV-MUTATION-MISSING`, `INV-BLOCKED-OWNER` (+`INV-BLOCKED-DEBT`) |
| 8 | validator unit tests and ≥8 deterministic RED mutations | 31 unittest tests + `tests/run_red_mutations.py`: 14 RED mutations, 2 GREEN controls, all passing |
| 9 | CI outputs coverage summary and debt summary; BLOCKED never counts as PASS | validator emits both summaries to stdout, `--report-json`, `--markdown-summary`; CI appends to `$GITHUB_STEP_SUMMARY`; pass rate = PASS/(total − NOT_APPLICABLE), BLOCKED/NOT_RUN count against coverage |
| 10 | governance tooling only; no full business inventory backfill (HE3 separate) | seed inventory = 13 nodes, zero PASS, zero evidence SHAs, all open work registered as owned debt targeting HE3 / post-VPS; no backend/frontend/test product code touched |

## Seed honesty rules

The validator refuses to let the seed manufacture coverage: `PASS` without a
40/64-hex evidence SHA is RED (`INV-PASS-EVIDENCE`), `FAIL` and `BLOCKED`
nodes must be tracked in open debt, and blank oracles mean NOT_COVERED. The
seed therefore ships `NOT_RUN`/`BLOCKED` only, with three owned debts:
`DEBT-AUTH-CRITICAL-TUPLES` (P0, HE3), `DEBT-COMMERCE-CRITICAL-TUPLES` (P0,
HE3), `DEBT-MOBILE-REAL-DEVICE` (P1 BLOCKED, environment, post-VPS).

## Enforcement semantics

- Baselines: PRs diff against `origin/product-dev-recovered`; pushes diff
  against `github.event.before` (fallback `HEAD^`). `--baseline-dir` exists
  for deterministic filesystem tests.
- Bootstrap: when the baseline predates the governance tree, drift and sync
  checks skip (the adopting change set cannot be indefinitely RED); unit
  tests and the mutation gate always run. Enforcement binds all changes after
  adoption.
- Order is canonical: the flagged reorder set is the minimal set of node IDs
  off the longest stable subsequence; a `reorder` protocol delta must cover it.
- Renames: node carries `renamed_from`; a `rename` delta must reference the
  real baseline ID, else `DRIFT-RENAME-UNKNOWN`/`DRIFT-RENAME-UNREGISTERED`.
- Warnings (never RED): `ANCHOR-MISSING`, `DRIFT-STATUS-RELABEL` (HE1 §16).

## Validation evidence (local, 2026-08-25)

- `python -m unittest discover -s harness-governance/tests -p "test_*.py" -v`
  — 31 tests, all GREEN.
- `python harness-governance/tests/run_red_mutations.py` — 14/14 mutations
  RED with intended rule codes; 2/2 controls GREEN.
- `python harness-governance/validator/harness_governance_validator.py
  --root .` — GREEN (13 nodes, 1 BLOCKED, 12 NOT_RUN, 3 open debts, 0
  coverage claims).
- Git-baseline mode exercised against `origin/product-dev-recovered`
  (bootstrap skip) and in the end-to-end CI simulation (probe change without
  inventory update → RED; with active waiver → GREEN; with inventory note
  update → GREEN).
- Source anchors resolve: 0 `ANCHOR-MISSING` warnings on the seed tree.

## Out of scope (explicit)

- HE3 risk-first business inventory backfill (signup/verification/login,
  retailer acquisition, SKU/pricing/inventory/order, payment reporting,
  platform support) — separately authorized.
- Any backend, frontend, migration, deployment, dependency, or product
  behavior change.
- Route-to-registry mapping enforcement for new routes (HE3 with backfill).

## Change set

1. new `harness-governance/` tree (schemas, seed inventory documents,
   governed-paths config, validator, tests, mutation gate, README);
2. new `.github/workflows/harness-governance-gate.yml`;
3. `decision-register/2026-08-25_harness-governance-tooling-he2.md` +
   register index update (DR-2026-08-25-002); and
4. this ledger.
