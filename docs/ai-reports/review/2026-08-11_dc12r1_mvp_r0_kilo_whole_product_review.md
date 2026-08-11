# DC-12R1-MVP-R0 Pre-Pilot Whole-Product Readiness Review

**Verdict:** `PASS_FOR_CTO_DC12R1_MVP_R0_LOCAL_REHEARSAL`

## Scope and evidence rules

- Review mode: independent adversarial source, architecture, test-authenticity, and technical-debt review.
- Frozen baseline reviewed: `origin/product-dev-recovered@d796dcb0d8ecc4ddffc2f82a67e90170c9cdb60f`
- Accepted product-code merge contained in baseline: `adcc7f281c661897ad050a8278686375b611edb5`
- Report branch: `reports/dc12r1-mvp-r0-kilo-whole-product-review-2026-08-11`
- No candidate source, migration, config, or dependency edits were made.
- I did **not** claim every source line was manually reviewed.

### Evidence legend

- **EXECUTED** — independently executed on this host.
- **GITNEXUS** — independently traced via `npx gitnexus analyze/status/query/context`.
- **STATIC** — source inspection only.
- **HISTORICAL-AUTH** — historical report/evidence reconciled against current source.
- **ENV-GATED** — runtime proof intentionally not manufactured on this host.

## SHA, ancestry, and protected-ref proof

### EXECUTED proof

- `git rev-parse HEAD` on the report branch after checkout from `origin/product-dev-recovered` returned `d796dcb0d8ecc4ddffc2f82a67e90170c9cdb60f`.
- `git rev-list --parents -n 1 d796dcb0d8ecc4ddffc2f82a67e90170c9cdb60f` returned:
  - child: `d796dcb0d8ecc4ddffc2f82a67e90170c9cdb60f`
  - parent 1: `adcc7f281c661897ad050a8278686375b611edb5`
  - parent 2: `0777759d2da9a7699fcd9fa49b20f39c7da2e3ec`
- `git merge-base --is-ancestor adcc7f281c661897ad050a8278686375b611edb5 HEAD` exited `0`.
- Protected refs remained at:
  - `origin/product-dev-recovered` -> `d796dcb0d8ecc4ddffc2f82a67e90170c9cdb60f`
  - `origin/main` -> `134ea59e02204842e55ebe36f721f44df5a33737`
  - `origin/platform-dev` -> `12c5ee557876498240b1a36cc850d030d7bd8293`

### GitNexus proof

- `npx gitnexus analyze` completed successfully on this checkout.
- `npx gitnexus status` reported the index up to date at commit `d796dcb`.

## Architecture and critical-flow coverage matrix

| Flow / area | Coverage | Key evidence | Outcome |
|---|---|---|---|
| Tenant provisioning and first-admin lifecycle | GITNEXUS + STATIC | `TenantProvisioningService` context shows orchestration from `complete_email_verified_onboarding`; source in `backend/services/tenant_provisioning_service.py:81-315` and `backend/services/onboarding_service.py:195-244` | No blocker found |
| Wholesaler login | GITNEXUS + STATIC | `backend/api/v1/auth.py:232-310`; GitNexus context for `Function:backend/api/v1/auth.py:login` shows `find_user_across_tenants` -> identity token flow | No blocker found |
| Retailer login | GITNEXUS + STATIC | GitNexus process `proc_205_retailer_login`; source `backend/api/v1/client/auth.py:92-315` | No blocker found |
| Retailer order creation | GITNEXUS + STATIC | GitNexus query matched client order hardening/tests; source `backend/api/v1/client/orders.py` and `backend/tests/test_dc12r1_s3_s1_catalog_order_hardening.py` | No blocker found |
| Direct payment | STATIC + HISTORICAL-AUTH | Canonical payment mutation path in `backend/services/canonical_payment_service.py`; reused by declaration confirmation | No blocker found |
| Declaration submit / confirm / reject / replay | GITNEXUS + STATIC | `declare_payment` context; `backend/services/payment_declaration_service.py:167-381`; `backend/api/v1/declarations.py:297-357` | No blocker found |
| Receipt allocation and rendering | STATIC + GITNEXUS | `backend/api/v1/client/declarations.py:178-245`; `services/print_service.py`; Contract C tests | No blocker found |
| Contract D relationship statement | GITNEXUS + STATIC | GitNexus context for `print_supplier_statement`; source `backend/api/v1/statements.py:124-182`, `backend/api/v1/client/statements.py:151-198`, `repositories/statement_repository.py` | P2/P3 debt only |
| Frontend route authorization | STATIC + GITNEXUS | `frontend/src/router/AppRouter.tsx`, `frontend/src/router/guards.tsx`, printable-workspace/statement tests | P2 finding `KILO-WPR-002`, `KILO-WPR-003` |
| Migration upgrade to sole head 037 | GITNEXUS + STATIC + HISTORICAL-AUTH | GitNexus query returned `proc_132_upgrade`; source `backend/alembic/versions/037_payment_declarations_schema.py`; bootstrap parity in `backend/scripts/bootstrap_tenant_schema.py:1313-1369` | No blocker found |

