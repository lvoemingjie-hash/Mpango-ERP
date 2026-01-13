# Implementation Plan: Backend Skeleton

## Overview

This plan implements the Mpango ERP backend skeleton that proves alignment between OpenAPI contract, PostgreSQL database schema, and FastAPI application. Tasks are ordered to build incrementally, with each step validating core functionality before proceeding.

## Tasks

- [x] 1. Set up configuration module
  - [x] 1.1 Create `backend/core/config.py` with Pydantic Settings
    - Define `Settings` class with DATABASE_URL, SECRET_KEY, CORS_ORIGINS
    - Implement `@lru_cache` for `get_settings()`
    - Support `.env` file loading
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_
  - [x] 1.2 Update `backend/.env.example` with all configuration variables
    - _Requirements: 7.2_

- [x] 2. Implement SQLAlchemy base models and mixins
  - [x] 2.1 Create `backend/models/base.py` with Base class and mixins
    - Define `Base` declarative base
    - Implement `AuditMixin` with created_at, updated_at, is_deleted, deleted_at
    - Implement `UserTrackingMixin` with created_by, updated_by
    - _Requirements: 1.4, 1.5, 3.1_
  - [x] 2.2 Write property test for ORM model structure compliance
    - **Property 1: ORM Model Structure Compliance**
    - **Validates: Requirements 1.3, 1.4, 3.2, 3.3**

- [x] 3. Implement ORM models
  - [x] 3.1 Create `backend/models/wholesaler.py` for public.wholesalers
    - UUID primary key with gen_random_uuid() default
    - All columns per database_contract.md
    - Unique index on `code`
    - _Requirements: 1.1, 1.3, 1.7, 3.2, 3.3, 3.4_
  - [x] 3.2 Create `backend/models/user.py` for tenant users table
    - UUID primary key, audit columns, user tracking
    - Unique index on `email`
    - Relationship to roles via user_roles
    - _Requirements: 1.2, 1.3, 1.6, 1.7, 3.4, 3.6_
  - [x] 3.3 Create `backend/models/role.py` for tenant roles table
    - UUID primary key, audit columns, user tracking
    - Relationships to users and permissions
    - _Requirements: 1.2, 1.3, 3.4, 3.6_
  - [x] 3.4 Create `backend/models/permission.py` for tenant permissions table
    - UUID primary key, audit columns, user tracking
    - Unique index on `code`
    - Relationship to roles
    - _Requirements: 1.2, 1.3, 3.4, 3.6_
  - [x] 3.5 Create association tables in `backend/models/__init__.py`
    - `user_roles` M2M table with CASCADE delete
    - `role_permissions` M2M table with CASCADE delete
    - _Requirements: 1.6, 3.6_

- [x] 4. Implement database session management
  - [x] 4.1 Update `backend/database/session.py` with async session factory
    - Create async engine from DATABASE_URL
    - Implement async_sessionmaker
    - _Requirements: 6.1_
  - [x] 4.2 Create tenant-aware session dependency in `backend/api/dependencies.py`
    - Implement `get_db_session()` dependency
    - Support tenant_schema parameter for search_path
    - Ensure session cleanup and rollback on error
    - _Requirements: 6.2, 6.3, 6.4, 6.5_
  - [x] 4.3 Write property test for tenant schema isolation
    - **Property 8: Tenant Schema Isolation**
    - **Validates: Requirements 6.3**

- [x] 5. Checkpoint - Verify database layer
  - Ensure all models can be imported without errors
  - Verify model metadata matches database_contract.md
  - Ask the user if questions arise

- [x] 6. Configure Alembic for multi-tenant migrations
  - [x] 6.1 Update `backend/alembic/env.py` for multi-schema support
    - Parse `-x tenant_schema` argument
    - Set search_path for tenant migrations
    - Create schema if not exists for tenant migrations
    - _Requirements: 2.1, 2.2, 2.3_
  - [x] 6.2 Create initial migration `backend/alembic/versions/001_initial_schema.py`
    - Public schema: wholesalers table
    - Tenant schema: users, roles, permissions, user_roles, role_permissions
    - All indexes and constraints
    - _Requirements: 2.4, 1.1, 1.2, 1.6, 1.7_
  - [x] 6.3 Write property test for tenant schema migration isolation
    - **Property 2: Tenant Schema Migration Isolation**
    - **Validates: Requirements 2.3**

