# PW1-R2 Phase 1 — Direct caller census (grep, complements GitNexus call-graph)
# GitNexus indexed: 15118 nodes / 45321 edges @ d2e7e44; TS/TSX JSX composition is file-level only —
# impact_*: upstream impact per symbol saved alongside; risk for auth surface treated as CRITICAL regardless of graph count.

## useAuthStore
  file: src\components\layout\ClientLayout.tsx
  file: src\components\layout\Header.tsx
  file: src\components\layout\Sidebar.tsx
  file: src\components\layout\__tests__\SidebarApprovals.test.tsx
  file: src\components\layout\__tests__\SidebarOps.test.tsx
  file: src\pages\DashboardPage.tsx
  file: src\pages\auth\LoginPage.tsx
  file: src\pages\auth\WorkspaceSelectorPage.tsx
  file: src\pages\client\ClientLoginPage.tsx
  file: src\pages\inventory\InventoryPage.tsx
  file: src\pages\orders\CreateOrderPage.tsx
  file: src\pages\orders\OrderListPage.tsx
  file: src\pages\platform\PlatformApprovalsPage.tsx
  file: src\pages\platform\PlatformDurableApprovalsPage.tsx
  file: src\pages\platform\PlatformIncidentCloseoutsPage.tsx
  file: src\pages\platform\PlatformOperatorTasksPage.tsx
  file: src\pages\platform\__tests__\PlatformApprovalsPage.test.tsx
  file: src\pages\platform\__tests__\PlatformControlledExecutionNav.test.tsx
  file: src\pages\platform\__tests__\PlatformDurableApprovalsPage.test.tsx
  file: src\pages\platform\__tests__\PlatformIncidentCloseoutsNav.test.tsx
  file: src\pages\platform\__tests__\PlatformIncidentCloseoutsPage.test.tsx
  file: src\pages\platform\__tests__\PlatformOperatorTasksNav.test.tsx
  file: src\pages\platform\__tests__\PlatformOperatorTasksPage.test.tsx
  file: src\pages\platform\__tests__\SupportConsolePage.test.tsx
  file: src\pages\platform\__tests__\p25\__helpers__\readiness.tsx
  file: src\pages\pricing\RetailerPricingPage.tsx
  file: src\pages\skus\DataIntakePage.tsx
  file: src\pages\skus\SKUListPage.tsx
  file: src\pages\tenants\TenantListPage.tsx
  file: src\router\__tests__\guards.test.tsx
  file: src\router\guards.tsx
  file: src\services\api.ts
  file: src\stores\authStore.ts
  file: src\tests\DataIntakePage.test.tsx
  file: src\tests\Dc12r1S2RetailerPortal.test.tsx
  file: src\tests\Dc12r1S3S2ClientFinance.test.tsx
  file: src\tests\H3PaymentPermissionContract.test.tsx
  file: src\tests\Header.test.tsx
  file: src\tests\PrintableWorkspace.test.tsx
  file: src\tests\S5BRealUserSmoke.test.tsx
  file: src\tests\SKUListPage.test.tsx
  file: src\tests\StatementPrintWorkspace.test.tsx
  file: src\tests\TenantListPage.test.tsx
  total_refs: 187

## updateTokens
  file: src\pages\auth\LoginPage.tsx
  file: src\pages\auth\WorkspaceSelectorPage.tsx
  file: src\services\api.ts
  file: src\stores\authStore.ts
  file: src\tests\SKUListPage.test.tsx
  total_refs: 8

## PublicRoute
  file: src\router\AppRouter.tsx
  file: src\router\guards.tsx
  total_refs: 4

## ProtectedRoute
  file: src\components\layout\MainLayout.tsx
  file: src\pages\auth\LoginPage.tsx
  file: src\router\AppRouter.tsx
  file: src\router\guards.tsx
  total_refs: 7

## WholesalerRoute
  file: src\router\AppRouter.tsx
  file: src\router\guards.tsx
  file: src\tests\Dc12r1S2RetailerPortal.test.tsx
  file: src\tests\PrintableWorkspace.test.tsx
  total_refs: 11

## RetailerRoute
  file: src\router\AppRouter.tsx
  file: src\router\guards.tsx
  file: src\tests\Dc12r1S2RetailerPortal.test.tsx
  file: src\tests\PrintableWorkspace.test.tsx
  file: src\tests\StatementPrintWorkspace.test.tsx
  total_refs: 13

## WorkspaceSelectorPage
  file: src\pages\auth\WorkspaceSelectorPage.tsx
  file: src\router\AppRouter.tsx
  total_refs: 3

## from '@/pages/auth/LoginPage'
  file: src\router\AppRouter.tsx
  file: src\tests\CredentialLifecyclePages.test.tsx
  total_refs: 2

