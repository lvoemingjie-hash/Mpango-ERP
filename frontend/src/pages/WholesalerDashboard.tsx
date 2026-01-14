import React from 'react'
import { useAuthStore } from '../stores/authStore'
import { OrderList } from '../components/orders/OrderList'
import { UserList } from '../components/users/UserList'
import { RoleBasedGuard } from '../components/auth/RoleBasedGuard'

export const WholesalerDashboard: React.FC = () => {
  const { user, tenant_schema } = useAuthStore()

  return (
    <RoleBasedGuard requiredRole="wholesaler">
      <div>
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-gray-900">Wholesaler Dashboard</h1>
          <p className="mt-1 text-sm text-gray-600">
            Manage orders, users, and oversee your wholesale operations.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <div className="bg-white overflow-hidden shadow rounded-lg">
            <div className="p-5">
              <div className="flex items-center">
                <div className="flex-shrink-0">
                  <div className="w-8 h-8 bg-purple-500 rounded-md flex items-center justify-center">
                    <span className="text-white text-sm font-medium">W</span>
                  </div>
                </div>
                <div className="ml-5 w-0 flex-1">
                  <dl>
                    <dt className="text-sm font-medium text-gray-500 truncate">Your Role</dt>
                    <dd className="text-lg font-medium text-gray-900">Wholesaler</dd>
                  </dl>
                </div>
              </div>
            </div>
          </div>

          <div className="bg-white overflow-hidden shadow rounded-lg">
            <div className="p-5">
              <div className="flex items-center">
                <div className="flex-shrink-0">
                  <div className="w-8 h-8 bg-green-500 rounded-md flex items-center justify-center">
                    <span className="text-white text-sm font-medium">T</span>
                  </div>
                </div>
                <div className="ml-5 w-0 flex-1">
                  <dl>
                    <dt className="text-sm font-medium text-gray-500 truncate">Tenant</dt>
                    <dd className="text-lg font-medium text-gray-900">{tenant_schema}</dd>
                  </dl>
                </div>
              </div>
            </div>
          </div>

          <div className="bg-white overflow-hidden shadow rounded-lg">
            <div className="p-5">
              <div className="flex items-center">
                <div className="flex-shrink-0">
                  <div className="w-8 h-8 bg-indigo-500 rounded-md flex items-center justify-center">
                    <span className="text-white text-sm font-medium">U</span>
                  </div>
                </div>
                <div className="ml-5 w-0 flex-1">
                  <dl>
                    <dt className="text-sm font-medium text-gray-500 truncate">User</dt>
                    <dd className="text-lg font-medium text-gray-900">{user?.full_name || user?.email}</dd>
                  </dl>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="space-y-8">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 mb-4">Order Management</h2>
            <OrderList />
          </div>

          <div>
            <h2 className="text-lg font-semibold text-gray-900 mb-4">User Management</h2>
            <UserList />
          </div>
        </div>
      </div>
    </RoleBasedGuard>
  )
}
