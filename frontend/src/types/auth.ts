/**
 * Auth types — mirrors backend schemas/auth.py exactly.
 * See openapi.yaml §Auth schemas.
 */

export interface LoginRequest {
  tenant_code: string;
  email: string;
  password: string;
}

export interface TokenData {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user_id: string;
  tenant_id: string;
  tenant_schema: string;
}

export interface LoginResponse {
  success: boolean;
  data: TokenData;
  timestamp: string;
}

export interface RefreshTokenRequest {
  refresh_token: string;
}

export interface CurrentUserData {
  id: string;
  email: string;
  full_name: string | null;
  tenant_id: string;
  tenant_schema: string;
  roles: string[];
  permissions: string[];
}

export interface CurrentUserResponse {
  success: boolean;
  data: CurrentUserData;
  timestamp: string;
}
