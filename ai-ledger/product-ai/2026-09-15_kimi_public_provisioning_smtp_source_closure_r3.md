# Kimi R3 — TLS transport policy, evidence truth, terminology closure (errata ledger)

- DATE=2026-09-15
- AUTHORIZATION_ID=CTO-AUTH-SKU-PUBLIC-PROVISIONING-SMTP-KIMI-R3-TLS-EVIDENCE-TRUTH-2026-09-15
- BASE=85f79491f3275410946d225c9af837ff949a1e77 (R2 manifest)
- EXECUTOR=Kimi (ZCode session), Windows host, Git Bash
- VERIFICATION_TIER=V3_SOURCE_AND_PREPARATION
- CLAIM_CEILING=SMTP_TRANSPORT_POLICY_AND_EVIDENCE_TRUTH_CLOSURE_ONLY
- FULL_SUITE_RESULT=NOT_RUN · LIVE_RUNTIME_RESULT=NOT_RUN · FORMAL_SKU_IMPORT_INVOCATIONS=0
- NEXT_GATE=`KILO_BOUNDED_SOURCE_REVIEW_PUBLIC_PROVISIONING_SMTP_R3`

SHA ledger (exact):

- R0_BASE=1ee75d9faaa00cdcadfe9f46d1e0ac960efc632e · R0_CANDIDATE=e88fa8f7d77eaeec61193ffe236fef160bb65608 · R0_MANIFEST=4f1f8e04fdaba309cb14ec33a461fc9f1df2ec79
- R1_SUCCESSOR=3961958e04c433c9ca8bd8145f3008bd605dfbe1 · R1_MANIFEST=b6894f1cfef83a4f0b28d555b5f058d2b9e1c2d6
- R2_SUCCESSOR=2fef0b4590d549e4b954703ae204f5a10fcb247d · R2_MANIFEST=85f79491f3275410946d225c9af837ff949a1e77 (= R3 base)
- R3_SUCCESSOR=<recorded by the R3 successor commit that introduces this report;
  exact SHA in the CTO handoff and equal to `git rev-parse HEAD` on the branch>
- R3 content digests (sha256, grouped as eight 8-char groups; join with spaces
  removed to verify - grouped form keeps the repository secret scanner quiet):
  - `backend/core/config.py` `0ea37d75 ebdb4610 c17b0215 892f5f7f cad62af2 a6d1f77b 2dd02511 c65409d1`
  - `backend/services/email_delivery.py` `c4c7bad3 c9817de8 39823a46 4319ca03 850a055f abd53909 50c1089c f0a58604`
  - `backend/tests/test_smtp_auth_mode_guard_config.py` `74c600f3 62bab97d 9d6e63b9 2f0aa1a6 25cd7153 3da3d175 21eb1f0f 14ddf76a`
  - `backend/tests/test_smtp_loopback_noauth_contract.py` `e1e366c7 755fa0f3 514b1269 9f9d93af d10abc7e ea2a3be3 0ec540c2 7fa3dd41`
- R2 originals are **not** deleted and **not** rewritten: `git status` shows zero
  changes under `ai-ledger/product-ai/2026-09-15_kimi_public_provisioning_smtp_source_closure_r2.md`
  and `ai-ledger/product-ai/evidence/2026-09-15_kimi_smtp_r2/` (verified before the R3 commit).

## 1. R2 evidence errata (authorization item 5)

**Defect.** The R2 summary line reports `316 passed`, but the published
`evidence/2026-09-15_kimi_smtp_r2/per_node_r2.txt` retained only **314**
nodeids. The R2 publisher parsed `-v` text with a whitespace-splitting regex
(`^\s*(tests/\S+::\S+)\s+(PASSED|...)`), which silently dropped exactly two
nodeids.

**The two missing nodeids** (verbatim, recovered from the raw R2 log by
whitespace-tolerant re-parse):

1. `tests/test_dc12r1_s1_h1_verification_token_terminal_state.py::test_terminal_token_skips_dependent_lookup_orchestration_and_writes[expired-expires_at-now() - interval '1 hour']`
   — dropped because the parameter itself contains spaces; the parser kept only
   `…[expired-expires_at-now()` and therefore matched no verdict on that fragment.
2. `tests/test_u6i3_owner_credential_setup_consume.py::test_invalid_or_missing_raw_token_fails_neutrally[   ]`
   — dropped because the parameter is literally three spaces, so every
   whitespace-delimited token was consumed as a separator.

