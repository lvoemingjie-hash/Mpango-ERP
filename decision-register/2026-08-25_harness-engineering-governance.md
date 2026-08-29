# Decision Register: Harness Engineering Governance

**Decision ID:** DR-2026-08-25-001
**Title:** Systematic Harness Coverage and Exploratory Testing Governance
**Status:** Approved
**Date:** 2026-08-25
**Authority:** CTO, L1 product-delivery governance

## Context

Mpango ERP repeatedly found customer-blocking defects only after the CTO or a
human operator happened to imagine a missing journey or interaction. The J1/H2
password-recovery work exposed three examples: no discoverable forgot-password
journey, a public reset 401 redirected by the global session interceptor, and a
raw-byte neutrality oracle invalidated by a legitimate request timestamp.

Green component suites and code-coverage percentages did not expose these
failures because the missing coverage was structural: unsupported journey
reachability, an untested cross-cutting composition, and an incorrect oracle.

## Decision

Mpango ERP adopts
`docs/ai/HARNESS_ENGINEERING_GOVERNANCE_STANDARD.md` as the governing standard
for product acceptance harnesses and release evidence.

The binding decisions are:

1. coverage is modeled through supported surfaces, lifecycle transitions,
   state pairs, failure classes, cross-cutting interactions, oracle
   completeness, mutation adequacy, journey reachability, and explicit debt;
2. code coverage and green test counts remain diagnostics, not sufficient
   release evidence;
3. risk-based pairwise selection is the ordinary floor, while critical auth,
   tenancy, money, inventory, credential, middleware/interceptor, retry, and
   prior-defect combinations are mandatory;
4. critical nodes define all applicable user/UI, navigation, network,
   session/client-state, and persistence/security oracles;
5. every P0/P1 finding becomes a retained deterministic node plus a targeted
   mutation/counterexample, or a named CTO-owned coverage-debt item;
6. independent exploratory charters run periodically to discover missing
   inventory cells, but exploration cannot be reported as deterministic PASS;
7. authoritative acceptance evidence uses frozen source/harness identities,
   isolated fresh dependencies, machine-derived reconciliation, cleanup proof,
   and independent evidence review; and
8. test and report labels must state the layer actually executed.

## Rationale

This model makes unknown coverage visible and reviewable. It prevents the team
from treating unimagined scenarios as passing, while avoiding an unbounded MVP
Cartesian matrix through risk-prioritized pairwise selection and mandatory
critical tuples.

Exploration remains valuable for finding unknown unknowns. Converting critical
discoveries into permanent deterministic nodes ensures that learning survives
the current CTO, model, host, and chat context.

## Alternatives Considered

### Continue relying on code coverage and green suites

Rejected. These measures cannot prove UI reachability, cross-cutting behavior,
or oracle correctness.

### Depend on CTO-authored scenario lists

Rejected. CTO review remains an approval gate, but coverage cannot depend on
one person's memory or imagination.

### Execute the complete Cartesian product

Rejected for MVP. It is expensive, slow, and obscures risk. The approved model
uses pairwise coverage as a floor and mandates high-risk tuples explicitly.

### Use exploratory testing only

Rejected as a release gate. Exploration discovers gaps but is not stable,
repeatable regression evidence until converted into frozen nodes.

## Impact

- Product authors must update the affected coverage inventory.
- Harness authors must implement frozen nodes and applicable five-oracle
  assertions without changing product behavior.
- Reviewers must challenge scenario completeness, oracle truth, mutations, and
  evidence provenance separately.
- Runtime verifiers must execute frozen candidates in isolated fresh runtimes.
- The CTO owns scope, mandatory tuples, waivers, coverage debt, and release
  decisions.

HE1 changes documentation only. Machine-validated inventory tooling and
risk-first workflow backfill require separate HE2 and HE3 authorization.

## Implementation

1. Publish the harness engineering governance standard.
2. Link it from the canonical AI read order and AI operating rules.
3. Clarify its precedence over legacy unit-test mocking conventions for
   authoritative integration and browser evidence.
4. In HE2, define a machine-validated inventory and coverage-debt format.
5. In HE3, backfill the highest-risk customer workflows first.

## Validation

- The standard defines product surfaces, state dimensions, mandatory tuples,
  five oracles, lifecycle gates, mutation rules, metrics, debt, and exploration.
- Canonical documentation points agents to the standard before acceptance work.
- P0/P1 closure requires retained regression coverage or explicit CTO debt.
- The HE1 change set contains documentation only.

## Related Decisions

- `docs/contracts/test_contract.md`
- `docs/ai/AI_TEAM_OPERATING_RULES.md`
- `docs/ai/AGENT_DELEGATION_PROTOCOL.md`

## Notes

The H2-B-R3 public password-recovery interceptor repair remains an independent
product candidate and review gate. This decision neither approves nor merges
that candidate.
