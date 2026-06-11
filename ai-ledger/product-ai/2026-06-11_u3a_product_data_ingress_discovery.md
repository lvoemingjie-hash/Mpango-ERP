# U3-A: Product Data Ingress Discovery & Design (R1 Revised)

**Branch:** `codebuddy/u3a-product-data-ingress-discovery-2026-06-11`
**Date:** 2026-06-11
**Sprint:** U3-A (Research & Design — No Production Code Changes)
**Revision:** R1 (2026-06-11 23:11) — Permission model correction, U3-B sub-sliced into 4, `skus:import` defined
**Author:** AI Engineer
**Status:** Pending CTO Final Approval

---

## 1. Current State

### 1.1 SKU Data Model

The `skus` table (created in Alembic migration `004_phase_b4_sku_inventory_mvp.py`) lives inside each tenant schema (`t_dev`, `t_test`, etc.) and has exactly **6 business fields**:

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK, default `gen_random_uuid()` | Inherited from `BaseModel` |
| `sku_code` | VARCHAR(64) | UNIQUE, NOT NULL | Human-readable product code |
| `name` | VARCHAR(255) | NOT NULL | Product display name |
| `description` | TEXT | nullable | Free-text description |
| `unit` | VARCHAR(32) | nullable | e.g. "kg", "pack", "box" |
| `category` | VARCHAR(64) | nullable | e.g. "Flour", "Beverages" |
| `is_active` | BOOLEAN | default `true` | Soft toggle |
| `created_at`, `updated_at` | TIMESTAMP | auto | From `AuditMixin` |
| `is_deleted`, `deleted_at` | BOOLEAN / TIMESTAMP | soft-delete | From `AuditMixin` |
| `created_by`, `updated_by` | UUID | nullable | From `UserTrackingMixin` |

**What is missing:** No `barcode`, no `image_url`, no `price` (pricing is separate), no `custom_attributes`, no `tags`, no `brand`, no `weight/volume` fields.

### 1.2 Related Data Tables

| Table | Relationship | Key Detail |
|-------|-------------|------------|
| `inventory_stocks` | 1:1 per SKU | Auto-created via `ensure_stock_row()` — `quantity_on_hand`, `quantity_reserved` |
| `inventory_movements` | Many per SKU | Audit journal of all stock changes |
| `retailer_prices` | Many per SKU | `retailer_id + sku_id → price` (UNIQUE constraint on pair) |
| `order_items` | Many per SKU | References `sku_code` + `product_name` (denormalized) |

### 1.3 Current SKU Creation Flow

```
User fills SKUFormModal → POST /api/v1/skus → SKUService.create_sku()
  → checks duplicate sku_code → SKURepository.create() → DB INSERT
  → inventory_ensure_stock_row() creates matching inventory_stocks row
```

- **Single-record only**: No bulk/batch API endpoints exist.
- **Frontend form**: `SKUFormModal.tsx` with fields: `sku_code`, `name`, `description`, `unit`, `category` — mirrors DB columns exactly.
- **Service validation**: Checks for duplicate `sku_code` within tenant schema before insert.

### 1.4 Existing Data Volume

The seed script (`backend/scripts/seed_demo_data.py`) creates **10 demo SKUs** — all Kenyan FMCG products (maize flour, sugar, cooking oil, rice, tea, soap, salt). This reflects the current target market: East African wholesale/distribution businesses with product catalogs ranging from 20 to 500+ SKUs.

### 1.5 JSONB Extensibility Precedents

The codebase already uses JSONB columns in two places:

1. **`sys_audit_logs.metadata_`** (JSONB) — stores arbitrary key-value audit metadata
2. **`platform_tenants.provisioning_log`** (JSONB) — stores tenant provisioning events

This establishes JSONB as an accepted extensibility pattern in the project, though it has not been applied to the SKU/product domain.

### 1.6 Multi-Tenant Architecture

- **Schema-per-tenant**: Each tenant gets its own PostgreSQL schema (`t_dev`, `t_test`, etc.)
- **Global tenant filter**: SQLAlchemy `do_orm_execute` event + `ContextVar`-based tenant context automatically scopes all queries
- **Bootstrap DDL**: `bootstrap_tenant_schema.py` creates all tables (including `skus`) per tenant schema
- **Implication**: Any schema change to `skus` must be applied via Alembic migration across all tenant schemas

### 1.7 Existing RBAC Permission System

**This is critical context that the original U3-A report missed.** Mpango already has a full Role-Based Access Control system. The claim in Section 2.2.7 ("No permission gating") was incorrect.

#### Permission Model

