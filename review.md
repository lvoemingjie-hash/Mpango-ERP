# Kilo Bounded Source Review — Public Provisioning SMTP R3

- Authorization: `CTO-AUTH-PUBLIC-PROVISIONING-SMTP-R3-KILO-V1-2026-09-15`
- Task: `KILO_BOUNDED_SOURCE_REVIEW_PUBLIC_PROVISIONING_SMTP_R3`
- Verification tier: `V3_INDEPENDENT_SOURCE_AND_TARGETED_EXECUTION`
- Claim ceiling: `SMTP_TRANSPORT_POLICY_AND_EVIDENCE_TRUTH_ONLY`
- BASE: `85f79491f3275410946d225c9af837ff949a1e77`
- PRODUCT_CANDIDATE: `a8249669a8c3895aebc2817054c1abb72233fb48`
- FROZEN_REVIEW_TIP: `2665f0ee019302291bfca1d3f579cf852bc633ff`
- Verdict: **PASS_FOR_CTO_PUBLIC_PROVISIONING_SMTP_R3_KILO_BOUNDED_SOURCE_REVIEW**
- Author PASS not inherited: every claim below was re-derived by the reviewer
  (fresh fetch, fresh isolated worktree, independently written probes,
  independently implemented mutation runner, independent collection).

## 0. Mandatory report fields

| field | value |
|---|---|
| CHANGED_OR_ADDED_TESTS_COVERING_NEW_PATHS | 2 test files modified by the candidate (`backend/tests/test_smtp_auth_mode_guard_config.py`, `backend/tests/test_smtp_loopback_noauth_contract.py`); the pure guard file covers all new R3 paths (51 nodes; 20 R3-specific nodes cover `login_would_send_cleartext` + the three transport-guard layers + the two transport orderings + loopback plaintext retention); the DB-backed module covers the public lifecycle (7 nodes; NOT RUN by this reviewer — requires the task database) |
| CODE_PATH_TO_TEST_MATRIX | see section 5 |
| NEGATIVE_AND_FAILURE_PATHS | see section 6 |
| FALSIFICATION_RESULT | M6/M7/M8 independently implemented, each SEMANTIC_RED on its named assertion; M1/M3/M4/M5 re-verified SEMANTIC_RED; M2 = ImportError (exit 4), listed as auxiliary evidence only; 0 survivors; 8/8 byte-identical restores (sha256 verified); see section 7 |
| UNCOVERED_NEW_PATHS | see section 8 |
| FULL_SUITE_RESULT | NOT_RUN |
| LIVE_RUNTIME_RESULT | NOT_RUN |
| FORMAL_SKU_IMPORT_INVOCATIONS | 0 |
| BROWSER_RUNTIME | NOT_RUN |

## 1. Phase 1-2: isolation and structure (verified)

- `git fetch --all --prune` against `origin` = `https://github.com/lvoemingjie-hash/Mpango-ERP.git` from a fresh full clone; a new isolated worktree was created at detached `2665f0ee` (`2366` files checked out, clean status).
- Remote tip of `origin/kimi/public-provisioning-smtp-source-closure-2026-09-15` == `2665f0ee019302291bfca1d3f579cf852bc633ff` (rev-parse proven).
- Two-layer parent chain: `2665f0ee` -> parent `a8249669` (PRODUCT_CANDIDATE) -> parent `85f79491` (BASE). The frozen tip itself only edits `ai-ledger/product-ai/2026-09-15_kimi_public_provisioning_smtp_source_closure_r3.md` (manifest recording).
- `git diff --name-only 85f79491 a8249669` = **exactly 19 paths**:
  - 1 modified ledger report + 14 added evidence paths under `ai-ledger/product-ai/evidence/2026-09-15_kimi_smtp_r3/` (incl. 5 published generators),
  - 2 modified product paths — **exactly** `backend/core/config.py` and `backend/services/email_delivery.py`,
  - 2 modified test paths (`test_smtp_auth_mode_guard_config.py`, `test_smtp_loopback_noauth_contract.py`).
