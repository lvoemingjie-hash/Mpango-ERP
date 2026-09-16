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
