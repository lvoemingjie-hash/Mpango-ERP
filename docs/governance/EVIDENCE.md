# Evidence and Verification Policy

## Purpose

Mpango uses AI agents heavily, so a confident narrative is never evidence by
itself. Every task declares its risk, verification tier, claim ceiling, exact
scope, frozen refs, stop conditions, and next gate before execution.

## Verification tiers

| Tier | Meaning | Maximum normal claim |
|---|---|---|
| V0 | Forensic, diagnostic, or metadata correction | No product PASS |
| V1 | Source, static, focused tests, bounded mutation review | Source/test authenticity only |
| V2 | Task-owned integration runtime | Integration behavior in that environment |
| V3 | Independent merge-critical fresh runtime | Candidate runtime authority for auth, tenancy, finance, inventory, migrations, or global state |
| V4 | Release/cross-host validation | Release evidence, still separate from deployment evidence |

The minimum tier is selected from risk, claim, and change class. A task may
raise but not lower it.

## Evidence owners

| Owner | Responsibility |
|---|---|
| Zcode / implementation agent | Bounded implementation, causal diagnosis, focused gates, candidate evidence |
| Kilo | Independent scope, source, test, mutation, and evidence-authenticity review |
| Lubuntu execution agent | Fresh-host runtime authority at an exact candidate SHA |
| CTO / Codex | Tier selection, frozen refs, STOP discipline, evidence reconciliation and controlled merge authorization |

Evidence from one owner does not silently become another owner's evidence.

## Environment preflight

Authoritative runtime work starts only after a cheap machine-readable preflight
proves environment ownership and contract compatibility. Record names and
presence booleans, not secret values.

Minimum preflight dimensions include:

- candidate and profile SHAs, clean worktree, canonical CWD;
- runtime/tool versions and exact entry point;
- task-owned PostgreSQL/Redis, role capabilities, safe DB name and ports;
- Alembic single head and declared lineage;
- Redis DB and fallback/sentinel traps;
- required environment names;
- frontend strict port/browser availability;
- EOL, UTF-8, BOM and cleanup ownership.

Any RED before authorization produces `VOID_ENVIRONMENT_PRECHECK`, cleanup and
STOP. Continuing after a mandatory stop makes later green output diagnostic only.

## Mandatory report contract

Every implementation or review report records:

```text
TASK
EXECUTOR
BASE
CANDIDATE
VERIFICATION_TIER
CLAIM_CEILING
EXACT_SCOPE
RESULT
EVIDENCE_BRANCH_OR_PATH
OPEN_RISKS
STOP_CONDITIONS
NEXT_GATE
```

Also include branch, full commit, parent, changed files, tests, report path,
environment classification, cleanup, and whether local/remote equality was
verified after publication.

## Test coverage delta

A full suite with zero red and coverage of new code paths are separate gates.
Every behavior-changing report includes:

```text
TEST_FILES_ADDED
TEST_FILES_MODIFIED
TEST_NODES_ADDED_OR_CHANGED
CODE_PATH_TO_TEST_MATRIX
NEGATIVE_AND_FAILURE_PATHS
TEST_AUTHENTICITY
FALSIFICATION_RESULT
UNCOVERED_NEW_PATHS
FULL_SUITE_RESULT
UNCHANGED_TEST_JUSTIFICATION
```

Rules:

1. Map every new or changed behavior to exact test nodes.
2. Label real HTTP/DB/browser/component tests separately from mocks and fixtures.
3. Demonstrate that removal or weakening of the guard makes a relevant test RED.
4. Prove modified tests did not weaken pre-existing assertions.
5. `UNCOVERED_NEW_PATHS` must be `0` for a completed implementation claim.
6. If test files did not change, identify the existing nodes that hit the new
   path and provide falsification evidence.
7. Docs/evidence-only changes may use `TEST_DELTA=NOT_APPLICABLE` only after
   proving product and test bytes did not change.

Recommended matrix:

| Code path or contract | Test node | New/changed/existing | Authenticity | Positive proof | Negative/falsification | Status |
|---|---|---|---|---|---|---|

## Documentation linkage delta

Every task that adds or changes a navigation, architecture, state, contract or
runbook document includes:

```text
DOCUMENTATION_FILES_ADDED_OR_CHANGED
PREDECESSOR_DOCUMENTS_REVIEWED
CONTRACT_INDEX_LINKS_ADDED_OR_CHANGED
SUPERSEDED_DOCUMENTS_AND_REASON
BROKEN_LINK_SCAN_RESULT
UNLINKED_RELEVANT_CONTRACTS
```

Rules:

1. `START-HERE`, overview, data-map and state pages summarize contracts; they do
   not replace contracts by omission.
2. A new canonical document must link to its predecessor and update the contract
   index plus every higher-level navigation page that names the topic.
3. Superseded documents remain in place until a separate reference-safe archive
   task proves no required links, ledgers or evidence depend on their path.
4. Deletion is never part of an incidental navigation cleanup.
5. `UNLINKED_RELEVANT_CONTRACTS` must be `0` for a completed documentation claim,
   or each remaining item must be an explicit finding with an owner and next gate.

## Evidence tiers inside a report

Use explicit labels:

- `EXECUTOR_INDEPENDENTLY_EXECUTED_EVIDENCE`
- `CANDIDATE_PROVIDED_EVIDENCE`
- `SAME_TREE_REUSED_EVIDENCE`
- `DIAGNOSTIC_ONLY`
- `NOT_EXECUTED`
- `HOST_LIMITATION`

Never convert a supplied total into independent evidence merely by quoting it.

## Publication integrity

- Reports are committed from the reviewed candidate unless a task explicitly
  defines a linear report correction.
- A commit cannot predeclare its own SHA or post-push local/remote equality.
- Evidence manifests are self-excluding and recomputed from committed blobs.
- Detect-secrets runs in a non-rewriting mode; baseline bytes are checked before
  and after.
- Historical conclusions are superseded, not rewritten.

## STOP conditions

STOP on scope drift, candidate drift, missing required tool/gate, secret
exposure, mutation false-green, failed byte restore, invalid preflight, continued
execution after RED/VOID, contradictory evidence, or an unsupported claim ceiling.

Passing a source review authorizes only the next declared gate. It never implies
merge, deployment, or customer readiness.
