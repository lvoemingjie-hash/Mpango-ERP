# DC-12R1-S1-R5 Migration Preflight + Exact Catalog Evidence

## Verdict

**STOP_AND_REPORT_CTO**

The R5 migration preflight/catalog corrections were implemented in the
disposable worktree and the focused R5/S1 regression evidence was green, but the
requested broader bootstrap regression gate exposed failures that required
production bootstrap/reconciliation decisions outside the allowed R5 scope. At
the original R5 STOP point no commit or push was made; R5A preserves this report
as the historical checkpoint evidence.

## Branch And Baseline

- Branch: `opencode/dc12r1-s1-retailer-identity-provisioning-2026-07-23`
- Expected preflight remote tip: `6a8ddcf348e9b1bdcc902929011e6212cc675cf8`
- Verified `origin/product-dev-recovered`: `757aef26b116370a066076ad6a17284a4c6288b9`
- Verified ancestor: `78c40563` is an ancestor of R5 worktree HEAD
- Disposable worktree: `C:\Users\Jeff0\MPANGO ERP\_dc12r1_s1_r5_preflight_2026-07-24`

## Implemented But Not Committed

- `backend/alembic/versions/036_retailer_mvp_identity.py`
  - Validates pre-existing setup/reset token tables in the read-only preflight before migration mutations.
  - Treats inactive mapped users as existence evidence only; compares password hashes only for active mapped users.
  - Fails closed with `RETAILER_MAPPING_USER_MISSING` when a mapped user row is absent.
  - Validates exact token-table primary key, server defaults, public FK identity, FK column cardinality, referenced OID and `ON DELETE CASCADE`.
- `backend/tests/test_dc12r1_s1_r4_exact_catalog.py`
  - Removes the helper-only rollback proof and global async mark from synchronous catalog tests.
- `backend/tests/test_dc12r1_s1_r5_migration_preflight_exact_catalog.py`
  - Adds real DB tests for inactive mapped users, missing users, active hash conflicts and inactive placeholder hash non-conflict.
  - Adds setup/reset FK adversarial tests for non-public same-name target, composite FK, wrong referenced column, wrong target table, missing cascade and valid public FK.
  - Adds setup/reset PK/default adversarial tests for missing PK, composite PK, missing default and wrong default.
  - Adds actual Alembic 035-to-036 failure/rollback proof followed by repaired upgrade and second no-op upgrade.
- `ai-ledger/product-ai/2026-07-23_dc12r1_s1_retailer_identity_provisioning.md`
  - Corrects the R4 final-tip wording and replaces the false helper-level rollback wording with the R5 actual Alembic proof statement.

## GitNexus Evidence

- Pre-edit impact checks:
  - `upgrade`: LOW impact, 0 impacted symbols.
  - `_check_conflicting_active_hashes`: LOW impact, 2 impacted symbols, affected process `upgrade`.
  - `_assert_fk`: LOW impact, 5 impacted symbols.
  - `_validate_token_table_exact`: LOW impact, 5 impacted symbols, affected process `upgrade`.
  - No HIGH or CRITICAL impact was reported before editing.
- `detect_changes(scope=all)` before STOP report:
  - Risk: MEDIUM.
  - Affected processes: 3 upgrade/preflight processes.
- `detect_changes(scope=all)` after intent-to-add made new files visible:
  - Risk: MEDIUM.
  - Changed files detected by GitNexus: 5.
  - Affected processes: 3 upgrade/preflight processes.

## GREEN Evidence

- `poetry run python -m py_compile alembic/versions/036_retailer_mvp_identity.py tests/test_dc12r1_s1_r4_exact_catalog.py tests/test_dc12r1_s1_r5_migration_preflight_exact_catalog.py`
  - PASS.
- `poetry run pytest tests/test_dc12r1_s1_r5_migration_preflight_exact_catalog.py -q -s`
  - PASS: 41 passed, 6 warnings.
  - Rollback fingerprint: `before=ef1443440d6a20180a2ffe7ec84dc9e11cc7de44f5b2b0fa9f2e2d8f020be2f4`, `after_failure=ef1443440d6a20180a2ffe7ec84dc9e11cc7de44f5b2b0fa9f2e2d8f020be2f4`.
  - No-op fingerprint: `before=fb4f1592311500350cb5966bb0ea620c010b532cbb49b89661b4abe9835350d8`, `after_second_upgrade=fb4f1592311500350cb5966bb0ea620c010b532cbb49b89661b4abe9835350d8`.
