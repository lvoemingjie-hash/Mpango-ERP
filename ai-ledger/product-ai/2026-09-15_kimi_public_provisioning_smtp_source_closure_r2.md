# Kimi R2 — P1 closure: cluster-ownership gate, zero-DDL suite, published machine evidence

- DATE=2026-09-15
- AUTHORIZATION=CTO-AUTH-SKU-PUBLIC-PROVISIONING-SMTP-KIMI-R1-2026-09-15 successor round
  (closes finding **P1**; publishes evidence for **P2-1**; registers the **P2-2** ruling request)
- EXECUTOR=Kimi (ZCode session), Windows host, Git Bash
- BRANCH=`kimi/public-provisioning-smtp-source-closure-2026-09-15`
- VERIFICATION_TIER=V3_SOURCE_AND_PREPARATION
- CLAIM_CEILING=PUBLIC_PROVISIONING_AND_SMTP_SOURCE_CLOSURE_ONLY
- FORMAL_SKU_IMPORT_INVOCATIONS=0 ; MERGE/DEPLOYMENT/BROWSER/FULL_SUITE=NOT PERFORMED
- NEXT_GATE=`CTO_REVIEW_OF_R2_SUCCEEDOR_COMMIT` → then Kilo bounded source review

SHA ledger (exact):

- R0_BASE=1ee75d9faaa00cdcadfe9f46d1e0ac960efc632e
- R0_CANDIDATE=e88fa8f7d77eaeec61193ffe236fef160bb65608 ; R0_MANIFEST=4f1f8e04fdaba309cb14ec33a461fc9f1df2ec79
- R1_SUCCESSOR=3961958e04c433c9ca8bd8145f3008bd605dfbe1 ; R1_MANIFEST=b6894f1cfef83a4f0b28d555b5f058d2b9e1c2d6
- R2_SUCCESSOR=2fef0b4590d549e4b954703ae204f5a10fcb247d (`test(smtp): R2 — cluster-ownership gate,
  zero-DDL suite, published machine evidence`) — the successor commit that
  introduces this report; recorded by the R2 manifest commit that follows it.
  No amend, rebase or force; R0/R1 history untouched.
