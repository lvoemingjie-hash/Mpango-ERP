import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore'

export const DashboardPage: React.FC = () => {
  const { role, isAuthenticated } = useAuthStore()
  const navigate = useNavigate()

  useEffect(() => {
    if (isAuthenticated && role) {
      // Redirect to role-specific dashboard
      if (role === 'retailer') {
        navigate('/retailer')
      } else if (role === 'wholesaler') {
        navigate('/wholesaler')
      }
    }
  }, [role, isAuthenticated, navigate])

  // Show loading while redirecting
  return (
    <div className="flex justify-center items-center h-64">
      <div className="text-gray-500">Redirecting to your dashboard...</div>
    </div>
  )
}