## Security / tenant-isolation verdict

**Verdict:** pass with no confirmed P0/P1.

### What I verified

- Dynamic identifier validation is centralized and strict in `backend/db/sql_safety.py:1-51`.
- Tenant sessions validate schema names before `SET LOCAL search_path` in `backend/database/session.py:153-197`.
- Retailer login validates wholesaler portal code, enforces registry-to-derived-schema parity, queries only the resolved supplier schema, and issues contextual tokens only after active user/binding/role/retailer checks (`backend/api/v1/client/auth.py:96-315`).
- Tenant provisioning validates derived schema names and refuses active-idempotent completion unless the expected bootstrap tables exist (`backend/services/tenant_provisioning_service.py:132-259`).

### Security conclusion

I found no confirmed cross-tenant disclosure, identifier-injection, or role-boundary bypass in the reviewed backend flows. Residual risk remains concentrated in frontend route-policy drift rather than backend authorization bypass.

## Financial-integrity verdict

**Verdict:** pass with no confirmed P0/P1.

### What I verified

- Declaration confirmation locks by `(declaration_id, wholesaler_id)`, fails closed on wrong wholesaler, re-verifies order ownership and active binding, and delegates the actual money mutation to `CanonicalPaymentService.confirm_payment()` (`backend/services/payment_declaration_service.py:167-321`).
- Replays of already-confirmed declarations rebuild canonical results without new writes and fail closed if the linked payment/order/receipt invariants no longer hold (`backend/services/payment_declaration_service.py:323-381`).
- Migration `037_payment_declarations_schema` enforces permission rename/grant cleanup and preflight checks before mutating live tenant schemas (`backend/alembic/versions/037_payment_declarations_schema.py:7-29`, `154-220`).
- Bootstrap parity repairs the same rename/grant rules on fresh schemas (`backend/scripts/bootstrap_tenant_schema.py:1313-1335`).

### Financial conclusion

I did not find a confirmed source-level path that lets a retailer declaration mutate ledger/receivable state before supplier confirmation, nor a confirmed receipt/statement write path outside the canonical payment flow.

## Customer-journey verdict

**Verdict:** pass for local rehearsal, but with P2 UX/authorization debt.

- Retailer and wholesaler authentication/session boundaries are materially implemented.
- Retailer declaration, receipt, and statement flows exist in source and are server-authoritative.
- Real mailbox/browser proof on the latest deployed SHA remains open by project design and is still an S4 residual risk.
- Frontend guard behavior does not fully mirror backend permission requirements on some retailer routes; see `KILO-WPR-002` and `KILO-WPR-003`.

## Test-authenticity verdict

**Verdict:** mixed; no confirmed critical false-green for backend financial invariants, but there is a frontend route-policy authenticity defect.

- GitNexus index and current source align with the post-I2B/I2C-I2B evidence trail.
- I did **not** independently run PostgreSQL/Redis-backed suites on this host.
- I authenticated historical evidence against current source and found one important source/test drift: frontend router tests explicitly admit protected client print routes for a `retailer_operator` with `permissions: []`, even though backend routes require `client:orders:read`, `client:payments:read`, or `client:finance:read`. See `KILO-WPR-002`.

## Migration / bootstrap verdict

**Verdict:** pass with no confirmed migration blocker.

