# DC-12R1-S1-R5A Bootstrap Permission Source-of-Truth + Gate Reconciliation

Date: 2026-07-24

Branch: `opencode/dc12r1-s1-retailer-identity-provisioning-2026-07-23`

Base checkpoint preserved:
- Input base: `6a8ddcf348e9b1bdcc902929011e6212cc675cf8`
- R5 checkpoint commit: `f12887c8d30654a30f8c4f0d8ae953872532ca8e`
- R5 historical report remains a STOP checkpoint pending this R5A correction.

Verdict: `PASS_FOR_CTO_DC12R1_S1_R5A_MERGE_REVIEW`

## Scope

R5A introduced a single runtime permission source-of-truth and reconciled stale
bootstrap/RBAC test contracts. Migration 036 remains self-contained and does
not import runtime registry code.

Changed areas:
- Canonical runtime permission registry: `backend/core/permission_registry.py`
- Bootstrap/RBAC consumers: `backend/scripts/onboard_tenant.py`, `backend/scripts/create_wholesaler.py`, `backend/scripts/seed_test_tenant.py`, `backend/scripts/bootstrap_tenant_schema.py`
- Owner credential admin RBAC consumer: `backend/services/owner_credential_service.py`
- Focused permission/bootstrap/auth tests.

No migrations 001-035 changed. Migration 036 was not changed in R5A.

## Runtime Permission Contract

Canonical registry:
- `ADMIN_PERMISSIONS`: wholesaler/admin permissions, including `invitations:revoke` and `retailers:reissue_credential`.
- `RETAILER_OPERATOR_PERMISSIONS`: exactly six approved `client:*` permissions.
- Admin and retailer-operator permission sets are disjoint.

Consumers:
- `onboard_tenant.py` uses `ADMIN_PERMISSIONS` and `ADMIN_ROLE`.
- `create_wholesaler.py` seeds `ADMIN_PERMISSIONS` and grants only resolved `ADMIN_PERMISSION_CODES`.
- `seed_test_tenant.py` uses `ADMIN_PERMISSIONS`; `_seed_admin_rbac` now grants only explicitly supplied codes and fails closed on duplicate or unresolved requested codes.
- `bootstrap_tenant_schema.py` uses `RETAILER_OPERATOR_PERMISSIONS`, `ADMIN_MANAGEMENT_PERMISSIONS`, `RETAILER_OPERATOR_ROLE`, and `ADMIN_ROLE`.
- `owner_credential_service.py` aliases owner-admin RBAC to `ADMIN_PERMISSIONS`.

Migration parity:
- `tests/test_dc12r1_s1_r5a_permission_registry_parity.py` proves migration 036 does not import runtime registry code.
- The same test proves migration 036 constants match the runtime registry values.

## GitNexus Evidence

Before bootstrap/RBAC edits:
- `setup_admin` impact: LOW, impactedCount 1, direct caller `onboard_tenant`.
- `create_permissions` impact: LOW, impactedCount 3, direct caller `bootstrap_tenant`.
- `assign_all_permissions_to_admin` impact: LOW, impactedCount 3, direct caller `bootstrap_tenant`.
- `_seed_admin_rbac` impact: LOW, impactedCount 0.
- `_reconcile_rbac_s1` impact: LOW, impactedCount 25; affected modules primarily tests plus one business path.

Additional owner-admin RBAC symbol:
- `create_first_admin_rbac` context located direct callers in `test_u6i4_first_admin_rbac_creation.py` and `api/v1/auth.py::setup_credential`.
- `create_first_admin_rbac` impact: MEDIUM, impactedCount 6, affected process `setup_credential`, direct modules Tests and Services.

Final GitNexus commands are recorded below after the publication gate.

Pre-commit GitNexus detect_changes:
- Tool: `mcp__gitnexus.detect_changes(scope=all, repo=_dc12r1_s1_r5_preflight_2026-07-24)`
- Summary: `changed_count=257`, `affected_count=11`, `changed_files=15`, `risk_level=high`.
- Affected processes: `onboard_tenant` validation path and `setup_credential` owner credential paths.
- Classification: high aggregate risk is expected for a central RBAC registry reconciliation; covered by static route/permission parity tests, S1/R1/R2/R3/R4/R5 migration tests, and owner/auth/onboarding DB regressions below.

## RED/GREEN Evidence

R5 checkpoint preservation:
- R5 41-test suite rerun before checkpoint commit: `41 passed`.
- R5 checkpoint commit: `f12887c8d30654a30f8c4f0d8ae953872532ca8e`.

Fresh PostgreSQL 16 / Redis 7 final infrastructure:
- Disposable containers: PG16 and Redis7 on loopback-only ports.
- Alembic upgrade/current/heads: sole head/current `036_retailer_mvp_identity`.
- Initial Alembic run exposed a Windows console GBK `UnicodeEncodeError`; recreated the disposable DB and reran with UTF-8 output. Migration then completed successfully.

