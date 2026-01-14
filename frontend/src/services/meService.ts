import api from './api'
import { User } from '../types/auth'

export const meService = {
  // Get current user info with role and tenant
  getMe: async (): Promise<User> => {
    const response = await api.get('/auth/me')
    return response.data
  }
}