- `037_payment_declarations_schema` is the sole source head and is reflected in `docs/ai/PROJECT.md` and `docs/ai/CTO_CURRENT_OPS.md`.
- Fresh-bootstrap parity for renamed retailer permissions and admin confirm permission is present in bootstrap reconcile code and covered by exact-contract tests.
- I found no source evidence of a fresh-schema bootstrap leaving `client:payments:create` active on `retailer_operator` after current reconcile logic.

## Operational / deployment-readiness verdict

**Verdict:** not pilot-ready, but no new P1 source blocker was confirmed in the reviewed scope.

Still open by source/project truth:

- exact deployed-SHA real mailbox/browser proof,
- non-mainland customer hosting closure,
- formal DB-OPS package,
- dedicated platform-operator runtime lifecycle,
- current manuals/runbooks matching latest merged behavior.

Runtime deployment validation on PG/Redis/SMTP was **ENV-GATED** on this host and was not manufactured.

## Technical-debt register

| Finding | Severity | Summary |
|---|---|---|
| `KILO-WPR-001` | P2 | Current truth docs still anchor the product baseline narrative to `adcc7f28` instead of the actual frozen baseline `d796dcb`, creating review/deployment evidence drift. |
| `KILO-WPR-002` | P2 | Frontend router/tests admit retailer print routes with role-only access while backend requires specific `client:*` permissions. |
| `KILO-WPR-003` | P2 | Retailer declaration write page is reachable via role-only routing and echoes backend-provided error text instead of a fixed neutral/status-derived denial. |
| `KILO-WPR-004` | P3 | Supplier/client Contract D routes duplicate the same `_map_statement_result()` logic, increasing drift risk on a safety-critical read path. |
| `KILO-WPR-005` | INFO | Tenant-schema validation, supplier-scoped retailer login, and canonical declaration-confirmation boundaries are source-consistent. |
| `KILO-WPR-006` | INFO | Migration `037` and bootstrap reconcile logic are aligned on permission rename/grant cleanup and receipt/declaration schema foundation. |

## Findings

### KILO-WPR-001

- **Severity:** P2
- **Domain:** Documentation / operational truth
- **Classification:** stale baseline and evidence narrative drift
- **File:** `docs/ai/PROJECT.md`; `docs/ai/CTO_CURRENT_OPS.md`
- **Line:** `79`; `16`; corroborated by EXECUTED `git rev-parse HEAD`
- **Exact evidence:**
  - `docs/ai/PROJECT.md:79` says `Product code baseline | origin/product-dev-recovered@adcc7f28 ...`.
  - `docs/ai/CTO_CURRENT_OPS.md:16-17` says ``origin/product-dev-recovered@adcc7f28`` includes the accepted I2B/A-D work.
  - EXECUTED baseline checkout proved `origin/product-dev-recovered` is `d796dcb0d8ecc4ddffc2f82a67e90170c9cdb60f`, whose first parent is `adcc7f281c661897ad050a8278686375b611edb5`.
- **Execution flow:** operator/readiness review, baseline selection, evidence reconciliation, rollback/deploy package selection.
- **Customer impact:** reviewers and operators can anchor validation/runbooks to the accepted merge SHA rather than the actual frozen baseline, risking wrong evidence packets and stale rollout assumptions.
- **Reproduction or mutation strategy:** compare `git rev-parse origin/product-dev-recovered` and `git rev-list --parents -n 1 d796dcb...` against the top-level “current truth” lines in both docs.
- **Required action:** update both current-truth documents so the active baseline, accepted merge ancestry, and still-open gates describe `d796dcb` exactly.
- **Proposed owner:** CTO / docs truth owner.
- **Closure gate:** docs must name the actual baseline SHA and ancestry; post-update cross-check against `git rev-parse origin/product-dev-recovered` must be exact.

### KILO-WPR-002

