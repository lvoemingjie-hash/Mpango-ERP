# Product Backlog & Future Roadmap

> **Status**: Living Document  
> **Purpose**: To track features, enhancements, and architectural changes that are explicitly **Out of Scope** for the MVP (Phase 1) but are planned for future iterations.

---

## 📦 Phase 2: Enhanced Retail & Marketing (Post-MVP)

### 1. Advanced Promotions Engine
*   **Context**: MVP only supports manual adjustments to base `Product.price`.
*   **Feature**: Automated promotion rules applied during order creation.
*   **Requirements**:
    *   New `Promotions` entity (type: percentage off, fixed amount, buy-x-get-y).
    *   Eligibility rules (date range, minimum order amount, specific SKUs).
    *   Engine to calculate `OrderItem.price` and `discount_amount` automatically.

### 2. Offline-First Capabilities (Offline Cart)
*   **Context**: MVP requires an internet connection for all state-changing operations.
*   **Feature**: Full offline ordering support for weak network environments.
*   **Requirements**:
    *   **Local Storage**: Persist product catalog and draft orders in IndexedDB/SQLite on the client.
    *   **Sync Queue**: A background service worker to queue offline actions (create order) and replay them when online.
    *   **Conflict Resolution**: UI flows to handle inventory shortage or price changes that occurred while the user was offline.

### 3. Multi-Warehouse & Transfers
*   **Context**: MVP treats inventory as a single aggregate pool per tenant.
*   **Feature**: Distinct inventory management for multiple physical locations.
*   **Requirements**:
    *   Expose `Warehouse` entity in APIs.
    *   New Workflow: `Internal Transfer` (Request -> Approve -> Ship -> Receive).
    *   Inventory visibility per warehouse in the Retailer App.

---

## 🛡️ Phase 3: Financial & Enterprise Compliance

### 4. Complex Refund Workflows
*   **Context**: MVP handles refunds as simple negative-value payment records created by admins.
*   **Feature**: Formal refund request and approval pipeline.
*   **Requirements**:
    *   New `RefundRequest` entity (Status: Requested, Approved, Rejected).
    *   Role-based approval steps (e.g., Finance Manager must approve refunds > $100).
    *   Integration with payment gateways (M-Pesa Reversal API) where possible.

### 5. Advanced Credit Management
*   **Context**: MVP strictly blocks orders if `Credit Limit` is exceeded.
*   **Feature**: Flexible credit overrides and approval flows.
*   **Requirements**:
    *   "Soft Block" mechanism: Allow orders to be created as `Blocked/Pending Approval` even if over limit.
    *   Approval workflow for Sales Managers to override limits on a per-order basis.
    *   Credit utilization history and aging reports.

---

## 🏗️ Technical Debt & Infrastructure (To be addressed post-launch)

*   **Audit Logging UI**: The backend records `InventoryLog` and `updated_by` fields, but there is no admin UI to view these audit trails in MVP.
*   **Automated Reconciliation**: MVP requires manual checking of M-Pesa transaction IDs. Future scope includes an automated job to ingest M-Pesa CSV statements and reconcile against `Payment` records.
*   **Cross-Tenant Analytics**: Super-Admin dashboard for platform owners to see aggregated stats across all Wholesalers (Data Warehouse solution).