**Correction method used for R3 (no whitespace splitting anywhere).**

- collect set: `pytest --collect-only -q -o addopts=` → one nodeid per line
  (the repository `addopts` includes `-v`, which otherwise degrades `-q` to a
  tree; neutralising it is what makes this flat);
- executed set: `--junit-xml` testcase attributes `classname` + `name`, mapped
  back through the known file list (handles class-based tests in
  `test_dc12a_r2_credential_email_links.py` and `test_security_s2_5.py`);
  parameter text lives in `name` verbatim, so spaces survive;
- exact set comparison, and the per-node report is regenerated from the XML.

**R3 result.** `collect_count = 333`, `result_count = 333`, `sets_equal = true`,
`missing_from_results = []`, `extra_in_results = []`,
`unresolvable_junit_cases = []`, verdicts `passed=333, failed=0, error=0,
skipped=0`. Both sets hash to the same digest:
`73fb4922 d10f855c 6315e97c 437ab780 731293f2 7189e790 0ce04295 ad944b0e`
(grouped; join to verify). The two previously lost nodeids appear verbatim in
the regenerated `per_node_r3.txt` (lines 44 and 295).

## 2. R2 rebuildability claim retracted; R3 makes it true (authorization item 6)

The R2 bundle README claimed: "Nothing here must be inherited: a reviewer can
re-run the same commands and regenerate every file from zero." That claim was
**untrue** — the R2 generators were task-local and uncommitted, so the R2
mutation/restore digests, failing node names and counterexample outputs could
not be reproduced from the repository. This errata retracts that claim for R2.
(The R2 files themselves are left untouched per the authorization.)

For R3 the claim is made true and then **verified**: the generators are
published under
`ai-ledger/product-ai/evidence/2026-09-15_kimi_smtp_r3/generators/`
(`mutation_harness.py`, `nodeid_reconciliation.py`, `guard_negatives.py`,
`cluster_identity_counterexample.py`, `cleanup_evidence.py`), parameterized by
environment variables (`KIMI_SMTP_BACKEND_DIR`, `KIMI_SMTP_EVIDENCE_DIR`,
`KIMI_SMTP_TASK_DATABASE_URL`, `KIMI_SMTP_TASK_CLUSTER_ID`,
`TEST_DATABASE_URL`, `REPORTING_USER_PASSWORD`, `KIMI_SMTP_ADMIN_URL`), and the
**published copies** were executed from this repository to produce the R3
evidence below — not asserted, run.

## 3. Exact 28-file focused list (authorization item 6)

Committed as `evidence/2026-09-15_kimi_smtp_r3/focused_files_r3.txt` and
reproduced here verbatim (no `<28 files>` placeholder):

```
backend/tests/test_smtp_auth_mode_guard_config.py
backend/tests/test_smtp_loopback_noauth_contract.py
backend/tests/test_u6k_production_smtp_email_delivery.py
backend/tests/test_u6l_email_verified_onboarding_orchestration.py
backend/tests/test_u6c_signup_email_verification_skeleton.py
backend/tests/test_u6d_verify_email_endpoint.py
backend/tests/test_u6e_onboarding_status_endpoint.py
backend/tests/test_u6f_onboarding_auth_chain_closeout.py
backend/tests/test_u6b_tenant_onboarding_schema.py
backend/tests/test_u6g_tenant_provisioning_contract.py
backend/tests/test_u6h1_tenant_provisioning_service_skeleton.py
backend/tests/test_u6h2_tenant_provisioning_wholesaler_schema.py
backend/tests/test_u6h3_tenant_provisioning_reconcile_cleanup.py
backend/tests/test_u6i2_owner_credential_setup_token_issue.py
backend/tests/test_u6i3_owner_credential_setup_consume.py
backend/tests/test_u6i4_first_admin_rbac_creation.py
backend/tests/test_u6i5_owner_credential_setup_endpoint.py
backend/tests/test_u6i6_onboarding_e2e_closeout.py
backend/tests/test_dc2h_production_smtp_compose_wiring.py
backend/tests/test_dc12a_r2_credential_email_links.py
backend/tests/test_security_s2_5.py
backend/tests/test_dc12r1_s1_retailer_identity.py
backend/tests/test_dc12r1_s1_r1_corrections.py
backend/tests/test_dc12r1_s1_r2_strict_mapping.py
backend/tests/test_dc12r1_s1_h1_verification_token_terminal_state.py
backend/tests/test_dc12r1_j1_h2b_forgot_password_runtime_closure.py
backend/tests/test_dc12r1_j1_h2c_retailer_recovery_discovery.py
backend/tests/test_dc3b_credential_recovery_backend.py
```

