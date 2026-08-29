# Kilo Final Cumulative Governance and Authority-Profile Review Report
## DC-12R1-MVP-L1-HE2-ET1-R3-A1-V1

**Verdict: `PASS_FOR_CTO_DC12R1_MVP_L1_HE2_ET1_R3_A1_V1_KILO_FINAL_CUMULATIVE_GOVERNANCE_AND_AUTHORITY_PROFILE_REVIEW`**

**BASE:** `cdb39e96a50b308aff91d4e94fd8526e7540d921`
**CANDIDATE:** `483b8ab01dae41d52404ebfe197e205a16d56e85`
**SOURCE_BRANCH:** `zcode/dc12r1-mvp-l1-he2-et1-r3-backend-cwd-tempdb-authority-preflight-closure-2026-08-29`
**VERIFICATION_TIER:** `V3_MERGE_CRITICAL_SOURCE_AND_TEST_AUTHENTICITY`

---

## Executive Summary

The CANDIDATE `483b8ab01dae41d52404ebfe197e205a16d56e85` represents the
cumulative HE2-ET1-R3 + R3-A1 evolution of the harness governance and
authority-runner system. After independent source review and executable-
contract validation:

- **R3 backend CWD/temp-DB authority closure** is confirmed: the runner
  preflight AND the child `pytest_sessionstart` independently enforce the
  CWD/MPANGO_ENV/DB-name/port-allowlist/host contract via an origin-bound
  shared stdlib module (`backend_env_authority.py`); drift after
  preflight/collect/authorize/launch voids the command (launch count = 0);
  evidence is fixed categories only — no URL, host, port, password, or env
  value leakage.
- **R3-A1 profile-bound alembic successor authority** is confirmed: the
  old global `EXPECTED_ALEMBIC_HEAD` is retired (`None`); the protected
  authority profile is the sole governance input (schema-required
  `expected_alembic_head`, optional `expected_alembic_parent`); raw-byte
  SHA-256 binds the profile into preflight/authorize/launch and the child
  proof; no CLI, env, or external JSON override path exists for expected
  head/parent; migration scanning reads real migration files and
  revision/down_revision (no filename-prefix, fuzzy-regex, allowlist-prefix,
  or latest-number inference); byte-exact head equality + declared parent
  lineage; multi-head/repeat-revision/missing-parent/wrong-parent/wrong-head/
  cycle/profile-drift/byte-drift all void before command launch.

### Evidence Tiers

- **186 unittests (185 passed, 1 skipped):** `KILO_INDEPENDENTLY_EXECUTED_EVIDENCE`
- **102 RED mutations / 9 GREEN controls:** `KILO_INDEPENDENTLY_EXECUTED_EVIDENCE`
- **Authority runner self-test:** `KILO_INDEPENDENTLY_EXECUTED_EVIDENCE`
- **Candidate fresh-PG/Redis E2E runs:** `CANDIDATE_PROVIDED_EVIDENCE / NOT_INDEPENDENTLY_EXECUTED_BY_KILO`
- **autocrlf=false/true dual checkout:** `HOST_LIMITATION` (autocrlf=false only)

### Residual Items (non-STOP)

- Release validator exit 3 (BLOCKED) due to pre-existing P0/P1 debt
  (`DEBT-AUTH-CRITICAL-TUPLES`, `DEBT-COMMERCE-CRITICAL-TUPLES`) — expected,
  structural gate PASS.
- One unittest (`test_symlink_cwd_is_not_canonical`) skipped on Windows host
  (symlink creation unavailable) — non-STOP; passes on Linux/Lubuntu.

---

## Proof Gate

