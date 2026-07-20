# DC-11T4A-H2 Full Backend Gate Report

Date: 2026-07-20
SHA: 6daa32bf3fd41b37ac53205b86764df757e2e4c7

## Environment
- PostgreSQL: 16.14
- Redis: 7.4.9
- Python: 3.12.3
- Poetry: 2.4.1

## Dependency Verification
- bcrypt: PASS (4.0.1)
- passlib: PASS (1.7.4)
- pip check: PASS (No broken requirements found)
- Alembic single head: PASS (034_platform_operators)
- Alembic upgrade head: PASS (all 34 migrations applied)

## Test Results
- Collected: 2801
- Passed: 2666
- Failed: 26
- Errors: 0
- Skipped: 94
- XFailed: 15

### Failed/Error Nodes

1. `tests/test_s6_2_materialized_views.py::test_mv_sales_daily_staleness_then_refresh`
2. `tests/test_s6_2_materialized_views.py::test_mv_sales_daily_has_unique_index`
3. `tests/test_s6_2_materialized_views.py::test_receivables_summary_is_realtime`
4. `tests/test_s6_2_materialized_views.py::test_mv_sales_daily_accessible_by_reporting_user`
5. `tests/test_s6_3_dashboard_api.py::test_query_builder_fetch_kpi_summary`
6. `tests/test_s6_3_dashboard_api.py::test_query_builder_fetch_all_receivables`
7. `tests/test_s6_3_dashboard_api.py::test_query_builder_fetch_time_series`
8. `tests/test_s6_3_dashboard_api.py::test_query_builder_empty_mv_returns_zeros`
9. `tests/test_s6_3_dashboard_api.py::test_query_builder_reporting_user_access`
10. `tests/test_s6_p_reporting_constraints.py::test_reporting_user_cannot_update`
11. `tests/test_s6_p_reporting_constraints.py::test_reporting_user_cannot_delete`
12. `tests/test_s6_p_reporting_constraints.py::test_reporting_user_can_select`
13. `tests/test_u6i5_owner_credential_setup_endpoint.py::test_no_query_string_token_support`
14. `tests/test_u6i6_onboarding_e2e_closeout.py::test_full_owner_onboarding_backend_chain_proves_hash_only_tokens_and_admin_rbac`
15. `tests/test_u6k_production_smtp_email_delivery.py::test_production_missing_smtp_config_returns_503_and_writes_no_rows`
16. `tests/test_u6k_production_smtp_email_delivery.py::test_production_smtp_success_creates_hash_only_registration_and_token`
17. `tests/test_u6k_production_smtp_email_delivery.py::test_production_smtp_send_failure_rolls_back_registration_and_token`
18. `tests/test_u6k_production_smtp_email_delivery.py::test_test_environment_still_uses_dev_sink_without_smtp`
19. `tests/test_u6k_production_smtp_email_delivery.py::test_duplicate_live_email_in_production_is_neutral_and_sends_no_extra_smtp`
20. `tests/test_u6l_email_verified_onboarding_orchestration.py::test_verify_email_provisions_tenant_issues_setup_token_and_sends_owner_email`
21. `tests/test_u6l_email_verified_onboarding_orchestration.py::test_emailed_setup_token_can_create_first_admin_rbac_and_status_is_public_active`
22. `tests/test_u6l_email_verified_onboarding_orchestration.py::test_repeated_internal_orchestration_does_not_duplicate_tenant_token_or_admin_rows`
23. `tests/test_u6l_email_verified_onboarding_orchestration.py::test_reused_verification_token_remains_neutral_and_does_not_duplicate_orchestration`
24. `tests/test_u6l_email_verified_onboarding_orchestration.py::test_production_missing_owner_setup_smtp_config_fails_closed`
25. `tests/test_u6l_email_verified_onboarding_orchestration.py::test_production_owner_setup_smtp_failure_fails_closed_with_retry_anchor`
26. `tests/test_u6l_email_verified_onboarding_orchestration.py::test_real_bootstrap_owner_setup_smtp_failure_persists_anchor_and_retry_reconciles`

## Verdict

STOP_AND_REPORT_CTO_WITH_EXACT_FAILED_ERROR_NODES
