export interface OrderItem {
  product_id: string
  quantity: number
  unit_price: number
}

export interface CreateOrderRequest {
  items: OrderItem[]
  notes?: string
}

export interface Order {
  id: string
  tenant_id: string
  user_id: string
  status: 'pending' | 'confirmed' | 'shipped' | 'cancelled'
  items: OrderItem[]
  total_amount: number
  notes?: string
  created_at: string
  updated_at: string
}

export interface OrderStatusTransition {
  status: Order['status']
  allowed_actions: ('confirm' | 'ship' | 'cancel')[]
}

// Role-based permissions
export interface UserRole {
  id: string
  email: string
  full_name?: string
  role: 'retailer' | 'wholesaler'
  tenant_id: string
  tenant_schema: string
  is_active: boolean
}
