-- Mpango ERP Database Initialization Script
-- This script sets up the basic database structure

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Create public schema tables (tenant registry)
CREATE TABLE IF NOT EXISTS public.wholesalers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(32) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    address TEXT,
    contact TEXT,
    plan_type VARCHAR(50),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMPTZ
);

-- Create indexes for wholesalers
CREATE INDEX IF NOT EXISTS idx_wholesalers_code ON public.wholesalers(code);
CREATE INDEX IF NOT EXISTS idx_wholesalers_is_deleted ON public.wholesalers(is_deleted);

-- Insert sample wholesaler for development
INSERT INTO public.wholesalers (code, name, address, contact, plan_type)
VALUES ('DEV001', 'Development Wholesaler', '123 Dev Street', 'dev@mpango.com', 'premium')
ON CONFLICT (code) DO NOTHING;

-- Create development tenant schema
CREATE SCHEMA IF NOT EXISTS "t_dev";

-- Note: Actual tenant tables will be created via Alembic migrations
-- This script only sets up the basic structure and sample data
