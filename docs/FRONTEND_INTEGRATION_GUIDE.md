# Frontend Integration Guide (Frozen)

**Status**: S1 Freeze — Track C complete, API Contract v0.1.7 locked
**Date**: 2026-02-13
**Audience**: Next developer, auditor, or AI agent onboarding to this codebase

---

## Section 1: Auth & Session Mechanics

### 1.1 Token Refresh Flow (Axios Interceptor)

The entire auth lifecycle is managed by a single Axios instance (`src/services/api.ts`).

**Sequence:**

```
Request fails with 401
        │
        ▼
Is this a /auth/login or /auth/refresh URL?
  YES → reject (prevents infinite loop)
  NO  ↓
        │
Has this request already been retried? (_retry flag)
  YES → reject
  NO  ↓
        │
Is another refresh already in progress? (isRefreshing mutex)
  YES → push request into failedQueue, await new token
  NO  ↓
        │
Set isRefreshing = true, _retry = true
        │
        ▼
POST /auth/refresh (via raw axios.post, NOT the intercepted instance)
        │
   ┌────┴────┐
 SUCCESS    FAIL
   │          │
   ▼          ▼
Store new    logout()
tokens       redirect → /login
   │
   ▼
processQueue(null, newToken)
Retry original request + all queued requests
   │
   ▼
isRefreshing = false
```

**Key design decisions:**
- **Mutex lock** (`isRefreshing` boolean): Only ONE refresh request is ever in-flight. Concurrent 401s are queued, not duplicated.
- **Raw `axios.post()`** for the refresh call: Bypasses the intercepted `api` instance to prevent recursive interception.
- **`_retry` flag**: Stamped on `originalRequest` to prevent infinite retry loops.
- **URL exclusion**: Requests to `/auth/refresh` and `/auth/login` are never retried.
- **`useAuthStore.getState()`**: Used instead of React hooks to avoid circular dependencies (api.ts is not a component).

### 1.2 Token Storage

**Mechanism**: Zustand store with `persist` middleware → **localStorage**
**Key**: `mpango-auth`

```typescript
// src/stores/authStore.ts
persist(
  (set) => ({ ... }),
  {
    name: 'mpango-auth',
    partialize: (state) => ({
      accessToken: state.accessToken,
      refreshToken: state.refreshToken,
      user: state.user,
      tenantCode: state.tenantCode,
    }),
  }
)
```

**What is persisted:**

| Field | Type | Purpose |
|-------|------|---------|
| `accessToken` | `string \| null` | JWT access token (30m TTL) |
| `refreshToken` | `string \| null` | JWT refresh token (7d TTL) |
| `user` | `CurrentUserData \| null` | User profile: id, email, full_name, tenant_id, tenant_schema, roles[], permissions[] |
| `tenantCode` | `string \| null` | Last-used tenant code (pre-fills login form) |

**On logout**: All fields reset to `null` via `set({ ...initialState })`.

### 1.3 Security: Dev-Mode Logging

The request interceptor logs outgoing requests in development only (`import.meta.env.DEV`). The `Authorization` header is **always redacted** to `[REDACTED]` before logging. This is stripped entirely from production builds by Vite.

```typescript
if (import.meta.env.DEV) {
  const safeHeaders = { ...config.headers };
  if (safeHeaders.Authorization) safeHeaders.Authorization = '[REDACTED]';
  console.debug('[API →]', config.method?.toUpperCase(), config.url, { headers: safeHeaders });
}
```

---

## Section 2: Error Handling Strategy

### 2.1 The Adapter: `normalizeApiError`

**File**: `src/utils/errorHandling.ts`

This function is the **single point of translation** between backend error shapes and user-facing strings. It handles the inconsistency documented in `API_CONTRACT_v0.1.7.md` Section 2.

```typescript
export function normalizeApiError(error: unknown): string
```

**Decision table:**

