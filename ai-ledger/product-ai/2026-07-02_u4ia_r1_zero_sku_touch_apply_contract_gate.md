# U4-I-A-R1 Zero-SKU-Touch Apply Contract Gate

Date: 2026-07-02

Branch: `opencode/u4ia-r1-zero-sku-touch-apply-contract-gate-2026-07-02`

Base: `origin/product-dev-recovered` at `e7caa48`

Verdict: `PASS_FOR_CTO_U4IA_R1_REVIEW`

## Scope

U4-I-A-R1 is a zero-SKU-touch contract gate. This branch does not implement an apply endpoint and does not edit any official SKU write path.

Changes made in this branch:

- Ledger/report only

Changes intentionally not made:

- No SKU model edits
- No SKU service or repository edits
- No `sku_imports` / `apply_import` edits
- No U4 intake service edits that write official SKUs
- No migration
- No frontend changes
- No deployment

## GitNexus Risk Finding

Pre-edit GitNexus impact for the `SKU` model returned `HIGH` risk:

```text
target: Class:backend/models/sku.py:SKU
impactedCount: 97
direct: 29
affected process: apply_import
risk: HIGH
```

Decision: `SKU` is a protected core master-data symbol. U4-I-A/R1 must not directly edit it, and must not edit existing SKU write paths. Any later SKU-write implementation requires expanded GitNexus review and cross-environment runtime proof before CTO approval.

Additional pre-edit signals:

- `IntakeService`: `MEDIUM` impact, mostly U4 parser/preview tests and `backend/api/v1/intake.py`
- `create_workspace`: `LOW` impact
- `apply_import`: `LOW` symbol-level upstream impact, but it is part of the HIGH-impact SKU process blast radius

## Apply Contract Proposal

Permission:

- Future U4 apply must require both `intake:update` and `skus:import`.
- `intake:create` cannot apply because creating/staging a workspace is not permission to mutate official master data.
- `intake:read` cannot apply because read access must remain non-mutating.
- `intake:update` alone is insufficient because U4 staging updates are lower risk than official SKU creation.
- `skus:import` alone is insufficient because the actor must also have authority over the intake workspace lifecycle.

Eligibility:

- Workspace status must be `READY_FOR_EXPORT`.
- Blocking validation issue count must be `0`.
- Mapped rows must exist.
- Rows with invalid price, barcode, unit, or SKU code must block apply.
- Rows missing required SKU master-data fields must block apply.
- Validation must be based on current staged rows and current mapping, not stale client-submitted summaries.

Duplicate SKU MVP rule:

- MVP behavior must fail closed if any staged SKU code already exists in official `skus`.
- No silent overwrite.
- No skip-and-continue behavior for U4 MVP.
- Upsert can be considered later only with explicit CTO approval and an additional update permission contract.

Idempotency:

- Repeated apply request must not duplicate official SKUs.
- If a workspace is already applied, response must be deterministic: either `ALREADY_APPLIED` or the previous immutable apply result.
- A retry after transport failure must not create a second copy of any SKU.

Atomicity:

- All valid staged rows apply atomically, or none apply.
- No partial SKU writes if row N fails.
- No partial workspace status update if a SKU insert fails.
- Apply must run inside one tenant transaction with commit/rollback owned by the existing request transaction lifecycle.

Audit trail:

- Workspace apply lifecycle should record `applied_at`, `applied_by`, and `apply_result`.
- Current intake schema does not expose dedicated `applied_at`, `applied_by`, or `apply_result` columns on U4 intake workspaces.
- U4-I-B needs CTO approval before adding either dedicated columns or an apply audit table.
- Existing `metadata` could technically hold provisional data, but that is not recommended as the durable contract for official SKU mutation audit.

Current U4 boundary:

- U4-D/U4-E/U4-F behavior remains staging-only until a later explicit U4 apply endpoint lands.
- U4-I-A-R1 introduces no code path that writes official SKUs.

## Current Code Audit

U4 intake endpoint audit:

```text
rg "SKU\(|from models\.sku|import SKU|sku_import|ImportService|apply_import|intake_public|public_token|public token|skus" backend/api/v1/intake.py
INTAKE_NO_SKU_OR_PUBLIC_APPLY_SURFACE
```

Conclusion: current U4 intake routes do not import SKU code, do not call import/apply services, do not reference `skus`, and do not expose public token/apply surfaces.

U3 SKU import apply audit:

```text
backend/api/v1/sku_imports.py contains:
- module note: All endpoints use RequirePermission("skus:import") per U3-B1 contract.
- async def apply_import(...)
- token dependency: RequirePermission("skus:import")
- service = ImportService()
- on_conflict support for skip/fail
```

Conclusion: existing U3 `apply_import` is separate from U4 intake and already gated by `skus:import`. U4-I-A-R1 does not edit or reuse it.

Apply audit schema audit:

```text
rg "applied_at|applied_by|apply_result" backend/models/intake.py backend/alembic/versions/024_intake_skeleton.py
INTAKE_APPLY_AUDIT_COLUMNS_ABSENT
```

Conclusion: the current U4 intake schema cannot represent a first-class apply lifecycle without either a future migration or an explicit decision to store provisional data in `metadata`.

Public token audit:

- No U4 intake public token path is introduced in this branch.
- Existing U4 intake API remains internal-login-only and permission-gated by `intake:create`, `intake:update`, and `intake:read`.

## Next Implementation Recommendation

U4-I-B should choose one CTO-approved implementation route before any SKU write code lands:

- Option 1: safely reuse U3 import apply service behind a U4-specific adapter that enforces U4 eligibility, duplicate fail-closed behavior, and U4 audit semantics.
- Option 2: build a new isolated U4 apply service with no dependency on U3 import behavior, then prove it with expanded GitNexus and runtime coverage.

Before U4-I-B, CTO must approve the apply audit storage decision:

- Add dedicated `applied_at`, `applied_by`, and `apply_result` fields to `intake_workspaces`; or
- Add a separate tenant-scoped intake apply audit table; or
- Explicitly accept `metadata` as temporary storage with a later migration plan.

Any SKU-write implementation requires:

- Expanded GitNexus impact review across `SKU`, SKU service/repository, U3 import apply, U4 intake, orders, inventory, and tests.
- Contract tests for permissions, eligibility, duplicate fail-closed behavior, idempotency, atomicity, and audit writes.
- Cross-environment runtime proof that no partial official SKU writes occur on failure.
- Explicit verification that U4 staging-only behavior remains unchanged until the apply endpoint is intentionally enabled.

## Validation

Planned validation for this zero-code report branch:

- `git diff --check`
- ASCII/mojibake scan for this report
- secret scan for this report/diff
- `npx gitnexus analyze`
- `npx gitnexus status`
- pre-commit hooks on commit, if available

No pytest was added or run because this branch intentionally contains report-only changes and no production/test code changes.