| Table | Location | Purpose |
|-------|----------|---------|
| `permissions` | Tenant schema | Permission codes: `skus:read`, `skus:create`, `skus:update`, `orders:create`, etc. |
| `roles` | Tenant schema | Roles: `admin`, `sales`, `warehouse`, `finance` |
| `role_permissions` | Tenant schema | M2M join: which roles hold which permissions |
| `user_roles` | Tenant schema | M2M join: which users hold which roles |

The `Permission` model (`backend/models/user.py` lines 101-134) uses the format `<resource>:<action>` (e.g., `skus:create`). The `admin` role gets ALL permissions assigned at bootstrap.

#### Enforcement Mechanism

All SKU API routes already enforce permissions via `RequirePermission()` from `backend/api/middleware/rbac.py`:

```python
# backend/api/v1/skus.py (existing code)
@router.get("/")
async def list_skus(..., token = Depends(RequirePermission("skus:read"))): ...

@router.post("/")
async def create_sku(..., token = Depends(RequirePermission("skus:create"))): ...

@router.put("/{sku_code}")
async def update_sku(..., token = Depends(RequirePermission("skus:update"))): ...
```

`RequirePermission` checks the user's roles (loaded from DB via tenant context), collects all permission codes, and returns 403 if the required code is absent. Super admins bypass the check.

#### Current SKU-Related Permission Codes

| Code | Used By | Status |
|------|---------|--------|
| `skus:read` | `GET /skus`, `GET /skus/{code}` | Enforced |
| `skus:create` | `POST /skus` | Enforced |
| `skus:update` | `PUT /skus/{code}` | Enforced |
| **`skus:import`** | **Not yet defined** | **Missing — must be created in U3-B** |

#### Implication for U3-B

U3-B MUST:
1. Create a new `skus:import` permission code in the tenant schema
2. Register it in `create_wholesaler.py` + `seed_demo_data.py` (both seed the full permission list)
3. Protect `POST /skus/batch` and `POST /skus/import` with `RequirePermission("skus:import")`
4. Assign `skus:import` to the `admin` role at bootstrap
5. Decide whether to also assign it to `warehouse` role (warehouse staff often do bulk data entry)

**Do NOT rely on reusing `skus:create`**: Import is a fundamentally different operation — it is bulk, accepts raw file uploads, and has different error semantics. A separate permission allows tenants to grant "create one product at a time" without granting "import 500 products at once."

---

## 2. Problem Statement

### 2.1 The Core Problem

A new tenant signing up for Mpango typically has an existing product catalog — often in a spreadsheet (Excel/CSV), sometimes in another system (QuickBooks, Tally, WhatsApp catalog). Today, they must enter every product **one at a time** through the SKU form modal. For a business with 200 SKUs, this is a 2-4 hour tedious task that creates immediate friction at onboarding.

### 2.2 Specific Pain Points

1. **No bulk creation**: Every product must be entered individually via a modal form
2. **No field mapping**: Tenants coming from different systems have different column names and structures
3. **No custom attributes**: A flour distributor needs "grade" (e.g., "Grade 1", "Grade 2"); a beverage distributor needs "volume" (e.g., "500ml", "1L"). The current rigid schema supports none of this.
4. **No barcode/EAN support**: Many FMCG distributors track products by barcode, which Mpango cannot capture or scan
5. **No image support**: Product images help field sales teams identify items quickly — currently not possible
6. **No import validation feedback**: When bulk data has errors (duplicates, missing fields), there is no mechanism to report row-level errors
7. **Missing `skus:import` permission**: The existing RBAC system already gates `skus:read`, `skus:create`, `skus:update` (see Section 1.7). However, there is no `skus:import` permission code. The batch import endpoints would either need a new dedicated permission or a decision to reuse `skus:create`. **CTO directive: import requires its own permission — do not skip this.**

### 2.3 Design Constraints

- **Do not break existing single-SKU creation flow** — it must continue working
- **Schema-per-tenant architecture** — any DDL change propagates to all tenant schemas
- **Mobile-first users** — many Mpango users are on phones, so field mapping UX must be simple
- **East African market** — CSV is more common than Excel; mobile scanning (camera) is high-value future

---

## 3. Design Options

### 3.1 Option A: Rigid CSV Import (Simplest)

**Approach:** Define a fixed CSV template with columns matching `skus` table exactly: `sku_code`, `name`, `description`, `unit`, `category`. Users must format their data to match.

**Pros:**
- Simplest to implement (~2 days)
- No schema changes needed
- Predictable validation rules

**Cons:**
- Cannot handle custom attributes
- Users must reformat their data to match Mpango's template — friction
- No extensibility path; any new field requires template change + migration
- **CTO directive explicitly warns against this**: "不把 CSV-only 作为最终架构"

**Verdict: Not recommended as final architecture. Could be a tactical v1 shortcut, but locks us into rigidity.**

---

### 3.2 Option B: Flexible Field Mapping + Custom Attributes (JSONB)

