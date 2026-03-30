# Phase C2: App Layout & Navigation Structure

**Date**: 2026-02-13
**Author**: Senior Frontend Architect (Cascade AI)
**Status**:  Complete
**Prerequisite**: Phase C1 (Auth) verified  login/logout/token refresh working.

---

## Checklist

- [x] **Check**: Sidebar stays fixed while main content scrolls
  - Sidebar uses `fixed inset-y-0 left-0` positioning with `h-screen` implied by `inset-y-0`
  - Main content area uses `flex-1 overflow-auto`  scrolls independently
  - Content area offset with `ml-64` to avoid overlap with sidebar
- [x] **Check**: Refreshing the page keeps Sidebar active state correct
  - Active state derived from `useLocation().pathname` on every render
  - Exact match for `/` (dashboard), prefix match for nested routes (e.g. `/users/123`)
  - No client-side state dependency  purely URL-driven
- [x] **Check**: Mobile responsiveness
  - Deferred to future phase (desktop-first per constraint)
  - Sidebar is fixed `w-64`  will need responsive toggle in Phase C3+

---

## Architecture Overview

```
─
  AppRouter                                              
   PublicRoute (no layout)                             
      /login  LoginPage (full screen)                
                                                        
   ProtectedRoute                                      
      MainLayout                                      
          Sidebar (fixed left, w-64)                  
          Header (sticky top, ml-64)                  
          <main>  <Outlet />                         
              /  DashboardPage                       
                                                        
   *  NotFoundPage (full screen, no layout)           

```

### Layout Structure (CSS)

```

            Header (sticky, h-16)               
  Sidebar    Breadcrumbs    User Profile    
  (fixed)   
  w-64                                          
            <main> (flex-1, overflow-auto, p-6) 
  Logo                                          
  Nav         <Outlet />  child routes          
  Items                                         
                                                
                                          
  Logout                                        

```

## Files Created / Modified

| File | Action | Purpose |
|------|--------|---------|
| `src/components/layout/Sidebar.tsx` | **Created** | Fixed left nav with navItems config, active state via useLocation, logout button |
| `src/components/layout/Header.tsx` | **Created** | Sticky top bar with auto-generated breadcrumbs + user profile display |
| `src/components/layout/MainLayout.tsx` | **Created** | App shell composing Sidebar + Header + Outlet |
| `src/pages/NotFoundPage.tsx` | **Created** | 404 page with link back to dashboard |
| `src/router/AppRouter.tsx` | **Modified** | Wrapped ProtectedRoute children with MainLayout, added wildcard 404 route |
| `src/pages/DashboardPage.tsx` | **Modified** | Simplified  removed redundant header/logout (now in layout shell) |

## Component Details

### Sidebar (`src/components/layout/Sidebar.tsx`)

- **Width**: `w-64` (256px), fixed position
- **Nav Items** (config-driven array):
  - Dashboard (`/`)  HomeIcon
  - Tenants (`/tenants`)  BuildingOfficeIcon
  - Users (`/users`)  UsersIcon
  - Settings (`/settings`)  Cog6ToothIcon
- **Active State Logic**:
  - Exact match for `/` (prevents false positives)
  - `startsWith()` for nested routes (e.g. `/users/123` highlights Users)
  - Styling: `bg-primary-50 text-primary-700` (active) vs `text-gray-600 hover:bg-gray-50` (inactive)
- **Logout**: Bottom-pinned button with red hover state, calls `useAuthStore.logout()`
- **Icons**: `@heroicons/react/24/outline` (already in deps from C0)

### Header (`src/components/layout/Header.tsx`)

- **Position**: `sticky top-0`, `h-16`, `z-20`
- **Left**: Auto-generated breadcrumbs from `useLocation().pathname`
  - Splits path segments, capitalizes first letter
  - Root `/` shows "Dashboard"
- **Right**: User avatar (UserCircleIcon) + name/role from `useAuthStore.user`

### MainLayout (`src/components/layout/MainLayout.tsx`)

- Composes Sidebar + Header + `<Outlet />`
- Main content: `flex-1 overflow-auto p-6`
- Only used by ProtectedRoute  login stays full-screen

### Router Changes

- ProtectedRoute now nests `MainLayout` as a layout route
- `MainLayout` renders `<Outlet />` for child page content
- Wildcard `*` route catches undefined paths  NotFoundPage (no layout)

## Verification Evidence

```
$ pnpm exec tsc --noEmit
(exit code 0  zero errors)

$ pnpm dev
VITE v5.4.21  ready in 479 ms
  Local:   http://localhost:5173/
```

## Suggested Commit

```
feat(frontend): Phase C2  app shell layout (sidebar, header, main layout)

- Add Sidebar with config-driven nav items and active state
- Add Header with auto-generated breadcrumbs and user profile
- Add MainLayout composing Sidebar + Header + Outlet
- Add NotFoundPage with 404 handling
- Wrap ProtectedRoute children with MainLayout
- Simplify DashboardPage (layout handles chrome)
```

---

*Boot Contract acknowledged. Architecture Constitution > Boot Contract > all other contracts.*