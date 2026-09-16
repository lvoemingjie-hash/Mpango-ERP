# MPANGO_TENANT_BOOTSTRAP_DB_AUTHORITY_R1_R4 — V3 Merge-Critical Evidence Pack

- **Authorization:** CTO-AUTH-TENANT-BOOTSTRAP-DB-AUTHORITY-R1-R4-2026-09-16
- **Executor:** Kimi (authorization EXECUTOR field); executed in a ZCode agent
  session on Windows 10.0.26200 x64
- **Implementation candidate commit:**
  `efe70792246bca48ee5277b33c4476313e6c14e8`
  (branch `zcode/tenant-bootstrap-db-authority-r1-r4-2026-09-16`, created from
  the R1-R3 manifest tip `69e2d5b69df61a06a7790aadf7813ee214bc3249`)
- **Immediate R1-R3 predecessor:** `a21878c169d97e4c6fa837cd19dd9cced7de71e2`
- **Frozen R1-R2 predecessor:** `8951112bf126d70643dc64882c8bbee911321928`
  (both ancestry-checked by the preflight)
- **Historical regression comparison base:**
  `0a16ed707ad898e9924c26b28097148708677af9` (R1 manifest commit, retained so
  the bootstrap-heavy comparison chain stays comparable)
- **Verification tier:** V3_MERGE_CRITICAL_DATA_INTEGRITY_SECURITY
- **Claim ceiling:** AUTHOR_IMPLEMENTATION_AND_TASK_OWNED_V3_EVIDENCE_ONLY
- **Machine:** Docker 29.1.3, TWO fresh `postgres:16.15` clusters
  (`server_version_num 160015`; system identifiers
  `7686066100049936429` / `7686066113991970856`)
- **Formal invocations of the full gate set:** 1 (no `--skip` flags). Three
  pre-formal rehearsals (`--skip-regression`, scratch directories OUTSIDE the
  repository, non-evidence) were used to derive and confirm the mutation
  declarations; they produced no artifact in this pack.
- **Predecessor evidence:** R1, R1-R1, R1-R2 and R1-R3 commits, journals and
  evidence are untouched — this pack is new and additive.

## Why this round exists (Kimi R1-R3 review: NEED CHANGES, P1 control plane)

The R1-R3 harness declared two named REDs for MM5 while only one fired, and the
gate accepted any non-empty hit set, so "every mutation is semantically
falsified" did not follow from the evidence. R1-R4 repairs the verification
control plane. **No product-source change**: the provisioning/refusal logic
under test is byte-identical to the reviewed R1-R3 candidate (grants script
`fc0db066…`/`b2ee0eb4…` group digests unchanged), which the report proves via
its pre-run and restored digests.

### 1. MM5 split into two single-target mutations

| Mutation | Deleted guard | Required named RED | Observed RED set |
| --- | --- | --- | --- |
| MM5a `existing_database_refusal_deleted` | target-database-already-exists refusal | `test_wrong_password_provision_refused_zero_writes` | exactly that one node |
| MM5b `partial_role_set_refusal_deleted` | partial-role-set refusal | `test_partial_exists_first_deploy_refused_zero_writes` | exactly that one node |

Each mutation now fires its own declared node, so no declaration is
aspirational. The deleted guard is a genuine semantic deletion in both cases:
the state falls through to a *different* guard (the credential probe), so the
refusal reason changes and the counterexample's specific `is not fresh`
assertions are what catch it.

### 2. Exact named-RED set verification (fail closed)

Every mutation declares a required `named_red` set plus an explicit
`tolerated_red` set (nodes that MAY go RED because the same defect also trips
them). The declared universe is required ∪ tolerated, and
`mutation_red_set_verdict()` / `assert_mutation_red_set_exact()` fail closed
when:

- a required named RED did **not** fire (**missing**),
- any RED falls **outside** required ∪ tolerated (**extra/undeclared**),
- a mutation declares **no** required node (an empty contract), or
- nothing went RED at all.

The formal gate now verifies every mutation result with the exact-set
validator (the previous non-empty check is gone — asserted by a static test)
and publishes the per-mutation verdicts in
`phases.mutation_red_set_verdicts`. Formal results: **9/9 mutations
`exact_set_ok = true`, 0 missing, 0 undeclared**, every mutated script
parseable.

The validator also closed an inherited hole found in this round: MM2's
replacement carried a stray third double-quote in the owner-fallback's
empty-string default, so the mutated bootstrap script did not PARSE. Its "RED"
came partly from an import-failure cascade — six import-error nodes that
R1-R2/R1-R3 never declared and the old gate accepted. MM2 is repaired (valid
Python, genuinely semantic) and its observed set is now exactly its two
required nodes; `assert_mutation_is_semantic()` additionally ast-parses every
mutated script before its suite runs, so a broken tree can never again be
counted as a semantic detection.