1. `git fetch --all --prune` executed.
2. Detached worktree created from CANDIDATE at `483b8ab0`.
3. Remote tip verified: `origin/zcode/dc12r1-mvp-l1-he2-et1-r3-backend-cwd-tempdb-authority-preflight-closure-2026-08-29` == `483b8ab01dae41d52404ebfe197e205a16d56e85`.
4. `CANDIDATE^` == BASE: `cdb39e96a50b308aff91d4e94fd8526e7540d921` ✓.
5. BASE..CANDIDATE: 1 commit, 17 files changed (all within `harness-governance/`).
6. **Product source, product tests, migration files, frontend, dependencies,
   lock files, deployment files: ZERO changes.** Verified via
   `git diff --name-only` with pathspec exclusion — all 17 changed files are
   under `harness-governance/`.
7. Delta confined to: HE2 governance/authority runner, schema/profile, tests,
   mutations, protocol-deltas, entry shim. No product code, no migrations, no
   README/ledger changes beyond the protocol-deltas metadata.
8. `product-dev-recovered` remains at BASE (`cdb39e96`); all frozen refs
   (tags) unchanged.

---

## R3 Environment Authority Review

### Shared stdlib module: `validator/backend_env_authority.py` (NEW, 266 lines)

The single implementation of the backend CWD + temp-DB authority contract.
The runner preflight AND the child plugin bootstrap THIS module from its
canonical path (origin-verified, raw bytes digest-bound):

1. **CWD is canonical `backend/`:** `backend_env_facts` checks
   `cwd.exists() AND cwd.name == "backend" AND cwd.is_dir() AND NOT cwd.is_symlink()`.
   Repo root, sibling dirs, and symlinks all fail closed with
   `cwd_not_canonical`.
2. **MPANGO_ENV present and exact:** must be in `{"test", "testing"}`.
   Missing → `mpango_env_missing`; other → `mpango_env_invalid`.
3. **TEST_DATABASE_URL present and parseable:** empty → `db_url_absent`.
4. **DB name fail-closed safety rule:**
   `^(?:test|pytest|ci)[_-][a-z0-9_-]+$`. `mpango_erp_test` (production-like)
   fails. No fallback to production or default DB.
5. **Port in allowlist:** explicit or default 5432 must be a member of
   `MPANGO_TEMP_DB_ALLOWED_PORTS` (comma-separated integers; missing/empty →
   `db_port_allowlist_missing`; not a member → `db_port_not_allowed`).
6. **Allowlist integrity:** missing, format errors (non-integer), empty, wrong
   port, or runtime drift all VOID.
7. **Drift voids command:** `_current_tempdb_binding()` recomputed at AUTHORIZED
   and RUNNING; mismatch with preflight binding → `drift_at_authorize` /
   `drift_at_launch` → VOID (command launch = 0).
8. **Sanitized error output:** every outcome is a fixed category from
   `BACKEND_ENV_CATEGORIES`; no paths, URLs, hosts, ports, or credential
   values escape. All parse/OS failures map to fixed categories.
9. **Shared probe binding:** canonical path + module origin + raw-byte
   SHA-256. A preloaded foreign entry under the fixed key is tamper evidence
   (`module_preload_detected`); the cache is evicted on every load.
10. **No self-authorization:** external proof JSON, env, or CLI cannot
    override the probe. The runner mints the nonce; the child must reproduce
    it. The child independently recomputes the accepted facts digest and the
    runner cross-compares against its own original.

### Runner preflight (R3 section of `authority_runner.py`)

- `EXPECTED_ALEMBIC_HEAD = None` (retired global).
- `bind_backend_env_module()`: freshly loads the shared module from the
  canonical path (origin verified) and binds its raw-byte SHA-256.
- `_enforce_backend_env_authority()`: runs the shared probe, binds a digest
  over the accepted facts (env, db_name, port, host, allowlist, cwd).
- `_enforce_backend_env_authority_alembic()`: reads expected head/parent from
  the PROTECTED profile; runs `alembic_verify` via the shared module.

### Child `pytest_sessionstart` (R3 section of `pytest_et1_collector.py`)

- `_backend_env_recheck_problems()`: the child independently loads the shared
  module from the canonical path, recomputes the accepted facts digest, and
  compares against the runner's ORIGINAL `ET1_RUNNER_TEMPDB_BINDING_SHA`.
