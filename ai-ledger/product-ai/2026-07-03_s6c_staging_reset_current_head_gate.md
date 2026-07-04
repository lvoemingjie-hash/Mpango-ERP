# S6-C Staging Reset Current-Head Gate

**Date**: 2026-07-03
**Branch**: `opencode/s6c-staging-reset-current-head-gate-2026-07-03`
**Baseline commit**: `61a6a534725fb1c54a83b7ade679e0b120c9906e`
**Executor**: OPS / opencode
**Verdict**: `NEEDS_ENV_VALIDATION`

## Summary

S6-C closes the staging-reset drift risk by changing `backend/scripts/reset-staging.sh` from an old fixed Alembic revision to current Alembic head and adding fail-closed post-reset tenant schema assertions for current MVP tables and intake apply audit columns.

No real destructive reset was run. Validation is static/contract-level plus shell syntax and Alembic-head inspection. A runner or live staging reset still needs to execute the script against an approved staging environment.

## Old Defect

`backend/scripts/reset-staging.sh` was pinned to an old B6 migration:

```text
python -m alembic upgrade 006_phase_b6_payments_idempotency_key
```

That excluded current S4/S5/U4 migration state from the reset path, including:

```text
022_import_runs
023_inventory_reservations
024_intake_skeleton
025_intake_apply_audit
```

The reset path could therefore create runtime drift after staging resets.

## GitNexus Impact Audit

Required pre-edit GitNexus context/impact checks were run:

```text
npx gitnexus context --repo s6c-staging-reset-current-head-gate-2026-07-03 reset-staging.sh
npx gitnexus impact --repo s6c-staging-reset-current-head-gate-2026-07-03 --depth 2 --include-tests reset-staging.sh
Result: reset-staging.sh found, LOW risk, impactedCount 0

npx gitnexus context --repo s6c-staging-reset-current-head-gate-2026-07-03 env.py
npx gitnexus impact --repo s6c-staging-reset-current-head-gate-2026-07-03 --depth 2 --include-tests env.py
Result: backend/alembic/env.py found, LOW risk, impactedCount 0

npx gitnexus context/impact bootstrap_tenant_schema.py
Result: MEDIUM risk, 7 direct test imports; file was audited but not modified

npx gitnexus context/impact 022_import_runs.py
npx gitnexus context/impact 023_inventory_reservations.py
npx gitnexus context/impact 024_intake_skeleton.py
npx gitnexus context/impact 025_intake_apply_audit.py
Result: all LOW risk, impactedCount 0
```

No HIGH or CRITICAL impact was reported.

## CTO Field Contract Correction

Initial instructions named row-level fields that do not exist in current migration/model/bootstrap contracts:

```text
intake_product_rows.applied_sku_id
intake_product_rows.apply_error
intake_product_rows.applied_at
```

CTO reviewed the current migration/model/bootstrap contract and superseded those field names.

No migration was added because current code already uses:

```text
intake_product_rows.target_sku_id
intake_product_rows.apply_error_code
intake_product_rows.apply_error_message
```

Row-level `applied_at` is intentionally omitted. Workspace-level `intake_workspaces.applied_at` is the authoritative apply timestamp. Row-level apply result is tracked by `apply_status`, `target_sku_id`, `apply_error_code`, and `apply_error_message`.

## New Contract

`reset-staging.sh` now runs:

```text
python -m alembic upgrade head
```

Alembic head was checked and is unambiguous:

```text
poetry run alembic heads
025_intake_apply_audit (head)
```

The script now requires `REPORTING_USER_PASSWORD` to be present for the Alembic reporting-role migration and does not print its value. The old hardcoded reporting password fallback was removed.

After demo seeding, the script runs the canonical tenant bootstrap reconciler for the demo tenant:

```text
python /app/scripts/bootstrap_tenant_schema.py "$TENANT_SCHEMA"
```

This keeps the reset path aligned with the existing current tenant schema contract without modifying `bootstrap_tenant_schema.py`, models, or migrations.

Post-reset assertions verify these tenant tables:

```text
import_runs
inventory_reservations
intake_workspaces
intake_uploads
intake_product_rows
intake_validation_issues
```

Post-reset assertions verify these `intake_workspaces` columns:

```text
apply_status
applied_at
applied_by
apply_result
```

Post-reset assertions verify these `intake_product_rows` columns:

```text
apply_status
target_sku_id
apply_error_code
apply_error_message
```

Fail-closed behavior:

```text
Any missing table or column prints table:<name> MISSING or column:<table>.<column> MISSING and exits 1.
The assertion section does not use || true.
```

## Changed Files

```text
.gitattributes
backend/scripts/reset-staging.sh
backend/tests/test_s6c_reset_staging_current_head_gate.py
ai-ledger/product-ai/2026-07-03_s6c_staging_reset_current_head_gate.md
```

`.gitattributes` pins only `backend/scripts/reset-staging.sh` to LF so `bash -n` and Linux containers do not regress to CRLF checkout drift.

## Validation

Pre-fix contract reproduction:

```text
poetry run pytest tests/test_s6c_reset_staging_current_head_gate.py -q
3 failed, 1 passed
Failures proved the old script was pinned to 006 and lacked post-reset MVP schema assertions.
```

Post-fix targeted contract tests:

```text
poetry run pytest tests/test_s6c_reset_staging_current_head_gate.py -q
4 passed in 0.27s
```

Shell syntax:

```text
bash -n backend/scripts/reset-staging.sh
PASS, exit 0. WSL emitted a host warning before bash output, but no shell syntax error.
```

Alembic head check:

```text
poetry run alembic heads
025_intake_apply_audit (head)
```

Hygiene:

```text
git diff --check: PASS
changed-file ASCII scan: PASS
changed-file mojibake scan: PASS
changed-file sensitive-keyword scan: matched only environment variable names and ledger/test statements that no secrets are printed
pre-commit run --files .gitattributes backend/scripts/reset-staging.sh backend/tests/test_s6c_reset_staging_current_head_gate.py ai-ledger/product-ai/2026-07-03_s6c_staging_reset_current_head_gate.md: PASS
npx gitnexus analyze; npx gitnexus status before commit: PASS, indexed baseline/current commit 61a6a53
npx gitnexus analyze; npx gitnexus status after commit: PASS, indexed commit 809d537
```

GitNexus CLI help did not expose a `detect_changes` command in this environment.

## Remaining Risk

This is not a live reset proof. No destructive reset was executed locally, on VPS, or in staging.

Remaining validation needed:

```text
Leo/runner/live staging should execute backend/scripts/reset-staging.sh in an approved staging reset window and confirm the post-reset assertions pass against the real database.
```

## Scope Discipline

- Migration added: no.
- `backend/models/intake.py` changed: no.
- `backend/alembic/versions/025_intake_apply_audit.py` changed: no.
- `backend/scripts/bootstrap_tenant_schema.py` changed: no.
- Production runtime code changed: no.
- Real destructive reset run: no.
- Deployment performed: no.
- VPS connected: no.
- `product-dev-recovered` pushed: no.
- Secrets read or printed: no.