### 3. Negative controls for the validator itself

The harness exercises its own validator with a synthetic case table BEFORE any
container starts and asserts every case behaves as declared:

| Case | Declared | Result |
| --- | --- | --- |
| `two_expected_one_hit` | must raise | raised |
| `single_expected_zero_hits` | must raise | raised |
| `undeclared_extra_red` | must raise | raised |
| `no_declaration_at_all` | must raise | raised |
| `exact_hits` | must pass | passed |
| `tolerated_red_may_fire` | must pass | passed |
| `tolerated_red_may_stay_green` | must pass | passed |

Because the gate asserts this table on every invocation, a validator that
stopped rejecting 2-expected/1-hit turns the formal gate RED. This was also
demonstrated locally by swapping in a lax validator (the R1-R3 behaviour): the
phase went RED on `two_expected_one_hit` and `undeclared_extra_red`. The V3
suite asserts the same semantics in
`test_formal_gate_declares_its_own_negative_cases_and_they_fail_closed`, plus
per-case tests for missing/extra/empty declarations and a static check that the
harness source uses the exact-set validator.

### 4. Identity and hygiene

Harness identity is R1-R4 (`TASK_ID`, `AUTHORIZATION_ID`). The preflight
requires the immediate R1-R3 predecessor **and** the frozen R1-R2 link to be
ancestors of HEAD (recorded as separate report fields), plus candidate ==
HEAD, a clean worktree, the authorization id in the commit message and 4/4
source digests matching the committed blobs. The run work dir holds
synthetic-credential manifests and is now removed at teardown
(`work_dir_disposition: removed`); under `--keep` it is deliberately retained
and reported. The 13 leftover `%TEMP%/mpango_v3_r1r1_*` directories from
earlier rounds were removed without touching any historical evidence.

## Machine results (from `harness_report.json`, verdict PASS)

| Gate | Result |
| --- | --- |
| Validator negative cases (before containers) | 7/7 behaved as declared |
| Identity preflight | candidate == HEAD, clean worktree, both predecessors ancestors, authorization id present, 4/4 source digests match blobs |
| Scenario suites (6 × full V3 suite) | all rc=0, 0 failed, 0 errors |
| Tool `--verify` | rc=0 (intact) / rc=2 (runtime-owned-guard counterexample) |
| Mutations (MM1, MM2, MM3, MM4, MM5a, MM5b, MM6, MM7, MM8) | 9/9 went RED; **9/9 exact-set OK** (0 missing, 0 undeclared); every mutated script parses; byte-identical restore after every run |
| Post-restore reproducibility | `v3_ok` GREEN (rc=0) |
| Synthetic-secret scan | 0 of 20 harness-generated evidence files contain the token |
| Regression (BASE vs candidate) | 104 / 104 per-node outcomes, deltas=0 (`88 passed, 5 xfailed, 11 errors` on both sides — the same pre-existing, environment-identical numbers as the frozen R1-R2/R1-R3 packs) |
| Teardown | both containers removed; work dir removed; no stray BASE worktree |

## Known limits (recorded, not hidden)

- **Tolerated REDs are explicit, not absent.** MM4 declares
  `test_partial_exists_first_deploy_refused_zero_writes` and MM6 declares the
  three zero-connection endpoint tests as tolerated; both fired in this run and
  are declared in `tolerated_red`, so the observed sets match the declarations
  exactly. Tolerance means "may fire" — the validator records
  `declared_but_not_red` for declared nodes that stayed green.
- The regression suite's 11 errors are pre-existing and identical on both sides
  of the comparison (unchanged from R1-R2 and R1-R3).
- The harness `--skip-*` flags exist and were used ONLY for the non-evidence
  pre-formal rehearsals; the formal invocation used the full gate set.
- **Normal-hook normalization of the evidence text.** The repository's normal
  `pre-commit` hooks (`trailing-whitespace`, `end-of-file-fixer`) normalized
  trailing whitespace / the end-of-file newline of the generated text evidence
  at commit time; no hook was bypassed and no evidence byte was hand-edited.
  `EVIDENCE_NORMALIZATION_AUDIT.txt` records every evidence file in BOTH digest
  forms (working-tree CRLF and stored blob LF), and the as-generated digest of
  the report captured before any git command was run, with the proof that the
  committed form differs from the generated form only by that one newline.

## Reproduce from zero

```
cd backend
<venv-python> scripts/v3_tenant_bootstrap_db_authority_harness.py \
    --evidence-dir <this directory> \
    --candidate-commit efe70792246bca48ee5277b33c4476313e6c14e8
```

The identity preflight refuses to start unless `HEAD` is exactly that commit
with a clean worktree; the validator phase refuses to start unless the
exact-set validator still fails closed on all seven synthetic cases.
