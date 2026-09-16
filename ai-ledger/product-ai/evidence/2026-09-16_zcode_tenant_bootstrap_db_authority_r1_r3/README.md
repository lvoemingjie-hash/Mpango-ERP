# MPANGO_TENANT_BOOTSTRAP_DB_AUTHORITY_R1_R3 — V3 Merge-Critical Evidence Pack

- **Authorization:** CTO-AUTH-TENANT-BOOTSTRAP-DB-AUTHORITY-R1-R3-2026-09-16
- **Executor:** Kimi (authorization EXECUTOR field); executed in a ZCode agent
  session on Windows 10.0.26200 x64
- **Implementation candidate commit:** `a21878c169d97e4c6fa837cd19dd9cced7de71e2`
  (branch `zcode/tenant-bootstrap-db-authority-r1-r3-2026-09-16`, created from
  the R1-R2 manifest commit `27dd16b814e0670a835cfba18a717d8ff133246c`)
- **Immediate R1-R2 predecessor:** `8951112bf126d70643dc64882c8bbee911321928`
  (ancestry enforced by the harness identity preflight)
- **Historical regression comparison base:** `0a16ed707ad898e9924c26b28097148708677af9`
  (R1 manifest commit; retained so the bootstrap-heavy comparison chain stays
  comparable across rounds)
- **Verification tier:** V3_MERGE_CRITICAL_DATA_INTEGRITY_SECURITY
- **Claim ceiling:** AUTHOR_IMPLEMENTATION_AND_TASK_OWNED_V3_EVIDENCE_ONLY
- **Machine:** Docker 29.1.3, TWO fresh `postgres:16.15` clusters per run
  (server_version_num `160015`; system identifiers
  `7686041494365143085` / `7686041508179918888` — recorded in
  `harness_report.json`)
- **Formal invocations of the full gate set:** 1 (no skips). One pre-formal
  rehearsal (`--skip-mutations --skip-regression`, scratch directory OUTSIDE
  the repository, non-evidence) was run to de-risk the containers path; it
  produced no artifact in this pack.
- **R1-R2 evidence:** untouched — this pack is new and additive. No existing
  R1, R1-R1 or R1-R2 commit, journal or evidence file was edited or relabelled.

## Required fixes → implementation map

1. **Zero-connection endpoint refusal (REQUIRED FIX 1).**
   `_assert_cluster_binding` Layer 1 validates all three URL endpoint
   bindings, the configured database paths and the expected role usernames,
   then raises `ClusterBindingError` **immediately** on any violation —
   before `asyncpg` is even imported and before ANY connection attempt, the
   admin URL included. Previously the mismatch was recorded but
   `_probe(self.admin_url)` still ran first. Diagnostics remain
   credential-free and are now rendered by one shared
   `_binding_refusal_message` helper, so the early and late refusal paths emit
   identical, credential-free text (host:port and role names only; no
   password, DSN, netloc or `@`). No valid live-binding, first-deployment,
   partial-state or credential-probe check was weakened: the deferral matrix
   and the credential probe are byte-identical to R1-R2.

2. **Executable semantic zero-connection tests (REQUIRED TEST 1).**
   Seven new tests, none of which need a manifest or a live cluster, so they
   run in every invocation of the suite:
   - `test_layer1_admin_endpoint_mismatch_refused_zero_connections`
   - `test_layer1_migrate_endpoint_mismatch_refused_zero_connections`
   - `test_layer1_app_endpoint_mismatch_refused_zero_connections`
   - `test_layer1_database_path_mismatch_refused_zero_connections`
   - `test_layer1_migrate_username_mismatch_refused_zero_connections`
   - `test_layer1_app_username_mismatch_refused_zero_connections`
   - `test_static_layer1_early_refusal_is_unconditional_and_precedes_connection`

   Each behavioral test drives `Provisioner._assert_cluster_binding` through
   an **intercepting `asyncpg.connect` spy** which records every attempt and
   refuses to connect, and proves: the method was invoked exactly once (an
   invocation recorder wraps it, so a vacuous pass is impossible), ZERO
   connections were attempted, the Layer-1 fragment is present in the
   refusal, and no password/DSN/`@` leaks into the diagnostic. The spy is
   semantic, not textual: under mutation MM8 the spy intercepts the real
   connection attempt and the tests fail with
   `connect spy intercepted asyncpg.connect under a Layer-1 binding violation`
   (see `pytest_mutation_MM8.txt`).

   The real two-PG-cluster zero-write counterexamples are **retained** and
   unmodified: `test_cluster_binding_mismatch_zero_writes` (admin on the
   second cluster) and `test_first_deploy_cross_cluster_refused_zero_writes`
   (true first deployment, admin cluster A / migrate+app cluster B). They now
   refuse before the first connection as well, and both still prove zero
   additions on BOTH clusters.