- `poetry run pytest tests/test_dc12r1_s1_retailer_identity.py tests/test_dc12r1_s1_r1_corrections.py tests/test_dc12r1_s1_r2_strict_mapping.py tests/test_dc12r1_s1_r3_migration_contract.py tests/test_dc12r1_s1_r4_exact_catalog.py tests/test_dc12r1_s1_r5_migration_preflight_exact_catalog.py -q -s`
  - PASS: 86 passed, 17 warnings.
  - Rollback fingerprint: `before=5c276bfb4287dcf007ae399504f4c783e7dead57bf471d2d672feef36b711a6b`, `after_failure=5c276bfb4287dcf007ae399504f4c783e7dead57bf471d2d672feef36b711a6b`.
  - No-op fingerprint: `before=7db2a604407cf21b17730297ea599ff621e7f559a03c3e55c0ce86687dfcde72`, `after_second_upgrade=7db2a604407cf21b17730297ea599ff621e7f559a03c3e55c0ce86687dfcde72`.
- Applicable current S1/backend functional regressions:
  - Command covered owner credential functional tests, auth, route-policy, current invitation identity tests, order, payment, DC-11D concurrency/idempotency, DC-10L, DC-10K and Finance.
  - PASS: 286 passed, 22 skipped, 4 xfailed, 256 warnings.
- Alembic fresh PostgreSQL 16 proof:
  - First `alembic upgrade head`: reached `036_retailer_mvp_identity`.
  - Second `alembic upgrade head`: no-op.
  - `alembic current`: `036_retailer_mvp_identity (head)`.
  - `alembic heads`: sole head `036_retailer_mvp_identity (head)`.
- Frontend retailer credential proof:
  - `pnpm exec vitest run src/tests/RetailerCredentialPages.test.tsx`: PASS, 9 passed.
  - `pnpm build`: PASS.
- Hygiene:
  - `git diff --check`: PASS.
  - Mojibake scan of touched files: PASS.
  - Scoped `pre-commit run --files ...`: PASS.
  - `detect-secrets-hook --baseline .secrets.baseline ...`: PASS.

## RED Evidence Requiring CTO Decision

The following suites were run because the task requested broad bootstrap and
owner/onboarding regression evidence. They failed on expectations that require
production bootstrap/reconciliation or legacy test-contract decisions outside R5.

- Broad owner/invitation/order/payment/Finance bundle:
  - Result: 2 failed, 276 passed, 22 skipped, 4 xfailed, 8 errors.
  - Connection errors were reproduced as a bundle-level PostgreSQL client saturation artifact and `test_order_creation.py` passed when rerun separately.
  - Persistent non-connection failures were stale branch-scope/head checks in `test_u6i1_owner_credential_setup_schema.py`.
- `tests/test_u6f_onboarding_auth_chain_closeout.py` rerun with `tests/test_order_creation.py`:
  - Result: 4 failed, 4 passed for U6F; order creation passed.
  - Stale expectations: tenant provisioning creates zero role rows, public allowlist excludes new retailer credential routes, and Alembic head remains 035.
- Migration/bootstrap broad bundle:
  - Result: 10 failed, 105 passed, 3 skipped, 5 xfailed.
  - Stale expectations: U6H tenant provisioning/reconcile tests expect no tenant role/RBAC rows, but S1 migration/bootstrap intentionally ensures `retailer_operator` RBAC.
  - Static diff guards compare the cumulative S1 branch against `origin/product-dev-recovered` and fail on already-approved S1 product files, not on the R5 delta.
  - Potential production bootstrap defect: `test_u1_bootstrap_permission_completeness.py` reports `onboard_tenant.py` and `seed_test_tenant.py` missing `invitations:revoke` and `retailers:reissue_credential` while `create_wholesaler.py` contains them.
  - Potential production bootstrap contract drift: `test_u1r1_bootstrap_completeness.py` reports admin has unexpected client permissions plus `invitations:revoke` and `retailers:reissue_credential`.

Because fixing or deciding these failures requires production bootstrap or
legacy regression-contract changes, R5 stops under the hard rule forbidding
production bootstrap/reconciliation changes.

## Cleanup

- Removed disposable containers: `dc12r1_r5_pg16`, `dc12r1_r5_redis7`.
- Removed disposable volume: `dc12r1_r5_pgdata`.
- Removed disposable network: `dc12r1_r5_net`.
- Removed frontend install/build artifacts: `frontend/node_modules`, `frontend/dist`.
- Remaining disposable worktree is intentionally preserved with uncommitted STOP evidence for review.

## Original R5 STOP Publication Status

- R5 implementation commit at original STOP point: not created before R5A.
- R5 report-publication commit at original STOP point: not created before R5A.
- Remote push at original STOP point: not performed.
- Protected branches and tags: untouched.
