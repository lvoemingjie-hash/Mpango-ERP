# Harness Governance (HE2-R1) — Machine-Enforced, Bypass-Closed Inventory Tooling

This directory implements **DC-12R1-MVP-L1-HE2** and its bypass-closure
revision **DC-12R1-MVP-L1-HE2-R1** on top of the HE1 standard
(`docs/ai/HARNESS_ENGINEERING_GOVERNANCE_STANDARD.md`): the inventory,
coverage-debt, and critical-interaction documents are machine-validated
artifacts, and CI blocks changes that silently diverge from them — including
changes that try to satisfy the gate by touching files without changing the
governed semantics.

**Scope guard:** HE2/R1 deliver governance tooling only. The seed inventory
proves the machinery against the J1/H2 incidents and the seven required
cross-cutting interactions; it deliberately claims no coverage (no node is
PASS, no evidence SHA is set). Risk-first business backfill is separately
authorized under HE3.

## HE2-ET1: execution traps + authority runner

The execution-traps registry (`harness-governance/inventory/execution-traps.json`)
is a hardcoded JSON catalog of 15 machine-verifiable traps (P0/P1/P2 mix);
the validator schema (`execution-traps.schema.json`) enforces
`additionalProperties=false` and the data shape (trap_id, category, risk,
applies_to, evaluator_id, stop_phase, stable_exit_code, required_evidence,
forbidden_next_phases, negative_control_id, owner, remediation,
source_evidence_refs, status). Authority profiles
(`authority-profiles.json` + `authority-profiles.schema.json`) name the
required traps per profile (any P0/P1 trap not referenced by any profile
fails closed). The fail-stop authority runner
(`harness-governance/validator/authority_runner.py`) is the single gate
between an environment and an authoritative command; only the SAME runner
process that completes preflight + exact collection + a just-in-time
recheck may launch the authority command, the authorization proof is bound
to a random nonce + candidate SHA + profile SHA + node-manifest SHA + a
wall-clock boundary, and an externally edited JSON cannot resume a run.

Manual CI equivalence (delegated to the runner):
```
cd /c/Users/Jeff0/MPANGO ERP/worktrees/zcode-he2et1-gov-2026-08-28/harness-governance
python validator/harness_governance_validator.py
python tests/run_red_mutations.py
python tests/test_harness_governance_validator.py
python tests/test_authority_runner_et1.py
python validator/authority_runner.py --self-test
```

The ET1 mutations (`tests/et1_mutations.py`) are appended to the HE2 mutation
gate, and the ET1 unit tests (`test_authority_runner_et1.py`) add 20 tests to
the suite (116 total). The protocol delta `PD-2026-08-28-HE2-ET1` authorizes
the new registry, schemas, profile, runner, and the related protected-path
additions.

## HE2-ET1-R1: end-to-end authority execution and child-process proof closure

R1 closes the runner's missing last mile: the authority command is a REAL
argv launch (never a shell string) and the collect set comes from a REAL
`pytest --collect-only` child process running the runner-owned plugin
(`tests/pytest_et1_collector.py`). Division of proof:

- The child's `pytest_sessionstart` re-verifies role (live PG: not superuser,
  has CREATEDB), TEST_DATABASE_URL presence, temp-DB capability flag, runner
  nonce, and candidate/profile/manifest bindings inside the child process.
- The child's `pytest_collection_finish` recomputes the live candidate HEAD
  and the profile/manifest file-byte SHAs, compares them against the
  runner-provided values, and writes the proof with the REAL node IDs.
- The runner compares the child's nonce against the ORIGINAL it minted
  (cross-process; self-comparison is a defect), requires the plugin's proof
  schema marker, checks count + uniqueness + exact set against the frozen
  node manifest (`inventory/et1-node-manifest.txt`), and only then
  authorizes.
- `candidate_sha` is the live `git rev-parse HEAD`; `profile_sha` and
  `manifest_sha` are SHA-256 over actual file bytes; lineage comes from live
  git refs (parent `HEAD^`, chain base resolved via `git rev-parse`).
- The authority profile is loaded from an explicit `--profile` path and
  validated against the JSON schema + trap registry; a hardcoded
  `{"mode":"cli"}` document can never pass.
- The state machine enforces an explicit `ALLOWED_TRANSITIONS` map; every
  trap lands VOID on disk (never COLLECT/AUTHORIZED/RUNNING after a
  failure); the command is launched exactly once (counter-guarded); a
  non-zero exit is the product test's REAL verdict (FINISHED + exit code,
  never VOID).
