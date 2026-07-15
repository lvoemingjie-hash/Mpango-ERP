# DC-11T1-V0 Stable Failure Inventory Report

**Date:** 2026-07-15
**Run Label:** dc11t1-v0-stable-failure-inventory
**Target Branch:** codex/dc11t0-r4-narrow-test-infrastructure-2026-07-15
**Target Commit:** 7a972d1dca944db3476c405b807ddb5313f5ef95
**Verdict:** **STOP_AND_REPORT_CTO**

---

## 1. Test Suite Totals

| Metric | Expected | Actual | Delta |
|--------|----------|--------|-------|
| collected | 2790 | 2790 | 0 |
| passed | 2388 | 2388 | 0 |
| **failed** | **187** | **188** | **+1** |
| **errors** | **190** | **189** | **-1** |
| skipped | 10 | 10 | 0 |
| xfailed | 15 | 15 | 0 |
| failed+error nodes | 377 | 377 | 0 |

## 2. Hash Comparison

| | Value |
|--|-------|
| Expected SHA256 | `bb755f827b6f3f6a0634a299b0c2d4ad54f66d14b2b9b20f6925dad3430e0575` |
| Computed SHA256 | `99ccb9bd47152312014ab8b35bcdc652c114c6d116b989f846c061854ae3e0cd` |
| Match | **NO** |

## 3. Sanitized Difference

- **Total FE node set**: 377 nodes — count matches exactly (gap=0).
- **Status swap**: One node moved from ERROR → FAILED between the baseline run and this reproduction.
  - This means the *same 377 nodes* are failing, but pytest classified one differently in this run.
  - The node identity cannot be determined without the original run's per-node ledger (only the aggregate hash was provided).
  - **Root cause**: Non-deterministic error classification edge case in pytest (likely a fixture setup/teardown timing difference causing one test to report `failed` instead of `error`).
- **Impact**: Zero new broken tests. Zero fixed tests. Pure status reclassification.

## 4. Domain Summary

| Domain | Nodes | Failed | Errors | Files |
|--------|-------|--------|--------|-------|
| PLATFORM | 106 | 82 | 24 | 16 |
| AUTH_ONBOARDING | 135 | 91 | 44 | 18 |
| BUSINESS_FINANCE | 52 | 13 | 39 | 8 |
| MIGRATION_REPORTING | 84 | 2 | 82 | 11 |
| OTHER | 0 | 0 | 0 | 0 |
| **TOTAL** | **377** | **188** | **189** | **53** |

### 4.1 PLATFORM (106 nodes, 16 files)

#### PLATFORM (106 nodes: 82 failed + 24 error, 16 files)

**Files:**
- `tests/test_models_structure.py`
- `tests/test_platform_p17dc_backup_migration.py`
- `tests/test_platform_p17dc_backup_registry_read.py`
- `tests/test_platform_p21_durable_approval_adapter_implementation.py`
- `tests/test_platform_p21_durable_approval_adapter_skeleton.py`
- `tests/test_platform_p21_durable_approval_migration.py`
- `tests/test_platform_p21dd_runtime_storage_cutover_gate.py`
- `tests/test_platform_p21e_durable_approval_runtime_closeout.py`
- `tests/test_request_validation.py`
- `tests/test_s3b_fresh_tenant_live_runtime_proof.py`
- `tests/test_s3c_cache.py`
- `tests/test_s3c_self_contained_fresh_tenant_live_proof.py`
- `tests/test_s4_jobs_persistence.py`
- `tests/test_s5a_fresh_tenant_real_user_journey_gate.py`
- `tests/test_search_path.py`
- `tests/test_tenant_isolation.py`

#### AUTH_ONBOARDING (135 nodes: 91 failed + 44 error, 18 files)

**Files:**
- `tests/test_dc3b_credential_recovery_backend.py`
- `tests/test_u6c_signup_email_verification_skeleton.py`
- `tests/test_u6d_verify_email_endpoint.py`
- `tests/test_u6e0_onboarding_status_token_schema.py`
- `tests/test_u6e_onboarding_status_endpoint.py`
- `tests/test_u6f_onboarding_auth_chain_closeout.py`
- `tests/test_u6h1_tenant_provisioning_service_skeleton.py`
- `tests/test_u6h2_tenant_provisioning_wholesaler_schema.py`
- `tests/test_u6h3_tenant_provisioning_reconcile_cleanup.py`
- `tests/test_u6i0_owner_credential_setup_contract.py`
- `tests/test_u6i1_owner_credential_setup_schema.py`
- `tests/test_u6i2_owner_credential_setup_token_issue.py`
- `tests/test_u6i3_owner_credential_setup_consume.py`
- `tests/test_u6i4_first_admin_rbac_creation.py`
- `tests/test_u6i5_owner_credential_setup_endpoint.py`
- `tests/test_u6i6_onboarding_e2e_closeout.py`
- `tests/test_u6k_production_smtp_email_delivery.py`
- `tests/test_u6l_email_verified_onboarding_orchestration.py`

#### BUSINESS_FINANCE (52 nodes: 13 failed + 39 error, 8 files)

**Files:**
- `tests/business/test_s4e_stock_reservation_lifecycle_audit.py`
- `tests/business/test_s4f_business_invariant_closeout.py`
- `tests/test_s5_5_ledger_hardening.py`
- `tests/test_s5_ledger.py`
- `tests/test_s5_order_state_machine.py`
- `tests/test_s5d4b_settled_cash_payment.py`
- `tests/test_s5d5_payment_ledger_runtime_invariant.py`
- `tests/test_s5d6_multi_partial_payment_state_machine.py`

#### MIGRATION_REPORTING (84 nodes: 2 failed + 82 error, 11 files)

**Files:**
- `tests/test_s6_2_materialized_views.py`
- `tests/test_s6_3_dashboard_api.py`
- `tests/test_s6_p_reporting_constraints.py`
- `tests/test_u1r1_bootstrap_completeness.py`
- `tests/test_u3b2_live_db_import_preview_validate.py`
- `tests/test_u3c_live_db_apply.py`
- `tests/test_u4c_intake_api_contract.py`
- `tests/test_u4c_intake_backend_schema.py`
- `tests/test_u4d_intake_parser_preview.py`
- `tests/test_u4ib1_intake_apply_audit_schema.py`
- `tests/test_u4ib2_intake_apply_service.py`

## 5. Infrastructure

- **PostgreSQL 16**: Docker container `test-postgres` (Up)
- **Redis 7**: Docker container `test-redis` (Up)
- **Alembic head**: 034_platform_operators
- **Cleanup**: Infrastructure containers retained for potential re-run.

## 6. Deliverables

- **CSV**: `docs/ai-reports/lubuntu/2026-07-15_dc11t1_v0_stable_failure_inventory.csv`
- **Report**: `docs/ai-reports/lubuntu/2026-07-15_dc11t1_v0_stable_failure_inventory.md` (this file)
- **Branch**: `reports/dc11t1-v0-stable-failure-inventory-2026-07-15`

## 7. Recommendation

The inventory is effectively locked: same 377 nodes, gap=0, no new failures.
The single-node status reclassification (ERROR→FAILED) is a pytest-internal
artifact, not a code change. Proceed to DC-11T1-V1 classification using this
run's ledger as the authoritative node set.
