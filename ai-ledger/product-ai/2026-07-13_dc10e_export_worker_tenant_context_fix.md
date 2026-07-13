# 2026-07-13 DC-10E Export Worker Tenant Context Reconstruction Fix

## Scope

- Branch: `opencode/dc10e-export-worker-tenant-context-reconstruction-2026-07-13`
- Base commit: `547b0b294aa387d6179f53eca3ec162532a1e29e`
- Verdict entering task: `CONFIRMED_P1_PRODUCT_DEFECT`
- Allowed code path changed: `backend/jobs/export_jobs.py`
- New regression tests: `backend/tests/test_dc10e_export_worker_tenant_context.py`
- Out of scope: frontend, migrations, permissions, deployment, protected branches, release tags

## Exact Root Cause

`POST /exports` correctly serializes `tenant_id` and `tenant_schema` into `ExportJobPayload`. `export_report_worker` deserializes and validates that payload, and passes both values into `SemanticQueryBuilder`. However, the worker opened `ReportingSessionLocal()` without restoring the tenant context into `session.info`.

`SemanticQueryBuilder._ensure_tenant_scope()` correctly preserved `SET LOCAL search_path`, but the following ORM statement execution passed through the global tenant filter. Because `session.info["tenant_schema"]` was absent, `db.tenant_filter._require_tenant_context()` raised `TenantContextMissingError("Tenant context required")`.

## Minimal Fix

Inside `export_report_worker`, immediately after opening the reporting session and before constructing/executing the query:

```python
session.info["tenant_id"] = job_payload.tenant_id
session.info["tenant_schema"] = job_payload.tenant_schema
```

No global tenant-filter bypass was added. `SemanticQueryBuilder._ensure_tenant_scope()` and its `SET LOCAL search_path` enforcement remain unchanged. Reporting uses the existing read-only reporting connection.

## GitNexus Pre-Edit Impact

GitNexus index had to be refreshed for the new worktree. Initial `--repo Mpango-ERP` impact attempts failed with an index storage-version mismatch, so `npx gitnexus analyze` was run and the new indexed repo name `dc10e-export-worker-tenant-context` was used.

- `export_report_worker`: LOW impact, 3 direct test callers, 0 affected processes.
- `_ensure_tenant_scope`: HIGH impact, 19 impacted, 4 affected dashboard/reporting processes: `get_kpi_summary`, `get_sales_trend`, `get_cash_flow_trend`, `analyze_report`.
- `SemanticQueryBuilder`: HIGH impact, 46 impacted, direct export worker/dashboard/query-builder tests and 4 affected dashboard/reporting processes.
- `ReportingSessionLocal`: not directly indexed as a variable by GitNexus. Fallback file-level impact on `backend/database/reporting_session.py`: MEDIUM, 33 impacted; direct imports include `backend/jobs/export_jobs.py`, `backend/api/v1/dashboards.py`, `backend/tests/conftest.py`, and reporting constraint tests.
- No CRITICAL impact reported.

## RED Proof

Command:

```powershell
poetry run pytest tests/test_dc10e_export_worker_tenant_context.py -q
```

Before the fix, the new real-session regression suite failed as expected:

- `test_red_worker_without_session_info_hits_real_tenant_filter`: failed with `db.tenant_filter.TenantContextMissingError: Tenant context required` from `db/tenant_filter.py:133` during `session.execute(stmt)` in `jobs/export_jobs.py`.
- `test_worker_sets_tenant_context_before_first_sql`: failed with `KeyError: 'tenant_id'` before first fake SQL execute.
- Valid export, tenant isolation, and retry tests also failed with the same missing tenant context.

Result: `5 failed, 3 passed`.

## GREEN Proof

Command:

```powershell
poetry run pytest tests/test_dc10e_export_worker_tenant_context.py -q
```

After the fix:

