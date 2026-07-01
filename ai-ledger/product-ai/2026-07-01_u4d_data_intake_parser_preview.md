# U4-D Data Intake Parser Preview

**Date**: 2026-07-01
**Branch**: `opencode/u4d-data-intake-parser-preview-2026-07-01`
**Base**: `origin/product-dev-recovered` at `958eb21`
**Executor**: OpenCode GPT-5.5
**Verdict**: `PASS_FOR_CTO_U4D_REVIEW`

## Scope

U4-D implements internal-login-only intake parser/preview behavior on top of the U4-C staging tables.

Implemented parser support:

- CSV uploads with UTF-8 and UTF-8-sig decoding.
- XLSX uploads using `openpyxl`, reading the first non-empty sheet only.
- Deterministic header normalization, including repeated header names.
- Preserved `source_row_number` for source-file row provenance.
- Preserved source row `raw_values` in staging rows.
- Unreadable or password-protected XLSX files fail closed with `XLSX_PARSE_ERROR`.

Implemented API routes:

- `POST /api/v1/intake/workspaces/{workspace_id}/uploads`, gated by `intake:create` or `intake:update`.
- `PUT /api/v1/intake/workspaces/{workspace_id}/mapping`, gated by `intake:update`.
- `POST /api/v1/intake/workspaces/{workspace_id}/validate`, gated by `intake:update`.
- `GET /api/v1/intake/workspaces/{workspace_id}/rows`, gated by `intake:read`.
- `GET /api/v1/intake/workspaces/{workspace_id}/issues`, gated by `intake:read`.

Implemented validation behavior:

- Missing `sku_code` writes blocking `ERROR` issue.
- Missing `name` writes blocking `ERROR` issue.
- Duplicate staged `sku_code` within the workspace writes blocking `ERROR` issues.
- Field length violations write blocking `ERROR` issues.
- Unmapped extra columns write non-blocking `WARNING` issues.
- Missing unit writes a non-blocking `WARNING`; U4-D does not silently default or mutate unit values.
- Blocking errors set workspace status to `NEEDS_REVIEW`; warnings alone allow `READY_FOR_EXPORT`.

## Files Changed

- `backend/alembic/versions/024_intake_skeleton.py`
- `backend/api/v1/intake.py`
- `backend/poetry.lock`
- `backend/pyproject.toml`
- `backend/schemas/intake.py`
- `backend/scripts/bootstrap_tenant_schema.py`
- `backend/services/intake_service.py`
- `backend/tests/test_u4c_intake_api_contract.py`
- `backend/tests/test_u4c_intake_backend_schema.py`
- `backend/tests/test_u4d_intake_parser_preview.py`

## Dependency Approval

CTO approved adding `openpyxl` only for XLSX parsing.

Dependency result:

- Added direct dependency: `openpyxl==3.1.5`.
- Lockfile added transitive dependency: `et-xmlfile`.
- Did not add `pandas`, `xlrd`, `xlsxwriter`, or broad data-processing dependencies.

Rationale:

- `openpyxl` is a narrow XLSX workbook parser dependency and is sufficient for first non-empty sheet parsing.
- `pandas` was not used because it is a broad data-processing dependency and explicitly out of scope.
- `xlrd` and `xlsxwriter` were not used because U4-D only needs XLSX read support, not legacy XLS parsing or XLSX writing.

## Boundaries Preserved

- No `intake_exports` table.
- No public token route.
- No `public.intake_public_tokens` table.
- No U3 `sku_imports` preview, validate, or apply call.
- No direct SKU insert or update path.
- No frontend changes.
- No deploy changes.
- Parser ledger entries do not store raw token or secret-like source contents.

## Schema Note

U4-D runtime inserts `IntakeValidationIssue` ORM rows. This exposed that the U4-C migration/bootstrap DDL omitted `created_by` and `updated_by` on `intake_validation_issues`, despite the model inheriting `BaseModel` user tracking columns like the other intake tables.

Fix:

- Added `created_by` and `updated_by` to `intake_validation_issues` in `024_intake_skeleton.py`.
- Added the same columns in `bootstrap_tenant_schema.py` fresh tenant DDL.
- Strengthened U4-C schema tests to assert user tracking columns on all four intake tables.

