# PW1-R2-R1 — api.ts request interceptor upstream impact

## GitNexus
- 'api' symbol resolves to backend Folder:backend/api (name collision); impacted 0.
- api.ts graph coverage: only processQueue indexed; the anonymous request-interceptor closure is not a named graph symbol.
- Conclusion: graph-level impact unusable for this TS closure; grep census is the authoritative caller inventory (documented limitation, consistent with PW1-R2 Phase 1).

## Grep census — every consumer of the shared axios instance (interceptor callers)
```
frontend/src\components\platform\__tests__\SupportBundleCard.test.tsx
frontend/src\components\platform\__tests__\SupportDiagnosticsPanel.test.tsx
frontend/src\pages\invite\InvitePage.tsx
frontend/src\pages\platform\__tests__\PlatformApprovalsPage.test.tsx
frontend/src\pages\platform\__tests__\PlatformControlledActionsPage.test.tsx
frontend/src\pages\platform\__tests__\PlatformControlledExecutionConsolePage.test.tsx
frontend/src\pages\platform\__tests__\PlatformDurableApprovalsPage.test.tsx
frontend/src\pages\platform\__tests__\PlatformIncidentCloseoutsPage.test.tsx
frontend/src\pages\platform\__tests__\PlatformOperatorTasksPage.test.tsx
frontend/src\pages\platform\__tests__\PlatformRegistryPage.test.tsx
frontend/src\pages\platform\__tests__\SupportConsolePage.test.tsx
frontend/src\pages\platform\__tests__\p25\P25_CopySafety.test.tsx
frontend/src\pages\platform\__tests__\p25\P25_ForbiddenControls.test.tsx
frontend/src\pages\platform\__tests__\p25\P25_RecordedDefects.test.tsx
frontend/src\pages\platform\__tests__\p25\P25_StateMatrix.test.tsx
frontend/src\pages\platform\ops\__tests__\IncidentTriagePage.test.tsx
frontend/src\services\__tests__\platformApi.test.ts
frontend/src\services\__tests__\platformControlledExecutionApi.test.ts
frontend/src\services\__tests__\platformIncidentCloseoutsApi.test.ts
frontend/src\services\__tests__\platformOperatorTasksApi.test.ts
frontend/src\services\__tests__\platformOpsApi.test.ts
frontend/src\services\__tests__\platformRegistryApi.test.ts
frontend/src\services\__tests__\supportApi.test.ts
frontend/src\services\authService.ts
frontend/src\services\clientFinanceService.ts
frontend/src\services\clientOrderService.ts
frontend/src\services\clientProductService.ts
frontend/src\services\dashboardService.ts
frontend/src\services\financeService.ts
frontend/src\services\intakeService.ts
frontend/src\services\inventoryService.ts
frontend/src\services\orderService.ts
frontend/src\services\paymentService.ts
frontend/src\services\pricingService.ts
frontend/src\services\retailerService.ts
frontend/src\services\skuImportService.ts
frontend/src\services\skuService.ts
frontend/src\services\statementService.ts
frontend/src\services\tenantService.ts
frontend/src\tests\Dc12r1S3S2ClientFinance.test.tsx
frontend/src\tests\H3PaymentPermissionContract.test.tsx
frontend/src\tests\PrintableWorkspace.test.tsx
frontend/src\tests\Pw1R2AuthSessionClosure.test.tsx
frontend/src\tests\S5BRealUserSmoke.test.tsx
frontend/src\tests\StatementPrintWorkspace.test.tsx
```
Total importer files (incl. tests): 45
Production service modules on the shared instance: 20

## Change-surface analysis
- The interceptor edit only affects requests WITHOUT an explicit Authorization header (behavior unchanged: store token injected).
- Requests WITH explicit Authorization (authService.login-caller paths: selectTenant(token), me(token)) now preserve the caller value instead of being overwritten.
- Refresh retry path sets originalRequest.headers.Authorization explicitly then re-dispatches; interceptor sees an existing header AND the store already holds the refreshed token — both resolve to refreshed-token; no regression path.