- Working-tree SHA256 of both product files matches the published mutation evidence `sha256_before` values byte-for-byte (`0ea37d75...c65409d1`, `c4c7bad3...f0a58604`), proving the published evidence was produced from this exact source state.

## 2. Phase 3: independent source review (author PASS not inherited)

### 2.1 Shared rule — `login_would_send_cleartext` (config.py:39-63)

Pure function, keyword-only. Returns True iff auth_mode is `login`
(strip/lower-normalized) AND neither `use_tls` nor `use_starttls` AND the host
is not a literal loopback host. Review findings:

- Correctly reuses `is_loopback_smtp_host`, which never resolves DNS names:
  `127.0.0.1.nip.io` (loopback-resolving name) is NOT exempt (proven by probe
  and by the pure suite truth table).
- `None`/blank/odd auth modes degrade to "not login" -> rule returns False
  (no false-positive blocking of noauth/unknown modes; those have their own
  R1/R2 guards).
- Loopback exemption is deliberate and safe: the task-owned capture sink is
  plaintext by design and bound to 127.0.0.0/8, ::1, or literal `localhost`.
- Grep-verified: exactly three production call sites (one per layer) plus
  tests. No other module imports or re-implements the rule -> no drift.

### 2.2 Layer 1 — Settings validator `validate_smtp_login_transport` (config.py:329-347)

Model validator, runs in **all** environments (env-independent). Raises
`ValueError` with a generic message ("enable SMTP_USE_TLS or SMTP_STARTTLS")
that echoes neither the host nor credentials (asserted). Placement before
`validate_production_secrets` is irrelevant to correctness (all `mode="after"`
validators run; order affects only which error surfaces first).

### 2.3 Layer 2 — `_smtp_config_complete` (email_delivery.py:322-330)

New guard returns False for insecure external login before the port check.
`getattr` fallbacks (`SMTP_USE_TLS` -> False, `SMTP_STARTTLS` -> True) mirror
the Settings field defaults, so a loosely constructed object missing
`SMTP_STARTTLS` is treated as encrypted-default, and the send layer attempts
STARTTLS — failing closed at the transport if unsupported. Consistent.

### 2.4 Layer 3 — `_send_smtp_email` final guard (email_delivery.py:381-389)

Raises `EmailDeliveryNotConfiguredError` **before** `client_factory`
selection, i.e. before `smtplib.SMTP`/`smtplib.SMTP_SSL` can ever be
constructed. This is the choke point for all five `record_*` wrappers; grep
confirms all production callers (`onboarding_service`,
`password_reset_service`, `retailer_provisioning_service`, both API routers)
reach SMTP only through this function.

### 2.5 Transport orderings (email_delivery.py:391-405)

- STARTTLS path (`use_tls=False, use_starttls=True`): plain `SMTP(host, port,
  timeout=15)` -> `client.starttls(context=context)` -> `client.login(...)` ->
  `client.send_message(...)`. Exactly connect->starttls->login->send.
- Implicit TLS (`use_tls=True`): `SMTP_SSL(host, port, timeout=15,
  context=ssl.create_default_context())` -> login -> send; the
  `use_starttls and not use_tls` condition suppresses a second upgrade
  (no double-TLS). Exactly SMTP_SSL->login->send.
- Literal-loopback plaintext login (login mode, 127.0.0.1/8, ::1, localhost,
  no TLS): the shared rule returns False (exempt) -> plain connect -> login ->
  send retained. Verified at recorder level AND at runtime against a real
  loopback AUTH-LOGIN sink (section 4).
- All transport exceptions wrap into `EmailDeliveryNotConfiguredError` (503
  category preserved; no silent fallback to the dev sink).

## 3. Phase 4: external login + TLS=false + STARTTLS=false (proven)

Independent probe (21/21 checks, reviewer-written, run from the isolated
worktree with the repository venv, Python 3.12.10 / pydantic 2.12.5):

1. Real `Settings(**insecure_kwargs)` raises `ValidationError`; message
   contains `SMTP_USE_TLS`/`SMTP_STARTTLS` and neither the external host nor
   the password.
