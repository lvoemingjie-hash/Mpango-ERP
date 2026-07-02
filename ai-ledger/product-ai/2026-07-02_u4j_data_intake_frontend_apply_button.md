# U4-J Data Intake Frontend Apply Button

Date: 2026-07-02

Branch: `opencode/u4j-data-intake-frontend-apply-button-2026-07-02`

Base: `origin/product-dev-recovered` at `e3d92c8` (`merge: U4-I-B2 intake apply service`)

Verdict: PASS_FOR_CTO_U4J_REVIEW

## Scope

Implemented the Data Intake frontend integration for the verified backend apply endpoint:

- Added `POST /intake/workspaces/{workspaceId}/apply` to the frontend intake service.
- Added an `Apply to Products` section on the Data Intake page after mapping exists.
- Kept apply unavailable until validation returns `READY_FOR_EXPORT`, there are no blocking issues, and the user has both `intake:update` and `skus:import`.
- Added a required confirmation dialog before calling apply.
- Added success feedback for created Product/SKU count and created SKU IDs.
- Added friendly errors for `ALREADY_APPLIED`, `DUPLICATE_STAGED_SKU_CODE`, `SKU_CODE_EXISTS`, and `BLOCKING_ISSUES`.
- Added tests for hidden/unavailable states, permissions, confirmation, double-submit prevention, success feedback, and friendly backend errors.

## Files Changed

- `frontend/src/pages/skus/DataIntakePage.tsx`
- `frontend/src/services/intakeService.ts`
- `frontend/src/tests/DataIntakePage.test.tsx`
- `ai-ledger/product-ai/2026-07-02_u4j_data_intake_frontend_apply_button.md`

No backend files, migrations, deployment files, public credential flows, image/PWA/mobile scan paths, or multilingual files were changed.

## UI Safeguards

- The apply button is not rendered before `READY_FOR_EXPORT`.
- Blocking issues and validation errors keep apply unavailable.
- Missing `intake:update` or `skus:import` keeps apply unavailable.
- Successful apply stores the apply result and removes the apply action from the UI.
- The confirmation dialog explicitly states that the action writes to official Products/SKUs, duplicate existing SKU codes are blocked, and there is no silent overwrite, upsert, or merge.
- Duplicate submit prevention uses an immediate `useRef` lock plus disabled button state while the apply request is in flight.

## GitNexus

Pre-edit impact checks were completed before modifying the frontend files:

- `DataIntakePage`: LOW impact.
- `intakeService`: target not found by symbol lookup; manually inspected as the frontend intake API boundary.
- Related helper lookups were LOW or unresolved/ambiguous and did not indicate backend changes were needed.

Post-edit checks:

- `npx gitnexus analyze`: already up to date after the final edit; earlier refresh indexed `6,278 nodes`, `17,987 edges`, `409 clusters`, and `227 flows`.
- `npx gitnexus status`: up to date at commit `e3d92c8`.

## Validation

- `pnpm exec vitest run src/tests/DataIntakePage.test.tsx`: PASS, 14 tests passed.
- `pnpm build`: PASS.
- `git diff --check`: PASS; only Git CRLF working-copy warnings were printed.
- ASCII scan changed files: PASS, no non-ASCII found.
- Mojibake scan changed files: PASS, no mojibake found.
- Sensitive-value scan changed files: PASS; only fake auth placeholders in the test store setup were reported.
- `pre-commit run --files frontend/src/pages/skus/DataIntakePage.tsx frontend/src/services/intakeService.ts frontend/src/tests/DataIntakePage.test.tsx`: PASS, including the credential detection hook.

Build warnings observed but not introduced by this change:

- Browserslist data is 6 months old.
- Vite chunk size warning for the main bundle over 500 kB.

## Residual Risks

- This is a frontend-only change; backend endpoint behavior is assumed from U4-I-B2 on the required base.
- No browser/manual visual pass was performed because the requested validation centered on unit tests, build, static scans, and GitNexus checks.
- No deploy was performed.

## R1 Apply UX Guard Completion

CTO finding:

- Apply failures with HTTP 403 reused the generic intake workspace permission message, which did not identify the two required apply permissions.
- `BLOCKING_ISSUES` apply error handling existed in the page but was not covered by an apply test.
- Generic HTTP 403 apply failures were not covered by an apply test.

R1 fix:

- Added `applyFriendlyError()` for the apply request path only.
- `handleConfirmApply()` now reports: `You need both intake:update and skus:import to apply staged rows to Products.` for HTTP 403 apply failures.
- Existing non-apply HTTP 403 flows continue to use the generic intake workspace permission guidance.
- Added explicit tests for apply `BLOCKING_ISSUES` and apply HTTP 403 guidance.

R1 validation:

- `pnpm exec vitest run src/tests/DataIntakePage.test.tsx`: PASS, 16 tests passed.
- `pnpm build`: PASS.
- No backend changes, migrations, deploy steps, public credential flows, image/PWA/mobile scan paths, or multilingual files were introduced.