- Publishing (`--publish-dir`) is sanitized: variable presence, labels,
  counts, and booleans only — never values.

Manual CI equivalence (delegated to the runner):
```
cd /c/Users/Jeff0/MPANGO ERP/worktrees/zcode-he2et1r1-e2e-2026-08-28
uv run --with pytest --with psycopg --with psycopg-binary \
  python harness-governance/validator/authority_runner.py --self-test
uv run --with pytest --with psycopg --with psycopg-binary \
  python -m unittest discover -s harness-governance/tests -p "test_*.py"
uv run --with pytest --with psycopg --with psycopg-binary \
  python harness-governance/tests/run_red_mutations.py

# E2E core chain (needs the round's gate PG + redis env vars):
#   TEST_DATABASE_URL        non-superuser CREATEDB role (e.g. container he2et1r1_pg16 :15445)
#   TEST_DATABASE_URL_SUPER  instance superuser (proves the superuser trap)
#   PW1R3_TEST_REDIS_URL     redis URL with /15 db
#   MPANGO_ALLOW_TEMP_DB_CREATE=1
uv run --with pytest --with psycopg --with psycopg-binary \
  python harness-governance/tests/run_e2e_core_chain.py
```

The R1 behavioral mutations (`tests/et1_e2e_mutations.py`) patch the
candidate runner/plugin with a specific weakening (self-compare restore,
actual=expected, command=None, foreign proof origin, state jumps, disabled
child sessionstart gate, duplicate nodes, hardcoded profile, env leaking,
double launch, nonzero→VOID, dropped file-byte bindings, dropped expiry,
hardcoded candidate, deleted child plugin) and an in-process probe must
report the gate WEAKENED; pristine-candidate and byte-exact-restore
controls guard the pattern. Total gate: 66 RED / 9 GREEN. The protocol
delta `PD-2026-08-28-HE2-ET1-R1` authorizes the R1 changes with
base_sha=aaff330e.


## Layout

```
harness-governance/
  governed-paths.json        data-driven config: governed prefixes, required
                            interaction categories (hardcoded floor applies on top)
  schemas/                   machine-parseable JSON Schemas (draft-07 subset)
    governed-paths.schema.json   config contract (non-empty, unique prefixes)
    inventory.schema.json    node contract: HE1 §9 fields, five oracles, status,
                            evidence binding fields (evidence_paths/evidence_commit)
    coverage-debt.schema.json debt contract: HE1 §13 fields + affected_paths
    critical-interactions.schema.json registry contract: HE1 §15 + affected_paths
    waivers.schema.json      fail-closed waiver contract (scoped, dated, approved)
    protocol-deltas.schema.json  single-use, base-bound, kind-precise deltas
  inventory/                 the governed state (what CI diffs against)
    inventory.json           seed: 13 nodes, honest statuses only
    coverage-debt.json       seed: 3 owned debts (P0 HE3 backfill, real-device)
    critical-interactions.json  the 7 required mechanisms with real anchors
    waivers.json             active waivers (empty; expired ones are RED)
    protocol-deltas.json     inventory identity changes + governance deltas
  validator/
    harness_governance_validator.py  stdlib-only validator + gates + CLI
  tests/
    test_harness_governance_validator.py  66 unit tests (unittest)
    test_authority_runner_et1.py  20 ET1 unit tests (unittest)
    run_red_mutations.py     66 deterministic RED mutations (48 tamper +
                             1 mode proof + 2 validator-scope + 15
                             authority-e2e) + 9 GREEN controls + candidate-
                             tree integrity check
    et1_mutations.py         ET1 registry/profile tamper mutations
    et1_e2e_mutations.py     R1 authority runner/plugin behavioral mutations
    pytest_et1_collector.py  runner-owned collect-only proof plugin
    _et1_collector_fixtures.py  stable node set collected by the runner child
    run_e2e_core_chain.py    8-case E2E core-chain gate (GREEN sentinel==1;
                             superuser/empty-url/capability/missing-command/
                             nonce-tamper/node-drift/profile-drift sentinel==0)
```

## Usage

```bash
# local, no baseline: structure + semantics + gates only
python harness-governance/validator/harness_governance_validator.py --root .

# the CI PR check: semantic sync + drift anti-replay vs the integration branch
python harness-governance/validator/harness_governance_validator.py \
  --root . --baseline-ref origin/product-dev-recovered --mode structural

# the release/milestone check: additionally requires no open P0/P1
# release-blocking debt (exit code 3 while blocked)
python harness-governance/validator/harness_governance_validator.py \
  --root . --mode release

# deterministic test batteries
python -m unittest discover -s harness-governance/tests -p "test_*.py" -v
python harness-governance/tests/run_red_mutations.py
```