- `_alembic_recheck_problems()`: the child independently runs
  `alembic_verify` against the profile's expected head/parent.
- Any mismatch → `pytest.exit` before collection.

---

## R3-A1 Alembic Profile Review

### Profile contract (`inventory/authority-profiles.json`)

- `AUTHORITY_H2C_BACKEND`: `expected_alembic_head = "037_payment_declarations_schema"`
  (no expected parent; H2-C uses 037 as the terminal head).
- `AUTHORITY_SKU_M1_BACKEND`: `expected_alembic_head = "038_catalog_identity_vertical_slice"`,
  `expected_alembic_parent = "037_payment_declarations_schema"` (038 must be the
  direct single successor of 037).

### Schema enforcement (`schemas/authority-profiles.schema.json`)

- `expected_alembic_head` is REQUIRED (pattern `^[a-z0-9_]+$`).
- `expected_alembic_parent` is optional (same pattern).
- `additionalProperties: false` — no extra fields can sneak in.

### Authority properties confirmed

1. **Old global `EXPECTED_ALEMBIC_HEAD` retired:** set to `None` in the runner;
   the comment states "retired: authority comes from the profile".
2. **Profile is protected, non-waiver:** loaded from explicit path, schema-
   validated, trap-registry cross-checked; a hardcoded `{"mode": "cli"}`
   document is rejected.
3. **Profile raw-byte SHA-256 binds the run:** `sha256_file(profile_path)`
   bound at COLLECT_PROVEN; child recomputes and compares; drift at AUTHORIZED
   voids.
4. **No CLI/env/external override:** source scan confirms no
   `expected-alembic-head`, `MPANGO_EXPECTED_ALEMBIC_HEAD`, or
   `os.environ.get("EXPECTED_ALEMBIC_HEAD"` in the runner.
5. **AUTHORITY_H2C authorizes exactly 037:** byte-exact; prefix-similar
   (`037_payment_declarations_schemax`) and whitespace (`" 037_...`) both
   fail with `alembic_head_mismatch`.
6. **AUTHORITY_SKU_M1 authorizes exactly 038 with parent 037:** head must equal
   `038_catalog_identity_vertical_slice` byte-exact; down_revision must be
   exactly `037_payment_declarations_schema` (merge parents, wrong parent,
   or missing parent all fail).
7. **Migration scanning reads real files:** `alembic_scan` reads every
   `*.py` in `versions/`, parses `revision` and `down_revision` with strict
   single-value semantics (tuples/lists = merge = not a single successor).
   No filename-prefix, fuzzy-regex, allowlist-prefix, or latest-number
   inference.
8. **Anomalies void before launch:** multi-head (`alembic_multiple_heads`),
   wrong head (`alembic_head_mismatch`), wrong parent
   (`alembic_parent_mismatch`), unreadable tree (`alembic_tree_unreadable`),
   profile drift, migration byte drift.
9. **H2-C does NOT require 038:** using the H2-C profile, the SKU profile's
   expected head/parent is irrelevant; the tree at 037 passes.
10. **SKU profile requires real 038 as 037's unique successor:** a tree at 037
    (no 038) fails with `alembic_head_mismatch`; a tree where 038 is not
    037's direct single successor fails with `alembic_parent_mismatch`.
11. **Runner + child independent computation + cross-compare:** head, parent,
    profile digest, migration binding are independently computed by runner
    and child; the runner cross-compares child proof values against its own
    originals (never self-compared).
12. **Non-zero product test results classified as TEST_RED/FINISHED:** a
    non-zero exit from the authority command lands FINISHED with
    `RUN_VERDICT_TEST_RED`; it is never misclassified as VOID.

---

## Independent Evidence (Kilo)

