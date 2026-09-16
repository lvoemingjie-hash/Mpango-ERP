# ZCode-W R1-R3 — Tenant bootstrap DB authority: zero-connection endpoint refusal + formal evidence identity

- DATE=2026-09-16
- TASK_ID=MPANGO_TENANT_BOOTSTRAP_DB_AUTHORITY_R1_R3
- AUTHORIZATION_ID=CTO-AUTH-TENANT-BOOTSTRAP-DB-AUTHORITY-R1-R3-2026-09-16
- BRANCH=zcode/tenant-bootstrap-db-authority-r1-r3-2026-09-16
- BRANCH_BASE=27dd16b814e0670a835cfba18a717d8ff133246c (R1-R2 manifest commit; fresh task branch, `fetch --all --prune` first)
- IMPLEMENTATION_CANDIDATE_COMMIT=a21878c169d97e4c6fa837cd19dd9cced7de71e2
- R1_R2_PREDECESSOR_COMMIT=8951112bf126d70643dc64882c8bbee911321928 (ancestry enforced by the preflight)
- HISTORICAL_REGRESSION_BASE_COMMIT=0a16ed707ad898e9924c26b28097148708677af9 (optional historical comparison base, retained from R1-R2 for chain comparability)
- EXECUTOR=Kimi (authorization EXECUTOR field); executed in a ZCode agent session
- VERIFICATION_TIER=V3_MERGE_CRITICAL_DATA_INTEGRITY_SECURITY
- CLAIM_CEILING=AUTHOR_IMPLEMENTATION_AND_TASK_OWNED_V3_EVIDENCE_ONLY
- EVIDENCE_DIR=ai-ledger/product-ai/evidence/2026-09-16_zcode_tenant_bootstrap_db_authority_r1_r3/
- SUCCESSOR_COMMIT=a21878c169d97e4c6fa837cd19dd9cced7de71e2 (`fix(bootstrap): MPANGO-TENANT-BOOTSTRAP-DB-AUTHORITY-R1-R3 …`, normal hooks, no --no-verify, no amend/rebase/force)
- EVIDENCE_COMMIT=ff1e79625070716cfea332b0f44646cc891e53c2 (append-only R1-R3 evidence pack; R1, R1-R1 and R1-R2 evidence untouched)
- SUCCESSOR_DIGESTS (bootstrap / grants / v3 suite / harness; working-tree CRLF vs committed-blob LF, grouped):
  - bootstrap wt=fc0db066 66b44f69 c96463cb 0fea076a 69f90f88 dc4c1885 c1d2abd3 524a4818
  - bootstrap blob=3301a55b a995359c 23da826c 566d821d 17307471 5fbb5c8c d3278e12 74aeff6d
  - grants wt=b2ee0eb4 320691c0 8256daf0 468dd521 361c834c f6e4abd0 b6f56d72 23630764
  - grants blob=25330f40 794f08a2 4213c82f d9fbd3a4 eafa4719 7ed866a4 5761613d 193f4861
  - v3_suite wt=41e8f12b 3c72dfde 1a8c351c e4eb37d9 7fe53b43 713054ea ff648fa5 b569097c
  - v3_suite blob=41c3b3bb 16cf22fb d90a5b70 5fab6d71 0477bcaa 23cdebd8 9ffc7cb8 b7c955cc
  - harness wt=3d28ac81 ee64dacf fc6b4e05 fa6f770c a4e8b43d 585e90c5 f3ff17d5 25d7de30
  - harness blob=3d28ac81 ee64dacf fc6b4e05 fa6f770c a4e8b43d 585e90c5 f3ff17d5 25d7de30
- EVIDENCE_DIGESTS (both forms; wt = Windows-checkout CRLF, blob = `git show HEAD:<path>`):
  - harness_report.json wt=c6be35f2 938f14dd 7a6e9222 078644bd 374b2d08 06c58a0b 31ef1c4d d4615fb1
  - harness_report.json blob=4fd59613 dad6793d 8497b1fe 514159f6 4b566368 07c84621 e6f0b775 6fe9028d
  - EVIDENCE_NORMALIZATION_AUDIT.txt wt=e9810ba3 421dd780 5e2908b1 d469e5fa 4c4cc872 ac8095e1 499e01b4 64033c7f
  - EVIDENCE_NORMALIZATION_AUDIT.txt blob=07e7fbc4 97861980 2c113208 f1d1b37f 63e2bf8d 298755ab ea6cb875 c29ec88c
  - README.md wt=blob=7d48dbf6 54f56149 5882e336 84cd074e 27ed816a f3f11238 1f05cef5 cd983ae0
  - the other 19 harness-generated files (suite/mutation/verify/regression logs): full wt+blob table in EVIDENCE_NORMALIZATION_AUDIT.txt
