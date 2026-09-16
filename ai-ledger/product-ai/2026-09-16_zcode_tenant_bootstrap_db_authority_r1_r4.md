# ZCode-W R1-R4 — Tenant bootstrap DB authority: exact named-RED verification, MM5 split, validator negative controls

- DATE=2026-09-16
- TASK_ID=MPANGO_TENANT_BOOTSTRAP_DB_AUTHORITY_R1_R4
- AUTHORIZATION_ID=CTO-AUTH-TENANT-BOOTSTRAP-DB-AUTHORITY-R1-R4-2026-09-16
- BRANCH=zcode/tenant-bootstrap-db-authority-r1-r4-2026-09-16
- BRANCH_BASE=69e2d5b69df61a06a7790aadf7813ee214bc3249 (R1-R3 manifest tip; fresh task branch)
- IMPLEMENTATION_CANDIDATE_COMMIT=efe70792246bca48ee5277b33c4476313e6c14e8
- R1_R3_PREDECESSOR_COMMIT=a21878c169d97e4c6fa837cd19dd9cced7de71e2 (ancestry enforced by the preflight)
- R1_R2_PREDECESSOR_COMMIT=8951112bf126d70643dc64882c8bbee911321928 (frozen chain link, ancestry enforced)
- HISTORICAL_REGRESSION_BASE_COMMIT=0a16ed707ad898e9924c26b28097148708677af9 (optional historical comparison base, retained for chain comparability)
- EXECUTOR=Kimi (authorization EXECUTOR field); executed in a ZCode agent session
- VERIFICATION_TIER=V3_MERGE_CRITICAL_DATA_INTEGRITY_SECURITY
- CLAIM_CEILING=AUTHOR_IMPLEMENTATION_AND_TASK_OWNED_V3_EVIDENCE_ONLY
- EVIDENCE_DIR=ai-ledger/product-ai/evidence/2026-09-16_zcode_tenant_bootstrap_db_authority_r1_r4/
- NEXT_GATE=`KILO_TENANT_BOOTSTRAP_DB_AUTHORITY_R1_R4_SOURCE_AND_REAL_PG16_REVIEW`

## Trigger: Kimi R1-R3 review — NEED CHANGES (P1 control plane, no product RED)

Kimi accepted the product-side fixes (zero-connection endpoint refusal, the
connect-spy tests, identity binding, candidate chain) but rejected the round
because the harness declared two named REDs for MM5 while only one fired, and
the gate only required a non-empty hit set. The conclusion "all of MM1-MM8 is
semantically falsified" therefore did not follow. R1-R4 is the requested
narrow repair, scoped to the verification control plane: **no product-source
change**, and the provisioning/refusal logic under test is byte-identical to
the reviewed R1-R3 candidate (proved by the report's pre-run and restored
script digests).

## Required fix 1 — MM5 split into two single-target mutations

- MM5a `existing_database_refusal_deleted` (target-database-already-exists
  refusal deleted) → required named RED
  `test_wrong_password_provision_refused_zero_writes`, observed exactly that
  one node.
- MM5b `partial_role_set_refusal_deleted` (partial-role-set refusal deleted) →
  required named RED
  `test_partial_exists_first_deploy_refused_zero_writes`, observed exactly that
  one node.

Both are genuine semantic deletions: the refused state falls through to the
credential probe (a different guard), so the refusal reason changes and the
counterexample's specific `is not fresh` / `already exists` assertions fire.

## Required fix 2 — exact named-RED set verification

Every mutation declares a required `named_red` set plus an explicit
`tolerated_red` set. The declared universe is required ∪ tolerated;
`mutation_red_set_verdict()` / `assert_mutation_red_set_exact()` fail closed on
a missing required RED, an extra/undeclared RED, an empty declaration, or a
mutation that produced no RED at all. The formal gate calls the validator for
every mutation (the old non-empty check is removed and a static test asserts
its absence) and publishes the verdicts in
`phases.mutation_red_set_verdicts`. Formal result: 9/9 mutations
`exact_set_ok = true`, 0 missing, 0 undeclared.

## Required fix 3 — negative controls for the validator itself