2. `_smtp_config_complete` -> False; `is_verification_email_delivery_configured`
   -> False (loose settings bypassing pydantic, to reach the layer).
3. With counting tripwires installed on `smtplib.SMTP` and `smtplib.SMTP_SSL`:
   `_send_smtp_email` raises `EmailDeliveryNotConfiguredError` AND
   `record_verification_email` raises it; **construction counts: SMTP = 0,
   SMTP_SSL = 0**.

## 4. Phase 5: orderings and loopback retention (proven)

Recorder fakes (no sockets) on the send layer:

- STARTTLS: events == `[connect:smtp.example.invalid:2525, starttls, login, send]`
- Implicit TLS: events == `[connect_ssl:..., login, send]`, and `starttls`
  never fires (no double upgrade).
- Loopback plaintext login: configuration still complete; events ==
  `[connect:127.0.0.1:2525, login, send]`.

Runtime proof that literal-loopback plaintext login **remains usable** (real
socket, no external network): a task-owned capture sink on 127.0.0.1
advertising `AUTH LOGIN` accepted a production-mode `record_verification_email`
call — exactly 1 message captured (`To`, `Subject` verified), exactly 1
connection, exactly one AUTH LOGIN exchange arriving
`("mailer@example.invalid", <task-local placeholder password>)`.

## 5. Code path to test matrix

| product path (new in R3) | suite node(s) | reviewer execution |
|---|---|---|
| `login_would_send_cleartext` truth table (10 cases incl. nip.io, None host) | pure::`test_login_would_send_cleartext_truth_table` | 51/51 run + probe S1c/S1d/S1e |
| Layer 1 Settings rejection | pure::`test_external_login_without_transport_encryption_is_rejected_by_settings` | run + probe S1 + M6 RED |
| Layer 2 completeness refusal | pure::`test_external_login_without_transport_encryption_fails_completeness` | run + probe S2 + M7 RED |
| Layer 3 send-guard, zero construction | pure::`test_external_login_without_transport_encryption_constructs_no_smtp_client` | run + probe S3 + M8 RED |
| STARTTLS ordering connect->starttls->login->send | pure::`test_external_starttls_upgrades_before_login` | run + probe P5a |
| Implicit TLS SMTP_SSL->login->send | pure::`test_external_implicit_tls_logs_in_after_ssl_connect` | run + probe P5b/P5c |
| Loopback plaintext login retained | pure::`test_loopback_login_plaintext_remains_usable` | run + probe P5d/P5e + real loopback sink P5f-P5i |
| R1/R2 noauth/loopback/unknown-mode guards (regression surface) | pure suite sections 1-4 (26 nodes) incl. static NO_DIRECT_BOOTSTRAP_OR_CLUSTER_LEVEL_DDL scan of the DB suite | 51/51 run |
| Public lifecycle over SMTP (DB-backed, V1 items 1-5) | DB suite 7 nodes | NOT RUN by reviewer (task database required) — author-claimed only |

## 6. Negative and failure paths

Independently executed by this reviewer:

- Settings construction rejection (insecure external login) — ValidationError.
- Completeness refusal (same config, loose object) — False / not-configured.
- Send-layer fail-closed with zero SMTP/SMTP_SSL constructions (same config).
- Pre-existing R1/R2 negatives re-proven green inside 51/51: unknown auth mode,
  none-off-loopback (also with implicit TLS), missing credentials, DDL-surface
  static invariant, noauth/unknown-mode zero-connection tripwires.
- Transport failure wrapping: any transport exception -> 503 category (code
  reviewed; loopback refused-port path is covered by the DB suite, NOT RUN
  here).

## 7. Falsification result (mutations; reviewer-implemented runner)

Method: reviewer-written runner (not the published harness). Anchor-uniqueness
check -> byte mutation -> changed-bytes assertion -> single detector node ->
verdict classification (SEMANTIC_RED requires a `FAILED tests/...` line naming
the expected node; ImportError/collection errors never count as semantic RED)
-> restore from memory -> sha256 byte-identity verification.