- **Severity:** P2
- **Domain:** Frontend guards / route-policy drift / test authenticity
- **Classification:** role-only route admit contradicts backend permission contract
- **File:** `frontend/src/router/guards.tsx`; `frontend/src/tests/PrintableWorkspace.test.tsx`; `frontend/src/tests/StatementPrintWorkspace.test.tsx`; backend corroboration in `backend/api/v1/client/orders.py`, `backend/api/v1/client/declarations.py`, `backend/api/v1/client/statements.py`
- **Line:** `guards.tsx:75-89`; `PrintableWorkspace.test.tsx:866-990`; `StatementPrintWorkspace.test.tsx:558-679`; backend `orders.py:325-335`, `declarations.py:114-123` and `178-187`, `statements.py:151-162`
- **Exact evidence:**
  - `RetailerRoute` checks only `user.roles?.includes('retailer_operator')` (`frontend/src/router/guards.tsx:75-89`).
  - Printable-workspace tests define `RETAILER_USER` with `permissions: []` and still assert all four client print routes are admitted and issue backend GETs (`frontend/src/tests/PrintableWorkspace.test.tsx:866-990`).
  - Statement-print tests do the same for `/client/statements/print` (`frontend/src/tests/StatementPrintWorkspace.test.tsx:558-679`).
  - Backend routes require specific permissions: `client:orders:read` for order print (`backend/api/v1/client/orders.py:325-335`), `client:payments:read` for declaration/receipt (`backend/api/v1/client/declarations.py:114-123`, `178-187`), and `client:finance:read` for Contract D print (`backend/api/v1/client/statements.py:151-162`).
- **Execution flow:** frontend route authorization for Contracts A-D print views.
- **Customer impact:** a retailer session with the right role but missing one or more required `client:*` permissions can still enter client print routes and only fail later at the API boundary; the current frontend tests encode this drift as green behavior, so permission regressions can hide in the UI layer.
- **Reproduction or mutation strategy:** remove `client:finance:read` (or `client:payments:read` / `client:orders:read`) from a retailer fixture while keeping `roles=['retailer_operator']`, navigate directly to the corresponding `/client/.../print` route, and observe router admission followed by backend denial.
- **Required action:** align client print-route admission with backend permission requirements and replace role-only green tests with explicit permission-empty deny tests.
- **Proposed owner:** frontend owner + auth/RBAC owner.
- **Closure gate:** direct-route tests must fail closed for `retailer_operator` users lacking the required permission on each protected client print route, while permitted sessions still pass.

### KILO-WPR-003

- **Severity:** P2
- **Domain:** Frontend retailer write path / neutral error contract
- **Classification:** declaration submit page lacks permission-aligned guard and echoes backend-provided message text
- **File:** `frontend/src/router/AppRouter.tsx`; `frontend/src/router/guards.tsx`; `frontend/src/pages/client/DeclarePaymentPage.tsx`; `frontend/src/tests/DeclarePaymentPage.test.tsx`; backend corroboration in `backend/api/v1/client/orders.py`
- **Line:** `AppRouter.tsx:143-167`; `guards.tsx:75-89`; `DeclarePaymentPage.tsx:44-48`; backend `client/orders.py:527-539`
- **Exact evidence:**
  - `/client/orders/:orderId/declare` is admitted under the same role-only `RetailerRoute` branch (`frontend/src/router/AppRouter.tsx:143-167`; `frontend/src/router/guards.tsx:75-89`).
  - The page catch path renders `response.data.message || Error.message` directly (`frontend/src/pages/client/DeclarePaymentPage.tsx:44-48`).
  - The backend submit route requires `RequirePermission("client:payments:declare")` (`backend/api/v1/client/orders.py:527-539`).
  - `frontend/src/tests/DeclarePaymentPage.test.tsx:58-196` covers idempotency only; it does not contain a deny-path permission or neutral-error contract test.
- **Execution flow:** retailer order -> declaration submit.
- **Customer impact:** an under-scoped retailer session can reach the declaration write UI and receive backend-derived error text instead of being denied at navigation time with fixed neutral copy, creating avoidable pilot friction and UI/API contract inconsistency.
- **Reproduction or mutation strategy:** keep `roles=['retailer_operator']`, remove `client:payments:declare`, navigate directly to `/client/orders/<id>/declare`, submit once, and observe route admission plus backend-denial handling.
- **Required action:** gate the route/page by `client:payments:declare` and move declaration-page failure copy to a fixed neutral/status-derived policy instead of rendering `response.data.message` verbatim.
- **Proposed owner:** frontend owner.
- **Closure gate:** deny-path tests must prove that missing `client:payments:declare` blocks route entry or submission before any backend call, and user-visible failure copy must be status-derived and non-echoing.

### KILO-WPR-004