## GitNexus Impact Note

`npx gitnexus status` reported indexed commit `958eb21` and current commit `958eb21`, up to date.

`npx gitnexus analyze` reported already up to date.

Bootstrap remains a high-impact touchpoint because fresh tenant setup and runtime tests depend on it. The U4-D bootstrap change is additive only and limited to the missing user-tracking columns on the existing approved `intake_validation_issues` table.

## Validation

Targeted tests:

```text
poetry run pytest tests/test_u4c_intake_backend_schema.py tests/test_u4c_intake_api_contract.py tests/test_u4d_intake_parser_preview.py -q
22 passed, 13 warnings
```

Parser coverage:

- UTF-8-sig CSV happy path.
- Source row number preservation.
- Duplicate header deterministic normalization.
- XLSX first non-empty sheet happy path.
- Unreadable XLSX fail-closed error.

API/runtime coverage:

- Upload accepts `intake:update` as an allowed permission.
- Upload rejects a user with only `intake:read`.
- Upload writes `intake_uploads` and `intake_product_rows` only.
- Mapping writes `normalized_values` and staged convenience fields only.
- Validation writes `intake_validation_issues`.
- Rows endpoint returns raw and normalized staged values.
- Issues endpoint returns row/file-level validation issues.

Additional checks:

```text
poetry check --lock
PASS with existing Poetry metadata warnings

poetry run python -m py_compile api/v1/intake.py schemas/intake.py services/intake_service.py
PASS

git diff --check
PASS

poetry run pre-commit run --config ../.pre-commit-config.yaml --files <changed U4-D files>
PASS

npx gitnexus status
up-to-date at 958eb21

npx gitnexus analyze
Already up to date
```

Dependency/scope scans:

- Changed implementation files contain no `ImportService`, `sku_import`, `skus/import`, `SKU(`, `intake_exports`, or public token route/table references.
- `pyproject.toml` and `poetry.lock` contain no `pandas`, `xlrd`, or `xlsxwriter` package entries.
- `poetry.lock` contains expected `openpyxl` and `et-xmlfile` entries.
- Pre-commit Detect Secrets passed on changed files.
- Changed-file mojibake/non-ASCII scan passed.

## Verdict

`PASS_FOR_CTO_U4D_REVIEW`

## R1 Parser Boundary and Unit Price Hardening

R1 added fail-closed parser boundaries:

- `MAX_ROWS = 5000`
- `MAX_COLUMNS = 100`
- `MAX_CELL_LENGTH = 2000`
- `MAX_HEADER_LENGTH = 255`

R1 parser error codes:

- `ROW_LIMIT_EXCEEDED`
- `COLUMN_LIMIT_EXCEEDED`
- `CELL_TOO_LARGE`
- `HEADER_TOO_LARGE`

R1 also fixed `unit_price` validation:

- Non-empty invalid decimal values no longer silently become `None` during validation.
- `validate_workspace()` writes blocking `ERROR` issue `INVALID_UNIT_PRICE` on field `unit_price`.
- Valid decimal values keep the existing staged convenience-column behavior.

R1 test coverage added:

- CSV and XLSX row limit failures.
- CSV and XLSX column limit failures.
- CSV and XLSX header length failures.
- CSV and XLSX cell length failures.
- `unit_price=abc` produces `INVALID_UNIT_PRICE`.
- U4-D implementation-level guard still proves no SKU write surface, no public token surface, and no U3 import service call.

R1 targeted tests:

```text
poetry run pytest tests/test_u4c_intake_backend_schema.py tests/test_u4c_intake_api_contract.py tests/test_u4d_intake_parser_preview.py -q
31 passed, 13 warnings
```

R1 additional checks:

```text
poetry check --lock
PASS with existing Poetry metadata warnings

git diff --check
PASS

poetry run py_compile services/intake_service.py api/v1/intake.py schemas/intake.py
Environment note: no py_compile console script exists in this Poetry environment.

poetry run python -m py_compile services/intake_service.py api/v1/intake.py schemas/intake.py
PASS

poetry run pre-commit run --config ../.pre-commit-config.yaml --files <changed U4-D files>
PASS

npx gitnexus analyze
Already up to date
```