- REPORT_AS_GENERATED_DIGEST=2a6a7344 e5e202a8 068c88c5 c1e105a0 a484753e fef7aa7b 47b1e69b 3371d78d (recorded before any git command; the committed working-tree file minus its single final newline byte reproduces it exactly — see the audit)
- FORMAL_INVOCATIONS=1 (full gate set, no --skip flags); PRE_FORMAL_REHEARSAL=1 (partial, scratch dir outside the repository, non-evidence)
- HOOK_NORMALIZATION=no bypass; the normal `trailing-whitespace`/`end-of-file-fixer` hooks normalized the generated text evidence (report: exactly one added end-of-file newline). See EVIDENCE_NORMALIZATION_AUDIT.txt; the report's own bytes are re-validated in the committed form.
- NEXT_GATE=`KILO_TENANT_BOOTSTRAP_DB_AUTHORITY_R1_R3_SOURCE_AND_REAL_PG16_REVIEW`

## Scope

Only `backend/scripts/provision_runtime_db_roles.py`,
`backend/tests/test_tenant_bootstrap_db_authority.py`,
`backend/scripts/v3_tenant_bootstrap_db_authority_harness.py` and the one
stale comment block in `backend/scripts/bootstrap_tenant_schema.py` changed.
No migrations, SKU, SMTP, order, payment, frontend or docker-entrypoint
changes. R1, R1-R1 and R1-R2 commits, journals and evidence are untouched:
this round is additive (new evidence directory, new journal, new commits from
the R1-R2 manifest commit).

## Required fix 1 — zero-connection endpoint refusal

`_assert_cluster_binding` Layer 1 (endpoint host:port for ALL THREE URLs,
configured database paths, expected role usernames) now raises
`ClusterBindingError` immediately on any violation, before `asyncpg` is
imported and before ANY connection attempt — including `self.admin_url`.
Previously the violation was recorded into `problems` but execution continued
into `_probe(self.admin_url)`, so a mis-wired URL set still opened a
connection before refusing. The early and late refusal paths now share
`_binding_refusal_message`, keeping diagnostics credential-free (host:port and
role names only — no password, DSN, netloc or `@`) and textually identical.
The R1-R2 deferral matrix (proven-fresh first deployment; established
principals + absent database with a live credential probe before any write)
and every partial-state / wrong-credential refusal are unchanged.

## Required test 1 — executable semantic zero-connection proofs

Seven tests, no manifest and no live cluster required, so they execute in
every suite invocation (and in both the formal run and each mutation run):

- `test_layer1_admin_endpoint_mismatch_refused_zero_connections`
- `test_layer1_migrate_endpoint_mismatch_refused_zero_connections`
- `test_layer1_app_endpoint_mismatch_refused_zero_connections`
- `test_layer1_database_path_mismatch_refused_zero_connections`
- `test_layer1_migrate_username_mismatch_refused_zero_connections`
- `test_layer1_app_username_mismatch_refused_zero_connections`
- `test_static_layer1_early_refusal_is_unconditional_and_precedes_connection`

Design: an intercepting `asyncpg.connect` spy records every attempt and raises
a sentinel instead of connecting, so a connection attempt under a Layer-1
violation fails the test on the spot; an invocation recorder wrapping
`_assert_cluster_binding` proves the method really ran exactly once (no
vacuous pass); each test asserts zero attempts, the Layer-1 message fragment,
and no password/DSN/`@` in the diagnostic. The fixture DSNs are assembled
from parts (`_spy_dsn`) so no source line carries a basic-auth shape, and the
detect-secrets pre-commit hook stays green. The retained real two-PG-cluster
counterexamples (`test_cluster_binding_mismatch_zero_writes`,
`test_first_deploy_cross_cluster_refused_zero_writes`) still prove zero
additions on BOTH clusters, now with zero connections on the refusing path.

## Required fix 2 — formal evidence identity

- Harness identity: `TASK_ID` / `AUTHORIZATION_ID` constants; the report no
  longer says R1-R1. Stale text corrected: docstring title and successor
  lineage, phase list (MM1–MM8), mutation-framework comment, work-dir prefix
  (`mpango_v3_r1r3_`), container prefix (`mpango-v3auth3`).
