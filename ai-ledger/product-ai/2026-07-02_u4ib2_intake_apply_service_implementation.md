# U4-I-B2 Intake Apply Service Implementation

Date: 2026-07-02

Branch: `opencode/u4ib2-intake-apply-service-implementation-2026-07-02`

Base: `origin/product-dev-recovered` at `9aafd12`

Verdict: `PASS_FOR_CTO_U4IB2_REVIEW`

## Scope

Implemented backend-only staged intake rows -> official SKU apply capability.

Included:

- New isolated apply helper: `backend/services/intake_apply_service.py`
- New backend endpoint: `POST /api/v1/intake/workspaces/{workspace_id}/apply`
- Response schema: `IntakeApplyRead`
- Focused service/API contract tests: `backend/tests/test_u4ib2_intake_apply_service.py`
- Existing U4 route contract update for the new endpoint and permission requirement

Explicitly not included:

- No frontend
- No deploy
- No public token/external onboarding
- No image/PWA/mobile scan work
- No migration beyond U4-I-B1
- No SKU model edit
- No `apply_import` or `ImportService.apply` edit
- No `product-dev-recovered` push

## Design

The apply implementation is isolated from U4-C/D staging code in `IntakeApplyService`. This preserves the existing staging guard that `backend/services/intake_service.py` remains SKU-write-free.

The route uses `RequireAllPermissions("intake:update", "skus:import")`, so neither `intake:create`, `intake:read`, `intake:update` alone, nor `skus:import` alone can apply.

The service locks the target workspace and staged rows with `FOR UPDATE` inside the request transaction, then performs all preflight checks before creating any SKU:

- Workspace exists for the tenant context
- `workspace.status == READY_FOR_EXPORT`
- `workspace.apply_status == not_applied`
- No blocking validation issue exists
- Staged rows exist
- Every row has required SKU fields (`sku_code`, `name`), matching the existing import apply required-field contract
- No duplicate staged `sku_code`
- No staged `sku_code` already exists in official tenant `skus`

SKU creation uses the existing `SKURepository.create` interface. The SKU model file was not edited. The existing U3 `ImportService.apply` path was not called or edited because its GitNexus impact is CRITICAL and it has separate import-run semantics.

## Duplicate Policy

MVP duplicate behavior is fail closed.

- Duplicate staged SKU code returns `409 DUPLICATE_STAGED_SKU_CODE` before any SKU write.
- Existing official SKU code returns `409 SKU_CODE_EXISTS` before any SKU write.
- No overwrite, upsert, merge, or skip mode exists in U4-I-B2.

## Atomicity And Rollback

The service does not commit. It relies on the existing middleware-owned tenant transaction lifecycle from U4-F-R1.

Success path:

- All official SKUs are created.
- Workspace audit is marked applied.
- Row audit fields are updated.
- Middleware commits the request transaction.

Failure path:

- Preflight failures raise HTTP errors before SKU writes.
- Runtime failures after a SKU flush are rolled back by middleware.
- The branch documents rollback behavior rather than persisting `failed` audit state on HTTP failure, because persisted failure audit would require a separate transaction and would weaken the all-or-none proof.

The mid-apply failure test monkeypatches the SKU repository to flush one SKU and then raise. The API returns 500, and the test proves no official SKU, workspace apply audit, or row apply audit was committed.

## Idempotency

First successful apply creates official SKUs and marks the workspace `applied`.

Repeated apply returns `409 ALREADY_APPLIED` and creates no additional SKUs. This is covered by `test_repeated_apply_returns_already_applied_without_duplicate_skus`.

## Audit

On success:

- `intake_workspaces.apply_status = 'applied'`
- `intake_workspaces.applied_at` is set
- `intake_workspaces.applied_by` is set from the authenticated user
- `intake_workspaces.apply_result.created_count` is set
- `intake_workspaces.apply_result.row_count` is set
- `intake_workspaces.apply_result.created_sku_ids` is set
- Each row gets `apply_status = 'applied'`
- Each row gets `target_sku_id`
- Row apply error fields are cleared

On failure:

- The request transaction rolls back.
- No partial official SKUs are committed.
- Workspace/row audit fields do not claim applied state.

## GitNexus Impact

Pre-edit required checks:

- `IntakeService`: `MEDIUM`
- `IntakeWorkspace`: `LOW`
- `IntakeProductRow`: `LOW`
- `SKU`: `HIGH`, with `apply_import` affected through existing flows
- `create_sku`: `LOW`
- `SKURepository`: `LOW`
- `apply_import`: `LOW`
- `ImportService.apply`: `CRITICAL`

Decision:

- Do not edit `models/sku.py`.
- Do not edit or call `ImportService.apply` or `apply_import`.
- Use an isolated U4-I-B2 service and the existing `SKURepository.create` boundary.

Post-edit checks after `npx gitnexus analyze`:

- `IntakeApplyService`: `LOW`
- `apply_workspace`: `LOW`
- `apply_intake_workspace`: `LOW`
- `npx gitnexus status`: up to date on `9aafd12`

## Tests

Added `backend/tests/test_u4ib2_intake_apply_service.py` covering:

- Missing `intake:update` fails
- Missing `skus:import` fails
- Successful apply creates expected SKUs
- Success updates workspace and row audit fields
- Duplicate staged SKU code fails before any SKU write
- Existing official SKU code fails before any SKU write
- Blocking validation issue fails
- Workspace not `READY_FOR_EXPORT` fails
- Repeated apply returns `ALREADY_APPLIED` and does not duplicate SKUs
- Simulated mid-apply failure rolls back SKU writes and audit changes
- Tenant isolation blocks applying another tenant workspace
- Missing required row fields fail before any SKU write

Updated `backend/tests/test_u4c_intake_api_contract.py` to assert the new route is registered and requires both permissions.

## Validation

Initial red check:

```text
poetry run pytest tests/test_u4ib2_intake_apply_service.py::test_apply_requires_intake_update -q
failed with 404 before endpoint implementation
```

New U4-I-B2 tests:

```text
poetry run pytest tests/test_u4ib2_intake_apply_service.py -q
11 passed
```

Required regression suite plus U4-I-B2:

```text
poetry run pytest tests/test_u4ib2_intake_apply_service.py tests/test_u4c_intake_backend_schema.py tests/test_u4c_intake_api_contract.py tests/test_u4d_intake_parser_preview.py tests/test_u4ib1_intake_apply_audit_schema.py -q
48 passed, 15 warnings
```

Static checks:

```text
git diff --check
passed

poetry run python -m py_compile api/v1/intake.py schemas/intake.py services/intake_service.py services/intake_apply_service.py tests/test_u4c_intake_api_contract.py tests/test_u4ib2_intake_apply_service.py
passed

non-ASCII scan of changed Python files
passed

pre-commit run --files backend/api/v1/intake.py backend/schemas/intake.py backend/services/intake_service.py backend/services/intake_apply_service.py backend/tests/test_u4c_intake_api_contract.py backend/tests/test_u4ib2_intake_apply_service.py
passed, including Detect secrets
```

Ruff note:

- `poetry run ruff check services/intake_apply_service.py tests/test_u4ib2_intake_apply_service.py`: passed after autofix/manual cleanup.
- Full changed-file Ruff still reports pre-existing legacy findings in older touched files such as `Optional[...]` style, import ordering, and `B904`; these were not used as the branch gate.

Secret scan note:

- Filename-only keyword scan found benign existing auth/test references in `api/v1/intake.py` and `test_u4c_intake_api_contract.py`.
- Pre-commit Detect secrets passed.
- No secret values were printed or introduced.

## Remaining Risks

- U4-I-B2 has no frontend button by design; users cannot trigger it from UI in this branch.
- Concurrent double-apply is mitigated with row/workspace locks and final official SKU uniqueness, but high-concurrency production proof should be part of a later runtime/load gate.
- Existing `datetime.utcnow()` warnings in intake routes remain out of scope.

## R1 Apply Status Guard Test Completion

CTO finding: U4-I-B2 production code already had guards for `apply_status == 'applied'` and `apply_status != 'not_applied'`, but tests only covered repeated/applied behavior. The non-terminal guarded states `applying` and `failed` were not explicitly covered.

R1 update:

- Added a parameterized test for `apply_status = 'applying'` and `apply_status = 'failed'`.
- The test proves both states return `409 INVALID_APPLY_STATUS`.
- The test proves SKU count is unchanged.
- The test proves workspace `apply_status` remains unchanged.
- The test proves staged row `apply_status` remains `not_applied`.
- No production code was changed for R1.