Exit codes: `0` GREEN, `1` structural violations (merge blocked), `3` release
blocked (release mode only), `2` environment error. Useful flags:
`--today YYYY-MM-DD` (deterministic waiver evaluation), `--base-sha`
(delta base binding for `--baseline-dir` runs), `--report-json`,
`--markdown-summary`. Python 3.11+, standard library only — no third-party
dependencies anywhere in this directory.

## Gates (R1): structural vs release

Every run reports two gates:

- **STRUCTURAL_GATE** = PASS/FAIL — document and semantic validity. This is
  the mandatory PR gate (CI check name `HE2-R1 structural gate`, fixed for
  branch protection). Ordinary PRs are not blocked by already-registered
  debt.
- **RELEASE_GATE** = PASS/BLOCKED — BLOCKED while any open P0/P1 debt with
  `release_blocked: true` exists, even when structural passes. Structural
  GREEN is never a release statement. The `HE2-R1 release gate` CI job
  (workflow_dispatch) exits 3 while blocked.

## What the validator enforces

| Code | Rule |
|---|---|
| `SCHEMA-*` | every document must satisfy its JSON Schema; the subset checker is fail-closed: unknown schema keywords (`SCHEMA-UNKNOWN-KEYWORD`) and unresolvable `$ref`s (`SCHEMA-BAD-REF`) are RED, and `uniqueItems` is enforced |
| `CONFIG-PREFIXES-EMPTY` / `CONFIG-PREFIX-DUP` / `CONFIG-MINIMUM-PREFIX` | governed_prefixes cannot be emptied, duplicated, or lose the minimum product paths (`backend/`, `frontend/src/`, `scenarios/`) |
| `SYNC-PROTECTED-PATH` | the governance core (workflow, governed-paths.json, validator/, schemas/, tests/) is hardcoded-governed and never waivable; changes need a `governance` protocol delta |
| `SYNC-SEMANTIC-MISSING` | every changed governed path needs a *semantically changed* record covering it: a node whose anchors include the path, an interaction source/affected path, a debt `affected_paths` entry, or a new/modified eligible protocol delta. Notes-only edits, README touches, and unrelated JSON churn do not satisfy the gate; uncovered paths are named in the violation |
| `INV-DUP-ID` / `DEBT-DUP-ID` / `REG-DUP-ID` / `WVR-DUP-ID` / `DELTA-DUP-ID` | no duplicate IDs in any registry |
| `INV-ORACLE-EMPTY` / `INV-ORACLE-INVALID` | blank oracles mean NOT_COVERED, never PASS; non-applicable oracles must use the exact sentinel `NOT_APPLICABLE` |
| `INV-STATUS-UNKNOWN` (via `SCHEMA-ENUM`) | status must be one of PASS / FAIL / BLOCKED / NOT_RUN / NOT_APPLICABLE |
| `INV-MUTATION-MISSING` | P0/P1 nodes require a mutation or counterexample ID (HE1 §11) |
| `INV-BLOCKED-OWNER` / `INV-BLOCKED-DEBT` / `INV-FAIL-DEBT` | BLOCKED needs an owner, a closure condition, and an open debt entry; FAIL needs debt |
| `INV-PASS-EVIDENCE` | PASS requires a 40/64-hex evidence SHA shape |
| `EVIDENCE-SHA-INVALID` | all-zero evidence SHAs are RED |
| `EVIDENCE-COMMIT-MISSING` / `EVIDENCE-COMMIT-UNREACHABLE` | 40-hex evidence must be an existing commit reachable from a fetched branch or tag; 64-hex digests must bind via `evidence_commit` |
| `EVIDENCE-PATH-MISSING` / `EVIDENCE-BLOB-MISMATCH` | `evidence_paths` must exist at the evidence commit; a 64-hex digest must equal the SHA-256 of the blob bytes at `evidence_commit:evidence_paths[0]` |
| `EVIDENCE-UNVERIFIABLE` | PASS claims outside a git repository fail closed |
| `DEBT-INCOMPLETE` | BLOCKED/NOT_COVERED debts need owner, reason, closure condition, target milestone (HE1 §13) |
| `DEBT-NODE-REF-UNKNOWN` / `REG-REF-UNKNOWN` | cross-references must resolve |
| `REG-CATEGORY-MISSING` | the seven required interaction categories must stay registered |
| `WVR-EXPIRED` / `WVR-INVALID-DATE` | expired or malformed waivers are RED, always — renew or remove; a waiver is active on its expiry day and RED the day after |
| `WVR-PATH-INVALID` / `WVR-PATH-PROTECTED` | waiver paths are required, unique, non-empty, wildcard-free, not a repo-root form, and may never touch the governance core |
| `DRIFT-SILENT-DELETE` / `DRIFT-REORDER` / `DRIFT-RENAME-*` | node removal, reorder, and rename need eligible protocol deltas |
| `DELTA-REPLAY` | a delta byte-identical to the baseline copy is single-use history; relying on it again is RED |
| `DELTA-BASE-MISMATCH` | deltas only authorize the comparison whose `base_sha` they carry; an unbound comparison (no base SHA) authorizes nothing |
| `STATUS-UNAUTHORIZED` | relabeling executed results (leaving PASS/FAIL, or entering/leaving NOT_APPLICABLE, or reopening CLOSED debt) needs a `reclassify` delta; ordinary evidence flow (NOT_RUN/BLOCKED → PASS/FAIL/BLOCKED) does not |
| `ANCHOR-MISSING` / `ANCHOR-LINE-INVALID` | source anchors must point at existing files with valid, in-range line numbers (`path`, `path:LINE`, `path:START-END`) |