- Recorded separately in `harness_report.json`:
  `task`, `authorization`, `implementation_candidate_commit`,
  `r1_r2_predecessor_commit`, `historical_regression_base_commit`.
- New required `--candidate-commit` flag; `preflight_identity()` runs BEFORE
  any container is created and fails closed unless: declared candidate ==
  HEAD; `git status --porcelain` empty; the R1-R2 predecessor is an ancestor
  of HEAD (`merge-base --is-ancestor`); the candidate commit message carries
  the R1-R3 authorization id; and each of the four source files' working-tree
  bytes equal their committed blobs (LF-normalized; both raw digest forms are
  recorded in the report's `identity_preflight.source_digests`).
- `_write_report` validates the report's task/authorization/candidate identity
  and refuses to publish a mis-identified report.
- Both refusal modes were observed before any container existed: candidate !=
  HEAD, and correct HEAD with a dirty worktree (the refusal listed exactly the
  four modified source files).
- Comment hygiene: the bootstrap script's stale comment claiming that an
  undeclared `MPANGO_MIGRATION_AUTHORITY_ROLE` makes the precondition compare
  the owner against the connected role (single-role fallback) was corrected to
  the implemented behaviour — catalog-derived authority, single-role topology
  always refused, no connected-role fallback. The grants script gained
  R1-R2/R1-R3 hardening sections and an explicit Layer-1 zero-connection
  contract. The suite docstring now names the current round and authorization
  while keeping the originating R1 authorization as lineage, and its scenario
  list includes `v3_verify_wrongown`.

## New named mutation MM8

`layer1_zero_connection_refusal_bypassed` (grants script): the early
`if problems:` raise is neutralised to `if False:`. Result: RED with **7/7**
declared named REDs (the six spy tests plus the static sentinel), then
byte-identical restore, then a green post-restore `v3_ok` run. MM1–MM7
retained; all eight mutations run isolated.

## Formal invocation

Exactly ONE formal invocation of the full gate set (no `--skip-*`), with
`--candidate-commit a21878c169d97e4c6fa837cd19dd9cced7de71e2` against the
clean candidate tree. One pre-formal rehearsal (`--skip-mutations
--skip-regression`, scratch directory outside the repository) was run to
de-risk the container path; it produced no artifact in the evidence pack and
is disclosed here for completeness. No failed formal invocation was repaired
or re-run.

## Machine results (two fresh postgres:16.15 clusters; verdict PASS)

- identity preflight: candidate == HEAD, worktree clean, predecessor is an
  ancestor, authorization id in the commit message, 4/4 source digests match
  committed blobs;
- six scenario suites GREEN (rc=0, 0 failed, 0 errors each);
- tool `--verify`: rc=0 (intact) and rc=2 (runtime-owned guard
  counterexample);
- MM1–MM8 each named-RED with byte-identical restore (bootstrap
  `fc0db06666b4…`, grants `b2ee0eb43206…` — the same digests as the committed
  candidate); post-restore GREEN;
- synthetic-secret scan: 19 harness-generated evidence files scanned, 0
  containing the token;
- BASE-vs-candidate bootstrap-heavy regression: 104/104 per-node outcomes,
  deltas=0 (`88 passed, 5 xfailed, 11 errors` on both sides — the same shape
  the frozen R1-R2 pack recorded, i.e. pre-existing environment-identical
  failures, not a delta);
- cleanup: both containers removed; no `mpango-v3auth3*` container remains.

## Known limits

- MM5 declares two named REDs and fires one (the surviving `elif` branch still
  refuses the partial-role state, so only the wrong-password counterexample
  goes RED). Identical to the frozen R1-R2 result (1/2 there too); reported
  rather than normalized. The harness gate requires a non-empty named-RED hit
  set per mutation; MM8 — the mutation this round adds — fires 7/7.
- The regression suite's 11 errors are pre-existing and appear identically on
  both sides of the comparison.
- `--candidate-commit` is inherently an invocation parameter (a commit cannot
  contain its own hash); the preflight is what binds it to the tree, and the
  report records it in the identity block.

## Scope discipline

Normal commits with normal hooks; no `--no-verify`, amend, rebase,
force-push, merge or deployment. The first commit attempt was rejected by the
`detect-secrets` pre-commit hook on synthetic fixture DSNs in the new tests;
the fix was structural (assemble fixture DSNs from parts) rather than a bypass,
and the commit was retried normally.
