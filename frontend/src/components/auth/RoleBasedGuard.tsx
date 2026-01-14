import React from 'react'
import { useRoleBasedAccess } from '../../hooks/useRoleBasedAccess'

interface RoleBasedGuardProps {
  children: React.ReactNode
  requiredRole?: 'retailer' | 'wholesaler'
  permission?: 'canCreateOrder' | 'canManageOrders' | 'canViewUsers'
  fallback?: React.ReactNode
}

export const RoleBasedGuard: React.FC<RoleBasedGuardProps> = ({
  children,
  requiredRole,
  permission,
  fallback = null,
}) => {
  const { role, canCreateOrder, canManageOrders, canViewUsers } = useRoleBasedAccess()

  // Check role requirement
  if (requiredRole && role !== requiredRole) {
    return <>{fallback}</>
  }

  // Check permission requirement
  if (permission) {
    const hasPermission = {
      canCreateOrder,
      canManageOrders,
      canViewUsers,
    }[permission]

    if (!hasPermission) {
      return <>{fallback}</>
    }
  }

  return <>{children}</>
}
