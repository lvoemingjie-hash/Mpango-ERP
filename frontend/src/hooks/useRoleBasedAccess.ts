import { useAuthStore } from '../stores/authStore'

export const useRoleBasedAccess = () => {
  const { user, role } = useAuthStore()

  const isRetailer = role === 'retailer'
  const isWholesaler = role === 'wholesaler'
  const canCreateOrder = isRetailer
  const canManageOrders = isWholesaler
  const canViewUsers = isWholesaler

  const canPerformOrderAction = (action: 'confirm' | 'ship' | 'cancel', orderStatus: string) => {
    if (!isWholesaler) return false
    
    switch (orderStatus) {
      case 'pending':
        return action === 'confirm' || action === 'cancel'
      case 'confirmed':
        return action === 'ship' || action === 'cancel'
      case 'shipped':
      case 'cancelled':
        return false
      default:
        return false
    }
  }

  return {
    user,
    role,
    isRetailer,
    isWholesaler,
    canCreateOrder,
    canManageOrders,
    canViewUsers,
    canPerformOrderAction,
  }
}
