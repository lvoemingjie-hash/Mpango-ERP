# Decision Register: HE2 Machine-Enforced Harness Governance Tooling

**Decision ID:** DR-2026-08-25-002
**Title:** Machine-Validated Coverage Inventory, Debt, and Interaction Governance
**Status:** Approved
**Date:** 2026-08-25
**Authority:** CTO directive DC-12R1-MVP-L1-HE2, on baseline 666af8a6

## Context

DR-2026-08-25-001 adopted the harness engineering governance standard (HE1)
as documentation only. Without machine validation, the standard depends on
voluntary compliance: inventory rows could lose required fields, node IDs
could be silently deleted or reordered, BLOCKED cells could lose owners, and
coverage claims could drift from evidence — all without any gate noticing.

HE2 (standard section 20) authorizes exactly this tooling as a separate
bounded task: a machine-validated inventory schema, required-field validator,
duplicate ID/order checks, coverage-debt report, and cross-cutting registry.

## Decision

Adopt `harness-governance/` as the machine-enforced governance system:

1. **Schemas** (`harness-governance/schemas/`): draft-07 JSON Schemas for the
   inventory node contract (HE1 §9: 18 fields, five oracles, status enum,
   risk, mutation, owner, evidence SHA), coverage debt (HE1 §13), critical
   interactions (HE1 §15), waivers, and protocol deltas.
2. **Validator** (`harness-governance/validator/harness_governance_validator.py`):
   Python 3.11+ standard library only. Enforces schema conformance plus
   semantic rules: duplicate IDs, blank or non-exact oracle sentinels, unknown
   statuses, P0/P1 nodes without mutations, BLOCKED nodes without owner or
   debt, PASS without a 40/64-hex evidence SHA, incomplete debt entries, and
   reference integrity.
3. **Drift control**: against a CI-provided baseline, silent node deletion,
   reorder, and unregistered renames are RED unless a reviewed protocol delta
   (`protocol-deltas.json`) records the change.
4. **Inventory-sync control**: changes to governed prefixes (`backend/`,
   `frontend/src/`, `scenarios/`, validator and schema directories) must
   co-change the governed inventory state, or carry a temporary waiver with
   owner, risk statement, and expiry. Expired waivers are RED. Waiver-file
   changes do not themselves satisfy the sync rule.
5. **Critical-interaction registry**: the seven required mechanisms (auth
   interceptor, tenant routing, rate limiting, idempotency, token replay,
   transaction rollback, mobile navigation) are registered with real source
   anchors and mandatory tuples; removing any required category is RED.
6. **CI gate** (`.github/workflows/harness-governance-gate.yml`): mandatory on
   every pull request and push targeting `product-dev-recovered`. It runs the
   unit tests, a 14-mutation deterministic RED gate with two GREEN controls,
   and the validator against the branch point, publishing the coverage
   summary and debt summary. BLOCKED and NOT_COVERED never count as PASS.

## Rationale

Governance that is not machine-checked degrades to documentation. The three
J1/H2 failure classes (missing journey reachability, untested interceptor
composition, incorrect oracle) were all structural: each would have been
visible as a missing or malformed inventory cell long before release review
if the inventory had been a validated, diff-enforced artifact.

Standard library only: the gate must run in CI with zero new third-party
dependencies, so it cannot itself become a supply-chain or budget problem.

## Alternatives Considered

### jsonschema library validation only

Rejected as sufficient: schema conformance cannot express cross-field rules
(BLOCKED needs an owner and a debt entry; P0/P1 need mutations) or baseline
drift. A stdlib subset checker plus semantic layer does, with no dependency.

### Enforce on every branch immediately

Rejected: enforcement binds changes after adoption (bootstrap skip when the
baseline predates the governance tree), otherwise the adopting change set
itself would be indefinitely RED.

### Full business inventory backfill inside HE2

Rejected: out of scope. The seed inventory (13 nodes) proves the machinery
and makes no coverage claim; HE3 owns risk-first backfill.

## Impact

