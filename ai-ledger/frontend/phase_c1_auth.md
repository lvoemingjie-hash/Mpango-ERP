# Phase C1: Auth & Session Architecture

**Date**: 2026-02-13
**Author**: Senior Frontend Architect (Cascade AI)
**Status**:  Complete
**Prerequisite**: Phase C0 verified  clean skeleton environment.

---

## Checklist

- [x] **Self-Audit**: Token Refresh flow does NOT cause infinite loop
  - `/auth/refresh` and `/auth/login` URLs are explicitly excluded from retry logic
  - `_retry` flag prevents double-retry on the same request
  - Refresh call uses raw `axios.post()` (not the intercepted `api` instance) to avoid recursion
- [x] **Self-Audit**: 401 on expired token successfully restores session without user action
  - Response interceptor catches 401  calls `/auth/refresh`  updates store  retries original request
  - Concurrent 401s are queued  only ONE refresh request is sent (mutex via `isRefreshing` flag)
  - Queued requests are replayed with the new token after refresh succeeds
- [x] **Self-Audit**: Manual "Logout" clears localStorage
  - `useAuthStore.logout()` resets all state to `initialState` (null tokens, null user)
  - Zustand `persist` middleware writes the cleared state to `localStorage` key `mpango-auth`
  - DashboardPage logout button calls `logout()` directly

---

## Architecture Overview

```
─
  main.tsx                                               
     App.tsx                                           
          AppRouter                                    
               PublicRoute  /login (LoginPage)       
               ProtectedRoute  / (DashboardPage)    


 Invisible Layer 
                                                         
  stores/authStore.ts (Zustand + persist)                
     State: accessToken, refreshToken, user, tenantCode
     Actions: login(), logout(), updateTokens()        
     Persistence: localStorage key "mpango-auth"       
                                                         
  services/api.ts (Axios singleton)                      
     Request interceptor: inject Bearer token          
     Response interceptor: atomic token refresh        
          Mutex: isRefreshing flag                     
          Queue: failedQueue[] for concurrent 401s     
          Escape: skip /auth/refresh & /auth/login     
                                                         
  services/authService.ts (thin API wrapper)             
     login(payload)  POST /auth/login                 
     refresh(token)  POST /auth/refresh               
     me()  GET /auth/me                               
     logout()  POST /auth/logout                      
                                                         
  router/guards.tsx                                      
     ProtectedRoute: redirect to /login if no token    
     PublicRoute: redirect to / if token exists         

```

## Files Created

| File | Purpose | Lines |
|------|---------|-------|
| `src/types/api.ts` | Generic API response types (ApiResponse, ApiErrorResponse, PaginatedData) | 43 |
| `src/types/auth.ts` | Auth types mirroring backend schemas/auth.py exactly | 50 |
| `src/stores/authStore.ts` | Zustand store with persist middleware | 63 |
| `src/services/api.ts` | Axios singleton with atomic token refresh + request queueing | 128 |
| `src/services/authService.ts` | Thin auth API wrapper (no logic) | 23 |
| `src/router/guards.tsx` | ProtectedRoute + PublicRoute components | 32 |
| `src/router/AppRouter.tsx` | Router configuration with createBrowserRouter | 30 |
| `src/pages/auth/LoginPage.tsx` | Login form with RHF + Zod validation + error display | 175 |
| `src/pages/DashboardPage.tsx` | Placeholder dashboard proving login worked | 55 |
| `src/App.tsx` | Updated to render AppRouter | 5 |

## Contract Compliance

### Backend Contract Alignment (openapi.yaml)

| Endpoint | Frontend Type | Backend Schema | Match |
|----------|--------------|----------------|-------|
| `POST /auth/login` | `LoginRequest  LoginResponse` | `schemas/auth.py LoginRequest  LoginResponse` |  |
| `POST /auth/refresh` | `RefreshTokenRequest  LoginResponse` | `schemas/auth.py RefreshTokenRequest  LoginResponse` |  |
| `GET /auth/me` | ` CurrentUserResponse` | `schemas/auth.py CurrentUserResponse` |  |
| `POST /auth/logout` | ` MessageResponse` | `schemas/common.py MessageResponse` |  |

### Frontend Contract Compliance

| Rule | Status |
|------|--------|
| All components use TypeScript |  |
| All styles use TailwindCSS |  |
| All state through Zustand |  |
| All forms use React Hook Form + Zod |  |
| All API through unified service layer |  |
| Named exports only (no default export) |  |
| No business logic in pages beyond auth |  |

## Token Refresh Flow  Detailed Sequence

```
Request A fails with 401
  
   Is /auth/refresh or /auth/login?  YES  reject (no retry)
  
   Already _retry?  YES  reject (no infinite loop)
  
   isRefreshing?  YES  queue request, wait for refresh result
                            On success: replay with new token
                            On failure: reject
  
   isRefreshing?  NO  set isRefreshing=true
       
        Has refreshToken?  NO  logout()  redirect /login
       
        POST /auth/refresh (raw axios, not intercepted)
            
             Success  updateTokens()  processQueue(null, newToken)
                         retry original request A
            
             Failure  processQueue(error, null)  logout()
                          redirect /login
```

**Infinite loop prevention**:
1. `_retry` flag on each request config  prevents double-retry
2. URL check  `/auth/refresh` and `/auth/login` are never retried
3. Raw `axios.post()` for refresh call  bypasses the intercepted `api` instance entirely

## Login Flow  User Experience

1. User enters tenant_code, email, password
2. Zod validates client-side (instant feedback)
3. `POST /auth/login`  receives tokens + tenant info
4. Tokens stored temporarily  `GET /auth/me`  receives user profile
5. Full state committed to Zustand store (persisted to localStorage)
6. Router navigates to `/` (dashboard)
7. On page refresh: Zustand rehydrates from localStorage  ProtectedRoute allows access

## Verification Evidence

```
$ pnpm exec tsc --noEmit
(exit code 0  zero errors)

$ pnpm dev
VITE v5.4.21  ready in 1035 ms
  Local:   http://localhost:5173/
```

## Suggested Commit

```
feat(frontend): Phase C1  auth spine (store, interceptors, login, guards)

- Add Zustand auth store with persist middleware
- Add Axios singleton with atomic token refresh + request queueing
- Add auth service layer (login, refresh, me, logout)
- Add router guards (ProtectedRoute, PublicRoute)
- Add login page with react-hook-form + zod validation
- Add placeholder dashboard page
- Wire up AppRouter with createBrowserRouter
- Types mirror backend schemas/auth.py exactly
```

---

*Boot Contract acknowledged. Architecture Constitution > Boot Contract > all other contracts.*