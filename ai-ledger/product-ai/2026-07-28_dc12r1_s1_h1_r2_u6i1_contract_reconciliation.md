# DC-12R1-S1-H1-R2 Stable U6I1 Historical Scope Contract

Date: Tuesday, July 28, 2026

- Branch: `opencode/dc12r1-s1-h1-r2-u6i1-contract-reconciliation-2026-07-28`
- Base candidate: `ac625b78850df3e6f078896a318770902b48a9f4`
- H1 product fix commit (unchanged, reference only):
  `9420476bc4d6f8bc0803b339a8c4671d9202d4e2`
- Final branch tip: proven equal to `git ls-remote` in the `R2 Push Proof`
  section below (recorded after the fast-forward push; not self-referenced
  inline).

## Verdict

`PASS_FOR_CTO_DC12R1_S1_H1_R2_INDEPENDENT_FULL_GATE`

The U6I1 owner-credential-setup schema test's scope guard no longer compares
the moving current HEAD against a fixed base (which structurally failed for
every later task that legitimately touched a runtime path). It now anchors the
U6I1 scope assertion on the fixed historical U6I1 implementation commit via
`git diff-tree`, requires exactly the original five U6I1 files, fails closed if
that commit is unavailable, and still rejects forbidden runtime paths. No U6I1
schema/security assertion was weakened; no product, migration, config, frontend,
or lockfile files were changed.

## Defect Repaired

`backend/tests/test_u6i1_owner_credential_setup_schema.py` previously held a
permanent current-HEAD comparison:

- `BASE_REF = "6a8ddcf3..."` and `_changed_paths()` ran
  `git diff --name-only BASE_REF` plus `git status --porcelain` against the
  whole working tree.
- `test_no_route_service_frontend_or_user_rbac_behavior_changed` therefore
  flagged any change (committed or untracked) to
  `backend/services/onboarding_service.py` (and other runtime paths) since that
  base, regardless of which task made the change.
- This made the guard structurally fail for H1 (whose entire purpose is to edit
  `onboarding_service.py`) and for any later task. It was a moving-target scope
  check, not a U6I1 scope check.

## Repair

Changed file:

- `backend/tests/test_u6i1_owner_credential_setup_schema.py`

Behavior now enforced:

- Removed `BASE_REF` and the moving current-HEAD `git diff`/`git status`
  comparison.
- The scope assertion is anchored on the fixed historical U6I1 implementation
  commit `712db0c1d3796a22c8b3c4c398d91577146d3ee1`.
- `_historical_u6i1_paths()` runs `git diff-tree --no-commit-id --name-only -r`
  against that exact commit.
- `test_u6i1_historical_implementation_scope_is_exactly_the_original_five_files`
  requires the diff-tree to equal exactly the original five U6I1 files
  (`EXPECTED_U6I1_PATHS`, count == 5) and to be disjoint from
  `FORBIDDEN_RUNTIME_PATHS` and from any `frontend/` path.
- Fail closed: if the historical commit is unavailable (e.g. shallow clone),
  `git rev-parse --verify <commit>^{commit}` returns non-zero and the helper
  raises `AssertionError("U6-I1 historical commit is unavailable; cannot verify
  scope")`. Verified at runtime: a missing SHA yields rev-parse returncode 128,
  which triggers the fail-closed assertion.
- New regression `test_synthetic_forbidden_runtime_path_is_still_rejected`
  proves the guard was not weakened: a synthetic scope containing
  `backend/services/onboarding_service.py` still fails the disjoint check.
- All U6I1 schema/security assertions (token-hash-only table, FK ondelete
  CASCADE, unique token_hash, active partial index with
  `used_at IS NULL AND revoked_at IS NULL AND is_deleted = false`, purpose
  default + check constraint, migration revision/down_revision, alembic head,
  forbidden token columns, foundation artifacts) are unchanged.

## Historical Scope Proof

`git diff-tree --no-commit-id --name-status -r 712db0c1d3796a22c8b3c4c398d91577146d3ee1`:

```
A  ai-ledger/product-ai/2026-07-08_u6i1_owner_credential_setup_schema.md
A  backend/alembic/versions/028_owner_credential_setup_tokens.py
M  backend/models/__init__.py
M  backend/models/tenant_onboarding.py
A  backend/tests/test_u6i1_owner_credential_setup_schema.py
```

Exactly five files, matching `EXPECTED_U6I1_PATHS`. None is a forbidden runtime
path; none is under `frontend/`.

## GitNexus Impact (before edit)