Warnings (never RED): `WVR-UNUSED` (active waiver matching no changed path)
and `WVR-OVERLAP` (two active waivers with overlapping scope).

## Waivers (fail-closed)

```json
{
  "waiver_id": "WVR-EXAMPLE-001",
  "scope": "inventory-sync",
  "reason": "dependency bump only; no behavioral surface change",
  "owner": "cto",
  "risk": "P2",
  "approval_ref": "CTO approval reference",
  "opened_on": "2026-08-25",
  "expires_on": "2026-09-15",
  "paths": ["backend/requirements.txt"]
}
```

Paths are exact repo paths or directory prefixes — required, unique, no
wildcards, no repo root, no implicit global exemption. The **union** of all
active waivers must cover *every* changed governed path not otherwise
mapped; a waiver matching one path never releases the others. The governance
core is not waivable at all — governance changes need a `kind=governance`
protocol delta (see `inventory/protocol-deltas.json` for the R1 example).

## Protocol deltas (single-use, base-bound, kind-precise)

Every delta carries `kind`, `affected_ids`, `affected_paths`, `base_sha`,
`owner`, `reason`, and `approval_ref`. A delta is eligible only when it is
new or substantively modified versus the baseline copy AND its `base_sha`
equals the validator's comparison base. Kinds authorize precisely:
`removal`, `rename` (both old and new id), `reorder`, `reclassify` (status
transitions), `governance` (protected paths, via `affected_paths`).

## Baselines and bootstrap

The CI structural gate compares against `origin/product-dev-recovered` on
pull requests and the previous pushed commit on pushes (`fetch-depth: 0` so
git objects and reachability checks work). When the baseline predates the
governance system (no `governed-paths.json`), drift/sync checks
bootstrap-skip — enforcement binds every change **after** adoption. The
unit tests and mutation gate always run.

## How the summaries count

Pass rate is `PASS / (total − NOT_APPLICABLE)`. BLOCKED, NOT_RUN, and
NOT_COVERED debt all count **against** coverage; BLOCKED is an honest state,
never a passing one. The same figures go to stdout, `--report-json`
(machine), `--markdown-summary` (CI step summary), and the debt table lists
every open debt with owner and milestone.

## Mutation sensitivity

`run_red_mutations.py` tampers with copies of the real governance tree and
asserts RED with the intended rule code: 29 tamper mutations (duplicate IDs,
blank oracles, unknown status, missing P0 mutations, missing blocked owners,
silent deletion, reorder, expired waivers on unmapped changes, fake
evidence, incomplete debts, missing registry categories, orphaned BLOCKED
nodes, dangling references, config self-protection attacks, notes-only
sync, partial path coverage, missing waiver paths, partial waiver coverage,
zero/nonexistent/unreachable evidence commits, missing evidence paths, blob
digest mismatch, historical delta replay, unauthorized relabeling, unknown
schema keywords, invalid refs) plus one mode proof (release-blocker debt can
never be reported as global GREEN). Five GREEN controls (pristine tree,
full scoped waiver, semantic record mapping, multi-waiver union, valid
committed evidence) prove the gate still passes when it should, and a
frozen-snapshot integrity check proves the gate never modifies the
candidate tree.
