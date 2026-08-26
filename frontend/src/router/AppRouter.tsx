import { createBrowserRouter, RouterProvider, Navigate, useSearchParams } from 'react-router-dom';
import { ProtectedRoute, PublicRoute, PlatformRoute, RetailerRoute, RetailerPermissionRoute, WholesalerRoute, WholesalerPermissionRoute } from '@/router/guards';
import { CLIENT_PERMISSIONS, INVITATION_PERMISSIONS } from '@/utils/permissions';
import { MainLayout } from '@/components/layout/MainLayout';
import { ClientLayout } from '@/components/layout/ClientLayout';
import { LoginPage } from '@/pages/auth/LoginPage';
import { SignupPage } from '@/pages/auth/SignupPage';
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
// DC-12R1-MVP-L1-J1-H2-A: wholesaler-side invitation authoring page
import { InviteCreatePage } from '@/pages/retailers/InviteCreatePage';
import { RetailerPricingPage } from '@/pages/pricing/RetailerPricingPage';
import { InvitePage } from '@/pages/invite/InvitePage';
// DC-12R1-MVP-L1-J1-H2-A: public invitation landing page (fragment-only code)
import { InvitationLandingPage } from '@/pages/invite/InvitationLandingPage';
import { FinancePage } from '@/pages/finance/FinancePage';
import { PaymentListPage } from '@/pages/finance/PaymentListPage';
import DeclarationQueuePage from '@/pages/finance/DeclarationQueuePage';
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
import DeclarationHistoryPage from '@/pages/client/DeclarationHistoryPage';
import DeclarePaymentPage from '@/pages/client/DeclarePaymentPage';
// DC-12R1-S3-S2B-I2C-I2: printable workspace views (Contracts A–C).
import { OrderPrintPage } from '@/pages/print/OrderPrintPage';
import { DeclarationPrintPage } from '@/pages/print/DeclarationPrintPage';
import { ReceiptPrintPage } from '@/pages/print/ReceiptPrintPage';
// DC-12R1-S3-S2B-I2C-I2B: printable relationship account statement (Contract D).
import { StatementPrintPage } from '@/pages/print/StatementPrintPage';
// DC-12R1-S1: retailer credential setup/reset pages (fragment-only token transport)
import { RetailerSetupCredentialPage } from '@/pages/retailer/RetailerSetupCredentialPage';
// DC-12R1-MVP-L1-J1-H2-A-R1: public dual-entry retailer self-join.
import { RetailerJoinPage } from '@/pages/retailer/RetailerJoinPage';
// DC-12R1-MVP-L1-J1-H2-C-R1: public retailer forgot-password discovery page.
import { RetailerForgotPasswordPage } from '@/pages/retailer/RetailerForgotPasswordPage';
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
      // DC-12R1-MVP-L1-J1-R1: public wholesaler self-service signup entry.
      // Closes the dead onboarding tenant-creation cold-start gap: a
      // first-time wholesaler now starts through this page via
      // POST /auth/signup.
      { path: '/signup', element: <SignupPage /> },
      { path: '/forgot-password', element: <ForgotPasswordPage /> },
      { path: '/reset-password', element: <ResetPasswordPage /> },
      { path: '/setup-credential', element: <SetupCredentialPage /> },
      { path: '/verify-email', element: <VerifyEmailPage /> },
      // DC-12R1-S1: retailer credential setup/reset (fragment-only token)
      { path: '/retailer/setup-credential', element: <RetailerSetupCredentialPage /> },
      { path: '/retailer/forgot-password', element: <RetailerForgotPasswordPage /> },
      { path: '/retailer/reset-password', element: <RetailerResetPasswordPage /> },
    ],
  },
  // DC-12R1-S2: /retail/login?w=<code> is the canonical retailer portal entry.
  {
    path: '/retail/login',
    element: <ClientLoginPage />,
  },
  // DC-12R1-MVP-L1-J1-H2-A-R1: /retail/join is the public dual-entry
  // self-join page (invitation link OR public supplier code). Credentials
  // (invitation code / join intent) travel only in JSON bodies.
  {
    path: '/retail/join',
    element: <RetailerJoinPage />,
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
  // DC-12R1-MVP-L1-J1-H2-A: /invite is the CANONICAL retailer entry. The
  // invitation code travels in the URL fragment only (/invite#code=...), is
  // captured and scrubbed on mount, and is then used exclusively in JSON
  // bodies (POST /invitations/lookup, POST /retailers/register).
  {
    path: '/invite',
    element: <InvitationLandingPage />,
  },
  // DEPRECATED compatibility entry (path token): retained only so links
  // issued by older builds keep working. New product UI must NEVER generate
  // this format — use /invite#code=<opaque-code> instead.
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
              // DC-12R1-MVP-L1-J1-H2-A: wholesaler invitation authoring.
              // Fail closed without invitations:create — the page never
              // mounts, so its POST /invitations submit cannot fire; the
              // backend enforces RequirePermission independently.
              {
                element: <WholesalerPermissionRoute permission={INVITATION_PERMISSIONS.CREATE} />,
                children: [
                  { path: '/retailers/invite', element: <InviteCreatePage /> },
                ],
              },
              { path: '/pricing', element: <RetailerPricingPage /> },
              { path: '/tenants', element: <TenantListPage /> },
              { path: '/finance', element: <FinancePage /> },
              { path: '/payments', element: <PaymentListPage /> },
              { path: '/declarations', element: <DeclarationQueuePage /> },
              // DC-12R1-S3-S2B-I2C-I2: cashier printable workspace (Contracts A–C).
              // mode is fixed by static route config (never a query param).
              { path: '/orders/:orderId/print', element: <OrderPrintPage mode="cashier" /> },
              { path: '/declarations/:declarationId/print', element: <DeclarationPrintPage mode="cashier" /> },
              { path: '/declarations/:declarationId/receipt', element: <ReceiptPrintPage mode="cashier" /> },
              // DC-12R1-S3-S2B-I2C-I2B: cashier relationship statement (Contract D).
              // mode is fixed by static route config; retailer_id/from/to are
              // read-only query inputs for the GET (never route/mode switches).
              { path: '/statements/print', element: <StatementPrintPage mode="cashier" /> },
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
              // DC-12R1-MVP-R0-R1 (WPR-003): the payment-declaration submission
              // page requires client:payments:declare. Fail closed before render
              // so a permission-empty user can never reach the form (zero POST).
              {
                element: <RetailerPermissionRoute permission={CLIENT_PERMISSIONS.PAYMENTS_DECLARE} />,
                children: [
                  { path: '/client/orders/:orderId/declare', element: <DeclarePaymentPage /> },
                ],
              },
              // DC-12R1-S3-S2B-I2C-I2: retailer printable workspace (Contracts A–C).
              // mode is fixed by static route config (never a query param).
              // WPR-002: each print route is admission-checked against the same
              // client:* permission its backend GET endpoint requires.
              {
                element: <RetailerPermissionRoute permission={CLIENT_PERMISSIONS.ORDERS_READ} />,
                children: [
                  { path: '/client/orders/:orderId/print', element: <OrderPrintPage mode="client" /> },
                ],
              },
              {
                element: <RetailerPermissionRoute permission={CLIENT_PERMISSIONS.PAYMENTS_READ} />,
                children: [
                  { path: '/client/declarations/:declarationId/print', element: <DeclarationPrintPage mode="client" /> },
                  { path: '/client/declarations/:declarationId/receipt', element: <ReceiptPrintPage mode="client" /> },
                ],
              },
              // DC-12R1-S3-S2B-I2C-I2B: retailer relationship statement (Contract D).
              // mode is fixed by static route config; from/to are read-only
              // query inputs for the GET (the retailer identity is server-derived).
              {
                element: <RetailerPermissionRoute permission={CLIENT_PERMISSIONS.FINANCE_READ} />,
                children: [
                  { path: '/client/statements/print', element: <StatementPrintPage mode="client" /> },
                ],
              },
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