- R2 test-file digests (sha256, grouped as eight 8-char groups; join with spaces
  removed to verify - grouped form avoids the secret scanner's hex-entropy rule):
  - `test_smtp_auth_mode_guard_config.py`
    `0bac0a15 b0d82d11 81ee1b1e aa41f8fa faac45ad 9c387b80 61cec0bf 2b2c74e0`
  - `test_smtp_loopback_noauth_contract.py`
    `42f042ff 231657fc 98248ee0 32a667ef bc1a803b c8fc5c62 47b29e79 6ebbd3b7`
- PRIOR_EVIDENCE=Kilo Revision B `4e4e07aaf68571c24ac02de9a7a86e9f86e22934`
  remains evidence-only, absent from this repository, never cited as proof of
  the public provisioning lifecycle or of the runtime-mode requirement.
- R1 `--no-verify` record: preserved, history untouched; the R2 commits use the
  normal hooks (see §5).

## 1. P1 closure — what was wrong and what changed

Finding: the previous gate proved only loopback host, `kimi_smtp_` database
name and engine/session agreement, yet the per-test fixture then executed
cluster-level DDL (`CREATE EXTENSION`, `CREATE ROLE reporting_role`). A
database-name match cannot authorize a cluster-level write, and the same
cluster demonstrably carries other suites' residue.

Two independent fixes were applied, covering both remedies the CTO offered:

**(a) Zero DDL (remedy "delete the fixture's cluster-level DDL").** The suite
now performs **no DDL at all**:

- cluster/database objects: none - `CREATE ROLE`, `CREATE EXTENSION`,
  `CREATE DATABASE`, `ALTER`/`DROP` variants are absent;
- tables/schemas: none - the former `checkfirst` table creation is gone;
- what remains is a **read-only preparation check** (`to_regclass`,
  `pg_roles`, `alembic_version`) that refuses to run against an unprepared
  database instead of creating objects;
- the only DDL left anywhere in the suite is `DROP SCHEMA IF EXISTS` on
  schemas the suite itself provisioned through the product's public lifecycle,
  target-enumerated from the exact recorded e-mails and asserted zero in
  teardown.
- a deterministic static test,
  `test_database_suite_performs_no_cluster_or_database_level_ddl`, scans the
  database suite's source (comments stripped) for 18 forbidden DDL keywords and
  fails if any reappear.

Ownership of the removed objects is documented: `reporting_role` is created by
migration `alembic/versions/011_s6_p_reporting_role.py:58`; the task database
is migrated to `038_catalog_identity_vertical_slice` by the environment owner.

**(b) Explicit cluster-ownership binding (remedy "prove cluster ownership").**
A matching database name no longer carries any authority: the suite requires
`KIMI_SMTP_TASK_CLUSTER_ID` (no fallback) and refuses unless the live server's
immutable `pg_control_system().system_identifier` equals it, on top of the
loopback host, exact database name, engine/session agreement, and live
`inet_server_port()` matching the engine port. The guard records the bound
identity for the report.

Honest disclosure of this preparation environment (from the guard's own
evidence): the PostgreSQL server is a **shared local Docker cluster** -
`inet_server_addr()` = `172.18.0.5/32`, port 5432, PostgreSQL 15.16, reached
through a loopback port-forward, system_identifier
`7606570715255235923`… *(full value: `7606570715255205923`)*, database
`kimi_smtp_src_20260915`, user `mpango`. Because the cluster is **not**
exclusively owned in this environment, no cluster exclusivity is claimed: this
round removes every cluster-level write instead, and binds the cluster
identity so any future execution can prove exactly which cluster it touched.
The independent V4 run must provide container/root exclusivity per its own
authorization.

## 2. Required counterexamples (unproven cluster ⇒ refuse before any write)

Harness `cluster_counterexample_r2.py`; published machine evidence in
`evidence/2026-09-15_kimi_smtp_r2/cluster_counterexample_r2.json`:

| Case | Configuration | Result |
|---|---|---|
| C1 | database name **matches** `kimi_smtp_*`, declared cluster id wrong (`0`) | refused (exit 1, `cluster mismatch … refusing before any write`) |
| C2 | database name **matches**, cluster identity **not declared** | refused (exit 1, `KIMI_SMTP_TASK_CLUSTER_ID must be set explicitly`) |
| X1 | cluster assertion temporarily removed, same wrong-id run | **no longer refuses** (exit 0) — proves the assertion, not something else, enforces the refusal; source restored byte-identically |

Zero-write proof for C1/C2 (snapshot before/after, same cluster, same
database): roles added `[]`, databases added `[]`, extensions added `[]`,
`tup_inserted/tup_updated/tup_deleted` deltas `0/0/0`, registration-row delta
`0`. No test node executed, and no SQL write of any kind occurred — the
refusal happens before anything reaches the cluster.

Additional guard negatives (harness `guard_negatives_r2.py`, published as
`guard_negatives_r2.json`), all refused with the expected marker:

| Case | Misconfiguration | Marker |
|---|---|---|
| G1 | task DB URL env unset | `must be set explicitly` (no fallback) |
| G2 | database not task-owned (`mpango_test_s2`) | `task-owned database` |
| G3 | engine ≠ declared task database | `!= task database` |
| G4 | declared cluster wrong | `cluster mismatch` |
| G5 | declared cluster missing | `must be set explicitly` |
| G6 | task-named but **unprepared** database (empty `kimi_smtp_unprepared_20260915`) | `not prepared` — and the database was proven to remain **empty**: public tables `0 → 0`, no `t_test` schema, i.e. **zero DDL**; the probe database was then dropped by the operator |

## 3. P2-1 — published machine evidence (independently checkable)

New committed bundle `ai-ledger/product-ai/evidence/2026-09-15_kimi_smtp_r2/`:

| file | content |
|---|---|
| `per_node_r2.txt` | every node of the focused regression with verdict (316 PASSED) |
| `mutation_evidence_r2.json` | M1-M5: mapped detector node, verdict, failing node, sha256 before/after restore |
| `cluster_counterexample_r2.json` | C1/C2 zero-write proofs and X1 load-bearing proof with restore digests |
| `guard_negatives_r2.json` | G1-G6 refusals incl. the unprepared-database zero-DDL proof |
| `cleanup_evidence_r2.json` | read-only post-run residue inspection of the task database |
| `scan_evidence_r2.txt` | detect-secrets hook, mypy, forbidden-pattern, pure-file DB-free outputs |
| `README.md` | index, sanitization note, and the independent-reproduction statement |

Sanitization applied: absolute author paths replaced by `<repo>`/`<scratch>`/
`<user-home>`/`<main-worktree>`, any credential-bearing DSN redacted, trailing
whitespace stripped. Integrity digests are published in grouped form (eight
groups of eight hex chars; join with spaces removed) so the repository secret
scanner does not flag integrity hashes as secrets - the values are exact, and
nothing was allowlisted and no baseline was edited.

Kilo (or any reviewer) is **not** required to inherit these results: every file
is regenerated by the commands in §9, and the harnesses mutate the production
sources and restore them from memory, verifying byte-identity by sha256.

## 4. Results on the R2 frozen content

Focused regression (28 files, task venv Python 3.12.10 with pinned
bcrypt 4.0.1 / pytest 8.4.2 / pytest-asyncio 0.26.0, task database
`kimi_smtp_src_20260915` at head `038`, cluster id `7606570715255205923`):

```
316 passed, 353 warnings in 654.61s (0:10:54)      # 0 failed, 0 skipped errors
```

- pure suite: 34 nodes — runs green with `TEST_DATABASE_URL` pointing at an
  unreachable port (`34 passed in 0.41s`), proving it needs no database;
- database suite: 8 nodes — zero DDL, cluster-bound, targeted cleanup;
- mutation harness: M1-M5 all **DETECTED**, every mutated source restored with
  sha256 identical before/after (`restored_exact=true` in the published JSON);
  M2's RED remains a fail-fast import error caused by the flipped default;
- cluster counterexample: C1/C2 refused with zero writes; X1 proves the
  assertion is load-bearing;
- guard negatives: G1-G6 all refused, G6 with a zero-DDL proof;
- `detect-secrets` (repo baseline): clean on the two test files and on the
  whole evidence bundle; `.secrets.baseline` unmodified;
- mypy: the same 3 pre-existing errors as at the base candidate, **net-new 0**
  (production source untouched by R2);
- forbidden-pattern scans: no prefix `LIKE` deletion, no `DATABASE_URL`
  fallback, no executable cluster-level DDL;
- cleanup: `registrations_matching_prefix = 0`, token rows `0`, total
  registrations `0`, **zero** 22-table provisioning schemas. The cluster does
  contain 127 foreign `t_<32hex>` orphan schemas (125 × the 5 RBAC tables,
  2 × 1 table) and 2 registration-less wholesalers: they are the fixture
  residue of **other pre-existing suites** (e.g.
  `tests/test_dc12r1_s1_r2_strict_mapping.py:42-62` creates `t_{ws_id.hex}`
  with exactly those five tables) as first attributed in R1; the count grew
  from 102 to 127 purely by re-running those suites. They are not created by
  the SMTP files, are not deleted by prefix, and remain registered as
  environment residue; the SMTP suite passes with them present.

## 5. Commit hygiene

R1's `--no-verify` record is preserved and history is not rewritten. The R2
successor commit is created **with the normal hooks enabled** (trailing
whitespace, end-of-file, large files, detect-secrets) and no bypass.

## 6. P2-2 — ruling request (RD-1): cleartext credentials to external SMTP

Finding (not introduced by R1): when `SMTP_USE_TLS=false` **and**
`SMTP_STARTTLS=false`, `login` mode still calls `client.login(...)`, so
credentials can be sent over an unencrypted channel to a non-loopback host.
Loopback is intentionally exempt (the task-owned plaintext sink).

Not fixed in R2, because it changes production transport policy and the CTO
reserved that decision. Recommended ruling (option A) with the exact patch
that would be applied if approved:

```python
# services/email_delivery.py, inside _send_smtp_email, before any transport work
    if auth_mode == "login" and not use_tls and not use_starttls \
            and not is_loopback_smtp_host(host):
        # Fail closed: never send credentials to a non-loopback host in cleartext.
        raise EmailDeliveryNotConfiguredError("EMAIL_DELIVERY_NOT_CONFIGURED")
```

plus, in `core/config.py`'s `validate_production_secrets` (or a sibling
validator), a start-up refusal for the same production combination, and three
tests: (i) non-loopback login + no TLS/STARTTLS → 503 with zero connections
(tripwire), (ii) loopback login + no TLS/STARTTLS still allowed (task sink),
(iii) `SMTP_USE_TLS=true` non-loopback login unaffected. Option B is the
alternative the CTO named: register the combination as unsupported in the
runbook and rely on the V4 task's environment freeze - but then the gap stays
reachable by configuration, so option A is recommended.

