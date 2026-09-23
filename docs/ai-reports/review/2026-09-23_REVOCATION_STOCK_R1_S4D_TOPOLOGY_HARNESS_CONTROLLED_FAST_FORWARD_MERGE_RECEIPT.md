# Revocation & Stock R1 S4-D Topology Harness Controlled Fast-Forward Merge Receipt

Date: 2026-09-23

## Disposition

`CONTROLLED_FAST_FORWARD_COMPLETE`

The working contract branch was advanced by fast-forward only after independent
CTO reconciliation of the author candidate and the Fresh Kilo R0, R1, and R2
evidence. This receipt is report-only and is not part of the merged candidate.

## Git Identity

- Target branch: `codex/order-state-r2-e1-source-revision-f1-f3-20260919`
- Previous tip: `c24bbab6b7a10c88ec50c821918d3977cbdad9a2`
- Merged candidate: `a78f544098bba55bbb0cba6f2ee9c5b84cddf86a`
- Candidate tree: `e458ce4e88cd97778f8bf01dc9efe0579771cd4f`
- Candidate parent: `c24bbab6b7a10c88ec50c821918d3977cbdad9a2`
- Advancement: one ordinary successor, no merge commit, `git merge --ff-only`
- Remote verification: `origin` target ref equals the merged candidate after push

The cumulative candidate delta is exactly:

- `backend/tests/conftest.py`
- `backend/tests/test_s4d_fixture_db_authority_contract.py`

Product source drift is zero.

## Accepted Evidence

### Fresh Kilo R0

- Fixture authority contract: 10 passed, 0 failed, 0 errors, 0 skipped.
- S4-D topology nodes: 9 passed, 0 failed, 0 errors, 0 skipped.
- The runtime fixture no longer recreates the migration-owned public ledger
  guard; the read-only authority assertion runs before tenant DDL.

### Fresh Kilo R1

- M1 public-guard DDL reintroduction: all 9 S4-D nodes became semantically
  non-green with `permission denied` on `public`; byte-exact restore returned
  9/9 to green.
- M2 authority-assertion bypass: both named controls became semantic RED;
  byte-exact restore returned 2/2 to green.
- Main regression profile A: 299 passed, 16 expected opt-in skips, 0 failed,
  0 errors; the skip set matched the frozen expected set exactly.

### Fresh Kilo R2

- A single Profile C supplied all runtime variables to preflight, collection,
  the formal invocation, and final product verification.
- Frozen acceptance: 84 passed, 0 failed, 0 errors, 0 skipped, exit code 0.
- JUnit contained 84 cases and matched the frozen 84-node sequence exactly,
  including the two duplicate parameterized node IDs present in both inputs.
- Final product `--verify` returned 0; guard OID, owner, body digest, and runtime
  privileges showed no drift; task Redis DB 15 and disposable resources had no
  residue.
- Report bundle SHA-256:
  `D8CF5E04E1F6F1B3FE83C66D16ACF1A25B920F8213565FDCBE61CF4F0E27B220`.

## Merge Controls

- `git fetch --all --prune` completed before promotion.
- The remote target was re-read immediately before merge and still equaled the
  frozen previous tip.
- `git merge-base --is-ancestor` succeeded.
- `git rev-list --count previous..candidate` returned `1`.
- `git rev-list --merges previous..candidate` returned no commits.
- `git diff --check previous candidate` was clean.
- The post-merge worktree was clean.
- The pushed remote ref was re-read and equaled the merged candidate.

## Boundaries

- `FULL_SUITE_RESULT=NOT_RUN_THIS_ROUND`
- `DEPLOYMENT_AUTHORIZED=NO`
- `PRICING_AND_FURTHER_ORDERING_AUTHORIZED=NO`
- `RESOURCE_INCIDENT_AUDIT=COMPLETE__ATTRIBUTION_PARTIALLY_UNKNOWN`
- `DEPLOYMENT_HOLD=REMAINS`

This merge closes the inherited S4-D test-topology error on the working
contract branch. It does not authorize deployment and does not resolve the
separate historical anonymous-volume attribution uncertainty.