| HTTP Status | Backend `detail` Shape | Adapter Output |
|-------------|----------------------|----------------|
| **422** | `[{ loc: [...], msg: "...", type: "..." }]` (array) | `"field: message"` (first error, `body` stripped from loc) |
| **409** | `{ code: "...", message: "..." }` (object) | `detail.message` or fallback |
| **403** | `{ code: "PERMISSION_DENIED", message: "..." }` | `detail.message` or "Permission denied..." |
| **404** | `{ code: "...", message: "..." }` | `detail.message` or "The requested resource was not found." |
| **500** | any | `"Internal server error. Please try again or contact support."` |
| other | string | The string itself |
| other | object with `message` | `detail.message` |
| network | no response | `axErr.message` (e.g., "Network Error") |
| unknown | — | `"An unexpected error occurred."` |

### 2.2 Policy

> **Rule**: UI components (pages, modals) **never** parse `error.response` directly. All error-to-string conversion goes through `normalizeApiError`.

**Correct:**
```typescript
import { normalizeApiError } from '@/utils/errorHandling';
// ...
catch (err) {
  setServerError(normalizeApiError(err));
}
```

**Forbidden:**
```typescript
// ❌ DO NOT do this in UI components
catch (err) {
  const msg = err.response?.data?.detail?.message;  // raw access
}
```

This ensures that when the backend changes its error envelope (e.g., standardizing 422 to object format), only ONE file needs updating.

---

## Section 3: Permission System

### 3.1 UI Guard: `canWrite`

Permission checks in UI components use the `permissions` array from the auth store's `user` object. This array is populated by `GET /auth/me` at login time.

**Pattern** (used in `TenantListPage.tsx`):

```typescript
const user = useAuthStore((s) => s.user);
const canWrite = user?.permissions?.includes('wholesalers:write') ?? false;
```

**Where it's applied:**

| Element | Guard | Effect When Denied |
|---------|-------|--------------------|
| Create button | `disabled={!canWrite}` | Greyed out, tooltip: "You need wholesalers:write permission" |
| Edit button | `disabled={!canWrite}` | Greyed out, tooltip: "wholesalers:write required" |
| Delete button | `disabled={!canWrite \|\| deletingId === t.id}` | Greyed out + spinner during delete |
| Submit button (modal) | `disabled={isSubmitting}` | Shows "Creating…" / "Saving…" text |

**Important**: Permission checks are **UI-only guards**. The backend enforces the same permissions via `RequirePermission` RBAC middleware. If a user bypasses the UI (e.g., via DevTools), the backend will return 403.

### 3.2 Route Guards

**File**: `src/router/guards.tsx`

Two layout-level route guards control access:

#### `ProtectedRoute`
- Reads `accessToken` from `useAuthStore`.
- If **no token** → `<Navigate to="/login" replace />`.
- If **token exists** → renders `<Outlet />` (child routes).
- Wraps all authenticated routes (Dashboard, Tenants, etc.).

#### `PublicRoute`
- Reads `accessToken` from `useAuthStore`.
- If **token exists** → `<Navigate to="/" replace />` (redirect to dashboard).
- If **no token** → renders `<Outlet />` (child routes).
- Wraps the login page only.

**Route tree** (`src/router/AppRouter.tsx`):

```
PublicRoute
  └── /login → LoginPage

ProtectedRoute
  └── MainLayout (Sidebar + Header + Outlet)
        ├── /         → DashboardPage
        └── /tenants  → TenantListPage

* (wildcard) → NotFoundPage
```

**Note**: Route guards check token **presence**, not validity. Token validity is enforced by the Axios response interceptor (401 → refresh or logout).

---

## Section 4: Project Standard (The "Spec")

### 4.1 Directory Structure (Frozen)

