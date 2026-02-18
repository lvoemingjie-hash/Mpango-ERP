import { createBrowserRouter, RouterProvider } from 'react-router-dom';
import { ProtectedRoute, PublicRoute } from '@/router/guards';
import { MainLayout } from '@/components/layout/MainLayout';
import { LoginPage } from '@/pages/auth/LoginPage';
import { DashboardPage } from '@/pages/DashboardPage';
import { OrderListPage } from '@/pages/orders/OrderListPage';
import { InventoryPage } from '@/pages/inventory/InventoryPage';
import { TenantListPage } from '@/pages/tenants/TenantListPage';
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
