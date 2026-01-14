import React, { useState } from 'react'
import { Order } from '../../types/order'
import { orderService } from '../../services/orderService'
import { useRoleBasedAccess } from '../../hooks/useRoleBasedAccess'

interface OrderDetailModalProps {
  order: Order
  onClose: () => void
  onUpdate: () => void
}

export const OrderDetailModal: React.FC<OrderDetailModalProps> = ({
  order,
  onClose,
  onUpdate,
}) => {
  const { canPerformOrderAction } = useRoleBasedAccess()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pendingActions, setPendingActions] = useState<Set<string>>(new Set())

  const handleAction = async (action: 'confirm' | 'ship' | 'cancel') => {
    if (!canPerformOrderAction(action, order.status)) {
      setError('Action not allowed')
      return
    }

    // Prevent duplicate requests
    const actionKey = `${order.id}-${action}`
    if (pendingActions.has(actionKey)) {
      return
    }

    // Immediately add to pending actions to prevent duplicates
    setPendingActions(prev => new Set(prev).add(actionKey))
    setLoading(true)
    setError(null)

    try {
      switch (action) {
        case 'confirm':
          await orderService.confirmOrder(order.id)
          break
        case 'ship':
          await orderService.shipOrder(order.id)
          break
        case 'cancel':
          await orderService.cancelOrder(order.id)
          break
      }
      
      onUpdate()
      onClose()
    } catch (err: any) {
      setError(err.response?.data?.detail || `Failed to ${action} order`)
    } finally {
      // Remove from pending actions and reset loading
      setPendingActions(prev => {
        const newSet = new Set(prev)
        newSet.delete(actionKey)
        return newSet
      })
      setLoading(false)
    }
  }

  const getStatusColor = (status: Order['status']) => {
    switch (status) {
      case 'pending':
        return 'bg-yellow-100 text-yellow-800'
      case 'confirmed':
        return 'bg-blue-100 text-blue-800'
      case 'shipped':
        return 'bg-green-100 text-green-800'
      case 'cancelled':
        return 'bg-red-100 text-red-800'
      default:
        return 'bg-gray-100 text-gray-800'
    }
  }

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleString()
  }

  return (
    <div className="fixed inset-0 bg-gray-600 bg-opacity-50 overflow-y-auto h-full w-full z-50">
      <div className="relative top-20 mx-auto p-5 border w-11/12 md:w-3/4 lg:w-1/2 shadow-lg rounded-md bg-white">
        <div className="mt-3">
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-lg leading-6 font-medium text-gray-900">
              Order Details
            </h3>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-500"
            >
              <span className="sr-only">Close</span>
              <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          {error && (
            <div className="mb-4 p-3 bg-red-100 border border-red-400 text-red-700 rounded">
              {error}
            </div>
          )}

          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <dt className="text-sm font-medium text-gray-500">Order ID</dt>
                <dd className="mt-1 text-sm text-gray-900">{order.id}</dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-gray-500">Status</dt>
                <dd className="mt-1">
                  <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getStatusColor(order.status)}`}>
                    {order.status}
                  </span>
                </dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-gray-500">Created</dt>
                <dd className="mt-1 text-sm text-gray-900">{formatDate(order.created_at)}</dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-gray-500">Last Updated</dt>
                <dd className="mt-1 text-sm text-gray-900">{formatDate(order.updated_at)}</dd>
              </div>
            </div>

            <div>
              <dt className="text-sm font-medium text-gray-500 mb-2">Items</dt>
              <div className="border rounded-lg overflow-hidden">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                        Product ID
                      </th>
                      <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                        Quantity
                      </th>
                      <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                        Unit Price
                      </th>
                      <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                        Total
                      </th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-200">
                    {order.items.map((item, index) => (
                      <tr key={index}>
                        <td className="px-4 py-2 text-sm text-gray-900">{item.product_id}</td>
                        <td className="px-4 py-2 text-sm text-gray-900">{item.quantity}</td>
                        <td className="px-4 py-2 text-sm text-gray-900">${item.unit_price.toFixed(2)}</td>
                        <td className="px-4 py-2 text-sm text-gray-900">
                          ${(item.quantity * item.unit_price).toFixed(2)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="border-t pt-4">
              <div className="flex justify-between items-center">
                <dt className="text-sm font-medium text-gray-500">Total Amount</dt>
                <dd className="text-lg font-semibold text-gray-900">
                  ${order.total_amount.toFixed(2)}
                </dd>
              </div>
            </div>

            {order.notes && (
              <div>
                <dt className="text-sm font-medium text-gray-500">Notes</dt>
                <dd className="mt-1 text-sm text-gray-900">{order.notes}</dd>
              </div>
            )}

            <div className="border-t pt-4">
              <dt className="text-sm font-medium text-gray-500 mb-2">Order Actions</dt>
              <div className="flex gap-2">
                {canPerformOrderAction('confirm', order.status) && (
                  <button
                    onClick={() => handleAction('confirm')}
                    disabled={loading || pendingActions.has(`${order.id}-confirm`)}
                    className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
                  >
                    {pendingActions.has(`${order.id}-confirm`) ? 'Processing...' : 'Confirm'}
                  </button>
                )}
                {canPerformOrderAction('ship', order.status) && (
                  <button
                    onClick={() => handleAction('ship')}
                    disabled={loading || pendingActions.has(`${order.id}-ship`)}
                    className="px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 disabled:opacity-50"
                  >
                    {pendingActions.has(`${order.id}-ship`) ? 'Processing...' : 'Ship'}
                  </button>
                )}
                {canPerformOrderAction('cancel', order.status) && (
                  <button
                    onClick={() => handleAction('cancel')}
                    disabled={loading || pendingActions.has(`${order.id}-cancel`)}
                    className="px-4 py-2 bg-red-600 text-white rounded-md hover:bg-red-700 disabled:opacity-50"
                  >
                    {pendingActions.has(`${order.id}-cancel`) ? 'Processing...' : 'Cancel'}
                  </button>
                )}
              </div>
            </div>
          </div>

          <div className="mt-6 flex justify-end">
            <button
              onClick={onClose}
              className="px-4 py-2 bg-gray-600 text-white rounded-md hover:bg-gray-700"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
