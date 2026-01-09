import { useEffect } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuthStore } from '../../stores/authStore'

interface ProtectedRouteProps {
  children: React.ReactNode
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ children }) => {
  const { isAuthenticated, token, refreshToken } = useAuthStore()

  useEffect(() => {
    // 如果有token但未认证，尝试刷新token
    if (token && !isAuthenticated) {
      refreshToken()
    }
  }, [token, isAuthenticated, refreshToken])

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  return <>{children}</>
}