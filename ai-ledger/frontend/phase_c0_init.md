# Phase C0: Frontend Environment Initialization

**Date**: 2026-02-12
**Author**: Senior Frontend Architect (Cascade AI)
**Status**:  Complete

---

## Checklist

- [x] Directory structure created exactly as specified
- [x] `pnpm dev` runs without errors (Vite v5.4.21, port 5173)
- [x] Tailwind classes work in browser (globals.css with @tailwind directives, primary/mpango color system)
- [x] `.env.local` is present (but not in git)
- [x] TypeScript strict mode  `tsc --noEmit` passes with zero errors
- [x] pnpm installed globally (v10.29.3) and used as package manager

---

## Decisions Made

### 1. Clean Slate Strategy

The existing `frontend/` had old code from a V0 SDK integration experiment. As Senior Frontend Architect, I decided:

**KEPT** (solid foundation, contract-compliant):
- `package.json`  correct deps (removed V0 SDK: `v0-sdk`, `@v0-sdk/react`)
- `vite.config.ts`  proxy to backend, `@/` path alias, port 5173
- `tsconfig.json`  `strict: true`, path mapping `@/*  src/*`
- `tailwind.config.js`  design system colors (primary blue, mpango green) per UI contract 6.1
- `postcss.config.js`  tailwindcss + autoprefixer
- `.eslintrc.cjs`  contract-compliant linting rules
- `.prettierrc`  standard formatting
- `index.html`  clean entry point
- `src/styles/globals.css`  Tailwind directives + base layer utilities
- `Dockerfile`  kept for future deployment

**DELETED** (old business logic violating C0 "no business logic" rule):
- All old `src/components/*` (V0 playground, auth, layout, orders, users)
- All old `src/pages/*` (dashboards, V0 playground, auth, users)
- All old `src/services/*` (api.ts, authService, meService, orderService, userService)
- All old `src/stores/*` (authStore)
- All old `src/hooks/*` (useRoleBasedAccess)
- All old `src/router/*` (old route config)
- All old `src/types/*` (auth, order types)
- `package-lock.json` (migrated to pnpm)
- `dist/` (stale build output)

### 2. Contract Alignment

The C0 task spec and `frontend_contract.md` had minor directory naming differences. Resolution:

| C0 Spec | Contract | Decision |
|---------|----------|----------|
| `routes/` | `router/` | **`router/`** (contract wins) |
| `contexts/` | not listed | **`contexts/`** (added  needed for React Context: Auth, Theme) |
| not listed | `stores/` | **`stores/`** (contract requires Zustand) |
| not listed | `styles/` | **`styles/`** (contract specifies global styles dir) |
| not listed | `components/forms/` | **`components/forms/`** (contract requires forms subdir) |

### 3. Named Exports Only

Per `ui_integration_contract.md` 5.1: "禁止 default export". The skeleton `App.tsx` uses named export: `export function App()`.

---

## Directory Structure

```
frontend/
 .env.example          # Committable env template
 .env.local            # Local env (gitignored)
 .eslintrc.cjs         # ESLint config
 .prettierrc           # Prettier config
 Dockerfile            # Container build
 index.html            # Entry HTML
 package.json          # Dependencies (pnpm)
 pnpm-lock.yaml        # Lock file
 postcss.config.js     # PostCSS + Tailwind
 tailwind.config.js    # Tailwind design system
 tsconfig.json         # TypeScript strict config
 tsconfig.node.json    # Vite node config
 vite.config.ts        # Vite + proxy + alias
 src/
     App.tsx            # Root component (named export)
     main.tsx           # Entry point
     vite-env.d.ts      # Vite env type declarations
     assets/            # Static images/icons
     components/
        ui/            # Atomic UI (Buttons, Inputs)
        layout/        # App Shell (Sidebar, Header)
        forms/         # Form components
     contexts/          # React Contexts (Auth, Theme)
     hooks/             # Custom Hooks
     pages/             # Route Components (lazy loaded)
     router/            # Router configuration
     services/          # API calls (Axios instances)
     stores/            # Zustand state management
     styles/
        globals.css    # Tailwind directives + base layer
     types/             # TypeScript interfaces/types
     utils/             # Helper functions
```

## Dependencies (Production)

| Package | Version | Purpose |
|---------|---------|---------|
| react | ^18.2.0 | UI framework |
| react-dom | ^18.2.0 | DOM renderer |
| react-router-dom | ^6.20.1 | Routing |
| zustand | ^4.4.7 | State management |
| axios | ^1.13.5 | HTTP client |
| zod | ^3.22.4 | Schema validation |
| react-hook-form | ^7.48.2 | Form handling |
| @hookform/resolvers | ^3.3.2 | Zod resolver for RHF |
| @headlessui/react | ^1.7.17 | Headless UI components |
| @heroicons/react | ^2.0.18 | Icons |

## Dependencies (Dev)

| Package | Version | Purpose |
|---------|---------|---------|
| typescript | ^5.2.2 | Type checking |
| vite | ^5.0.0 | Build tool |
| tailwindcss | ^3.3.6 | CSS framework |
| vitest | ^1.0.0 | Testing |
| eslint | ^8.53.0 | Linting |
| prettier | ^3.1.0 | Formatting |
| @testing-library/react | ^14.1.2 | Component testing |

## Verification Evidence

```
$ pnpm exec tsc --noEmit
(exit code 0  zero errors)

$ pnpm dev
VITE v5.4.21  ready in 927 ms
  Local:   http://localhost:5173/
```

## Next Phase

Phase C1 will implement:
- Router configuration with protected routes
- Auth context + Zustand auth store
- API service layer (Axios instance with interceptors)
- App shell layout (Sidebar, Header)
- Login page

---

*Boot Contract acknowledged. Architecture Constitution > Boot Contract > all other contracts.*