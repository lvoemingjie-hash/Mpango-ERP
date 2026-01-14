import React, { useState } from 'react'
import { useRoleBasedAccess } from '../../hooks/useRoleBasedAccess'
import { orderService } from '../../services/orderService'
import { CreateOrderRequest, OrderItem } from '../../types/order'

interface CreateOrderFormProps {
  onSuccess?: () => void
}

export const CreateOrderForm: React.FC<CreateOrderFormProps> = ({ onSuccess }) => {
  const { canCreateOrder } = useRoleBasedAccess()
  const [items, setItems] = useState<OrderItem[]>([
    { product_id: '', quantity: 1, unit_price: 0 }
  ])
  const [notes, setNotes] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  const addItem = () => {
    setItems([...items, { product_id: '', quantity: 1, unit_price: 0 }])
  }

  const removeItem = (index: number) => {
    setItems(items.filter((_, i) => i !== index))
  }

  const updateItem = (index: number, field: keyof OrderItem, value: string | number) => {
    const newItems = [...items]
    newItems[index] = { ...newItems[index], [field]: value }
    setItems(newItems)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    
    if (!canCreateOrder) {
      setError('You do not have permission to create orders')
      return
    }

    // Prevent duplicate submissions
    if (isSubmitting) {
      return
    }

    // Validate items
    const validItems = items.filter(item => item.product_id && item.quantity > 0 && item.unit_price > 0)
    if (validItems.length === 0) {
      setError('Please add at least one valid item')
      return
    }

    // Immediately set submitting state to prevent duplicates
    setIsSubmitting(true)
    setLoading(true)
    setError(null)

    try {
      const orderData: CreateOrderRequest = {
        items: validItems,
        notes: notes.trim() || undefined
      }

      await orderService.createOrder(orderData)
      
      // Reset form
      setItems([{ product_id: '', quantity: 1, unit_price: 0 }])
      setNotes('')
      
      onSuccess?.()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to create order')
    } finally {
      setIsSubmitting(false)
      setLoading(false)
    }
  }

  if (!canCreateOrder) {
    return (
      <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
        <p className="text-yellow-800">You do not have permission to create orders.</p>
      </div>
    )
  }

  return (
    <div className="bg-white shadow rounded-lg p-6">
      <h2 className="text-lg font-semibold text-gray-900 mb-4">Create New Order</h2>
      
      {error && (
        <div className="mb-4 p-3 bg-red-100 border border-red-400 text-red-700 rounded">
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Order Items
          </label>
          {items.map((item, index) => (
            <div key={index} className="flex gap-2 mb-2">
              <input
                type="text"
                placeholder="Product ID"
                value={item.product_id}
                onChange={(e) => updateItem(index, 'product_id', e.target.value)}
                className="flex-1 p-2 border rounded-md"
                required
              />
              <input
                type="number"
                placeholder="Quantity"
                value={item.quantity}
                onChange={(e) => updateItem(index, 'quantity', parseInt(e.target.value) || 0)}
                className="w-24 p-2 border rounded-md"
                min="1"
                required
              />
              <input
                type="number"
                placeholder="Unit Price"
                value={item.unit_price}
                onChange={(e) => updateItem(index, 'unit_price', parseFloat(e.target.value) || 0)}
                className="w-32 p-2 border rounded-md"
                min="0"
                step="0.01"
                required
              />
              {items.length > 1 && (
                <button
                  type="button"
                  onClick={() => removeItem(index)}
                  className="px-3 py-2 bg-red-600 text-white rounded-md hover:bg-red-700"
                >
                  Remove
                </button>
              )}
            </div>
          ))}
          <button
            type="button"
            onClick={addItem}
            className="mt-2 px-4 py-2 bg-gray-600 text-white rounded-md hover:bg-gray-700"
          >
            Add Item
          </button>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Notes (optional)
          </label>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            className="w-full p-2 border rounded-md"
            rows={3}
            placeholder="Add any notes about this order..."
          />
        </div>

        <div className="flex gap-2">
          <button
            type="submit"
            disabled={loading || isSubmitting}
            className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
          >
            {isSubmitting ? 'Creating...' : 'Create Order'}
          </button>
        </div>
      </form>
    </div>
  )
}