- [x] 7. Implement Pydantic schemas
  - [x] 7.1 Create `backend/schemas/common.py` with shared schemas
    - Pagination, ErrorDetail, ErrorResponse, MessageResponse
    - Generic DataResponse[T]
    - _Requirements: 5.1_
  - [x] 7.2 Create `backend/schemas/auth.py` with auth schemas
    - LoginRequest, LoginResponse, RefreshTokenRequest, TokenData
    - CurrentUserResponse
    - _Requirements: 5.1, 5.2_
  - [x] 7.3 Create `backend/schemas/user.py` with user schemas
    - UserCreate, UserUpdate, UserRead (no password_hash)
    - UserListResponse, AssignRolesRequest
    - _Requirements: 5.1, 5.2, 5.3, 5.4_
  - [x] 7.4 Create `backend/schemas/role.py` with role schemas
    - RoleRead, RoleListResponse
    - _Requirements: 5.1_
  - [x] 7.5 Create `backend/schemas/order.py` with order schemas
    - OrderStatus enum, OrderItemCreate, OrderCreateRequest
    - OrderItem, Order, OrderResponse, OrderListResponse, OrderActionResponse
    - _Requirements: 5.1, 3.5_
  - [x] 7.6 Write property test for password hash exclusion
    - **Property 5: Password Hash Exclusion**
    - **Validates: Requirements 5.3**
  - [x] 7.7 Write property test for UUID serialization
    - **Property 6: UUID Serialization**
    - **Validates: Requirements 5.4**

- [x] 8. Implement FastAPI route stubs
  - [x] 8.1 Create `backend/api/v1/auth.py` with auth route stubs
    - POST /login, POST /refresh, POST /logout, GET /me
    - Return 501 Not Implemented for all
    - _Requirements: 4.2, 4.3_
  - [x] 8.2 Update `backend/api/v1/users.py` with user route stubs
    - GET /users, POST /users, GET /users/{id}, PUT /users/{id}, DELETE /users/{id}
    - PUT /users/{id}/roles
    - Return 501 Not Implemented for all
    - _Requirements: 4.2, 4.3_
  - [x] 8.3 Create `backend/api/v1/roles.py` with role route stubs
    - GET /roles
    - Return 501 Not Implemented
    - _Requirements: 4.2, 4.3_
  - [x] 8.4 Create `backend/api/v1/orders.py` with order route stubs
    - GET /orders, POST /orders, GET /orders/{id}
    - POST /orders/{id}/confirm, POST /orders/{id}/ship, POST /orders/{id}/cancel
    - Return 501 Not Implemented for all
    - _Requirements: 4.2, 4.3_
  - [x] 8.5 Write property test for OpenAPI route coverage
    - **Property 3: OpenAPI Route Coverage**
    - **Validates: Requirements 4.2, 4.3**

- [x] 9. Implement main application
  - [x] 9.1 Update `backend/main.py` with FastAPI app configuration
    - Load OpenAPI spec from docs/contracts/openapi.yaml
    - Configure CORS middleware
    - Add health check endpoint at /health
    - Include all routers with correct prefixes
    - _Requirements: 4.1, 4.4, 4.5_
  - [x] 9.2 Write property test for request validation
    - **Property 7: Request Validation**
    - **Validates: Requirements 5.5**

- [x] 10. Checkpoint - Verify API layer
  - Ensure FastAPI app starts without errors
  - Verify /health endpoint returns 200
  - Verify /openapi.json returns the loaded spec
  - Ask the user if questions arise

- [x] 11. Create AI ledger entry
  - [x] 11.1 Create `ai-ledger/architect/2026-01-12_backend_skeleton_implementation.md`
    - Document all work performed
    - List files created/modified
    - Note any decisions made
    - _Requirements: N/A (process requirement)_

- [x] 12. Final checkpoint - Prove alignment
  - Run Alembic migration to create public schema
  - Verify all route stubs return 501
  - Confirm OpenAPI ↔ DB ↔ FastAPI structural alignment
  - Ask the user if questions arise

## Notes

- All tasks including property tests are required
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties
- No business logic is implemented - only structural skeleton