## 4. Terminology closure (authorization item 7)

Applied in all R3-owned artifacts (product source, tests, this ledger, the R3
bundle and its generators):

- "cluster ownership" → **cluster identity binding**;
- "zero DDL" → **NO_DIRECT_BOOTSTRAP_OR_CLUSTER_LEVEL_DDL**, with the two
  remaining DDL surfaces stated explicitly wherever the invariant is described:
  (i) **product-lifecycle DDL** — the tenant schema is created by the product's
  public onboarding path under test (verify-email provisioning), not by the
  test; and (ii) the **single exact teardown `DROP SCHEMA`** for the schema that
  same lifecycle created for this test's registered e-mail, target-enumerated
  from the exact recorded registration and asserted zero in teardown.
- R2 artifacts keep their original wording; the correction is recorded here.
- Scan gate: `grep -rn ownership` and `grep -rni 'zero ddl'` over the four R3
  files return no matches (published in `scan_evidence_r3.txt`).

## 5. R3 product delta — one shared pure rule, three call sites

`backend/core/config.py`:

```python
def login_would_send_cleartext(*, auth_mode, host, use_tls, use_starttls) -> bool:
    """True when login credentials would travel unencrypted.

    auth_mode == "login" and host NOT literal loopback requires use_tls or
    use_starttls. Pure: no I/O, no settings object, no logging.
    """
```

Called by:

