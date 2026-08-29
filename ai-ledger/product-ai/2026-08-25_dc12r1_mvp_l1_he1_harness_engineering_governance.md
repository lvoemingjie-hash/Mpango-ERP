# DC-12R1-MVP-L1-HE1 Harness Engineering Governance

## Status

`PASS_FOR_CTO_DC12R1_MVP_L1_HE1_DOCS_ONLY_GOVERNANCE_REVIEW`

## Objective

Replace memory-driven acceptance coverage with a governed structure based on
surface inventories, state combinations, cross-cutting interactions, five
oracles, mutations, independent fresh-runtime execution, and periodic
exploratory testing.

## Trigger

The J1/H2 journey demonstrated that individually green components did not prove
the customer workflow:

- the forgot-password capability existed below the UI before it was navigable;
- a public reset 401 interacted with the global Axios session interceptor and
  redirected the anonymous user before the page could render its neutral error;
- raw-response byte equality incorrectly treated a legitimate per-request
  timestamp as semantic account-state drift.

These cases show why line coverage and CTO memory cannot be the acceptance
model.

## Scope

Exactly seven documentation files:

1. new `docs/ai/HARNESS_ENGINEERING_GOVERNANCE_STANDARD.md`;
2. link and completion rules in `docs/ai/AI_TEAM_OPERATING_RULES.md`;
3. canonical read-order and update-rule entry in `docs/ai/README.md`;
4. acceptance-harness precedence note in `docs/contracts/test_contract.md`;
5. approved decision `decision-register/2026-08-25_harness-engineering-governance.md`;
6. decision index update in `decision-register/README.md`; and
7. this ledger.

No backend, frontend, test, migration, dependency, lockfile, deployment, or
runtime file is changed.

## Governance Decisions

1. Code coverage is diagnostic, not sufficient release evidence.
2. Coverage is measured through surfaces, transitions, state pairs, failure
   classes, cross-cutting interactions, oracle completeness, mutations, journey
   reachability, and visible coverage debt.
3. Acceptance nodes define five applicable oracles: UI, navigation, network,
   client/session state, and persistence/security.
4. Risk-based pairwise selection is the default, with mandatory critical tuples
   for auth, tenancy, money, credentials, interceptors, middleware, retries, and
   prior P0/P1 defects.
5. Every P0/P1 finding becomes a retained deterministic node and mutation or an
   explicitly owned CTO coverage-debt item.
6. Periodic independent exploratory charters are required to discover missing
   inventory cells, but exploration alone is not deterministic PASS evidence.
7. Report names and verdicts must match the executed layer.
8. Acceptance harnesses use fresh real dependencies; the legacy all-mocks rule
   remains limited to bounded unit tests.

## CTO Instruction Compliance Check

| CTO instruction | Implementation evidence | Validation evidence | Status |
|---|---|---|---|
| Make coverage systematic rather than memory-driven | Coverage model, mandatory tuples, inventory contract, metrics | Document review and exact docs-only scope | PASS |
| Add periodic exploratory testing | Section 14 charter, cadence, independence, conversion rule | Charter template and P0/P1 conversion gate | PASS |
| Preserve deterministic harness governance | Lifecycle, mutation standard, single-run evidence rules | Required machine evidence and STOP semantics | PASS |
| Avoid unlimited MVP matrix expansion | Risk-based pairwise floor plus mandatory critical tuples | Adoption plan prioritizes P0/P1 risk-first backfill | PASS |
| Keep HE1 governance-only | Seven documentation paths only | `git diff --name-only` and product/test zero-delta gate | PASS |

## Counterexample Check

| Counterexample | Why it is invalid | Governing control |
|---|---|---|
| Report 90% line coverage while forgot-password has no navigation entry | Executed lines do not prove user reachability | Surface inventory and Journey Reachability metric |
| Test reset page and interceptor independently but never compose anonymous 401 | Component tests miss the actual user failure | Mandatory public x anonymous x 4xx x interceptor tuple |
| Compare only HTTP status for account neutrality | Semantic or navigation leaks can remain | Five oracles and neutrality oracle rules |
| Run an exploratory session and label observations as regression PASS | Result is not deterministic or frozen | Exploration-to-node conversion rule |
| Generate every Cartesian combination | Cost explodes and slows MVP without prioritizing risk | Pairwise floor plus mandatory critical tuples |

## Follow-Up Boundaries

- HE2 may add a machine-validated inventory schema and coverage-debt tooling.
- HE3 may backfill risk-prioritized product workflows.
- Neither follow-up is authorized by this docs-only task.
- H2-B-R3 product review remains a separate branch and gate.

## Risk

Documentation-only. The main risk is governance drift if long-lived branches do
not adopt the shared document. Merge/reconciliation should preserve this file
across product and platform branches.
