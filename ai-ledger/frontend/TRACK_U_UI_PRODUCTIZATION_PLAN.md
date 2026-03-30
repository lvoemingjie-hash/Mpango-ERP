# Track U: UI Productization Plan — Reducing Cognitive Friction

**Phase:** P-B (Session 4 Cont.)
**Objective:** Polish the UI for the Investor Demo / First-Time User Experience (FTUE).
**Constraints:** Frontend-only changes (React/TSX). No new features.

---

## 1. The 3 Core User Journeys (MVP)

We will optimize the UI specifically for these three "Happy Paths":

### Journey A: The "Day One" Wholesaler (Onboarding)
**Persona:** A new business owner logging in for the first time.
1.  **Log In**: User enters credentials.
2.  **Dashboard**: Sees a clean, welcoming "Zero State" dashboard (not broken/empty).
3.  **Action**: Navigates to **Inventory** to add their first product (SKU).
4.  **Result**: Sees the new item listed and feels "setup is complete".

### Journey B: The Order Manager (Daily Ops)
**Persona:** A sales manager handling incoming retailer orders.
1.  **Signal**: Sees a "Pending Order" count on the Dashboard.
2.  **Review**: Navigates to **Orders**, clicks on a `Draft` order to review details.
3.  **Action**: Clicks **Confirm**.
4.  **Fulfillment**: Marks the order as **Shipped** (Fulfilled).
5.  **Result**: Downloads the **Invoice** JSON (PDF placeholder) for the physical package.

### Journey C: The Financial Glance (Executive Check-in)
**Persona:** The business owner checking health at the end of the day.
1.  **Dashboard**: Checks "Today's Revenue" and "Outstanding Receivables" KPIs.
2.  **Deep Dive**: Navigates to **Finance** (newly added in Phase P-A).
3.  **Action**: Exports the **Financial Summary** report (CSV).

---

## 2. Friction Points Analysis (The "Why")

Based on current codebase analysis (`DashboardPage.tsx`, `Sidebar.tsx`, etc.):

| User Journey | Current "Engineer UI" Friction | Impact |
| :--- | :--- | :--- |
| **Global Navigation** | Sidebar items `Tenants` and `Users` feel like "Admin tools" rather than business functions. `Settings` icon is a generic "Tooth" icon. | Users feel they are using a database tool, not a business app. |
| **Empty Dashboard** | "No orders found. Run the seed script first." | intimidating/confusing for a production user. |
| **Data Loading** | `Loading dashboard...` (plain text) causes layout shift. | Feels slow and unpolished. |
| **Order List** | Inline buttons (Confirm/Cancel) clutter the row. "View Details" is missing (users have to guess they can't click the row?). | hard to scan large lists; unclear how to see item details without expanding. |
| **Inventory** | No visual distinction between "Low Stock" and "Normal Stock" other than text. | Hard to spot urgent restock needs. |
| **Feedback** | Toast messages are generic (`Order Confirmed`). | Doesn't confirm *what* happened explicitly enough (e.g., "Order #123 Confirmed & Invoice Generated"). |

---

## 3. UI Action Items (The "What")

### 3.1 IA & Navigation Polish (`Sidebar.tsx`)
*   **Rename & Reorder**:
    1.  `Dashboard` (Home)
    2.  `Orders` (Clipboard) — *Move to top, primary action.*
    3.  `Inventory` (Cube)
    4.  `Finance` (Banknotes) — *Keep as is.*
    5.  `Customers` (rename from `Retailers` or `Tenants` context) — *If `Tenants` lists retailers, rename to `Customers`. If it lists system tenants, hide for non-system-admins.*
    6.  `Team` (rename from `Users`) — *Friendlier term.*
*   **Visuals**: Add active state indicator (vertical bar or specialized background) to make current location obvious.

### 3.2 Dashboard "Zero State" (`DashboardPage.tsx`)
*   **Condition**: When `orders.length === 0`.
*   **Design**:
    *   Show a friendly illustration (SVG icon) or a gray placeholder box.
    *   **Text**: "No orders yet. Your business is ready to roll!"
    *   **CTA Button**: "View Inventory" (Drive them to check stock) or "Invite Retailers" (if that feature exists on frontend).
*   **Loading**: Replace `Loading dashboard...` with a `<DashboardSkeleton />` component (gray pulsing boxes matching the grid layout).

### 3.3 Enhanced Order List (`OrderListPage.tsx`)
*   **Status Badges**: Ensure consistent colors:
    *   `Draft`: Gray
    *   `Confirmed`: Blue
    *   `Paid`: Green
    *   `Fulfilled`: Purple
    *   `Cancelled`: Red
*   **Empty State**: "No orders found" -> "Waiting for orders. Share your catalog to get started."
*   **Tooltips**: Add tooltips to the Action Buttons explaining consequences (e.g. "Confirming locks the order price").

### 3.4 Inventory Visuals (`InventoryPage.tsx`)
*   **Low Stock Warning**: If `quantity_available < 10`, highlight the row number in **Red** or add a generic "Warning" icon.
*   **Currency**: Ensure all prices display `KES` prefix explicitly.

### 3.5 General Polish
*   **Page Titles**: Ensure every page has a standard `<PageHeader title="..." description="..." />` component so spacing/fonts are consistent.
*   **404 Page**: Make it friendly ("Lost in the warehouse?") with a "Back to Dashboard" button.