- **Severity:** P3
- **Domain:** Technical debt / duplicate safety logic
- **Classification:** duplicated Contract D error-to-HTTP mapping
- **File:** `backend/api/v1/statements.py`; `backend/api/v1/client/statements.py`
- **Line:** `statements.py:66-121`; `client/statements.py:89-148`
- **Exact evidence:** both modules carry near-identical `_map_statement_result()` implementations mapping `StatementPeriodError`, `StatementRangeTooLarge`, `StatementLedgerScopeIncomplete`, `StatementInternalInconsistent`, and `StatementReconciliationFailed` to the same 400/404/409 envelopes.
- **Execution flow:** supplier and retailer Contract D printable statements.
- **Customer impact:** future one-sided edits can silently diverge statement safety behavior between supplier and retailer routes.
- **Reproduction or mutation strategy:** mutate one mapper’s 409/404 handling in isolation and compare supplier vs retailer statement responses.
- **Required action:** centralize the shared mapper or add one parity test that proves both routes expose identical fail-closed status/code mapping.
- **Proposed owner:** backend owner.
- **Closure gate:** one shared helper or a parity test that fails on any mapping drift.

### KILO-WPR-005

- **Severity:** INFO
- **Domain:** Tenant isolation / auth / financial integrity
- **Classification:** verified control
- **File:** `backend/db/sql_safety.py`; `backend/database/session.py`; `backend/api/v1/client/auth.py`; `backend/services/payment_declaration_service.py`
- **Line:** `sql_safety.py:25-50`; `database/session.py:170-197`; `client/auth.py:96-315`; `payment_declaration_service.py:167-321`
- **Exact evidence:**
  - strict identifier regex validation before dynamic SQL,
  - validated tenant `search_path` setup/reset,
  - supplier-scoped retailer login with registry/schema parity and contextual JWT issuance only after active user/binding/role checks,
  - declaration confirmation re-verifying ownership/binding and delegating all money mutation to `CanonicalPaymentService.confirm_payment()`.
- **Execution flow:** tenant-bound session creation, retailer login, declaration confirm.
- **Customer impact:** positive control; I found no confirmed cross-tenant read/write bypass in these reviewed backend flows.
- **Reproduction or mutation strategy:** N/A — informational verification.
- **Required action:** retain current controls and regression coverage.
- **Proposed owner:** backend/security owners.
- **Closure gate:** maintain exact-contract tests and fail-closed behavior.

### KILO-WPR-006

- **Severity:** INFO
- **Domain:** Migration / bootstrap parity
- **Classification:** verified control
- **File:** `backend/alembic/versions/037_payment_declarations_schema.py`; `backend/scripts/bootstrap_tenant_schema.py`; `backend/tests/test_dc12r1_s3_s2b_i1_financial_schema_foundation.py`
- **Line:** `037_payment_declarations_schema.py:7-29,154-220`; `bootstrap_tenant_schema.py:1313-1369`; `test_dc12r1_s3_s2b_i1_financial_schema_foundation.py:369-425`
- **Exact evidence:** migration `037` renames `client:payments:create` -> `client:payments:declare`, grants `payments:confirm_declaration` to admin, removes stale retailer grants, and preflights registered tenant schemas; bootstrap reconcile applies the same role/permission cleanup; exact-contract tests assert the post-bootstrap role set.
- **Execution flow:** fresh tenant bootstrap and upgrade to sole head `037`.
- **Customer impact:** positive control; I found no confirmed fresh-schema parity defect in the current source.
- **Reproduction or mutation strategy:** N/A — informational verification.
- **Required action:** retain parity checks as migrations advance.
- **Proposed owner:** backend/migration owners.
- **Closure gate:** keep migration/bootstrapping parity tests green on the next head.

## Exact P0 / P1 / P2 / P3 / INFO accounting

- P0: 0
- P1: 0
- P2: 3
- P3: 1
- INFO: 2
- Reviewed findings = mapped findings: 6
- Accounting gap: 0

## Residual-risk statement

This baseline is acceptable for a CTO local rehearsal because I found no confirmed P0/P1 source blocker in tenant isolation, auth/session boundaries, canonical financial mutation, or 037/bootstrap parity. Residual risk remains in three areas: (1) frontend permission/route drift that can produce broken-but-not-bypassed retailer journeys, (2) current-truth documentation drift around the exact frozen baseline SHA, and (3) still-open non-source delivery gates such as real mailbox/browser proof, deployment/DB-OPS closure, and operator runtime readiness.
