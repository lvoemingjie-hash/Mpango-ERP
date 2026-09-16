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
- SUCCESSOR_COMMIT=efe70792246bca48ee5277b33c4476313e6c14e8 (`fix(harness): MPANGO-TENANT-BOOTSTRAP-DB-AUTHORITY-R1-R4 …`, normal hooks, no --no-verify, no amend/rebase/force; reached through a6b22f83 → d6747819 → b89c3276 → efe70792, all normal successors)
- EVIDENCE_COMMIT=d3cc4570bcf5364db121404b6ce9a779fabb91e1 (append-only R1-R4 evidence pack; R1, R1-R1, R1-R2 and R1-R3 evidence untouched)
- SUCCESSOR_DIGESTS (bootstrap / grants / v3 suite / harness; working-tree CRLF vs committed-blob LF, grouped):
  - bootstrap wt=fc0db066 66b44f69 c96463cb 0fea076a 69f90f88 dc4c1885 c1d2abd3 524a4818
  - bootstrap blob=3301a55b a995359c 23da826c 566d821d 17307471 5fbb5c8c d3278e12 74aeff6d
  - grants wt=b2ee0eb4 320691c0 8256daf0 468dd521 361c834c f6e4abd0 b6f56d72 23630764
  - grants blob=25330f40 794f08a2 4213c82f d9fbd3a4 eafa4719 7ed866a4 5761613d 193f4861
  - v3_suite wt=cfee4f95 a14f5f14 91f47235 cd5bc1c1 34b43709 624cd6df 6d14d0cf d6012854
  - v3_suite blob=847d99a2 e736dbf2 1c583cac 3d272c3f 6fec4c83 c2f356b3 b96efd20 3b457e90
  - harness wt=b3580402 a19b9e9e 190e686d 0e1b69dc 062008a5 d161e3c8 5a8de9d7 9d351fce
  - harness blob=b3580402 a19b9e9e 190e686d 0e1b69dc 062008a5 d161e3c8 5a8de9d7 9d351fce
  - NOTE: the bootstrap and grants digests are byte-identical to R1-R3 — the product logic under test did not change in this round.
- EVIDENCE_DIGESTS (both forms):
  - harness_report.json wt=f18864e2 233100fb 4b314c97 3484d3b0 3a19ab18 9ac8df7b 30fc6311 625af845
  - harness_report.json blob=19be1839 9ec08c3f a46f1c64 2bf51cee 5d860e6a 68be0003 4024b021 f1e8de05
  - EVIDENCE_NORMALIZATION_AUDIT.txt wt=ea102579 937b20fb 524edb5d 4dcab16b 4196a7aa 402aec62 ca6add8a 88d392df
  - EVIDENCE_NORMALIZATION_AUDIT.txt blob=a6d86b8c 70cec83a 4b3a6a29 37fe3bae b30528e6 66b71ab2 e6f01ccc aed792ad
  - README.md wt=blob=176bde7b b4bf6f3d 62396bed 18b031f7 17ab6307 10f9c8ff f3b25e85 a7b3f26a
  - the other 20 harness-generated files: full as-generated + wt + blob table in EVIDENCE_NORMALIZATION_AUDIT.txt
- REPORT_AS_GENERATED_DIGEST=8baa38d4 3004dfc3 39b595e0 ddc4e23c 01258834 1d56bd4a b6cf975c 22d6bf64 (captured before any git command; the committed working-tree file equals it plus exactly one trailing newline — verified per file in the audit)
- FORMAL_INVOCATIONS=1 (full gate set, no --skip flags); PRE_FORMAL_REHEARSALS=3 (partial, scratch dirs outside the repository, non-evidence)
- HOOK_NORMALIZATION=no bypass; the normal `trailing-whitespace`/`end-of-file-fixer` hooks normalized the generated text evidence; the audit proves per file that the change is semantic-free
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
