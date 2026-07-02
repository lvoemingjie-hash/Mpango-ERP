# U4-I-B0 Intake Apply Readiness Design Gate

Date: 2026-07-02

Branch: `opencode/u4ib0-intake-apply-readiness-design-gate-2026-07-02`

Base: `origin/product-dev-recovered` at `e7caa48`

Verdict: `PASS_FOR_CTO_U4IB0_REVIEW`

## Scope

U4-I-B0 is a design and audit gate before any staged-intake-to-official-SKU write implementation.

This branch is report-only. It does not write SKUs, edit production code, add migrations, change frontend code, or deploy.

## 1. Schema Readiness

Audited existing U4 intake tables from `backend/models/intake.py` and `backend/alembic/versions/024_intake_skeleton.py`:

- `intake_workspaces`
- `intake_uploads`
- `intake_product_rows`
- `intake_validation_issues`

Current relevant fields:

- `intake_workspaces`: `status`, `approved_by`, `approved_at`, `metadata`
- `intake_uploads`: source file metadata, parser status/counts, headers, `parse_summary`
- `intake_product_rows`: raw values, normalized values, mapped SKU fields, `review_status`, `dedupe_key`
- `intake_validation_issues`: row/file validation issues with severity, code, field, source header, message, blocking flag, resolution fields

Readiness matrix:

| Apply need | Current schema support | Decision |
| --- | --- | --- |
| `applied_at` | Can be stored in workspace `metadata`; `approved_at` exists but has wrong semantics | Use `metadata` only if CTO accepts MVP JSON audit; prefer migration |
| `applied_by` | Can be stored in workspace `metadata`; `approved_by` exists but has wrong semantics | Use `metadata` only if CTO accepts MVP JSON audit; prefer migration |
| `apply_status` | Could overload workspace `status` with `EXPORTED`/`PUSHED_TO_ERP_PREVIEW` or store in `metadata`; no dedicated apply status | Prefer explicit migration; metadata is acceptable only as temporary MVP contract |
| `apply_result` summary | Workspace `metadata` can hold JSON result | Sufficient for MVP if immutable once written |
| source row -> created SKU id mapping | Workspace `metadata.apply_result.rows[]` can hold row id/source row/SKU id; no first-class row field | Technically possible, but migration is preferable for queryability and recovery |
| failure reason per row | Existing `intake_validation_issues` can hold pre-apply blockers; apply-attempt failures could also be stored there with apply-specific codes | Sufficient if apply failure writes are rolled back with the failed apply, or persisted only for preflight failures |
| idempotency marker | Workspace `metadata.apply_idempotency_key` or `metadata.apply_result` can mark completed apply | Sufficient for MVP if guarded transactionally and immutable after success |

Conclusion:

- Current schema can support a minimal MVP apply-readiness contract without an immediate migration if CTO accepts workspace `metadata` as the temporary apply audit envelope.
- Current schema is not ideal for durable, queryable apply audit because it lacks dedicated apply lifecycle fields and row-level SKU mapping fields.
- A migration is recommended for U4-I-B1 or the first production SKU-write slice, but it is not required to complete this design gate.

Minimal future migration proposal, if CTO wants first-class audit before U4-I-B writes SKUs:

- Add to `intake_workspaces`: `apply_status`, `applied_at`, `applied_by`, `apply_result`, `apply_idempotency_key`.
- Add to `intake_product_rows`: `applied_sku_id`, `apply_status`, `apply_error_code`, `apply_error_message`.
- Add indexes on `intake_workspaces.apply_status`, `intake_workspaces.applied_at`, and `intake_product_rows.applied_sku_id`.
- Keep all columns tenant-schema local; no public tables.

## 2. Reuse vs New Service Decision

### Option A: Reuse U3 `sku_imports` apply logic

Description: Create a thin U4 adapter that converts validated intake rows into the shape expected by `ImportService.apply()` or directly calls shared import apply logic with forced `on_conflict='fail'`.

Benefits:

- Reuses a proven SKU apply path with existing atomic apply behavior.
- Existing U3 service already supports duplicate fail-closed behavior through `on_conflict='fail'`.
- Existing U3 service already writes `applied_at`, `applied_by`, and `apply_result` for `import_runs`.
- Minimizes direct edits to protected SKU master-data symbols.

Risks:

- U3 `import_run` schema and U4 intake workspace/row schema are not identical.
- U3 also supports `on_conflict='skip'`; U4 MVP must forbid skip and force fail-closed.
- U3 route-level `apply_import` owns commit/rollback, while U4 should preserve tenant middleware transaction ownership.
- Adapter mistakes could bypass U4 validation issue semantics or produce stale mappings.

