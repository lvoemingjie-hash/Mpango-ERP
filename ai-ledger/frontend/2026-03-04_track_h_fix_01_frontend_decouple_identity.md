# Frontend H-Fix-01: Decouple Identity from Tenant Context

**Date**: 2026-03-04
**Priority**: P0 BLOCKER FIX

## Problem Statement
The frontend login flow was tightly coupled to the tenant context, requiring a `tenant_code` upfront. This caused friction for new users and locked out super admins.

## Implementation Details

### 1. Updated Auth API Types (`src/types/auth.ts`)
- Removed `tenant_code` from `LoginRequest`
- Added new types: `TenantInfo`, `IdentityTokenData`, `IdentityLoginResponse`, `SelectTenantRequest`
- Updated `TokenData` and `CurrentUserData` to handle optional tenant fields.

### 2. Updated API Service (`src/services/authService.ts`)
- Modified `login` method to return `IdentityLoginResponse`
- Added `selectTenant` method to handle the second phase of auth.

### 3. Redesigned Login Page (`src/pages/auth/LoginPage.tsx`)
- Removed `tenant_code` field from the UI and form validation schema.
- Implemented the Two-Phase Auth routing logic:
  - **Condition A (Super Admin)**: Routes directly to dashboard if `super_admin` role is present.
  - **Condition B (Single Tenant)**: Automatically calls `selectTenant` if only 1 tenant is available, then routes to dashboard.
  - **Condition C (Multi-Tenant)**: Routes to `/select-workspace` if >1 tenants are available. Includes Invite Link Auto-Resolution (checks URL query string for `tenant_code`).
  - **Condition D (Cold Start)**: Routes to `/onboarding/create-tenant` if 0 tenants are available.

### 4. Created Workspace Selector (`src/pages/auth/WorkspaceSelectorPage.tsx`)
- New clean UI for selecting a tenant when multiple are available.
- Handles the `selectTenant` API call and updates the auth store with the new contextual tokens and user data.

### 5. Updated Auth Store (`src/stores/authStore.ts`)
- Updated types to support `IdentityTokenData` and allow `tenantCode` to be null.

### 6. Invite Link Polish (`src/pages/invite/InvitePage.tsx` & `LoginPage.tsx`)
- Updated the "Continue to Login" button on the invite page to pass the `tenant_code` via URL query parameters.
- `LoginPage.tsx` reads this query parameter and automatically resolves the tenant if it exists in the user's available tenants list, bypassing the workspace selector.

### 7. App Router (`src/router/AppRouter.tsx`)
- Added the `/select-workspace` route.
