# U6-H3 Tenant Provisioning Reconcile + Cleanup Safety Gate

Date: 2026-07-08
Branch: `opencode/u6h3-tenant-provisioning-reconcile-cleanup-2026-07-08`
Base: `origin/product-dev-recovered` at `27623beb merge: U6-H2 tenant provisioning wholesaler schema`
Implementation commit: `b622f351 feat(U6-H3): reconcile partial tenant provisioning`
Verdict: `PASS_FOR_CTO_REVIEW`

## Pre-Edit GitNexus Impact

Completed before edits:

- `TenantProvisioningService`: `LOW`, `0` impacted.
- `TenantRegistration`: `LOW`, `8` impacted; affected path remains onboarding/provisioning service usage.
- `bootstrap_tenant_schema.bootstrap`: exact target not found by GitNexus.
- Fallback `bootstrap`: `LOW`, `4` impacted; affected paths are bootstrap script, seed script, and tests.

No `HIGH` or `CRITICAL` impact required edits outside `TenantProvisioningService`, tests, or docs.

## Scope

U6-H3 closes the U6-H2 residual risk where `bootstrap_tenant_schema.bootstrap` commits independently and can leave a partial tenant schema after failure.

Included:

- Explicit reconcile path for `provisioning` registrations with persisted `wholesaler_id + tenant_schema`.
- Complete-schema detection using required baseline bootstrap tables, not a single-table marker.
- If a persisted schema is complete, complete provisioning without rerunning bootstrap.
- If a persisted schema is incomplete, rerun canonical bootstrap idempotently and complete only after baseline tables exist.
- If reconcile bootstrap fails again, keep registration not active/not completed and persist sanitized `BOOTSTRAP_FAILED` failure state.
- Clear stale failure fields after successful reconcile.
- Preserve no-automatic-drop policy; tests clean their own temporary schemas only.

Excluded:

- No migration.
- No frontend.
- No public API endpoint.
- No admin user/RBAC/permission row seeding.
- No password delivery.
- No deploy/VPS changes.
- No `product-dev-recovered` push.
- No Wholesaler model/API/CRUD/repository edits.
- No `bootstrap_tenant_schema.py` edit.

## Validation Results

Completed using disposable local Postgres container `opencode_u6h3_pg` on localhost port `55434`:

- `poetry run pytest tests/test_u6h3_tenant_provisioning_reconcile_cleanup.py -q`: `7 passed`.
- `poetry run pytest tests/test_u6h2_tenant_provisioning_wholesaler_schema.py tests/test_u6h1_tenant_provisioning_service_skeleton.py -q`: `24 passed`.
- `poetry run python -m py_compile services/tenant_provisioning_service.py tests/test_u6h3_tenant_provisioning_reconcile_cleanup.py`: passed.
- `git diff --check`: passed.
- ASCII scan on changed files: passed, no matches.
- Mojibake scan on changed files: passed, no matches.
- Secret-pattern scan on changed files: reviewed; matches were expected test placeholders, explicit leakage assertions, and field/config names.
- `pre-commit run --files backend/services/tenant_provisioning_service.py backend/tests/test_u6h3_tenant_provisioning_reconcile_cleanup.py ai-ledger/product-ai/2026-07-08_u6h3_tenant_provisioning_reconcile_cleanup.md`: passed.
- Forbidden-file check: no changes in Wholesaler model/API/CRUD/repository, platform APIs, or `backend/scripts/bootstrap_tenant_schema.py`.

Final GitNexus evidence:

- `npx gitnexus analyze`: repository indexed successfully; `6,794 nodes`, `19,319 edges`, `449 clusters`, `229 flows`.
- `npx gitnexus status`: indexed commit `b622f35`, current commit `b622f35`, status up-to-date.

## Residual Risk

U6-H3 does not drop tenant schemas automatically. Reconcile retries canonical bootstrap, and failed retries remain fail-closed with sanitized failure metadata. Any future destructive cleanup of abandoned schemas requires an explicit CTO-approved task.
