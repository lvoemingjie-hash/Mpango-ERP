# AI Team Operating Rules

This file defines the operating rules for Mpango ERP AI agents.

It complements `docs/contracts/AI workrules.md`.
That contract is the broad engineering charter.
This file is the practical team discipline for day-to-day multi-agent work.

## Required Startup

Before starting any task, every AI agent must:

1. Fetch the latest remote state.
2. Confirm the active branch.
3. Read:
   - `docs/ai/README.md`
   - `docs/ai/PROJECT.md`
   - `docs/ai/PROJECT_MEMORY.md`
   - `docs/ai/HARNESS_ENGINEERING_GOVERNANCE_STANDARD.md` when the task adds,
     changes, reviews, or executes tests or acceptance evidence
4. Read the track-specific handoff skill if one exists.
5. State the intended scope and files before editing.

## Branch Discipline

- Product work belongs on the active product branch, currently `product-dev-recovered`.
- Platform work belongs on `platform-dev`.
- Do not commit product ledger or product code to `platform-dev`.
- Do not commit platform ledger or platform code to the product branch.
- Shared governance docs must stay synchronized across long-lived branches.
- If shared docs drift, stop feature work and reconcile docs first.

## CTO Instruction Compliance Check

No AI may report `COMPLETE` only because code changed and tests passed.

Before reporting completion, the AI must add a `CTO Instruction Compliance Check`
section to the relevant ledger.

The section must include:

1. A row for every CTO constraint in the task.
2. Implementation evidence for each constraint.
3. Test evidence for each constraint.
4. At least two counterexamples that could satisfy the literal wording but violate the CTO intent.
5. The test that proves each counterexample is rejected.
6. A completion claim of `COMPLETE`, `PARTIAL`, or `BLOCKED`.

Use this table:

```md
## CTO Instruction Compliance Check

| CTO instruction | Implementation evidence | Test evidence | Status |
|----------------|-------------------------|---------------|--------|
| ... | ... | ... | PASS / FAIL / NOT COVERED |

## Counterexample Check

| Counterexample | Expected behavior | Test coverage |
|----------------|-------------------|---------------|
| ... | ... | ... |

## Completion Claim

- COMPLETE only if every CTO constraint has implementation evidence and test evidence.
- PARTIAL if any constraint lacks evidence.
- BLOCKED if semantics are unclear or require CTO decision.
```

If a constraint is not tested, do not report `COMPLETE`.

## Validation Discipline

Agents must separate:

- Code blockers
- Environment blockers
- Test-data blockers
- Branch or synchronization blockers

Do not hide an environmental blocker inside a success claim.
Do not describe endpoint-function tests as full route-level tests.
Do not describe a visibility push as final approval.

For product acceptance and release evidence, agents must follow
`docs/ai/HARNESS_ENGINEERING_GOVERNANCE_STANDARD.md`. Code coverage and a green
suite are not sufficient by themselves. The report must identify scenario,
state-pair, failure-class, cross-cutting interaction, oracle, mutation, and
journey-reachability coverage as applicable.

Every P0/P1 product defect must produce a retained deterministic regression
node or an explicit CTO-owned coverage-debt item. Exploratory findings do not
become PASS evidence until converted into a frozen, reproducible node.

## Escalation

Stop and ask for CTO review when:

- A task touches auth, RBAC, tenancy, session handling, migrations, or money movement.
- A requested change crosses product and platform ownership.
- A test passes but a counterexample still violates the business intent.
- Two branches disagree on shared governance docs.
- The working tree contains unrelated files that would be swept into the commit.

## Completion Standard

A task is not ready for CTO review until:

1. The implementation matches the task scope.
2. The CTO Instruction Compliance Check is complete.
3. Relevant tests were run or blockers were documented.
4. The ledger truthfully records what was and was not validated.
5. The diff contains only intended files.