| id | verdict | exit | restored_exact | detector |
|---|---|---|---|---|
| M1_settings_loopback_validator_removed | SEMANTIC_RED | 1 | True | test_noauth_mode_is_rejected_for_non_loopback_host |
| M2_default_auth_mode_flipped_to_none | IMPORT_ERROR (auxiliary ONLY) | 4 | True | (module import fails; NOT a named semantic RED) |
| M3_config_completeness_loopback_guard_removed | SEMANTIC_RED | 1 | True | test_config_completeness_rejects_offloopback_noauth |
| M4_send_layer_loopback_guard_removed | SEMANTIC_RED | 1 | True | test_delivery_layer_guard_blocks_offloopback_noauth_before_transport |
| M5_send_layer_unknown_mode_guard_removed | SEMANTIC_RED | 1 | True | test_send_layer_unknown_mode_guard_blocks_before_transport |
| M6_settings_login_transport_guard_removed | SEMANTIC_RED | 1 | True | test_external_login_without_transport_encryption_is_rejected_by_settings |
| M7_completeness_login_transport_guard_removed | SEMANTIC_RED | 1 | True | test_external_login_without_transport_encryption_fails_completeness |
| M8_send_layer_login_transport_guard_removed | SEMANTIC_RED | 1 | True | test_external_login_without_transport_encryption_constructs_no_smtp_client |

- M6/M7/M8: each RED on exactly its named semantic assertion; none is an
  import error, syntax error, or dirty-file artifact. Requirement met.
- M2: flipping the `SMTP_AUTH_MODE` default breaks the module-level
  `settings = get_settings()` (config.py:446) via the S2.5 SECRET_KEY/loopback
  validators at import time -> exit 4 conftest ImportError. Listed strictly as
  auxiliary evidence; the named-node semantic RED claim is NOT made for M2.
- 0 survivors; 8/8 byte-identical restores; product tree clean afterwards
  (`git status --porcelain` empty; hashes re-verified).

## 8. Phase 9/10: checklist truth and generator audit

Independent collection (venv pytest `--collect-only -q -o addopts=`, 28-file
list from the published `focused_files_r3.txt`):

- Collected nodes: **333** (matches published checklist).
- Sorted-set sha256 = `73fb4922d10f855c6315e97c437ab780731293f27189e7900ce04295ad944b0e`
  — identical to BOTH published `collect_set_sha256` and `result_set_sha256`.
- `per_node_r3.txt` = 333 node lines, set-equal to my independent collection.
- Exactly **2 nodeids containing spaces**, matching the published bundle:
  1. `tests/test_dc12r1_s1_h1_verification_token_terminal_state.py::test_terminal_token_skips_dependent_lookup_orchestration_and_writes[expired-expires_at-now() - interval '1 hour']`
  2. `tests/test_u6i3_owner_credential_setup_consume.py::test_invalid_or_missing_raw_token_fails_neutrally[   ]`

Generator audit (`generators/`):

- `nodeid_reconciliation.py`: `main()` returns 0 iff `sets_equal and not
  unresolvable` — **verdicts are never consulted.** A run where all 333 nodes
  fail still exits 0. Therefore `nodeid_reconciliation exit 0` proves only
  collect-set == result-set identity, NOT that tests are green; green-ness
  lives only in the separately-written `verdicts` dict. The published
  `verdicts` (333 passed) is author-claimed runtime data and is NOT
  independently reproduced here (its `result_ids()` runs the full 28-file
  suite against the task database — out of scope and prohibited for this
  review).
- `mutation_harness.py`: logic equivalent to my independent reproduction;
  latent defect — line 25 reassigns `BACKEND = WORKTREE + "\backend"`,
  discarding the env-derived value (Windows-only path join; breaks
  rebuildability on POSIX and if the checkout's backend dir is named
  differently). Non-blocking: my results do not depend on it.
- `guard_negatives.py` / `cluster_identity_counterexample.py` /
  `cleanup_evidence.py`: require the task Postgres cluster (admin DSN,
  database create/drop in G6). Not executed here; published G1-G6/C1-C2/X1
  claims reviewed as author-run evidence only.

