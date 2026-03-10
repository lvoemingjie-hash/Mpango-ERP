import { createBrowserRouter, RouterProvider } from 'react-router-dom';
import { ProtectedRoute, PublicRoute } from '@/router/guards';
import { MainLayout } from '@/components/layout/MainLayout';
import { LoginPage } from '@/pages/auth/LoginPage';
import { WorkspaceSelectorPage } from '@/pages/auth/WorkspaceSelectorPage';
import { DashboardPage } from '@/pages/DashboardPage';
import { OrderListPage } from '@/pages/orders/OrderListPage';
import { InventoryPage } from '@/pages/inventory/InventoryPage';
import { SKUListPage } from '@/pages/skus/SKUListPage';
import { TenantListPage } from '@/pages/tenants/TenantListPage';
import { RetailerListPage } from '@/pages/retailers/RetailerListPage';
import { InvitePage } from '@/pages/invite/InvitePage';
import { FinancePage } from '@/pages/finance/FinancePage';
import { NotFoundPage } from '@/pages/NotFoundPage';

const router = createBrowserRouter([
  {
    element: <PublicRoute />,
    children: [
      { path: '/login', element: <LoginPage /> },
    ],
  },
  // Workspace selector — after login, but before app
  {
    path: '/select-workspace',
    element: <WorkspaceSelectorPage />,
  },
  // Invite page — public, no auth required
  {
    path: '/invite/:code',
    element: <InvitePage />,
  },
  {
    element: <ProtectedRoute />,
    children: [
      {
        element: <MainLayout />,
        children: [
          { path: '/', element: <DashboardPage /> },
          { path: '/orders', element: <OrderListPage /> },
          { path: '/inventory', element: <InventoryPage /> },
          { path: '/skus', element: <SKUListPage /> },
          { path: '/retailers', element: <RetailerListPage /> },
          { path: '/tenants', element: <TenantListPage /> },
          { path: '/finance', element: <FinancePage /> },
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
