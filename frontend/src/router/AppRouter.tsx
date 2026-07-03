import { createBrowserRouter, RouterProvider } from 'react-router-dom';
import { ProtectedRoute, PublicRoute } from '@/router/guards';
import { MainLayout } from '@/components/layout/MainLayout';
import { ClientLayout } from '@/components/layout/ClientLayout';
import { LoginPage } from '@/pages/auth/LoginPage';
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
import { NotFoundPage } from '@/pages/NotFoundPage';
// Client App pages (Retailer-facing)
import { ClientLoginPage } from '@/pages/client/ClientLoginPage';
import { ProductListPage } from '@/pages/client/ProductListPage';
import { ProductDetailPage } from '@/pages/client/ProductDetailPage';
import { CreateOrderPage as ClientCreateOrderPage } from '@/pages/client/CreateOrderPage';
import { ClientOrderListPage } from '@/pages/client/OrderListPage';
import { OrderDetailPage } from '@/pages/client/OrderDetailPage';

const router = createBrowserRouter([
  {
    element: <PublicRoute />,
    children: [
      { path: '/login', element: <LoginPage /> },
    ],
  },
  // Client login - separate from wholesaler login
  {
    path: '/client/login',
    element: <ClientLoginPage />,
  },
  // Workspace selector - after login, but before app
  {
    path: '/select-workspace',
    element: <WorkspaceSelectorPage />,
  },
  // Invite page - public, no auth required
  {
    path: '/invite/:code',
    element: <InvitePage />,
  },
  // Wholesaler ERP routes
  {
    element: <ProtectedRoute />,
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
        ],
      },
      // Client App routes (Retailer-facing, mobile-friendly layout)
      {
        element: <ClientLayout />,
        children: [
          { path: '/client', element: <ProductListPage /> },
          { path: '/client/products/:productId', element: <ProductDetailPage /> },
          { path: '/client/orders', element: <ClientOrderListPage /> },
          { path: '/client/orders/new', element: <ClientCreateOrderPage /> },
          { path: '/client/orders/:orderId', element: <OrderDetailPage /> },
        ],
      },
    ],
  },
  {
    path: '*',
    element: <NotFoundPage />,
  },
]);

export function AppRouter() {
  return <RouterProvider router={router} />;
}