The harness runs a synthetic case table (`two_expected_one_hit,
single_expected_zero_hits, undeclared_extra_red, no_declaration_at_all,
exact_hits, tolerated_red_may_fire, tolerated_red_may_stay_green`) before any
container starts and asserts every case behaves as declared, so a validator
that stopped failing closed on the 2-expected/1-hit case turns the FORMAL gate
RED. I also demonstrated it locally by swapping in a lax validator: the phase
went RED on `two_expected_one_hit` and `undeclared_extra_red`. The V3 suite
carries the same semantics as tests plus static checks.

## Defect found and closed by the new validator (R1-R3 inheritance)

The exact-set validator immediately exposed a second inherited defect: MM2's
replacement had a stray third double-quote in the owner-fallback's
empty-string default argument, so the mutated `bootstrap_tenant_schema.py` did
not parse. MM2's "RED" therefore included an import-failure cascade — six
import-error nodes R1-R2/R1-R3 never declared, accepted by the old non-empty
gate. Fixes: the replacement is repaired (valid Python, mutation genuinely
semantic; observed set is now exactly its two required nodes), and
`assert_mutation_is_semantic()` ast-parses every mutated script BEFORE its
suite runs, failing closed on a broken tree. A rehearsal of the broken form
was the evidence: the validator refused it and the repaired form then matched
its declaration exactly.

## Hygiene

- The run work dir holds synthetic-credential manifests; it is now removed at
  teardown (`work_dir_disposition: removed`) and retained only under `--keep`,
  where its path is reported (isolated, never silently left behind).
- The 13 leftover `%TEMP%/mpango_v3_r1r1_*` directories from the earlier rounds
  were removed. No historical evidence, commit or journal was rewritten.
- 20 of 20 harness-generated evidence files scanned for the synthetic token:
  0 hits.

## Formal invocation

Exactly ONE formal invocation of the full gate set (no `--skip` flags) with
`--candidate-commit efe70792246bca48ee5277b33c4476313e6c14e8`, against the
clean candidate tree. Three pre-formal rehearsals (`--skip-regression`,
scratch directories outside the repository, non-evidence) were used to derive
and confirm the mutation declarations; they produced no artifact in the
evidence pack. No failed formal invocation was repaired or re-run.

## Machine results (two fresh postgres:16.15 clusters; verdict PASS)

- validator negative cases: 7/7 behaved as declared (four must raise, three
  must pass);
- identity preflight: candidate == HEAD, worktree clean, R1-R3 AND R1-R2
  predecessors are ancestors, authorization id in the commit message, 4/4
  source digests match committed blobs;
- six scenario suites GREEN (rc=0, 0 failed, 0 errors each);
- tool `--verify`: rc=0 (intact) and rc=2 (runtime-owned-guard
  counterexample);
- nine mutations (MM1, MM2, MM3, MM4, MM5a, MM5b, MM6, MM7, MM8): all went RED,
  all exact-set OK, all mutated scripts parseable, byte-identical restore
  (bootstrap `fc0db06666b4…`, grants `b2ee0eb43206…` — the committed candidate
  bytes); post-restore GREEN;
- synthetic-secret scan: 20 harness-generated files scanned, 0 containing the
  token;
- BASE-vs-candidate bootstrap-heavy regression: 104/104 per-node outcomes,
  deltas=0 (`88 passed, 5 xfailed, 11 errors` on both sides — pre-existing and
  identical, unchanged from R1-R2/R1-R3);
- cleanup: both containers removed, no stray BASE worktree, work dir removed,
  no `mpango-v3auth3*` container left.

## Known limits

- Tolerated declarations are explicit: MM4 tolerates
  `test_partial_exists_first_deploy_refused_zero_writes` and MM6 tolerates the
  three zero-connection endpoint tests; both fired and are declared, so the
  observed sets match the declarations exactly. `declared_but_not_red` records
  any tolerated node that stayed green.
- The regression suite's 11 errors are pre-existing and identical on both
  sides.
- `--candidate-commit` remains an invocation parameter (a commit cannot contain
  its own hash); the preflight is what binds it to the tree, and the report
  records it plus both predecessors separately.
- The normal pre-commit hooks normalized trailing whitespace / the end-of-file
  newline of the generated text evidence; see
  EVIDENCE_NORMALIZATION_AUDIT.txt, which records both digest forms and the
  as-generated report digest captured before any git command ran.

## Scope discipline

Normal commits with normal hooks; no `--no-verify`, amend, rebase,
force-push, merge or deployment. Scope: the harness and the V3 suite only. The
one product-adjacent artefact touched is the MM2 mutation TEXT inside the
harness (a test instrument), not any product source.