## 9. Phase 11 adjudication: dev_sink + residual external plaintext SMTP parameters

**Disposition: ACCEPTABLE_STRICT_POLICY** (no BLOCKING_DEFECT).

- `EMAIL_PROVIDER`/`EMAIL_DELIVERY_MODE` = `dev_sink` in production never
  completes configuration (`_smtp_config_complete` requires both == "smtp");
  every `record_*` wrapper fails closed with `EMAIL_DELIVERY_NOT_CONFIGURED`.
  The in-memory `_DEV_*` capture lists are reachable only when
  `MPANGO_ENV != "production"` — production can never fall back to the sink.
- Residual external plaintext SMTP parameters (login + non-loopback + no
  TLS/STARTTLS) are rejected strictly at all three layers: Settings
  construction (real objects), completeness (loose objects), and the final
  send guard (zero transport constructions). Rejection is env-independent and
  keeps the generic 503 category without echoing host/credentials.
- Literal-loopback plaintext login remains usable by design, with the
  DNS-name loophole closed (loopback-resolving names stay rejected).

NONBLOCKING_OBSERVATIONS (recorded, none blocking):

1. `_DEV_EMAIL_DELIVERIES` / `_DEV_RESET_EMAIL_DELIVERIES` /
   `_DEV_RETAILER_EMAIL_DELIVERIES` grow unboundedly in long-lived
   non-production processes (memory only; no network egress).
2. In `_send_smtp_email`, a loose settings object with `SMTP_HOST=None` is
   coerced to the literal string `"None"` before the guards; every R3-relevant
   path still fails closed (login+None-host -> shared rule True -> guard; or
   transport error -> wrapped 503). Pre-existing behavior, not introduced by
   R3.
3. Published `mutation_harness.py` Windows-only `BACKEND` reassignment
   (section 8) — generator robustness nit.
4. `mypy` reports 3 pre-existing errors on the `client_factory` indirection in
   `email_delivery.py` (byte-identical at the base candidate; net-new 0).

## 10. Phase 12: hygiene (verified)

- `git diff --check`: clean (exit 0) on the untouched worktree.
- UTF-8/LF audit of all 19 changed paths: utf8=ok for 19/19, no BOM, uniform
  line endings (no mixed endings), final newline present in 19/19.
- detect-secrets (read-only): `python -m detect_secrets.pre_commit_hook
  --baseline .secrets.baseline <changed files>` exit 0; `.secrets.baseline`
  SHA256 before == after ==
  `03D01ADE9A61E4322E405550139EE26AE75A8A2577F717218081CAFF37DDF4C2`
  (unchanged; the one pre-existing DATABASE_URL dev default stays annotated
  `# pragma: allowlist secret` in config.py).

## 11. Prohibitions and scope compliance

- No product/migration/SKU/public-registration-response changes: working tree
  byte-identical to `2665f0ee` after all execution (status clean).
- No external SMTP contacted: all transport proof used recorder fakes or a
  127.0.0.1 loopback capture sink owned by the probe.
- No shared database generator run; no task database contacted;
  FULL_SUITE_RESULT=NOT_RUN; the only suite executions are the database-free
  pure guard file (51/51) and single-node mutation detectors.
- No merge, no deploy, no amend/force.

## 12. Verdict

The R3 product change enforces a single, drift-proof transport rule — external
SMTP login requires implicit TLS or STARTTLS — at three independent layers
with a fail-closed 503 category and zero transport constructions on every
rejection path, while preserving the task-owned literal-loopback plaintext
capture sink and both encrypted orderings. Evidence-truth requirements are met
(exit-0 reconciliation correctly downgraded to set-identity proof; M2
downgraded to auxiliary import-error evidence). Published-checklist
arithmetic, digests, and space-nodeids reconcile exactly with independent
collection.

**PASS_FOR_CTO_PUBLIC_PROVISIONING_SMTP_R3_KILO_BOUNDED_SOURCE_REVIEW**

Next gate: `FRESH_INDEPENDENT_V4_PUBLIC_API_SMTP_RUNTIME`.
