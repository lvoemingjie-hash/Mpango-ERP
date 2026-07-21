# DC-11T4A-H2-R1A Reporting Failure Classification

Date: 2026-07-21
Target SHA: `6daa32bf3fd41b37ac53205b86764df757e2e4c7`
Branch: `reports/dc11t4a-h2-r1a-reporting-classification-2026-07-20`

## Verdict

`PASS_DC11T4A_H2_R1A_CLASSIFICATION_COMPLETE`

No `CURRENT_PRODUCT_DEFECT` was found. No CTO stop condition was triggered.

## Environment

- PostgreSQL: `16.14`
- Redis: `7.4.9`
- Python: `3.12.3`
- Poetry: `2.4.1`

## Execution Contract

The run followed the requested constraints:

1. Fresh disposable PostgreSQL 16 / Redis 7 infrastructure.
2. Full Alembic chain executed to `034_platform_operators`.
3. No manual DDL, `create_all`, bootstrap repair, or schema reconciliation before assertions.
4. Three file-isolated pytest processes on fresh DB A.
5. Same three file-isolated pytest processes on fresh DB B.
6. One grouped pytest process in H2 file order on fresh DB C.
7. One grouped pytest process in reverse file order on fresh DB D.

## Scenario Results

| Scenario | Fresh DB | Pytest processes | Result |
|---|---:|---:|---|
| `individual_a` | 1 | 3 | `4 + 5 + 3 = 12` failures |
| `individual_b` | 1 | 3 | `4 + 5 + 3 = 12` failures |
| `group_h2` | 1 | 1 | `12 / 40` failures |
| `group_reverse` | 1 | 1 | `12 / 40` failures |

Stability observations:

- Exact same 12 nodes failed in every scenario.
- No extra failing nodes appeared in grouped or reverse order.
- No target node disappeared in any scenario.
- Order sensitivity: none observed.

## Alembic Evidence

Fresh-db Alembic logs were deterministic:

- migration `011_s6_p_reporting_role`: `Granted SELECT on 0 tenant schema(s) + public`
- migration `012_s6_1_read_models`: `Read Models created in 0 tenant schema(s)`
- migration `013_s6_2_materialize_sales`: `Materialized 0 tenant schema(s)`
- current revision after upgrade: `034_platform_operators (head)`

This matches the target SHA behavior: public migration to head completed successfully, but no tenant schema existed at migration time, so no tenant reporting objects were created.

## Classification Summary

| Class | Count |
|---|---:|
| `TEST_INFRASTRUCTURE` | 0 |
| `STALE_TEST_CONTRACT` | 12 |
| `CURRENT_PRODUCT_DEFECT` | 0 |
| `ENVIRONMENT_GATED` | 0 |

Accounting: `12 / 12`, gap=`0`

## Node Classification

| Node | Observed exception class | Sanitized root cause | Classification |
|---|---|---|---|
| `tests/test_s6_2_materialized_views.py::test_mv_sales_daily_staleness_then_refresh` | `sqlalchemy.exc.ProgrammingError` | `t_test.mv_sales_daily` does not exist | `STALE_TEST_CONTRACT` |
| `tests/test_s6_2_materialized_views.py::test_mv_sales_daily_has_unique_index` | `AssertionError` | expected unique index `idx_mv_sales_daily_u1`, found none because `t_test.mv_sales_daily` was never created | `STALE_TEST_CONTRACT` |
| `tests/test_s6_2_materialized_views.py::test_receivables_summary_is_realtime` | `sqlalchemy.exc.ProgrammingError` | `t_test.rpt_receivables_summary` does not exist | `STALE_TEST_CONTRACT` |
| `tests/test_s6_2_materialized_views.py::test_mv_sales_daily_accessible_by_reporting_user` | `sqlalchemy.exc.ProgrammingError` | `t_test.mv_sales_daily` does not exist for `reporting_user` either | `STALE_TEST_CONTRACT` |
| `tests/test_s6_3_dashboard_api.py::test_query_builder_fetch_kpi_summary` | `sqlalchemy.exc.ProgrammingError` | query builder resolves to `mv_sales_daily`, but `t_test.mv_sales_daily` does not exist | `STALE_TEST_CONTRACT` |
| `tests/test_s6_3_dashboard_api.py::test_query_builder_fetch_all_receivables` | `sqlalchemy.exc.ProgrammingError` | query builder resolves to `rpt_receivables_summary`, but `t_test.rpt_receivables_summary` does not exist | `STALE_TEST_CONTRACT` |
| `tests/test_s6_3_dashboard_api.py::test_query_builder_fetch_time_series` | `sqlalchemy.exc.ProgrammingError` | query builder resolves to `rpt_cash_flow_daily`, but `t_test.rpt_cash_flow_daily` does not exist | `STALE_TEST_CONTRACT` |
| `tests/test_s6_3_dashboard_api.py::test_query_builder_empty_mv_returns_zeros` | `sqlalchemy.exc.ProgrammingError` | graceful-empty-path never executes because `t_test.mv_sales_daily` does not exist | `STALE_TEST_CONTRACT` |
| `tests/test_s6_3_dashboard_api.py::test_query_builder_reporting_user_access` | `sqlalchemy.exc.ProgrammingError` | reporting-user path still targets missing `t_test.rpt_receivables_summary` | `STALE_TEST_CONTRACT` |
| `tests/test_s6_p_reporting_constraints.py::test_reporting_user_cannot_update` | `AssertionError` | test expected permission/read-only denial, but actual failure is missing `t_test.ledger_entries` | `STALE_TEST_CONTRACT` |
| `tests/test_s6_p_reporting_constraints.py::test_reporting_user_cannot_delete` | `AssertionError` | test expected permission/read-only denial, but actual failure is missing `t_test.ledger_entries` | `STALE_TEST_CONTRACT` |
| `tests/test_s6_p_reporting_constraints.py::test_reporting_user_can_select` | `sqlalchemy.exc.ProgrammingError` | `t_test.ledger_entries` does not exist for the reporting session | `STALE_TEST_CONTRACT` |