**Approach:**
1. User uploads CSV/Excel with **any column structure**
2. Mpango shows a **field mapping UI**: "Which of your columns maps to Product Code? Product Name? Category?"
3. Unmapped columns are optionally stored in a new `custom_attributes` JSONB column on `skus`
4. Backend provides a **batch SKU creation endpoint** (`POST /api/v1/skus/batch`)

**Schema change:**
```sql
ALTER TABLE skus ADD COLUMN custom_attributes JSONB DEFAULT '{}';
```

**Pros:**
- Accepts any CSV format — users don't reformat their data, they map it
- Custom attributes via JSONB support tenant-specific needs without schema changes
- JSONB is already an accepted pattern in the codebase
- Extensible to barcode, brand, weight, etc. without migrations
- Field mapping UI is reusable for future import types (customers, orders)

**Cons:**
- More complex frontend (mapping wizard: 2-3 extra screens)
- JSONB queries are slower than native columns for filtering/sorting
- Need to decide: which attributes are "native" (searchable/sortable) vs "custom" (display-only)
- Batch endpoint needs careful transaction management (partial success handling)

**Estimated effort:** 4-6 days (backend 2 days + frontend field mapping 3 days + testing 1 day)

---

### 3.3 Option C: EAV (Entity-Attribute-Value) for Custom Fields

**Approach:** Create a `sku_attributes` table with `sku_id`, `attribute_name`, `attribute_value` columns.

**Pros:**
- Fully normalized — each custom attribute is a queryable row
- Supports typed values (string, number, date)

**Cons:**
- Complex queries (self-joins per attribute)
- Poor performance at scale
- Overkill for current Mpango scale (50-500 SKUs per tenant)
- No existing precedent in the codebase

**Verdict: Over-engineered for current scale. JSONB is simpler and already proven in the codebase.**

---

### 3.4 Option D: Full Product Information Management (PIM) System

**Approach:** Build a complete PIM with product families, variants, multi-channel publishing, etc.

**Verdict: Far beyond current MVP scope. Defer to long-term roadmap.**

---

### Recommendation Summary

| Option | Flexibility | Complexity | Extensibility | Fit |
|--------|------------|------------|---------------|-----|
| A: Rigid CSV | Low | Low | None | Poor |
| **B: Field Mapping + JSONB** | **High** | **Medium** | **High** | **Best** |
| C: EAV | High | High | High | Over-engineered |
| D: Full PIM | Very High | Very High | Very High | Future |

**Recommended: Option B** — Field mapping + JSONB custom attributes. Balances flexibility, implementation cost, and extensibility.

---

## 4. Recommended MVP Slice (U3-B Scope)

### 4.1 MVP Scope: "Upload & Map"

The MVP implements the minimum viable version of Option B:

#### Backend Changes

| Component | Change | Files |
|-----------|--------|-------|
| **SKU Model** | Add `custom_attributes JSONB DEFAULT '{}'` | `backend/models/sku.py` |
| **Alembic Migration** | New migration adding `custom_attributes` column | `backend/alembic/versions/0xx_sku_custom_attributes.py` |
| **Pydantic Schemas** | Add `custom_attributes: Optional[Dict[str, Any]]` to Create/Update/Read | `backend/schemas/sku.py` |
| **Batch Endpoint** | `POST /api/v1/skus/batch` — accepts array of SKU dicts + field mapping spec | `backend/api/v1/skus.py` |
| **Batch Service** | `SKUService.create_skus_batch()` — validates, deduplicates, inserts within transaction | `backend/services/sku_service.py` |
| **Import Endpoint** | `POST /api/v1/skus/import` — accepts CSV file upload, returns parsed columns + preview | `backend/api/v1/skus.py` |
| **Import Service** | `ImportService.parse_csv()` — CSV parsing with encoding detection | New: `backend/services/import_service.py` |
| **Permission: skus:import** | New permission code + seed in `create_wholesaler.py` & `seed_demo_data.py`; assign to `admin` role at bootstrap | `backend/scripts/create_wholesaler.py`, `backend/scripts/seed_demo_data.py` |
| **Batch/Import RBAC** | Protect `POST /skus/batch` and `POST /skus/import` with `RequirePermission("skus:import")` | `backend/api/v1/skus.py` |

**Batch endpoint behavior:**
```python
# Request
POST /api/v1/skus/batch
{
  "skus": [
    {"sku_code": "F001", "name": "Maize Flour 2kg", "category": "Flour",
     "custom_attributes": {"brand": "Jogoo", "grade": "Grade 1"}},
    ...
  ],
  "on_conflict": "skip"  # or "update" or "error"
}

# Response
{
  "created": 45,
  "skipped": 3,
  "updated": 0,
  "errors": [
    {"row": 12, "sku_code": "F001", "error": "duplicate sku_code"}
  ]
}
```