| Check | Result | Evidence Tier |
|-------|--------|---------------|
| Governance unittests (186) | 185 passed, 1 skipped (symlink/Windows) | KILO_INDEPENDENTLY_EXECUTED_EVIDENCE |
| Authority runner self-test | OK | KILO_INDEPENDENTLY_EXECUTED_EVIDENCE |
| Mutation gate (102 RED / 9 GREEN) | 102 RED + 9 GREEN, tree integrity byte-identical | KILO_INDEPENDENTLY_EXECUTED_EVIDENCE |
| CWD sibling VOID | T221 RED | KILO_INDEPENDENTLY_EXECUTED_EVIDENCE |
| Missing allowlist VOID | CLI + T226 RED | KILO_INDEPENDENTLY_EXECUTED_EVIDENCE |
| Wrong port VOID | CLI + T224 RED | KILO_INDEPENDENTLY_EXECUTED_EVIDENCE |
| Unsafe DB name VOID | CLI + T223 RED | KILO_INDEPENDENTLY_EXECUTED_EVIDENCE |
| MPANGO_ENV missing/invalid VOID | CLI + T222 RED | KILO_INDEPENDENTLY_EXECUTED_EVIDENCE |
| Preflight drift VOID | T228 RED | KILO_INDEPENDENTLY_EXECUTED_EVIDENCE |
| Profile env/CLI override blocked | A105 + A106 RED | KILO_INDEPENDENTLY_EXECUTED_EVIDENCE |
| Wrong head VOID | A102 RED | KILO_INDEPENDENTLY_EXECUTED_EVIDENCE |
| Wrong parent VOID | A104 RED | KILO_INDEPENDENTLY_EXECUTED_EVIDENCE |
| Multi-head VOID | A103 RED | KILO_INDEPENDENTLY_EXECUTED_EVIDENCE |
| Child recheck deletion VOID | T226 + A107 RED | KILO_INDEPENDENTLY_EXECUTED_EVIDENCE |
| Runner-child self-compare blocked | S225 + X01 RED | KILO_INDEPENDENTLY_EXECUTED_EVIDENCE |
| Nonzero exit = TEST_RED not VOID | X11 RED | KILO_INDEPENDENTLY_EXECUTED_EVIDENCE |
| Candidate fresh-PG/Redis E2E | 8/8 core + 7/7 redis claimed | CANDIDATE_PROVIDED_EVIDENCE / NOT_INDEPENDENTLY_EXECUTED_BY_KILO |
| autocrlf=false/true dual checkout | autocrlf=false only on this host | HOST_LIMITATION |

---

## Quality Gate

| Check | Result |
|-------|--------|
| Structural validator | exit 0, structural=PASS |
| Release validator | exit 3, release=BLOCKED (pre-existing P0/P1 debt only) |
| `git diff --check` | clean (no conflict markers, no whitespace issues) |
| detect-secrets (delta files) | clean (`results: {}`) |
| Strict UTF-8 / no BOM / no NUL / LF | OK across all 17 changed files |
| GitNexus analyze/status | indexed, up-to-date at 483b8ab |
| Detached worktree | clean (nothing to commit) |

---

## STOP Conditions

No STOP condition triggered:

- CANDIDATE/parent/remote tip: consistent ✓
- Product/migration files: zero changes ✓
- Profile override: none exists ✓
- Successor/prefix acceptance: byte-exact only ✓
- Head/parent/multi-head drift: blocked before launch ✓
- Child independent recheck + cross-compare: confirmed ✓
- CWD/temp-DB negative control: command launch = 0 ✓
- Mutations: all 102 RED, all 9 GREEN ✓
- Tree integrity: before == after ✓
- Sensitive env values: none in report ✓
- 186/102-9/tree-integrity: all hold ✓

---

## Verdict

**PASS_FOR_CTO_DC12R1_MVP_L1_HE2_ET1_R3_A1_V1_KILO_FINAL_CUMULATIVE_GOVERNANCE_AND_AUTHORITY_PROFILE_REVIEW**

This PASS does NOT represent:
- Lubuntu fresh-runtime PASS
- SKU-M1 product candidate PASS
- Merge approval
- Deployment approval
