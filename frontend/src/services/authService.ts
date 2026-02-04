import api from './api'
import { LoginRequest, LoginResponse } from '../types/auth'

export const authService = {
  login: async (loginData: LoginRequest): Promise<LoginResponse> => {
    const response = await api.post('/auth/login', loginData)
    return response.data
  },

  refreshToken: async (refreshToken: string): Promise<LoginResponse> => {
    const response = await api.post('/auth/refresh', { refresh_token: refreshToken })
    return response.data
  },

  logout: async (): Promise<void> => {
    await api.post('/auth/logout')
  },
}
