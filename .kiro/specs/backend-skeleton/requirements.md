# Requirements Document

## Introduction

This specification defines the requirements for the Mpango ERP backend skeleton - an executable foundation that proves alignment between OpenAPI contract, PostgreSQL database schema, and FastAPI application. The skeleton implements no business logic; it establishes the structural integrity of the multi-tenant ERP system.

## Glossary

- **Backend_Skeleton**: The minimal executable FastAPI application that loads OpenAPI spec, connects to PostgreSQL, and validates structural alignment
- **Tenant_Schema**: A PostgreSQL schema named `t_<uuid_without_dashes>` containing all tenant-scoped tables
- **Public_Schema**: The PostgreSQL `public` schema containing the `wholesalers` tenant registry table
- **Alembic_Migration**: A versioned database migration script managed by Alembic
- **ORM_Model**: A SQLAlchemy 2.0 async model class representing a database table
- **OpenAPI_Contract**: The canonical API specification in `docs/contracts/openapi.yaml`
- **Database_Contract**: The canonical database schema specification in `docs/contracts/database_contract.md`

## Requirements

### Requirement 1: PostgreSQL Schema Generation

**User Story:** As a backend developer, I want the database schema generated from database_contract.md, so that the database structure matches the canonical specification.

#### Acceptance Criteria

1. THE Backend_Skeleton SHALL create the `public.wholesalers` table with all columns matching database_contract.md
2. THE Backend_Skeleton SHALL create tenant schema tables (`users`, `roles`, `permissions`) with all columns matching database_contract.md
3. WHEN a table is created, THE Backend_Skeleton SHALL use UUID primary keys with `gen_random_uuid()` default
4. WHEN a table is created, THE Backend_Skeleton SHALL include audit columns (`created_at`, `updated_at`, `is_deleted`, `deleted_at`)
5. WHEN a table is created, THE Backend_Skeleton SHALL include user tracking columns (`created_by`, `updated_by`) where specified
6. THE Backend_Skeleton SHALL create indexes on all foreign key columns
7. THE Backend_Skeleton SHALL create unique indexes on `email` in users and `code` in wholesalers

### Requirement 2: Alembic Migration Infrastructure

**User Story:** As a backend developer, I want Alembic migrations that support multi-tenant schema deployment, so that I can provision and upgrade tenant schemas independently.

#### Acceptance Criteria

1. THE Alembic_Migration SHALL support the `-x tenant_schema=<schema_name>` parameter for tenant-specific migrations
2. WHEN running migrations without tenant_schema parameter, THE Alembic_Migration SHALL apply changes to the public schema only
3. WHEN running migrations with tenant_schema parameter, THE Alembic_Migration SHALL apply tenant-scoped tables to the specified schema
4. THE Alembic_Migration SHALL create the initial schema structure in a single versioned migration
5. IF a migration fails, THEN THE Alembic_Migration SHALL rollback all changes in that migration

### Requirement 3: SQLAlchemy ORM Models

**User Story:** As a backend developer, I want SQLAlchemy 2.0 async ORM models that match the database contract, so that I can interact with the database using Python objects.

#### Acceptance Criteria

1. THE ORM_Model SHALL use SQLAlchemy 2.0 async mode with `AsyncSession`
2. THE ORM_Model SHALL define explicit `__tablename__` matching database table names
3. THE ORM_Model SHALL use `PascalCase` class names (e.g., `User`, `Wholesaler`, `Role`)
4. THE ORM_Model SHALL define all columns matching database_contract.md specifications
5. THE ORM_Model SHALL use Python `Enum` classes for enumerated types
6. THE ORM_Model SHALL define foreign key relationships using SQLAlchemy relationship patterns

### Requirement 4: FastAPI Application Structure

**User Story:** As a backend developer, I want a FastAPI application that loads the OpenAPI contract, so that the API structure is driven by the canonical specification.

#### Acceptance Criteria

1. THE Backend_Skeleton SHALL load and serve the OpenAPI specification from `docs/contracts/openapi.yaml`
2. THE Backend_Skeleton SHALL define route stubs for all endpoints in openapi.yaml
3. WHEN an endpoint is called, THE Backend_Skeleton SHALL return a stub response matching the OpenAPI schema structure
4. THE Backend_Skeleton SHALL configure CORS middleware for development
5. THE Backend_Skeleton SHALL include health check endpoint at `/health`

### Requirement 5: Pydantic Schema Alignment

**User Story:** As a backend developer, I want Pydantic schemas that match OpenAPI component schemas, so that request/response validation is consistent with the API contract.

#### Acceptance Criteria

1. THE Backend_Skeleton SHALL define Pydantic schemas for all OpenAPI component schemas
2. THE Backend_Skeleton SHALL separate schemas into `Create`, `Update`, and `Read` variants where applicable
3. THE Backend_Skeleton SHALL NOT include `password_hash` in any Read schema
4. THE Backend_Skeleton SHALL serialize UUID fields as strings in responses
5. THE Backend_Skeleton SHALL validate request bodies against Pydantic schemas

### Requirement 6: Database Session Management

**User Story:** As a backend developer, I want async database session management with tenant schema support, so that requests are isolated to the correct tenant data.

#### Acceptance Criteria

1. THE Backend_Skeleton SHALL use async database sessions with SQLAlchemy 2.0
2. THE Backend_Skeleton SHALL provide a dependency injection pattern for database sessions
3. WHEN a tenant_schema is provided, THE Backend_Skeleton SHALL set `search_path` to the tenant schema
4. THE Backend_Skeleton SHALL properly close database sessions after each request
5. IF a database error occurs, THEN THE Backend_Skeleton SHALL rollback the transaction

### Requirement 7: Configuration Management

**User Story:** As a backend developer, I want environment-based configuration, so that the application can run in different environments without code changes.

#### Acceptance Criteria

1. THE Backend_Skeleton SHALL load configuration from environment variables
2. THE Backend_Skeleton SHALL support `.env` file loading for local development
3. THE Backend_Skeleton SHALL require `DATABASE_URL` configuration
4. THE Backend_Skeleton SHALL provide sensible defaults for optional configuration
5. IF required configuration is missing, THEN THE Backend_Skeleton SHALL fail fast with a clear error message