#### Frontend Changes

| Component | Change | Files |
|-----------|--------|-------|
| **Import Wizard Step 1** | Upload CSV/Excel file, show raw preview | New: `frontend/src/pages/skus/ImportWizard/` |
| **Import Wizard Step 2** | Field mapping UI: drag/map CSV columns → Mpango fields + custom attributes | New: `frontend/src/pages/skus/ImportWizard/Step2FieldMapping.tsx` |
| **Import Wizard Step 3** | Preview mapped data, show validation errors, confirm import | New: `frontend/src/pages/skus/ImportWizard/Step3Preview.tsx` |
| **SKU Form Update** | Add `custom_attributes` display/edit section | `frontend/src/pages/skus/SKUFormModal.tsx` |
| **SKU List Update** | Show custom attribute columns (configurable) | `frontend/src/pages/skus/SKUListPage.tsx` |
| **Import Service** | Frontend service wrapping import/batch API calls | New: `frontend/src/services/importService.ts` |

**Import wizard UX flow:**
```
Step 1: Upload File
  → Drag & drop or click to upload .csv/.xlsx
  → Backend parses, returns: {columns: [...], rows_preview: [...], row_count: N}

Step 2: Map Fields
  → Left: CSV columns. Right: Mpango fields (sku_code*, name*, description, unit, category)
  → "Add custom attribute" button for unmapped columns
  → Required fields highlighted (sku_code, name)
  → Save mapping as template for future use (optional, post-MVP)

Step 3: Preview & Import
  → Show first 10 rows with mapped data
  → Highlight validation errors (missing required, duplicate sku_codes)
  → "Import N products" button
  → Progress bar during import
  → Results summary: "Created 45, Skipped 3, Errors 2"
```

### 4.2 Explicitly Out of Scope for MVP

| Feature | Reason |
|---------|--------|
| Image upload/import | Requires file storage infrastructure (S3/CloudBase Storage) — defer to U3-C |
| Barcode scanning | Requires camera API integration — defer to U4 |
| Excel (.xlsx) support | Start with CSV only; add xlsx parsing after core flow works |
| Import templates (save/load mappings) | Nice-to-have, defer |
| Webhook/API-based product sync | Requires external API design — long-term roadmap |
| Product variants (size, flavor) | Requires variant data model design — separate discovery |

### 4.3 U3-B Sub-Slice Breakdown (4 Slices)

The original 5-day U3-B estimate is split into 4 independently shippable sub-slices. Each slice produces a working, testable increment and can be reviewed/merged independently.

---

#### Slice U3-B1: Permission Foundation (0.5 day)

**Goal:** Define `skus:import` permission so batch endpoints have RBAC enforcement from day one.

| Task | File(s) | Notes |
|------|---------|-------|
| Add `skus:import` permission code | `backend/scripts/create_wholesaler.py` | Add `("skus:import", "Import SKUs in bulk via CSV upload")` to `permissions_data` list |
| Add `skus:import` permission code | `backend/scripts/seed_demo_data.py` | Add `("skus:import", "Import SKUs")` to `PERMISSION_CODES` list |
| Assign to `admin` role | `backend/scripts/create_wholesaler.py` | Already auto-assigned: `assign_all_permissions_to_admin()` picks up all permissions |
| Test: existing bootstrap creates the permission | `backend/scripts/create_wholesaler.py` | Run bootstrap, verify `skus:import` exists in `permissions` table |

**Acceptance criteria:**
- `skus:import` permission exists in tenant `permissions` table after bootstrap
- `admin` role holds `skus:import`
- No API changes — this is purely seed data

---

#### Slice U3-B2: Backend Batch + CSV Import (1.5 days)

**Goal:** Working `POST /skus/batch` and `POST /skus/import` endpoints with RBAC enforcement.

| Task | File(s) | Notes |
|------|---------|-------|
| Alembic migration: add `custom_attributes JSONB` | `backend/alembic/versions/0xx_sku_custom_attributes.py` | `ALTER TABLE skus ADD COLUMN custom_attributes JSONB DEFAULT '{}'` |
| Update SKU ORM model | `backend/models/sku.py` | Add `custom_attributes: Mapped[dict] = mapped_column(JSONB, ...)` |
| Update Pydantic schemas | `backend/schemas/sku.py` | Add `custom_attributes: Optional[Dict[str, Any]]` to `SKUCreateRequest`, `SKUUpdateRequest`, `SKURead` |
| Implement `POST /api/v1/skus/batch` | `backend/api/v1/skus.py` | Array input, duplicate detection, `on_conflict` strategy, row-level errors, **protected by `RequirePermission("skus:import")`** |
| Implement `POST /api/v1/skus/import` | `backend/api/v1/skus.py` | `multipart/form-data` CSV upload, **protected by `RequirePermission("skus:import")`** |
| CSV parsing service | New: `backend/services/import_service.py` | `chardet` encoding detection, BOM stripping, column/row extraction |
| Unit tests | `backend/tests/` | Batch duplicate handling, CSV edge cases (BOM, encoding, empty file) |

