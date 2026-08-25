# Harness Governance (HE2) — Machine-Enforced Inventory Tooling

This directory implements **DC-12R1-MVP-L1-HE2** on top of the HE1 standard
(`docs/ai/HARNESS_ENGINEERING_GOVERNANCE_STANDARD.md`): the inventory,
coverage-debt, and critical-interaction documents become machine-validated
artifacts, and CI blocks changes that silently diverge from them.

**Scope guard:** HE2 delivers governance tooling only. The seed inventory here
proves the machinery against the J1/H2 incidents and the seven required
cross-cutting interactions; it deliberately claims no coverage (no node is
PASS, no evidence SHA is set). Risk-first business backfill is separately
authorized under HE3.

## Layout

```
harness-governance/
  governed-paths.json        data-driven config: governed prefixes, sync paths,
                            required interaction categories
  schemas/                   machine-parseable JSON Schemas (draft-07)
    inventory.schema.json    node contract: HE1 §9 fields, five oracles, status
    coverage-debt.schema.json debt contract: HE1 §13 fields
    critical-interactions.schema.json registry contract: HE1 §15
    waivers.schema.json      temporary waiver contract
    protocol-deltas.schema.json  reviewed removal/rename/reorder/reclassify
  inventory/                 the governed state (what CI diffs against)
    inventory.json           seed: 13 nodes, honest statuses only
    coverage-debt.json       seed: 3 owned debts (P0 HE3 backfill, real-device)
    critical-interactions.json  the 7 required mechanisms with real anchors
    waivers.json             active waivers (empty; expired ones are RED)
    protocol-deltas.json     inventory identity changes (empty)
  validator/
    harness_governance_validator.py  stdlib-only validator + summaries + CLI
  tests/
    test_harness_governance_validator.py  unit tests (unittest)
    run_red_mutations.py     14 deterministic RED mutations + 2 GREEN controls
```

## Usage

```bash
# local, no baseline: structure + semantics + summaries only
python harness-governance/validator/harness_governance_validator.py --root .

# the CI check: drift + inventory-sync versus the integration branch
python harness-governance/validator/harness_governance_validator.py \
  --root . --baseline-ref origin/product-dev-recovered

# deterministic test batteries
python -m unittest discover -s harness-governance/tests -p "test_*.py" -v
python harness-governance/tests/run_red_mutations.py
```

Exit codes: `0` GREEN, `1` RED (merge blocked), `2` environment error.
Useful flags: `--today YYYY-MM-DD` (deterministic waiver evaluation),
`--report-json`, `--markdown-summary`, `--baseline-dir` (filesystem baseline,
used by the tests). Python 3.11+, standard library only — no new third-party
dependencies anywhere in this directory.

## What the validator enforces

| Code | Rule |
|---|---|
| `SCHEMA-*` | every document must satisfy its JSON Schema (types, required fields, enums, patterns, `additionalProperties: false`) |
| `INV-DUP-ID` / `DEBT-DUP-ID` / `REG-DUP-ID` / `WVR-DUP-ID` / `DELTA-DUP-ID` | no duplicate IDs in any registry |
| `INV-ORACLE-EMPTY` | a blank oracle means NOT_COVERED, never PASS; blank or whitespace oracles are RED |
| `INV-ORACLE-INVALID` | non-applicable oracles must use the exact sentinel `NOT_APPLICABLE` |
| `INV-STATUS-UNKNOWN` (via `SCHEMA-ENUM`) | status must be one of PASS / FAIL / BLOCKED / NOT_RUN / NOT_APPLICABLE |
| `INV-MUTATION-MISSING` | P0/P1 nodes require a mutation or counterexample ID (HE1 §11) |
| `INV-BLOCKED-OWNER` | BLOCKED requires `blocked_owner` and `blocked_closure_condition` (HE1 §9.18) |
| `INV-BLOCKED-DEBT` / `INV-FAIL-DEBT` | BLOCKED and FAIL nodes must be tracked in an open debt entry |
| `INV-PASS-EVIDENCE` | PASS requires a 40- or 64-hex evidence SHA — no fabricated greens |
| `DEBT-INCOMPLETE` | BLOCKED/NOT_COVERED debts need owner, reason, closure condition, target milestone (HE1 §13) |
| `DEBT-NODE-REF-UNKNOWN` / `REG-REF-UNKNOWN` | cross-references must resolve |
| `REG-CATEGORY-MISSING` | the seven required interaction categories must stay registered |
| `WVR-EXPIRED` / `WVR-INVALID-DATE` | an expired or malformed waiver is RED, always — renew or remove it |
| `DRIFT-SILENT-DELETE` | a node removed versus the baseline without a `removal` protocol delta |
| `DRIFT-REORDER` | node order changed without `reorder` deltas (order is canonical, HE1 §9) |
| `DRIFT-RENAME-UNKNOWN` / `DRIFT-RENAME-UNREGISTERED` | renames must reference a real baseline ID and carry a `rename` delta |
| `SYNC-INVENTORY-MISSING` | governed product/test/harness paths changed without an inventory update or an active waiver |

Warnings (never RED): `ANCHOR-MISSING` (anchor path absent in this tree) and
`DRIFT-STATUS-RELABEL` (executed status changed; history must be preserved per
HE1 §16).

## The inventory-sync rule (requirement 6 of the directive)

When a change touches any prefix in `governed-paths.json` (`backend/`,
`frontend/src/`, `scenarios/`, `harness-governance/validator/`,
`harness-governance/schemas/`), the same change must also update the governed
state under `harness-governance/inventory/` — **except** `waivers.json`,
because a waiver is the alternative to an inventory update, not an update
itself. Otherwise the change must carry a temporary waiver:

```json
{
  "waiver_id": "WVR-EXAMPLE-001",
  "scope": "inventory-sync",
  "reason": "dependency bump only; no behavioral surface change",
  "owner": "cto",
  "risk": "low: lockfile-only change, no API or UI surface affected",
  "expires": "2026-09-15"
}
```

A waiver is active on its expiry day and RED the day after. Expired waivers
may not stay parked in the file — remove or renew them; history lives in git.

## Baselines and bootstrap

The CI job (`harness-governance-gate.yml`, mandatory for PRs and pushes to
`product-dev-recovered`) compares against `origin/product-dev-recovered` on
pull requests and against the previous pushed commit on pushes. When the
baseline predates this governance system (no `governed-paths.json`), drift and
sync checks bootstrap-skip — enforcement binds every change **after** adoption.
The unit tests and mutation gate always run.

## How the summaries count (requirement 9)

Pass rate is `PASS / (total − NOT_APPLICABLE)`. BLOCKED, NOT_RUN, and
NOT_COVERED debt all count **against** coverage; BLOCKED is an honest state,
never a passing one. Oracle completeness is the share of nodes with all five
oracles explicit (assertion or `NOT_APPLICABLE`). The same figures are emitted
to stdout, `--report-json` (machine), `--markdown-summary` (CI step summary),
and the debt table lists every open debt with owner and milestone.

## Mutation sensitivity (requirement 8)

`run_red_mutations.py` tampers with a copy of the real governance tree and
asserts the validator goes RED with the intended rule code — 14 mutations
covering duplicate IDs, blank oracles, unknown status, missing P0 mutations,
missing blocked owners, silent deletion, reorder, expired waivers on unsynced
changes, fake evidence SHAs, incomplete debts, missing registry categories,
orphaned BLOCKED nodes, and dangling references. Two GREEN controls (pristine
tree; active waiver covering a governed change) prove the gate still passes
when it should. A mutation that escapes (stays GREEN) fails CI.
