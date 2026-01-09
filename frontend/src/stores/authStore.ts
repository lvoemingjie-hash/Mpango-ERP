import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { AuthState, LoginRequest, User } from '../types/auth'
import { authService } from '../services/authService'

interface AuthStore extends AuthState {
  login: (loginData: LoginRequest) => Promise<void>
  logout: () => void
  refreshToken: () => Promise<void>
  setUser: (user: User) => void
  loading: boolean
  error: string | null
}

export const useAuthStore = create<AuthStore>()(
  persist(
    (set, get) => ({
      user: null,
      token: null,
      isAuthenticated: false,
      tenant_id: null,
      tenant_schema: null,
      loading: false,
      error: null,

      login: async (loginData: LoginRequest) => {
        set({ loading: true, error: null })
        try {
          const response = await authService.login(loginData)
          
          // 存储令牌到localStorage
          localStorage.setItem('access_token', response.access_token)
          localStorage.setItem('refresh_token', response.refresh_token)
          
          set({
            token: response.access_token,
            isAuthenticated: true,
            tenant_id: response.tenant_id,
            tenant_schema: response.tenant_schema,
            loading: false,
          })
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
        localStorage.removeItem('user_info')
        
        // 重置状态
        set({
          user: null,
          token: null,
          isAuthenticated: false,
          tenant_id: null,
          tenant_schema: null,
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
          
          localStorage.setItem('access_token', response.access_token)
          localStorage.setItem('refresh_token', response.refresh_token)
          
          set({
            token: response.access_token,
            isAuthenticated: true,
          })
        } catch (error) {
          get().logout()
        }
      },

      setUser: (user: User) => {
        set({ user })
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
      }),
    }
  )
)