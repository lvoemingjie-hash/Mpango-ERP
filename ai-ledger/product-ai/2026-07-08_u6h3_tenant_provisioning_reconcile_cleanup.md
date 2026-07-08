# U6-H3 Tenant Provisioning Reconcile + Cleanup Safety Gate

Date: 2026-07-08
Branch: `opencode/u6h3-tenant-provisioning-reconcile-cleanup-2026-07-08`
Base: `origin/product-dev-recovered` at `27623beb merge: U6-H2 tenant provisioning wholesaler schema`
Implementation commit: `b622f351 feat(U6-H3): reconcile partial tenant provisioning`
R1 base commit: `b7a91394 docs(U6-H3): record final validation evidence`
Verdict: `PASS_FOR_CTO_REVIEW_PENDING_R1_FINAL_GITNEXUS`

## Pre-Edit GitNexus Impact

Completed before edits:

- `TenantProvisioningService`: `LOW`, `0` impacted.
- `TenantRegistration`: `LOW`, `8` impacted; affected path remains onboarding/provisioning service usage.
- `bootstrap_tenant_schema.bootstrap`: exact target not found by GitNexus.
- Fallback `bootstrap`: `LOW`, `4` impacted; affected paths are bootstrap script, seed script, and tests.

No `HIGH` or `CRITICAL` impact required edits outside `TenantProvisioningService`, tests, or docs.

## Scope

U6-H3 closes the U6-H2 residual risk where `bootstrap_tenant_schema.bootstrap` commits independently and can leave a partial tenant schema after failure.

U6-H3-R1 fixes a P1 gap in the first-attempt path: the service flushed `wholesaler_id + tenant_schema` before bootstrap, but rolled that assignment back when bootstrap failed. Because bootstrap can commit independently, a failed first attempt could leave a partial schema derived from the rolled-back wholesaler UUID. A retry would then create a new wholesaler UUID and a different schema, leaving the first partial schema unreachable.

Included:

- Explicit reconcile path for `provisioning` registrations with persisted `wholesaler_id + tenant_schema`.
- Complete-schema detection using required baseline bootstrap tables, not a single-table marker.
- If a persisted schema is complete, complete provisioning without rerunning bootstrap.
- If a persisted schema is incomplete, rerun canonical bootstrap idempotently and complete only after baseline tables exist.
- If reconcile bootstrap fails again, keep registration not active/not completed and persist sanitized `BOOTSTRAP_FAILED` failure state.
- Clear stale failure fields after successful reconcile.
- Preserve no-automatic-drop policy; tests clean their own temporary schemas only.
- R1: if first-attempt bootstrap fails after independently committing the generated schema, recover the generated public assignment after rollback before recording sanitized failure metadata.
- R1: if bootstrap fails without leaving the generated schema, preserve the prior U6-H2 behavior and do not persist an assignment.

## R1 Transaction And Retry Boundary

Chosen boundary: keep the initial public assignment and bootstrap in the existing transaction until bootstrap returns, but after rollback, check whether the generated tenant schema exists. If it exists, bootstrap has crossed its independent commit boundary, so the service restores the same wholesaler UUID/code and stores `wholesaler_id + tenant_schema` on the registration while recording `BOOTSTRAP_FAILED`.

This is the smallest safe fix because it does not change tenant identity semantics, does not require a migration, does not edit bootstrap, and does not create a durable assignment for failures that leave no schema behind.

No orphan schema is left unreachable: when a first attempt leaves a schema, the registration keeps the exact schema name and public wholesaler identity derived from the UUID that produced that schema. A retry enters the existing-assignment reconcile path, reruns canonical/idempotent bootstrap against the same schema, and completes the same wholesaler to active rather than creating a second wholesaler or a new schema.

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

R1 validation using disposable local Postgres container `opencode_u6h3_r1_pg` on localhost port `55435`:

- RED regression before service fix: `test_first_attempt_partial_schema_failure_persists_retry_anchor_and_reconciles` failed because `wholesaler_id` was `None` after first-attempt partial schema failure.
- `poetry run pytest tests/test_u6h3_tenant_provisioning_reconcile_cleanup.py::test_first_attempt_partial_schema_failure_persists_retry_anchor_and_reconciles -q`: `1 passed` after fix.
- `poetry run pytest tests/test_u6h3_tenant_provisioning_reconcile_cleanup.py -q`: `8 passed`.
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
