import api from './api'
import { Order, CreateOrderRequest } from '../types/order'

export const orderService = {
  // Create order (Retailer only)
  createOrder: async (orderData: CreateOrderRequest): Promise<Order> => {
    const response = await api.post('/orders', orderData)
    return response.data
  },

  // Get orders list (both roles)
  getOrders: async (): Promise<Order[]> => {
    const response = await api.get('/orders')
    return response.data
  },

  // Get order detail (both roles)
  getOrder: async (orderId: string): Promise<Order> => {
    const response = await api.get(`/orders/${orderId}`)
    return response.data
  },

  // Order lifecycle actions (Wholesaler only)
  confirmOrder: async (orderId: string): Promise<Order> => {
    const response = await api.post(`/orders/${orderId}/confirm`)
    return response.data
  },

  shipOrder: async (orderId: string): Promise<Order> => {
    const response = await api.post(`/orders/${orderId}/ship`)
    return response.data
  },

  cancelOrder: async (orderId: string): Promise<Order> => {
    const response = await api.post(`/orders/${orderId}/cancel`)
    return response.data
  },

  // Get allowed actions for order status
  getAllowedActions: (status: Order['status']): ('confirm' | 'ship' | 'cancel')[] => {
    switch (status) {
      case 'pending':
        return ['confirm', 'cancel']
      case 'confirmed':
        return ['ship', 'cancel']
      case 'shipped':
      case 'cancelled':
        return []
      default:
        return []
    }
  }
}
