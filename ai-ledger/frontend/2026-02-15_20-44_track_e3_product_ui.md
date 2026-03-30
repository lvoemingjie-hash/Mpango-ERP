# Track E3: Product UI (v0.2.0)

**Date**: 2026-02-15 20:44 UTC+08:00
**Role**: Senior Product Engineer (Frontend Focus)
**Prerequisite**: Track E1 (Guardrail) & E2 (Staging) COMPLETE

---

## Objective

Build the UI that consumes the hardened backend and staging seed data without crashing or confusing the user. Focus on wiring, error handling, and tenant context awareness.

## Deliverables

### 1. Guardrail-Aware Error Handling

**`src/services/api.ts`** — Enhanced response interceptor:
- **500 + TenantContextMissing** → Red toast: "Security Alert: Tenant Context Lost. Please refresh."
- **403 PermissionDenied** → Yellow toast: "Access Denied: You do not have permission…"
- **409 InvalidStateTransition** → Yellow toast: "Action Not Allowed: conflicts with current state."
- **500+ generic** → Red toast: "Server Error: An unexpected server error occurred."

**`src/stores/toastStore.ts`** — Zustand store for toast notifications with auto-dismiss (6s).

**`src/components/ui/ToastContainer.tsx`** — Renders toast stack in top-right corner with type-specific icons and colors.

### 2. Tenant Context Awareness

**`src/components/layout/Header.tsx`** — Updated to show:
- Tenant code badge (e.g., "DEMO001") with building icon
- User name + primary role

**`src/components/layout/Sidebar.tsx`** — Added Orders and Inventory nav items.

### 3. Dashboard Page (Seed Data Visualization)

**`src/pages/DashboardPage.tsx`** — Replaced placeholder with:
- 4 summary cards: Total Orders, Active SKUs, Revenue (Paid+Fulfilled), Pending Confirmation
- Order status breakdown grid (all 7 statuses with counts)
- Recent orders table with status badges

### 4. Order List Page (State-Aware Actions)

**`src/pages/orders/OrderListPage.tsx`** — Full order management:
- Table with ID, status, items, total, notes, created date
- **Confirm** button: only visible when status is `draft` (legal transition)
- **Cancel** button: only visible when status is `draft` or `confirmed`
- Buttons disabled when user lacks `orders:write`/`orders:update` permission
- Shows "Read-only" label for users without write permission
- Shows "No actions" for terminal states (fulfilled, cancelled, voided)
- Success toasts on action completion; error toasts via global interceptor

### 5. Inventory Page

**`src/pages/inventory/InventoryPage.tsx`** — Card grid showing:
- SKU name + code
- In Stock / Out of Stock badge
- On Hand, Reserved, Available quantities

### 6. Invite Page (Error Handling)

**`src/pages/invite/InvitePage.tsx`** — Public route at `/invite/:code`:
- Calls `GET /api/v1/invitations/{code}` to verify
- **Valid**: Shows wholesaler name, expiry, "Continue to Login" button
- **Invalid/Expired (400/403)**: Friendly "Invitation Expired or Invalid" page with icon
- **Not Found (404)**: "Invitation not found" message
- **Server Error**: Generic retry message
- Never shows blank screen or console error

## Files Created

| File | Purpose |
|------|---------|
| `src/types/order.ts` | Order types, status labels/colors, allowed transitions |
| `src/types/inventory.ts` | StockView type |
| `src/services/orderService.ts` | Order API service (list, confirm, cancel) |
| `src/services/inventoryService.ts` | Inventory API service (list stocks) |
| `src/stores/toastStore.ts` | Toast notification store |
| `src/components/ui/ToastContainer.tsx` | Toast renderer |
| `src/pages/orders/OrderListPage.tsx` | Order list with state-aware actions |
| `src/pages/inventory/InventoryPage.tsx` | Inventory card grid |
| `src/pages/invite/InvitePage.tsx` | Invitation verification page |

## Files Modified

| File | Change |
|------|--------|
| `src/services/api.ts` | Added guardrail-aware error toasts (500/403/409) |
| `src/App.tsx` | Added ToastContainer |
| `src/components/layout/Header.tsx` | Added tenant code badge + BuildingOffice2Icon |
| `src/components/layout/Sidebar.tsx` | Added Orders + Inventory nav items |
| `src/pages/DashboardPage.tsx` | Replaced placeholder with data-driven dashboard |
| `src/router/AppRouter.tsx` | Added /orders, /inventory, /invite/:code routes |

## Verification

- **`tsc --noEmit`**: Zero errors
- **`pnpm dev`**: Vite dev server starts on :5173
- Backend proxy: `/api` → `http://localhost:8000`

## Design Constraints Followed

1. **Logic > Aesthetics**: Standard Tailwind, no custom CSS generators
2. **No Magic Generators**: Only standard HTML/Tailwind + existing components (Badge, Modal, Pagination)
3. **Focus on Wiring**: OrderService → OrderList, UserRole → Button.disabled