Actual Alembic rollback proof:
- Command: `pytest tests/test_dc12r1_s1_r5_migration_preflight_exact_catalog.py -q -s`
- Result: `41 passed`.
- Failure rollback fingerprint: `before=73e266a680eb99c0dda2c95d946cc726569f62a00f176d539192afb98a8761de`, `after_failure=73e266a680eb99c0dda2c95d946cc726569f62a00f176d539192afb98a8761de`.
- Repaired second-upgrade no-op fingerprint: `before=4a1d895bcf8ff073969c4350f4fdae21a0bdae9c90ce198cf2efd956d54d2caa`, `after_second_upgrade=4a1d895bcf8ff073969c4350f4fdae21a0bdae9c90ce198cf2efd956d54d2caa`.

Static permission/route gate:
- Command: `pytest tests/test_u1_bootstrap_permission_completeness.py tests/test_dc12r1_s1_r5a_permission_registry_parity.py tests/test_route_authorization_policy.py -q`
- Result: `48 passed`.

U1/U1-R1/U6F/U6H owner-bootstrap gate:
- Command: `pytest tests/test_u6f_onboarding_auth_chain_closeout.py tests/test_u6h2_tenant_provisioning_wholesaler_schema.py tests/test_u6h3_tenant_provisioning_reconcile_cleanup.py tests/test_u1r1_bootstrap_completeness.py tests/test_u6i1_owner_credential_setup_schema.py tests/test_u6i4_first_admin_rbac_creation.py tests/test_u6i5_owner_credential_setup_endpoint.py tests/test_u6i6_onboarding_e2e_closeout.py tests/test_u6l_email_verified_onboarding_orchestration.py -q`
- Result: `86 passed, 5 xfailed`.
- Classification: the five xfails are pre-existing U1-R1 platform diagnostic xfails, not added or modified by R5A. R5A did not add skip/xfail/deselection.

S1/R1/R2/R3/R4/R5/R5A migration and mapping bundle:
- Command: `pytest tests/test_dc12r1_s1_retailer_identity.py tests/test_dc12r1_s1_r1_corrections.py tests/test_dc12r1_s1_r2_strict_mapping.py tests/test_dc12r1_s1_r3_migration_contract.py tests/test_dc12r1_s1_r4_exact_catalog.py tests/test_dc12r1_s1_r5_migration_preflight_exact_catalog.py tests/test_dc12r1_s1_r5a_permission_registry_parity.py -q`
- Result: `90 passed`.

Auth, invitation, owner credential and route-policy regressions:
- Command: `pytest tests/test_auth_regressions.py tests/test_auth_bypass.py tests/test_test_mode_auth_bypass.py tests/test_u6d_verify_email_endpoint.py tests/test_u6e0_onboarding_status_token_schema.py tests/test_u6e_onboarding_status_endpoint.py tests/test_u6i0_owner_credential_setup_contract.py tests/test_u6i2_owner_credential_setup_token_issue.py tests/test_u6i3_owner_credential_setup_consume.py tests/test_u6i4_first_admin_rbac_creation.py tests/test_u6i5_owner_credential_setup_endpoint.py tests/test_u6i6_onboarding_e2e_closeout.py tests/test_u6l_email_verified_onboarding_orchestration.py tests/test_route_authorization_policy.py -q`
- Result: `137 passed`.

## Teardown / Cleanup Evidence

Test fixture cleanup:
- U6D/U6F/U6H/U6I/U6L fixtures remove created tenant schemas and public registry rows for their test namespaces.
- U1-R1 focused seed-helper regression drops its temporary tenant schema in `finally`.

Disposable infrastructure cleanup:
- `docker rm -f dc12r1_r5a_phase1_pg16 dc12r1_r5a_phase1_redis7 dc12r1_r5a_final_pg16 dc12r1_r5a_final_redis7`: removed.
- `docker network rm dc12r1_r5a_phase1_net dc12r1_r5a_final_net`: removed.
- `docker volume rm dc12r1_r5a_phase1_pgdata dc12r1_r5a_final_pgdata`: removed.
- Follow-up inventory for `dc12r1_r5a_*` containers, networks and volumes returned no entries.

## Hygiene / Publication Gate

Before commit:
- `py_compile`: passed.
- `git diff --check`: passed.
- Scoped `pre-commit`: passed.
- `detect-secrets-hook --baseline .secrets.baseline`: passed.
- `mcp__gitnexus.detect_changes(scope=all)`: completed; high aggregate risk classified above.

After final commit:
- `gitnexus analyze`
- `gitnexus status`
- clean worktree
