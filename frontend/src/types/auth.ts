/**
 * Auth types — mirrors backend schemas/auth.py exactly.
 * See openapi.yaml §Auth schemas.
 */

export interface LoginRequest {
  email: string;
  password: string;
}

export interface TenantInfo {
  id: string;
  code: string;
  name: string;
}

export interface IdentityTokenData {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user_id: string;
  roles: string[];
  available_tenants: TenantInfo[];
}

export interface IdentityLoginResponse {
  success: boolean;
  data: IdentityTokenData;
  timestamp: string;
}

export interface SelectTenantRequest {
  tenant_id: string;
}

export interface TokenData {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user_id: string;
  tenant_id: string;
  tenant_schema: string;
  roles: string[];
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
  email: string | null;
  full_name: string | null;

  tenant_id: string | null;
  tenant_schema: string | null;
  roles: string[];
  permissions: string[];
}

export interface CurrentUserResponse {
  success: boolean;
  data: CurrentUserData;
  timestamp: string;
}

// ---------------------------------------------------------------------------
// DC-12R1-S2: Supplier-scoped retailer login
// ---------------------------------------------------------------------------

export interface RetailerLoginRequest {
  email: string;
  password: string;
  wholesaler_code: string;
}

export interface RetailerLoginTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user_id: string;
  tenant_id: string;
  tenant_schema: string;
  roles: string[];
}

export interface RetailerLoginUser {
  id: string;
  email: string | null;
  full_name: string | null;
  /** PW1-R4-B4: server-derived effective permission context (verbatim). */
  permissions: string[];
}

export interface RetailerLoginRetailer {
  id: string;
  name: string | null;
}

export interface RetailerLoginWholesaler {
  id: string;
  code: string;
  name: string;
}

export interface RetailerLoginData {
  tokens: RetailerLoginTokens;
  user: RetailerLoginUser;
  retailer: RetailerLoginRetailer;
  wholesaler: RetailerLoginWholesaler;
}

export interface RetailerLoginResponse {
  success: boolean;
  data: RetailerLoginData;
  timestamp: string;
}