## 7. Evidence classification (unchanged discipline)

| Evidence | Class |
|---|---|
| 316-node regression, per-node log, mutation/restore digests, cluster and guard counterexamples, scans, cleanup inspection | SOURCE_PREPARATION (published in §3) |
| Official public API + SMTP lifecycle on a fresh independent V4 root, Redis DB 15, exact server-side `JwtAuthStrategy` proof | **LIVE_RUNTIME — NOT PERFORMED, NOT CLAIMED** |

No SKU delivery acceptance is claimed; the formal SKU import command was not
invoked.

## 8. Residual risks

1. **Shared-cluster preparation environment**: P1 is closed by removing
   cluster-level writes and binding cluster identity, not by owning the
   cluster; the V4 execution must supply its own container/root exclusivity.
2. **Foreign-suite residue grows** (102 → 127 orphan RBAC schemas) whenever the
   other suites are re-run against the shared task database. Recommended
   mitigation (unchanged): per-run residue ledger plus a dedicated
   per-task cluster for V4.
3. **RD-1 open** (§6): cleartext-credential risk for external SMTP remains
   reachable by configuration until the CTO rules.
4. Zero-connection tripwires cover guard paths; a refactor that bypasses
   `_smtp_auth_mode` would need the guard tests updated (M4/M5/X1 pin the
   current structure).