```
frontend/src/
├── App.tsx                          # Root component, renders AppRouter
├── main.tsx                         # Vite entry point
├── vite-env.d.ts                    # Vite type declarations
│
├── assets/                          # Static assets (images, fonts)
├── components/
│   ├── forms/                       # Reusable form components (reserved)
│   ├── layout/
│   │   ├── Header.tsx               # Sticky top bar with breadcrumbs
│   │   ├── MainLayout.tsx           # App shell: Sidebar + Header + Outlet
│   │   └── Sidebar.tsx              # Fixed left nav, config-driven
│   └── ui/
│       ├── Badge.tsx                # Status badge (green/gray/red/blue/yellow)
│       ├── Modal.tsx                # Generic dialog (Headless UI)
│       └── Pagination.tsx           # Page navigation (Previous/Next)
│
├── contexts/                        # React contexts (reserved)
├── hooks/                           # Custom hooks (reserved)
│
├── pages/
│   ├── auth/
│   │   └── LoginPage.tsx            # Multi-tenant login (RHF + Zod)
│   ├── tenants/
│   │   ├── TenantFormModal.tsx      # Create/Edit form modal
│   │   └── TenantListPage.tsx       # Full CRUD page
│   ├── DashboardPage.tsx            # Dashboard placeholder
│   └── NotFoundPage.tsx             # 404 page
│
├── router/
│   ├── AppRouter.tsx                # createBrowserRouter config
│   └── guards.tsx                   # ProtectedRoute, PublicRoute
│
├── services/
│   ├── api.ts                       # Axios singleton + interceptors
│   ├── authService.ts               # Auth API wrapper (login, refresh, me, logout)
│   └── tenantService.ts             # Tenant CRUD wrapper (/wholesalers)
│
├── stores/
│   └── authStore.ts                 # Zustand + persist (tokens, user, tenantCode)
│
├── styles/
│   └── globals.css                  # Tailwind directives + custom utilities
│
├── types/
│   ├── api.ts                       # ApiResponse, ApiErrorResponse, PaginatedData
│   ├── auth.ts                      # LoginRequest, TokenData, CurrentUserData
│   └── tenant.ts                    # Tenant, CreateTenantRequest, UpdateTenantRequest
│
└── utils/
    └── errorHandling.ts             # normalizeApiError adapter
```

### 4.2 Tech Stack (Version Lock)

| Package | Version | Purpose |
|---------|---------|---------|
| **react** | ^18.2.0 | UI framework |
| **react-dom** | ^18.2.0 | DOM renderer |
| **react-router-dom** | ^6.20.1 | Client-side routing |
| **typescript** | ^5.2.2 | Type safety (strict mode) |
| **vite** | ^5.0.0 | Build tool + dev server |
| **tailwindcss** | ^3.3.6 | Utility-first CSS |
| **zustand** | ^4.4.7 | State management (auth store) |
| **axios** | ^1.13.5 | HTTP client |
| **react-hook-form** | ^7.48.2 | Form state management |
| **zod** | ^3.22.4 | Schema validation |
| **@hookform/resolvers** | ^3.3.2 | Zod ↔ RHF bridge |
| **@headlessui/react** | ^1.7.17 | Accessible UI primitives (Modal) |
| **@heroicons/react** | ^2.0.18 | Icon library |
| **vitest** | ^1.0.0 | Unit testing |
| **@testing-library/react** | ^14.1.2 | Component testing |
| **eslint** | ^8.53.0 | Linting |
| **prettier** | ^3.1.0 | Code formatting |

### 4.3 Conventions

- **Named exports only** — no default exports (per `ui_integration_contract.md` §5.1).
- **Package manager**: pnpm.
- **Path alias**: `@/` → `src/` (configured in `vite.config.ts` and `tsconfig.json`).
- **API base URL**: `VITE_API_URL` env var, falls back to `/api/v1`.
- **Dev server port**: 5173 (Vite default).
- **Type check command**: `pnpm exec tsc --noEmit`.
- **Build command**: `tsc && vite build`.

---

**Freeze Version**: S1-FE
**Authority**: CTO
**Companion Document**: `docs/API_CONTRACT_v0.1.7.md`
