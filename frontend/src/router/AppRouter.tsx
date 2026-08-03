import { createBrowserRouter, RouterProvider, Navigate, useSearchParams } from 'react-router-dom';
import { ProtectedRoute, PublicRoute, PlatformRoute, RetailerRoute, WholesalerRoute } from '@/router/guards';
import { MainLayout } from '@/components/layout/MainLayout';
import { ClientLayout } from '@/components/layout/ClientLayout';
import { LoginPage } from '@/pages/auth/LoginPage';
import { ForgotPasswordPage } from '@/pages/auth/ForgotPasswordPage';
import { ResetPasswordPage } from '@/pages/auth/ResetPasswordPage';
import { SetupCredentialPage } from '@/pages/auth/SetupCredentialPage';
import { VerifyEmailPage } from '@/pages/auth/VerifyEmailPage';
import { WorkspaceSelectorPage } from '@/pages/auth/WorkspaceSelectorPage';
import { DashboardPage } from '@/pages/DashboardPage';
import { OrderListPage } from '@/pages/orders/OrderListPage';
import { CreateOrderPage as WholesalerCreateOrderPage } from '@/pages/orders/CreateOrderPage';
import { InventoryPage } from '@/pages/inventory/InventoryPage';
import { InventoryLogPage } from '@/pages/inventory/InventoryLogPage';
import { SKUListPage } from '@/pages/skus/SKUListPage';
import { DataIntakePage } from '@/pages/skus/DataIntakePage';
import { MobileScanPreview } from '@/pages/skus/MobileScanPreview';
import { TenantListPage } from '@/pages/tenants/TenantListPage';
import { RetailerListPage } from '@/pages/retailers/RetailerListPage';
import { RetailerPricingPage } from '@/pages/pricing/RetailerPricingPage';
import { InvitePage } from '@/pages/invite/InvitePage';
import { FinancePage } from '@/pages/finance/FinancePage';
import { PaymentListPage } from '@/pages/finance/PaymentListPage';
import { DeclarationQueuePage } from '@/pages/finance/DeclarationQueuePage';
import { NotFoundPage } from '@/pages/NotFoundPage';
// Client App pages (Retailer-facing)
import { ClientLoginPage } from '@/pages/client/ClientLoginPage';
import { ProductListPage } from '@/pages/client/ProductListPage';
import { ProductDetailPage } from '@/pages/client/ProductDetailPage';
import { CreateOrderPage as ClientCreateOrderPage } from '@/pages/client/CreateOrderPage';
import { ClientOrderListPage } from '@/pages/client/OrderListPage';
import { OrderDetailPage } from '@/pages/client/OrderDetailPage';
import { ClientPaymentHistoryPage } from '@/pages/client/PaymentHistoryPage';
import { ClientFinanceBalancePage } from '@/pages/client/FinanceBalancePage';
import { DeclarationHistoryPage } from '@/pages/client/DeclarationHistoryPage';
import { DeclarePaymentPage } from '@/pages/client/DeclarePaymentPage';
// DC-12R1-S1: retailer credential setup/reset pages (fragment-only token transport)
import { RetailerSetupCredentialPage } from '@/pages/retailer/RetailerSetupCredentialPage';
import { RetailerResetPasswordPage } from '@/pages/retailer/RetailerResetPasswordPage';
// Platform Admin Cockpit pages (P11)
import { PlatformOverviewPage } from '@/pages/platform/PlatformOverviewPage';
import { PlatformTenantDirectoryPage } from '@/pages/platform/PlatformTenantDirectoryPage';
import { PlatformAuditEventsPage } from '@/pages/platform/PlatformAuditEventsPage';
import { PlatformTenantHealthPage } from '@/pages/platform/PlatformTenantHealthPage';
import { PlatformSystemHealthPage } from '@/pages/platform/PlatformSystemHealthPage';
import { SupportConsolePage } from '@/pages/platform/SupportConsolePage';
import { PlatformRegistryPage } from '@/pages/platform/PlatformRegistryPage';
import { PlatformControlledActionsPage } from '@/pages/platform/PlatformControlledActionsPage';
import { PlatformApprovalsPage } from '@/pages/platform/PlatformApprovalsPage';
import { PlatformDurableApprovalsPage } from '@/pages/platform/PlatformDurableApprovalsPage';
import { PlatformControlledExecutionConsolePage } from '@/pages/platform/PlatformControlledExecutionConsolePage';
import { PlatformOperatorTasksPage } from '@/pages/platform/PlatformOperatorTasksPage';
import { PlatformIncidentCloseoutsPage } from '@/pages/platform/PlatformIncidentCloseoutsPage';
// P13 Operations Cockpit pages
import { OpsHealthPage } from '@/pages/platform/ops/OpsHealthPage';
import { OpsErrorsPage } from '@/pages/platform/ops/OpsErrorsPage';
import { OpsSlowRoutesPage } from '@/pages/platform/ops/OpsSlowRoutesPage';
import { OpsResourcesPage } from '@/pages/platform/ops/OpsResourcesPage';
import { OpsNoisyNeighborsPage } from '@/pages/platform/ops/OpsNoisyNeighborsPage';
import { IncidentTriagePage } from '@/pages/platform/ops/IncidentTriagePage';

