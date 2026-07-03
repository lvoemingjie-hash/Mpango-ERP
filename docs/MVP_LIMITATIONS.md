# MVP Limitations — Mpango ERP v0.2.0

**Last Updated:** 2026-02-18
**Target Release:** v0.2.0 (Investor Demo)

This document explicitly states known limitations of the MVP release to set correct expectations for stakeholders, demo audiences, and early adopters.

---

## 1. Warehouse: Single Warehouse Per Tenant

**Limitation:** Each tenant (wholesaler) supports **only 1 warehouse** in v0.2.0.

**Impact:**
- All inventory (`inventory_stocks` table) is implicitly associated with a single warehouse.
- There is no warehouse selection or transfer UI.
- The `Warehouse` entity is design-reserved in the data model but has **no functional endpoints**.

**Workaround:** Wholesalers with multiple physical locations should use a single "virtual warehouse" representing aggregated stock.

**Planned Resolution:** Multi-warehouse support (inventory per-warehouse, inter-warehouse transfers, warehouse picker UI) is scoped for **Phase 2** (GAP 14 in PRD gap analysis).

---

## 2. Notifications: File-Logged Simulation

**Limitation:** Email and SMS notifications are **simulated** — all messages are written to log files instead of delivered to real recipients.

**Current Behavior:**
| Channel | Action | Log Destination |
|---|---|---|
| Email | Order confirmed → "Order #{id} Confirmed" | `backend/logs/email.log` |
| SMS | Order shipped (fulfilled) → "Order #{id} is on the way!" | `backend/logs/sms.log` |

**Impact:**
- No actual email/SMS delivery occurs in v0.2.0.
- The notification service interface (`NotificationService.send_email()` / `.send_sms()`) is provider-agnostic and ready for real providers.
- Retailer contact information (email, phone) uses placeholder values.

**Planned Resolution:**
- **Phase 2:** Integrate Africa's Talking (SMS gateway for Kenya) or Twilio.
- **Phase 2:** Integrate SendGrid or SES for transactional email.
- **Phase 2:** Add retailer profile fields for `phone_number` and `email`.

---

## 3. Data Export: CSV Format Only

**Limitation:** Data export endpoints only support **CSV** format.

**Current Behavior:**
| Endpoint | Output |
|---|---|
| `GET /api/v1/orders/export?format=csv` | Orders CSV (streaming) |
| `GET /api/v1/inventory/export?format=csv` | Inventory CSV (streaming) |
| `POST /api/v1/exports` | Async job-based export (CSV via S4 job queue) |

**Impact:**
- No PDF, XLSX, or other formats available.
- CSV files can be opened in Excel/Google Sheets but lack formatting, charts, or branding.

**Workaround:** Import CSV files into Google Sheets or Excel for custom formatting and sharing.

**Planned Resolution:**
- **Phase 2:** Add `format=xlsx` option using `openpyxl`.
- **Phase 2/3:** PDF export for invoices and reports (via `weasyprint` or `reportlab`).

---

## 4. Payments: M-Pesa STK Push Not Integrated

**Limitation:** M-Pesa STK Push is **documented but not implemented**. Payment recording is manual — an admin/finance user creates payment records via the API.

**Impact:**
- No real-time mobile money integration.
- Payment confirmation must be entered manually by staff.

**Planned Resolution:** M-Pesa Daraja API integration is scoped for **Phase 2** with STK Push webhook endpoint and automated payment reconciliation.

---

## 5. Finance: JSON Invoices Only

**Limitation:** Invoice generation returns **JSON data**, not downloadable PDF documents.

**Current Behavior:**
- `GET /api/v1/orders/{order_id}/invoice` returns a JSON invoice object with line items, totals, and metadata.
- The frontend renders this data in a styled view, but there is no print-optimized PDF output.

**Planned Resolution:**
- **Phase 2:** Server-side PDF generation using `weasyprint` with branded invoice templates.
- **Phase 2:** Receipt printing support for thermal printers (POS use case).

---

## 6. Offline Mode: Not Supported

**Limitation:** The system requires an active internet connection. **No offline capability** is available in v0.2.0.

**Impact:**
- Sales reps in areas with poor connectivity cannot create orders.
- No local data caching or sync mechanism exists.

**Planned Resolution:** Progressive Web App (PWA) capabilities with offline order creation and background sync are scoped for **Phase 3**.

---

## 7. Localization: Hardcoded to KES / English

**Limitation:** All monetary values are denominated in **Kenya Shillings (KES)** and the interface language is **English only**.

**Impact:**
- No multi-currency support (TZS, UGX, USD).
- No Swahili or other language options.

**Planned Resolution:**
- **Phase 2:** Localization framework (i18n) for English + Swahili.
- **Phase 3:** Multi-currency support with configurable base currency per tenant.

---

## 8. Data Intake: Catalog SKU Creation Only

**Limitation:** Data Intake Apply creates **catalog SKU records only** in the current MVP scope.

**Impact:**
- Apply creates catalog SKU records only.
- It does not initialize inventory.
- It does not create retailer-specific prices.
- It does not create image assets, barcode lookup automation, custom attributes, or sellable readiness.
- Orders require an active SKU, stock, and retailer price.

**Planned Resolution:**
- **Future phase:** Extend post-intake workflows so stock, retailer pricing, barcode workflows, and sellable readiness can be configured through explicit follow-up steps or dedicated intake slices.

---

## Summary Table

| Area | v0.2.0 Status | Target Phase |
|---|---|---|
| Warehouse | Single warehouse per tenant | Phase 2 |
| Notifications | File-logged simulation | Phase 2 |
| Data Export | CSV only | Phase 2 |
| M-Pesa Payments | Manual entry only | Phase 2 |
| Invoices | JSON (no PDF) | Phase 2 |
| Offline Mode | Not supported | Phase 3 |
| Localization | KES / English only | Phase 2-3 |
| Data Intake | Catalog SKU creation only | Future phase |