**Acceptance criteria:**
- `POST /skus/import` accepts CSV and returns `{columns, rows_preview, row_count}`
- `POST /skus/batch` creates SKUs with `on_conflict: skip | update | error`
- Both endpoints return 403 when user lacks `skus:import`
- Existing `POST /skus` (single create) unchanged, still requires `skus:create`
- Row-level errors returned for invalid entries without failing the batch

---

#### Slice U3-B3: Frontend Import Wizard (2 days)

**Goal:** Complete 3-step import wizard in the frontend.

| Task | File(s) | Notes |
|------|---------|-------|
| Import service (API wrapper) | New: `frontend/src/services/importService.ts` | `uploadCSV()`, `batchImport()`, typed responses |
| Step 1: Upload | New: `frontend/src/pages/skus/ImportWizard/Step1Upload.tsx` | Drag-and-drop / click upload, calls `/skus/import`, shows raw preview table |
| Step 2: Field Mapping | New: `frontend/src/pages/skus/ImportWizard/Step2FieldMapping.tsx` | Dropdown selectors: CSV column → Mpango field. Auto-detect by header name. Unmapped → custom attribute. |
| Step 3: Preview & Confirm | New: `frontend/src/pages/skus/ImportWizard/Step3Preview.tsx` | Show mapped data preview, highlight validation errors, confirm button calls `/skus/batch`, results summary |
| Wire from SKU List | `frontend/src/pages/skus/SKUListPage.tsx` | Replace disabled "Import Products" placeholder with working button → opens ImportWizard |

**Acceptance criteria:**
- User can upload a CSV file and see raw preview
- Field mapping correctly dispatches CSV columns to Mpango fields
- Unmapped columns become custom attributes
- Preview shows validation errors before import
- Results summary shows created/skipped/errored counts
- Import button in SKU list opens the wizard

---

#### Slice U3-B4: Custom Attributes in SKU UI (1 day)

**Goal:** Display and edit `custom_attributes` in the existing SKU form and list.

| Task | File(s) | Notes |
|------|---------|-------|
| SKU Form: custom attributes editor | `frontend/src/pages/skus/SKUFormModal.tsx` | Key-value pair editor (add/remove rows) |
| SKU List: optional columns | `frontend/src/pages/skus/SKUListPage.tsx` | Show custom attribute columns when present; toggle visibility |
| Update SKU service | `frontend/src/services/skuService.ts` | Support `custom_attributes` in create/update payloads |

**Acceptance criteria:**
- SKU form shows existing custom attributes and allows editing
- SKU list shows custom attributes as visible columns
- Single SKU creation (non-import) can also set custom attributes

---

### 4.4 Total Effort Summary

| Slice | Duration | Deliverable |
|-------|----------|-------------|
| U3-B1: Permission Foundation | 0.5 day | `skus:import` in RBAC tables |
| U3-B2: Backend Batch + CSV | 1.5 days | Working import/batch endpoints with RBAC |
| U3-B3: Frontend Import Wizard | 2 days | Complete 3-step import wizard |
| U3-B4: Custom Attributes UI | 1 day | Custom attributes in SKU form + list |
| **Total** | **5 days** | |

---

## 5. Future Roadmap

### Phase 1 (U3-B1 through U3-B4): CSV Import with Field Mapping — 5 days
Split into 4 sub-slices as detailed in Section 4.3: Permission Foundation → Backend Batch/CSV → Frontend Import Wizard → Custom Attributes UI.

### Phase 2 (U3-C): Product Images — 3 days
- Add `image_url` column to `skus` (VARCHAR, nullable)
- Integrate with CloudBase Storage or S3 for image hosting
- Support image upload in SKU form and bulk import (ZIP file with images, filename → sku_code mapping)
- Thumbnail generation for SKU list view

### Phase 3 (U4-A): Barcode Support — 3 days
- Add `barcode` column to `skus` (VARCHAR, nullable, indexed)
- Mobile camera scan: integrate browser BarcodeDetector API or QuaggaJS
- Barcode search in SKU list and order creation
- Support EAN-13, Code-128 formats

### Phase 4 (U5-A): Excel Support & Import Templates — 2 days
- Add xlsx parsing (using `openpyxl` backend / SheetJS frontend)
- Save/load field mapping templates per tenant
- Auto-detect common formats (first row = headers detection improvement)

