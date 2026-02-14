/**
 * Tenant (Wholesaler) types — mirrors backend schemas/wholesaler.py.
 * Backend entity is "Wholesaler" but frontend uses "Tenant" terminology.
 */

export interface Tenant {
  id: string;
  code: string;
  name: string;
  address: string | null;
  contact: string | null;
  plan_type: string | null;
  schema_name: string;
  created_at: string;
  updated_at: string;
}

export interface CreateTenantRequest {
  code: string;
  name: string;
  address?: string | null;
  contact?: string | null;
  plan_type?: string | null;
}

export interface UpdateTenantRequest {
  name?: string;
  address?: string | null;
  contact?: string | null;
  plan_type?: string | null;
}