Index up-to-date at base `ac625b7` (13,604 nodes / 41,944 edges).

- `gitnexus impact _changed_paths --direction upstream --include-tests`:
  `impactedCount: 2`, risk `LOW`, no production processes affected. The two
  direct dependents are the scope-guard test functions inside the same file.
- A sibling `_changed_paths` exists in
  `test_u6i0_owner_credential_setup_contract.py`; it is out of R2 scope and was
  not touched.

## Validation Bundle (real PostgreSQL 16 + Redis 7)

Fresh disposable environment:

- PostgreSQL 16 container `dc12r1_s1_h1r2_pg16` (image `postgres:16`,
  server `16.14`, host `127.0.0.1:5518`)
- Redis 7 container `dc12r1_s1_h1r2_redis7` (image `redis:7`,
  host `127.0.0.1:6392`)
- source DB `test_dc12r1_s1_h1r2` migrated to head
  (`036_retailer_mvp_identity`) before the run; `MPANGO_ENV=test`,
  loopback-only DSN.

Command:

```bash
cd backend
pytest \
  tests/test_u6i1_owner_credential_setup_schema.py \
  tests/test_dc12r1_s1_h1_verification_token_terminal_state.py \
  tests/test_u6d_verify_email_endpoint.py \
  tests/test_u6f_onboarding_auth_chain_closeout.py \
  tests/test_u6l_email_verified_onboarding_orchestration.py \
  tests/test_u6i6_onboarding_e2e_closeout.py \
  tests/test_auth_regressions.py \
  tests/test_route_authorization_policy.py
```

Result:

- `74 passed`

Proves:

- the repaired U6I1 scope guard is green
  (`test_u6i1_historical_implementation_scope_is_exactly_the_original_five_files`,
  `test_synthetic_forbidden_runtime_path_is_still_rejected`) and all U6I1
  schema/security assertions still pass;
- the H1 terminal-state boundary is unchanged;
- U6D / U6F / U6L / U6I6 / auth / route-policy regressions are green.

## Quality Gates

- `python -m py_compile tests/test_u6i1_owner_credential_setup_schema.py` ->
  `PYCOMPILE_OK`
- `git diff --check` -> clean (no whitespace errors)
- scoped `pre-commit run --files` on the U6I1 test: trailing-whitespace,
  end-of-file-fixer, check-added-large-files, detect-secrets all Passed
- scoped `detect-secrets scan --baseline .secrets.baseline` on the U6I1 test ->
  exit 0 (no new secrets; the unintended Windows path-separator normalization of
  `.secrets.baseline` produced by the scan was discarded and is not committed)
- mojibake scan on the U6I1 test -> `MOJIBAKE_CLEAN` (pure ASCII)
- GitNexus `impact` before edit -> LOW risk, 2 same-file dependents, no
  production processes affected
- GitNexus `analyze`/`status` after commit -> recorded in `R2 Push Proof`

## Final Changed-File Scope (exactly 2 files)

`git diff --name-status ac625b78..HEAD`:

```
M  backend/tests/test_u6i1_owner_credential_setup_schema.py
A  ai-ledger/product-ai/2026-07-28_dc12r1_s1_h1_r2_u6i1_contract_reconciliation.md
```

No product, migration, model/schema, frontend, config, lockfile, or deploy
files. (`backend/models/tenant_onboarding.py` is referenced by the historical
diff-tree proof above but is NOT modified by R2.)

## Cleanup Proof

- disposable PostgreSQL 16 container `dc12r1_s1_h1r2_pg16` removed
- disposable Redis 7 container `dc12r1_s1_h1r2_redis7` removed
- R2 throwaway helper scripts (`_r2_failclosed_probe.py`, `_r2_mojibake.py`)
  removed; final `git status --porcelain | wc -l` == 0 (zero tracked, zero
  untracked), so the worktree is genuinely clean.

## R2 Push Proof

- push method: fast-forward only (no `--force`).
- protected branches untouched:
  `origin/product-dev-recovered` == `c78101186f1fb4811a886e3e55f96708ea960c0a`,
  `origin/main` == `134ea59e02204842e55ebe36f721f44df5a33737`.
- local HEAD == `git ls-remote` HEAD for
  `opencode/dc12r1-s1-h1-r2-u6i1-contract-reconciliation-2026-07-28`
  (recorded in the delivery response).
- GitNexus `analyze`/`status` after final commit: indexed commit == current
  commit, `Status: up-to-date`.

## R2 Verdict

`PASS_FOR_CTO_DC12R1_S1_H1_R2_INDEPENDENT_FULL_GATE`.