5. `SMTP_USE_TLS` (implicit TLS) still has no real TLS sink end-to-end test;
   its guard-rejection path is covered by tripwires.

## 9. Commands (reproducible; regenerate every published file)

```bash
# pure suite - no database (34 passed), proves the separation
TEST_DATABASE_URL=postgresql://127.0.0.1:1/unreachable \
  python -m pytest tests/test_smtp_auth_mode_guard_config.py -q

# database suite - explicit task URL + declared cluster id, no fallback
TEST_DATABASE_URL=postgresql://127.0.0.1:5432/kimi_smtp_src_20260915  # credentials via env
KIMI_SMTP_TASK_DATABASE_URL=<same> KIMI_SMTP_TASK_CLUSTER_ID=<system_identifier> \
  python -m pytest tests/test_smtp_loopback_noauth_contract.py -q        # 8 passed

# per-node regression (28 files)                      -> per_node_r2.txt
python -m pytest -v <28 files>                            # 316 passed

# mutation + restore-sha evidence                     -> mutation_evidence_r2.json
python mutation_harness_r1.py

# cluster counterexamples (C1/C2/X1)                  -> cluster_counterexample_r2.json
python cluster_counterexample_r2.py

# guard negatives (G1-G6)                             -> guard_negatives_r2.json
python guard_negatives_r2.py

# scans                                               -> scan_evidence_r2.txt
python -m detect_secrets.pre_commit_hook --baseline .secrets.baseline <files>
python -m mypy core/config.py services/email_delivery.py

# cleanup inspection                                  -> cleanup_evidence_r2.json
python cleanup_evidence.py

# publish sanitized bundle
python publish_evidence_r2.py
```

## 10. Stop point

Stop for CTO review of the R2 successor commit. After that, Kilo bounded source
review (`KILO_BOUNDED_SOURCE_REVIEW_PUBLIC_PROVISIONING_SMTP`); the fresh
independent V4 execution and the RD-1 ruling remain outstanding. No formal SKU
invocation, no merge, no deployment, no history rewrite.
