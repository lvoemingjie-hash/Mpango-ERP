# U4-C Data Intake Backend Schema Skeleton

**Date**: 2026-07-01
**Branch**: `opencode/u4c-data-intake-backend-schema-skeleton-2026-07-01`
**Base**: `origin/product-dev-recovered` at `3d39d4b`
**Executor**: OpenCode GPT-5.5
**Verdict**: `PASS_FOR_CTO_U4C_REVIEW`

## Scope

U4-C implements the internal-login-only backend skeleton for data intake workspaces.

Implemented tenant-scoped tables:

- `intake_workspaces`
- `intake_uploads`
- `intake_product_rows`
- `intake_validation_issues`

Implemented API routes:

- `POST /api/v1/intake/workspaces`, gated by `intake:create`
- `GET /api/v1/intake/workspaces`, gated by `intake:read`
- `GET /api/v1/intake/workspaces/{workspace_id}`, gated by `intake:read`

## Files Changed

- `backend/alembic/versions/024_intake_skeleton.py`
- `backend/models/intake.py`
- `backend/models/__init__.py`
- `backend/schemas/intake.py`
- `backend/api/v1/intake.py`
- `backend/api/app.py`
- `backend/scripts/bootstrap_tenant_schema.py`
- `backend/scripts/create_wholesaler.py`
- `backend/scripts/onboard_tenant.py`
- `backend/scripts/seed_test_tenant.py`
- `backend/tests/test_u1_bootstrap_permission_completeness.py`
- `backend/tests/test_u4c_intake_api_contract.py`
- `backend/tests/test_u4c_intake_backend_schema.py`

## Boundaries Preserved

- No `intake_assets` table.
- No `intake_exports` table.
- No `public.intake_public_tokens` table.
- No public token route or tenant-schema scanning.
- No file upload endpoint.
- No CSV/XLSX parser implementation.
- No direct SKU write path.
- No calls into U3 `sku_imports` preview, validate, or apply.
- No frontend or deployment changes.

## GitNexus Impact Note

Pre-edit GitNexus impact reported `HIGH` for `backend/scripts/bootstrap_tenant_schema.py:bootstrap` with impacted seed/runtime/test paths. This was expected because bootstrap is used for fresh tenant setup and tenant-schema test preparation.

Mitigation:

- The bootstrap change is additive only.
- Existing table DDL and reconciliation paths were not changed.
- U4-C creates only the four approved intake tables.
- Intake index reconciliation is idempotent and isolated to those four tables.
- Targeted bootstrap/schema tests verify table scope and forbidden table absence.

## Validation

Targeted tests:

```text
pytest backend/tests/test_u4c_intake_backend_schema.py backend/tests/test_u4c_intake_api_contract.py backend/tests/test_u1_bootstrap_permission_completeness.py -q
15 passed, 1 warning
```

Additional checks:

```text
git diff --check
PASS

npx gitnexus analyze; npx gitnexus status
Already up to date; status up-to-date at 3d39d4b

pre-commit run --files <U4-C changed files>
PASS
```

Pre-commit note:

- `pre-commit run --all-files` is not usable on this repository state because repository-wide legacy files trigger existing encoding/YAML issues and hook auto-fixes outside this slice.
- The repository-wide hook side effects were restored, and scoped U4-C pre-commit passed.

ASCII scan:

- New U4-C files are ASCII.
- Existing non-ASCII glyphs remain in legacy touched scripts and comments; no new mojibake was introduced.

Secret scan:

- Scoped diff scan found no secret-like values in implementation changes.
- Full diff pattern scan found only false positives: ledger text, `TokenPayload`, and allowlisted test-only placeholder environment values.

## Notes

- Seed scripts already contained `intake:*` permissions from U4-A, so no permission set expansion was required.
- Only stale comments were updated to reflect that U4-C now exposes workspace routes.
- `get_tenant_db_session` is required on every U4-C route, so routes cannot operate without tenant context.

## R1 Runtime Contract Proof

R1 added runtime-level tests beyond source-string checks.

API runtime coverage added:

- Unauthenticated request to `/api/v1/intake/workspaces` returns `401` with `UNAUTHENTICATED`.
- Authenticated contextual tenant user without `intake:create` cannot `POST /api/v1/intake/workspaces`.
- Authenticated contextual tenant user without `intake:read` cannot list or detail workspaces.
- Contextual tenant user with `intake:create` can create a workspace through the real router.
- Contextual tenant user with `intake:read` can list and detail a created workspace through the real router.
- Detail endpoint returns `404 WORKSPACE_NOT_FOUND` for another tenant's workspace ID.

Bootstrap runtime coverage added:

- Creates a temporary existing tenant schema missing the four intake tables.
- Runs `bootstrap_tenant_schema.bootstrap(schema, database_url)` directly.
- Verifies exactly these intake tables exist in that schema:
  `intake_workspaces`, `intake_uploads`, `intake_product_rows`, `intake_validation_issues`.
- Verifies forbidden tables do not exist:
  `intake_assets`, `intake_exports`, `public.intake_public_tokens`.
- Verifies core U4-C intake indexes exist.

R1 validation command:

```text
pytest tests/test_u4c_intake_backend_schema.py tests/test_u4c_intake_api_contract.py tests/test_u1_bootstrap_permission_completeness.py -q
22 passed, 5 warnings
```

R1 additional checks:

```text
git diff --check
PASS

npx gitnexus analyze; npx gitnexus status
Already up to date; status up-to-date at b6c8973
```

R1 secret/scope scan:

- Secret-pattern scan matched only false positives in test-only placeholders, `TokenPayload`, and forbidden-token assertions.
- Forbidden-scope scan matched only negative assertions in tests; no implementation references to `intake_assets`, `intake_exports`, public token routes/tables, upload handling, U3 import, or SKU writes.

R1 verdict: `PASS_FOR_CTO_U4C_REVIEW`.
