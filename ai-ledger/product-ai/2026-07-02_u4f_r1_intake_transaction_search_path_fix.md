# U4-F-R1 Intake Transaction Search Path Fix

Date: 2026-07-02

Branch: `opencode/u4f-r1-intake-transaction-search-path-fix-2026-07-02`

Base: `origin/product-dev-recovered` at `c89d468`

Verdict: `PASS_FOR_CTO_REVIEW`

## U4-F Failure Summary

U4-F runtime browser proof reached Products -> Data Intake and rendered `/skus/intake`, but `POST /api/v1/intake/workspaces` returned HTTP 500 when the user clicked `Create workspace`.

The failure blocked the rest of the browser flow: upload, mapping, validation, rows preview, and issues preview could not be truthfully claimed.

## Root Cause

The U4 intake routes used tenant-scoped sessions where `SET LOCAL search_path` is active only for the current transaction. Four write endpoints also called `await db.commit()` inside the route:

- `create_workspace`
- `upload_intake_file`
- `update_intake_mapping`
- `validate_intake_workspace`

After a route-level commit, PostgreSQL reset the transaction-local `search_path`. Follow-up ORM operations such as `db.refresh(workspace)` then issued unqualified queries outside the tenant schema, causing `UndefinedTableError: relation "intake_workspaces" does not exist`.

Route-level commit was also wrong because tenant transaction ownership belongs to `finalize_tenant_context()` in authentication middleware. That middleware commits successful responses and rolls back failed responses. Committing inside a route bypassed the intended all-or-nothing request boundary and could leave partial intake rows if response construction failed after a flush or commit.

## Fix

Changed `backend/api/v1/intake.py` so U4 intake write endpoints no longer end the tenant transaction themselves.

- `create_workspace`: removed `db.commit()` and `db.refresh(workspace)`, added `db.flush()` so generated/default fields are available before building the response.
- `upload_intake_file`: removed route-level `db.commit()` and `db.refresh(upload)`; `IntakeService.create_upload_rows()` already flushes the upload, rows, and workspace status.
- `update_intake_mapping`: removed route-level `db.commit()` and `db.refresh(workspace)`; `IntakeService.apply_mapping()` already flushes mapped rows and workspace metadata/status.
- `validate_intake_workspace`: removed route-level `db.commit()` and `db.refresh(workspace)`; `IntakeService.validate_workspace()` already flushes validation issues and workspace status.

Responses are now built from in-memory ORM objects while the original tenant transaction and `search_path` are still valid. Final commit/rollback remains middleware-owned through `finalize_tenant_context()`.

## Tests Added Or Updated

- Added static contract test proving U4 intake routes do not call route-level `db.commit()` or `db.refresh()`.
- Added runtime-like ASGI rollback test that forces create response construction to fail after flush and proves no partial workspace row remains.
- Existing runtime-like ASGI create/list/detail tests now pass with the route transaction fix.
- Existing upload -> mapping -> validate test now also asserts SKU count is unchanged, proving no official SKU rows are written.

## GitNexus Impact

Before editing, ran GitNexus impact analysis for all four route handlers:

```text
npx gitnexus impact --repo s5d4b-r1-financial-atomicity-proof --direction upstream --depth 3 --include-tests create_workspace
npx gitnexus impact --repo s5d4b-r1-financial-atomicity-proof --direction upstream --depth 3 --include-tests upload_intake_file
npx gitnexus impact --repo s5d4b-r1-financial-atomicity-proof --direction upstream --depth 3 --include-tests update_intake_mapping
npx gitnexus impact --repo s5d4b-r1-financial-atomicity-proof --direction upstream --depth 3 --include-tests validate_intake_workspace
```

GitNexus reported zero upstream symbol callers for each FastAPI route handler and `LOW` symbol-level risk. Practical risk is assessed as `MEDIUM` because transaction ownership changed across four write endpoints and depends on middleware commit/rollback behavior.

## Validation

Focused transaction proof:

```text
poetry run pytest tests/test_u4c_intake_api_contract.py::test_contextual_tenant_user_with_intake_create_can_create_workspace tests/test_u4c_intake_api_contract.py::test_contextual_tenant_user_with_intake_read_can_list_and_detail_created_workspace tests/test_u4c_intake_api_contract.py::test_failed_create_after_flush_rolls_back_without_partial_workspace tests/test_u4d_intake_parser_preview.py::test_upload_mapping_validation_rows_and_issues_are_staging_only -q
4 passed, 11 warnings
```

Required U4 suite:

```text
poetry run pytest tests/test_u4c_intake_backend_schema.py tests/test_u4c_intake_api_contract.py tests/test_u4d_intake_parser_preview.py -q
33 passed, 13 warnings
```

Additional checks:

- `git diff --check`: passed
- `poetry run python -m py_compile api/v1/intake.py tests/test_u4c_intake_api_contract.py tests/test_u4d_intake_parser_preview.py`: passed
- `rg "await db\.(commit|refresh)\(" backend/api/v1/intake.py`: no matches
- diff secret pattern scan: passed

## Remaining Risks

- This branch was not deployed by design; runtime browser re-proof should be done in the next runtime validation branch or after CTO review.
- The fix relies on `AuthenticationMiddleware` continuing to call `finalize_tenant_context()` after the response is produced.
- Existing timestamp warnings from `datetime.utcnow()` remain out of scope.