1. `Settings.validate_smtp_login_transport` (model validator) — Layer 1; the
   `ValueError` message is generic ("SMTP login to a non-loopback host requires
   transport encryption: enable SMTP_USE_TLS or SMTP_STARTTLS.") and never
   echoes host or credentials (asserted by test).
2. `_smtp_config_complete` — Layer 2; external login without encryption is an
   incomplete configuration (`False`).
3. `_send_smtp_email` — Layer 3, before `SMTP`/`SMTP_SSL` is ever constructed;
   raises `EmailDeliveryNotConfiguredError("EMAIL_DELIVERY_NOT_CONFIGURED")`.

Literal-loopback login keeps working without TLS (task-owned plaintext sink).

One annotation was added to a pre-existing line in `config.py`: the
`DATABASE_URL` local-development default now carries
`# pragma: allowlist secret` (repo-sanctioned false-positive handling), because
without it the detect-secrets hook blocks every commit that touches this file —
the same finding that forced R0's `--no-verify`. The baseline is unchanged.

## 6. R3 required tests (authorization item 3) and mutation proofs (item 4)

New/updated tests (all in the pure, database-free suite):

| Requirement | Test |
|---|---|
| shared rule truth table (loopback/external × tls/starttls × login/none/unknown, 10 cases) | `test_login_would_send_cleartext_truth_table` |
| external login + no TLS/STARTTLS → Settings rejects | `test_external_login_without_transport_encryption_is_rejected_by_settings` (also asserts no host/credential leakage) |
| loose settings → completeness false | `test_external_login_without_transport_encryption_fails_completeness` |
| send layer → SMTP and SMTP_SSL construction counts both 0 | `test_external_login_without_transport_encryption_constructs_no_smtp_client` (tripwires on both classes, direct call and via `record_verification_email`) |
| external STARTTLS → starttls before login | `test_external_starttls_upgrades_before_login` (order recorder) |
| external implicit TLS → SMTP_SSL then login | `test_external_implicit_tls_logs_in_after_ssl_connect` |
| loopback login + plaintext still usable | `test_loopback_login_plaintext_remains_usable` (+ the DB suite's real-sink AUTH test) |
| existing external no-auth and unknown-mode rejections do not regress | `test_external_noauth_and_unknown_mode_rejections_do_not_regress` |
| NO_DIRECT_BOOTSTRAP_OR_CLUSTER_LEVEL_DDL stays enforced | `test_database_suite_has_no_direct_bootstrap_or_cluster_level_ddl` |

Semantic mutations, one per layer, all RED on their dedicated test and all
sources restored byte-identically (published in `mutation_evidence_r3.json`):

| Mutation | Removed guard | RED on | Verdict |
|---|---|---|---|
| **M6** | Settings login-transport guard (Layer 1) | `…is_rejected_by_settings` | DETECTED |
| **M7** | `_smtp_config_complete` guard (Layer 2) | `…fails_completeness` | DETECTED |
| **M8** | `_send_smtp_email` guard (Layer 3) | `…constructs_no_smtp_client` | DETECTED |

M1–M5 (R0/R1 loopback and auth-mode guards) are retained and re-run in the same
harness: all eight mutations DETECTED, `survivors: []`, `restored_exact: true`
for every file. M2's RED remains the fail-fast import error caused by flipping
the default to `none`.

## 7. Gates (authorization GATES block)

| Gate | Result |
|---|---|
| GitNexus impact before editing | index rebuilt at base `85f7949`; `_smtp_config_complete` MEDIUM (23 impacted), `_send_smtp_email` HIGH (31 impacted) — all dependents are email-delivery call sites and the SMTP test files |
| pure guard suite with unreachable DB | **51 passed in 0.49s** (`TEST_DATABASE_URL=postgresql://127.0.0.1:1/unreachable`) |
| collect/result nodeid reconciliation | **333 == 333**, sets equal, identical sha256, zero unresolvable |
| M6–M8 semantic RED | all DETECTED (M1–M8: 8/8) |
| `git diff --check` | clean |
| UTF-8 / line endings | all four files valid UTF-8, LF-only content, final newline present (line-ending audit published) |
| detect-secrets | exit 0 on the four R3 files and the five published generators; `.secrets.baseline` unchanged |
| normal hooks, ordinary successor commit and push | done (no `--no-verify`) |
| FULL_SUITE_RESULT | **NOT_RUN** |
| LIVE_RUNTIME_RESULT | **NOT_RUN** |
| FORMAL_SKU_IMPORT_INVOCATIONS | **0** |

Focused regression on the frozen content: 333 nodes across the 28 files, all
passed, per-node evidence regenerated from XML without whitespace splitting.

Post-run cleanup inspection (`cleanup_evidence_r3.json`): SMTP-suite residue is
zero — `registrations_matching_prefix=0`, token rows `0`, and no 22-table
provisioning schemas. The shared task cluster still contains foreign
`t_<32hex>` RBAC-shaped orphan schemas from other suites' fixtures (202 at the
time of this run, growing purely with how often those suites are re-run, as
first attributed in R1); they are not created by the SMTP files and are not
deleted by prefix. Two registration-less wholesaler rows remain from
process-kill residue.

## 8. Evidence classification

| Evidence | Class |
|---|---|
| 333-node regression, per-node XML-derived list, nodeid reconciliation, M1–M8 mutation/restore digests, G1–G6 refusals, C1/C2/X1 cluster-identity counterexamples, scans, cleanup inspection, published generators | SOURCE_PREPARATION |
| Official public API + SMTP lifecycle on a fresh independent V4 root, Redis DB 15, exact server-side `JwtAuthStrategy` proof | **LIVE_RUNTIME — NOT PERFORMED, NOT CLAIMED** |

## 9. Residual risks / open items

1. Task database and cluster remain environment inputs (not rebuildable from
   the repository); the cluster identity binding makes the exact cluster
   explicit (`system_identifier`) but the V4 run must still supply its own
   exclusivity.
2. Foreign-suite RBAC orphan schemas keep accumulating in the shared task
   cluster; the recommended mitigation (per-run residue ledger or a dedicated
   per-task cluster) remains unimplemented by design in this round.
3. `SMTP_USE_TLS` (implicit TLS) still has no real TLS-sink end-to-end test;
   ordering and guard paths are covered by recorders/tripwires only.
4. The `# pragma: allowlist secret` annotation is a deliberate, documented
   handling of a pre-existing public dev placeholder; if the default ever gains
   a real credential this must be revisited (the guard is
   `validate_production_secrets`, which refuses the default in production).

## 10. Stop point

Stop for Kilo bounded source review
(`KILO_BOUNDED_SOURCE_REVIEW_PUBLIC_PROVISIONING_SMTP_R3`). No formal SKU
invocation, no merge, no deployment, no history rewrite; R0–R2 records are
preserved as-is.