- Product authors changing `backend/`, `frontend/src/`, `scenarios/`, or the
  governance tooling must co-update the inventory state or file a waiver.
- Harness authors get an enforced node contract; silent ID deletion, reorder,
  or oracle blanking fails CI.
- Reviewers get machine-derived coverage and debt summaries in which BLOCKED
  is visible and never counted as PASS.
- The CTO owns waiver approval, protocol deltas, and debt milestones.

## Validation

- `python -m unittest discover -s harness-governance/tests -p "test_*.py"` —
  31 tests GREEN.
- `python harness-governance/tests/run_red_mutations.py` — all 14 mutations
  RED with intended codes, both controls GREEN.
- `python harness-governance/validator/harness_governance_validator.py
  --root .` — GREEN on the seed tree with zero coverage claims.
- No third-party imports anywhere under `harness-governance/`.

## Related Decisions

- DR-2026-08-25-001 (harness engineering governance standard, HE1)
- HE3 (risk-first workflow backfill) — separately authorized, not started here

## Notes

The HE2 change set adds governance tooling, one CI workflow, and register
entries only. It changes no backend, frontend, test, migration, deployment,
or dependency code.

## R1 Addendum (DR-2026-08-25-002-R1): Bypass Closure

**Date:** 2026-08-25
**Authority:** CTO directive DC-12R1-MVP-L1-HE2-R1, on HE2 checkpoint 94b0c300

Review of the HE2 gate identified bypass classes; R1 closes them
machine-side (validator 2.0.0):

1. **Governance self-protection.** `governed-paths.json` no longer controls
   whether the governance core is governed: the workflow, the config file,
   `validator/`, `schemas/`, and `tests/` are hardcoded protected paths,
   changeable only through a `kind=governance` protocol delta (owner,
   reason, approval_ref, base_sha). `governed_prefixes` cannot be emptied,
   duplicated, or lose `backend/`, `frontend/src/`, `scenarios/`.
2. **Semantic sync.** "Any inventory file changed" no longer satisfies the
   gate. Each changed governed path must be covered by a record that
   *semantically changed* this comparison (node anchor, interaction
   source/affected path, debt `affected_paths`, or an eligible new delta).
   Notes-only edits and unrelated JSON churn stay RED; uncovered paths are
   named.
3. **Fail-closed waivers.** `paths` required/unique/non-empty, no wildcards
   or repo-root forms; owner, reason, risk (P0–P3), approval_ref, opened_on,
   expires_on required; union coverage per changed path; expired waivers
   always RED; the governance core is never waivable.
4. **PASS evidence authenticity.** 40-hex SHAs must be existing commits
   reachable from fetched refs/tags with `evidence_paths` present at that
   commit; 64-hex digests must bind `evidence_commit` and match the blob
   bytes; all-zero, dangling, wrong-path, and wrong-digest claims are RED;
   unverifiable contexts fail closed. The seed still claims 0 PASS.
5. **Delta anti-replay.** Deltas carry base_sha bound to the comparison
   base; historical deltas are single-use; kind-precise authorization;
   unauthorized status transitions (leaving PASS/FAIL, NOT_APPLICABLE in or
   out, reopening CLOSED debt) are violations, not warnings.
6. **Fail-closed schema checking.** Unknown schema keywords and
   unresolvable $refs are RED; `uniqueItems` enforced; source anchors must
   exist with in-range line numbers.
7. **Structural vs release gates.** STRUCTURAL_GATE (PASS/FAIL) is the PR
   gate; RELEASE_GATE (PASS/BLOCKED) fails release runs while open P0/P1
   release-blocking debt exists (`--mode release`, exit 3). Registered debt
   does not block ordinary PRs; structural GREEN is never a release
   statement.

**R1 validation:** 66 unit tests GREEN (original 31 kept or strengthened);
30 RED mutations (14 original + 16 new including the release-mode proof)
plus 5 GREEN controls and a candidate-tree integrity check all pass on the
committed tree. R1 changes no backend, frontend, business-test, migration,
dependency, or deployment code.