### Phase 5 (U6-A): Custom Attribute Schema — 5 days
- Move from ad-hoc JSONB to a managed custom attribute system:
  - `sku_attribute_definitions` table: tenant defines attribute name, type (text/number/select), options
  - `sku_attributes` remains JSONB but is validated against definitions
  - Admin UI to manage attribute definitions
- Enables typed filtering, faceted search, dropdown options

### Phase 6 (Long-term): External Integrations — 10+ days
- QuickBooks product sync
- Tally ERP integration
- WhatsApp Business Catalog import
- REST API for third-party product data push

---

## 6. Risks and Open Questions

### 6.1 Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| **CSV encoding issues** (UTF-8 vs Latin-1, BOM headers) | Medium | Use `chardet` for encoding detection; strip BOM on parse |
| **Large file imports** (>1000 rows) blocking | Medium | Batch inserts in chunks of 100; async progress reporting via polling or WebSocket |
| **JSONB query performance** at scale | Low | Current scale (50-500 SKUs/tenant) is trivial for JSONB. Add GIN index if needed later |
| **Field mapping UX complexity** on mobile | Medium | Design mobile-first mapping wizard; use dropdowns instead of drag-and-drop |
| **Migration rollback** if custom_attributes causes issues | Low | JSONB column is nullable with default — safe to add, safe to ignore |
| **Duplicate sku_code handling** in batch | Medium | Support `on_conflict: skip | update | error` strategies — let tenant choose |
| **Data quality** from messy spreadsheets | High | Provide clear validation feedback with row numbers; require manual fix before import |

### 6.2 Open Questions for CTO

1. **Custom attributes scope**: Should custom attributes be searchable/filterable in the product list, or display-only initially? (Recommendation: display-only for MVP, searchable in Phase 5)

2. **Conflict strategy default**: When importing SKUs that already exist, should the default be `skip` or `error`? (Recommendation: `skip` with clear count in results)

3. **Tenant attribute sharing**: Should attribute definitions be shareable across tenants (e.g., a "standard FMCG attribute pack"), or purely per-tenant? (Recommendation: per-tenant for MVP)

4. **Import permission scope**: The existing RBAC system already enforces `skus:read`, `skus:create`, `skus:update` (see Section 1.7). U3-B MUST create a new `skus:import` permission rather than reusing `skus:create`. The rationale: import is a bulk operation with file upload, different error semantics, and higher blast radius — tenants should be able to grant "add products one at a time" without also granting "upload 500 products at once." The `skus:import` permission will be assigned to `admin` at bootstrap. Open question: should `warehouse` also get `skus:import`? (Recommendation: yes — warehouse staff frequently handle stock intake with product data.)

5. **File size limit**: Maximum CSV file size for import? (Recommendation: 5MB / 5000 rows for MVP — covers 95% of target users)

6. **Category standardization**: Should categories be free-text or from a predefined list? Currently free-text. Import would benefit from a category picker or auto-suggest. (Recommendation: keep free-text for MVP, add category management in Phase 5)

7. **Inventory initial quantity**: When importing SKUs, should users also be able to set initial stock quantities in the same import? The `inventory_stocks` row is auto-created at 0. (Recommendation: defer to separate "stock adjustment import" feature — keep SKU import focused on product data)

---

## 7. Exact Files Read

### Backend — Models
| File | Purpose |
|------|---------|
| `backend/models/sku.py` | SKU ORM model — 6 business fields, no extensibility |
| `backend/models/base.py` | BaseModel, AuditMixin, UserTrackingMixin inheritance chain |
| `backend/models/inventory_stock.py` | InventoryStock — 1:1 per SKU, auto-created |
| `backend/models/inventory_movement.py` | InventoryMovement — stock audit journal |
| `backend/models/retailer_price.py` | RetailerPrice — pricing is separate from SKU |
| `backend/models/order.py` | Order + OrderItem — denormalized sku_code reference |
| `backend/models/audit.py` | SysAuditLog — JSONB `metadata_` precedent |
| `backend/models/platform_tenant.py` | PlatformTenant — JSONB `provisioning_log` precedent |

### Backend — API / Services / Repositories
| File | Purpose |
|------|---------|
| `backend/api/v1/skus.py` | SKU CRUD routes — single-record only |
| `backend/services/sku_service.py` | SKUService — create_sku with duplicate check |
| `backend/repositories/sku_repository.py` | SKURepository — basic CRUD operations |
| `backend/schemas/sku.py` | Pydantic schemas — mirrors DB columns exactly |
| `backend/api/v1/inventory.py` | Inventory routes — shows stock lifecycle |
| `backend/services/inventory_service.py` | InventoryService — SELECT FOR UPDATE pattern |
| `backend/api/v1/pricing.py` | Pricing routes — retailer+SKU pricing |
| `backend/core/domain/order_state.py` | Order state machine — references sku_code |

