-- P25-EC-R1 Tenant Schema Provisioning for Identity Smoke Test
--
-- Creates a minimal throwaway tenant schema (t_smoke_r1) with RBAC tables
-- and a seed user. This allows the auth middleware's resolve_tenant_context
-- to succeed cleanly, isolating the P10 platform guard boundary test.
--
-- Run against Docker Postgres (mpango_p25ec_pg, port 5433):
--   PGPASSWORD=p25ec_throwaway_pw psql -h 127.0.0.1 -p 5433 -U mpango -d mpango_erp -f tenant_setup_r1.sql
--
-- This is THROWAWAY data -- not a production migration. Drop after testing.

CREATE SCHEMA IF NOT EXISTS t_smoke_r1;

-- Users table (minimal columns for get_user_with_permissions)
CREATE TABLE IF NOT EXISTS t_smoke_r1.users (
    id UUID PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    full_name VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Roles table
CREATE TABLE IF NOT EXISTS t_smoke_r1.roles (
    id UUID PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    description TEXT
);

-- Permissions table
CREATE TABLE IF NOT EXISTS t_smoke_r1.permissions (
    id UUID PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    description TEXT
);

-- User-Roles junction
CREATE TABLE IF NOT EXISTS t_smoke_r1.user_roles (
    user_id UUID REFERENCES t_smoke_r1.users(id),
    role_id UUID REFERENCES t_smoke_r1.roles(id),
    PRIMARY KEY (user_id, role_id)
);

-- Role-Permissions junction
CREATE TABLE IF NOT EXISTS t_smoke_r1.role_permissions (
    role_id UUID REFERENCES t_smoke_r1.roles(id),
    permission_id UUID REFERENCES t_smoke_r1.permissions(id),
    PRIMARY KEY (role_id, permission_id)
);

-- Seed data: one super_admin user
INSERT INTO t_smoke_r1.users (id, email, full_name, is_active)
VALUES ('00000000-0000-0000-0000-000000000002', 'smoke-r1@mpango.example', 'Smoke R1 Admin', TRUE)
ON CONFLICT (id) DO NOTHING;

INSERT INTO t_smoke_r1.roles (id, name, description)
VALUES ('00000000-0000-0000-0000-000000000010', 'super_admin', 'Smoke test super admin role')
ON CONFLICT (id) DO NOTHING;

INSERT INTO t_smoke_r1.user_roles (user_id, role_id)
VALUES ('00000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000010')
ON CONFLICT DO NOTHING;