const router = createBrowserRouter([
  {
    element: <PublicRoute />,
    children: [
      { path: '/login', element: <LoginPage /> },
      { path: '/forgot-password', element: <ForgotPasswordPage /> },
      { path: '/reset-password', element: <ResetPasswordPage /> },
      { path: '/setup-credential', element: <SetupCredentialPage /> },
      { path: '/verify-email', element: <VerifyEmailPage /> },
      // DC-12R1-S1: retailer credential setup/reset (fragment-only token)
      { path: '/retailer/setup-credential', element: <RetailerSetupCredentialPage /> },
      { path: '/retailer/reset-password', element: <RetailerResetPasswordPage /> },
    ],
  },
  // DC-12R1-S2: /retail/login?w=<code> is the canonical retailer portal entry.
  {
    path: '/retail/login',
    element: <ClientLoginPage />,
  },
  // /client/login is kept as a compatibility redirect/alias preserving `w`.
  {
    path: '/client/login',
    element: <ClientLoginAliasRedirect />,
  },
  // Workspace selector -- after login, but before app
  {
    path: '/select-workspace',
    element: <WorkspaceSelectorPage />,
  },
  // Invite page -- public, no auth required
  {
    path: '/invite/:code',
    element: <InvitePage />,
  },
  // Wholesaler ERP routes
  {
    element: <ProtectedRoute />,
    children: [
      {
        // DC-12R1-S2: retailer_operator must not enter wholesaler ERP routes.
        element: <WholesalerRoute />,
        children: [
          {
            element: <MainLayout />,
            children: [
              { path: '/', element: <DashboardPage /> },
              { path: '/orders', element: <OrderListPage /> },
              { path: '/orders/new', element: <WholesalerCreateOrderPage /> },
              { path: '/inventory', element: <InventoryPage /> },
              { path: '/inventory/logs', element: <InventoryLogPage /> },
              { path: '/skus', element: <SKUListPage /> },
              { path: '/skus/intake', element: <DataIntakePage /> },
              { path: '/skus/scan', element: <MobileScanPreview /> },
              { path: '/retailers', element: <RetailerListPage /> },
              { path: '/pricing', element: <RetailerPricingPage /> },
              { path: '/tenants', element: <TenantListPage /> },
              { path: '/finance', element: <FinancePage /> },
              { path: '/payments', element: <PaymentListPage /> },
              { path: '/declarations', element: <DeclarationQueuePage /> },
            ],
          },
        ],
      },
      // Client App routes (Retailer-facing, mobile-friendly layout)
      // DC-12R1-S2: only retailer_operator may enter /client/**.
      {
        element: <RetailerRoute />,
        children: [
          {
            element: <ClientLayout />,
            children: [
              { path: '/client', element: <ProductListPage /> },
              { path: '/client/products/:productId', element: <ProductDetailPage /> },
              { path: '/client/orders', element: <ClientOrderListPage /> },
              { path: '/client/orders/new', element: <ClientCreateOrderPage /> },
              { path: '/client/orders/:orderId', element: <OrderDetailPage /> },
              { path: '/client/payments', element: <ClientPaymentHistoryPage /> },
              { path: '/client/finance', element: <ClientFinanceBalancePage /> },
              { path: '/client/declarations', element: <DeclarationHistoryPage /> },
              { path: '/client/orders/:orderId/declare', element: <DeclarePaymentPage /> },
            ],
          },
        ],
      },
      // Platform Admin Cockpit routes (P11) -- super_admin only
      {
        element: <PlatformRoute />,
        children: [
          {
            element: <MainLayout />,
            children: [
              { path: '/platform', element: <PlatformOverviewPage /> },
              { path: '/platform/tenants', element: <PlatformTenantDirectoryPage /> },
              { path: '/platform/audit', element: <PlatformAuditEventsPage /> },
              { path: '/platform/tenants/:tenantId/health', element: <PlatformTenantHealthPage /> },
              { path: '/platform/system/health', element: <PlatformSystemHealthPage /> },
              { path: '/platform/support', element: <SupportConsolePage /> },
              // P17 Platform Registry route (read-only, identity-only super_admin)
              { path: '/platform/registry', element: <PlatformRegistryPage /> },
              // P18 Controlled Actions route (request skeleton, identity-only super_admin)
              { path: '/platform/controlled-actions', element: <PlatformControlledActionsPage /> },
              // P19 Approval Workflow route (approval console, identity-only super_admin)
              { path: '/platform/approvals', element: <PlatformApprovalsPage /> },
              // P20 Durable Approval Governance route (durable approval console,
              // identity-only super_admin; maker-checker + quorum; not executed)
              { path: '/platform/durable-approvals', element: <PlatformDurableApprovalsPage /> },
              // P22 Controlled Execution route (non-executing operator console,
              // identity-only super_admin; dry-run + record request; never executes)
              {
                path: '/platform/controlled-execution',
                element: <PlatformControlledExecutionConsolePage />,
              },
              // P23 Operator Task / Notification Queue route (view, not executor;
              // record, not delivery; identity-only super_admin; triage console;
              // never executes / decides / delivers)
              {
                path: '/platform/operator-tasks',
                element: <PlatformOperatorTasksPage />,
              },
              // P24 Incident + Runbook Closeout route (view, not executor; pointer,
              // not execution; record, not repair; identity-only super_admin;
              // closeout + step triage console; never executes / decides / clears
              // flag / delivers)
              {
                path: '/platform/incident-closeouts',
                element: <PlatformIncidentCloseoutsPage />,
              },
              // P13 Operations Cockpit routes
              { path: '/platform/ops/health', element: <OpsHealthPage /> },
              { path: '/platform/ops/errors', element: <OpsErrorsPage /> },
              { path: '/platform/ops/slow-routes', element: <OpsSlowRoutesPage /> },
              { path: '/platform/ops/resources', element: <OpsResourcesPage /> },
              { path: '/platform/ops/noisy-neighbors', element: <OpsNoisyNeighborsPage /> },
              { path: '/platform/ops/incidents/triage', element: <IncidentTriagePage /> },
            ],
          },
        ],
      },
    ],
  },
  {
    path: '*',
    element: <NotFoundPage />,
  },
]);

/**
 * DC-12R1-S2: /client/login compatibility alias. Preserves the `w` query
 * param and redirects to the canonical /retail/login entry, so legacy
 * supplier links keep working and the portal code is not lost.
 */
function ClientLoginAliasRedirect() {
  const [searchParams] = useSearchParams();
  const w = searchParams.get('w');
  const target = w ? `/retail/login?w=${encodeURIComponent(w)}` : '/retail/login';
  return <Navigate to={target} replace />;
}

export function AppRouter() {
  return <RouterProvider router={router} />;
}
