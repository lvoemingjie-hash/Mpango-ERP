-- Mpango ERP Database Initialization Script
-- Only sets up prerequisites that Alembic migrations depend on.
-- All table creation is owned by Alembic — do NOT create tables here.

-- Enable UUID extension (required by migrations)
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Pre-create alembic_version with wider column (default is VARCHAR(32),
-- but this project uses long descriptive revision IDs up to ~50 chars)
CREATE TABLE IF NOT EXISTS public.alembic_version (
    version_num VARCHAR(128) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Create development tenant schema (Alembic migrations may reference it)
CREATE SCHEMA IF NOT EXISTS "t_dev";