### Backend — Infrastructure
| File | Purpose |
|------|---------|
| `backend/db/tenant_filter.py` | Schema-per-tenant filtering via SQLAlchemy event |
| `backend/scripts/seed_demo_data.py` | Demo seeder — 10 Kenyan FMCG products |
| `backend/scripts/bootstrap_tenant_schema.py` | Tenant bootstrap DDL — all table CREATE statements |
| `backend/alembic/versions/004_phase_b4_sku_inventory_mvp.py` | Migration creating `skus` + `inventory_stocks` |
| `backend/alembic/versions/017_retailer_prices.py` | Migration creating `retailer_prices` |

### Frontend
| File | Purpose |
|------|---------|
| `frontend/src/services/skuService.ts` | SKU API service — getAll, create, update |
| `frontend/src/pages/skus/SKUFormModal.tsx` | SKU creation/edit form — 5 fields |
| `frontend/src/pages/skus/SKUListPage.tsx` | SKU list with empty state + import placeholder |
| `frontend/src/types/inventory.ts` | StockView type |
| `frontend/src/types/pricing.ts` | RetailerPriceView type |
| `frontend/src/types/order.ts` | Order types |
| `frontend/src/types/client.ts` | Client-facing product types |
| `frontend/src/services/clientProductService.ts` | Retailer-facing product service |

### U3-A-R1 Additional Files Read (Permission System)
| File | Purpose |
|------|---------|
| `backend/api/middleware/rbac.py` | `RequirePermission` dependency — enforces `<resource>:<action>` checks |
| `backend/core/governance/roles.py` | Default BI permission matrix, role-action mapping |
| `backend/core/governance/policy.py` | BI policy engine with evaluation order |
| `backend/api/context/auth_context.py` | JWT bearer, token decoding, tenant schema resolution |
| `backend/models/user.py` | User, Role, Permission ORM models (M2M through `user_roles`, `role_permissions`) |
| `backend/api/v1/skus.py` | Existing SKU routes already enforce `skus:read`, `skus:create`, `skus:update` |
| `backend/scripts/create_wholesaler.py` | Full permission list + admin assignment — where `skus:import` must be added |
| `backend/scripts/seed_demo_data.py` | Demo seeder including RBAC — where `skus:import` must be added |

---

## 8. Proposed U3-B Implementation Plan (4 Sub-Slices)

### 8.1 Branch Strategy

```
Branch: codebuddy/u3b-product-csv-import-2026-06-12
Base:   origin/product-dev-recovered
```

### 8.2 Slice U3-B1: Permission Foundation (0.5 day)

**Commit:** `u3b1_permission_skus_import`

1. Add `("skus:import", "Import SKUs in bulk via CSV upload")` to `create_wholesaler.py` → `permissions_data` list
2. Add `("skus:import", "Import SKUs")` to `seed_demo_data.py` → `PERMISSION_CODES` list
3. Verify: run bootstrap → `skus:import` exists in `permissions` table, `admin` role holds it
4. No API route changes in this slice

### 8.3 Slice U3-B2: Backend Batch + CSV Import (1.5 days)

**Commit:** `u3b2_backend_batch_csv_import`

1. Create Alembic migration adding `custom_attributes JSONB DEFAULT '{}'` to `skus`
2. Update `SKU` model (`backend/models/sku.py`) — add `custom_attributes` column
3. Update Pydantic schemas (`backend/schemas/sku.py`) — add `custom_attributes` to Create/Update/Read
4. Implement `POST /api/v1/skus/batch` endpoint:
   - Array input validation
   - Duplicate `sku_code` detection within batch + against existing
   - `on_conflict` strategy (skip / update / error)
   - Row-level error reporting
   - **Protected by `RequirePermission("skus:import")`**
5. Implement `POST /api/v1/skus/import` endpoint:
   - Accept `multipart/form-data` CSV file upload
   - Parse CSV with `chardet` encoding detection
   - Return `{columns, rows_preview, row_count}`
   - **Protected by `RequirePermission("skus:import")`**
6. Create `ImportService.parse_csv()` (`backend/services/import_service.py`)
7. Unit tests: batch duplicates, partial failure, CSV encoding edge cases, 403 on missing permission

### 8.4 Slice U3-B3: Frontend Import Wizard (2 days)

**Commit:** `u3b3_frontend_import_wizard`

1. Create `frontend/src/services/importService.ts` — `uploadCSV()`, `batchImport()`
2. Create ImportWizard component structure under `frontend/src/pages/skus/ImportWizard/`:
   - `Step1Upload.tsx` — file drop zone, calls `/skus/import`, shows raw preview
   - `Step2FieldMapping.tsx` — dropdown selectors mapping CSV columns to Mpango fields, unmapped → custom attribute
   - `Step3Preview.tsx` — mapped data preview, validation error highlights, confirm button → `/skus/batch`, results summary
