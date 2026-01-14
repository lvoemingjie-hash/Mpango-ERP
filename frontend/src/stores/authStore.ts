import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { AuthState, LoginRequest, User } from '../types/auth'
import { authService } from '../services/authService'
import { meService } from '../services/meService'

interface AuthStore extends AuthState {
  login: (loginData: LoginRequest) => Promise<void>
  logout: () => void
  refreshToken: () => Promise<void>
  fetchUser: () => Promise<void>
  loading: boolean
  error: string | null
  setupTokenRefresh: () => void
  initializeAuth: () => void
}

export const useAuthStore = create<AuthStore>()(
  persist(
    (set, get) => ({
      user: null,
      token: null,
      isAuthenticated: false,
      tenant_id: null,
      tenant_schema: null,
      role: null,
      tokenExpiresAt: null,
      loading: false,
      error: null,

      login: async (loginData: LoginRequest) => {
        set({ loading: true, error: null })
        try {
          const response = await authService.login(loginData)
          
          // Calculate token expiration time
          const expiresAt = response.expires_in 
            ? Date.now() + (response.expires_in * 1000)
            : Date.now() + (3600 * 1000) // Default 1 hour if not provided
          
          // 存储令牌到localStorage
          localStorage.setItem('access_token', response.access_token)
          localStorage.setItem('refresh_token', response.refresh_token)
          localStorage.setItem('token_expires_at', expiresAt.toString())
          
          set({
            token: response.access_token,
            isAuthenticated: true,
            tenant_id: response.tenant_id,
            tenant_schema: response.tenant_schema,
            tokenExpiresAt: expiresAt,
            loading: false,
          })

          // Fetch user info with role
          await get().fetchUser()
          
          // Set up automatic token refresh
          get().setupTokenRefresh()
        } catch (error: any) {
          set({
            error: error.response?.data?.detail || 'Login failed',
            loading: false,
          })
          throw error
        }
      },

      logout: () => {
        // 清除本地存储
        localStorage.removeItem('access_token')
        localStorage.removeItem('refresh_token')
        localStorage.removeItem('token_expires_at')
        localStorage.removeItem('user_info')
        
        // 重置状态
        set({
          user: null,
          token: null,
          isAuthenticated: false,
          tenant_id: null,
          tenant_schema: null,
          role: null,
          tokenExpiresAt: null,
          error: null,
        })
        
        // 调用后端登出接口（可选）
        authService.logout().catch(console.error)
      },

      refreshToken: async () => {
        const refreshToken = localStorage.getItem('refresh_token')
        if (!refreshToken) {
          get().logout()
          return
        }

        try {
          const response = await authService.refreshToken(refreshToken)
          
          // Calculate new expiration time
          const expiresAt = response.expires_in 
            ? Date.now() + (response.expires_in * 1000)
            : Date.now() + (3600 * 1000) // Default 1 hour
          
          localStorage.setItem('access_token', response.access_token)
          localStorage.setItem('refresh_token', response.refresh_token)
          localStorage.setItem('token_expires_at', expiresAt.toString())
          
          set({
            token: response.access_token,
            isAuthenticated: true,
            tokenExpiresAt: expiresAt,
          })
          
          // Set up next refresh
          get().setupTokenRefresh()
        } catch (error) {
          get().logout()
        }
      },

      setupTokenRefresh: () => {
        const { tokenExpiresAt } = get()
        if (!tokenExpiresAt) return

        const now = Date.now()
        const timeUntilExpiry = tokenExpiresAt - now
        
        // If token expires in less than 5 minutes, refresh now
        if (timeUntilExpiry < 5 * 60 * 1000) {
          get().refreshToken()
          return
        }

        // Set up refresh 1 minute before expiry
        const refreshTime = timeUntilExpiry - (60 * 1000)
        setTimeout(() => {
          get().refreshToken()
        }, refreshTime)
      },

      fetchUser: async () => {
        try {
          const user = await meService.getMe()
          set({
            user,
            role: user.role,
          })
        } catch (error) {
          console.error('Failed to fetch user info:', error)
          // Don't logout on me fetch failure, just log error
        }
      },

      setUser: (user: User) => {
        set({ user, role: user.role })
      },

      initializeAuth: () => {
        const token = localStorage.getItem('access_token')
        const expiresAt = localStorage.getItem('token_expires_at')
        
        if (token && expiresAt) {
          const expiryTime = parseInt(expiresAt)
          const now = Date.now()
          
          // If token is expired or will expire soon, refresh now
          if (expiryTime <= now || (expiryTime - now) < 5 * 60 * 1000) {
            get().refreshToken()
          } else {
            // Set up refresh for later
            get().setupTokenRefresh()
          }
        }
      },
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({
        user: state.user,
        token: state.token,
        isAuthenticated: state.isAuthenticated,
        tenant_id: state.tenant_id,
        tenant_schema: state.tenant_schema,
        role: state.role,
        tokenExpiresAt: state.tokenExpiresAt,
      }),
    }
  )
)