## Why These Are `STALE_TEST_CONTRACT`

The failures do not indicate broken fresh infrastructure:

- PostgreSQL 16 and Redis 7 were healthy.
- Alembic upgraded cleanly to head `034`.
- `reporting_user` existed and role-level timeout behavior worked.
- `test_reporting_user_cannot_insert`, `test_reporting_query_timeout`, `test_reporting_role_has_timeout`, and `test_reporting_user_can_read_public_tables` all passed.

The failures also do not indicate a current product defect in the supported tenant lifecycle:

- `backend/alembic/versions/011_s6_p_reporting_role.py` grants reporting access only to tenant schemas that already exist at migration time.
- `backend/alembic/versions/012_s6_1_read_models.py` and `013_s6_2_materialize_sales.py` create reporting objects only in tenant schemas discovered at migration time.
- `backend/tests/conftest.py` bootstraps `t_test` after migrations using `_bootstrap_tenant_test_schema(...)`, but that helper does not reconcile reporting views/materialized views or reporting grants.
- The current canonical product path is `backend/docker-entrypoint.sh` -> `backend/scripts/bootstrap_tenant_schema.py`, and `_reconcile_reporting(...)` there explicitly creates:
  - `rpt_receivables_summary`
  - `rpt_cash_flow_daily`
  - `mv_sales_daily`
  - `idx_mv_sales_daily_u1`
  - reporting-role grants for post-migration tenant schemas
- `docs/contracts/database_contract.md` requires tenant provisioning via `CREATE SCHEMA` plus `alembic upgrade head -x tenant_schema=<schema>`.
- `docs/contracts/tenant_onboarding_provisioning_contract.md` requires tenant schemas to be created/reconciled through the canonical `bootstrap_tenant_schema.py` path or an equivalent production wrapper.

So the product contract at this SHA is: public-head migration alone is not sufficient for a tenant schema that appears later. The reporting tests still assume that unsupported `t_test` bootstrap path should already contain reporting objects and reporting grants. That assumption is stale.

## Per-File Notes

### `tests/test_s6_2_materialized_views.py`

All four failing nodes depend on reporting objects that are absent from `t_test`. The one passing node, `test_advisory_lock_prevents_double_refresh`, does not depend on those objects and therefore confirms the test session itself is healthy.

### `tests/test_s6_3_dashboard_api.py`

All five failing nodes are integration tests that execute real SQL against reporting models. The semantic-layer, whitelist, and Pydantic tests all passed, which isolates the failure surface to missing tenant reporting objects rather than query-builder logic.

### `tests/test_s6_p_reporting_constraints.py`

The reporting role itself is present and partially validated:

- `cannot_insert`: passed
- `query_timeout`: passed
- `role_has_timeout`: passed
- `can_read_public_tables`: passed

The three failing nodes all assume `t_test.ledger_entries` exists for the reporting path. On this run it does not, because no tenant bootstrap/reconcile was performed before assertions.

## Final Classification

All 12 H2 reporting nodes are reproducible `STALE_TEST_CONTRACT` failures against an unsupported test bootstrap path. There is no evidence in this run of:

- broken infrastructure,
- environment gating,
- or a current product defect in the supported tenant bootstrap/provisioning contract.