3. Wire up ImportWizard from SKUListPage "Import Products" button (replacing disabled placeholder)

### 8.5 Slice U3-B4: Custom Attributes in SKU UI (1 day)

**Commit:** `u3b4_custom_attributes_ui`

1. Update `SKUFormModal.tsx` — key-value pair editor for custom attributes
2. Update `SKUListPage.tsx` — show custom attribute columns, toggle visibility
3. Update `skuService.ts` — support `custom_attributes` in create/update payloads

### 8.6 Validation Commands

```bash
pnpm lint                          # 0 errors
pnpm build                         # pass
git diff --check origin/product-dev-recovered..HEAD  # no whitespace issues
```

### 8.7 Definition of Done

- [ ] `skus:import` permission exists, enforced on batch/import endpoints, admin role holds it
- [ ] Tenant can upload a CSV file with any column structure
- [ ] Field mapping wizard correctly maps CSV columns to Mpango fields
- [ ] Unmapped columns are stored as custom attributes
- [ ] Batch import creates SKUs with row-level error reporting
- [ ] Both batch/import endpoints return 403 without `skus:import`
- [ ] Existing single-SKU creation flow unchanged, still requires `skus:create`
- [ ] Import results show created/skipped/errored counts
- [ ] No production code changes outside the U3-B scope

---

## Appendix A: CSV Import Flow Diagram

```
┌─────────────┐     ┌──────────────┐     ┌────────────────┐     ┌──────────────┐
│  Upload CSV  │────▶│  Parse &     │────▶│  Field Mapping │────▶│  Preview &   │
│  File        │     │  Detect Cols │     │  (user maps    │     │  Validate    │
└─────────────┘     └──────────────┘     │  columns)      │     └──────┬───────┘
                                         └────────────────┘            │
                                                                       ▼
                                                              ┌──────────────┐
                                                              │  POST        │
                                                              │  /skus/batch │
                                                              └──────┬───────┘
                                                                     │
                                                         ┌───────────┴──────────┐
                                                         ▼                      ▼
                                                  ┌─────────────┐     ┌──────────────┐
                                                  │  Success:   │     │  Errors:     │
                                                  │  N created  │     │  Row-level   │
                                                  │  M skipped  │     │  details     │
                                                  └─────────────┘     └──────────────┘
```

## Appendix B: Field Mapping UI Wireframe

```
┌─────────────────────────────────────────────────────┐
│  Map Your Columns to Mpango Products                │
│─────────────────────────────────────────────────────│
│                                                     │
│  Your CSV Columns          Mpango Fields            │
│  ┌──────────────┐          ┌──────────────────┐     │
│  │ Product Code │─────────▶│ sku_code *       │     │
│  └──────────────┘          └──────────────────┘     │
│  ┌──────────────┐          ┌──────────────────┐     │
│  │ Product Name │─────────▶│ name *           │     │
│  └──────────────┘          └──────────────────┘     │
│  ┌──────────────┐          ┌──────────────────┐     │
│  │ Category     │─────────▶│ category         │     │
│  └──────────────┘          └──────────────────┘     │
│  ┌──────────────┐          ┌──────────────────┐     │
│  │ Unit Type    │─────────▶│ unit             │     │
│  └──────────────┘          └──────────────────┘     │
│  ┌──────────────┐          ┌──────────────────┐     │
│  │ Brand        │─────────▶│ + Custom Attr    │     │
│  └──────────────┘          │  "brand"         │     │
│                            └──────────────────┘     │
│  ┌──────────────┐          ┌──────────────────┐     │
│  │ Weight       │─────────▶│ + Custom Attr    │     │
│  └──────────────┘          │  "weight"        │     │
│                            └──────────────────┘     │
│                                                     │
│  * Required fields                                  │
│                                                     │
│  [  Back  ]                          [ Next: Preview ]│
└─────────────────────────────────────────────────────┘
```

---

**End of U3-A-R1 Discovery Report — Awaiting CTO Final Approval**

### R1 Revision Changelog

| Change | Section(s) |
|--------|------------|
| Corrected "no permission gating" claim — RBAC system documented | 1.7 (new), 2.2.7, 6.2.4, 7 (appended) |
| Defined `skus:import` as a new permission (not reuse `skus:create`) | 1.7, 4.1, 4.2, 8.7 |
| Split U3-B into 4 sub-slices (B1: Permission, B2: Backend, B3: Frontend, B4: UI) | 4.3, 5, 8.2-8.5 |
| Removed "Role-based import permissions" from Out of Scope | 4.2 |
| Added sub-slice commit strategy to implementation plan | 8.2-8.5 |
| Added Definition of Done item for 403 on missing `skus:import` | 8.7 |
| No mojibake found — all text confirmed valid UTF-8 / proper box-drawing characters | (file scan) |
