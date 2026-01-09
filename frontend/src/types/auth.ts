export interface LoginRequest {
  tenant_code: string
  email: string
  password: string
}

export interface LoginResponse {
  access_token: string
  refresh_token: string
  token_type: string
  user_id: string
  tenant_id: string
  tenant_schema: string
}

export interface User {
  id: string
  email: string
  full_name?: string
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface AuthState {
  user: User | null
  token: string | null
  isAuthenticated: boolean
  tenant_id: string | null
  tenant_schema: string | null
}