Affected symbols:

- `backend/services/import_service.py::ImportService.apply`
- `backend/api/v1/sku_imports.py::apply_import` as reference only, not necessarily edited
- `backend/models/import_run.py`
- U4 intake route/service adapter files added in U4-I-B

GitNexus expected risk:

- MEDIUM to HIGH, because `SKU` is a HIGH-impact symbol and U3 import apply is in the SKU write blast radius.

Test burden:

- Contract tests that U4 adapter always uses fail-closed duplicate behavior.
- Tests proving no skip/upsert path can be selected from U4.
- Tests for idempotent repeated apply.
- Live DB atomicity tests for row N failure and duplicate SKU pre-scan.
- Static tests that U4 apply requires `intake:update` plus `skus:import`.

Runtime proof burden:

- Browser/API proof with a READY_FOR_EXPORT workspace.
- Duplicate existing SKU proof returns conflict and writes no SKUs.
- Failure injection proof leaves no partial SKU rows or partial apply status.

### Option B: Build intake-specific apply service

Description: Add a new U4-only apply service that reads `intake_workspaces`/`intake_product_rows` and writes official SKUs directly.

Benefits:

- Exact fit for U4 intake statuses, rows, validation issues, metadata, and future audit columns.
- Easier to enforce U4-specific permissions, eligibility, duplicate fail-closed behavior, idempotency, and audit semantics.
- Avoids forcing U4 data into U3 `import_run` shape.

Risks:

- New SKU write path increases blast radius and review burden.
- More likely to touch protected SKU model/service/repository code.
- Duplicates logic already proven in U3 import apply unless carefully factored.

Affected symbols:

- New U4 apply service module
- `backend/api/v1/intake.py` for a future apply endpoint
- `backend/models/sku.py` indirectly through official SKU inserts
- Possibly `backend/services/sku_service.py` or `backend/repositories/sku_repository.py` if not using raw ORM insert

GitNexus expected risk:

- HIGH unless implemented as a narrow adapter with no direct SKU model/service changes.

Test burden:

- Full permission, eligibility, duplicate, idempotency, audit, and atomicity suite.
- Static tests that no U4 apply route exposes public token/image/barcode scan behavior.
- Live DB tests for all-or-none writes and status rollback.

Runtime proof burden:

- Highest burden because this is a new official SKU write path.

### Option C: Convert intake workspace into U3 `import_run`, then call existing apply path

Description: Materialize a U3 `import_run` from a READY_FOR_EXPORT intake workspace, then invoke the existing U3 apply behavior with `on_conflict='fail'`.

Benefits:

- Maximum reuse of existing import audit fields and apply response shape.
- Avoids direct SKU model/service edits in U4 code.
- Keeps official SKU write behavior centralized in U3 import apply.

Risks:

- Adds a second staging record (`import_run`) that may diverge from the intake workspace if not transactionally coupled.
- Requires precise provenance mapping back to intake rows.
- U3 `import_run` contract may not represent all U4 intake row metadata without lossy conversion.
- U3 route commit/rollback ownership should not be reused directly; service-level use must be inside U4 transaction control.

Affected symbols:

- `backend/models/import_run.py`
- `backend/services/import_service.py`
- New U4 adapter module
- Future U4 intake apply endpoint

GitNexus expected risk:

- MEDIUM to HIGH, lower than a fully new SKU write service if direct SKU symbols remain untouched.

Test burden:

- Tests proving import_run conversion is deterministic and lossless for required U4 fields.
- Tests proving U4 workspace and import_run status/audit update atomically.
- Tests proving repeated apply does not create duplicate import_runs or SKUs.

Runtime proof burden:

- Proof of workspace -> import_run -> apply in one tenant context.
- Proof no divergence on failure.

Recommended direction:

- Prefer Option C or a narrow variant of Option A if the U3 `import_run` contract can represent U4 intake rows without lossy conversion.
- Do not choose Option B unless CTO accepts the higher risk of a new official SKU write path.
- Do not edit `SKU`, SKU service/repository, or `sku_imports.apply_import` until an expanded GitNexus review is complete.

## 3. Apply Contract Finalization

Permission:

- Require both `intake:update` and `skus:import`.
- `intake:create` and `intake:read` must never be sufficient to apply official SKUs.

Eligibility:

- Workspace status must be exactly `READY_FOR_EXPORT`.
- Blocking validation issues must equal `0`.
- Mapped rows must exist.
- Mapping version used for apply must match the current staged rows.
- Rows with invalid price, barcode, unit, SKU code, or required SKU master-data fields must block apply.

Duplicate SKU behavior:

- MVP must fail closed if any SKU code already exists in official `skus`.
- No silent overwrite.
- No skip-and-continue for U4 MVP, even though U3 import apply supports `skip`.
- Upsert requires future CTO approval plus explicit update permission design.

Idempotency:

- Repeated apply must not duplicate SKUs.
- If a workspace already has a completed immutable apply result, return deterministic `ALREADY_APPLIED` or the previous result.
- Any idempotency key/result must be written in the same transaction as official SKU creation.

Atomicity:

- All rows apply, or none apply.
- No partial SKU writes if any row fails.
- No partial workspace/import status update if SKU insert fails.
- Use one tenant transaction; do not split apply across route-level commits.

Audit:

- Apply must record actor, time, result summary, row count, created SKU ids, duplicate/conflict outcome, and idempotency marker.
- If CTO accepts metadata for MVP, write under a namespaced immutable key such as `metadata.apply`.
- If CTO requires first-class queryability, implement the minimal migration before SKU writes.

Explicit exclusions:

- No public token path.
- No image ingestion.
- No barcode scan workflow.
- No frontend apply button in this slice.

## 4. U4-I-B Implementation Proposal

Recommended next coding slice: U4-I-B1 apply-readiness infrastructure, still before broad runtime launch.

Allowed files for U4-I-B1, subject to CTO approval:

- New `backend/services/intake_apply_contract.py` or `backend/services/intake_apply_service.py` adapter module.
- New `backend/tests/test_u4ib_intake_apply_contract.py`.
- `backend/api/v1/intake.py` only to add a single explicit apply endpoint after contract tests exist.
- `backend/schemas/intake.py` only for typed apply request/response contracts.
- Optional migration file only if CTO approves first-class apply audit columns/table.
- Product ledger report.

Forbidden files for U4-I-B1 unless CTO separately approves expanded SKU-write work:

- `backend/models/sku.py`
- `backend/services/sku_service.py`
- `backend/repositories/sku_repository.py`
- `backend/api/v1/skus.py`
- `backend/api/v1/sku_imports.py::apply_import`
- frontend files
- public token/PWA/image/barcode scan paths

Required tests for U4-I-B1:

- Static permission test: future U4 apply requires `intake:update` and `skus:import`.
- Eligibility tests for non-`READY_FOR_EXPORT`, blocking issues, no mapped rows, invalid values, and stale mapping.
- Duplicate existing SKU test: returns conflict and writes zero SKUs.
- Idempotency test: repeated apply returns deterministic already-applied result and writes no duplicate SKUs.
- Atomicity test: injected row N failure leaves zero SKU writes and no partial apply status.
- Audit test: actor/time/result/row mapping/idempotency marker recorded in the chosen audit storage.
- Regression tests that U4-C/U4-D staging-only routes still do not write official SKUs.

GitNexus pre-checks for U4-I-B1:

- `SKU`
- `ImportService.apply`
- `apply_import`
- `IntakeService`
- future `intake_apply_*` symbols before merge
- `backend/api/v1/intake.py`
- `backend/models/import_run.py` if Option C is selected

Expected runtime proof for U4-I-B1/B2:

- API/browser-authenticated proof using tenant context.
- Apply happy path creates expected SKUs once.
- Duplicate existing SKU path fails closed and writes no SKUs.
- Injected failure path proves all-or-none behavior.
- Repeated apply path proves idempotency.
- DB proof of audit fields/result and row-to-SKU mapping.

STOP conditions for U4-I-B1:

- GitNexus impact is HIGH/CRITICAL and not explicitly approved by CTO.
- Any implementation requires direct edits to protected SKU core symbols without approval.
- U3 import path would require enabling `skip`/overwrite behavior for U4.
- Existing schema/audit decision is unresolved before writing official SKUs.
- Any path writes official SKUs before permission, eligibility, idempotency, atomicity, and audit tests exist.
- Any secret appears in report, tests, logs, or output.

## Validation Plan For This Branch

This branch is report-only, so no pytest was required or run.

Validation to run before commit:

- `git diff --check`
- ASCII/mojibake scan for this report
- secret scan for this report/diff
- `npx gitnexus analyze`
- `npx gitnexus status`
- pre-commit hooks on commit, if configured