3. **Formal evidence identity (REQUIRED FIX 2).**
   The harness and the report it generates no longer identify as R1-R1. Four
   identity facts are recorded **separately**: task authorization id, the
   exact implementation candidate commit (declared per invocation via the new
   required `--candidate-commit` flag), the immediate R1-R2 predecessor, and
   the historical regression comparison base. A new **fail-closed identity
   preflight runs before container creation** and refuses unless:
   declared candidate == checked-out HEAD; the worktree is clean; the R1-R2
   predecessor is an ancestor of HEAD; the candidate commit message carries
   the R1-R3 authorization id; and all four source files' working-tree bytes
   match their committed blobs (LF-normalized, with both digest forms
   recorded). `_write_report` additionally refuses to publish a report whose
   identity does not match R1-R3. Stale R1-R1 / single-role comments were
   corrected in the harness (docstring, phase list, work-dir prefix, container
   prefix), the grants script (R1-R2 + R1-R3 hardening sections, Layer-1
   contract) and the bootstrap script (catalog-derived authority, single-role
   refusal, no connected-role fallback). Both failure modes of the preflight
   were observed refusing before any container: candidate != HEAD, and
   correct HEAD with a dirty worktree.

4. **MM8 — new named mutation (REQUIRED TEST 1's mutation).**
   MM8 bypasses the early Layer-1 refusal (`if False:` in place of
   `if problems:`). All **7/7** declared named REDs fire — the six spy tests
   plus the unconditional-guard static sentinel — proving the zero-connection
   tests are load-bearing rather than decorative. MM1–MM7 are retained; all
   eight mutations run isolated, and after them both scripts are proven
   byte-identical (bootstrap `fc0db066…`, grants `b2ee0eb4…`) with a green
   post-restore `v3_ok` run.

## Machine results (from `harness_report.json`, verdict PASS)

| Gate | Result |
| --- | --- |
| Identity preflight (before containers) | candidate == HEAD, worktree clean, predecessor ancestor, authorization id present, 4/4 source digests match blobs |
| Scenario suites (6 × full V3 suite) | all rc=0, 0 failed, 0 errors (`v3_ok`, `v3_nofunc`, `v3_badsig`, `v3_wrongown`, `v3_nopriv`, `v3_verify_wrongown`) |
| Tool `--verify` | rc=0 on the intact database; rc=2 on the runtime-owned-guard counterexample |
| Mutations MM1–MM8 | each went RED on its named semantic assertions; byte-identical restore after every run |
| MM8 named REDs | 7/7 (six spy tests + the unconditional-guard static) |
| Post-restore reproducibility | `v3_ok` GREEN (rc=0) |
| Synthetic-secret scan | 0 of 19 harness-generated evidence files contain the token |
| Regression (BASE vs candidate) | 104 / 104 per-node outcomes, deltas=0 |
| Teardown | both containers removed; no `mpango-v3auth3*` container left behind |

Regression detail: `88 passed, 5 xfailed, 11 errors` on BOTH sides in an
identical two-role topology — the same numbers the frozen R1-R2 pack recorded,
so the 11 errors are pre-existing, environment-identical failures of that
7-file bootstrap-heavy suite, not a delta introduced by this candidate. The
gate is per-node identity, which holds exactly (deltas=0).

## Known limits (recorded, not hidden)

- **MM5 declares two named REDs and fires one.** Under MM5
  (`deferral_allowed = True` with `if False:` in place of `if database_exists:`)
  the surviving `elif migrate_role_exists != app_role_exists:` branch still
  refuses the partial-role state, so
  `test_partial_exists_first_deploy_refused_zero_writes` stays GREEN while
  `test_wrong_password_provision_refused_zero_writes` goes RED. This is
  **identical to the frozen R1-R2 result** (1/2 there as well, confirmed by
  reading the R1-R2 `harness_report.json`); it is reported here rather than
  silently normalized, and the harness gate requires a non-empty named-RED hit
  set per mutation.
- The regression suite's 11 errors are pre-existing and identical on both
  sides of the comparison (see above).
- The harness `--skip-*` flags exist and were used ONLY for the non-evidence
  pre-formal rehearsal; the formal invocation used the full gate set.
- **Normal-hook normalization of the evidence text.** The repository's
  `pre-commit` hooks (`trailing-whitespace`, `end-of-file-fixer`) normalized
  trailing whitespace / the end-of-file newline of the harness-generated text
  evidence when it was committed. No hook was bypassed and no evidence byte
  was hand-edited. `EVIDENCE_NORMALIZATION_AUDIT.txt` records every evidence
  file in BOTH digest forms (working-tree CRLF and stored blob LF) and proves
  the change is semantic-free: the report's working-tree bytes differ from the
  as-generated bytes by exactly one end-of-file newline (removing that single
  byte reproduces the recorded as-generated digest `2a6a7344e5e202a8…`), the
  stored blob is the working-tree bytes with CRLF→LF, the report is identical
  after JSON parsing, and 28/28 cross-consistency checks between the committed
  report and the committed logs pass (suite rcs, every mutation's FAILED
  nodeids and named REDs, verify rcs, and the mutation-restore script digests
  matching the candidate blobs). The post-normalization report was
  re-validated: identity R1-R3, verdict PASS, MM8 7/7, secret scan 0, committed
  report sha256 wt `c6be35f2938f14dd…` / blob `4fd59613dad6793d…`.

## Reproduce from zero

```
cd backend
<venv-python> scripts/v3_tenant_bootstrap_db_authority_harness.py \
    --evidence-dir <this directory> \
    --candidate-commit a21878c169d97e4c6fa837cd19dd9cced7de71e2
```

The identity preflight will refuse to start unless `HEAD` is exactly that
commit with a clean worktree.