- Real PostgreSQL reporting session export completed.
- Worker restored `tenant_id` and `tenant_schema` before first SQL.
- Valid tenant export created CSV and metadata.
- Status and download handlers completed using generated metadata.
- Tenant A export did not include Tenant B rows.
- Missing/invalid tenant context still failed closed.
- Retry executed twice without losing tenant context.
- Static guard confirmed no `run_as_system`, `ignore_tenant`, or `mark_session_as_system` in `backend/jobs/export_jobs.py`.
- Metadata scan confirmed no raw DB URL, authorization bearer value, or sensitive SQL text in export metadata.

Result: `8 passed`.

## Validation

- `poetry run pytest tests/test_dc10e_export_worker_tenant_context.py -q`: `8 passed`.
- `poetry run pytest tests/test_s6_4_async_exports.py -q`: `38 passed`.
- `poetry run pytest tests/test_route_authorization_policy.py -q`: `35 passed`, 1 existing SQLAlchemy deprecation warning.
- `poetry run python -m py_compile jobs/export_jobs.py tests/test_dc10e_export_worker_tenant_context.py`: passed.
- `git diff --check`: clean except LF-to-CRLF warnings.
- ASCII scan on changed code/test files: clean after normalizing pre-existing Unicode punctuation in touched `backend/jobs/export_jobs.py` comments/docstring.
- Mojibake scan on changed code/test files: clean.
- Secret-pattern scan on changed code/test files: expected test references only (`TokenPayload`, `redacted-test-token`, literal negative assertions for `postgresql://`, `Authorization`, `Bearer`); no real secrets.
- Scoped pre-commit on changed files: passed, including detect-secrets.
- `npx gitnexus augment "backend/jobs/export_jobs.py backend/tests/test_dc10e_export_worker_tenant_context.py"`: completed with no output from the available CLI fallback for staged change detection.
- `npx gitnexus analyze`: already up to date.
- `npx gitnexus status`: up to date at `547b0b2`.

### Required S6 Reporting Validation Caveat

Command:

```powershell
poetry run pytest tests/test_s6_2_materialized_views.py tests/test_s6_3_dashboard_api.py -q
```

Initial run on a fresh isolated DB failed 9 nodes because the DB had no pre-existing `t_test` reporting assets and direct reporting-user checks could not authenticate. After preparing `t_test` reporting assets in the isolated DB, rerun result was `30 passed, 2 failed`.

Remaining failed nodes:

- `tests/test_s6_2_materialized_views.py::test_mv_sales_daily_accessible_by_reporting_user`
- `tests/test_s6_3_dashboard_api.py::test_query_builder_reporting_user_access`

Classification: `TEST_INFRA_DRIFT`.

Reason: both tests construct their own reporting-user URL as `postgresql+asyncpg://reporting_user:{password}@{POSTGRES_HOST}:5432/mpango_erp`, ignoring `POSTGRES_PORT`. DC-10E isolated PostgreSQL runs on `127.0.0.1:55433` to avoid shared containers, so these two tests connect to the unrelated host service on `5432` and fail authentication. The other 30 S6 reporting/dashboard tests passed against the isolated DB after expected test assets were present.

## No Bypass Confirmation

The fix does not use or introduce:

- `run_as_system`
- `ignore_tenant`
- `mark_session_as_system`
- Any tenant-filter bypass
- Any weakening of tenant/schema validation
- Any migration or frontend change

`SemanticQueryBuilder._ensure_tenant_scope()` remains unchanged and still performs `SET LOCAL search_path TO "{tenant_schema}", public` before query execution.

## Changed Files

- `backend/jobs/export_jobs.py`
- `backend/tests/test_dc10e_export_worker_tenant_context.py`
- `ai-ledger/product-ai/2026-07-13_dc10e_export_worker_tenant_context_fix.md`

## Verdict

DC-10E product defect is fixed and covered by RED/GREEN tests. Final release-gate status has a `TEST_INFRA_DRIFT` caveat for two required S6 reporting tests that hardcode port 5432 and cannot target the isolated Docker PostgreSQL port.

Recommended CTO disposition: `PASS_FOR_CTO_DC10E_REVIEW_WITH_TEST_INFRA_DRIFT_CAVEAT`.
