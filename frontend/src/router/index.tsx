import { createBrowserRouter } from 'react-router-dom'
import App from '../App'
import { LoginPage } from '../pages/auth/LoginPage'
import { DashboardPage } from '../pages/DashboardPage'
import { RetailerDashboard } from '../pages/RetailerDashboard'
import { WholesalerDashboard } from '../pages/WholesalerDashboard'
import { UsersPage } from '../pages/users/UsersPage'
import { V0Playground } from '../pages/V0Playground'
import { ProtectedRoute } from '../components/auth/ProtectedRoute'

export const router = createBrowserRouter([
  {
    path: '/login',
    element: <LoginPage />,
  },
  {
    path: '/',
    element: (
      <ProtectedRoute>
        <App />
      </ProtectedRoute>
    ),
    children: [
      {
        index: true,
        element: <DashboardPage />,
      },
      {
        path: 'retailer',
        element: <RetailerDashboard />,
      },
      {
        path: 'wholesaler',
        element: <WholesalerDashboard />,
      },
      {
        path: 'users',
        element: <UsersPage />,
      },
      {
        path: 'v0-playground',
        element: <V0Playground />,
      },
      // 其他路由将在后续添加
    ],
  },
])