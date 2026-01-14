import api from './api'
import { User } from '../types/auth'

export const userService = {
  // Get users list (Wholesaler only)
  getUsers: async (): Promise<User[]> => {
    const response = await api.get('/users')
    return response.data
  }
}
